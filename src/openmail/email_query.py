from __future__ import annotations

from typing import TYPE_CHECKING, List, Optional, Sequence

from openmail.imap import IMAPQuery, PagedSearchResult
from openmail.models import EmailMessage, EmailOverview
from openmail.utils import iso_days_ago

if TYPE_CHECKING:
    from openmail.email_manager import EmailManager

class EmailQuery:
    """
    Builder that composes filters and only hits IMAP when you call .search() or .fetch().
    """

    def __init__(self, manager: Optional[EmailManager], mailbox: str = "INBOX"):
        self._m = manager
        self._mailbox = mailbox
        self._q = IMAPQuery()
        self._limit: int = 50

    def mailbox(self, mailbox: str) -> EmailQuery:
        self._mailbox = mailbox
        return self

    def limit(self, n: int) -> EmailQuery:
        self._limit = n
        return self

    @property
    def query(self) -> IMAPQuery:
        """
        The underlying IMAPQuery.

        This is a LIVE object:
        mutating it will affect this EmailQuery.

        Example:
            easy = EmailQuery(mgr)

            # mutate existing IMAPQuery
            easy.query.unseen().from_("alerts@example.com")

            # later:
            refs = easy.search()
        """
        return self._q
    
    @query.setter
    def query(self, value: IMAPQuery) -> None:
        """
        Replace the underlying IMAPQuery.

        Example:
            q = IMAPQuery().unseen().subject("invoice")
            easy.query = q
        """
        if not isinstance(value, IMAPQuery):
            raise TypeError("query must be an IMAPQuery")
        self._q = value

    def last_days(self, days: int) -> EmailQuery:
        """Convenience: messages since N days ago (UTC)."""
        if days < 0:
            raise ValueError("days must be >= 0")
        self._q.since(iso_days_ago(days))
        return self

    def from_any(self, *senders: str) -> EmailQuery:
        """
        FROM any of the senders (nested OR). Equivalent to:
            OR FROM a OR FROM b FROM c ...
        """
        qs = [IMAPQuery().from_(s) for s in senders if s]
        if len(qs) == 0:
            return self
        if len(qs) == 1:
            self._q.parts += qs[0].parts
            return self
        self._q.or_(*qs)
        return self

    def to_any(self, *recipients: str) -> EmailQuery:
        qs = [IMAPQuery().to(s) for s in recipients if s]
        if len(qs) == 0:
            return self
        if len(qs) == 1:
            self._q.parts += qs[0].parts
            return self
        self._q.or_(*qs)
        return self

    def subject_any(self, *needles: str) -> EmailQuery:
        qs = [IMAPQuery().subject(s) for s in needles if s]
        if len(qs) == 0:
            return self
        if len(qs) == 1:
            self._q.parts += qs[0].parts
            return self
        self._q.or_(*qs)
        return self

    def text_any(self, *needles: str) -> EmailQuery:
        qs = [IMAPQuery().text(s) for s in needles if s]
        if len(qs) == 0:
            return self
        if len(qs) == 1:
            self._q.parts += qs[0].parts
            return self
        self._q.or_(*qs)
        return self

    def recent_unread(self, days: int = 7) -> EmailQuery:
        """UNSEEN AND SINCE (days ago)."""
        self._q.unseen()
        return self.last_days(days)

    def inbox_triage(self, days: int = 14) -> EmailQuery:
        """
        A very common triage filter:
        - not deleted
        - not drafts
        - recent window
        - and either unseen OR flagged
        """
        triage_or = IMAPQuery().or_(
            IMAPQuery().unseen(),
            IMAPQuery().flagged(),
        )
        self._q.undeleted().undraft()
        self.last_days(days)
        self._q.raw(triage_or.build())
        return self

    def header_contains(self, name: str, needle: str) -> EmailQuery:
        if name and needle:
            self._q.header(name, needle)
        return self
    
    def for_thread_root(self, root: EmailMessage) -> EmailQuery:
        """
        Narrow this query to messages that look like they belong to the same
        thread as `root`, based on its Message-ID.
        """
        if not root.message_id:
            return self

        mid = root.message_id

        self._q.or_(
            IMAPQuery().header("References", mid),
            IMAPQuery().header("In-Reply-To", mid),
        )
        return self
    
    def thread_like(self, *, subject: Optional[str] = None, participants: Sequence[str] = ()) -> EmailQuery:
        """
        Approximate "thread" matching:
        - optional SUBJECT contains `subject`
        - AND (FROM any participants OR TO any participants OR CC any participants)
        """
        if subject:
            self._q.subject(subject)

        p = [x for x in participants if x]
        if not p:
            return self

        q_from = [IMAPQuery().from_(x) for x in p]
        q_to = [IMAPQuery().to(x) for x in p]
        q_cc = [IMAPQuery().cc(x) for x in p]

        self._q.or_(*(q_from + q_to + q_cc))
        return self

    def newsletters(self) -> EmailQuery:
        """
        Common newsletter identification:
        - has List-Unsubscribe header
        """
        self._q.header("List-Unsubscribe", "")
        return self

    def from_domain(self, domain: str) -> EmailQuery:
        """
        Practical: FROM contains '@domain'.
        (IMAP has no dedicated "domain" operator.)
        """
        if not domain:
            return self
        needle = domain if domain.startswith("@") else f"@{domain}"
        self._q.from_(needle)
        return self

    def invoices_or_receipts(self) -> EmailQuery:
        """Common finance mailbox query."""
        return self.subject_any("invoice", "receipt", "payment", "order confirmation")

    def security_alerts(self) -> EmailQuery:
        """Common security / auth notifications."""
        return self.subject_any(
            "security alert",
            "new sign-in",
            "new login",
            "password",
            "verification code",
            "one-time",
            "2fa",
        )

    def with_attachments_hint(self) -> EmailQuery:
        """
        IMAP SEARCH cannot reliably filter 'has attachment' across servers.
        """
        hint = IMAPQuery().or_(
            IMAPQuery().header("Content-Disposition", "attachment"),
            IMAPQuery().header("Content-Type", "name="),
            IMAPQuery().header("Content-Type", "filename="),
        )

        self._q.raw(hint.build())
        return self

    def raw(self, *tokens: str) -> EmailQuery:
        self._q.raw(*tokens)
        return self

    def search(
        self,
        *,
        before_uid: Optional[int] = None,
        after_uid: Optional[int] = None,
        refresh: bool = False,
    ) -> PagedSearchResult:
        return self._m.imap.search_page_cached(
            mailbox=self._mailbox,
            query=self._q,
            page_size=self._limit,
            before_uid=before_uid,
            after_uid=after_uid,
            refresh=refresh,
        )

    def fetch(
        self,
        *,
        before_uid: Optional[int] = None,
        after_uid: Optional[int] = None,
        refresh: bool = False,
        include_attachment_meta: bool = False,
    ) -> tuple[PagedSearchResult, List[EmailMessage]]:
        """
        Fetch a page of full EmailMessage objects plus its paging metadata.
        """
        page = self.search(before_uid=before_uid, after_uid=after_uid, refresh=refresh)
        if not page.refs:
            return page, []
        messages = self._m.imap.fetch(page.refs, include_attachment_meta=include_attachment_meta)
        return page, messages

    def fetch_overview(
        self,
        *,
        before_uid: Optional[int] = None,
        after_uid: Optional[int] = None,
        refresh: bool = False,
    ) -> tuple[PagedSearchResult, List[EmailOverview]]:
        """
        Fetch a page of EmailOverview objects plus its paging metadata.
        """
        page = self.search(before_uid=before_uid, after_uid=after_uid, refresh=refresh)
        if not page.refs:
            return page, []
        overviews = self._m.imap.fetch_overview(page.refs)
        return page, overviews