from __future__ import annotations
from dataclasses import dataclass, field
from email.message import EmailMessage as PyEmailMessage
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple, TypedDict


from email_management.assistants import (
    llm_classify_emails,
    llm_detect_phishing_for_email,
    llm_evaluate_sender_trust_for_email,
    llm_generate_follow_up_for_email,
    llm_concise_reply_for_email,
    llm_summarize_single_email,
    llm_summarize_many_emails,
    llm_easy_imap_query_from_nl,
    llm_reply_suggestions_for_email,
    llm_prioritize_emails,
    llm_summarize_thread_emails,
    llm_compose_email,
    llm_rewrite_email,
    llm_translate_email,
    llm_extract_tasks_from_emails,
    llm_summarize_attachments_for_email,
)
from email_management.email_manager import EmailManager
from email_management.email_query import EasyIMAPQuery
from email_management.models import EmailMessage, Task

@dataclass
class EmailAssistantProfile:
    """
    Generic profile for personalizing email behavior.
    Designed to be reusable across domains (CRM, helpdesk, etc.).
    """
    name: Optional[str] = None
    role: Optional[str] = None
    company: Optional[str] = None
    tone: Optional[str] = None          # e.g. "formal", "friendly", "concise"
    signature: Optional[str] = None     # default signature block
    locale: Optional[str] = None        # e.g. "en-US"
    extra_context: Optional[str] = None # free-form org / domain context

    def generate_prompt(self):
        """Convert profile dataclass fields into a structured prompt string."""
        parts = []
        if self.name:
            parts.append(f"You are {self.name}.")
        if self.role:
            parts.append(f"Your role is {self.role}.")
        if self.company:
            parts.append(f"You represent {self.company}.")
        if self.tone:
            parts.append(f"Use a {self.tone} tone.")
        if self.locale:
            parts.append(f"Locale: {self.locale}.")
        if self.extra_context:
            parts.append(f"Context: {self.extra_context}")

        return " ".join(parts).strip()
    
