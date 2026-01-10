from __future__ import annotations

from typing import List, Optional, Sequence, TYPE_CHECKING

from email_management.models import EmailMessage
from email_management.imap import IMAPQuery
from email_management.types import EmailRef
from email_management.utils import iso_days_ago

if TYPE_CHECKING:
    from email_management.email_manager import EmailManager

class EasyIMAPQuery:
    """
    Builder that composes filters and only hits IMAP when you call .search() or .fetch().
    """

    def __init__(self, manager: "EmailManager", mailbox: str = "INBOX"):
        self._m = manager
        self._mailbox = mailbox
        self._q = IMAPQuery()
        self._limit: int = 50

    def mailbox(self, mailbox: str) -> EasyIMAPQuery:
        self._mailbox = mailbox
        return self

    def limit(self, n: int) -> EasyIMAPQuery:
        self._limit = n
        return self

    @property
    def query(self) -> IMAPQuery:
        """
        The underlying IMAPQuery.

        This is a LIVE object:
        mutating it will affect this EasyIMAPQuery.

        Example:
            easy = EasyIMAPQuery(mgr)

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

    def last_days(self, days: int) -> EasyIMAPQuery:
        """Convenience: messages since N days ago (UTC)."""
        if days < 0:
            raise ValueError("days must be >= 0")
        self._q.since(iso_days_ago(days))
        return self

    def from_any(self, *senders: str) -> EasyIMAPQuery:
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

    def to_any(self, *recipients: str) -> EasyIMAPQuery:
        qs = [IMAPQuery().to(s) for s in recipients if s]
        if len(qs) == 0:
            return self
        if len(qs) == 1:
            self._q.parts += qs[0].parts
            return self
        self._q.or_(*qs)
        return self

    def subject_any(self, *needles: str) -> EasyIMAPQuery:
        qs = [IMAPQuery().subject(s) for s in needles if s]
        if len(qs) == 0:
            return self
        if len(qs) == 1:
            self._q.parts += qs[0].parts
            return self
        self._q.or_(*qs)
        return self

    def text_any(self, *needles: str) -> EasyIMAPQuery:
        qs = [IMAPQuery().text(s) for s in needles if s]
        if len(qs) == 0:
            return self
        if len(qs) == 1:
            self._q.parts += qs[0].parts
            return self
        self._q.or_(*qs)
        return self

    def recent_unread(self, days: int = 7) -> EasyIMAPQuery:
        """UNSEEN AND SINCE (days ago)."""
        self._q.unseen()
        return self.last_days(days)

    def inbox_triage(self, days: int = 14) -> EasyIMAPQuery:
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
        self = self.last_days(days)
        self._q.raw(triage_or.build())
        return self

    def thread_like(self, *, subject: Optional[str] = None, participants: Sequence[str] = ()) -> EasyIMAPQuery:
        """
        Approximate "thread" matching:
        - optional SUBJECT contains `subject`
        - AND (FROM any participants OR TO any participants OR CC any participants)

        Note: IMAP SEARCH doesn't have real threading; this is a practical heuristic.
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

    def newsletters(self) -> EasyIMAPQuery:
        """
        Common newsletter identification:
        - has List-Unsubscribe header
        """
        self._q.header("List-Unsubscribe", "")
        return self

    def from_domain(self, domain: str) -> EasyIMAPQuery:
        """
        Practical: FROM contains '@domain'.
        (IMAP has no dedicated "domain" operator.)
        """
        if not domain:
            return self
        needle = domain if domain.startswith("@") else f"@{domain}"
        self._q.from_(needle)
        return self

    def invoices_or_receipts(self) -> EasyIMAPQuery:
        """Common finance mailbox query."""
        return self.subject_any("invoice", "receipt", "payment", "order confirmation")

    def security_alerts(self) -> EasyIMAPQuery:
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

    def with_attachments_hint(self) -> EasyIMAPQuery:
        """
        IMAP SEARCH cannot reliably filter 'has attachment' across servers.
        Best-effort heuristic:
        - look for common MIME markers in BODY (server-dependent).
        """
        hint = IMAPQuery().or_(
            IMAPQuery().body("Content-Disposition: attachment"),
            IMAPQuery().body("filename="),
            IMAPQuery().body("name="),
        )
        self._q.raw(hint.build())
        return self

    def raw(self, *tokens: str) -> EasyIMAPQuery:
        self._q.raw(*tokens)
        return self

    def search(self) -> List[EmailRef]:
        return self._m.imap.search(mailbox=self._mailbox, query=self._q, limit=self._limit)

    def fetch(self, *, include_attachments: bool = False) -> List[EmailMessage]:
        refs = self.search()
        return self._m.imap.fetch(refs, include_attachments=include_attachments)

