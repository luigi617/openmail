from __future__ import annotations

import copy
from dataclasses import dataclass
from datetime import datetime, timezone
import time
from typing import Dict, List, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

from email_management import EmailManager, EmailAssistant, EmailQuery
from email_management.imap import IMAPQuery
from email_management.models import EmailOverview
from utils import encode_cursor, decode_cursor
from ttl_cache import TTLCache


# First-page refresh behavior is governed by this TTL:
# - cache hit: return cached response (no refresh)
# - cache miss (incl. TTL expiry): fetch, and if it's first page => refresh=True
_OVERVIEW_RESPONSE_CACHE = TTLCache(ttl_seconds=15, maxsize=512)


@dataclass
class _CachedDerivedQuery:
    created_at: float
    query_snapshot: IMAPQuery
    debug_repr: str


# Replaces _DerivedIMAPQueryCache with TTLCache directly
_DERIVED_QUERY_CACHE = TTLCache(ttl_seconds=3600, maxsize=256)


def _apply_cached_query(base_q: EmailQuery, cached: _CachedDerivedQuery) -> None:
    base_q.query = copy.deepcopy(cached.query_snapshot)


def _normalize_search(s: Optional[str]) -> Optional[str]:
    if not s:
        return None
    ss = " ".join(s.strip().split())
    return ss if ss else None


def _normalize_ai_cache_key(s: str) -> str:
    # Keep consistent with prior behavior: normalize whitespace + lowercase
    return " ".join(s.strip().split()).lower()


def _cache_key(
    *,
    mailbox: str,
    limit: int,
    cursor: Optional[str],
    account_ids: List[str],
    search_query: Optional[str],
    search_mode: str,
) -> str:
    acc_key = ",".join(account_ids)
    sq = search_query or ""
    return f"mb={mailbox}|lim={limit}|cursor={cursor or ''}|acc={acc_key}|mode={search_mode}|q={sq}"


