import base64
from typing import Callable

import pytest

from openmail.auth import OAuth2Auth
from openmail.errors import AuthError


class FakeIMAPConnection:
    """
    Minimal IMAP-like object implementing .authenticate(mechanism, callback)
    so we can test OAuth2Auth.apply_imap without real network.
    """

    def __init__(self, response_type="OK", response_data=None):
        self.response_type = response_type
        self.response_data = response_data or [b"OK"]
        self.calls = []

    def authenticate(self, mechanism: str, auth_cb: Callable[[bytes], bytes]):
        self.calls.append((mechanism, auth_cb))

        auth_bytes = auth_cb(None)
        assert isinstance(auth_bytes, (bytes, bytearray))

        return self.response_type, self.response_data


class FakeSMTPServer:
    """
    Minimal SMTP-like object implementing .docmd(command, arg)
    so we can test OAuth2Auth.apply_smtp without real network.
    """

    def __init__(self, code=235, resp=b"2.7.0 Accepted"):
        self.code = code
        self.resp = resp
        self.calls = []

    def docmd(self, command: str, arg: str):
        self.calls.append((command, arg))
        return self.code, self.resp



def make_token_provider(value: str):
    def provider() -> str:
        return value
    return provider


def make_raising_provider(exc: Exception):
    def provider() -> str:
        raise exc
    return provider



def test_imap_success():
    auth = OAuth2Auth(
        username="user@example.com",
        token_provider=make_token_provider("access-token-123"),
    )
    conn = FakeIMAPConnection(response_type="OK")

    # ctx is unused by OAuth2Auth, so we can pass None
    auth.apply_imap(conn, ctx=None)

    # sanity check: authenticate was called correctly
    assert len(conn.calls) == 1
    mechanism, cb = conn.calls[0]
    assert mechanism == "XOAUTH2"

    xoauth_bytes = cb(None)
    assert b"user=user@example.com" in xoauth_bytes
    assert b"auth=Bearer access-token-123" in xoauth_bytes


def test_imap_failure_when_server_rejects():
    auth = OAuth2Auth(
        username="user@example.com",
        token_provider=make_token_provider("access-token-123"),
    )
    # IMAP returns non-OK -> should raise AuthError
    conn = FakeIMAPConnection(response_type="NO", response_data=[b"AUTH failed"])

    with pytest.raises(AuthError) as excinfo:
        auth.apply_imap(conn, ctx=None)

    msg = str(excinfo.value)
    assert "IMAP XOAUTH2 auth failed (non-OK response" in msg


def test_imap_failure_when_token_empty():
    auth = OAuth2Auth(
        username="user@example.com",
        token_provider=make_token_provider(""),
    )
    conn = FakeIMAPConnection(response_type="OK")

    with pytest.raises(AuthError) as excinfo:
        auth.apply_imap(conn, ctx=None)

    assert "token provider returned empty token" in str(excinfo.value)


def test_imap_failure_when_provider_raises():
    auth = OAuth2Auth(
        username="user@example.com",
        token_provider=make_raising_provider(RuntimeError("boom")),
    )
    conn = FakeIMAPConnection(response_type="OK")

    with pytest.raises(AuthError) as excinfo:
        auth.apply_imap(conn, ctx=None)

    # The original exception should be wrapped
    assert "IMAP XOAUTH2 auth failed:" in str(excinfo.value)
    assert "boom" in str(excinfo.value)



def test_smtp_success():
    auth = OAuth2Auth(
        username="user@example.com",
        token_provider=make_token_provider("access-token-456"),
    )
    server = FakeSMTPServer(code=235, resp=b"2.7.0 Accepted")

    auth.apply_smtp(server, ctx=None)

    # sanity check: AUTH XOAUTH2 was called with a base64 payload
    assert len(server.calls) == 1
    command, arg = server.calls[0]
    assert command == "AUTH"
    assert arg.startswith("XOAUTH2 ")

    b64_part = arg.split(" ", 1)[1]
    raw = base64.b64decode(b64_part.encode("ascii")).decode("utf-8")
    assert "user=user@example.com" in raw
    assert "auth=Bearer access-token-456" in raw


def test_smtp_failure_on_non_235_code():
    auth = OAuth2Auth(
        username="user@example.com",
        token_provider=make_token_provider("some-token"),
    )
    # Non-235 status code -> should raise AuthError
    server = FakeSMTPServer(code=535, resp=b"5.7.8 Authentication Failed")

    with pytest.raises(AuthError) as excinfo:
        auth.apply_smtp(server, ctx=None)

    msg = str(excinfo.value)
    assert "SMTP XOAUTH2 auth failed: 535" in msg
    assert "Authentication Failed" in msg


def test_smtp_failure_when_token_empty():
    auth = OAuth2Auth(
        username="user@example.com",
        token_provider=make_token_provider(""),
    )
    server = FakeSMTPServer()

    with pytest.raises(AuthError) as excinfo:
        auth.apply_smtp(server, ctx=None)

    assert "token provider returned empty token" in str(excinfo.value)


def test_smtp_failure_when_provider_raises():
    auth = OAuth2Auth(
        username="user@example.com",
        token_provider=make_raising_provider(RuntimeError("kaboom")),
    )
    server = FakeSMTPServer()

    with pytest.raises(AuthError) as excinfo:
        auth.apply_smtp(server, ctx=None)

    assert "SMTP XOAUTH2 auth failed:" in str(excinfo.value)
    assert "kaboom" in str(excinfo.value)
