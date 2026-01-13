from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Set

from email.message import EmailMessage as PyEmailMessage

from email_management.errors import IMAPError
from email_management.models import EmailMessage
from email_management.types import EmailRef
from email_management.imap.query import IMAPQuery
from email_management.imap.parser import parse_rfc822


@dataclass
class _StoredMessage:
    msg: EmailMessage
    flags: Set[str]


@dataclass
class FakeIMAPClient:
    """
    In-memory IMAP client for testing.

    - No network or real IMAP server.
    - Mailboxes and messages are stored in memory.
    - Public API is compatible with IMAPClient for typical usage in EmailManager.
    """

    # You can pass anything here in tests (IMAPConfig, dummy object, None)
    config: Optional[object] = None

    # mailbox -> uid -> _StoredMessage
    _mailboxes: Dict[str, Dict[int, _StoredMessage]] = field(default_factory=dict)
    _next_uid: int = 1

    # If True, the next IMAP operation will raise IMAPError (for error paths).
    fail_next: bool = False

    # --- internal helpers -------------------------------------------------

    def _ensure_mailbox(self, name: str) -> Dict[int, _StoredMessage]:
        return self._mailboxes.setdefault(name, {})

    def _alloc_uid(self) -> int:
        uid = self._next_uid
        self._next_uid += 1
        return uid

    def _maybe_fail(self) -> None:
        if self.fail_next:
            self.fail_next = False
            raise IMAPError("FakeIMAPClient forced failure")

    # --- test helpers (optional but handy) --------------------------------

    def add_parsed_message(
        self,
        mailbox: str,
        msg: EmailMessage,
        *,
        flags: Optional[Set[str]] = None,
    ) -> EmailRef:
        """
        Seed a mailbox with an existing EmailMessage model.

        Returns the EmailRef used to store it.
        """
        box = self._ensure_mailbox(mailbox)
        uid = self._alloc_uid()
        ref = EmailRef(uid=uid, mailbox=mailbox)

        # Replace ref so EmailManager.fetch_message_by_ref works.
        stored_msg = EmailMessage(
            ref=ref,
            subject=msg.subject,
            from_email=msg.from_email,
            to=msg.to,
            cc=msg.cc,
            bcc=msg.bcc,
            text=msg.text,
            html=msg.html,
            attachments=list(msg.attachments),
            date=msg.date,
            message_id=msg.message_id,
            headers=dict(msg.headers),
        )
        box[uid] = _StoredMessage(stored_msg, set(flags or set()))
        return ref

    # --- API matching real IMAPClient -------------------------------------

    def search(self, *, mailbox: str, query: IMAPQuery, limit: int = 50) -> List[EmailRef]:
        """
        Very small subset of IMAP SEARCH semantics:

        - UNSEEN / SEEN
        - DELETED / UNDELETED
        - DRAFT / UNDRAFT
        - FLAGGED / UNFLAGGED
        - HEADER "List-Unsubscribe" "" (header present)

        Everything else is effectively ignored.
        """
        self._maybe_fail()
        box = self._mailboxes.get(mailbox, {})
        parts = list(query.parts)

        refs: List[EmailRef] = []
        for uid in sorted(box.keys(), reverse=True):  # newest first
            stored = box[uid]
            if self._matches_query(stored, parts):
                refs.append(EmailRef(uid=uid, mailbox=mailbox))
                if len(refs) >= limit:
                    break
        return refs

    def _matches_query(self, stored: _StoredMessage, parts: List[str]) -> bool:
        flags = stored.flags
        msg = stored.msg

        # Flags-based filters
        if "UNSEEN" in parts and r"\Seen" in flags:
            return False
        if "SEEN" in parts and r"\Seen" not in flags:
            return False
        if "DELETED" in parts and r"\Deleted" not in flags:
            return False
        if "UNDELETED" in parts and r"\Deleted" in flags:
            return False
        if "DRAFT" in parts and r"\Draft" not in flags:
            return False
        if "UNDRAFT" in parts and r"\Draft" in flags:
            return False
        if "FLAGGED" in parts and r"\Flagged" not in flags:
            return False
        if "UNFLAGGED" in parts and r"\Flagged" in flags:
            return False

        # Simple header presence check for newsletter-related queries:
        # IMAPQuery.header("List-Unsubscribe", "")
        for i, token in enumerate(parts):
            if token == "HEADER" and i + 2 < len(parts):
                name_token = parts[i + 1].strip('"')
                value_token = parts[i + 2].strip('"')
                if name_token.lower() == "list-unsubscribe":
                    has_header = any(
                        k.lower() == "list-unsubscribe" for k in msg.headers.keys()
                    )
                    if value_token == "":
                        if not has_header:
                            return False
                    else:
                        header_val = msg.headers.get("List-Unsubscribe", "")
                        if value_token.lower() not in header_val.lower():
                            return False

        # Everything else: accept
        return True

    def fetch(
        self,
        refs: Sequence[EmailRef],
        *,
        include_attachments: bool = False,
    ) -> List[EmailMessage]:
        self._maybe_fail()
        if not refs:
            return []

        out: List[EmailMessage] = []
        for r in refs:
            box = self._mailboxes.get(r.mailbox, {})
            stored = box.get(r.uid)
            if not stored:
                continue

            msg = stored.msg
            if include_attachments:
                out.append(msg)
            else:
                # Shallow clone without attachments
                out.append(
                    EmailMessage(
                        ref=msg.ref,
                        subject=msg.subject,
                        from_email=msg.from_email,
                        to=msg.to,
                        cc=msg.cc,
                        bcc=msg.bcc,
                        text=msg.text,
                        html=msg.html,
                        attachments=[],
                        date=msg.date,
                        message_id=msg.message_id,
                        headers=dict(msg.headers),
                    )
                )
        return out

    def append(
        self,
        mailbox: str,
        msg: PyEmailMessage,
        *,
        flags: Optional[Set[str]] = None,
    ) -> EmailRef:
        """
        Behaves similarly to real IMAPClient.append: parses the RFC822 message
        into an EmailMessage and stores it with a new UID.
        """
        self._maybe_fail()
        box = self._ensure_mailbox(mailbox)
        uid = self._alloc_uid()
        ref = EmailRef(uid=uid, mailbox=mailbox)

        raw = msg.as_bytes()
        parsed = parse_rfc822(ref, raw, include_attachments=True)
        box[uid] = _StoredMessage(parsed, set(flags or set()))
        return ref

    # --- flag operations ---------------------------------------------------

    def add_flags(self, refs: Sequence[EmailRef], *, flags: Set[str]) -> None:
        self._maybe_fail()
        for r in refs:
            box = self._mailboxes.get(r.mailbox, {})
            stored = box.get(r.uid)
            if stored:
                stored.flags |= set(flags)

    def remove_flags(self, refs: Sequence[EmailRef], *, flags: Set[str]) -> None:
        self._maybe_fail()
        for r in refs:
            box = self._mailboxes.get(r.mailbox, {})
            stored = box.get(r.uid)
            if stored:
                stored.flags -= set(flags)

    # --- mailbox maintenance ----------------------------------------------

    def expunge(self, mailbox: str = "INBOX") -> None:
        """
        Remove messages flagged as \\Deleted from a mailbox.
        """
        self._maybe_fail()
        box = self._mailboxes.get(mailbox, {})
        to_delete = [uid for uid, s in box.items() if r"\Deleted" in s.flags]
        for uid in to_delete:
            del box[uid]

    def list_mailboxes(self) -> List[str]:
        self._maybe_fail()
        return sorted(self._mailboxes.keys())

    def mailbox_status(self, mailbox: str = "INBOX") -> Dict[str, int]:
        self._maybe_fail()
        box = self._mailboxes.get(mailbox, {})
        messages = len(box)
        unseen = sum(1 for s in box.values() if r"\Seen" not in s.flags)
        return {"messages": messages, "unseen": unseen}

    # --- copy / move / mailbox ops ----------------------------------------

    def move(
        self,
        refs: Sequence[EmailRef],
        *,
        src_mailbox: str,
        dst_mailbox: str,
    ) -> None:
        self._maybe_fail()
        if not refs:
            return

        src = self._mailboxes.get(src_mailbox, {})
        dst = self._ensure_mailbox(dst_mailbox)

        for r in refs:
            stored = src.pop(r.uid, None)
            if stored:
                # Assign a new UID in the destination mailbox
                new_uid = self._next_uid
                self._next_uid += 1
                dst[new_uid] = stored


    def copy(
        self,
        refs: Sequence[EmailRef],
        *,
        src_mailbox: str,
        dst_mailbox: str,
    ) -> None:
        self._maybe_fail()
        if not refs:
            return

        src = self._mailboxes.get(src_mailbox, {})
        dst = self._ensure_mailbox(dst_mailbox)

        for r in refs:
            stored = src.get(r.uid)
            if stored:
                # Assign a new UID in the destination mailbox
                new_uid = self._next_uid
                self._next_uid += 1
                # shallow copy of EmailMessage, copy of flags
                dst[new_uid] = _StoredMessage(stored.msg, set(stored.flags))

    def create_mailbox(self, name: str) -> None:
        self._maybe_fail()
        self._ensure_mailbox(name)

    def delete_mailbox(self, name: str) -> None:
        self._maybe_fail()
        self._mailboxes.pop(name, None)

    def ping(self) -> None:
        """
        Minimal health check; used by EmailManager.health_check.
        """
        self._maybe_fail()
        # no-op if not failing
