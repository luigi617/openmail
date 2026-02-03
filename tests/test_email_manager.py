# tests/test_email_manager.py

from __future__ import annotations

from datetime import datetime
from email.message import EmailMessage as PyEmailMessage

import pytest

from openmail.email_manager import EmailManager
from openmail.models import Attachment, EmailMessage, UnsubscribeCandidate, UnsubscribeMethod
from openmail.types import EmailRef
from openmail.utils import ensure_forward_subject, ensure_reply_subject
from tests.fake_imap_client import FakeIMAPClient
from tests.fake_smtp_client import FakeSMTPClient

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def fake_imap() -> FakeIMAPClient:
    return FakeIMAPClient()


@pytest.fixture
def fake_smtp() -> FakeSMTPClient:
    # Ensure config.from_email exists if EmailManager injects From in some paths.
    class Cfg:
        from_email = "me@example.com"
    return FakeSMTPClient(config=Cfg())


@pytest.fixture
def manager(fake_imap: FakeIMAPClient, fake_smtp: FakeSMTPClient) -> EmailManager:
    return EmailManager(smtp=fake_smtp, imap=fake_imap)


def make_email_message(
    uid: int = 1,
    mailbox: str = "INBOX",
    *,
    subject: str = "Hello",
    from_email: str = "alice@example.com",
    to: list[str] | None = None,
    cc: list[str] | None = None,
    bcc: list[str] | None = None,
    text: str | None = "Body text",
    html: str | None = None,
    received_at: datetime | None = None,
    sent_at: datetime | None = None,
    message_id: str | None = "<msg-1@example.com>",
    headers: dict[str, str] | None = None,
    attachments: list[Attachment] | None = None,
) -> EmailMessage:
    if to is None:
        to = ["bob@example.com"]
    if cc is None:
        cc = []
    if bcc is None:
        bcc = []
    if headers is None:
        headers = {}
    if attachments is None:
        attachments = []

    return EmailMessage(
        ref=EmailRef(uid=uid, mailbox=mailbox),
        subject=subject,
        from_email=from_email,
        to=to,
        cc=cc,
        bcc=bcc,
        text=text,
        html=html,
        attachments=attachments,
        received_at=received_at,
        sent_at=sent_at,
        message_id=message_id,
        headers=headers,
    )


def get_text_and_html_from_pymsg(msg: PyEmailMessage) -> tuple[str | None, str | None]:
    """Inspect what EmailManager._set_body produced."""
    if msg.is_multipart():
        text = None
        html = None
        for part in msg.walk():
            if part.is_multipart():
                continue
            ctype = part.get_content_type()
            disp = (part.get_content_disposition() or "").lower()
            if disp not in ("", "inline"):
                continue
            if ctype == "text/plain":
                text = part.get_content()
            elif ctype == "text/html":
                html = part.get_content()
        return text, html
    else:
        ctype = msg.get_content_type()
        content = msg.get_content()
        if ctype == "text/html":
            return None, content
        return content, None


# ---------------------------------------------------------------------------
# compose / send / save_draft
# ---------------------------------------------------------------------------

def test_compose_text_html_attachments(manager: EmailManager):
    att = Attachment(
        idx=1,
        part="part",
        filename="test.txt",
        content_type="text/plain",
        data=b"hello",
        size=len(b"hello"),
    )

    msg = manager.compose(
        subject="Subject",
        to=["user@example.com"],
        from_addr="me@example.com",
        cc=["cc@example.com"],
        bcc=["bcc@example.com"],
        text="Plain",
        html="<p>HTML</p>",
        attachments=[att],
        extra_headers={"X-Custom": "value", "subject": "should-be-ignored"},
    )

    assert msg["From"] == "me@example.com"
    assert msg["To"] == "user@example.com"
    assert msg["Cc"] == "cc@example.com"
    assert msg["Bcc"] == "bcc@example.com"
    assert msg["Subject"] == "Subject"
    assert msg["X-Custom"] == "value"
    assert "should-be-ignored" not in msg.as_string()

    text, html = get_text_and_html_from_pymsg(msg)
    assert (text or "").strip() == "Plain"
    assert "<p>HTML</p>" in (html or "")

    filenames = [p.get_filename() for p in msg.walk() if p.get_filename()]
    assert "test.txt" in filenames


def test_compose_and_send_requires_some_recipient(manager: EmailManager):
    # compose_and_send enforces at least one of to/cc/bcc non-empty
    with pytest.raises(ValueError):
        manager.compose_and_send(subject="No one", to=[])


