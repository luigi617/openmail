# Email-Manager

Lightweight Python toolkit for working with email via IMAP (read/search) and SMTP (send), with optional LLM-enhanced workflows such as summarization, prioritization, task extraction, reply assistance, and MUCH MORE!

Email-Manager provides a clean separation of concerns between:
- transport (IMAP/SMTP)
- query building
- assistant logic

---

## 📦 Installation

```
pip install email-management
```

---

## ✨ Features

- IMAP + SMTP high-level convenience via `EmailManager`
- Fluent IMAP builder via `EmailQuery`
- Natural-language IMAP queries, email summarization, reply assistant, email analysis...

---

## 🧱 Core Components

| Component | Responsibility |
|---|---|
| **EmailManager** | Coordinates SMTP & IMAP, handles sending, replying, forwarding, inbox triage |
| **EmailQuery** | Fluent IMAP builder with optional NL search |
| **EmailAssistant** | LLM entry point for summary, reply, task extraction, classification, etc. |

Detailed component documentation is provided in:
- [`docs/EmailAssistant.md`](docs/EmailAssistant.md)
- [`docs/EmailManager.md`](docs/EmailManager.md)
- [`docs/EmailQuery.md`](docs/EmailQuery.md)

---

## 🔧 Quick Start Example

```
from email_management.smtp import SMTPClient
from email_management.imap import IMAPClient
from email_management.auth import PasswordAuth
from email_management import EmailManager, EmailAssistant, EmailAssistantProfile

# Password Authentication
auth = PasswordAuth(username="you@example.com", password="secret_app_password")

# Or use OAuth2Auth (e.g. Gmail/Outlook with OAuth tokens).
# def token_provider():
#     # Must return a fresh OAuth2 access token string
#     return get_access_token_somehow()
# auth = OAuth2Auth(username="you@example.com", token_provider=token_provider)

imap = IMAPClient(host="imap.example.com", port=993, auth=auth)
smtp = SMTPClient(host="smtp.example.com", port=587, auth=auth)

mgr = EmailManager(imap=imap, smtp=smtp)

profile = EmailAssistantProfile(
    name="Alex",
    role="Support Engineer",
    company="ExampleCorp",
    tone="friendly",
)

assistant = EmailAssistant(profile=profile)
```

---

## 📨 Searching & Fetching Email

IMAP operations can be performed directly:

```
msgs = mgr.fetch_latest(unseen_only=True, n=20)
```

Or via fluent IMAP builder:

```
q = mgr.imap_query().from_any("alerts@example.com").recent_unread(3)
msgs = q.fetch()
```

Natural-language searches are also supported:

```
query, info = assistant.search_emails(
    "find unread security alerts from Google last week",
    provider="openai",
    model_name="gpt-4.1",
    manager=mgr,
)
msgs = query.fetch()
```

---

## 🤖 Summarization, Classification & Replies

```
summary, meta = assistant.summarize_email(
    message=msgs[0],
    provider="openai",
    model_name="gpt-4.1",
)

reply_text, meta = assistant.generate_reply(
    reply_context="Confirm resolution and next steps",
    message=msgs[0],
    provider="openai",
    model_name="gpt-4.1",
)
```

Utility tasks include:
- `prioritize_emails()`
- `classify_emails()`
- `generate_follow_up()`
- `extract_tasks()`
- `summarize_thread()`
- `detect_phishing()`
- `evaluate_sender_trust()`

---

## 🧰 EmailManager Overview

Supports:
- Sending & composing
- Drafts
- Reply / Reply-all
- Forwarding
- Folder operations (move, copy, delete)
- Flag operations (seen, answered, flagged, etc.)
- Thread fetching
- Unsubscribe helpers
- Health checks

Example:

```
mgr.reply(
    original=msgs[0],
    body="Thanks! We'll follow up shortly.",
)
```

---

## 🗂 Documentation Structure

This README covers overall usage. Focused guides are in:

- [`docs/EmailAssistant.md`](docs/EmailAssistant.md)
- [`docs/EmailManager.md`](docs/EmailManager.md)
- [`docs/EmailQuery.md`](docs/EmailQuery.md)

---

## 🪪 License

MIT
