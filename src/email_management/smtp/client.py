from __future__ import annotations
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage as PyEmailMessage

from email_management import SMTPConfig
from email_management.errors import AuthError, ConfigError, SMTPError
from email_management.types import SendResult
from email_management.auth import AuthContext

@dataclass(frozen=True)
class SMTPClient:
    config: SMTPConfig

    @classmethod
    def from_config(cls, config: SMTPConfig) -> "SMTPClient":
        if not config.host:
            raise ConfigError("SMTP host required")
        if config.use_ssl and config.use_starttls:
            raise ConfigError("Choose use_ssl or use_starttls (not both)")
        return cls(config)

    def _from_email(self) -> str:
        if self.config.from_email:
            return self.config.from_email
        if self.config.username:
            return self.config.username
        raise ConfigError("No from_email and no username set")

    def send(self, msg: PyEmailMessage) -> "SendResult":
        # Ensure From is set
        from_email = msg.get("From")
        if not from_email:
            from_email = self._from_email()
            # Work on a copy so we don't mutate callers' object
            msg = msg.clone() if hasattr(msg, "clone") else msg.__class__(msg)
            msg["From"] = from_email

        # Ensure there is at least one recipient
        to_all = (
            msg.get_all("To", [])
            + msg.get_all("Cc", [])
            + msg.get_all("Bcc", [])
        )
        if not to_all:
            raise ConfigError("No recipients (To/Cc/Bcc are all empty)")

        server = None
        try:
            server = self._connect()
            # Let send_message derive recipients from headers
            server.send_message(msg, from_addr=from_email)
            return SendResult(ok=True, message_id=str(msg["Message-ID"]))
        except smtplib.SMTPAuthenticationError as e:
            raise AuthError(f"SMTP auth failed: {e}") from e
        except smtplib.SMTPException as e:
            raise SMTPError(f"SMTP send failed: {e}") from e
        finally:
            if server is not None:
                try:
                    server.quit()
                except Exception:
                    pass

    def _connect(self) -> smtplib.SMTP:
        cfg = self.config
        server: smtplib.SMTP

        try:
            if cfg.use_ssl:
                ctx = ssl.create_default_context()
                server = smtplib.SMTP_SSL(cfg.host, cfg.port, timeout=cfg.timeout, context=ctx)
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

            cfg.auth.apply_smtp(server, AuthContext(host=cfg.host, port=cfg.port))
            return server

        except smtplib.SMTPAuthenticationError as e:
            raise SMTPError(f"SMTP authentication failed: {e}") from e
        except smtplib.SMTPException as e:
            raise SMTPError(f"SMTP connection failed: {e}") from e
        except OSError as e:
            raise SMTPError(f"SMTP network error: {e}") from e
    
    def ping(self) -> None:
        """
        Minimal SMTP health check.
        Raises SMTPError if anything fails.
        """
        server = None
        try:
            server = self._connect()
            code, msg = server.noop()
            # RFC says 250 is OK for NOOP
            if code != 250:
                raise SMTPError(f"SMTP NOOP failed: {code} {msg!r}")
        except smtplib.SMTPAuthenticationError as e:
            raise AuthError(f"SMTP auth failed during ping: {e}") from e
        except smtplib.SMTPException as e:
            raise SMTPError(f"SMTP ping failed: {e}") from e
        except OSError as e:
            raise SMTPError(f"SMTP network error during ping: {e}") from e
        finally:
            if server is not None:
                try:
                    server.quit()
                except Exception:
                    pass