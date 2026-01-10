import os

import pytest
from email_management.auth import PasswordAuth
from email_management.config import SMTPConfig, IMAPConfig
from email_management.errors import AuthError
from email_management.smtp.client import SMTPClient
from email_management.imap.client import IMAPClient
from email_management import EmailManager
from email_management.models import EmailMessage

from dotenv import load_dotenv
load_dotenv(override=True)

def test_password_auth_with_correct_info():
    username = os.environ.get("TEST_EMAIL_USERNAME")
    password = os.environ.get("TEST_EMAIL_PASSWORD")
    auth = PasswordAuth(
        username=username,
        password=password,
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
    
def test_password_auth_with_wrong_password():
    username = os.environ.get("TEST_EMAIL_USERNAME")
    password = "1234567890"
    auth = PasswordAuth(
        username=username,
        password=password,
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
    
def test_password_auth_with_wrong_username():
    username = "test@gmail.com"
    password = os.environ.get("TEST_EMAIL_PASSWORD")
    auth = PasswordAuth(
        username=username,
        password=password,
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
    
