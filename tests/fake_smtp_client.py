from __future__ import annotations

import copy
from dataclasses import dataclass, field
from email.message import EmailMessage as PyEmailMessage
from email.utils import make_msgid, parseaddr
from typing import Iterable, List, Optional, Sequence

from email_management.errors import ConfigError, SMTPError
from email_management.types import SendResult


@dataclass
class SentEmailRecord:
    """
    Stored info about one sent email, for assertions in tests.
    Mirrors what SMTPClient actually sends: (final message, from_email, recipients).
    """
    msg: PyEmailMessage
    from_email: str
    recipients: List[str]


@dataclass
class FakeSMTPClient:
    """
    In-memory fake SMTP client for tests, aligned with current SMTPClient.

    - Public API compatibility:
        - send(msg, recipients)
        - send_many(batch)
        - ping(), close()
        - context manager
    - Behaviors mirrored:
        - requires explicit recipients argument(s)
        - From header handling + config.from_email fallback
        - deepcopy message when injecting From
        - ensures Message-ID exists
        - max_messages_per_connection rotation semantics (simulated)
    """

    # Can be real SMTPConfig, stub, or None in tests.
    config: Optional[object] = None

    sent: List[SentEmailRecord] = field(default_factory=list)

    fail_next: bool = False

    # Mirrors SMTPClient defaults/fields
    max_messages_per_connection: int = 100

    # simulated "connection" state
    _connected: bool = field(default=False, init=False, repr=False)
    _sent_since_connect: int = field(default=0, init=False, repr=False)

    # ------------- internal helpers -------------

    def _maybe_fail(self) -> None:
        if self.fail_next:
            self.fail_next = False
            raise SMTPError("FakeSMTPClient forced failure")

    def _from_email(self) -> str:
        cfg = self.config
        if cfg is not None and getattr(cfg, "from_email", None):
            return str(getattr(cfg, "from_email"))
        raise ConfigError("No from_email set")

    def _ensure_connected(self) -> None:
        # Real client lazily connects; we simulate that state.
        if not self._connected:
            self._connected = True
            self._sent_since_connect = 0

    def _reset_connection(self) -> None:
        self._connected = False
        self._sent_since_connect = 0

    def _ensure_message_id(self, msg: PyEmailMessage) -> None:
        if msg.get("Message-ID") is None:
            msg["Message-ID"] = make_msgid()

    def _prepare_from_and_msg(self, msg: PyEmailMessage) -> tuple[PyEmailMessage, str]:
        """
        Mirrors SMTPClient.send()/send_many() behavior:

        - If "From" exists:
            parseaddr; if parsed email empty -> fallback to config.from_email
            do NOT deepcopy; message left as-is.
        - If "From" missing:
            from_email := config.from_email (required)
            deepcopy msg and inject From header
        """
        hdr_from = msg.get("From")
        if hdr_from:
            _, from_email = parseaddr(hdr_from)
            if not from_email:
                from_email = self._from_email()
            return msg, from_email

        from_email = self._from_email()
        final_msg = copy.deepcopy(msg)
        final_msg["From"] = from_email
        return final_msg, from_email

    def _record_send(self, msg: PyEmailMessage, from_email: str, recipients: List[str]) -> SendResult:
        self._ensure_message_id(msg)
        self.sent.append(SentEmailRecord(msg=msg, from_email=from_email, recipients=recipients))
        self._sent_since_connect += 1

        # Simulate the real client's rotation behavior
        if self._sent_since_connect >= self.max_messages_per_connection:
            self._reset_connection()

        return SendResult(ok=True, message_id=str(msg["Message-ID"]))

    # ------------- public API -------------

    @classmethod
    def from_config(cls, config: object) -> "FakeSMTPClient":
        """
        Parity with SMTPClient.from_config for tests that use it.
        We keep validation minimal but consistent where it matters for unit tests.
        """
        # Current SMTPClient validates host and ssl/starttls mutual exclusion;
        # tests typically don't rely on these for the fake, but keeping a light check is fine.
        if config is None:
            raise ConfigError("SMTP config required")
        return cls(config=config)

    def send(self, msg: PyEmailMessage, recipients: List[str]) -> SendResult:
        """
        Matches SMTPClient.send signature and validation:
          - recipients must be provided and non-empty
          - determines from_email from header or config
          - injects From if missing (deepcopy)
          - ensures Message-ID
          - records send
        """
        self._maybe_fail()

        if not recipients:
            raise ConfigError("send(): recipients list is empty")

        self._ensure_connected()

        final_msg, from_email = self._prepare_from_and_msg(msg)
        return self._record_send(final_msg, from_email, list(recipients))

    def send_many(self, batch: Iterable[tuple[PyEmailMessage, Iterable[str]]]) -> List[SendResult]:
        """
        Matches SMTPClient.send_many(batch):
          - validates each message has recipients
          - applies From logic per message (deepcopy only when injecting)
          - records sends, keeps one simulated connection
        """
        self._maybe_fail()
        self._ensure_connected()

        prepared: List[tuple[PyEmailMessage, str, List[str]]] = []
        for msg, rcpts_iter in batch:
            rcpts = list(rcpts_iter)
            if not rcpts:
                raise ConfigError("send_many(): one of the messages has no recipients")

            final_msg, from_email = self._prepare_from_and_msg(msg)
            prepared.append((final_msg, from_email, rcpts))

        results: List[SendResult] = []
        for final_msg, from_email, rcpts in prepared:
            # mirror real: if we hit rotation threshold mid-batch, the real client resets and continues
            if not self._connected:
                self._ensure_connected()
            results.append(self._record_send(final_msg, from_email, rcpts))

        return results

    def ping(self) -> None:
        """
        Minimal SMTP health check.
        Real client uses NOOP and checks 250; here it's just a failpoint + connect simulation.
        """
        self._maybe_fail()
        self._ensure_connected()
        # no-op

    def close(self) -> None:
        """
        Matches SMTPClient.close() shape.
        """
        self._maybe_fail()
        self._reset_connection()

    def __enter__(self) -> "FakeSMTPClient":
        # lazy connect like real client
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()
