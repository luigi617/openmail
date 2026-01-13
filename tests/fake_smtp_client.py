from __future__ import annotations

from dataclasses import dataclass, field
from email.message import EmailMessage as PyEmailMessage
from email.utils import make_msgid
from typing import List, Optional

from email_management.types import SendResult
from email_management.errors import ConfigError, SMTPError


@dataclass
class SentEmailRecord:
    """
    Stored info about one sent email, for assertions in tests.
    """
    msg: PyEmailMessage
    from_email: str
    recipients: List[str]


@dataclass
class FakeSMTPClient:
    """
    In-memory fake SMTP client for pytest.

    - Does NOT talk to a real SMTP server.
    - Captures all sent messages in `sent`.
    - Exposes `send(msg)` and `ping()` like the real SMTPClient.
    """

    # You can pass a real SMTPConfig, a stub, or None in tests.
    config: Optional[object] = None

    # Collected sent emails
    sent: List[SentEmailRecord] = field(default_factory=list)

    # If True, the next send() or ping() will raise SMTPError
    fail_next: bool = False

    # ------------- internal helpers -------------

    def _maybe_fail(self) -> None:
        if self.fail_next:
            self.fail_next = False
            raise SMTPError("FakeSMTPClient forced failure")

    def _from_email(self, msg: PyEmailMessage) -> str:
        """
        Mirror real behavior roughly:
        - Use msg["From"] if present
        - Else, try config.from_email or config.username
        - Else, raise ConfigError
        """
        from_email = msg.get("From")
        if from_email:
            return from_email

        cfg = self.config
        if cfg is not None:
            if getattr(cfg, "from_email", None):
                return cfg.from_email
            if getattr(cfg, "username", None):
                return cfg.username

        raise ConfigError("FakeSMTPClient: no From header and no config.from_email/username")

    def _ensure_message_id(self, msg: PyEmailMessage) -> None:
        if msg.get("Message-ID") is None:
            msg["Message-ID"] = make_msgid()

    # ------------- public API -------------

    def send(self, msg: PyEmailMessage) -> SendResult:
        """
        Fake send:
        - Validates From / recipients.
        - Optionally fails if fail_next is True.
        - Records the message in `sent`.
        - Returns SendResult(ok=True, message_id=...).
        """
        self._maybe_fail()

        from_email = self._from_email(msg)

        # Collect all recipients like the real implementation does
        to_all = (
            msg.get_all("To", [])
            + msg.get_all("Cc", [])
            + msg.get_all("Bcc", [])
        )
        if not to_all:
            raise ConfigError("FakeSMTPClient: No recipients (To/Cc/Bcc are all empty)")

        # Ensure we have a Message-ID
        self._ensure_message_id(msg)

        # Record the send
        record = SentEmailRecord(
            msg=msg,
            from_email=from_email,
            recipients=to_all,
        )
        self.sent.append(record)

        return SendResult(
            ok=True,
            message_id=str(msg["Message-ID"]),
            detail="fake-send-ok",
        )

    def ping(self) -> None:
        """
        Fake ping used by EmailManager.health_check().
        Raises SMTPError if fail_next is True.
        Otherwise, it's a no-op.
        """
        self._maybe_fail()
