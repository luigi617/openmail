from __future__ import annotations

import html as _html
from dataclasses import dataclass
from email.message import EmailMessage as PyEmailMessage
from typing import Dict, List, Optional, Sequence, Set

from openmail.imap import IMAPClient, PagedSearchResult
from openmail.models import (
    Attachment,
    EmailMessage,
    EmailOverview,
    UnsubscribeActionResult,
    UnsubscribeCandidate,
)
from openmail.smtp import SMTPClient
from openmail.subscription import SubscriptionDetector, SubscriptionService
from openmail.types import EmailRef, SendResult
from openmail.utils import (
    build_references,
    dedup_addrs,
    ensure_forward_subject,
    ensure_reply_subject,
    get_header,
    parse_addrs,
    quote_forward_html,
    quote_forward_text,
    quote_original_reply_html,
    quote_original_reply_text,
    remove_addr,
)

from .email_query import EmailQuery

SEEN = r"\Seen"
ANSWERED = r"\Answered"
FLAGGED = r"\Flagged"
DELETED = r"\Deleted"
DRAFT = r"\Draft"

@dataclass(frozen=True)
class EmailManager:
    smtp: SMTPClient
    imap: IMAPClient

    def _set_body(
        self,
        msg: PyEmailMessage,
        text: Optional[str],
        html: Optional[str],
    ) -> None:
        """
        Set message body as:
        - text only if no html
        - multipart/alternative if both text and html are provided
        - html-only if only html is provided
        """
        if html is not None:
            if text:
                msg.set_content(text)
                msg.add_alternative(html, subtype="html")
            else:
                msg.set_content(html, subtype="html")
        else:
            msg.set_content(text or "")

    def _add_attachment(
        self,
        msg: PyEmailMessage,
        attachments: Optional[Sequence[Attachment]],
    ) -> None:
        """
        Add attachments to the email message.
        """
        if not attachments:
            return

        for att in attachments:
            content_type = att.content_type or "application/octet-stream"
            maintype, _, subtype = content_type.partition("/")
            data = att.data
            filename = att.filename
            if data is not None:
                msg.add_attachment(
                    data,
                    maintype=maintype or "application",
                    subtype=subtype or "octet-stream",
                    filename=filename,
                )
    
    def _extract_envelope_recipients(self, msg: PyEmailMessage) -> list[str]:
        addr_headers = []
        addr_headers.extend(msg.get_all("To", []))
        addr_headers.extend(msg.get_all("Cc", []))
        addr_headers.extend(msg.get_all("Bcc", []))

        pairs = parse_addrs(*addr_headers)
        # simple dedup by lowercase address
        seen = set()
        result: list[str] = []
        for _, addr in pairs:
            norm = addr.strip().lower()
            if norm and norm not in seen:
                seen.add(norm)
                result.append(addr)
        return result
    
    def fetch_message_by_ref(
        self,
        ref: EmailRef,
        *,
        include_attachment_meta: bool = False,
    ) -> EmailMessage:
        """
        Fetch exactly one EmailMessage by EmailRef.
        """
        msgs = self.imap.fetch([ref], include_attachment_meta=include_attachment_meta)
        if not msgs:
            raise ValueError(f"No message found for ref: {ref!r}")
        return msgs[0]
    
    def fetch_attachment_by_ref_and_meta(
        self,
        ref: EmailRef,
        attachment_part: str,
    ) -> bytes:
        """
        Fetch exactly one EmailMessage by EmailRef.
        """
        attachment = self.imap.fetch_attachment(ref, attachment_part)
        if not attachment:
            raise ValueError(f"No attachment found for ref: {ref!r} and part: {attachment_part!r}")
        return attachment

    def fetch_messages_by_multi_refs(
        self,
        refs: Sequence[EmailRef],
        *,
        include_attachment_meta: bool = False,
    ) -> List[EmailMessage]:
        """
        Fetch multiple EmailMessage by EmailRef.
        """
        if not refs:
            return []
        return list(self.imap.fetch(refs, include_attachment_meta=include_attachment_meta))

    def send(self, msg: PyEmailMessage) -> SendResult:
        recipients = self._extract_envelope_recipients(msg)

        if "Bcc" in msg:
            del msg["Bcc"]
        
        if not recipients:
            raise ValueError("send(): no recipients found in To/Cc/Bcc")
    
        return self.smtp.send(msg, recipients)

    def compose(
        self,
        *,
        subject: str,
        to: Sequence[str],
        from_addr: Optional[str] = None,
        cc: Sequence[str] = (),
        bcc: Sequence[str] = (),
        text: Optional[str] = None,
        html: Optional[str] = None,
        attachments: Optional[Sequence[Attachment]] = None,
        extra_headers: Optional[Dict[str, str]] = None,
    ) -> PyEmailMessage:
        """
        Build a new outgoing email.

        - subject, to, from_addr are the main headers
        - text/html: plain-text and/or HTML bodies
        - attachments: list of your Attachment models
        - extra_headers: optional extra headers (e.g. Reply-To)
        """

        msg = PyEmailMessage()

        if from_addr:
            msg["From"] = from_addr
        msg["To"] = ", ".join(to)
        if cc:
            msg["Cc"] = ", ".join(cc)
        if bcc:
            msg["Bcc"] = ", ".join(bcc)

        msg["Subject"] = subject

        if extra_headers:
            for k, v in extra_headers.items():
                if k.lower() in {"from", "to", "cc", "bcc", "subject"}:
                    continue
                msg[k] = v

        self._set_body(msg, text, html)
        self._add_attachment(msg, attachments)

        return msg
    
    def compose_and_send(
        self,
        *,
        subject: str,
        to: Sequence[str],
        from_addr: Optional[str] = None,
        cc: Sequence[str] = (),
        bcc: Sequence[str] = (),
        text: Optional[str] = None,
        html: Optional[str] = None,
        attachments: Optional[Sequence[Attachment]] = None,
        extra_headers: Optional[Dict[str, str]] = None,
    ) -> SendResult:
        """
        Convenience wrapper: compose a new email and send it.
        """

        if not to and not cc and not bcc:
            raise ValueError(
                "compose_and_send(): at least one of to/cc/bcc must contain a recipient"
            )
    
        msg = self.compose(
            subject=subject,
            to=to,
            from_addr=from_addr,
            cc=cc,
            bcc=bcc,
            text=text,
            html=html,
            attachments=attachments,
            extra_headers=extra_headers,
        )
        return self.send(msg)
    
    def save_draft(
        self,
        *,
        subject: str,
        to: Sequence[str],
        from_addr: Optional[str] = None,
        cc: Sequence[str] = (),
        bcc: Sequence[str] = (),
        text: Optional[str] = None,
        html: Optional[str] = None,
        attachments: Optional[Sequence[Attachment]] = None,
        extra_headers: Optional[Dict[str, str]] = None,
        mailbox: str = "Drafts",
    ) -> EmailRef:
        """
        Compose an email and save it to a Drafts mailbox without sending.
        Returns EmailRef for later .send().
        """
        msg = self.compose(
            subject=subject,
            to=to,
            from_addr=from_addr,
            cc=cc,
            bcc=bcc,
            text=text,
            html=html,
            attachments=attachments,
            extra_headers=extra_headers,
        )
        return self.imap.append(mailbox, msg, flags={DRAFT})

    def reply(
        self,
        original: EmailMessage,
        *,
        text: str,
        html: Optional[str] = None,
        from_addr: Optional[str] = None,
        quote_original: bool = False,
        to: Optional[Sequence[str]] = None,
        cc: Optional[Sequence[str]] = None,
        bcc: Optional[Sequence[str]] = None,
        subject: Optional[str] = None,
        attachments: Optional[Sequence[Attachment]] = None,
        extra_headers: Optional[Dict[str, str]] = None,
    ) -> SendResult:
        """
        Reply to a single sender.

        - If to/cc/bcc/subject/attachments are None, sensible defaults are derived
          from `original`.
        - If provided, they override the defaults but threading headers are still
          managed here.
        """
        if to is None:
            reply_to = get_header(original.headers, "Reply-To") or original.from_email
            if not reply_to:
                raise ValueError("reply(): original message has no Reply-To or From address")

            to_pairs = parse_addrs(reply_to)
            to_addrs = dedup_addrs(to_pairs)
            if not to_addrs:
                raise ValueError("reply(): could not parse any valid reply addresses")
        else:
            to_addrs = list(to)

        cc_addrs = list(cc) if cc is not None else []
        bcc_addrs = list(bcc) if bcc is not None else []

        final_subject = subject or ensure_reply_subject(original.subject)

        headers: Dict[str, str] = {}
        orig_mid = original.message_id
        if orig_mid:
            headers["In-Reply-To"] = orig_mid
            existing_refs = get_header(original.headers, "References")
            headers["References"] = build_references(existing_refs, orig_mid)

        if extra_headers:
            headers.update(extra_headers)

        if quote_original:
            quoted_text = quote_original_reply_text(original)
            text_body = text + "\n\n" + quoted_text if text else quoted_text

            if html is not None:
                quoted_html = quote_original_reply_html(original)
                html_body = html + "<br><br>" + quoted_html
            else:
                html_body = None
        else:
            text_body = text
            html_body = html

        msg = self.compose(
            subject=final_subject,
            to=to_addrs,
            from_addr=from_addr,
            cc=cc_addrs,
            bcc=bcc_addrs,
            text=text_body,
            html=html_body,
            attachments=attachments,
            extra_headers=headers or None,
        )

        return self.send(msg)

    def reply_all(
        self,
        original: EmailMessage,
        *,
        text: str,
        html: Optional[str] = None,
        from_addr: Optional[str] = None,
        quote_original: bool = False,
        to: Optional[Sequence[str]] = None,
        cc: Optional[Sequence[str]] = None,
        bcc: Optional[Sequence[str]] = None,
        subject: Optional[str] = None,
        attachments: Optional[Sequence[Attachment]] = None,
        extra_headers: Optional[Dict[str, str]] = None,
    ) -> SendResult:
        """
        Reply to everyone.

        - If to/cc/bcc are None, they are derived from original (Reply-To/From + To/Cc).
        - If provided, we trust the UI values and do not recompute recipients.
        """
        # Recipients
        if to is None and cc is None and bcc is None:
            # Derive default reply-all recipients
            primary = get_header(original.headers, "Reply-To") or original.from_email
            primary_pairs = parse_addrs(primary) if primary else []

            to_str = ", ".join(original.to) if original.to else ""
            cc_str = ", ".join(original.cc) if original.cc else ""
            others_pairs = parse_addrs(to_str, cc_str)

            if from_addr:
                primary_pairs = remove_addr(primary_pairs, from_addr)
                others_pairs = remove_addr(others_pairs, from_addr)

            primary_set = {addr.strip().lower() for _, addr in primary_pairs}
            cc_pairs = [(n, a) for (n, a) in others_pairs if a.strip().lower() not in primary_set]

            to_addrs = dedup_addrs(primary_pairs)
            cc_addrs = dedup_addrs(cc_pairs)
            bcc_addrs: List[str] = []
        else:
            to_addrs = list(to) if to is not None else []
            cc_addrs = list(cc) if cc is not None else []
            bcc_addrs = list(bcc) if bcc is not None else []

        if not to_addrs:
            raise ValueError("reply_all(): no primary recipients")

        final_subject = subject or ensure_reply_subject(original.subject)

        headers: Dict[str, str] = {}
        orig_mid = original.message_id
        if orig_mid:
            headers["In-Reply-To"] = orig_mid
            existing_refs = get_header(original.headers, "References")
            headers["References"] = build_references(existing_refs, orig_mid)

        if extra_headers:
            headers.update(extra_headers)

        if quote_original:
            quoted_text = quote_original_reply_text(original)
            text_body = text + "\n\n" + quoted_text if text else quoted_text

            if html is not None:
                quoted_html = quote_original_reply_html(original)
                html_body = html + "<br><br>" + quoted_html
            else:
                html_body = None
        else:
            text_body = text
            html_body = html

        msg = self.compose(
            subject=final_subject,
            to=to_addrs,
            from_addr=from_addr,
            cc=cc_addrs,
            bcc=bcc_addrs,
            text=text_body,
            html=html_body,
            attachments=attachments,
            extra_headers=headers or None,
        )

        return self.send(msg)

    def forward(
        self,
        original: EmailMessage,
        *,
        to: Sequence[str],
        text: Optional[str] = None,
        html: Optional[str] = None,
        from_addr: Optional[str] = None,
        include_original: bool = False,
        include_attachments: bool = True,
        cc: Optional[Sequence[str]] = None,
        bcc: Optional[Sequence[str]] = None,
        subject: Optional[str] = None,
        attachments: Optional[Sequence[Attachment]] = None,
        extra_headers: Optional[Dict[str, str]] = None,
    ) -> SendResult:
        """
        Forward an existing email.
        """
        if not to:
            raise ValueError("forward(): 'to' must contain at least one recipient")

        text_parts: List[str] = []
        if text:
            text_parts.append(text)
        if include_original:
            text_parts.append(quote_forward_text(original))
        text_body = "\n".join(text_parts)

        if html is not None:
            html_body = html
        else:
            html_parts: List[str] = []
            if text:
                html_parts.append(f"<p>{_html.escape(text)}</p>")
            if include_original:
                quoted_html = quote_forward_html(original)
                if quoted_html is not None:
                    html_parts.append(quoted_html)
            html_body = "\n".join(html_parts) if html_parts else None

        # Subject default
        final_subject = subject or ensure_forward_subject(original.subject or "")

        final_attachments = []
        if attachments is not None:
            final_attachments.extend(attachments)
        if include_attachments and original.attachments:
            final_attachments.extend(original.attachments)

        msg = self.compose(
            subject=final_subject,
            to=to,
            from_addr=from_addr,
            cc=cc or (),
            bcc=bcc or (),
            text=text_body,
            html=html_body,
            attachments=final_attachments,
            extra_headers=extra_headers,
        )

        return self.send(msg)
    
    def imap_query(self, mailbox: str = "INBOX") -> EmailQuery:
        return EmailQuery(self, mailbox=mailbox)

    def fetch_overview(
        self,
        *,
        mailbox: str = "INBOX",
        n: int = 50,
        before_uid: Optional[int] = None,
        after_uid: Optional[int] = None,
        refresh: bool = False,
    ) -> tuple[PagedSearchResult, List[EmailOverview]]:
        """
        Fetch a page of EmailOverview objects with paging metadata.

        - For the first (latest) page, call with refresh=True, before_uid=None.
        - For next (older) pages, call with before_uid=prev_page.next_before_uid.
        - For previous (newer) pages, call with after_uid=prev_page.prev_after_uid.
        """
        q = self.imap_query(mailbox).limit(n)
        page, overviews = q.fetch_overview(
            before_uid=before_uid,
            after_uid=after_uid,
            refresh=refresh,
        )
        return page, overviews
    
    def fetch_latest(
        self,
        *,
        mailbox: str = "INBOX",
        n: int = 50,
        unseen_only: bool = False,
        include_attachment_meta: bool = False,
        before_uid: Optional[int] = None,
        after_uid: Optional[int] = None,
        refresh: bool = False,
    ) -> tuple[PagedSearchResult, List[EmailMessage]]:
        """
        Fetch a page of latest messages plus paging metadata.

        - For the first (latest) page, call with refresh=True, before_uid=None.
        - For next (older) pages, call with before_uid=prev_page.next_before_uid.
        - For previous (newer) pages, call with after_uid=prev_page.prev_after_uid.
        """
        q = self.imap_query(mailbox).limit(n)
        if unseen_only:
            q.query.unseen()

        page, messages = q.fetch(
            before_uid=before_uid,
            after_uid=after_uid,
            refresh=refresh,
            include_attachment_meta=include_attachment_meta,
        )
        return page, messages

    def fetch_thread(
        self,
        root: EmailMessage,
        *,
        mailbox: str = "INBOX",
        include_attachment_meta: bool = False,
    ) -> List[EmailMessage]:
        """
        Fetch messages belonging to the same thread as `root`.
        """
        if not root.message_id:
            return [root]

        q = (
            self.imap_query(mailbox)
            .for_thread_root(root)
            .limit(200)
        )

        _, msgs = q.fetch(include_attachment_meta=include_attachment_meta)

        # Ensure root is present exactly once
        mid = root.message_id
        if all(m.message_id != mid for m in msgs):
            msgs = [root] + msgs

        return msgs

    def add_flags(self, refs: Sequence[EmailRef], flags: Set[str]) -> None:
        """Bulk add flags to refs."""
        if not refs:
            return
        self.imap.add_flags(refs, flags=set(flags))

    def remove_flags(self, refs: Sequence[EmailRef], flags: Set[str]) -> None:
        """Bulk remove flags from refs."""
        if not refs:
            return
        self.imap.remove_flags(refs, flags=set(flags))

    def mark_seen(self, refs: Sequence[EmailRef]) -> None:
        self.add_flags(refs, {SEEN})

    def mark_all_seen(self, mailbox: str = "INBOX", *, chunk_size: int = 500) -> int:
        total = 0

        # Build a reusable EmailQuery for UNSEEN messages in this mailbox
        q = self.imap_query(mailbox).limit(chunk_size)
        q.query.unseen()

        before_uid: Optional[int] = None
        refresh = True  # do a real SEARCH once to build the cache

        while True:
            page = q.search(before_uid=before_uid, refresh=refresh)
            refresh = False  # all further pages come from cache

            refs = page.refs
            if not refs:
                break

            self.add_flags(refs, {SEEN})
            total += len(refs)

            if not page.has_next or page.next_before_uid is None:
                break

            before_uid = page.next_before_uid

        return total

    def mark_unseen(self, refs: Sequence[EmailRef]) -> None:
        self.remove_flags(refs, {SEEN})

    def flag(self, refs: Sequence[EmailRef]) -> None:
        self.add_flags(refs, {FLAGGED})

    def unflag(self, refs: Sequence[EmailRef]) -> None:
        self.remove_flags(refs, {FLAGGED})

    def mark_answered(self, refs: Sequence[EmailRef]) -> None:
        if refs:
            self.add_flags(refs, {ANSWERED})

    def clear_answered(self, refs: Sequence[EmailRef]) -> None:
        if refs:
            self.remove_flags(refs, {ANSWERED})

    def delete(self, refs: Sequence[EmailRef]) -> None:
        self.add_flags(refs, {DELETED})

    def undelete(self, refs: Sequence[EmailRef]) -> None:
        self.remove_flags(refs, {DELETED})

    def expunge(self, mailbox: str = "INBOX") -> None:
        """
        Permanently remove messages flagged as \\Deleted.
        """
        self.imap.expunge(mailbox)

    def list_mailboxes(self) -> List[str]:
        """
        Return a list of mailbox names.
        """
        return self.imap.list_mailboxes()
    
    def mailbox_status(self, mailbox: str = "INBOX") -> Dict[str, int]:
        """
        Return counters, e.g. {"messages": X, "unseen": Y}.
        """
        return self.imap.mailbox_status(mailbox)

    def move(
        self,
        refs: Sequence[EmailRef],
        *,
        src_mailbox: str,
        dst_mailbox: str,
    ) -> None:
        """
        Move messages between mailboxes.
        """
        if not refs:
            return
        self.imap.move(refs, src_mailbox=src_mailbox, dst_mailbox=dst_mailbox)

    def copy(
        self,
        refs: Sequence[EmailRef],
        *,
        src_mailbox: str,
        dst_mailbox: str,
    ) -> None:
        """
        Copy messages between mailboxes.
        """
        if not refs:
            return
        self.imap.copy(refs, src_mailbox=src_mailbox, dst_mailbox=dst_mailbox)
    
    def create_mailbox(self, name: str) -> None:
        """
        Create a new mailbox/folder.
        """
        self.imap.create_mailbox(name)

    def delete_mailbox(self, name: str) -> None:
        """
        Delete a mailbox/folder.
        """
        self.imap.delete_mailbox(name)

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
    
    def health_check(self) -> Dict[str, bool]:
        """
        Run minimal IMAP + SMTP checks.
        """
        imap_ok = False
        smtp_ok = False

        try:
            self.imap.ping()  # or list_mailboxes(), or NOOP
            imap_ok = True
        except Exception:
            pass

        try:
            self.smtp.ping()  # or EHLO/NOOP
            smtp_ok = True
        except Exception:
            pass

        return {"imap": imap_ok, "smtp": smtp_ok}

    def close(self) -> None:
        # Best-effort close both
        try:
            self.imap.close()
        except Exception:
            pass
        try:
            self.smtp.close()
        except Exception:
            pass

    def __enter__(self) -> EmailManager:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()
