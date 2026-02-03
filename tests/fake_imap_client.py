from __future__ import annotations

from dataclasses import dataclass, field
from bisect import bisect_left, bisect_right
from typing import Dict, List, Optional, Sequence, Set, Tuple, Any

from email.message import EmailMessage as PyEmailMessage

from email_management.errors import IMAPError
from email_management.models import EmailMessage, EmailOverview
from email_management.types import EmailRef
from email_management.imap.query import IMAPQuery
from email_management.imap.parser import parse_rfc822, parse_overview
from email_management.imap.pagination import PagedSearchResult


@dataclass
class _StoredMessage:
    msg: EmailMessage
    flags: Set[str]


@dataclass
class FakeIMAPClient:
    """
    In-memory IMAP client for testing.

    Goals:
      - Keep public API compatible with current IMAPClient (search cache/pagination, fetch, fetch_overview,
        append, flag ops, mailbox ops, copy/move, expunge, ping, close, ctx manager).
      - Deterministic, in-memory behavior; no real IMAP semantics beyond what tests need.
    """

    config: Optional[object] = None

    # mailbox -> uid -> _StoredMessage
    _mailboxes: Dict[str, Dict[int, _StoredMessage]] = field(default_factory=dict)
    _next_uid: int = 1

    # cache key: (mailbox, criteria_str) -> ascending UID list
    _search_cache: Dict[Tuple[str, str], List[int]] = field(default_factory=dict)

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

    def _invalidate_search_cache(self, mailbox: Optional[str] = None) -> None:
        if mailbox is None:
            self._search_cache.clear()
            return
        keys = [k for k in self._search_cache.keys() if k[0] == mailbox]
        for k in keys:
            self._search_cache.pop(k, None)

    def _assert_same_mailbox(self, refs: Sequence[EmailRef], op_name: str) -> str:
        if not refs:
            raise IMAPError(f"{op_name} called with empty refs")
        mailbox = refs[0].mailbox
        for r in refs:
            if r.mailbox != mailbox:
                raise IMAPError(
                    f"All EmailRef.mailbox must match for {op_name} "
                    f"(got {refs[0].mailbox!r} and {r.mailbox!r})"
                )
        return mailbox

    # --- message cloning helpers -----------------------------------------

    def _clone_message_with_ref(self, msg: EmailMessage, new_ref: EmailRef) -> EmailMessage:
        # Rebuild EmailMessage to ensure `ref` is correct and nothing keeps old mailbox/uid.
        return EmailMessage(
            ref=new_ref,
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

    # --- test helpers -----------------------------------------------------

    def add_parsed_message(
        self,
        mailbox: str,
        msg: EmailMessage,
        *,
        flags: Optional[Set[str]] = None,
    ) -> EmailRef:
        """
        Seed a mailbox with an existing EmailMessage model. Returns the EmailRef used to store it.
        """
        self._maybe_fail()
        box = self._ensure_mailbox(mailbox)
        uid = self._alloc_uid()
        ref = EmailRef(uid=uid, mailbox=mailbox)

        stored_msg = self._clone_message_with_ref(msg, ref)
        box[uid] = _StoredMessage(stored_msg, set(flags or set()))
        self._invalidate_search_cache(mailbox)
        return ref

    # --- SEARCH + pagination (matches current IMAPClient surface) ---------

    def refresh_search_cache(self, *, mailbox: str, query: IMAPQuery) -> List[int]:
        """
        Compute (and cache) matching UIDs in ascending order.
        """
        self._maybe_fail()
        criteria = (query.build() or "ALL")
        cache_key = (mailbox, criteria)

        box = self._mailboxes.get(mailbox, {})
        parts = list(getattr(query, "parts", []))

        # Ascending old->new, like real client cache.
        uids: List[int] = []
        for uid in sorted(box.keys()):
            if self._matches_query(box[uid], parts):
                uids.append(uid)

        self._search_cache[cache_key] = uids
        return uids

    def search_page_cached(
        self,
        *,
        mailbox: str,
        query: IMAPQuery,
        page_size: int = 50,
        before_uid: Optional[int] = None,
        after_uid: Optional[int] = None,
        refresh: bool = False,
    ) -> PagedSearchResult:
        """
        Mirrors current IMAPClient.search_page_cached contract:
        - Cache stores ascending UIDs.
        - Returned refs are newest-first (descending) for the page.
        """
        self._maybe_fail()
        if before_uid is not None and after_uid is not None:
            raise ValueError("Cannot specify both before_uid and after_uid")

        criteria = (query.build() or "ALL")
        cache_key = (mailbox, criteria)

        uids = None if refresh else self._search_cache.get(cache_key)
        if uids is None:
            uids = self.refresh_search_cache(mailbox=mailbox, query=query)

        if not uids:
            return PagedSearchResult(refs=[], total=0, has_next=False, has_prev=False)

        uids_sorted = uids  # ascending old->new
        total_matches = len(uids_sorted)

        if before_uid is not None:
            idx = bisect_left(uids_sorted, before_uid)
            end = idx
            start = max(0, end - page_size)
        elif after_uid is not None:
            idx = bisect_right(uids_sorted, after_uid)
            start = idx
            end = min(len(uids_sorted), start + page_size)
        else:
            end = len(uids_sorted)
            start = max(0, end - page_size)

        if start >= end:
            return PagedSearchResult(refs=[], total=total_matches, has_next=False, has_prev=False)

        page_uids_asc = uids_sorted[start:end]
        page_uids_desc = list(reversed(page_uids_asc))

        refs = [EmailRef(uid=uid, mailbox=mailbox) for uid in page_uids_desc]

        oldest_uid = page_uids_asc[0]
        newest_uid = page_uids_asc[-1]

        has_older = start > 0
        has_newer = end < len(uids_sorted)

        return PagedSearchResult(
            refs=refs,
            next_before_uid=oldest_uid if has_older else None,
            prev_after_uid=newest_uid if has_newer else None,
            newest_uid=newest_uid,
            oldest_uid=oldest_uid,
            total=total_matches,
            has_next=has_older,
            has_prev=has_newer,
        )

    def search(self, *, mailbox: str, query: IMAPQuery, limit: int = 50) -> PagedSearchResult:
        """
        Matches current IMAPClient.search(): refresh cache and return newest-first refs.
        """
        page = self.search_page_cached(
            mailbox=mailbox,
            query=query,
            page_size=limit,
            refresh=True,
        )
        return page.refs

    def _matches_query(self, stored: _StoredMessage, parts: List[str]) -> bool:
        """
        Very small subset of IMAP SEARCH semantics:

        - UNSEEN / SEEN
        - DELETED / UNDELETED
        - DRAFT / UNDRAFT
        - FLAGGED / UNFLAGGED
        - HEADER "List-Unsubscribe" "" (header present)

        Everything else is ignored (accept).
        """
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

        # Simple header presence check:
        # IMAPQuery.header("List-Unsubscribe", "")
        for i, token in enumerate(parts):
            if token == "HEADER" and i + 2 < len(parts):
                name_token = parts[i + 1].strip('"')
                value_token = parts[i + 2].strip('"')
                if name_token.lower() == "list-unsubscribe":
                    has_header = any(k.lower() == "list-unsubscribe" for k in msg.headers.keys())
                    if value_token == "":
                        if not has_header:
                            return False
                    else:
                        header_val = msg.headers.get("List-Unsubscribe", "")
                        if value_token.lower() not in header_val.lower():
                            return False

        return True

    # --- FETCH full message ----------------------------------------------

    def fetch(
        self,
        refs: Sequence[EmailRef],
        *,
        include_attachments: bool = False,
    ) -> List[EmailMessage]:
        self._maybe_fail()
        if not refs:
            return []

        mailbox = self._assert_same_mailbox(refs, "fetch")
        box = self._mailboxes.get(mailbox, {})

        out: List[EmailMessage] = []
        for r in refs:
            stored = box.get(r.uid)
            if not stored:
                continue

            msg = stored.msg
            if include_attachments:
                out.append(msg)
            else:
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

    # --- FETCH overview ---------------------------------------------------

    def fetch_overview(self, refs: Sequence[EmailRef]) -> List[EmailOverview]:
        """
        Mirrors IMAPClient.fetch_overview() surface by returning EmailOverview.
        We synthesize minimal header bytes and call parse_overview() (same helper as real IMAPClient).
        """
        self._maybe_fail()
        if not refs:
            return []

        mailbox = self._assert_same_mailbox(refs, "fetch_overview")
        box = self._mailboxes.get(mailbox, {})

        out: List[EmailOverview] = []
        for r in refs:
            stored = box.get(r.uid)
            if not stored:
                continue

            msg = stored.msg
            flags = set(stored.flags)

            # Minimal headers needed by parse_overview()
            # Keep it conservative; parse_overview reads common fields.
            hdr_lines: List[str] = []
            def _add(name: str, value: Optional[str]) -> None:
                if value is None:
                    return
                if value == "":
                    return
                hdr_lines.append(f"{name}: {value}")

            _add("From", msg.headers.get("From") or msg.from_email)
            _add("To", msg.headers.get("To") or (", ".join(msg.to) if msg.to else ""))
            _add("Subject", msg.headers.get("Subject") or msg.subject)
            _add("Date", msg.headers.get("Date") or (msg.date.isoformat() if msg.date else ""))
            _add("Message-ID", msg.headers.get("Message-ID") or (msg.message_id or ""))

            # Preserve any other stored headers that might matter for tests (best-effort)
            # but avoid duplicates for the main ones.
            used = {h.split(":", 1)[0].lower() for h in hdr_lines}
            for k, v in (msg.headers or {}).items():
                if k.lower() in used:
                    continue
                if v is None:
                    continue
                hdr_lines.append(f"{k}: {v}")

            header_bytes = ("\r\n".join(hdr_lines) + "\r\n\r\n").encode("utf-8", errors="replace")
            out.append(parse_overview(r, flags, header_bytes, internaldate_raw=None))

        return out

    # --- Attachment fetch -------------------------------------------------

    def fetch_attachment(self, ref: EmailRef, attachment_part: str) -> bytes:
        """
        Best-effort attachment retrieval. The real client fetches part bytes via IMAP BODY[].

        Here we look inside stored EmailMessage.attachments for a matching `.part`
        (or `.attachment_part`) and return bytes from common fields (`content`, `data`, `payload`).
        """
        self._maybe_fail()
        box = self._mailboxes.get(ref.mailbox, {})
        stored = box.get(ref.uid)
        if not stored:
            raise IMAPError(f"Message not found for {ref!r}")

        msg = stored.msg
        atts = getattr(msg, "attachments", None) or []
        for att in atts:
            part = getattr(att, "part", None) or getattr(att, "attachment_part", None)
            if part != attachment_part:
                continue

            # common payload field names
            for key in ("content", "data", "payload", "bytes"):
                val = getattr(att, key, None)
                if isinstance(val, (bytes, bytearray)):
                    return bytes(val)

            # if the attachment itself is bytes
            if isinstance(att, (bytes, bytearray)):
                return bytes(att)

            raise IMAPError(
                f"Attachment found for part={attachment_part!r} but no byte payload "
                f"(expected .content/.data/.payload as bytes)"
            )

        raise IMAPError(f"Attachment part not found: uid={ref.uid} part={attachment_part}")

    # --- Mutations --------------------------------------------------------

    def append(
        self,
        mailbox: str,
        msg: PyEmailMessage,
        *,
        flags: Optional[Set[str]] = None,
    ) -> EmailRef:
        """
        Behaves similarly to IMAPClient.append(): parses RFC822 and stores with a new UID.
        """
        self._maybe_fail()
        box = self._ensure_mailbox(mailbox)
        uid = self._alloc_uid()
        ref = EmailRef(uid=uid, mailbox=mailbox)

        raw = msg.as_bytes()
        parsed = parse_rfc822(ref, raw, include_attachments=True)
        box[uid] = _StoredMessage(parsed, set(flags or set()))
        self._invalidate_search_cache(mailbox)
        return ref

    def add_flags(self, refs: Sequence[EmailRef], *, flags: Set[str]) -> None:
        self._maybe_fail()
        if not refs:
            return
        mailbox = self._assert_same_mailbox(refs, "add_flags")
        box = self._mailboxes.get(mailbox, {})
        for r in refs:
            stored = box.get(r.uid)
            if stored:
                stored.flags |= set(flags)
        self._invalidate_search_cache(mailbox)

    def remove_flags(self, refs: Sequence[EmailRef], *, flags: Set[str]) -> None:
        self._maybe_fail()
        if not refs:
            return
        mailbox = self._assert_same_mailbox(refs, "remove_flags")
        box = self._mailboxes.get(mailbox, {})
        for r in refs:
            stored = box.get(r.uid)
            if stored:
                stored.flags -= set(flags)
        self._invalidate_search_cache(mailbox)

    # --- mailbox maintenance ---------------------------------------------

    def expunge(self, mailbox: str = "INBOX") -> None:
        """
        Remove messages flagged as \\Deleted from a mailbox.
        """
        self._maybe_fail()
        box = self._mailboxes.get(mailbox, {})
        to_delete = [uid for uid, s in box.items() if r"\Deleted" in s.flags]
        for uid in to_delete:
            del box[uid]
        self._invalidate_search_cache(mailbox)

    def list_mailboxes(self) -> List[str]:
        self._maybe_fail()
        return sorted(self._mailboxes.keys())

    def mailbox_status(self, mailbox: str = "INBOX") -> Dict[str, int]:
        self._maybe_fail()
        box = self._mailboxes.get(mailbox, {})
        messages = len(box)
        unseen = sum(1 for s in box.values() if r"\Seen" not in s.flags)
        return {"messages": messages, "unseen": unseen}

    # --- copy / move / mailbox ops ---------------------------------------

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
        for r in refs:
            if r.mailbox != src_mailbox:
                raise IMAPError("All EmailRef.mailbox must match src_mailbox for move()")

        src = self._mailboxes.get(src_mailbox, {})
        dst = self._ensure_mailbox(dst_mailbox)

        # move: remove from src, create new UID+ref in dst, update message ref
        for r in refs:
            stored = src.pop(r.uid, None)
            if not stored:
                continue

            new_uid = self._alloc_uid()
            new_ref = EmailRef(uid=new_uid, mailbox=dst_mailbox)
            new_msg = self._clone_message_with_ref(stored.msg, new_ref)
            dst[new_uid] = _StoredMessage(new_msg, set(stored.flags))

        self._invalidate_search_cache(src_mailbox)
        self._invalidate_search_cache(dst_mailbox)

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
        for r in refs:
            if r.mailbox != src_mailbox:
                raise IMAPError("All EmailRef.mailbox must match src_mailbox for copy()")

        src = self._mailboxes.get(src_mailbox, {})
        dst = self._ensure_mailbox(dst_mailbox)

        for r in refs:
            stored = src.get(r.uid)
            if not stored:
                continue

            new_uid = self._alloc_uid()
            new_ref = EmailRef(uid=new_uid, mailbox=dst_mailbox)
            new_msg = self._clone_message_with_ref(stored.msg, new_ref)
            dst[new_uid] = _StoredMessage(new_msg, set(stored.flags))

        self._invalidate_search_cache(dst_mailbox)

    def create_mailbox(self, name: str) -> None:
        self._maybe_fail()
        self._ensure_mailbox(name)
        self._invalidate_search_cache()

    def delete_mailbox(self, name: str) -> None:
        self._maybe_fail()
        self._mailboxes.pop(name, None)
        self._invalidate_search_cache()

    def ping(self) -> None:
        """
        Minimal health check; used by EmailManager.health_check.
        """
        self._maybe_fail()

    def close(self) -> None:
        """
        Real IMAPClient.close() drops network connection; here it's a no-op.
        """
        self._maybe_fail()

    def __enter__(self) -> "FakeIMAPClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()
