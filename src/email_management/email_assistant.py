from __future__ import annotations

from dataclasses import dataclass
from email.message import EmailMessage as PyEmailMessage
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple


from email_management.assistants import (
    llm_concise_reply_for_email,
    llm_summarize_single_email,
    llm_summarize_many_emails
)
from .email_query import EasyIMAPQuery
from email_management.models import UnsubscribeCandidate, EmailMessage, UnsubscribeActionResult
from email_management.subscription import SubscriptionService, SubscriptionDetector
from email_management.imap import IMAPClient
from email_management.smtp import SMTPClient
from email_management.types import EmailRef, SendResult
from email_management.utils import (ensure_reply_subject,
                                    get_header,
                                    parse_addrs,
                                    dedup_addrs,
                                    build_references,
                                    remove_addr)


SEEN = r"\Seen"
ANSWERED = r"\Answered"
FLAGGED = r"\Flagged"
DELETED = r"\Deleted"
DRAFT = r"\Draft"

@dataclass
class EmailAssistant:

    def generate_reply(
        self,
        message: EmailMessage,
        *,
        model_path: str,
    ) -> Tuple[str, Dict[str, Any]]:
        return llm_concise_reply_for_email(
            message,
            model_path=model_path,
        )
    
    def summarize_email(
        self,
        message: EmailMessage,
        *,
        model_path: str,
    ) -> Tuple[str, Dict[str, Any]]:
        return llm_summarize_single_email(
            message,
            model_path=model_path,
        )
    
    def summarize_multi_emails(
        self,
        messages: Sequence[EmailMessage],
        *,
        model_path: str,
    ) -> Tuple[str, Dict[str, Any]]:
        
        if not messages:
            return "No emails selected.", {}

        return llm_summarize_many_emails(
            messages,
            model_path=model_path,
        )