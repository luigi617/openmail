from __future__ import annotations

import copy
import smtplib
import ssl
import threading
from dataclasses import dataclass, field
from email.message import EmailMessage as PyEmailMessage
from email.utils import parseaddr
from typing import Iterable, List

from openmail import SMTPConfig
from openmail.auth import AuthContext
from openmail.errors import AuthError, ConfigError, SMTPError
from openmail.types import SendResult


@dataclass
class SMTPClient:
    config: SMTPConfig
    _server: smtplib.SMTP | None = field(default=None, init=False, repr=False)
    _lock: threading.RLock = field(default_factory=threading.RLock, init=False, repr=False)
    _sent_since_connect: int = field(default=0, init=False, repr=False)

    max_messages_per_connection: int = 100

    @classmethod
    def from_config(cls, config: SMTPConfig) -> SMTPClient:
        if not config.host:
            raise ConfigError("SMTP host required")
        if config.use_ssl and config.use_starttls:
            raise ConfigError("Choose use_ssl or use_starttls (not both)")
        return cls(config)


    def _from_email(self) -> str:
        if self.config.from_email:
            return self.config.from_email
        raise ConfigError("No from_email set")

    def _open_new_server(self) -> smtplib.SMTP:
        cfg = self.config
        try:
            if cfg.use_ssl:
                ctx = ssl.create_default_context()
                server = smtplib.SMTP_SSL(
                    cfg.host, cfg.port, timeout=cfg.timeout, context=ctx
                )
                server.ehlo()
            else:
                server = smtplib.SMTP(cfg.host, cfg.port, timeout=cfg.timeout)
                server.ehlo()
                if cfg.use_starttls:
                    ctx = ssl.create_default_context()
                    server.starttls(context=ctx)
                    server.ehlo()

            if cfg.auth is None:
                raise ConfigError("SMTPConfig.auth is required (PasswordAuth or OAuth2Auth)")

            try:
                cfg.auth.apply_smtp(server, AuthContext(host=cfg.host, port=cfg.port))
            except smtplib.SMTPAuthenticationError as e:
                try:
                    server.quit()
                except Exception:
                    pass
                raise AuthError(f"SMTP auth failed: {e}") from e
            
            self._sent_since_connect = 0

            return server

        except AuthError:
            raise
        except smtplib.SMTPException as e:
            raise SMTPError(f"SMTP connection failed: {e}") from e
        except OSError as e:
            raise SMTPError(f"SMTP network error: {e}") from e

    def _get_server(self) -> smtplib.SMTP:
        # Must be called with self._lock held
        if self._server is not None:
            return self._server
        self._server = self._open_new_server()
        return self._server

    def _reset_server(self) -> None:
        # Must be called with self._lock held
        if self._server is not None:
            try:
                self._server.quit()
            except Exception:
                pass
        self._server = None
        self._sent_since_connect = 0

    def _run_with_server(self, op):
        """
        Run an operation with a server, handling:
        - thread-safety (RLock)
        - reconnect-on-disconnect (retry once)

        `op` is a callable taking a single `smtplib.SMTP` argument.
        """
        last_exc: BaseException | None = None

        for _ in range(2):
            with self._lock:
                server = self._get_server()
                try:
                    result = op(server)
                    if self._sent_since_connect >= self.max_messages_per_connection:
                        self._reset_server()
                    return result
                except smtplib.SMTPServerDisconnected as e:
                    # Connection dropped; reset and retry with a fresh one.
                    last_exc = e
                    self._reset_server()
                except AuthError:
                    raise
                except smtplib.SMTPException as e:
                    raise SMTPError(f"SMTP operation failed: {e}") from e

        # If we get here, we had repeated disconnects
        raise SMTPError(f"SMTP connection repeatedly disconnected: {last_exc}") from last_exc

    def _send_with_known_server(self, server: smtplib.SMTP, msg: PyEmailMessage, from_email: str, recipients: list[str]) -> SendResult:
        try:
            server.send_message(msg, from_addr=from_email, to_addrs=recipients)
        except smtplib.SMTPAuthenticationError as e:
            raise AuthError(f"SMTP auth failed during send: {e}") from e

        self._sent_since_connect += 1
        return SendResult(ok=True, message_id=str(msg["Message-ID"]))

    def send(self, msg: PyEmailMessage, recipients: List[str]) -> SendResult:
        if not recipients:
            raise ConfigError("send(): recipients list is empty")
        
        hdr_from = msg.get("From")
        if hdr_from:
            _, from_email = parseaddr(hdr_from)
            if not from_email:
                from_email = self._from_email()
        else:
            from_email = self._from_email()
            # keep the message self-consistent for debugging/logging
            msg = copy.deepcopy(msg)
            msg["From"] = from_email

        def _impl(server: smtplib.SMTP) -> SendResult:
            return self._send_with_known_server(server, msg, from_email, recipients)

        return self._run_with_server(_impl)
    
    def send_many(self, batch: Iterable[tuple[PyEmailMessage, Iterable[str]]]) -> list[SendResult]:

        """
        Send multiple messages in a single (or minimal) SMTP session.
        """
        prepared: list[tuple[PyEmailMessage, str, list[str]]] = []

        for msg, rcpts_iter in batch:
            rcpts = list(rcpts_iter)
            if not rcpts:
                raise ConfigError("send_many(): one of the messages has no recipients")

            hdr_from = msg.get("From")
            if hdr_from:
                _, from_email = parseaddr(hdr_from)
                if not from_email:
                    from_email = self._from_email()
                final_msg = msg
            else:
                from_email = self._from_email()
                final_msg = copy.deepcopy(msg)
                final_msg["From"] = from_email

            prepared.append((final_msg, from_email, rcpts))

        results: list[SendResult] = []
        i = 0

        def _impl(server: smtplib.SMTP) -> list[SendResult]:
            nonlocal i, results
            while i < len(prepared):
                msg, from_email, recipients = prepared[i]
                res = self._send_with_known_server(server, msg, from_email, recipients)
                results.append(res)
                i += 1
            return results

        return self._run_with_server(_impl)

    def ping(self) -> None:
        """
        Minimal SMTP health check.
        """
        def _impl(server: smtplib.SMTP) -> None:
            try:
                code, reply = server.noop()
            except smtplib.SMTPAuthenticationError as e:
                raise AuthError(f"SMTP auth failed during ping: {e}") from e
            if code != 250:
                raise SMTPError(f"SMTP NOOP failed: {code} {reply!r}")

        self._run_with_server(_impl)

    def close(self) -> None:
        with self._lock:
            self._reset_server()

    def __enter__(self) -> SMTPClient:
        # lazy connect;
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()
