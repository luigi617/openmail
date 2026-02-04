# email_service_sql.py
from __future__ import annotations

import base64
from contextlib import contextmanager
import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional
from urllib.parse import urlencode, urlparse

from dotenv import load_dotenv
import requests
from cryptography.fernet import Fernet
from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
    select,
)
from sqlalchemy.orm import DeclarativeBase, Session, relationship, sessionmaker

from oauth2 import (
    GoogleOAuth2Config,
    MicrosoftOAuth2Config,
    YahooOAuth2Config,
    refresh_google_access_token,
    refresh_microsoft_access_token,
    refresh_yahoo_access_token,
)

from openmail import EmailManager
from openmail.auth import NoAuth, OAuth2Auth, PasswordAuth
from openmail.config import IMAPConfig, SMTPConfig
from openmail.imap.client import IMAPClient
from openmail.smtp.client import SMTPClient
load_dotenv(override=True)

# ---------------------------
# DB + encryption
# ---------------------------

DEFAULT_DB_URL = os.getenv("ACCOUNTS_DB_URL", "sqlite:///./accounts.db")
SECRET_KEY = os.getenv("EMAIL_SECRET_KEY")  # MUST be a Fernet key

if not SECRET_KEY:
    # To generate: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    raise RuntimeError("Missing EMAIL_SECRET_KEY (Fernet key). Set it in server environment.")

def utcnow() -> datetime:
    """Timezone-aware UTC 'now' (safe for DB defaults + comparisons)."""
    return datetime.now(timezone.utc)

class SecretBox:
    def __init__(self, key: str):
        self.f = Fernet(key.encode("utf-8") if isinstance(key, str) else key)

    def enc(self, s: Optional[str]) -> Optional[str]:
        if s is None:
            return None
        return self.f.encrypt(s.encode("utf-8")).decode("utf-8")

    def dec(self, s: Optional[str]) -> Optional[str]:
        if s is None:
            return None
        return self.f.decrypt(s.encode("utf-8")).decode("utf-8")


BOX = SecretBox(SECRET_KEY)


class Base(DeclarativeBase):
    pass


class Account(Base):
    __tablename__ = "accounts"

    id = Column(Integer, primary_key=True)
    provider = Column(String(32), nullable=False)     # gmail|outlook|yahoo|icloud
    email = Column(String(320), nullable=False, unique=True)
    auth_method = Column(String(16), nullable=False)  # app|oauth2|no-auth

    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    secrets = relationship("AccountSecrets", back_populates="account", uselist=False, cascade="all, delete-orphan")


class AccountSecrets(Base):
    __tablename__ = "account_secrets"

    account_id = Column(Integer, ForeignKey("accounts.id", ondelete="CASCADE"), primary_key=True)

    # app-password auth
    password_enc = Column(Text, nullable=True)

    # oauth2 auth
    client_id_enc = Column(Text, nullable=True)
    client_secret_enc = Column(Text, nullable=True)
    refresh_token_enc = Column(Text, nullable=True)

    account = relationship("Account", back_populates="secrets")


class OAuthState(Base):
    """
    Minimal/necessary OAuth scratchpad:
      - state (PK): correlates callback + CSRF protection
      - account_id: which account to store refresh token to
      - provider: which OAuth provider logic to use
      - code_verifier: PKCE verifier needed at /token
      - redirect_uri: must match in /token exchange for many providers
      - created_at: expire old states
    """
    __tablename__ = "oauth_states"

    state = Column(String(128), primary_key=True)
    account_id = Column(Integer, ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False)
    provider = Column(String(32), nullable=False)
    code_verifier = Column(String(256), nullable=False)
    redirect_uri = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


_engine = create_engine(DEFAULT_DB_URL, future=True)
_SessionLocal = sessionmaker(bind=_engine, class_=Session, expire_on_commit=False, future=True)


def init_db() -> None:
    Base.metadata.create_all(_engine)


def db_session() -> Session:
    return _SessionLocal()


# ---------------------------
# PKCE
# ---------------------------

