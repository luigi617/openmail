from email_management.assistants.reply import llm_concise_reply_for_email
from email_management.assistants.summary import llm_summarize_single_email
from email_management.assistants.summary_multi import llm_summarize_many_emails
from email_management.assistants.natural_language_query import llm_easy_imap_query_from_nl
from email_management.assistants.reply_suggestions import llm_reply_suggestions_for_email
from email_management.assistants.classify_emails import llm_classify_emails
from email_management.assistants.detect_phishing_for_email import llm_detect_phishing_for_email
from email_management.assistants.evaluate_sender_trust_for_email import llm_evaluate_sender_trust_for_email
from email_management.assistants.generate_follow_up_for_email import llm_generate_follow_up_for_email
from email_management.assistants.prioritize_emails import llm_prioritize_emails
from email_management.assistants.summarize_thread_emails import llm_summarize_thread_emails
from email_management.assistants.compose_email import llm_compose_email
from email_management.assistants.rewrite_email import llm_rewrite_email
from email_management.assistants.translate_email import llm_translate_email
from email_management.assistants.extract_tasks_from_emails import llm_extract_tasks_from_emails
from email_management.assistants.summarize_attachments_for_email import llm_summarize_attachments_for_email

__all__ = [
    "llm_concise_reply_for_email",
    "llm_summarize_single_email",
    "llm_summarize_many_emails",
    "llm_easy_imap_query_from_nl",
    "llm_reply_suggestions_for_email",
    "llm_classify_emails",
    "llm_detect_phishing_for_email",
    "llm_evaluate_sender_trust_for_email",
    "llm_generate_follow_up_for_email",
    "llm_prioritize_emails",
    "llm_summarize_thread_emails",
    "llm_compose_email",
    "llm_rewrite_email",
    "llm_translate_email",
    "llm_extract_tasks_from_emails",
    "llm_summarize_attachments_for_email",
]
