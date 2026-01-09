import pytest

from email_management.imap.query import IMAPQuery
from email_management.email_manager import EasyIMAPQuery
import email_management.email_manager as easy_mod


class FakeImap:
    def __init__(self):
        self.search_calls = []
        self.fetch_calls = []

    def search(self, mailbox, query, limit):
        self.search_calls.append((mailbox, query, limit))
        return ["ref-1", "ref-2"]

    def fetch(self, refs, include_attachments=False):
        self.fetch_calls.append((refs, include_attachments))
        return ["msg-1", "msg-2"]


class FakeEmailManager:
    def __init__(self):
        self.imap = FakeImap()


def test_mailbox_and_limit_config():
    mgr = FakeEmailManager()
    easy = EasyIMAPQuery(mgr)

    result = easy.mailbox("Archive").limit(10)
    assert result is easy
    assert easy._mailbox == "Archive"
    assert easy._limit == 10


def test_query_property_live_object():
    mgr = FakeEmailManager()
    easy = EasyIMAPQuery(mgr)

    q = easy.query
    assert isinstance(q, IMAPQuery)

    q.unseen().from_("a@example.com")
    built = easy.query.build()
    assert "UNSEEN" in built
    assert '"a@example.com"' in built


def test_query_setter_replaces_imapquery():
    mgr = FakeEmailManager()
    easy = EasyIMAPQuery(mgr)

    new_q = IMAPQuery().to("b@example.com")
    easy.query = new_q

    assert easy.query is new_q
    assert 'TO "b@example.com"' in easy.query.build()


def test_query_setter_rejects_non_imapquery():
    mgr = FakeEmailManager()
    easy = EasyIMAPQuery(mgr)

    with pytest.raises(TypeError):
        easy.query = "not a query"


def test_last_days_uses_since(monkeypatch):
    monkeypatch.setattr(easy_mod, "iso_days_ago", lambda d: "2025-01-01")

    mgr = FakeEmailManager()
    easy = EasyIMAPQuery(mgr)

    easy.last_days(7)
    built = easy.query.build()

    assert "SINCE 01-Jan-2025" in built


def test_last_days_rejects_negative():
    mgr = FakeEmailManager()
    easy = EasyIMAPQuery(mgr)

    with pytest.raises(ValueError):
        easy.last_days(-1)

def test_from_any_zero_arguments_noop():
    mgr = FakeEmailManager()
    easy = EasyIMAPQuery(mgr)

    easy.from_any()
    assert easy.query.build() == "ALL"


def test_from_any_single_argument_expands_inline():
    mgr = FakeEmailManager()
    easy = EasyIMAPQuery(mgr)

    easy.from_any("a@example.com")
    assert easy.query.build() == 'FROM "a@example.com"'


def test_from_any_multiple_arguments_uses_or():
    mgr = FakeEmailManager()
    easy = EasyIMAPQuery(mgr)

    easy.from_any("a@example.com", "b@example.com")
    built = easy.query.build()

    assert "OR" in built
    assert '"a@example.com"' in built
    assert '"b@example.com"' in built


def test_to_any_behaviour():
    mgr = FakeEmailManager()
    easy = EasyIMAPQuery(mgr)

    easy.to_any("x@example.com", "y@example.com")
    built = easy.query.build()
    assert "OR" in built
    assert 'TO "x@example.com"' in built
    assert 'TO "y@example.com"' in built


def test_subject_any_behaviour():
    mgr = FakeEmailManager()
    easy = EasyIMAPQuery(mgr)

    easy.subject_any("invoice", "receipt")
    built = easy.query.build()
    assert "OR" in built
    assert 'SUBJECT "invoice"' in built
    assert 'SUBJECT "receipt"' in built


def test_text_any_behaviour():
    mgr = FakeEmailManager()
    easy = EasyIMAPQuery(mgr)

    easy.text_any("foo", "bar")
    built = easy.query.build()
    assert "OR" in built
    assert 'TEXT "foo"' in built
    assert 'TEXT "bar"' in built

def test_recent_unread_adds_unseen_and_since(monkeypatch):
    monkeypatch.setattr(easy_mod, "iso_days_ago", lambda d: "2025-01-01")

    mgr = FakeEmailManager()
    easy = EasyIMAPQuery(mgr)

    easy.recent_unread(days=3)
    built = easy.query.build()

    assert "UNSEEN" in built
    assert "SINCE 01-Jan-2025" in built

