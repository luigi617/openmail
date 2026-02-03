import pytest

from email_management.imap import IMAPQuery, PagedSearchResult
from email_management.email_query import EmailQuery
import email_management.email_query as easy_mod



class FakeImap:
    def __init__(self):
        self.search_page_cached_calls = []
        self.fetch_calls = []
        self.fetch_overview_calls = []

    def search_page_cached(
        self,
        *,
        mailbox: str,
        query: IMAPQuery,
        page_size: int = 50,
        before_uid=None,
        after_uid=None,
        refresh: bool = False,
    ):
        self.search_page_cached_calls.append(
            (mailbox, query, page_size, before_uid, after_uid, refresh)
        )
        # EmailQuery expects newest-first refs; tests can treat them as opaque.
        return PagedSearchResult(refs=["ref-1", "ref-2"])

    def fetch(self, refs, *, include_attachment_meta: bool = False):
        self.fetch_calls.append((refs, include_attachment_meta))
        return ["msg-1", "msg-2"]

    def fetch_overview(self, refs):
        self.fetch_overview_calls.append(refs)
        return ["ov-1", "ov-2"]


class FakeEmailManager:
    def __init__(self):
        self.imap = FakeImap()


def test_mailbox_and_limit_config():
    mgr = FakeEmailManager()
    easy = EmailQuery(mgr)

    result = easy.mailbox("Archive").limit(10)
    assert result is easy
    assert easy._mailbox == "Archive"
    assert easy._limit == 10


def test_query_property_live_object():
    mgr = FakeEmailManager()
    easy = EmailQuery(mgr)

    q = easy.query
    assert isinstance(q, IMAPQuery)

    q.unseen().from_("a@example.com")
    built = easy.query.build()
    assert "UNSEEN" in built
    assert '"a@example.com"' in built


def test_query_setter_replaces_imapquery():
    mgr = FakeEmailManager()
    easy = EmailQuery(mgr)

    new_q = IMAPQuery().to("b@example.com")
    easy.query = new_q

    assert easy.query is new_q
    assert 'TO "b@example.com"' in easy.query.build()


def test_query_setter_rejects_non_imapquery():
    mgr = FakeEmailManager()
    easy = EmailQuery(mgr)

    with pytest.raises(TypeError):
        easy.query = "not a query"


def test_last_days_uses_since(monkeypatch):
    # EmailQuery.last_days -> IMAPQuery.since(iso_days_ago(days))
    # The IMAPQuery.since() expects ISO date like "YYYY-MM-DD" and formats it to SINCE DD-Mon-YYYY.
    monkeypatch.setattr(easy_mod, "iso_days_ago", lambda d: "2025-01-01")

    mgr = FakeEmailManager()
    easy = EmailQuery(mgr)
    easy.last_days(7)
    built = easy.query.build()

    assert "SINCE 01-Jan-2025" in built


def test_last_days_rejects_negative():
    mgr = FakeEmailManager()
    easy = EmailQuery(mgr)

    with pytest.raises(ValueError):
        easy.last_days(-1)


def test_from_any_zero_arguments_noop():
    mgr = FakeEmailManager()
    easy = EmailQuery(mgr)

    easy.from_any()
    assert easy.query.build() == "ALL"


def test_from_any_single_argument_expands_inline():
    mgr = FakeEmailManager()
    easy = EmailQuery(mgr)

    easy.from_any("a@example.com")
    assert easy.query.build() == 'FROM "a@example.com"'


def test_from_any_multiple_arguments_uses_or():
    mgr = FakeEmailManager()
    easy = EmailQuery(mgr)

    easy.from_any("a@example.com", "b@example.com")
    built = easy.query.build()

    assert "OR" in built
    assert '"a@example.com"' in built
    assert '"b@example.com"' in built


def test_to_any_behaviour():
    mgr = FakeEmailManager()
    easy = EmailQuery(mgr)

    easy.to_any("x@example.com", "y@example.com")
    built = easy.query.build()
    assert "OR" in built
    assert 'TO "x@example.com"' in built
    assert 'TO "y@example.com"' in built


def test_subject_any_behaviour():
    mgr = FakeEmailManager()
    easy = EmailQuery(mgr)

    easy.subject_any("invoice", "receipt")
    built = easy.query.build()
    assert "OR" in built
    assert 'SUBJECT "invoice"' in built
    assert 'SUBJECT "receipt"' in built


def test_text_any_behaviour():
    mgr = FakeEmailManager()
    easy = EmailQuery(mgr)

    easy.text_any("foo", "bar")
    built = easy.query.build()
    assert "OR" in built
    assert 'TEXT "foo"' in built
    assert 'TEXT "bar"' in built


def test_recent_unread_adds_unseen_and_since(monkeypatch):
    monkeypatch.setattr(easy_mod, "iso_days_ago", lambda d: "2025-01-01")

    mgr = FakeEmailManager()
    easy = EmailQuery(mgr)

    easy.recent_unread(days=3)
    built = easy.query.build()

    assert "UNSEEN" in built
    assert "SINCE 01-Jan-2025" in built


