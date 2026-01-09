from email.message import EmailMessage as PyEmailMessage
import email_management.email_manager as mgr_mod
from email_management.email_manager import EmailManager
from email_management.models.message import EmailMessage
from email_management.types import EmailRef, SendResult


class FakeSMTPClient:
    def __init__(self):
        self.sent = []

    def send(self, msg: PyEmailMessage):
        self.sent.append(msg)
        return "send-result"


class FakeIMAPClient:
    def __init__(self):
        self.add_flags_calls = []
        self.remove_flags_calls = []

    def add_flags(self, refs, flags):
        self.add_flags_calls.append((list(refs), set(flags)))

    def remove_flags(self, refs, flags):
        self.remove_flags_calls.append((list(refs), set(flags)))


def test_send_delegates_to_smtp():
    smtp = FakeSMTPClient()
    imap = FakeIMAPClient()
    mgr = EmailManager(smtp=smtp, imap=imap)

    msg = PyEmailMessage()
    msg["Subject"] = "Test"

    result = mgr.send(msg)

    assert result == "send-result"
    assert smtp.sent[0] is msg

def _make_original_message(**overrides):
    base = dict(
        ref=EmailRef(1),
        subject="Hello",
        from_email="alice@example.com",
        to=["bob@example.com"],
        cc=[],
        bcc=[],
        text="hi",
        html=None,
        attachments=[],
        date=None,
        message_id="<msg-1@example.com>",
        headers={},
    )
    base.update(overrides)
    return EmailMessage(**base)


def test_reply_uses_reply_to_and_thread_headers():
    smtp = FakeSMTPClient()
    imap = FakeIMAPClient()
    mgr = EmailManager(smtp=smtp, imap=imap)

    original = _make_original_message(
        headers={
            "Reply-To": "Alice <alice+reply@example.com>",
            "References": "<old1@example.com> <old2@example.com>",
        },
    )

    result = mgr.reply(original, body="Thanks!", from_addr="me@example.com")

    assert result == "send-result"
    assert len(smtp.sent) == 1
    msg = smtp.sent[0]

    
    assert msg["From"] == "me@example.com"

    
    assert msg["Subject"].startswith("Re:")

    
    assert "alice+reply@example.com" in msg["To"]

    
    assert msg["In-Reply-To"] == original.message_id
    assert original.message_id in msg["References"]

    
    assert msg.get_content().strip() == "Thanks!"


def test_reply_falls_back_to_from_when_no_reply_to():
    smtp = FakeSMTPClient()
    imap = FakeIMAPClient()
    mgr = EmailManager(smtp=smtp, imap=imap)

    original = _make_original_message(headers={})  

    mgr.reply(original, body="Hello back", from_addr="me@example.com")

    msg = smtp.sent[0]
    
    assert msg["To"] == "alice@example.com"


def test_reply_all_to_and_cc_resolved_correctly():
    smtp = FakeSMTPClient()
    imap = FakeIMAPClient()
    mgr = EmailManager(smtp=smtp, imap=imap)

    original = _make_original_message(
        from_email="alice@example.com",
        to=["me@example.com"],
        cc=["carol@example.com", "dave@example.com"],
        headers={},  
    )

    mgr.reply_all(original, body="Replying all", from_addr="me@example.com")
    msg = smtp.sent[0]

    
    assert msg["To"] == "alice@example.com"

    
    cc_list = [a.strip() for a in msg["Cc"].split(",")]
    assert set(cc_list) == {"carol@example.com", "dave@example.com"}
    assert "me@example.com" not in cc_list

    
    assert msg["Subject"].startswith("Re:")

def test_imap_query_returns_easy_query():
    smtp = FakeSMTPClient()
    imap = FakeIMAPClient()
    mgr = EmailManager(smtp=smtp, imap=imap)

    q = mgr.imap_query("Archive")

    
    assert q.__class__.__name__ == "EasyIMAPQuery"
    assert q._mailbox == "Archive"
    assert q._m is mgr


class FakeEasyQuery:
    def __init__(self):
        self.limits = []
        self.unseen_called = False
        self.fetch_calls = []

    def limit(self, n: int):
        self.limits.append(n)
        return self

    def unseen(self):
        self.unseen_called = True
        return self

    def fetch(self, *, include_attachments: bool = False):
        self.fetch_calls.append(include_attachments)
        return ["msg-1", "msg-2"]


