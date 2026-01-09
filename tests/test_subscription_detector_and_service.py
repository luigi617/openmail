from __future__ import annotations
from typing import List, Optional
from email.message import EmailMessage as PyEmailMessage
import email_management.subscription.detector as detector_mod
import email_management.subscription.service as service_mod
from email_management.subscription.detector import SubscriptionDetector
from email_management.subscription.service import SubscriptionService
from email_management.models import (
    UnsubscribeCandidate,
    UnsubscribeMethod,
    UnsubscribeActionResult,
)
from email_management.types import EmailRef

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

class FakeMessage:
    """Minimal message object with attributes used by SubscriptionDetector."""

    def __init__(self, from_email: str, subject: str, headers: dict):
        self.from_email = from_email
        self.subject = subject
        self.headers = headers

class FakeIMAPClient:
    """Fake IMAP client for SubscriptionDetector tests."""

    def __init__(self, refs, msgs):
        self._refs = refs
        self._msgs = msgs
        self.search_calls = []
        self.fetch_calls = []

    def search(self, *, mailbox, query, limit):
        
        self.search_calls.append((mailbox, query, limit))
        
        return self._refs[:limit]

    def fetch(self, refs):
        
        self.fetch_calls.append(list(refs))
        
        idx_by_ref = {r: i for i, r in enumerate(self._refs)}
        return [self._msgs[idx_by_ref[r]] for r in refs]


class FakeIMAPQuery:
    """Fake IMAPQuery to track unseen/since usage."""

    instances: List["FakeIMAPQuery"] = []

    def __init__(self):
        self.__class__.instances.append(self)
        self.unseen_called = False
        self.since_args: List[str] = []

    def unseen(self):
        self.unseen_called = True
        return self

    def since(self, date_str: str):
        self.since_args.append(date_str)
        return self


class FakeSMTPClient:
    """Fake SMTP client for SubscriptionService tests."""

    def __init__(self):
        self.sent_messages: List[PyEmailMessage] = []

    def send(self, msg: PyEmailMessage):
        self.sent_messages.append(msg)
        return "smtp-send-result"



def test_subscription_detector_builds_candidates_and_uses_query(monkeypatch):
    """
    - unseen_only=True -> IMAPQuery.unseen() is called
    - since is applied via IMAPQuery.since()
    - search/fetch are called correctly
    - only messages with List-Unsubscribe and parsed methods become candidates
    """
    
    monkeypatch.setattr(detector_mod, "IMAPQuery", FakeIMAPQuery)

    
    def fake_parse_list_unsubscribe(header_value: str) -> List[UnsubscribeMethod]:
        if "unsub1" in header_value:
            return [UnsubscribeMethod(kind="mailto", value="unsub1@example.com")]
        if "unsub2" in header_value:
            return [
                UnsubscribeMethod(kind="http", value="https://example.com/unsub2"),
                UnsubscribeMethod(kind="mailto", value="unsub2@example.com"),
            ]
        
        return []

    monkeypatch.setattr(detector_mod, "parse_list_unsubscribe", fake_parse_list_unsubscribe)

    
    ref1 = EmailRef(uid=1)
    ref2 = EmailRef(uid=2)
    ref3 = EmailRef(uid=3)

    msg1 = FakeMessage(
        from_email="sender1@example.com",
        subject="Subject 1",
        headers={"List-Unsubscribe": "<mailto:unsub1@example.com>"},
    )
    
    msg2 = FakeMessage(
        from_email="sender2@example.com",
        subject="Subject 2",
        headers={},
    )
    
    msg3 = FakeMessage(
        from_email="sender3@example.com",
        subject="Subject 3",
        headers={"List-Unsubscribe": "<mailto:ignore@example.com>"},
    )

    refs = [ref1, ref2, ref3]
    msgs = [msg1, msg2, msg3]

    imap = FakeIMAPClient(refs, msgs)
    detector = SubscriptionDetector(imap)

    cands = detector.find(
        mailbox="NEWS",
        limit=3,
        since="2025-01-01",
        unseen_only=True,
    )

    
    assert len(cands) == 1
    cand = cands[0]
    assert isinstance(cand, UnsubscribeCandidate)
    assert cand.ref is ref1
    assert cand.from_email == "sender1@example.com"
    assert cand.subject == "Subject 1"
    assert len(cand.methods) == 1
    assert cand.methods[0].kind == "mailto"
    assert cand.methods[0].value == "unsub1@example.com"

    
    assert len(imap.search_calls) == 1
    mailbox, query_obj, limit_used = imap.search_calls[0]
    assert mailbox == "NEWS"
    assert limit_used == 3
    assert isinstance(query_obj, FakeIMAPQuery)

    
    assert FakeIMAPQuery.instances, "Expected at least one FakeIMAPQuery instance"
    q = FakeIMAPQuery.instances[-1]
    assert q.unseen_called is True
    assert q.since_args == ["2025-01-01"]

    
    assert len(imap.fetch_calls) == 1
    assert imap.fetch_calls[0] == refs[:3]


