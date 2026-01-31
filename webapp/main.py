from datetime import datetime, timezone
import io
import mimetypes
import os
from typing import Dict, List, Optional, Tuple
from pathlib import Path
from urllib.parse import unquote

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Response, UploadFile
from fastapi import Form, File
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware


from email_management import EmailManager
from email_management.types import EmailRef
from email_management.models import EmailMessage, EmailOverview
from email_management.imap import PagedSearchResult

from email_service import parse_accounts
from utils import uploadfiles_to_attachments, build_extra_headers, encode_cursor, decode_cursor, safe_filename

BASE = Path(__file__).parent

app = FastAPI()
app.mount("/static", StaticFiles(directory=str(BASE / "static")), name="static")

load_dotenv(override=True)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

ACCOUNTS: Dict[str, EmailManager] = parse_accounts(os.getenv("ACCOUNTS", ""))


@app.get("/api/emails/overview")
def get_email_overview(
    mailbox: str = "INBOX",
    limit: int = 50,
    cursor: Optional[str] = Query(
        default=None,
        description="Opaque pagination cursor.",
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

    if cursor:
        try:
            cursor_state = decode_cursor(cursor)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid cursor")

        try:
            direction = cursor_state["direction"]
            mailbox = cursor_state["mailbox"]
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
            n=limit,
            before_uid=before_uid,
            after_uid=after_uid,
            refresh=is_first_page,
        )

        total_count += page_meta.total

        for ov in overview_list:
            combined_entries.append((acc_id, ov))

    page_entries: list[Tuple[str, EmailOverview]] = []
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

    contributed: Dict[str, List["EmailOverview"]] = {}
    for acc_id, ov in page_entries:
        contributed.setdefault(acc_id, []).append(ov)

    data = []
    for acc_id, ov in page_entries:
        d = ov.to_dict()
        ref: dict = d["ref"]
        ref.setdefault("account", acc_id)
        data.append(d)

    
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
            if direction == "next":
                state["prev_after_uid"] = state["next_before_uid"]
            else:
                state["next_before_uid"] = state["prev_after_uid"]

        new_state_accounts[acc_id] = state

    # Aggregate has_next / has_prev across accounts based on anchors
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

    data = message.to_dict()
    data["ref"].setdefault("account", account)
    return data

@app.get("/api/accounts/{account:path}/mailboxes/{mailbox:path}/emails/{email_id}/attachment")
def download_email_attachment(
    account: str,
    mailbox: str,
    email_id: int,
    part: str = Query(..., description='IMAP part section for attachment, e.g. "2.1"'),
    filename: str | None = Query(
        None, description="Filename to use when downloading"
    ),
    content_type: str | None = Query(
        None, description="MIME type, e.g. application/pdf"
    ),
) -> Response:
    """
    Download a single attachment by EmailRef + IMAP part.
    """
    account = unquote(account)
    mailbox = unquote(mailbox)

    manager = ACCOUNTS.get(account)
    if manager is None:
        raise HTTPException(status_code=404, detail="Account not found")

    part = (part or "").strip()
    if not part:
        raise HTTPException(status_code=400, detail="part is required")

    ref = EmailRef(mailbox=mailbox, uid=email_id)

    try:
        attachment_bytes = manager.fetch_attachment_by_ref_and_meta(ref, part)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch attachment: {e}")

    filename = safe_filename(filename, fallback=f"email-{email_id}-part-{part}.bin")

    resolved_content_type = (
        content_type
        or mimetypes.guess_type(filename)[0]
        or "application/octet-stream"
    )

    headers = {
        "Content-Disposition": f'attachment; filename="{filename}"'
    }

    return StreamingResponse(
        io.BytesIO(attachment_bytes),
        media_type=resolved_content_type,
        headers=headers,
    )



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

@app.post("/api/accounts/{account:path}/mailboxes/{mailbox:path}/emails/{email_id}/move")
def move_email(
    account: str,
    mailbox: str,
    email_id: int,
    destination_mailbox: str = Form(..., description="Target mailbox to move the message into"),
) -> dict:
    """
    Move a single email to another mailbox.
    """
    account = unquote(account)
    mailbox = unquote(mailbox)

    manager = ACCOUNTS.get(account)
    if manager is None:
        raise HTTPException(status_code=404, detail="Account not found")

    ref = EmailRef(mailbox=mailbox, uid=email_id)

    mailboxes = manager.list_mailboxes()
    if destination_mailbox not in mailboxes:
        manager.create_mailbox(destination_mailbox)

    manager.move([ref], src_mailbox=mailbox, dst_mailbox=destination_mailbox)

    return {
        "status": "ok",
        "action": "move",
        "account": account,
        "src_mailbox": mailbox,
        "dst_mailbox": destination_mailbox,
        "email_id": email_id,
    }

@app.post("/api/accounts/{account:path}/draft")
async def save_draft(
    account: str,
    subject: Optional[str] = Form(None),
    to: Optional[List[str]] = Form(None),
    from_addr: Optional[str] = Form(None),
    cc: Optional[List[str]] = Form(None),
    bcc: Optional[List[str]] = Form(None),
    text: Optional[str] = Form(None),
    html: Optional[str] = Form(None),
    reply_to: Optional[List[str]] = Form(None),
    priority: Optional[str] = Form(None),
    drafts_mailbox: str = Form("Drafts", description="Mailbox where the draft will be stored"),
    attachments: List[UploadFile] = File([]),
) -> dict:
    """
    Save a draft email instead of sending it.
    """
    account = unquote(account)

    manager = ACCOUNTS.get(account)
    if manager is None:
        raise HTTPException(status_code=404, detail="Account not found")

    attachment_models = await uploadfiles_to_attachments(attachments)
    extra_headers = build_extra_headers(reply_to=reply_to, priority=priority)

    save_result = manager.save_draft(
        subject=subject,
        to=to or [],
        from_addr=from_addr or account,
        cc=cc or [],
        bcc=bcc or [],
        text=text,
        html=html,
        attachments=attachment_models or None,
        extra_headers=extra_headers or None,
        mailbox=drafts_mailbox,
    )

    return {
        "status": "ok",
        "action": "save_draft",
        "account": account,
        "mailbox": drafts_mailbox,
        "result": save_result.to_dict(),
    }

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
        "result": send_result.to_dict(),
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
        "result": send_result.to_dict(),
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
        "result": send_result.to_dict(),
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
        "result": send_result.to_dict(),
    }
