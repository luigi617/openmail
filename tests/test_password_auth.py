import pytest

from openmail.auth import PasswordAuth
from openmail.errors import AuthError


class DummySMTPServer:
    def __init__(self, should_fail: bool = False):
        self.should_fail = should_fail
        self.logged_in_with = None

    def login(self, username, password):
        self.logged_in_with = (username, password)
        if self.should_fail:
            raise Exception("Invalid SMTP credentials")


class DummyIMAPConn:
    def __init__(self, mode: str = "ok"):
        """
        mode:
          - "ok": login succeeds and returns ("OK", _)
          - "no": login returns non-OK typ
          - "error": login raises an exception
        """
        self.mode = mode
        self.logged_in_with = None

    def login(self, username, password):
        self.logged_in_with = (username, password)
        if self.mode == "ok":
            return "OK", [b"logged in"]
        if self.mode == "no":
            return "NO", [b"bad credentials"]
        if self.mode == "error":
            raise Exception("IMAP login error")
        return "OK", [b"default"]


def test_password_auth_with_correct_info():
    username = "test@example.com"
    password = "correct-password"

    auth = PasswordAuth(
        username=username,
        password=password,
    )

    smtp_server = DummySMTPServer(should_fail=False)
    imap_conn = DummyIMAPConn(mode="ok")

    # Should not raise
    auth.apply_smtp(smtp_server, ctx=None)
    auth.apply_imap(imap_conn, ctx=None)

    assert smtp_server.logged_in_with == (username, password)
    assert imap_conn.logged_in_with == (username, password)


def test_password_auth_with_wrong_password():
    username = "test@example.com"
    password = "1234567890"

    auth = PasswordAuth(
        username=username,
        password=password,
    )

    # For SMTP, simulate the underlying server raising an error
    smtp_server = DummySMTPServer(should_fail=True)
    # For IMAP, simulate a non-OK response
    imap_conn = DummyIMAPConn(mode="no")

    with pytest.raises(AuthError, match="SMTP login failed"):
        auth.apply_smtp(smtp_server, ctx=None)

    with pytest.raises(AuthError, match="IMAP login failed"):
        auth.apply_imap(imap_conn, ctx=None)


def test_password_auth_with_wrong_username():
    username = "test@gmail.com"
    password = "correct-password"

    auth = PasswordAuth(
        username=username,
        password=password,
    )

    # For SMTP, simulate the server rejecting username
    smtp_server = DummySMTPServer(should_fail=True)
    # For IMAP, simulate an exception during login
    imap_conn = DummyIMAPConn(mode="error")

    with pytest.raises(AuthError, match="SMTP login failed"):
        auth.apply_smtp(smtp_server, ctx=None)

    with pytest.raises(AuthError, match="IMAP login failed"):
        auth.apply_imap(imap_conn, ctx=None)