def test_inbox_triage_shape(monkeypatch):
    monkeypatch.setattr(easy_mod, "iso_days_ago", lambda d: "2025-01-01")

    mgr = FakeEmailManager()
    easy = EasyIMAPQuery(mgr)

    easy.inbox_triage(days=14)
    built = easy.query.build()

    assert "UNDELETED" in built
    assert "UNDRAFT" in built
    assert "SINCE 01-Jan-2025" in built

    assert "UNSEEN" in built
    assert "FLAGGED" in built
    assert "OR" in built

def test_thread_like_subject_only():
    mgr = FakeEmailManager()
    easy = EasyIMAPQuery(mgr)

    easy.thread_like(subject="hello thread", participants=())
    built = easy.query.build()

    assert 'SUBJECT "hello thread"' in built
    assert "OR" not in built


def test_thread_like_with_participants():
    mgr = FakeEmailManager()
    easy = EasyIMAPQuery(mgr)

    easy.thread_like(
        subject=None,
        participants=["a@example.com", "b@example.com"],
    )
    built = easy.query.build()

    assert "OR" in built
    assert '"a@example.com"' in built
    assert '"b@example.com"' in built

    assert "FROM" in built
    assert "TO" in built
    assert "CC" in built


def test_newsletters_adds_list_unsubscribe_header():
    mgr = FakeEmailManager()
    easy = EasyIMAPQuery(mgr)

    easy.newsletters()
    built = easy.query.build()

    assert 'HEADER "List-Unsubscribe" ""' in built


def test_from_domain_adds_at_prefix_if_missing():
    mgr = FakeEmailManager()
    easy = EasyIMAPQuery(mgr)

    easy.from_domain("example.com")
    built = easy.query.build()

    assert 'FROM "@example.com"' in built


def test_from_domain_respects_existing_at():
    mgr = FakeEmailManager()
    easy = EasyIMAPQuery(mgr)

    easy.from_domain("@example.com")
    built = easy.query.build()

    assert 'FROM "@example.com"' in built


def test_from_domain_noop_on_empty():
    mgr = FakeEmailManager()
    easy = EasyIMAPQuery(mgr)

    easy.from_domain("")
    assert easy.query.build() == "ALL"


def test_invoices_or_receipts_subject_any_keywords():
    mgr = FakeEmailManager()
    easy = EasyIMAPQuery(mgr)

    easy.invoices_or_receipts()
    built = easy.query.build()

    assert "SUBJECT" in built
    for kw in ["invoice", "receipt", "payment", "order confirmation"]:
        assert f'SUBJECT "{kw}"' in built


def test_security_alerts_subject_any_keywords():
    mgr = FakeEmailManager()
    easy = EasyIMAPQuery(mgr)

    easy.security_alerts()
    built = easy.query.build()

    for kw in [
        "security alert",
        "new sign-in",
        "new login",
        "password",
        "verification code",
        "one-time",
        "2fa",
    ]:
        assert f'SUBJECT "{kw}"' in built


def test_with_attachments_hint_adds_body_hints():
    mgr = FakeEmailManager()
    easy = EasyIMAPQuery(mgr)

    easy.with_attachments_hint()
    built = easy.query.build()

    assert "Content-Disposition: attachment" in built
    assert "filename=" in built
    assert "name=" in built
    assert "OR" in built


def test_raw_delegates_to_underlying_query():
    mgr = FakeEmailManager()
    easy = EasyIMAPQuery(mgr)

    easy.raw("UNSEEN", 'FROM "x@example.com"')
    built = easy.query.build()

    assert "UNSEEN" in built
    assert 'FROM "x@example.com"' in built


def test_search_calls_manager_imap_search():
    mgr = FakeEmailManager()
    easy = EasyIMAPQuery(mgr, mailbox="INBOX")
    easy.limit(42)
    easy.query.unseen()

    refs = easy.search()

    assert refs == ["ref-1", "ref-2"]
    assert len(mgr.imap.search_calls) == 1
    mailbox, query_obj, limit = mgr.imap.search_calls[0]

    assert mailbox == "INBOX"
    assert isinstance(query_obj, IMAPQuery)
    assert limit == 42
    assert "UNSEEN" in query_obj.build()


def test_fetch_calls_search_then_fetch():
    mgr = FakeEmailManager()
    easy = EasyIMAPQuery(mgr, mailbox="INBOX")

    msgs = easy.fetch(include_attachments=True)

    assert msgs == ["msg-1", "msg-2"]

    assert len(mgr.imap.search_calls) == 1
    assert len(mgr.imap.fetch_calls) == 1

    refs, include_attachments = mgr.imap.fetch_calls[0]
    assert refs == ["ref-1", "ref-2"]
    assert include_attachments is True

