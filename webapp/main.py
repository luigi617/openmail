import io
import mimetypes
import os
from typing import Dict, List, Optional, Tuple
from pathlib import Path
from urllib.parse import unquote
from starlette.middleware.gzip import GZipMiddleware

from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, HTTPException, Query, Response, UploadFile
from fastapi import Form, File
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles


from email_management import EmailManager
from email_management.types import EmailRef
from email_management.models import EmailMessage

from email_service import parse_accounts
from utils import uploadfiles_to_attachments, build_extra_headers, safe_filename
from email_overview import build_email_overview
from ttl_cache import TTLCache


BASE = Path(__file__).parent

app = FastAPI()

load_dotenv(override=True)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

ACCOUNTS: Dict[str, EmailManager] = parse_accounts(os.getenv("ACCOUNTS", ""))

_MAILBOX_CACHE = TTLCache(ttl_seconds=60, maxsize=64)
_MESSAGE_CACHE = TTLCache(ttl_seconds=600, maxsize=512)


def _emails_equal(a: dict, b: dict) -> bool:
    """
    Compare two email overview dicts for identity using stable keys.
    We compare the full dict as returned (data entries), but you can tighten
    this to only compare refs (account+uid) if desired.
    """
    return a == b


def _ref_key(item: dict) -> Tuple[str, int]:
    """
    Stable unique key for an email item. Assumes:
      item["ref"]["account"] exists (we setdefault this in build_email_overview)
      item["ref"]["uid"] exists (or is None)
    """
    ref = item.get("ref") or {}
    acc = ref.get("account") or ""
    uid = ref.get("uid")
    # uid should be int; if missing, normalize to -1 so it still sorts/compares stably
    return (str(acc), int(uid) if uid is not None else -1)

@app.get("/api/test/overview")
def test_email_overview() -> dict:
    """
    Test overview pagination consistency.

    - Call build_email_overview 3x with limit=50 using cursor chaining to collect 150 newest
    - Call build_email_overview 1x with limit=150 (first page)
    - Compare whether the 150 items match (by stable ref keys and optionally by full payload)

    Notes:
    - This test assumes your paging logic is consistent across different limits.
    - Because results can change between calls (new mail arriving), it's best run in a quiet mailbox.
    """
    mailbox = "INBOX"
    search_query = None
    search_mode = ""
    l = 10
    l_times = 50
    # --------- Fetch 150 via 3 pages of 50 ---------
    pages: List[dict] = []
    cursor: Optional[str] = None
    collected: List[dict] = []

    for i in range(l_times):
        resp = build_email_overview(
            mailbox=mailbox,
            limit=l,
            search_query=search_query,
            search_mode=search_mode,
            cursor=cursor,
            ACCOUNTS=ACCOUNTS,
        )
        pages.append(resp)

        data = resp["data"]
        collected.extend(data)

        cursor = (resp.get("meta") or {}).get("next_cursor")

        # Stop early if there's no next page or we got fewer than 50 (not enough emails)
        if not cursor or len(data) < l:
            break


    # --------- Fetch 150 via single call ---------
    resp_1 = build_email_overview(
        mailbox=mailbox,
        limit=l*l_times,
        search_query=search_query,
        search_mode=search_mode,
        cursor=None,
        ACCOUNTS=ACCOUNTS,
    )
    single_1 = resp_1["data"]

    collected_keys = [_ref_key(x) for x in collected]
    single_keys = [_ref_key(x) for x in single_1]

    same_by_keys = collected_keys == single_keys
    same_by_full_payload = _emails_equal(collected, single_1)

    

    return {
        "ok": same_by_keys and (len(collected) == len(single_1) == l*l_times),
        "same_by_keys": same_by_keys,
        "same_by_full_payload": same_by_full_payload,
    }


