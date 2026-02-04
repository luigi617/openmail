# accounts_api.py
from __future__ import annotations

import threading
from typing import List, Optional

from fastapi.responses import HTMLResponse

from context import ACCOUNTS
from email_service import (
    BOX,
    Account,
    AccountSecrets,
    begin_oauth,
    complete_oauth_callback,
    db_session,
    get_account,
    init_db,
    list_accounts,
    upsert_app_password_account,
    upsert_oauth2_account,
)
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/accounts", tags=["accounts"])

# We need a hook to reload the in-memory ACCOUNTS dict living in main.py
# main.py will call set_reload_callback(reload_fn)
_reload_callback = None
_reload_lock = threading.Lock()


def set_reload_callback(fn):
    global _reload_callback
    _reload_callback = fn


def _reload_accounts_now():
    """
    Calls main.py's reload function so new accounts are used immediately.
    """
    if _reload_callback is None:
        return
    with _reload_lock:
        _reload_callback()


# ---------------------------
# Pydantic models
# ---------------------------


class AccountUI(BaseModel):
    id: int
    provider: str
    email: str
    auth_method: str
    has_password: bool
    has_client: bool
    has_refresh_token: bool
    created_at: str
    updated_at: str


class CreateAppAccountIn(BaseModel):
    provider: str = Field(..., pattern="^(gmail|outlook|yahoo|icloud)$")
    email: str
    password: str


class CreateOAuth2AccountIn(BaseModel):
    provider: str = Field(..., pattern="^(gmail|outlook|yahoo)$")  # icloud not supported for oauth2
    email: str
    client_id: str
    client_secret: str
    redirect_uri: str  # where provider redirects with ?code=&state=
    scopes: Optional[str] = None  # optional override


class UpdateAccountMetaIn(BaseModel):
    provider: Optional[str] = Field(None, pattern="^(gmail|outlook|yahoo|icloud)$")
    email: Optional[str] = None
    auth_method: Optional[str] = Field(None, pattern="^(app|oauth2|no-auth)$")


class UpdateSecretsIn(BaseModel):
    # allow rotation / updates
    password: Optional[str] = None
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    clear_refresh_token: bool = False


# ---------------------------
# Endpoints
# ---------------------------


@router.get("/{account}/connected")
def is_account_connected(account: str) -> dict:
    email_manager = ACCOUNTS.get(account)
    if not email_manager:
        return {"result": False, "detail": "Account does not exist"}
    health_res = email_manager.health_check()
    if not health_res["imap"] and not health_res["smtp"]:
        return {"result": False, "detail": "IMAP and SMTP are not active"}
    elif not health_res["imap"]:
        return {"result": False, "detail": "IMAP is not active"}
    elif not health_res["smtp"]:
        return {"result": False, "detail": "SMTP are not active"}
    return {"result": True, "detail": "ok"}


@router.get("", response_model=List[AccountUI])
def get_all_accounts():
    """
    UI-friendly list of accounts, without secrets.
    """
    return list_accounts()


@router.get("/{account_id}", response_model=AccountUI)
def get_one_account(account_id: int):
    a = get_account(account_id)
    if not a:
        raise HTTPException(status_code=404, detail="Account not found")
    return a


@router.post("/app")
def create_or_update_app_password_account(payload: CreateAppAccountIn):
    """
    Create/update an 'app password' account (email + password).
    """
    init_db()
    account_id = upsert_app_password_account(payload.provider, payload.email, payload.password)

    # reload runtime dict so email endpoints immediately see it
    _reload_accounts_now()

    return {
        "status": "ok",
        "account_id": account_id,
        "account": get_account(account_id),
    }