def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def make_code_verifier() -> str:
    # 43-128 chars recommended; this is ~43 chars
    return _b64url(os.urandom(32))


def make_code_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return _b64url(digest)

def _normalize_redirect_uri(uri: str) -> str:
    if not uri or not isinstance(uri, str):
        raise ValueError("redirect_uri is required")

    uri = uri.strip()

    # reject already-encoded redirect URIs (common cause of "malformed" via double-encoding)
    if "%3A" in uri or "%2F" in uri or "%25" in uri:
        raise ValueError("redirect_uri looks URL-encoded; pass the raw URL (e.g. http://localhost:8000/callback)")

    parsed = urlparse(uri)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"redirect_uri must be http/https, got: {parsed.scheme!r}")
    if not parsed.netloc:
        raise ValueError("redirect_uri must include host (and port if needed)")

    return uri

def _normalize_scopes(scopes: Optional[str]) -> str:
    scopes = (scopes or "").strip()
    if not scopes:
        raise ValueError("scope is required and cannot be empty")
    # collapse any weird whitespace
    return " ".join(scopes.split())


def as_utc_aware(dt: datetime) -> datetime:
    if dt is None:
        return dt
    if dt.tzinfo is None:
        # treat stored value as UTC
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


# ---------------------------
# EmailManager factory (reuse your existing behavior)
# ---------------------------

def get_gmail_manager(username, auth_method, **kwargs):
    if auth_method == "app":
        password = kwargs.get("password")
        auth = PasswordAuth(username=username, password=password)

    elif auth_method == "oauth2":
        refresh_token = kwargs.get("refresh_token")
        client_id = kwargs.get("client_id")
        client_secret = kwargs.get("client_secret")

        config = GoogleOAuth2Config(client_id=client_id, client_secret=client_secret)
        token_provider = lambda: refresh_google_access_token(config, refresh_token)["access_token"]
        auth = OAuth2Auth(username=username, token_provider=token_provider)

    elif auth_method == "no-auth":
        auth = NoAuth()
    else:
        raise ValueError(f"Unsupported auth_method for Gmail: {auth_method}")

    smtp_cfg = SMTPConfig(host="smtp.gmail.com", port=587, use_starttls=True, from_email=username, auth=auth)
    imap_cfg = IMAPConfig(host="imap.gmail.com", port=993, auth=auth)

    return EmailManager(smtp=SMTPClient.from_config(smtp_cfg), imap=IMAPClient.from_config(imap_cfg))


def get_outlook_manager(username, auth_method, **kwargs):
    if auth_method == "app":
        password = kwargs.get("password")
        auth = PasswordAuth(username=username, password=password)

    elif auth_method == "oauth2":
        refresh_token = kwargs.get("refresh_token")
        client_id = kwargs.get("client_id")
        client_secret = kwargs.get("client_secret")

        config = MicrosoftOAuth2Config(client_id=client_id, client_secret=client_secret)
        token_provider = lambda: refresh_microsoft_access_token(config, refresh_token)["access_token"]
        auth = OAuth2Auth(username=username, token_provider=token_provider)

    elif auth_method == "no-auth":
        auth = NoAuth()
    else:
        raise ValueError(f"Unsupported auth_method for Microsoft: {auth_method}")

    smtp_cfg = SMTPConfig(host="smtp.office365.com", port=587, use_starttls=True, from_email=username, auth=auth)
    imap_cfg = IMAPConfig(host="outlook.office365.com", port=993, auth=auth)

    return EmailManager(smtp=SMTPClient.from_config(smtp_cfg), imap=IMAPClient.from_config(imap_cfg))