@app.get("/api/emails/overview")
def get_email_overview(
    mailbox: str = "INBOX",
    limit: int = 50,
    search_query: Optional[str] = Query(
        default=None,
        description="Optional natural-language search query (will be converted to IMAP query).",
    ),
    search_mode: str = Query(
        default="general",
        description='Search mode: "general" (subject/from/to/text) or "ai" (LLM-derived IMAP).',
        pattern="^(general|ai)$",
    ),
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
    """

    return build_email_overview(
        mailbox=mailbox,
        limit=limit,
        search_query=search_query,
        search_mode=search_mode,
        cursor=cursor,
        accounts=accounts,
        ACCOUNTS=ACCOUNTS,
    )

@app.get("/api/emails/mailbox")
def get_email_mailbox(background_tasks: BackgroundTasks) -> Dict[str, Dict[str, Dict[str, int]]]:
    """
    Return available mailboxes per account.
    """
    cache_key = "mailboxes_all_accounts"
    cached = _MAILBOX_CACHE.get(cache_key)
    if cached is not None:
        background_tasks.add_task(_refresh_mailbox_cache, cache_key)
        return cached

    res = _compute_mailbox_status()
    _MAILBOX_CACHE.set(cache_key, res)
    return res


def _compute_mailbox_status() -> Dict[str, Dict[str, Dict[str, int]]]:
    res: Dict[str, Dict[str, Dict[str, int]]] = {}
    for acc_name, manager in ACCOUNTS.items():
        mailbox_list = manager.list_mailboxes()
        res[acc_name] = {}
        for mailbox in mailbox_list:
            mailbox_status = manager.mailbox_status(mailbox)
            res[acc_name][mailbox] = mailbox_status
    return res


def _refresh_mailbox_cache(cache_key: str) -> None:
    try:
        res = _compute_mailbox_status()
        _MAILBOX_CACHE.set(cache_key, res)
    except Exception:
        pass


@app.get("/api/accounts/{account:path}/mailboxes/{mailbox:path}/emails/{email_id}")
def get_email(background_tasks: BackgroundTasks, account: str, mailbox: str, email_id: int) -> dict:
    """
    Fetch a single email by UID for a given account and mailbox.
    """
    account = unquote(account)
    mailbox = unquote(mailbox)

    manager = ACCOUNTS.get(account)
    if manager is None:
        raise HTTPException(status_code=404, detail="Account not found")

    cache_key = f"{account}|{mailbox}|{int(email_id)}"
    cached = _MESSAGE_CACHE.get(cache_key)
    if cached is not None:
        # still mark seen in background (idempotent-ish)
        email_ref = EmailRef(mailbox=mailbox, uid=email_id)
        background_tasks.add_task(_safe_mark_seen, account, email_ref)
        return cached  # type: ignore

    email_ref = EmailRef(mailbox=mailbox, uid=email_id)

    message: EmailMessage = manager.fetch_message_by_ref(
        email_ref,
        include_attachment_meta=True,
    )

    # mark seen asynchronously
    background_tasks.add_task(_safe_mark_seen, account, email_ref)

    data = message.to_dict()
    data["ref"].setdefault("account", account)

    _MESSAGE_CACHE.set(cache_key, data)
    return data


def _safe_mark_seen(account: str, ref: EmailRef) -> None:
    try:
        manager = ACCOUNTS.get(account)
        if manager is None:
            return
        manager.mark_seen([ref])
    except Exception:
        pass

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
        include_attachment_meta=False,
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
        include_attachment_meta=False,
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
        include_attachment_meta=True,
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


app.add_middleware(GZipMiddleware, minimum_size=1000)
FRONTEND_DIR = BASE / "frontend"
DIST_DIR = FRONTEND_DIR / "dist"

if DIST_DIR.exists():
    # Vite puts hashed assets in dist/assets
    app.mount("/assets", StaticFiles(directory=DIST_DIR / "assets"), name="assets")

    # If you have other static files in dist (favicon, manifest, etc),
    # you can mount the whole dist as well. This works because "/assets"
    # is more specific and will win for /assets/*.
    app.mount("/static", StaticFiles(directory=DIST_DIR), name="static")

    @app.get("/{path:path}")
    def spa(path: str):
        """
        Serve the SPA index for any non-API route.
        """
        # Never hijack API routes
        if path.startswith("api/") or path == "api":
            raise HTTPException(status_code=404, detail="Not found")

        # Serve actual built files if requested directly (favicon, manifest, etc.)
        candidate = DIST_DIR / path
        if path and candidate.is_file():
            return FileResponse(candidate)

        # Default: SPA entrypoint
        return FileResponse(DIST_DIR / "index.html")