@router.post("/oauth2")
def create_or_update_oauth2_account(payload: CreateOAuth2AccountIn):
    """
    Create/update an OAuth2 account (email + client_id + client_secret).
    Returns the authorize_url to open in browser.
    """
    init_db()
    account_id = upsert_oauth2_account(
        payload.provider, payload.email, payload.client_id, payload.client_secret
    )

    # Start OAuth immediately (creates oauth_state row)
    try:
        authorize_url = begin_oauth(
            provider=payload.provider,
            account_id=account_id,
            redirect_uri=payload.redirect_uri,
            scopes=payload.scopes,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    return {
        "status": "ok",
        "account_id": account_id,
        "authorize_url": authorize_url,
        "account": get_account(account_id),
    }


@router.post("/{account_id}/oauth2/authorize")
def start_oauth_existing_account(
    account_id: int,
    redirect_uri: str = Query(...),
    scopes: Optional[str] = Query(None),
):
    """
    For an existing oauth2 account, generate an authorize_url again.
    """
    a = get_account(account_id)
    if not a:
        raise HTTPException(status_code=404, detail="Account not found")
    if a["auth_method"] != "oauth2":
        raise HTTPException(status_code=400, detail="Account is not oauth2")
    try:
        authorize_url = begin_oauth(
            provider=a["provider"],
            account_id=account_id,
            redirect_uri=redirect_uri,
            scopes=scopes,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    return {"status": "ok", "authorize_url": authorize_url}


@router.get("/oauth/callback")
def oauth_callback(state: str = Query(...), code: str = Query(...)):
    """
    Provider redirects here with ?state=...&code=...
    This endpoint exchanges code -> refresh_token and stores it encrypted.
    """
    try:
        complete_oauth_callback(state=state, code=code)
    except Exception as e:
        return HTMLResponse(f"""
            <html>
            <body>
                <h3>OAuth failed</h3>
                <pre>{str(e)}</pre>
                <p>You can close this tab.</p>
            </body>
            </html>
            """, status_code=400)

    # reload runtime accounts so oauth2 accounts become active immediately
    _reload_accounts_now()

    return HTMLResponse("""
        <html>
        <body>
            <script>
            try {
                if (window.opener && !window.opener.closed) {
                window.opener.postMessage({ type: "oauth-success" }, "*");
                }
            } finally {
                window.close();
            }
            </script>
            <p>Authentication complete. You can close this tab.</p>
        </body>
        </html>
        """)


@router.patch("/{account_id}")
def update_account_meta(account_id: int, payload: UpdateAccountMetaIn):
    """
    Update provider/email/auth_method.
    Note: changing auth_method may require setting secrets accordingly.
    """
    with db_session() as db:
        a = db.get(Account, account_id)
        if not a:
            raise HTTPException(status_code=404, detail="Account not found")

        if payload.provider is not None:
            a.provider = payload.provider
        if payload.email is not None:
            a.email = payload.email
        if payload.auth_method is not None:
            a.auth_method = payload.auth_method

        db.commit()

    _reload_accounts_now()
    return {"status": "ok", "account": get_account(account_id)}


@router.patch("/{account_id}/secrets")
def update_secrets(account_id: int, payload: UpdateSecretsIn):
    """
    Rotate/update secrets for an account.
    - For app auth: set password
    - For oauth2 auth: set client_id/client_secret, optionally clear refresh token
    """
    with db_session() as db:
        a = db.get(Account, account_id)
        if not a:
            raise HTTPException(status_code=404, detail="Account not found")

        if a.secrets is None:
            a.secrets = AccountSecrets(account_id=a.id)

        s = a.secrets

        if payload.password is not None:
            s.password_enc = BOX.enc(payload.password)

        if payload.client_id is not None:
            s.client_id_enc = BOX.enc(payload.client_id)

        if payload.client_secret is not None:
            s.client_secret_enc = BOX.enc(payload.client_secret)

        if payload.clear_refresh_token:
            s.refresh_token_enc = None

        db.commit()

    _reload_accounts_now()
    return {"status": "ok", "account": get_account(account_id)}


@router.delete("/{account_id}")
def delete_account(account_id: int):
    with db_session() as db:
        a = db.get(Account, account_id)
        if not a:
            raise HTTPException(status_code=404, detail="Account not found")
        db.delete(a)
        db.commit()

    _reload_accounts_now()
    return {"status": "ok"}


@router.post("/reload")
def reload_accounts():
    """
    Manual reload of in-memory ACCOUNTS dict.
    """
    _reload_accounts_now()
    return {"status": "ok"}