def get_yahoo_manager(username, auth_method, **kwargs):
    if auth_method == "app":
        password = kwargs.get("password")
        auth = PasswordAuth(username=username, password=password)

    elif auth_method == "oauth2":
        refresh_token = kwargs.get("refresh_token")
        client_id = kwargs.get("client_id")
        client_secret = kwargs.get("client_secret")

        config = YahooOAuth2Config(client_id=client_id, client_secret=client_secret, redirect_uri=kwargs.get("redirect_uri", "oob"))
        token_provider = lambda: refresh_yahoo_access_token(config, refresh_token)["access_token"]
        auth = OAuth2Auth(username=username, token_provider=token_provider)

    elif auth_method == "no-auth":
        auth = NoAuth()
    else:
        raise ValueError(f"Unsupported auth_method for Yahoo: {auth_method}")

    smtp_cfg = SMTPConfig(host="smtp.mail.yahoo.com", port=587, use_starttls=True, from_email=username, auth=auth)
    imap_cfg = IMAPConfig(host="imap.mail.yahoo.com", port=993, auth=auth)

    return EmailManager(smtp=SMTPClient.from_config(smtp_cfg), imap=IMAPClient.from_config(imap_cfg))


def get_icloud_manager(username, auth_method, **kwargs):
    if auth_method == "app":
        password = kwargs.get("password")
        auth = PasswordAuth(username=username, password=password)
    elif auth_method == "oauth2":
        raise ValueError("iCloud Mail does not support OAuth2 tokens for IMAP/SMTP; use an app password.")
    elif auth_method == "no-auth":
        auth = NoAuth()
    else:
        raise ValueError(f"Unsupported auth_method for iCloud: {auth_method}")

    smtp_cfg = SMTPConfig(host="smtp.mail.me.com", port=587, use_starttls=True, from_email=username, auth=auth)
    imap_cfg = IMAPConfig(host="imap.mail.me.com", port=993, auth=auth)

    return EmailManager(smtp=SMTPClient.from_config(smtp_cfg), imap=IMAPClient.from_config(imap_cfg))


def get_email_manager(provider, username, auth_method, **kwargs):
    if provider == "gmail":
        return get_gmail_manager(username, auth_method, **kwargs)
    if provider == "outlook":
        return get_outlook_manager(username, auth_method, **kwargs)
    if provider == "yahoo":
        return get_yahoo_manager(username, auth_method, **kwargs)
    if provider == "icloud":
        return get_icloud_manager(username, auth_method, **kwargs)
    raise ValueError(f"Unsupported email provider: {provider}")


# ---------------------------
# Load accounts into EmailManager dict
# ---------------------------
@contextmanager
def get_db():
    db = db_session()
    try:
        yield db
    finally:
        db.close()

def load_accounts_from_db() -> Dict[str, EmailManager]:
    """
    Returns {email: EmailManager} just like your old parse_accounts().
    """
    results: Dict[str, EmailManager] = {}

    with db_session() as db:
        accounts = db.execute(select(Account)).scalars().all()
        for acc in accounts:
            s = acc.secrets
            kwargs = {}

            if acc.auth_method == "app":
                kwargs["password"] = BOX.dec(s.password_enc)

            elif acc.auth_method == "oauth2":
                kwargs["client_id"] = BOX.dec(s.client_id_enc)
                kwargs["client_secret"] = BOX.dec(s.client_secret_enc)
                kwargs["refresh_token"] = BOX.dec(s.refresh_token_enc)

            elif acc.auth_method == "no-auth":
                pass
            else:
                continue

            results[acc.email] = get_email_manager(acc.provider, acc.email, acc.auth_method, **kwargs)

    return results


# ---------------------------
# CRUD helpers
# ---------------------------
def list_accounts():
    """
    Returns safe account info for UI (no secrets).
    """
    with db_session() as db:
        accounts = db.execute(select(Account)).scalars().all()
        out = []
        for a in accounts:
            s = a.secrets
            out.append(
                {
                    "id": a.id,
                    "provider": a.provider,
                    "email": a.email,
                    "auth_method": a.auth_method,
                    "has_password": bool(s and s.password_enc),
                    "has_client": bool(s and s.client_id_enc and s.client_secret_enc),
                    "has_refresh_token": bool(s and s.refresh_token_enc),
                    "created_at": a.created_at.isoformat(),
                    "updated_at": a.updated_at.isoformat(),
                }
            )
        return out
    
