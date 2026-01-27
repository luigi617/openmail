from datetime import datetime, timezone
import os
from typing import Dict, List, Optional, Tuple
from pathlib import Path
from urllib.parse import unquote

from dotenv import load_dotenv
from fastapi import FastAPI, Request, HTTPException, Query, UploadFile
from fastapi import Form, File
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from email_management import EmailManager
from email_management.types import EmailRef
from email_management.models import EmailMessage, EmailOverview
from email_management.imap import PagedSearchResult

from email_service import parse_accounts
from utils import uploadfiles_to_attachments, build_extra_headers, encode_cursor, decode_cursor

BASE = Path(__file__).parent

app = FastAPI()
templates = Jinja2Templates(directory=str(BASE / "templates"))
app.mount("/static", StaticFiles(directory=str(BASE / "static")), name="static")

load_dotenv(override=True)

ACCOUNTS: Dict[str, EmailManager] = parse_accounts(os.getenv("ACCOUNTS", ""))

@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/api/emails/overview")
def get_email_overview(
    mailbox: str = "INBOX",
    limit: int = 50,
    cursor: Optional[str] = Query(
        default=None,
        description=(
            "Opaque pagination cursor. "
            "Use the value from meta.next_cursor or meta.prev_cursor "
            "from a previous response."
        ),
    ),
    # Optional; can be omitted to use all accounts.
    accounts: Optional[List[str]] = Query(
        default=None,
        description="Optional list of account IDs. If omitted, all accounts are used.",
    ),
) -> dict:
    """
    Multi-account email overview with per-account pagination.

    Cursor format (opaque to clients, but documented here):

        {
          "direction": "next" | "prev",
          "mailbox": "<mailbox>",
          "limit": <int>,
          "accounts": {
            "<account_id>": {
              "next_before_uid": <int or null>,  # older-page anchor
              "prev_after_uid": <int or null>,   # newer-page anchor
            },
            ...
          }
        }
    """

    if limit < 1:
        raise HTTPException(status_code=400, detail="limit must be >= 1")

    # ---------- Decode / init cursor state ----------
    if cursor:
        try:
            cursor_state = decode_cursor(cursor)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid cursor")

        try:
            direction = cursor_state["direction"]  # "next" or "prev"
            mailbox = cursor_state["mailbox"]
            limit = cursor_state["limit"]
            account_state: Dict[str, Dict[str, Optional[int]]] = cursor_state["accounts"]
        except KeyError:
            raise HTTPException(status_code=400, detail="Malformed cursor")

        account_ids = list(account_state.keys())
    else:
        direction = "next"
        if accounts is None:
            account_ids = list(ACCOUNTS.keys())
        else:
            account_ids = accounts

        # Initial state: no anchors yet for any account.
        account_state = {
            acc_id: {"next_before_uid": None, "prev_after_uid": None}
            for acc_id in account_ids
        }

    if not account_ids:
        raise HTTPException(status_code=400, detail="No accounts specified or available")

    # ---------- Resolve managers ----------
    managers: Dict[str, "EmailManager"] = {}
    for acc_id in account_ids:
        manager = ACCOUNTS.get(acc_id)
        if manager is None:
            raise HTTPException(status_code=404, detail=f"Unknown account: {acc_id}")
        managers[acc_id] = manager

    combined_entries: List[Tuple[str, "EmailOverview"]] = []
    total_count = 0

    per_account_meta: Dict[str, "PagedSearchResult"] = {}
    per_account_overviews: Dict[str, List["EmailOverview"]] = {}

    is_first_page = cursor is None

    # ---------- Fetch page per account ----------
    for acc_id, manager in managers.items():
        state = account_state.get(acc_id, {"next_before_uid": None, "prev_after_uid": None})
        next_before_uid = state.get("next_before_uid")
        prev_after_uid = state.get("prev_after_uid")

        if direction == "next":
            before_uid = next_before_uid
            after_uid = None
        else:  # direction == "prev"
            before_uid = None
            after_uid = prev_after_uid

        page_meta, overview_list = manager.fetch_overview(
            mailbox=mailbox,
            n=limit,  # page_size per account
            before_uid=before_uid,
            after_uid=after_uid,
            refresh=is_first_page,
        )

        per_account_meta[acc_id] = page_meta
        per_account_overviews[acc_id] = overview_list
        total_count += page_meta.total or len(overview_list)

        for ov in overview_list:
            combined_entries.append((acc_id, ov))

    # ---------- Global merge & slice ----------
    # Always present the page newest-first in the response.
    combined_entries.sort(
        key=lambda pair: pair[1].date or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )

    page_entries = combined_entries[:limit]
    result_count = len(page_entries)

    # Track which overviews from each account are in THIS page
    contributed: Dict[str, List["EmailOverview"]] = {}
    for acc_id, ov in page_entries:
        contributed.setdefault(acc_id, []).append(ov)

    # ---------- Build response payload ----------
    data = []
    for acc_id, ov in page_entries:
        d = ov.to_dict()

        # Put account on the ref object if it exists
        ref = d.get("ref")
        if isinstance(ref, dict):
            ref.setdefault("account", acc_id)
        else:
            d.setdefault("account", acc_id)

        data.append(d)

    # ---------- Build per-account anchors for NEXT calls ----------
    # For each account, we simply take its page_meta anchors:
    #   - next_before_uid: cursor for going older (direction="next")
    #   - prev_after_uid: cursor for going newer (direction="prev")
    new_state_accounts: Dict[str, Dict[str, Optional[int]]] = {}

    for acc_id in account_ids:
        page_meta = per_account_meta[acc_id]

        new_state_accounts[acc_id] = {
            "next_before_uid": page_meta.next_before_uid,
            "prev_after_uid": page_meta.prev_after_uid,
        }

    # Aggregate has_next / has_prev across accounts
    any_has_next = any(meta.has_next for meta in per_account_meta.values())
    any_has_prev = any(meta.has_prev for meta in per_account_meta.values())

    next_cursor = None
    prev_cursor = None

    if result_count > 0 and any_has_next:
        next_cursor_state = {
            "direction": "next",
            "mailbox": mailbox,
            "limit": limit,
            "accounts": new_state_accounts,
        }
        next_cursor = encode_cursor(next_cursor_state)

    if result_count > 0 and any_has_prev:
        prev_cursor_state = {
            "direction": "prev",
            "mailbox": mailbox,
            "limit": limit,
            "accounts": new_state_accounts,
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

@app.get("/api/emails/mailbox")
def get_email_mailbox() -> Dict[str, List[str]]:
    """
    Return available mailboxes per account.
    """
    res: Dict[str, List[str]] = {}
    for acc_name, manager in ACCOUNTS.items():
        mailbox_list = manager.list_mailboxes()
        res[acc_name] = mailbox_list
    return res

@app.get("/api/accounts/{account:path}/mailboxes/{mailbox:path}/emails/{email_id}")
def get_email(account: str, mailbox: str, email_id: int) -> dict:
    """
    Fetch a single email by UID for a given account and mailbox.
    """
    account = unquote(account)
    mailbox = unquote(mailbox)
    manager = ACCOUNTS.get(account)
    if manager is None:
        raise HTTPException(status_code=404, detail="Account not found")

    message: EmailMessage = manager.fetch_message_by_ref(
        EmailRef(mailbox=mailbox, uid=email_id),
        include_attachments=True,
    )
    return message.to_dict()

@app.post("/api/accounts/{account:path}/mailboxes/{mailbox:path}/emails/{email_id}/archive")
def archive_email(account: str, mailbox: str, email_id: int) -> dict:
    """
    Archive a single email by moving it out of the current mailbox.

    Here we define "archive" as moving the message to an "Archive" mailbox.
    If that mailbox does not exist, we create it.
    """
    account = unquote(account)
    mailbox = unquote(mailbox)
    manager = ACCOUNTS.get(account)
    if manager is None:
        raise HTTPException(status_code=404, detail="Account not found")

    ref = EmailRef(mailbox=mailbox, uid=email_id)

    # Ensure Archive mailbox exists
    archive_mailbox = "Archive"
    mailboxes = manager.list_mailboxes()
    if archive_mailbox not in mailboxes:
        manager.create_mailbox(archive_mailbox)

    manager.move([ref], src_mailbox=mailbox, dst_mailbox=archive_mailbox)

    return {"status": "ok", "action": "archive", "account": account, "mailbox": mailbox, "email_id": email_id}

@app.delete("/api/accounts/{account:path}/mailboxes/{mailbox:path}/emails/{email_id}")
def delete_email(account: str, mailbox: str, email_id: int) -> dict:
    """
    Delete a single email (mark as \\Deleted and expunge from the mailbox).
    """
    account = unquote(account)
    mailbox = unquote(mailbox)
    manager = ACCOUNTS.get(account)
    if manager is None:
        raise HTTPException(status_code=404, detail="Account not found")

    ref = EmailRef(mailbox=mailbox, uid=email_id)

    manager.delete([ref])
    manager.expunge(mailbox=mailbox)

    return {"status": "ok", "action": "delete", "account": account, "mailbox": mailbox, "email_id": email_id}

@app.post("/api/accounts/{account:path}/mailboxes/{mailbox:path}/emails/{email_id}/reply")
async def reply_email(
    account: str,
    mailbox: str,
    email_id: int,
    body: str = Form(...),
    body_html: Optional[str] = Form(None),
    from_addr: Optional[str] = Form(None),
    quote_original: bool = Form(True),
    subject: Optional[str] = Form(None),
    to: Optional[List[str]] = Form(None),
    cc: Optional[List[str]] = Form(None),
    bcc: Optional[List[str]] = Form(None),
    reply_to: Optional[List[str]] = Form(None),
    priority: Optional[str] = Form(None),
    attachments: List[UploadFile] = File([]),
) -> dict:
    account = unquote(account)
    mailbox = unquote(mailbox)

    manager = ACCOUNTS.get(account)
    if manager is None:
        raise HTTPException(status_code=404, detail="Account not found")

    original: EmailMessage = manager.fetch_message_by_ref(
        EmailRef(mailbox=mailbox, uid=email_id),
        include_attachments=False,
    )

    attachment_models = await uploadfiles_to_attachments(attachments)
    extra_headers = build_extra_headers(reply_to=reply_to, priority=priority)

    send_result = manager.reply(
        original=original,
        body=body,
        body_html=body_html,
        from_addr=from_addr,
        quote_original=quote_original,
        to=to,
        cc=cc,
        bcc=bcc,
        subject=subject,
        attachments=attachment_models or None,
        extra_headers=extra_headers or None,
    )

    return {
        "status": "ok",
        "action": "reply",
        "account": account,
        "mailbox": mailbox,
        "email_id": email_id,
        "result": getattr(send_result, "to_dict", lambda: str(send_result))(),
    }


@app.post("/api/accounts/{account:path}/mailboxes/{mailbox:path}/emails/{email_id}/reply-all")
async def reply_all_email(
    account: str,
    mailbox: str,
    email_id: int,
    body: str = Form(...),
    body_html: Optional[str] = Form(None),
    from_addr: Optional[str] = Form(None),
    quote_original: bool = Form(True),
    subject: Optional[str] = Form(None),
    to: Optional[List[str]] = Form(None),
    cc: Optional[List[str]] = Form(None),
    bcc: Optional[List[str]] = Form(None),
    reply_to: Optional[List[str]] = Form(None),
    priority: Optional[str] = Form(None),
    attachments: List[UploadFile] = File([]),
) -> dict:
    account = unquote(account)
    mailbox = unquote(mailbox)

    manager = ACCOUNTS.get(account)
    if manager is None:
        raise HTTPException(status_code=404, detail="Account not found")

    original: EmailMessage = manager.fetch_message_by_ref(
        EmailRef(mailbox=mailbox, uid=email_id),
        include_attachments=False,
    )

    attachment_models = await uploadfiles_to_attachments(attachments)
    extra_headers = build_extra_headers(reply_to=reply_to, priority=priority)

    send_result = manager.reply_all(
        original=original,
        body=body,
        body_html=body_html,
        from_addr=from_addr,
        quote_original=quote_original,
        to=to,
        cc=cc,
        bcc=bcc,
        subject=subject,
        attachments=attachment_models or None,
        extra_headers=extra_headers or None,
    )

    return {
        "status": "ok",
        "action": "reply_all",
        "account": account,
        "mailbox": mailbox,
        "email_id": email_id,
        "result": getattr(send_result, "to_dict", lambda: str(send_result))(),
    }

@app.post("/api/accounts/{account:path}/mailboxes/{mailbox:path}/emails/{email_id}/forward")
async def forward_email(
    account: str,
    mailbox: str,
    email_id: int,
    to: List[str] = Form(...),
    body: Optional[str] = Form(None),
    body_html: Optional[str] = Form(None),
    from_addr: Optional[str] = Form(None),
    include_original: bool = Form(True),
    include_attachments: bool = Form(True),
    cc: Optional[List[str]] = Form(None),
    bcc: Optional[List[str]] = Form(None),
    subject: Optional[str] = Form(None),
    reply_to: Optional[List[str]] = Form(None),
    priority: Optional[str] = Form(None),
    attachments: List[UploadFile] = File([]),
) -> dict:
    account = unquote(account)
    mailbox = unquote(mailbox)

    manager = ACCOUNTS.get(account)
    if manager is None:
        raise HTTPException(status_code=404, detail="Account not found")

    original: EmailMessage = manager.fetch_message_by_ref(
        EmailRef(mailbox=mailbox, uid=email_id),
        include_attachments=True,
    )

    attachment_models = await uploadfiles_to_attachments(attachments)
    extra_headers = build_extra_headers(reply_to=reply_to, priority=priority)

    send_result = manager.forward(
        original=original,
        to=to,
        body=body,
        body_html=body_html,
        from_addr=from_addr,
        include_original=include_original,
        include_attachments=include_attachments,
        cc=cc,
        bcc=bcc,
        subject=subject,
        attachments=attachment_models or None,
        extra_headers=extra_headers or None,
    )

    return {
        "status": "ok",
        "action": "forward",
        "account": account,
        "mailbox": mailbox,
        "email_id": email_id,
        "result": getattr(send_result, "to_dict", lambda: str(send_result))(),
    }

@app.post("/api/accounts/{account:path}/send")
async def send_email(
    account: str,
    subject: str = Form(...),
    to: List[str] = Form(...),
    from_addr: Optional[str] = Form(None),
    cc: Optional[List[str]] = Form(None),
    bcc: Optional[List[str]] = Form(None),
    text: Optional[str] = Form(None),
    html: Optional[str] = Form(None),
    reply_to: Optional[List[str]] = Form(None),
    priority: Optional[str] = Form(None),
    attachments: List[UploadFile] = File([]),
) -> dict:
    account = unquote(account)

    manager = ACCOUNTS.get(account)
    if manager is None:
        raise HTTPException(status_code=404, detail="Account not found")

    attachment_models = await uploadfiles_to_attachments(attachments)
    extra_headers = build_extra_headers(reply_to=reply_to, priority=priority)

    send_result = manager.compose_and_send(
        subject=subject,
        to=to,
        from_addr=from_addr or account,
        cc=cc or [],
        bcc=bcc or [],
        text=text,
        html=html,
        attachments=attachment_models or None,
        extra_headers=extra_headers or None,
    )

    return {
        "status": "ok",
        "action": "send",
        "account": account,
        "result": getattr(send_result, "to_dict", lambda: str(send_result))(),
    }