def test_send_and_compose_and_send_records_email(manager: EmailManager, fake_smtp: FakeSMTPClient):
    result = manager.compose_and_send(
        subject="Hi",
        to=["to@example.com"],
        from_addr="me@example.com",
        text="Body",
    )
    assert result.ok
    assert len(fake_smtp.sent) == 1

    record = fake_smtp.sent[0]
    assert record.from_email == "me@example.com"
    assert record.recipients == ["to@example.com"]


def test_save_draft_appends_to_drafts_with_flag(manager: EmailManager, fake_imap: FakeIMAPClient):
    ref = manager.save_draft(
        subject="Draft",
        to=["d@example.com"],
        from_addr="me@example.com",
        text="Draft body",
    )

    assert ref.mailbox == "Drafts"
    box = fake_imap._mailboxes["Drafts"]
    stored = box[ref.uid]
    assert stored.msg.subject == "Draft"
    assert r"\Draft" in stored.flags


# ---------------------------------------------------------------------------
# fetch APIs
# ---------------------------------------------------------------------------

def test_fetch_message_by_ref_and_multi_refs(manager: EmailManager, fake_imap: FakeIMAPClient):
    m1 = make_email_message(
        uid=1,
        text="m1",
        attachments=[Attachment(idx=1, part="part1", filename="a.txt", content_type="text/plain", data=b"a", size=1)],
    )
    m2 = make_email_message(
        uid=2,
        text="m2",
        attachments=[Attachment(idx=2, part="part2", filename="b.txt", content_type="text/plain", data=b"b", size=1)],
    )
    ref1 = fake_imap.add_parsed_message("INBOX", m1)
    ref2 = fake_imap.add_parsed_message("INBOX", m2)

    msg1_no_atts = manager.fetch_message_by_ref(ref1, include_attachment_meta=False)
    assert msg1_no_atts.text == "m1"
    assert msg1_no_atts.attachments == []

    msg1_with_atts = manager.fetch_message_by_ref(ref1, include_attachment_meta=True)
    assert len(msg1_with_atts.attachments) == 1

    msgs = manager.fetch_messages_by_multi_refs([ref1, ref2], include_attachment_meta=False)
    texts = {m.text for m in msgs}
    assert texts == {"m1", "m2"}


def test_fetch_message_by_ref_missing_raises(manager: EmailManager):
    with pytest.raises(ValueError):
        manager.fetch_message_by_ref(EmailRef(uid=999, mailbox="INBOX"))


# ---------------------------------------------------------------------------
# reply / reply_all / forward
# ---------------------------------------------------------------------------

def test_reply_basic(manager: EmailManager, fake_smtp: FakeSMTPClient):
    original = make_email_message(
        headers={"Reply-To": "reply@example.com"},
        message_id="<orig@example.com>",
    )

    result = manager.reply(
        original,
        text="Thanks!",
        from_addr="me@example.com",
    )

    assert result.ok
    assert len(fake_smtp.sent) == 1
    msg = fake_smtp.sent[0].msg

    assert msg["Subject"] == ensure_reply_subject(original.subject)
    assert msg["To"] == "reply@example.com"
    assert msg["In-Reply-To"] == "<orig@example.com>"
    assert "<orig@example.com>" in msg["References"]

    text, html = get_text_and_html_from_pymsg(msg)
    assert "Thanks!" in (text or "")
    assert html is None or html == ""


def test_reply_with_quote_text_and_html(manager: EmailManager, fake_smtp: FakeSMTPClient):
    original = make_email_message(
        text="Original body",
        html="<p>Original HTML</p>",
        message_id="<orig2@example.com>",
    )

    manager.reply(
        original,
        text="Reply text",
        html="<p>Reply HTML</p>",
        from_addr="me@example.com",
        quote_original=True,
    )

    msg = fake_smtp.sent[-1].msg
    text, html = get_text_and_html_from_pymsg(msg)

    assert "Reply text" in (text or "")
    assert "Original body" in (text or "")  # quoted
    assert "Reply HTML" in (html or "")
    assert "Original HTML" in (html or "")


def test_reply_error_when_no_reply_to_and_no_from(manager: EmailManager):
    original = make_email_message(
        from_email="",
        headers={},
    )
    with pytest.raises(ValueError):
        manager.reply(original, text="hi")


