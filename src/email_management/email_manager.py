from __future__ import annotations

from dataclasses import dataclass
from email.message import EmailMessage as PyEmailMessage
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple


from email_management.assistants import (
    llm_concise_reply_for_email,
    llm_summarize_single_email,
    llm_summarize_many_emails
)
from email_management.models import UnsubscribeCandidate, EmailMessage
from email_management.models.subscription import UnsubscribeActionResult
from email_management.subscription import SubscriptionService, SubscriptionDetector
from email_management.imap import IMAPClient, IMAPQuery
from email_management.smtp import SMTPClient
from email_management.types import EmailRef, SendResult
from email_management.utils import (iso_days_ago,
                                    ensure_reply_subject,
                                    get_header,
                                    parse_addrs,
                                    dedup_addrs,
                                    build_references,
                                    remove_addr)


SEEN = r"\Seen"
ANSWERED = r"\Answered"
FLAGGED = r"\Flagged"
DELETED = r"\Deleted"
DRAFT = r"\Draft"


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



@dataclass(frozen=True)
class EmailManager:
    smtp: SMTPClient
    imap: IMAPClient

    def fetch_message_by_ref(
        self,
        ref: EmailRef,
        *,
        include_attachments: bool = False,
    ) -> EmailMessage:
        """
        Fetch exactly one EmailMessage by EmailRef.

        Assumes IMAPClient.fetch(refs, include_attachments=...) -> List[EmailMessage].
        Adjust to your actual IMAPClient API if needed.
        """
        msgs = self.imap.fetch([ref], include_attachments=include_attachments)
        if not msgs:
            raise ValueError(f"No message found for ref: {ref!r}")
        return msgs[0]

    def fetch_messages_by_multi_refs(
        self,
        refs: Sequence[EmailRef],
        *,
        include_attachments: bool = False,
    ) -> List[EmailMessage]:
        if not refs:
            return []
        return list(self.imap.fetch(refs, include_attachments=include_attachments))

    def send(self, msg: PyEmailMessage) -> SendResult:
        return self.smtp.send(msg)
    
    def reply(
        self,
        original: EmailMessage,
        *,
        body: str,
        from_addr: Optional[str] = None,
    ) -> SendResult:
        """
        Reply to a single sender, based on our EmailMessage model.

        - To: Reply-To (if present) or From of the original
        - Subject: Re: <original subject> (added only once)
        - Threading: In-Reply-To, References (if message_id is present)
        """
        msg = PyEmailMessage()

        if from_addr:
            msg["From"] = from_addr

        msg["Subject"] = ensure_reply_subject(original.subject)

        reply_to = get_header(original.headers, "Reply-To") or original.from_email
        if reply_to:
            to_pairs = parse_addrs(reply_to)
            to_addrs = dedup_addrs(to_pairs)
            if to_addrs:
                msg["To"] = ", ".join(to_addrs)

        orig_mid = original.message_id
        if orig_mid:
            msg["In-Reply-To"] = orig_mid
            existing_refs = get_header(original.headers, "References")
            msg["References"] = build_references(existing_refs, orig_mid)

        msg.set_content(body)

        return self.send(msg)

    def reply_all(
        self,
        original: EmailMessage,
        *,
        body: str,
        from_addr: Optional[str] = None,
    ) -> SendResult:
        """
        Reply to everyone:

        - To: Reply-To (or From) from original
        - Cc: everyone in original To/Cc (except yourself and duplicates)
        - Subject: Re: <original subject>
        - Threading: In-Reply-To, References
        """
        msg = PyEmailMessage()

        if from_addr:
            msg["From"] = from_addr

        msg["Subject"] = ensure_reply_subject(original.subject)

        primary = get_header(original.headers, "Reply-To") or original.from_email
        primary_pairs = parse_addrs(primary) if primary else []

        to_str = ", ".join(original.to) if original.to else ""
        cc_str = ", ".join(original.cc) if original.cc else ""
        others_pairs = parse_addrs(to_str, cc_str)

        others_pairs = remove_addr(others_pairs, from_addr)

        primary_set = {addr.strip().lower() for _, addr in primary_pairs}
        cc_pairs = [(n, a) for (n, a) in others_pairs if a.strip().lower() not in primary_set]

        to_addrs = dedup_addrs(primary_pairs)
        cc_addrs = dedup_addrs(cc_pairs)

        if to_addrs:
            msg["To"] = ", ".join(to_addrs)
        if cc_addrs:
            msg["Cc"] = ", ".join(cc_addrs)

        orig_mid = original.message_id
        if orig_mid:
            msg["In-Reply-To"] = orig_mid
            existing_refs = get_header(original.headers, "References")
            msg["References"] = build_references(existing_refs, orig_mid)

        msg.set_content(body)

        return self.send(msg)

    def imap_query(self, mailbox: str = "INBOX") -> EasyIMAPQuery:
        return EasyIMAPQuery(self, mailbox=mailbox)

    def fetch_latest(
        self,
        *,
        mailbox: str = "INBOX",
        n: int = 50,
        unseen_only: bool = False,
        include_attachments: bool = False,
    ):
        q = self.imap_query(mailbox).limit(n)
        if unseen_only:
            q.unseen()
        return q.fetch(include_attachments=include_attachments)

    def add_flags(self, refs: Sequence[EmailRef], flags: Set[str]) -> None:
        """Bulk add flags to refs."""
        if not refs:
            return
        self.imap.add_flags(refs, flags=flags)

    def remove_flags(self, refs: Sequence[EmailRef], flags: Set[str]) -> None:
        """Bulk remove flags from refs."""
        if not refs:
            return
        self.imap.remove_flags(refs, flags=flags)

    def mark_seen(self, refs: Sequence[EmailRef]) -> None:
        self.add_flags(refs, {SEEN})

    def mark_all_seen(self, mailbox: str = "INBOX", *, chunk_size: int = 500) -> int:
        total = 0
        while True:
            refs = self.imap_query(mailbox).unseen().limit(chunk_size).search()
            if not refs:
                break
            self.add_flags(refs, {SEEN})
            total += len(refs)
        return total

    def mark_unseen(self, refs: Sequence[EmailRef]) -> None:
        self.remove_flags(refs, {SEEN})

    def flag(self, refs: Sequence[EmailRef]) -> None:
        self.add_flags(refs, {FLAGGED})

    def unflag(self, refs: Sequence[EmailRef]) -> None:
        self.remove_flags(refs, {FLAGGED})

    def delete(self, refs: Sequence[EmailRef]) -> None:
        self.add_flags(refs, {DELETED})

    def undelete(self, refs: Sequence[EmailRef]) -> None:
        self.remove_flags(refs, {DELETED})

    def list_unsubscribe_candidates(
        self,
        *,
        mailbox: str = "INBOX",
        limit: int = 200,
        since: Optional[str] = None,
        unseen_only: bool = False,
    ) -> List[UnsubscribeCandidate]:
        """
        Returns emails that expose List-Unsubscribe.
        Requires your parser to preserve headers (List-Unsubscribe).
        """
        detector = SubscriptionDetector(self.imap)
        return detector.find(
            mailbox=mailbox,
            limit=limit,
            since=since,
            unseen_only=unseen_only,
        )

    def unsubscribe_selected(
        self,
        candidates: Sequence[UnsubscribeCandidate],
        *,
        prefer: str = "mailto",
        from_addr: Optional[str] = None,
        dry_run: bool = True,
    ) -> Dict[str, List[UnsubscribeActionResult]]:
        """
        Delegates unsubscribe execution to SubscriptionService.

        Safety:
        - dry_run=True does not send anything
        - http unsubscribe is returned for manual action (no requests)
        """
        service = SubscriptionService(self.smtp)
        return service.unsubscribe(
            list(candidates),
            prefer=prefer,
            from_addr=from_addr,
            dry_run=dry_run,
        )
    
    def generate_reply(
        self,
        message: EmailMessage,
        *,
        model_path: str,
    ) -> Tuple[str, Dict[str, Any]]:
        return llm_concise_reply_for_email(
            message,
            model_path=model_path,
        )
    
    def summarize_email(
        self,
        message: EmailMessage,
        *,
        model_path: str,
    ) -> Tuple[str, Dict[str, Any]]:
        return llm_summarize_single_email(
            message,
            model_path=model_path,
        )
    
    def summarize_multi_emails(
        self,
        messages: Sequence[EmailMessage],
        *,
        model_path: str,
    ) -> Tuple[str, Dict[str, Any]]:
        
        if not messages:
            return "No emails selected.", {}


        return llm_summarize_many_emails(
            messages,
            model_path=model_path,
        )