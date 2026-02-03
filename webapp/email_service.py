from typing import Dict

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


class AccountParseError(Exception):
    pass


def parse_accounts(env_value: str) -> Dict[str, EmailManager]:
    if not env_value:
        return {}

    raw_accounts = [line for line in env_value.splitlines()]

    results: Dict[str, EmailManager] = {}

    for raw in raw_accounts:
        parts = raw.split(':')
        if len(parts) < 3:
            raise AccountParseError(f"Invalid account entry (needs at least provider:username:auth_method): {raw!r}")

        provider = parts[0].strip()
        username = parts[1].strip()
        auth_method = parts[2].strip()

        if not provider:
            raise AccountParseError(f"Missing provider in {raw!r}")
        if not username:
            raise AccountParseError(f"Missing username in {raw!r}")
        if not auth_method:
            raise AccountParseError(f"Missing auth_method in {raw!r}")

        # parse key=value pairs
        kv_pairs = {}
        for p in parts[3:]:
            if '=' not in p:
                raise AccountParseError(
                    f"Invalid field {p!r} in {raw!r}, expected key=value"
                )
            key, val = p.split('=', 1)
            key = key.strip()
            val = val.strip()
            if not key:
                raise AccountParseError(f"Empty key in field {p!r} for {raw!r}")
            kv_pairs[key] = val

        results[username] = get_email_manager(provider, username, auth_method, **kv_pairs)

    return results

def get_gmail_manager(username, auth_method, **kwargs):
    if auth_method == "app":
        password = kwargs.get("password")
        auth = PasswordAuth(
            username=username,
            password=password,
        )
    elif auth_method == "oauth2":
        refresh_token = kwargs.get("refresh_token")
        client_id = kwargs.get("client_id")
        client_secret = kwargs.get("client_secret")
        config = GoogleOAuth2Config(
            client_id=client_id,
            client_secret=client_secret,
        )
        token_provider = lambda: refresh_google_access_token(config, refresh_token)["access_token"]
        auth = OAuth2Auth(
            username=username,
            token_provider=token_provider,
        )
    elif auth_method == "no-auth":
        auth = NoAuth()
    else:
        raise ValueError(f"Unsupported auth_method for Gmail: {auth_method}")

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

    return manager

def get_outlook_manager(username, auth_method, **kwargs):
    if auth_method == "app":
        password = kwargs.get("password")
        auth = PasswordAuth(
            username=username,
            password=password,
        )
    elif auth_method == "oauth2":
        refresh_token = kwargs.get("refresh_token")
        client_id = kwargs.get("client_id")
        client_secret = kwargs.get("client_secret")
        config = MicrosoftOAuth2Config(
            client_id=client_id,
            client_secret=client_secret,
        )
        token_provider = lambda: refresh_microsoft_access_token(config, refresh_token)["access_token"]
        auth = OAuth2Auth(
            username=username,
            token_provider=token_provider,
        )
    elif auth_method == "no-auth":
        auth = NoAuth()
    else:
        raise ValueError(f"Unsupported auth_method for Microsoft: {auth_method}")

    smtp_cfg = SMTPConfig(
        host="smtp.office365.com",
        port=587,
        use_starttls=True,
        from_email=username,
        auth=auth,
    )

    imap_cfg = IMAPConfig(
        host="outlook.office365.com",
        port=993,
        auth=auth,
    )

    smtp = SMTPClient.from_config(smtp_cfg)
    imap = IMAPClient.from_config(imap_cfg)
    return EmailManager(smtp=smtp, imap=imap)

def get_yahoo_manager(username, auth_method, **kwargs):
    if auth_method == "app":
        password = kwargs.get("password")
        auth = PasswordAuth(
            username=username,
            password=password,
        )
    elif auth_method == "oauth2":
        refresh_token = kwargs.get("refresh_token")
        client_id = kwargs.get("client_id")
        client_secret = kwargs.get("client_secret")
        config = YahooOAuth2Config(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri="oob",
        )
        token_provider = lambda: refresh_yahoo_access_token(config, refresh_token)["access_token"]
        auth = OAuth2Auth(
            username=username,
            token_provider=token_provider,
        )
    elif auth_method == "no-auth":
        auth = NoAuth()
    else:
        raise ValueError(f"Unsupported auth_method for Yahoo: {auth_method}")

    smtp_cfg = SMTPConfig(
        host="smtp.mail.yahoo.com",
        port=587,
        use_starttls=True,
        from_email=username,
        auth=auth,
    )

    imap_cfg = IMAPConfig(
        host="imap.mail.yahoo.com",
        port=993,
        auth=auth,
    )

    smtp = SMTPClient.from_config(smtp_cfg)
    imap = IMAPClient.from_config(imap_cfg)
    return EmailManager(smtp=smtp, imap=imap)

def get_icloud_manager(username, auth_method, **kwargs):
    if auth_method == "app":
        password = kwargs.get("password")
        auth = PasswordAuth(
            username=username,
            password=password,
        )
    elif auth_method == "oauth2":
        raise ValueError(
            "iCloud Mail does not support OAuth2 tokens for IMAP/SMTP; "
            "use an app-specific password and normal IMAP/SMTP auth instead."
        )
    elif auth_method == "no-auth":
        auth = NoAuth()
    else:
        raise ValueError(f"Unsupported auth_method for iCloud: {auth_method}")

    smtp_cfg = SMTPConfig(
        host="smtp.mail.me.com",
        port=587,
        use_starttls=True,
        from_email=username,
        auth=auth,
    )

    imap_cfg = IMAPConfig(
        host="imap.mail.me.com",
        port=993,
        auth=auth,
    )

    smtp = SMTPClient.from_config(smtp_cfg)
    imap = IMAPClient.from_config(imap_cfg)
    return EmailManager(smtp=smtp, imap=imap)

def get_email_manager(provider, username, auth_method, **kwargs):
    if provider == "gmail":
        return get_gmail_manager(username, auth_method, **kwargs)
    elif provider == "outlook":
        return get_outlook_manager(username, auth_method, **kwargs)
    elif provider == "yahoo":
        return get_yahoo_manager(username, auth_method, **kwargs)
    elif provider == "icloud":
        return get_icloud_manager(username, auth_method, **kwargs)
    else:
        raise ValueError(f"Unsupported email provider: {provider}")
