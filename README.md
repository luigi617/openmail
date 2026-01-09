# email-manager

Lightweight Python toolkit for working with email via IMAP (read/search) and SMTP (send).  
Provides a simple high-level `EmailManager` plus a flexible `EasyIMAPQuery` builder for composing IMAP queries without worrying about low-level protocol details.

---

## Installation

Install from PyPI:

```
pip install email-manager
```

---

## Features

- Base functionality via SMTP and IMAP (sends, search, fetch)
- Compose IMAP queries using a compact builder pattern  
- Designed to be minimal, testable, and framework-agnostic  
- Supports AI assistants (e.g., automated summaries, reply templates, and more upcoming)

---

## Core Concepts

### `EmailManager`

`EmailManager` coordinates the IMAP and SMTP layers.  
You create it once with the necessary clients/auth, then use it to send emails or navigate mailboxes.


---

### `EasyIMAPQuery`

`EasyIMAPQuery` is a query builder used to construct IMAP search expressions before executing them.  
It abstracts away raw IMAP tokens, letting you express filters more naturally, and only hits the server when you call a search/fetch method on it (from the manager).


---

## Example Usage

Initialize an `EmailManager` with your own IMAP/SMTP clients:

```
from email_management.email_manager import EmailManager
from email_management.smtp import SMTPClient
from email_management.imap import IMAPClient

# Password Authentication
# Use when your provider allows direct username/password IMAP and SMTP login.
from email_management.auth import PasswordAuth
auth = PasswordAuth(username="you@example.com", password="secret")

# or use OAuth2Auth
# Use for providers like Gmail or Outlook where SMTP/IMAP require OAuth tokens.
# from email_management.auth import OAuth2Auth
# def token_provider():
#     # Must return a fresh OAuth2 access token string
#     return get_access_token_somehow()

auth = OAuth2Auth(username="you@example.com", token_provider=token_provider)

smtp = SMTPClient(host="smtp.example.com", port=587, auth=auth)
imap = IMAPClient(host="imap.example.com", port=993, auth=auth)

mgr = EmailManager(imap=imap, smtp=smtp)
```

Now you can use `mgr` wherever you need to send or browse email.

---

## License

MIT
