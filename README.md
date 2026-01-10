# Email-Manager

Lightweight Python toolkit for working with email via IMAP (read/search) and SMTP (send), with optional AI assistant features (summaries, reply templates, and more).  
Provides a simple high-level `EmailManager`, a flexible `EasyIMAPQuery` builder, and an `EmailAssistant` that wraps your LLM logic.

---

## Installation

Install from PyPI:

```
pip install email-management
```

---

## Features

- Base functionality via SMTP and IMAP (send, search, fetch)
- High-level `EmailManager` to coordinate IMAP/SMTP
- `EasyIMAPQuery` builder for composing IMAP queries in a fluent way
- Optional `EmailAssistant` for:
  - generating concise reply drafts
  - summarizing individual emails
  - summarizing multiple emails into one digest
- Designed to be minimal, testable, and framework-agnostic

---

## Core Concepts

### `EmailManager`

`EmailManager` coordinates the IMAP and SMTP layers.  
You create it once with the necessary clients/auth, then use it to send emails or navigate mailboxes.

---

### `EasyIMAPQuery`

`EasyIMAPQuery` is a query builder used to construct IMAP search expressions before executing them.  
It abstracts away raw IMAP tokens, letting you express filters more naturally, and only hits the server when you call a `search`/`fetch` method on it (via the manager).

---

### `EmailAssistant`

`EmailAssistant` is a thin wrapper around the LLM helpers in `email_management.assistants`.  
It gives you a clean entry point for AI-powered workflows such as:

- generating a concise reply draft for an `EmailMessage`
- summarizing a single email into a short description
- aggregating multiple emails into a prioritized digest (highlighting important ones)

You provide a `model_path` string that your LLM stack understands, and `EmailAssistant` calls into the underlying helpers accordingly.

---

## Example Usage

Initialize an `EmailManager` with your own IMAP/SMTP clients, and optionally an `EmailAssistant` for AI features:

```
from email_management.email_manager import EmailManager, EmailAssistant
from email_management.smtp import SMTPClient
from email_management.imap import IMAPClient
from email_management.auth import PasswordAuth, OAuth2Auth
from email_management.models import EmailMessage

# Password Authentication
# Use when your provider allows direct username/password IMAP and SMTP login.
auth = PasswordAuth(username="you@example.com", password="secret")

# Or use OAuth2Auth (e.g. Gmail/Outlook with OAuth tokens).
# def token_provider():
#     # Must return a fresh OAuth2 access token string
#     return get_access_token_somehow()
# auth = OAuth2Auth(username="you@example.com", token_provider=token_provider)

smtp = SMTPClient(host="smtp.example.com", port=587, auth=auth)
imap = IMAPClient(host="imap.example.com", port=993, auth=auth)

mgr = EmailManager(imap=imap, smtp=smtp)
assistant = EmailAssistant()

# Example: summarize a single email (EmailMessage is your parsed message model)
some_email: EmailMessage = ...
summary, meta = assistant.summarize_email(
    message=some_email,
    model_path="your/model/path",
)

# Example: generate a reply suggestion
reply_text, meta = assistant.generate_reply(
    message=some_email,
    model_path="your/model/path",
)
```

Now you can use:

- `mgr` to send/browse email and build queries (via `EasyIMAPQuery`)
- `assistant` to plug in your LLM backend for summaries and reply drafts

---

## License

MIT
