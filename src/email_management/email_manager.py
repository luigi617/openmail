from __future__ import annotations

from datetime import datetime
import html as _html
from dataclasses import dataclass
from email.message import EmailMessage as PyEmailMessage
from typing import Dict, List, Optional, Sequence, Set

from .email_query import EasyIMAPQuery
from email_management.models import (UnsubscribeCandidate,
                                     EmailMessage,
                                     EmailOverview,
                                     UnsubscribeActionResult,
                                     Attachment)
from email_management.subscription import SubscriptionService, SubscriptionDetector
from email_management.imap import IMAPClient, PagedSearchResult
from email_management.smtp import SMTPClient
from email_management.types import EmailRef, SendResult
from email_management.utils import (ensure_reply_subject,
                                    ensure_forward_subject,
                                    get_header,
                                    parse_addrs,
                                    dedup_addrs,
                                    build_references,
                                    remove_addr,
                                    quote_original_text,
                                    quote_original_html)


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
    
    def fetch_message_by_ref(
        self,
        ref: EmailRef,
        *,
        include_attachments: bool = False,
    ) -> EmailMessage:
        """
        Fetch exactly one EmailMessage by EmailRef.
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
        """
        Fetch multiple EmailMessage by EmailRef.
        """
        if not refs:
            return []
        return list(self.imap.fetch(refs, include_attachments=include_attachments))

    def send(self, msg: PyEmailMessage) -> SendResult:
        return self.smtp.send(msg)
    
    def send_later(
        self,
        *,
        subject: str,
        to: Sequence[str],
        from_addr: Optional[str] = None,
        scheduled_at: datetime,
        cc: Sequence[str] = (),
        bcc: Sequence[str] = (),
        text: Optional[str] = None,
        html: Optional[str] = None,
        attachments: Optional[Sequence[Attachment]] = None,
        extra_headers: Optional[Dict[str, str]] = None,
    ) -> PyEmailMessage:
        """
        Build an email intended for future sending.
        Caller can store/send later via EmailManager.send(msg).
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
        msg["X-Scheduled-At"] = scheduled_at.isoformat()
        return msg

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
        if not to:
            raise ValueError("compose(): 'to' must contain at least one recipient")

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
        body: str,
        body_html: Optional[str] = None,
        from_addr: Optional[str] = None,
        quote_original: bool = False,
    ) -> SendResult:
        """
        Reply to a single sender, based on our EmailMessage model.

        - To: Reply-To (if present) or From of the original
        - Subject: Re: <original subject> (added only once)
        - Threading: In-Reply-To, References (if message_id is present)
        - body: plain-text reply body
        - body_html: optional HTML version of the reply
        - quote_original: if True, append a quoted block of the original email
          to the reply (text and HTML, if available)
        """
        msg = PyEmailMessage()

        if from_addr:
            msg["From"] = from_addr

        msg["Subject"] = ensure_reply_subject(original.subject)

        reply_to = get_header(original.headers, "Reply-To") or original.from_email
        if not reply_to:
            raise ValueError("reply(): original message has no Reply-To or From address")
        
        to_pairs = parse_addrs(reply_to)
        to_addrs = dedup_addrs(to_pairs)
        if not to_addrs:
            raise ValueError("reply(): could not parse any valid reply addresses")

        msg["To"] = ", ".join(to_addrs)

        orig_mid = original.message_id
        if orig_mid:
            msg["In-Reply-To"] = orig_mid
            existing_refs = get_header(original.headers, "References")
            msg["References"] = build_references(existing_refs, orig_mid)

        if quote_original:
            quoted_text = quote_original_text(original)
            text_body = body + "\n\n" + quoted_text if body else quoted_text

            if body_html is not None:
                quoted_html = quote_original_html(original)
                html_body = body_html + "<br><br>" + quoted_html
            else:
                html_body = None
        else:
            text_body = body
            html_body = body_html

        self._set_body(msg, text_body, html_body)

        return self.send(msg)

    def reply_all(
        self,
        original: EmailMessage,
        *,
        body: str,
        body_html: Optional[str] = None,
        from_addr: Optional[str] = None,
        quote_original: bool = False,
    ) -> SendResult:
        """
        Reply to everyone:

        - To: Reply-To (or From) from original
        - Cc: everyone in original To/Cc (except yourself and duplicates)
        - Subject: Re: <original subject>
        - Threading: In-Reply-To, References
        - body/body_html: reply content
        - quote_original: if True, append a quoted block of the original email
          to the reply (text and HTML, if available)
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

        if from_addr:
            primary_pairs = remove_addr(primary_pairs, from_addr)
            others_pairs = remove_addr(others_pairs, from_addr)

        primary_set = {addr.strip().lower() for _, addr in primary_pairs}
        cc_pairs = [(n, a) for (n, a) in others_pairs if a.strip().lower() not in primary_set]

        to_addrs = dedup_addrs(primary_pairs)
        cc_addrs = dedup_addrs(cc_pairs)

        if not to_addrs:
            raise ValueError("reply_all(): no primary recipients after filtering")

        msg["To"] = ", ".join(to_addrs)

        if cc_addrs:
            msg["Cc"] = ", ".join(cc_addrs)

        orig_mid = original.message_id
        if orig_mid:
            msg["In-Reply-To"] = orig_mid
            existing_refs = get_header(original.headers, "References")
            msg["References"] = build_references(existing_refs, orig_mid)

        if quote_original:
            quoted_text = quote_original_text(original)
            text_body = body + "\n\n" + quoted_text if body else quoted_text

            if body_html is not None:
                quoted_html = quote_original_html(original)
                html_body = body_html + "<br><br>" + quoted_html
            else:
                html_body = None
        else:
            text_body = body
            html_body = body_html

        self._set_body(msg, text_body, html_body)

        return self.send(msg)

    def forward(
        self,
        original: EmailMessage,
        *,
        to: Sequence[str],
        body: Optional[str] = None,
        body_html: Optional[str] = None,
        from_addr: Optional[str] = None,
        include_attachments: bool = True,
    ) -> SendResult:
        """
        Forward an existing email.

        - To: explicit `to`
        - From: optional `from_addr`
        - Subject: Fwd: <original subject> (added only once)
        - Body (HTML): optional HTML version; if None but original has HTML,
          we build a simple HTML block quoting the original.
        - Attachments: optionally re-attached from the original message
        """
        if not to:
            raise ValueError("forward(): 'to' must contain at least one recipient")
        msg = PyEmailMessage()

        if from_addr:
            msg["From"] = from_addr

        msg["To"] = ", ".join(to)
        msg["Subject"] = ensure_forward_subject(original.subject or "")

        parts: List[str] = []

        if body:
            parts.append(body)

        quoted_lines: List[str] = []
        quoted_lines.append("")
        quoted_lines.append("---- Forwarded message ----")
        quoted_lines.append(f"From: {original.from_email}")
        if original.to:
            quoted_lines.append(f"To: {', '.join(original.to)}")
        if original.cc:
            quoted_lines.append(f"Cc: {', '.join(original.cc)}")
        if original.date:
            quoted_lines.append(f"Date: {original.date.isoformat()}")
        if original.subject:
            quoted_lines.append(f"Subject: {original.subject}")
        quoted_lines.append("")
        if original.text:
            quoted_lines.append(original.text)

        parts.append("\n".join(quoted_lines))
        text_body = "\n".join(parts)

        html_body: Optional[str] = body_html
        if html_body is None and (original.html or original.text):
            html_parts: List[str] = []

            if body:
                html_parts.append(f"<p>{_html.escape(body)}</p>")

            html_parts.append("<hr>")
            html_parts.append("<p>---- Forwarded message ----</p>")

            header_lines: List[str] = []
            header_lines.append(f"From: {original.from_email}")
            if original.to:
                header_lines.append(f"To: {', '.join(original.to)}")
            if original.cc:
                header_lines.append(f"Cc: {', '.join(original.cc)}")
            if original.date:
                header_lines.append(f"Date: {original.date.isoformat()}")
            if original.subject:
                header_lines.append(f"Subject: {original.subject}")

            header_html = "<br>".join(_html.escape(line) for line in header_lines)
            html_parts.append(f"<p>{header_html}</p>")

            if original.html:
                html_parts.append(original.html)
            elif original.text:
                html_parts.append("<pre>" + _html.escape(original.text) + "</pre>")

            html_body = "\n".join(html_parts)

        self._set_body(msg, text_body, html_body)


        # Attachments (if your Attachment model supports this)

        if include_attachments and original.attachments:
            self._add_attachment(msg, original.attachments)

        return self.send(msg)
    
    def imap_query(self, mailbox: str = "INBOX") -> EasyIMAPQuery:
        return EasyIMAPQuery(self, mailbox=mailbox)

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
        include_attachments: bool = False,
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
            include_attachments=include_attachments,
        )
        return page, messages

    def fetch_thread(
        self,
        root: EmailMessage,
        *,
        mailbox: str = "INBOX",
        include_attachments: bool = False,
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

        _, msgs = q.fetch(include_attachments=include_attachments)

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

        # Build a reusable EasyIMAPQuery for UNSEEN messages in this mailbox
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

            if not page.has_more or page.next_before_uid is None:
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

    def __enter__(self) -> "EmailManager":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()
