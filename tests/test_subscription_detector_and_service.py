from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional
from email.message import EmailMessage as PyEmailMessage

import email_management.subscription.detector as detector_mod
import email_management.subscription.service as service_mod
from email_management.subscription.detector import SubscriptionDetector
from email_management.subscription.service import SubscriptionService
from email_management.models import (
    EmailMessage,
    UnsubscribeCandidate,
    UnsubscribeMethod,
    UnsubscribeActionResult,
)
from email_management.types import EmailRef, SendResult

from tests.fake_imap_client import FakeIMAPClient
from tests.fake_smtp_client import FakeSMTPClient


def make_unsubscribe_candidate(
    uid: int,
    *,
    from_email: str = "news@example.com",
    subject: str = "Newsletter",
    methods: Optional[List[UnsubscribeMethod]] = None,
) -> UnsubscribeCandidate:
    ref = EmailRef(uid=uid, mailbox="INBOX")
    if methods is None:
        methods = [UnsubscribeMethod(kind="mailto", value="unsubscribe@example.com")]
    return UnsubscribeCandidate(
        ref=ref,
        from_email=from_email,
        subject=subject,
        methods=methods,
    )


class RecordingFakeIMAPClient(FakeIMAPClient):
    """FakeIMAPClient plus call recording for assertions."""

    def __init__(self):
        super().__init__()
        self.search_page_cached_calls = []
        self.fetch_calls = []

    def search_page_cached(
        self,
        *,
        mailbox: str,
        query,
        page_size: int = 50,
        before_uid=None,
        after_uid=None,
        refresh: bool = False,
    ):
        self.search_page_cached_calls.append(
            (mailbox, query, page_size, before_uid, after_uid, refresh)
        )
        return super().search_page_cached(
            mailbox=mailbox,
            query=query,
            page_size=page_size,
            before_uid=before_uid,
            after_uid=after_uid,
            refresh=refresh,
        )

    def fetch(self, refs, *, include_attachments: bool = False):
        self.fetch_calls.append((list(refs), include_attachments))
        return super().fetch(refs, include_attachments=include_attachments)


def _mk_email_message(*, subject: str, from_email: str, headers: dict) -> EmailMessage:
    # FakeIMAPClient.add_parsed_message() will overwrite the ref.
    placeholder_ref = EmailRef(uid=0, mailbox="__seed__")
    return EmailMessage(
        ref=placeholder_ref,
        subject=subject,
        from_email=from_email,
        to=[],
        cc=[],
        bcc=[],
        text="",
        html="",
        attachments=[],
        date=datetime(2025, 1, 2, tzinfo=timezone.utc),
        message_id=None,
        headers=headers,
    )


def _sent_msg(record):
    """
    FakeSMTPClient implementations vary:
    - sometimes smtp.sent contains message objects directly
    - sometimes it contains objects with a `.msg` attribute
    This helper makes the test resilient.
    """
    return getattr(record, "msg", record)


def test_subscription_detector_builds_candidates_and_uses_query(monkeypatch):
    """
    - unseen_only=True -> IMAPQuery.unseen() is included in query
    - since is applied via IMAPQuery.since()
    - search_page_cached/fetch are called correctly
    - only messages with List-Unsubscribe and parsed methods become candidates
    """

    def fake_parse_list_unsubscribe(header_value: str) -> List[UnsubscribeMethod]:
        if "unsub1" in header_value:
            return [UnsubscribeMethod(kind="mailto", value="unsub1@example.com")]
        if "unsub2" in header_value:
            return [
                UnsubscribeMethod(kind="http", value="https://example.com/unsub2"),
                UnsubscribeMethod(kind="mailto", value="unsub2@example.com"),
            ]
        return []

    # detector module imports parse_list_unsubscribe into its namespace
    monkeypatch.setattr(detector_mod, "parse_list_unsubscribe", fake_parse_list_unsubscribe)

    imap = RecordingFakeIMAPClient()

    # Seed 3 messages into NEWS
    ref1 = imap.add_parsed_message(
        "NEWS",
        _mk_email_message(
            from_email="sender1@example.com",
            subject="Subject 1",
            headers={"List-Unsubscribe": "<mailto:unsub1@example.com>"},
        ),
    )
    ref2 = imap.add_parsed_message(
        "NEWS",
        _mk_email_message(
            from_email="sender2@example.com",
            subject="Subject 2",
            headers={},
        ),
    )
    ref3 = imap.add_parsed_message(
        "NEWS",
        _mk_email_message(
            from_email="sender3@example.com",
            subject="Subject 3",
            headers={"List-Unsubscribe": "<mailto:ignore@example.com>"},
        ),
    )

    detector = SubscriptionDetector(imap)

    cands = detector.find(
        mailbox="NEWS",
        limit=3,
        since="2025-01-01",
        unseen_only=True,
    )

    # One candidate from msg1
    assert len(cands) == 1
    cand = cands[0]
    assert isinstance(cand, UnsubscribeCandidate)
    assert cand.ref == ref1
    assert cand.from_email == "sender1@example.com"
    assert cand.subject == "Subject 1"
    assert len(cand.methods) == 1
    assert cand.methods[0].kind == "mailto"
    assert cand.methods[0].value == "unsub1@example.com"

    # IMAP search usage: search_page_cached called once
    assert len(imap.search_page_cached_calls) == 1
    mailbox, query_obj, page_size, before_uid, after_uid, refresh = imap.search_page_cached_calls[0]
    assert mailbox == "NEWS"
    assert page_size == 3
    assert before_uid is None
    assert after_uid is None

    built = query_obj.build()
    assert "UNSEEN" in built
    # IMAPQuery.since("YYYY-MM-DD") formats to SINCE DD-Mon-YYYY
    assert "SINCE 01-Jan-2025" in built

    # fetch called once with the refs returned by search_page_cached
    assert len(imap.fetch_calls) == 1
    fetched_refs, include_attachments = imap.fetch_calls[0]
    assert include_attachments is False
    assert set(fetched_refs) == {ref1, ref2, ref3}