def test_fetch_latest_seen_and_unseen(monkeypatch):
    smtp = FakeSMTPClient()
    imap = FakeIMAPClient()
    mgr = EmailManager(smtp=smtp, imap=imap)

    fake_easy = FakeEasyQuery()

    def fake_imap_query(self, mailbox="INBOX"):
        return fake_easy

    
    monkeypatch.setattr(EmailManager, "imap_query", fake_imap_query)

    
    msgs = mgr.fetch_latest(mailbox="INBOX", n=10, unseen_only=False, include_attachments=True)
    assert msgs == ["msg-1", "msg-2"]
    assert fake_easy.limits == [10]
    assert fake_easy.unseen_called is False
    assert fake_easy.fetch_calls == [True]

    
    fake_easy.limits.clear()
    fake_easy.unseen_called = False
    fake_easy.fetch_calls.clear()

    
    msgs = mgr.fetch_latest(mailbox="INBOX", n=5, unseen_only=True, include_attachments=False)
    assert msgs == ["msg-1", "msg-2"]
    assert fake_easy.limits == [5]
    assert fake_easy.unseen_called is True
    assert fake_easy.fetch_calls == [False]


def test_add_and_remove_flags_delegate_to_imap():
    smtp = FakeSMTPClient()
    imap = FakeIMAPClient()
    mgr = EmailManager(smtp=smtp, imap=imap)

    refs = [EmailRef(uid=1), EmailRef(uid=2)]
    mgr.add_flags(refs, {"\\Seen"})
    mgr.remove_flags(refs, {"\\Seen"})

    assert imap.add_flags_calls == [([refs[0], refs[1]], {"\\Seen"})]
    assert imap.remove_flags_calls == [([refs[0], refs[1]], {"\\Seen"})]


def test_add_flags_no_refs_does_nothing():
    smtp = FakeSMTPClient()
    imap = FakeIMAPClient()
    mgr = EmailManager(smtp=smtp, imap=imap)

    mgr.add_flags([], {"\\Seen"})
    mgr.remove_flags([], {"\\Seen"})

    assert imap.add_flags_calls == []
    assert imap.remove_flags_calls == []


def test_mark_seen_and_unseen_use_seen_flag():
    smtp = FakeSMTPClient()
    imap = FakeIMAPClient()
    mgr = EmailManager(smtp=smtp, imap=imap)

    refs = [EmailRef(uid=1)]

    mgr.mark_seen(refs)
    mgr.mark_unseen(refs)

    assert imap.add_flags_calls == [([refs[0]], {mgr_mod.SEEN})]
    assert imap.remove_flags_calls == [([refs[0]], {mgr_mod.SEEN})]


def test_flag_unflag_delete_undelete_use_correct_flags():
    smtp = FakeSMTPClient()
    imap = FakeIMAPClient()
    mgr = EmailManager(smtp=smtp, imap=imap)

    refs = [EmailRef(uid=1)]

    mgr.flag(refs)
    mgr.unflag(refs)
    mgr.delete(refs)
    mgr.undelete(refs)

    assert imap.add_flags_calls == [
        ([refs[0]], {mgr_mod.FLAGGED}),
        ([refs[0]], {mgr_mod.DELETED}),
    ]
    assert imap.remove_flags_calls == [
        ([refs[0]], {mgr_mod.FLAGGED}),
        ([refs[0]], {mgr_mod.DELETED}),
    ]


class FakeEasyLoop:
    def __init__(self, batches):
        self.batches = list(batches)  
        self.unseen_calls = 0
        self.limits = []

    def unseen(self):
        self.unseen_calls += 1
        return self

    def limit(self, n: int):
        self.limits.append(n)
        return self

    def search(self):
        if self.batches:
            return self.batches.pop(0)
        return []


def test_mark_all_seen_loops_until_no_refs(monkeypatch):
    smtp = FakeSMTPClient()
    imap = FakeIMAPClient()
    mgr = EmailManager(smtp=smtp, imap=imap)

    refs_batch1 = [EmailRef(uid=1), EmailRef(uid=2)]
    refs_batch2 = [EmailRef(uid=3)]
    easy = FakeEasyLoop([refs_batch1, refs_batch2, []])

    def fake_imap_query(self, mailbox="INBOX"):
        return easy

    monkeypatch.setattr(EmailManager, "imap_query", fake_imap_query)

    total = mgr.mark_all_seen(mailbox="INBOX", chunk_size=2)

    assert total == 3  
    
    assert len(imap.add_flags_calls) == 2
    assert imap.add_flags_calls[0] == ([refs_batch1[0], refs_batch1[1]], {mgr_mod.SEEN})
    assert imap.add_flags_calls[1] == ([refs_batch2[0]], {mgr_mod.SEEN})