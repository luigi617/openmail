from __future__ import annotations

import copy
from dataclasses import dataclass
from datetime import datetime, timezone
import time
from typing import Dict, List, Optional, Tuple, Callable, Any

from email_management import EmailManager, EmailAssistant, EmailQuery
from email_management.imap import IMAPQuery
from email_management.models import EmailOverview
from utils import encode_cursor, decode_cursor

@dataclass
class _CachedDerivedQuery:
    created_at: float
    query_snapshot: IMAPQuery
    debug_repr: str


class _DerivedIMAPQueryCache:
    """
    In-memory cache:
      (mailbox, normalized_user_query) -> snapshot of EmailQuery.query
    """
    def __init__(self, *, maxsize: int = 256, ttl_seconds: int = 3600) -> None:
        self.maxsize = maxsize
        self.ttl_seconds = ttl_seconds
        self._store: Dict[Tuple[str, str], _CachedDerivedQuery] = {}
        self._lru: List[Tuple[str, str]] = []  # oldest -> newest

    def _normalize(self, s: str) -> str:
        return " ".join(s.strip().split()).lower()

    def get(self, mailbox: str, user_query: str) -> Optional[_CachedDerivedQuery]:
        key = (mailbox, self._normalize(user_query))
        item = self._store.get(key)
        if not item:
            return None
        print(key)
        print(item.debug_repr)

        # TTL check
        if (time.time() - item.created_at) > self.ttl_seconds:
            self._store.pop(key, None)
            try:
                self._lru.remove(key)
            except ValueError:
                pass
            return None

        # LRU bump
        try:
            self._lru.remove(key)
        except ValueError:
            pass
        self._lru.append(key)
        return item

    def set(self, mailbox: str, user_query: str, item: _CachedDerivedQuery) -> None:
        key = (mailbox, self._normalize(user_query))

        if key in self._store:
            self._store[key] = item
            try:
                self._lru.remove(key)
            except ValueError:
                pass
            self._lru.append(key)
            return

        # Evict if needed
        while len(self._lru) >= self.maxsize:
            oldest = self._lru.pop(0)
            self._store.pop(oldest, None)

        self._store[key] = item
        self._lru.append(key)


_DERIVED_QUERY_CACHE = _DerivedIMAPQueryCache(maxsize=256, ttl_seconds=3600)


def _apply_cached_query(base_q: EmailQuery, cached: _CachedDerivedQuery) -> None:
    """
    Apply the cached IMAP criteria onto a new EmailQuery instance.
    Assumes EmailQuery has a `.query` object we can replace.
    """
    # Deepcopy to avoid cross-request mutation
    base_q.query = copy.deepcopy(cached.query_snapshot)