def test_get_header_is_case_insensitive():
    """Small unit test for internal _get_header helper."""
    h = {"List-Unsubscribe": "<mailto:x@example.com>", "Other": "value"}
    assert detector_mod._get_header(h, "List-Unsubscribe") == "<mailto:x@example.com>"
    assert detector_mod._get_header(h, "list-unsubscribe") == "<mailto:x@example.com>"
    assert detector_mod._get_header(h, "missing") == ""


def test_unsubscribe_mailto_sends_email():
    smtp = FakeSMTPClient(config=type("Cfg", (), {"from_email": "fallback@example.com"})())
    svc = SubscriptionService(smtp)

    cand = make_unsubscribe_candidate(
        uid=1,
        methods=[UnsubscribeMethod(kind="mailto", value="unsub@example.com")],
    )
    result = svc.unsubscribe(
        [cand],
        prefer="mailto",
        from_addr="me@example.com",
    )

    # Check SMTP message
    assert len(smtp.sent) == 1
    msg = _sent_msg(smtp.sent[0])

    assert msg["To"] == "unsub@example.com"
    assert msg["Subject"] == "Unsubscribe"
    assert msg["From"] == "me@example.com"
    assert msg.get_content().strip() == "Please unsubscribe me."

    # Check results structure
    sent = result["sent"]
    assert len(sent) == 1
    r = sent[0]
    assert isinstance(r, UnsubscribeActionResult)
    assert r.ref == cand.ref
    assert r.method.kind == "mailto"
    assert r.method.value == "unsub@example.com"
    assert r.sent is True

    assert isinstance(r.send_result, SendResult)

    assert result["http"] == []
    assert result["skipped"] == []


def test_unsubscribe_http_method_uses_http_flow(monkeypatch):
    """
    HTTP unsubscribe should:
    - not send any SMTP email
    - call _http_unsubscribe_flow()
    - populate result in the 'http' bucket with a SendResult
    """
    smtp = FakeSMTPClient(config=type("Cfg", (), {"from_email": "fallback@example.com"})())
    svc = SubscriptionService(smtp)

    cand = make_unsubscribe_candidate(
        uid=1,
        methods=[UnsubscribeMethod(kind="http", value="https://example.com/unsub")],
    )

    called = {}

    def fake_http_unsubscribe_flow(url: str, timeout: int = 10):
        called["url"] = url
        called["timeout"] = timeout
        return True, "fake-ok-detail"

    monkeypatch.setattr(service_mod, "_http_unsubscribe_flow", fake_http_unsubscribe_flow)

    result = svc.unsubscribe(
        [cand],
        prefer="mailto",  # prefer mailto, but only http method exists
        from_addr="me@example.com",
    )

    # No SMTP activity
    assert smtp.sent == []

    assert called["url"] == "https://example.com/unsub"
    assert called["timeout"] == 10

    assert result["sent"] == []
    assert result["skipped"] == []
    assert len(result["http"]) == 1

    r = result["http"][0]
    assert isinstance(r, UnsubscribeActionResult)
    assert r.ref == cand.ref
    assert r.method.kind == "http"
    assert r.method.value == "https://example.com/unsub"
    assert r.sent is True
    assert r.send_result.ok is True
    assert r.send_result.detail == "fake-ok-detail"


def test_unsubscribe_http_flow_failure_goes_to_http_with_error(monkeypatch):
    """
    If the HTTP unsubscribe flow raises, the candidate should:
    - still end up in the 'http' bucket
    - have sent=False
    - have send_result.ok=False with the error message in detail
    - have note == "HTTP request failed"
    """
    smtp = FakeSMTPClient(config=type("Cfg", (), {"from_email": "fallback@example.com"})())
    svc = SubscriptionService(smtp)

    cand = make_unsubscribe_candidate(
        uid=1,
        methods=[UnsubscribeMethod(kind="http", value="https://example.com/unsub")],
    )

    def fake_http_unsubscribe_flow_raises(url: str, timeout: int = 10):
        raise RuntimeError("boom-error")

    monkeypatch.setattr(service_mod, "_http_unsubscribe_flow", fake_http_unsubscribe_flow_raises)

    result = svc.unsubscribe(
        [cand],
        prefer="http",
        from_addr="me@example.com",
    )

    assert smtp.sent == []

    assert result["sent"] == []
    assert result["skipped"] == []
    assert len(result["http"]) == 1

    r = result["http"][0]
    assert isinstance(r, UnsubscribeActionResult)
    assert r.ref == cand.ref
    assert r.method.kind == "http"
    assert r.method.value == "https://example.com/unsub"
    assert r.sent is False
    assert r.note == "HTTP request failed"
    assert r.send_result.ok is False
    assert "boom-error" in r.send_result.detail


def test_unsubscribe_no_supported_method_goes_to_skipped():
    smtp = FakeSMTPClient(config=type("Cfg", (), {"from_email": "fallback@example.com"})())
    svc = SubscriptionService(smtp)

    cand = make_unsubscribe_candidate(uid=1, methods=[])

    result = svc.unsubscribe(
        [cand],
        prefer="mailto",
        from_addr="me@example.com",
    )

    assert result["sent"] == []
    assert result["http"] == []
    assert len(result["skipped"]) == 1

    r = result["skipped"][0]
    assert isinstance(r, UnsubscribeActionResult)
    assert r.ref == cand.ref
    assert r.method is None
    assert r.sent is False
    assert r.note == "No supported unsubscribe method"