def get_account(account_id: int):
    with db_session() as db:
        a = db.get(Account, account_id)
        if not a:
            return None
        s = a.secrets
        return {
            "id": a.id,
            "provider": a.provider,
            "email": a.email,
            "auth_method": a.auth_method,
            "has_password": bool(s and s.password_enc),
            "has_client": bool(s and s.client_id_enc and s.client_secret_enc),
            "has_refresh_token": bool(s and s.refresh_token_enc),
            "created_at": a.created_at.isoformat(),
            "updated_at": a.updated_at.isoformat(),
        }

def upsert_app_password_account(provider: str, email: str, password: str) -> int:
    with db_session() as db:
        acc = db.execute(select(Account).where(Account.email == email)).scalar_one_or_none()
        if acc is None:
            acc = Account(provider=provider, email=email, auth_method="app")
            db.add(acc)
            db.flush()
            db.add(AccountSecrets(account_id=acc.id, password_enc=BOX.enc(password)))
        else:
            acc.provider = provider
            acc.auth_method = "app"
            if acc.secrets is None:
                acc.secrets = AccountSecrets(account_id=acc.id)
            acc.secrets.password_enc = BOX.enc(password)
            # clear oauth fields
            acc.secrets.client_id_enc = None
            acc.secrets.client_secret_enc = None
            acc.secrets.refresh_token_enc = None

        db.commit()
        return acc.id


def upsert_oauth2_account(provider: str, email: str, client_id: str, client_secret: str) -> int:
    with db_session() as db:
        acc = db.execute(select(Account).where(Account.email == email)).scalar_one_or_none()
        if acc is None:
            acc = Account(provider=provider, email=email, auth_method="oauth2")
            db.add(acc)
            db.flush()
            db.add(
                AccountSecrets(
                    account_id=acc.id,
                    client_id_enc=BOX.enc(client_id),
                    client_secret_enc=BOX.enc(client_secret),
                    refresh_token_enc=None,
                )
            )
        else:
            acc.provider = provider
            acc.auth_method = "oauth2"
            if acc.secrets is None:
                acc.secrets = AccountSecrets(account_id=acc.id)
            acc.secrets.client_id_enc = BOX.enc(client_id)
            acc.secrets.client_secret_enc = BOX.enc(client_secret)
            # refresh token will be set after callback
            acc.secrets.refresh_token_enc = None
            # clear app password
            acc.secrets.password_enc = None

        db.commit()
        return acc.id


# ---------------------------
# OAuth2: build authorize URL + handle callback
# ---------------------------

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"

MS_AUTH_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/authorize"
MS_TOKEN_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/token"

YAHOO_AUTH_URL = "https://api.login.yahoo.com/oauth2/request_auth"
YAHOO_TOKEN_URL = "https://api.login.yahoo.com/oauth2/get_token"


def _default_scopes(provider: str) -> str:
    # You can adjust if your providers require different scopes in your app.
    if provider == "gmail":
        return "https://mail.google.com/"
    if provider == "outlook":
        # Common set for Microsoft v2 to get refresh token; actual IMAP/SMTP scopes depend on your usage.
        return "offline_access https://outlook.office.com/IMAP.AccessAsUser.All https://outlook.office.com/SMTP.Send"
    if provider == "yahoo":
        return "mail-r"
    return ""


