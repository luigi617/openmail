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
from .email_query import EasyIMAPQuery
from email_management.models import UnsubscribeCandidate, EmailMessage, UnsubscribeActionResult
from email_management.subscription import SubscriptionService, SubscriptionDetector
from email_management.imap import IMAPClient
from email_management.smtp import SMTPClient
from email_management.types import EmailRef, SendResult
from email_management.utils import (ensure_reply_subject,
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
    ) -> Dict[str, List[UnsubscribeActionResult]]:
        """
        Delegates unsubscribe execution to SubscriptionService.
        """
        service = SubscriptionService(self.smtp)
        return service.unsubscribe(
            list(candidates),
            prefer=prefer,
            from_addr=from_addr,
        )