def build_email_overview(
    *,
    mailbox: str = "INBOX",
    limit: int = 50,
    search_query: Optional[str] = None,
    cursor: Optional[str] = None,
    accounts: Optional[List[str]] = None,
    ACCOUNTS: Dict[str, EmailManager],
) -> dict:
    
    if limit < 1:
        raise ValueError("limit must be >= 1")

    if cursor:
        cursor_state = decode_cursor(cursor)
        direction = cursor_state["direction"]
        mailbox = cursor_state["mailbox"]
        account_state: Dict[str, Dict[str, Optional[int]]] = cursor_state["accounts"]
        account_ids = list(account_state.keys())
        search_query = cursor_state.get("search_query")
    else:
        direction = "next"
        if accounts is None:
            account_ids = list(ACCOUNTS.keys())
        else:
            account_ids = accounts

        account_state = {
            acc_id: {"next_before_uid": None, "prev_after_uid": None}
            for acc_id in account_ids
        }

    if not account_ids:
        raise ValueError("No accounts specified or available")

    # ---------- Resolve managers ----------
    managers: Dict[str, EmailManager] = {}
    for acc_id in account_ids:
        manager = ACCOUNTS.get(acc_id)
        if manager is None:
            raise KeyError(f"Unknown account: {acc_id}")
        managers[acc_id] = manager

    cached = None
    normalized_search = None
    if search_query and search_query.strip():
        normalized_search = " ".join(search_query.strip().split())
        cached = _DERIVED_QUERY_CACHE.get(mailbox, normalized_search)
        if cached is None:
            email_assistant = EmailAssistant()
            easy_imap_query, _ = email_assistant.search_emails(
                normalized_search,
                provider="groq",
                model_name="llama-3.1-8b-instant",
                mailbox=mailbox,
            )

            snap = copy.deepcopy(easy_imap_query.query)
            debug_repr = ""
            try:
                debug_repr = str(easy_imap_query.query)
            except Exception:
                debug_repr = ""

            cached = _CachedDerivedQuery(
                created_at=time.time(),
                query_snapshot=snap,
                debug_repr=debug_repr,
            )
            _DERIVED_QUERY_CACHE.set(mailbox, normalized_search, cached)

    combined_entries: List[Tuple[str, EmailOverview]] = []
    total_count = 0
    is_first_page = cursor is None

    # ---------- Fetch page per account ----------
    for acc_id, manager in managers.items():
        state = account_state.get(acc_id, {"next_before_uid": None, "prev_after_uid": None})
        next_before_uid = state.get("next_before_uid")
        prev_after_uid = state.get("prev_after_uid")

        if direction == "next":
            before_uid = next_before_uid
            after_uid = None
        else:  # "prev"
            before_uid = None
            after_uid = prev_after_uid

        q = manager.imap_query(mailbox).limit(limit)
        if cached is not None:
            _apply_cached_query(q, cached)

        page_meta, overview_list = q.fetch_overview(
            before_uid=before_uid,
            after_uid=after_uid,
            refresh=is_first_page,
        )
        
        total_count += page_meta.total
        for ov in overview_list:
            combined_entries.append((acc_id, ov))

    # ---------- Merge + slice ----------
    if direction == "next":
        combined_entries.sort(
            key=lambda pair: pair[1].date or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True,
        )
        page_entries = combined_entries[:limit]
    else:
        combined_entries.sort(
            key=lambda pair: pair[1].date or datetime.min.replace(tzinfo=timezone.utc),
            reverse=False,
        )
        page_entries = combined_entries[:limit]
        page_entries.reverse()

    result_count = len(page_entries)

    contributed: Dict[str, List[EmailOverview]] = {}
    for acc_id, ov in page_entries:
        contributed.setdefault(acc_id, []).append(ov)

    data: List[dict] = []
    for acc_id, ov in page_entries:
        d = ov.to_dict()
        ref: dict = d["ref"]
        ref.setdefault("account", acc_id)
        data.append(d)

    # ---------- Build next/prev anchors per account ----------
    new_state_accounts: Dict[str, Dict[str, Optional[int]]] = {}

    for acc_id in account_ids:
        prev_state = account_state.get(acc_id, {"next_before_uid": None, "prev_after_uid": None})
        state = {
            "next_before_uid": prev_state.get("next_before_uid"),
            "prev_after_uid": prev_state.get("prev_after_uid"),
        }

        contrib_list = contributed.get(acc_id, [])
        if contrib_list:
            uids = [ov.ref.uid for ov in contrib_list]
            uids = [u for u in uids if u is not None]
            if uids:
                oldest_uid = min(uids)
                newest_uid = max(uids)
                state["next_before_uid"] = max(oldest_uid - 1, 1)
                state["prev_after_uid"] = newest_uid + 1
        else:
            # Keep cursor progression consistent even if this account contributed nothing
            if direction == "next":
                state["prev_after_uid"] = state["next_before_uid"]
            else:
                state["next_before_uid"] = state["prev_after_uid"]

        new_state_accounts[acc_id] = state

    any_has_next = result_count > 0 and any(
        s.get("next_before_uid") is not None for s in new_state_accounts.values()
    )
    any_has_prev = result_count > 0 and any(
        s.get("prev_after_uid") is not None for s in new_state_accounts.values()
    )

    next_cursor = None
    prev_cursor = None

    if result_count > 0 and any_has_next:
        next_cursor_state = {
            "direction": "next",
            "mailbox": mailbox,
            "limit": limit,
            "accounts": new_state_accounts,
            "search_query": normalized_search,
        }
        next_cursor = encode_cursor(next_cursor_state)

    if result_count > 0 and any_has_prev:
        prev_cursor_state = {
            "direction": "prev",
            "mailbox": mailbox,
            "limit": limit,
            "accounts": new_state_accounts,
            "search_query": normalized_search,
        }
        prev_cursor = encode_cursor(prev_cursor_state)

    return {
        "data": data,
        "meta": {
            "next_cursor": next_cursor,
            "prev_cursor": prev_cursor,
            "result_count": result_count,
            "total_count": total_count,
        },
    }
