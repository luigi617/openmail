from __future__ import annotations
import smtplib
import ssl
from dataclasses import dataclass
from typing import Sequence

from email_management import SMTPConfig
from email_management.errors import AuthError, ConfigError, SMTPError
from email_management.models import EmailMessage
from email_management.types import SendResult
from email_management.auth import AuthContext

from email_management.smtp.builder import build_mime_message

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

    def send(self, msg: EmailMessage) -> "SendResult":
        from_email = msg.from_email or self._from_email()
        if not msg.to and not msg.cc and not msg.bcc:
            raise ConfigError("No recipients")

        # create a copy with from filled (avoid mutating frozen dataclass)
        msg2 = EmailMessage(
            subject=msg.subject,
            from_email=from_email,
            to=msg.to,
            cc=msg.cc,
            bcc=msg.bcc,
            text=msg.text,
            html=msg.html,
            attachments=list(msg.attachments),
            date=msg.date,
            message_id=msg.message_id,
            headers=dict(msg.headers),
        )

        m = build_mime_message(msg2)
        recipients: Sequence[str] = list(msg2.to) + list(msg2.cc) + list(msg2.bcc)

        server = None
        try:
            server = self._connect()
            server.send_message(m, from_addr=from_email, to_addrs=list(recipients))
            return SendResult(ok=True, message_id=str(m["Message-ID"]))
        except smtplib.SMTPAuthenticationError as e:
            raise AuthError(f"SMTP auth failed: {e}") from e
        except smtplib.SMTPException as e:
            raise SMTPError(f"SMTP send failed: {e}") from e
        finally:
            if server is not None:
                try: server.quit()
                except Exception: pass

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