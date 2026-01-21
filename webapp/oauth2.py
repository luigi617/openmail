
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Any, Optional

import requests


class OAuth2TokenError(RuntimeError):
    """Raised when the token endpoint returns an error response."""


@dataclass(frozen=True)
class GoogleOAuth2Config:
    client_id: str
    client_secret: str


def refresh_google_access_token(
    config: GoogleOAuth2Config,
    refresh_token: str,
) -> Dict[str, Any]:
    """
    Exchange a Google refresh token for a new access token.

    Returns the parsed JSON from Google's token endpoint, typically:
      {
        "access_token": "...",
        "expires_in": 3600,
        "scope": "...",
        "token_type": "Bearer",
        "refresh_token": "..."  # sometimes omitted
      }

    Raises OAuth2TokenError on HTTP or JSON-level errors.
    """
    token_endpoint = "https://oauth2.googleapis.com/token"

    data = {
        "client_id": config.client_id,
        "client_secret": config.client_secret,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }

    resp = requests.post(token_endpoint, data=data, timeout=10)
    if not resp.ok:
        raise OAuth2TokenError(
            f"Google token endpoint HTTP {resp.status_code}: {resp.text}"
        )

    payload = resp.json()
    if "access_token" not in payload:
        # Google typically includes a more specific error
        raise OAuth2TokenError(f"Google token response error: {payload!r}")

    return payload


@dataclass(frozen=True)
class MicrosoftOAuth2Config:
    client_id: str
    client_secret: str
    # For personal + work accounts you can usually use "common";
    # for only consumer accounts, "consumers"; for only org: your tenant ID.
    tenant: str = "common"


def refresh_microsoft_access_token(
    config: MicrosoftOAuth2Config,
    refresh_token: str,
    scope: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Exchange a Microsoft refresh token for a new access token.

    `scope` should usually match or be a subset of what you originally requested,
    e.g.:
      "https://outlook.office.com/IMAP.AccessAsUser.All offline_access"
      "offline_access https://outlook.office.com/SMTP.Send"

    Returns JSON with:
      {
        "token_type": "Bearer",
        "scope": "...",
        "expires_in": 3599,
        "access_token": "...",
        "refresh_token": "..."  # may or may not be present
      }
    """
    token_endpoint = (
        f"https://login.microsoftonline.com/{config.tenant}/oauth2/v2.0/token"
    )

    data = {
        "client_id": config.client_id,
        "client_secret": config.client_secret,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }

    # Some flows require passing scope again; harmless to omit if not needed.
    if scope:
        data["scope"] = scope

    resp = requests.post(token_endpoint, data=data, timeout=10)
    if not resp.ok:
        raise OAuth2TokenError(
            f"Microsoft token endpoint HTTP {resp.status_code}: {resp.text}"
        )

    payload = resp.json()
    if "access_token" not in payload:
        raise OAuth2TokenError(f"Microsoft token response error: {payload!r}")

    return payload


@dataclass(frozen=True)
class YahooOAuth2Config:
    client_id: str
    client_secret: str
    redirect_uri: str


def refresh_yahoo_access_token(
    config: YahooOAuth2Config,
    refresh_token: str,
) -> Dict[str, Any]:
    """
    Exchange a Yahoo refresh token for a new access token.

    Yahoo uses the same /get_token endpoint for both code->token and refresh.

    Request:
      POST https://api.login.yahoo.com/oauth2/get_token
      Authorization: Basic base64(client_id:client_secret)
      Content-Type: application/x-www-form-urlencoded

      grant_type=refresh_token&
      redirect_uri=...&
      refresh_token=...

    Response (simplified):
      {
        "access_token": "...",
        "token_type": "bearer",
        "expires_in": 3600,
        "refresh_token": "...",
        ...
      }
    """
    token_endpoint = "https://api.login.yahoo.com/oauth2/get_token"

    data = {
        "grant_type": "refresh_token",
        "redirect_uri": config.redirect_uri,
        "refresh_token": refresh_token,
    }

    resp = requests.post(
        token_endpoint,
        data=data,
        auth=(config.client_id, config.client_secret),
        timeout=10,
    )

    if not resp.ok:
        raise OAuth2TokenError(
            f"Yahoo token endpoint HTTP {resp.status_code}: {resp.text}"
        )

    payload = resp.json()
    if "access_token" not in payload:
        raise OAuth2TokenError(f"Yahoo token response error: {payload!r}")

    return payload