def begin_oauth(provider: str, account_id: int, redirect_uri: str, scopes: Optional[str] = None) -> str:
    """
    Creates oauth_states row and returns provider authorize URL.
    """
    provider = (provider or "").strip().lower()
    if provider not in ("gmail", "outlook", "yahoo"):
        raise ValueError(f"Unsupported provider for OAuth: {provider}")
    
    redirect_uri = _normalize_redirect_uri(redirect_uri)
    scopes = _normalize_scopes(scopes or _default_scopes(provider))

    with db_session() as db:
        acc = db.get(Account, account_id)
        if not acc:
            raise ValueError("Account not found")
        if acc.provider != provider:
            raise ValueError(f"Account provider mismatch: account={acc.provider}, requested={provider}")
        if acc.auth_method != "oauth2":
            raise ValueError("Account is not oauth2")
        if not acc.secrets or not (acc.secrets.client_id_enc and acc.secrets.client_secret_enc):
            raise ValueError("Missing client_id/client_secret")

        client_id = BOX.dec(acc.secrets.client_id_enc)
        code_verifier = make_code_verifier()
        code_challenge = make_code_challenge(code_verifier)
        state = secrets.token_urlsafe(32)

        db.add(
            OAuthState(
                state=state,
                account_id=account_id,
                provider=provider,
                code_verifier=code_verifier,
                redirect_uri=redirect_uri,
            )
        )
        db.commit()

    if provider == "gmail":
        params = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": scopes,
            "state": state,

            # refresh token
            "access_type": "offline",
            "prompt": "consent",

            # PKCE is supported by Google
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
        return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"

    if provider == "outlook":
        # Microsoft v2 supports PKCE; keep it.
        params = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": scopes,
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            # optional but often helpful
            "response_mode": "query",
        }
        return f"{MS_AUTH_URL}?{urlencode(params)}"

    if provider == "yahoo":
        # Yahoo OAuth2 authorize commonly does NOT support PKCE params. Remove them.
        params = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": scopes,
            "state": state,
        }
        return f"{YAHOO_AUTH_URL}?{urlencode(params)}"

    raise ValueError(f"Unsupported provider for OAuth: {provider}")


def complete_oauth_callback(state: str, code: str) -> None:
    """
    Exchanges authorization code -> refresh token and stores it on the account.
    """
    with db_session() as db:
        st = db.get(OAuthState, state)
        if not st:
            raise ValueError("Invalid state")

        # expire after 10 minutes
        if as_utc_aware(st.created_at) < (utcnow() - timedelta(minutes=10)):
            db.delete(st)
            db.commit()
            raise ValueError("State expired")

        acc = db.get(Account, st.account_id)
        if not acc or not acc.secrets:
            raise ValueError("Account missing")

        client_id = BOX.dec(acc.secrets.client_id_enc)
        client_secret = BOX.dec(acc.secrets.client_secret_enc)
        code_verifier = st.code_verifier
        redirect_uri = st.redirect_uri

        refresh_token = _exchange_code_for_refresh_token(
            provider=st.provider,
            client_id=client_id,
            client_secret=client_secret,
            code=code,
            code_verifier=code_verifier,
            redirect_uri=redirect_uri,
        )

        acc.secrets.refresh_token_enc = BOX.enc(refresh_token)

        # cleanup state
        db.delete(st)
        db.commit()


def _exchange_code_for_refresh_token(
    provider: str,
    client_id: str,
    client_secret: str,
    code: str,
    code_verifier: str,
    redirect_uri: str,
) -> str:
    """
    Authorization code exchange. Returns refresh_token.
    """
    if provider == "gmail":
        data = {
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
            "code_verifier": code_verifier,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        }
        r = requests.post(GOOGLE_TOKEN_URL, data=data, timeout=20)
        r.raise_for_status()
        j = r.json()
        rt = j.get("refresh_token")
        if not rt:
            raise ValueError("Google did not return refresh_token (try prompt=consent + access_type=offline)")
        return rt

    if provider == "outlook":
        data = {
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
            "code_verifier": code_verifier,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        }
        r = requests.post(MS_TOKEN_URL, data=data, timeout=20)
        r.raise_for_status()
        j = r.json()
        rt = j.get("refresh_token")
        if not rt:
            raise ValueError("Microsoft did not return refresh_token (ensure offline_access scope)")
        return rt

    if provider == "yahoo":
        # Yahoo commonly uses Basic auth with client_id:client_secret
        basic = base64.b64encode(f"{client_id}:{client_secret}".encode("utf-8")).decode("ascii")
        headers = {"Authorization": f"Basic {basic}"}
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "code_verifier": code_verifier,
        }
        r = requests.post(YAHOO_TOKEN_URL, data=data, headers=headers, timeout=20)
        r.raise_for_status()
        j = r.json()
        rt = j.get("refresh_token")
        if not rt:
            raise ValueError("Yahoo did not return refresh_token")
        return rt

    raise ValueError(f"Unsupported provider token exchange: {provider}")
