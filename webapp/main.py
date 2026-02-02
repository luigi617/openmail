import io
import mimetypes
import os
from typing import Dict, List, Optional
from pathlib import Path
from urllib.parse import unquote

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Response, UploadFile
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
from starlette.middleware.gzip import GZipMiddleware

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


@app.get("/api/emails/overview")
def get_email_overview(
    mailbox: str = "INBOX",
    limit: int = 50,
    search_query: Optional[str] = Query(
        default=None,
        description="Optional natural-language search query (will be converted to IMAP query).",
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

    return build_email_overview(
        mailbox=mailbox,
        limit=limit,
        search_query=search_query,
        cursor=cursor,
        accounts=accounts,
        ACCOUNTS=ACCOUNTS
    )

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