class EmailAssistant:

    def __init__(
        self,
        profile: Optional[EmailAssistantProfile] = None,
    ) -> None:
        self.profile = profile

    def generate_reply_suggestions(
        self,
        message: EmailMessage,
        *,
        provider: str,
        model_name: str,
    ) -> Tuple[List[str], Dict[str, Any]]:
        return llm_reply_suggestions_for_email(
            message,
            provider=provider,
            model_name=model_name,
        )
    
    def generate_reply(
        self,
        reply_context: str,
        message: EmailMessage,
        *,
        previous_reply: Optional[str] = None,
        provider: str,
        model_name: str,
    ) -> Tuple[str, Dict[str, Any]]:
        persona = self.profile.generate_prompt() if self.profile else ""
        enriched_context = f"{persona}\n\n{reply_context}".strip()

        return llm_concise_reply_for_email(
            enriched_context,
            message,
            provider=provider,
            model_name=model_name,
            previous_reply=previous_reply,
        )
    
    def summarize_email(
        self,
        message: EmailMessage,
        *,
        provider: str,
        model_name: str,
    ) -> Tuple[str, Dict[str, Any]]:
        return llm_summarize_single_email(
            message,
            provider=provider,
            model_name=model_name,
        )
    
    def summarize_multi_emails(
        self,
        messages: Sequence[EmailMessage],
        *,
        provider: str,
        model_name: str,
    ) -> Tuple[str, Dict[str, Any]]:
        
        if not messages:
            return "No emails selected.", {}

        return llm_summarize_many_emails(
            messages,
            provider=provider,
            model_name=model_name,
        )
    
    def summarize_thread(
        self,
        thread_messages: Sequence[EmailMessage],
        *,
        provider: str,
        model_name: str,
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Summarize an email conversation thread (ordered sequence of messages).
        Highlight key decisions, open questions, and next steps.
        """
        if not thread_messages:
            return "No emails in thread.", {}

        return llm_summarize_thread_emails(
            thread_messages,
            provider=provider,
            model_name=model_name,
        )
    
    def search_emails(
        self,
        user_request: str,
        *,
        provider: str,
        model_name: str,
        manager: EmailManager,
        mailbox: str = "INBOX",
    ) -> Tuple[EasyIMAPQuery, Dict[str, Any]]:
        """
        Turn a natural-language request like:
            "find unread security alerts from Google last week"
        into an EasyIMAPQuery + llm_call_info.
        """
        return llm_easy_imap_query_from_nl(
            user_request,
            provider=provider,
            model_name=model_name,
            manager=manager,
            mailbox=mailbox,
        )
    
    def classify_emails(
        self,
        messages: Sequence[EmailMessage],
        classes: Sequence[str],
        *,
        provider: str,
        model_name: str,
    ) -> Tuple[List[str], Dict[str, Any]]:
        """
        Classify multiple emails at once.
        """
        if not messages:
            return [], {}

        return llm_classify_emails(
            messages,
            classes=classes,
            provider=provider,
            model_name=model_name,
        )

    def prioritize_emails(
        self,
        messages: Sequence[EmailMessage],
        *,
        provider: str,
        model_name: str,
    ) -> Tuple[List[float], Dict[str, Any]]:
        """
        Assign a priority score to multiple emails at once.
        """
        if not messages:
            return [], {}

        return llm_prioritize_emails(
            messages,
            provider=provider,
            model_name=model_name,
        )

    def generate_follow_up(
        self,
        message: EmailMessage,
        *,
        provider: str,
        model_name: str,
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Generate a follow-up email to a previous message
        (e.g. when there was no response or action).
        """
        return llm_generate_follow_up_for_email(
            message,
            provider=provider,
            model_name=model_name,
        )

    def compose_email(
        self,
        instructions: str,
        *,
        provider: str,
        model_name: str,
    ) -> Tuple[str, str, Dict[str, Any]]:
        """
        Compose a new email (subject and body) from natural language instructions
        or bullet points.
        """
        persona = self.profile.generate_prompt() if self.profile else ""
        enriched_instructions = f"{persona}\n\n{instructions}".strip()

        return llm_compose_email(
            enriched_instructions,
            provider=provider,
            model_name=model_name,
        )
    
    def rewrite_email(
        self,
        draft_text: str,
        style: str,
        *,
        provider: str,
        model_name: str,
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Rewrite an email draft according to a requested style.
        """
        return llm_rewrite_email(
            draft_text,
            style,
            provider=provider,
            model_name=model_name,
        )

    def translate_email(
        self,
        text: str,
        target_language: str,
        *,
        provider: str,
        model_name: str,
        source_language: Optional[str] = None,
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Translate an email or arbitrary text into a target language.

        target_language: e.g. "en", "es", "fr-FR".
        source_language: optional; if None, LLM may auto-detect.
        """
        return llm_translate_email(
            text,
            target_language=target_language,
            source_language=source_language,
            provider=provider,
            model_name=model_name,
        )

    def extract_tasks(
        self,
        messages: Sequence[EmailMessage],
        *,
        provider: str,
        model_name: str,
    ) -> Tuple[List[Task], Dict[str, Any]]:
        """
        Extract action items / tasks from one or more emails, using a generic
        Task structure that can be mapped into different domains
        (task managers, CRMs, ticketing systems, etc.).
        """
        if not messages:
            return [], {}

        return llm_extract_tasks_from_emails(
            messages,
            provider=provider,
            model_name=model_name,
        )
    
    def summarize_attachments(
        self,
        message: EmailMessage,
        *,
        provider: str,
        model_name: str,
    ) -> Tuple[Dict[str, str], Dict[str, Any]]:
        """
        Summarize each attachment in an email.
        """
        return llm_summarize_attachments_for_email(
            message,
            provider=provider,
            model_name=model_name,
        )
    
    def detect_missing_attachment(self, message: PyEmailMessage) -> bool:
        """
        Heuristically detect if the email text implies an attachment
        should be present, but there is no actual attachment.
        """
        # 1) Check if there are any actual attachments.
        has_attachments = any(
            part.get_content_disposition() == "attachment"
            for part in message.iter_attachments()
        )

        if has_attachments:
            return False

        # 2) Extract a reasonable body representation.
        body_text = ""
        try:
            # Prefer text/plain, fall back to text/html if needed.
            payload = message.get_body(preferencelist=("plain", "html"))
            if payload is not None:
                body_text = payload.get_content() or ""
            else:
                # Fallback: some messages are simple / not multipart
                if message.get_content_type().startswith("text/"):
                    body_text = message.get_content() or ""
        except Exception:
            # Be robust to weird encodings / structures
            body_text = ""

        body_lower = body_text.lower()

        # 3) Look for common phrases that imply an attachment.
        trigger_phrases = [
            "see attached",
            "see the attached",
            "attached file",
            "attached document",
            "i've attached",
            "i have attached",
            "please find attached",
        ]

        mentions_attachment = any(phrase in body_lower for phrase in trigger_phrases)

        return mentions_attachment and not has_attachments

    def detect_phishing(
        self,
        message: EmailMessage,
        *,
        provider: str,
        model_name: str,
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Detect whether an email is likely to be a phishing attempt.
        """
        return llm_detect_phishing_for_email(
            message,
            provider=provider,
            model_name=model_name,
        )

    def evaluate_sender_trust(
        self,
        message: EmailMessage,
        *,
        provider: str,
        model_name: str,
    ) -> Tuple[float, Dict[str, Any]]:
        """
        Evaluate how trustworthy the sender looks based on:
        - email address / domain
        - content patterns
        - known orgs, signatures, etc.
        """
        return llm_evaluate_sender_trust_for_email(
            message,
            provider=provider,
            model_name=model_name,
        )