def test_inbox_triage_shape(monkeypatch):
    monkeypatch.setattr(easy_mod, "iso_days_ago", lambda d: "2025-01-01")

    mgr = FakeEmailManager()
    easy = EmailQuery(mgr)

    easy.inbox_triage(days=14)
    built = easy.query.build()

    assert "UNDELETED" in built
    assert "UNDRAFT" in built
    assert "SINCE 01-Jan-2025" in built

    # inbox_triage adds a raw OR query containing UNSEEN and FLAGGED
    assert "UNSEEN" in built
    assert "FLAGGED" in built
    assert "OR" in built


def test_thread_like_subject_only():
    mgr = FakeEmailManager()
    easy = EmailQuery(mgr)

    easy.thread_like(subject="hello thread", participants=())
    built = easy.query.build()

    assert 'SUBJECT "hello thread"' in built
    # no participants => no OR clause added by thread_like
    # (There could still be OR from earlier calls; here there aren't.)
    assert "OR" not in built


def test_thread_like_with_participants():
    mgr = FakeEmailManager()
    easy = EmailQuery(mgr)

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
    easy = EmailQuery(mgr)

    easy.newsletters()
    built = easy.query.build()

    assert 'HEADER "List-Unsubscribe" ""' in built


def test_from_domain_adds_at_prefix_if_missing():
    mgr = FakeEmailManager()
    easy = EmailQuery(mgr)

    easy.from_domain("example.com")
    built = easy.query.build()

    assert 'FROM "@example.com"' in built


def test_from_domain_respects_existing_at():
    mgr = FakeEmailManager()
    easy = EmailQuery(mgr)

    easy.from_domain("@example.com")
    built = easy.query.build()

    assert 'FROM "@example.com"' in built


def test_from_domain_noop_on_empty():
    mgr = FakeEmailManager()
    easy = EmailQuery(mgr)

    easy.from_domain("")
    assert easy.query.build() == "ALL"


def test_invoices_or_receipts_subject_any_keywords():
    mgr = FakeEmailManager()
    easy = EmailQuery(mgr)

    easy.invoices_or_receipts()
    built = easy.query.build()

    assert "SUBJECT" in built
    for kw in ["invoice", "receipt", "payment", "order confirmation"]:
        assert f'SUBJECT "{kw}"' in built


def test_security_alerts_subject_any_keywords():
    mgr = FakeEmailManager()
    easy = EmailQuery(mgr)

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
    easy = EmailQuery(mgr)

    easy.with_attachments_hint()
    built = easy.query.build()

    assert 'HEADER "Content-Disposition" "attachment"' in built
    assert 'HEADER "Content-Type" "name="' in built
    assert 'HEADER "Content-Type" "filename="' in built
    assert "OR" in built


def test_raw_delegates_to_underlying_query():
    mgr = FakeEmailManager()
    easy = EmailQuery(mgr)

    easy.raw("UNSEEN", 'FROM "x@example.com"')
    built = easy.query.build()

    assert "UNSEEN" in built
    assert 'FROM "x@example.com"' in built


def test_search_calls_manager_imap_search_page_cached():
    mgr = FakeEmailManager()
    easy = EmailQuery(mgr, mailbox="INBOX")
    easy.limit(42)
    easy.query.unseen()

    page = easy.search()

    assert page.refs == ["ref-1", "ref-2"]
    assert len(mgr.imap.search_page_cached_calls) == 1

    mailbox, query_obj, page_size, before_uid, after_uid, refresh = mgr.imap.search_page_cached_calls[0]
    assert mailbox == "INBOX"
    assert isinstance(query_obj, IMAPQuery)
    assert page_size == 42
    assert before_uid is None
    assert after_uid is None
    assert refresh is False
    assert "UNSEEN" in query_obj.build()


def test_fetch_calls_search_then_fetch():
    mgr = FakeEmailManager()
    easy = EmailQuery(mgr, mailbox="INBOX")

    page, msgs = easy.fetch(include_attachment_meta=True)

    assert page.refs == ["ref-1", "ref-2"]
    assert msgs == ["msg-1", "msg-2"]

    assert len(mgr.imap.search_page_cached_calls) == 1
    assert len(mgr.imap.fetch_calls) == 1

    refs, include_attachment_meta = mgr.imap.fetch_calls[0]
    assert refs == ["ref-1", "ref-2"]
    assert include_attachment_meta is True


def test_fetch_overview_calls_search_then_fetch_overview():
    mgr = FakeEmailManager()
    easy = EmailQuery(mgr, mailbox="INBOX")

    page, ovs = easy.fetch_overview()

    assert page.refs == ["ref-1", "ref-2"]
    assert ovs == ["ov-1", "ov-2"]

    assert len(mgr.imap.search_page_cached_calls) == 1
    assert len(mgr.imap.fetch_overview_calls) == 1
    assert mgr.imap.fetch_overview_calls[0] == ["ref-1", "ref-2"]