def test_get_header_is_case_insensitive():
    """Small unit test for internal _get_header helper."""
    h = {"List-Unsubscribe": "<mailto:x@example.com>", "Other": "value"}
    assert detector_mod._get_header(h, "List-Unsubscribe") == "<mailto:x@example.com>"
    assert detector_mod._get_header(h, "list-unsubscribe") == "<mailto:x@example.com>"
    assert detector_mod._get_header(h, "missing") == ""



def test_unsubscribe_mailto_dry_run_does_not_send_email():
    smtp = FakeSMTPClient()
    svc = SubscriptionService(smtp)

    cand = make_unsubscribe_candidate(
        uid=1,
        methods=[UnsubscribeMethod(kind="mailto", value="unsub@example.com")],
    )

    result = svc.unsubscribe(
        [cand],
        prefer="mailto",
        from_addr="me@example.com",
        dry_run=True,
    )

    
    assert smtp.sent_messages == []

    
    assert isinstance(result, dict)
    assert set(result.keys()) == {"sent", "http", "skipped"}

    sent = result["sent"]
    assert len(sent) == 1
    r = sent[0]
    assert isinstance(r, UnsubscribeActionResult)
    assert r.ref is cand.ref
    assert r.method.kind == "mailto"
    assert r.method.value == "unsub@example.com"
    assert r.sent is False
    assert r.note == "dry-run"
    assert result["http"] == []
    assert result["skipped"] == []


def test_unsubscribe_mailto_sends_email_when_not_dry_run():
    smtp = FakeSMTPClient()
    svc = SubscriptionService(smtp)

    cand = make_unsubscribe_candidate(
        uid=1,
        methods=[UnsubscribeMethod(kind="mailto", value="unsub@example.com")],
    )

    result = svc.unsubscribe(
        [cand],
        prefer="mailto",
        from_addr="me@example.com",
        dry_run=False,
    )

    
    assert len(smtp.sent_messages) == 1
    msg = smtp.sent_messages[0]
    assert msg["To"] == "unsub@example.com"
    assert msg["Subject"] == "unsubscribe"
    assert msg["From"] == "me@example.com"
    assert msg.get_content().strip() == "unsubscribe"

    
    sent = result["sent"]
    assert len(sent) == 1
    r = sent[0]
    assert r.sent is True
    assert r.send_result == "smtp-send-result"
    assert result["http"] == []
    assert result["skipped"] == []


def test_unsubscribe_http_method_goes_to_http_bucket():
    smtp = FakeSMTPClient()
    svc = SubscriptionService(smtp)

    cand = make_unsubscribe_candidate(
        uid=1,
        methods=[UnsubscribeMethod(kind="http", value="https://example.com/unsub")],
    )

    result = svc.unsubscribe(
        [cand],
        prefer="mailto",  
        from_addr="me@example.com",
        dry_run=False,
    )

    assert smtp.sent_messages == []

    sent = result["sent"]
    skipped = result["skipped"]
    http = result["http"]

    assert sent == []
    assert skipped == []
    assert len(http) == 1

    r = http[0]
    assert isinstance(r, UnsubscribeActionResult)
    assert r.ref is cand.ref
    assert r.method.kind == "http"
    assert r.method.value == "https://example.com/unsub"
    assert r.sent is False
    assert r.note == "manual http unsubscribe"


def test_unsubscribe_no_supported_method_goes_to_skipped():
    smtp = FakeSMTPClient()
    svc = SubscriptionService(smtp)

    
    cand = make_unsubscribe_candidate(uid=1, methods=[])

    result = svc.unsubscribe(
        [cand],
        prefer="mailto",
        from_addr="me@example.com",
        dry_run=False,
    )

    assert result["sent"] == []
    assert result["http"] == []
    assert len(result["skipped"]) == 1

    r = result["skipped"][0]
    assert isinstance(r, UnsubscribeActionResult)
    assert r.ref is cand.ref
    
    assert r.method is None
    assert r.sent is False
    assert r.note == "No supported unsubscribe method"
