import os
from typing import Callable

import pytest
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from email_management.auth import OAuth2Auth
from email_management.config import SMTPConfig, IMAPConfig
from email_management.errors import AuthError
from email_management.smtp.client import SMTPClient
from email_management.imap.client import IMAPClient
from email_management import EmailManager
from email_management.models import EmailMessage

from dotenv import load_dotenv
load_dotenv(override=True)


def make_gmail_token_provider(
    client_id: str,
    client_secret: str,
    refresh_token: str,
) -> Callable[[], str]:
    """
    Returns a zero-arg function that always gives you a *valid* access token.
    It hides all the refresh logic inside.
    """
    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret,
        scopes=["https://mail.google.com/"],
    )

    def provider() -> str:
        if not creds.valid or not creds.token:
            creds.refresh(Request())
        return creds.token

    return provider

def test_oauth2_auth_with_correct_info():
    username = os.environ.get("TEST_EMAIL_USERNAME")
    client_id = os.environ.get("TEST_EMAIL_CLIENT_ID")
    client_secret = os.environ.get("TEST_EMAIL_CLIENT_SECRET")
    refresh_token = os.environ.get("TEST_EMAIL_REFRESH_TOKEN")

    token_provider = make_gmail_token_provider(
        client_id=client_id,
        client_secret=client_secret,
        refresh_token=refresh_token,
    )
    
    auth = OAuth2Auth(
        username=username,
        token_provider=token_provider,
    )

    smtp_cfg = SMTPConfig(
        host="smtp.gmail.com",
        port=587,
        use_starttls=True,
        from_email=username,
        auth=auth,
    )

    imap_cfg = IMAPConfig(
        host="imap.gmail.com",
        port=993,
        auth=auth,
    )

    smtp = SMTPClient.from_config(smtp_cfg)
    imap = IMAPClient.from_config(imap_cfg)
    manager = EmailManager(smtp=smtp, imap=imap)

    messages = manager.fetch_latest(n=1)
    assert len(messages) == 1

def test_oauth2_auth_with_wrong_client_id():
    username = os.environ.get("TEST_EMAIL_USERNAME")
    client_id = os.environ.get("TEST_EMAIL_CLIENT_ID")
    client_secret = "wrongsecret"
    refresh_token = os.environ.get("TEST_EMAIL_REFRESH_TOKEN")

    token_provider = make_gmail_token_provider(
        client_id=client_id,
        client_secret=client_secret,
        refresh_token=refresh_token,
    )
    
    auth = OAuth2Auth(
        username=username,
        token_provider=token_provider,
    )

    smtp_cfg = SMTPConfig(
        host="smtp.gmail.com",
        port=587,
        use_starttls=True,
        from_email=username,
        auth=auth,
    )

    imap_cfg = IMAPConfig(
        host="imap.gmail.com",
        port=993,
        auth=auth,
    )

    smtp = SMTPClient.from_config(smtp_cfg)
    imap = IMAPClient.from_config(imap_cfg)
    manager = EmailManager(smtp=smtp, imap=imap)

    with pytest.raises(AuthError):
        manager.fetch_latest(n=1)
    
def test_oauth2_auth_with_wrong_client_secret():
    username = os.environ.get("TEST_EMAIL_USERNAME")
    client_id = "wrong.apps.googleusercontent.com"
    client_secret = os.environ.get("TEST_EMAIL_CLIENT_SECRET")
    refresh_token = os.environ.get("TEST_EMAIL_REFRESH_TOKEN")

    token_provider = make_gmail_token_provider(
        client_id=client_id,
        client_secret=client_secret,
        refresh_token=refresh_token,
    )
    
    auth = OAuth2Auth(
        username=username,
        token_provider=token_provider,
    )

    smtp_cfg = SMTPConfig(
        host="smtp.gmail.com",
        port=587,
        use_starttls=True,
        from_email=username,
        auth=auth,
    )

    imap_cfg = IMAPConfig(
        host="imap.gmail.com",
        port=993,
        auth=auth,
    )

    smtp = SMTPClient.from_config(smtp_cfg)
    imap = IMAPClient.from_config(imap_cfg)
    manager = EmailManager(smtp=smtp, imap=imap)

    with pytest.raises(AuthError):
        manager.fetch_latest(n=1)
    
def test_oauth2_auth_with_wrong_username():
    username = "test@gmail.com"
    client_id = os.environ.get("TEST_EMAIL_CLIENT_ID")
    client_secret = os.environ.get("TEST_EMAIL_CLIENT_SECRET")
    refresh_token = os.environ.get("TEST_EMAIL_REFRESH_TOKEN")

    token_provider = make_gmail_token_provider(
        client_id=client_id,
        client_secret=client_secret,
        refresh_token=refresh_token,
    )
    
    auth = OAuth2Auth(
        username=username,
        token_provider=token_provider,
    )

    smtp_cfg = SMTPConfig(
        host="smtp.gmail.com",
        port=587,
        use_starttls=True,
        from_email=username,
        auth=auth,
    )

    imap_cfg = IMAPConfig(
        host="imap.gmail.com",
        port=993,
        auth=auth,
    )

    smtp = SMTPClient.from_config(smtp_cfg)
    imap = IMAPClient.from_config(imap_cfg)
    manager = EmailManager(smtp=smtp, imap=imap)

    with pytest.raises(AuthError):
        manager.fetch_latest(n=1)
    
def test_oauth2_auth_with_wrong_refresh_token():
    username = os.environ.get("TEST_EMAIL_USERNAME")
    client_id = os.environ.get("TEST_EMAIL_CLIENT_SECRET")
    client_secret = os.environ.get("TEST_EMAIL_CLIENT_SECRET")
    refresh_token = "wrongrefreshtoken"

    token_provider = make_gmail_token_provider(
        client_id=client_id,
        client_secret=client_secret,
        refresh_token=refresh_token,
    )
    
    auth = OAuth2Auth(
        username=username,
        token_provider=token_provider,
    )

    smtp_cfg = SMTPConfig(
        host="smtp.gmail.com",
        port=587,
        use_starttls=True,
        from_email=username,
        auth=auth,
    )

    imap_cfg = IMAPConfig(
        host="imap.gmail.com",
        port=993,
        auth=auth,
    )

    smtp = SMTPClient.from_config(smtp_cfg)
    imap = IMAPClient.from_config(imap_cfg)
    manager = EmailManager(smtp=smtp, imap=imap)

    with pytest.raises(AuthError):
        manager.fetch_latest(n=1)
    