def test_reply_all_builds_to_and_cc(manager: EmailManager, fake_smtp: FakeSMTPClient):
    original = make_email_message(
        from_email="alice@example.com",
        to=["me@example.com", "bob@example.com"],
        cc=["carol@example.com"],
        headers={},
    )

    manager.reply_all(
        original,
        text="Reply all",
        from_addr="me@example.com",
    )

    msg = fake_smtp.sent[-1].msg

    # Primary goes to original sender
    assert "alice@example.com" in msg["To"]
    assert "me@example.com" not in msg["To"]

    # Others go to CC
    cc_val = msg.get("Cc", "")
    assert "bob@example.com" in cc_val
    assert "carol@example.com" in cc_val
    assert "me@example.com" not in cc_val
    assert "alice@example.com" not in cc_val


def test_forward_include_original_and_attachments(manager: EmailManager, fake_smtp: FakeSMTPClient):
    att = Attachment(idx=1, part="part1", filename="file.txt", content_type="text/plain", data=b"123", size=3)
    original = make_email_message(
        subject="Orig subject",
        from_email="alice@example.com",
        to=["me@example.com"],
        text="Original body",
        attachments=[att],
    )

    manager.forward(
        original,
        to=["dest@example.com"],
        from_addr="me@example.com",
        text="FYI",
        include_original=True,          # <-- required to get forwarded content
        include_attachments=True,
    )

    msg = fake_smtp.sent[-1].msg

    assert msg["Subject"] == ensure_forward_subject(original.subject or "")
    assert msg["To"] == "dest@example.com"

    text, html = get_text_and_html_from_pymsg(msg)
    assert "FYI" in (text or "")
    # quote_forward_text() content should appear when include_original=True
    assert "alice@example.com" in (text or "")

    filenames = [p.get_filename() for p in msg.walk() if p.get_filename()]
    assert "file.txt" in filenames


def test_forward_requires_to(manager: EmailManager):
    original = make_email_message()
    with pytest.raises(ValueError):
        manager.forward(original, to=[], text="x")


# ---------------------------------------------------------------------------
# fetch_latest / fetch_thread
# ---------------------------------------------------------------------------

def test_fetch_latest_unseen_and_limit(manager: EmailManager, fake_imap: FakeIMAPClient):
    m1 = make_email_message(uid=1, text="m1")
    m2 = make_email_message(uid=2, text="m2")
    m3 = make_email_message(uid=3, text="m3")
    r1 = fake_imap.add_parsed_message("INBOX", m1)
    r2 = fake_imap.add_parsed_message("INBOX", m2)
    r3 = fake_imap.add_parsed_message("INBOX", m3)

    # mark newest as seen
    fake_imap.add_flags([r3], flags={r"\Seen"})

    page, msgs = manager.fetch_latest(mailbox="INBOX", n=2, unseen_only=True, refresh=True)
    texts = [m.text for m in msgs]

    assert "m3" not in texts  # seen excluded
    assert texts == ["m2", "m1"]


def test_fetch_thread_includes_root_once(manager: EmailManager, fake_imap: FakeIMAPClient):
    root = make_email_message(
        uid=1,
        message_id="<root@example.com>",
        text="root",
    )
    fake_imap.add_parsed_message("INBOX", root)

    reply = make_email_message(
        uid=2,
        message_id="<reply@example.com>",
        text="reply",
        headers={"In-Reply-To": "<root@example.com>"},
    )
    fake_imap.add_parsed_message("INBOX", reply)

    msgs = manager.fetch_thread(root, mailbox="INBOX")
    mids = [m.message_id for m in msgs]

    assert mids.count("<root@example.com>") == 1
    assert len(msgs) >= 2


# ---------------------------------------------------------------------------
# flag / mailbox operations
# ---------------------------------------------------------------------------

def test_flagging_and_expunge_and_mark_all_seen(manager: EmailManager, fake_imap: FakeIMAPClient, monkeypatch):

    # Patch only the check site by monkeypatching attribute access pattern:
    # easiest is to monkeypatch EmailManager.mark_all_seen local usage by wrapping search result,
    # but we don't have hook; so we structure test so only one page is needed.

    m1 = make_email_message(uid=1, text="m1")
    m2 = make_email_message(uid=2, text="m2")
    r1 = fake_imap.add_parsed_message("INBOX", m1)
    r2 = fake_imap.add_parsed_message("INBOX", m2)

    manager.mark_seen([r1])
    assert r"\Seen" in fake_imap._mailboxes["INBOX"][r1.uid].flags

    manager.mark_unseen([r1])
    assert r"\Seen" not in fake_imap._mailboxes["INBOX"][r1.uid].flags

    manager.flag([r1])
    assert r"\Flagged" in fake_imap._mailboxes["INBOX"][r1.uid].flags
    manager.unflag([r1])
    assert r"\Flagged" not in fake_imap._mailboxes["INBOX"][r1.uid].flags

    manager.delete([r2])
    assert r"\Deleted" in fake_imap._mailboxes["INBOX"][r2.uid].flags
    manager.undelete([r2])
    assert r"\Deleted" not in fake_imap._mailboxes["INBOX"][r2.uid].flags
    manager.delete([r2])
    manager.expunge("INBOX")
    assert r2.uid not in fake_imap._mailboxes["INBOX"]

    # Ensure only one unseen message exists so mark_all_seen doesn't need multiple pages
    count = manager.mark_all_seen("INBOX", chunk_size=500)
    assert count == 1
    assert r"\Seen" in fake_imap._mailboxes["INBOX"][r1.uid].flags


