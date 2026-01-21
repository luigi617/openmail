from dataclasses import asdict
from http.client import HTTPException
import os
from typing import Dict, List
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from dotenv import load_dotenv

from email_management import EmailManager
from email_management.types import EmailRef
from email_management.models import EmailMessage, EmailOverview

from email_service import parse_accounts

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
def get_email_overview(mailbox: str = "INBOX", n: int = 50) -> List[dict]:
    """
    Return a combined, date-sorted list of EmailOverview objects
    from all configured accounts.
    """
    res: List[EmailOverview] = []
    for manager in ACCOUNTS.values():
        overview_list: List[EmailOverview] = manager.fetch_overview(mailbox=mailbox, n=n)
        res.extend(overview_list)
    res.sort(key=lambda x: x.date, reverse=True)
    payload = [email.to_dict() for email in res]
    return payload

@app.get("/api/emails")
def get_emails(mailbox: str = "INBOX", n: int = 50) -> List[dict]:
    """
    Return a combined, date-sorted list of EmailMessage objects
    from all configured accounts.
    """
    res: List[EmailMessage] = []
    for manager in ACCOUNTS.values():
        email_list: List[EmailMessage] = manager.fetch_latest(mailbox=mailbox, n=n)
        res.extend(email_list)
    res.sort(key=lambda x: x.date, reverse=True)
    payload = [email.to_dict() for email in res]
    return payload

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

@app.get("/api/accounts/{account}/mailboxes/{mailbox}/emails/{email_id}")
def get_email(account: str, mailbox: str, email_id: int) -> dict:
    """
    Fetch a single email by UID for a given account and mailbox.
    Example:
        GET /api/accounts/work/mailboxes/INBOX/emails/123
    """
    manager = ACCOUNTS.get(account)
    if manager is None:
        raise HTTPException(status_code=404, detail="Account not found")

    message: EmailMessage = manager.fetch_message_by_ref(
        EmailRef(mailbox=mailbox, uid=email_id),
        include_attachments=True,
    )
    return message.to_dict()