def build_email_overview(
    *,
    mailbox: str = "INBOX",
    limit: int = 50,
    search_query: Optional[str] = None,
    search_mode: str = "general",  # "general" | "ai"
    cursor: Optional[str] = None,
    accounts: Optional[List[str]] = None,
    ACCOUNTS: Dict[str, EmailManager],
) -> dict:

    if limit < 1:
        raise ValueError("limit must be >= 1")

    if cursor:
        cursor_state = decode_cursor(cursor)
        mailbox = cursor_state["mailbox"]
        account_state: Dict[str, Dict[str, Optional[int]]] = cursor_state["accounts"]
        account_ids = list(account_state.keys())
        search_query = cursor_state.get("search_query")
        search_mode = cursor_state.get("search_mode", search_mode)
    else:
        if accounts is None:
            account_ids = list(ACCOUNTS.keys())
        else:
            account_ids = accounts

        account_state = {acc_id: {"next_before_uid": None} for acc_id in account_ids}

    if not account_ids:
        raise ValueError("No accounts specified or available")

    normalized_search = _normalize_search(search_query)

    key = _cache_key(
        mailbox=mailbox,
        limit=limit,
        cursor=cursor,
        account_ids=account_ids,
        search_query=normalized_search,
        search_mode=search_mode,
    )
    cached_resp = _OVERVIEW_RESPONSE_CACHE.get(key)
    if cached_resp is not None:
        return cached_resp

    managers: Dict[str, EmailManager] = {}
    for acc_id in account_ids:
        manager = ACCOUNTS.get(acc_id)
        if manager is None:
            raise KeyError(f"Unknown account: {acc_id}")
        managers[acc_id] = manager

    is_first_page = cursor is None

    cached_ai: Optional[_CachedDerivedQuery] = None

    if normalized_search and search_mode == "ai":
        ai_key = _normalize_ai_cache_key(normalized_search)
        cached_ai = _DERIVED_QUERY_CACHE.get(ai_key)

        if cached_ai is None:
            email_assistant = EmailAssistant()
            easy_imap_query, _ = email_assistant.search_emails(
                normalized_search,
                provider="groq",
                model_name="llama-3.1-8b-instant",
            )
            snap = copy.deepcopy(easy_imap_query.query)
            try:
                debug_repr = str(easy_imap_query.query)
            except Exception:
                debug_repr = ""

            cached_ai = _CachedDerivedQuery(
                created_at=time.time(),
                query_snapshot=snap,
                debug_repr=debug_repr,
            )
            _DERIVED_QUERY_CACHE.set(ai_key, cached_ai)

    def _fetch_one_account(acc_id: str) -> Tuple[str, int, List[EmailOverview]]:
        """
        Returns: (acc_id, total_count, list_of_overviews)
        """
        manager = managers[acc_id]
        state = account_state.get(acc_id, {"next_before_uid": None})
        before_uid = state.get("next_before_uid")

        q = manager.imap_query(mailbox).limit(limit)

        # Apply search
        if normalized_search:
            if search_mode == "ai" and cached_ai is not None:
                _apply_cached_query(q, cached_ai)
            else:
                q.query = q.query.or_(
                    IMAPQuery().subject(normalized_search),
                    IMAPQuery().text(normalized_search),
                    IMAPQuery().to(normalized_search),
                    IMAPQuery().from_(normalized_search),
                )

        # Refresh only on first page AND only on cache miss (we're here)
        refresh_flag = is_first_page

        page_meta, overview_list = q.fetch_overview(
            before_uid=before_uid,
            after_uid=None,
            refresh=refresh_flag,
        )
        return acc_id, int(page_meta.total), overview_list

    combined_entries: List[Tuple[str, EmailOverview]] = []
    total_count = 0

    # ---------- Parallel fetch across accounts ----------
    max_workers = min(8, max(1, len(account_ids)))
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = [ex.submit(_fetch_one_account, acc_id) for acc_id in account_ids]
        for fut in as_completed(futures):
            acc_id, acc_total, overview_list = fut.result()
            total_count += acc_total
            for ov in overview_list:
                combined_entries.append((acc_id, ov))

    def _unique_sort_key(pair: Tuple[str, EmailOverview]) -> Tuple[datetime, str, int]:
        acc_id, ov = pair
        dt = ov.received_at or datetime.min.replace(tzinfo=timezone.utc)
        uid = ov.ref.uid or -1
        return (dt, acc_id, uid)

    combined_entries.sort(key=_unique_sort_key, reverse=True)
    page_entries = combined_entries[:limit]

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

    # ---------- Build next anchors per account ----------
    new_state_accounts: Dict[str, Dict[str, Optional[int]]] = {}

    for acc_id in account_ids:
        prev_state = account_state.get(acc_id, {"next_before_uid": None})
        state = {"next_before_uid": prev_state.get("next_before_uid")}

        contrib_list = contributed.get(acc_id, [])
        if contrib_list:
            uids = [ov.ref.uid for ov in contrib_list]
            uids = [u for u in uids if u is not None]
            if uids:
                oldest_uid = min(uids)
                state["next_before_uid"] = max(oldest_uid, 1)

        new_state_accounts[acc_id] = state

    any_has_next = result_count > 0 and any(
        s.get("next_before_uid") is not None for s in new_state_accounts.values()
    )

    next_cursor = None
    if result_count > 0 and any_has_next:
        next_cursor_state = {
            "mailbox": mailbox,
            "limit": limit,
            "accounts": new_state_accounts,
            "search_query": normalized_search,
            "search_mode": search_mode,
        }
        next_cursor = encode_cursor(next_cursor_state)

    resp = {
        "data": data,
        "meta": {
            "next_cursor": next_cursor,
            "result_count": result_count,
            "total_count": total_count,
        },
    }

    _OVERVIEW_RESPONSE_CACHE.set(key, resp)
    return resp