def test_list_mailboxes_status_move_copy_create_delete(manager: EmailManager, fake_imap: FakeIMAPClient):
    m = make_email_message(uid=1)
    ref = fake_imap.add_parsed_message("INBOX", m)

    manager.create_mailbox("Archive")
    assert "Archive" in manager.list_mailboxes()

    manager.copy([ref], src_mailbox="INBOX", dst_mailbox="Archive")
    assert manager.mailbox_status("Archive")["messages"] == 1
    assert manager.mailbox_status("INBOX")["messages"] == 1

    manager.move([ref], src_mailbox="INBOX", dst_mailbox="Archive")
    assert fake_imap.mailbox_status("INBOX")["messages"] == 0
    assert fake_imap.mailbox_status("Archive")["messages"] == 2  # one copied + one moved

    status = manager.mailbox_status("Archive")
    assert status["messages"] == 2

    manager.delete_mailbox("Archive")
    assert "Archive" not in manager.list_mailboxes()


# ---------------------------------------------------------------------------
# unsubscribe-related APIs (delegation only, via monkeypatch)
# ---------------------------------------------------------------------------

def test_list_unsubscribe_candidates_uses_detector(manager: EmailManager, monkeypatch):
    import openmail.email_manager as em_mod

    seen_args: list[tuple] = []

    class DummyDetector:
        def __init__(self, imap):
            self.imap = imap

        def find(self, *, mailbox, limit, since, unseen_only):
            seen_args.append((mailbox, limit, since, unseen_only))
            method = UnsubscribeMethod(kind="mailto", value="list@example.com")
            cand = UnsubscribeCandidate(
                ref=EmailRef(uid=1, mailbox=mailbox),
                from_email="newsletter@example.com",
                subject="Sub",
                methods=[method],
            )
            return [cand]

    monkeypatch.setattr(em_mod, "SubscriptionDetector", DummyDetector)

    cands = manager.list_unsubscribe_candidates(
        mailbox="INBOX", limit=10, since="2026-01-01", unseen_only=True
    )
    assert len(cands) == 1
    assert cands[0].from_email == "newsletter@example.com"
    assert seen_args == [("INBOX", 10, "2026-01-01", True)]


def test_unsubscribe_selected_uses_service(manager: EmailManager, monkeypatch):
    import openmail.email_manager as em_mod

    called: list[tuple] = []

    class DummyService:
        def __init__(self, smtp):
            self.smtp = smtp

        def unsubscribe(self, candidates, *, prefer, from_addr):
            called.append((candidates, prefer, from_addr))
            return {"sent": [], "http": [], "skipped": []}

    monkeypatch.setattr(em_mod, "SubscriptionService", DummyService)

    method = UnsubscribeMethod(kind="mailto", value="list@example.com")
    cand = UnsubscribeCandidate(
        ref=EmailRef(uid=1, mailbox="INBOX"),
        from_email="newsletter@example.com",
        subject="Sub",
        methods=[method],
    )

    res = manager.unsubscribe_selected([cand], prefer="mailto", from_addr="me@example.com")
    assert res == {"sent": [], "http": [], "skipped": []}
    assert len(called) == 1
    cands, prefer, from_addr = called[0]
    assert prefer == "mailto"
    assert from_addr == "me@example.com"
    assert cands[0].from_email == "newsletter@example.com"


# ---------------------------------------------------------------------------
# health_check
# ---------------------------------------------------------------------------

def test_health_check_ok(manager: EmailManager):
    status = manager.health_check()
    assert status == {"imap": True, "smtp": True}


def test_health_check_with_failures(manager: EmailManager, fake_imap: FakeIMAPClient, fake_smtp: FakeSMTPClient):
    fake_imap.fail_next = True
    fake_smtp.fail_next = True

    status = manager.health_check()
    assert status == {"imap": False, "smtp": False}
