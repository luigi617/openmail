# EmailManager

`EmailManager` coordinates IMAP and SMTP so you can **send, fetch, reply, forward, move, and triage emails** through a single high-level API.

It wraps:

- `SMTPClient` (sending mail)
- `IMAPClient` (reading/searching mail)
- `EasyIMAPQuery` (fluent IMAP query builder)

---

## Creating an EmailManager

```
from email_management.smtp import SMTPClient
from email_management.imap import IMAPClient
from email_management.auth import PasswordAuth

from email_manager import EmailManager

auth = PasswordAuth(username="you@example.com", password="secret")

smtp = SMTPClient(host="smtp.example.com", port=587, auth=auth)
imap = IMAPClient(host="imap.example.com", port=993, auth=auth)

mgr = EmailManager(smtp=smtp, imap=imap)
```

You can also use OAuth-based auth if your provider requires it.

```
def token_provider():
    # Must return a fresh OAuth2 access token string
    return get_access_token_somehow()
auth = OAuth2Auth(username="you@example.com", token_provider=token_provider)
```

---

## Composing & Sending Email

### Compose only

Use `compose()` when you want a `EmailMessage` (from stdlib `email.message.EmailMessage`) you can store or inspect:

```
msg = mgr.compose(
    subject="Welcome!",
    to=["user@example.com"],
    from_addr="me@example.com",
    text="Thanks for signing up.",
)
```

### Compose and send

`compose_and_send()` builds and sends in one step:

```
result = mgr.compose_and_send(
    subject="Daily report",
    to=["boss@example.com"],
    from_addr="me@example.com",
    text="Here is the report...",
)
```

### Scheduled sending (build now, send later)

`send_later()` builds a message tagged with `X-Scheduled-At` which you can enqueue in your own scheduler:

```
from datetime import datetime, timedelta

msg = mgr.send_later(
    subject="Reminder",
    to=["user@example.com"],
    from_addr="me@example.com",
    text="Just checking in.",
    scheduled_at=datetime.utcnow() + timedelta(hours=2),
)

# later in your scheduler:
mgr.send(msg)
```

---

## Drafts

Save a draft into an IMAP mailbox (default `"Drafts"`):

```
ref = mgr.save_draft(
    subject="Draft email",
    to=["user@example.com"],
    from_addr="me@example.com",
    text="I'll finish this later.",
)
```

You can later fetch by `EmailRef` using `imap.fetch(...)` (via `IMAPClient`) if needed.

---

## Replies & Forwarding

### Reply

Reply to the sender (or `Reply-To` if present):

```
mgr.reply(
    original=email_msg,         # EmailMessage model
    body="Thanks for the update.",
    from_addr="me@example.com", # optional
    quote_original=True,        # include quoted original body
)
```

- Automatically sets `Subject` as `Re: ...` if needed  
- Uses `Reply-To` or `From` from the original  
- Sets `In-Reply-To` and `References` for threading

### Reply all

```
mgr.reply_all(
    original=email_msg,
    body="Looping everyone in.",
    from_addr="me@example.com",
    quote_original=True,
)
```

- Sends to main recipient and copies everyone from original `To` / `Cc`, excluding yourself and duplicates.

### Forward

```
mgr.forward(
    original=email_msg,
    to=["other@example.com"],
    body="FYI.",
    from_addr="me@example.com",
    include_attachments=True,
)
```

Forward builds a new message summarizing headers and body, with optional attachments.

---

## Fetching Email

### Quick inbox overview

`fetch_overview()` is good for list views / previews:

```
overview = mgr.fetch_overview(
    mailbox="INBOX",
    n=50,
    preview_bytes=1024,
)
```

Returns a list of lightweight `EmailOverview` objects (subject/from/preview).

### Latest messages

```
msgs = mgr.fetch_latest(
    mailbox="INBOX",
    n=50,
    unseen_only=True,
    include_attachments=False,
)
```

Use `unseen_only=True` for basic triage, and `include_attachments=True` when you need full message data.

### Thread fetching

Fetch all messages belonging to the same thread as a root message:

```
thread = mgr.fetch_thread(
    root=msgs[0],
    mailbox="INBOX",
    include_attachments=False,
)
```

If the `root` has no `message_id`, this simply returns `[root]`.

---

## EasyIMAPQuery Integration

Use `imap_query()` to build a fluent filter via `EasyIMAPQuery`:

```
q = (
    mgr.imap_query("INBOX")
       .recent_unread(7)
       .from_any("noreply@github.com", "support@example.com")
)

msgs = q.fetch(include_attachments=False)
```

See [`docs/EasyIMAPQuery.md`](docs/EasyIMAPQuery.md) for all query helpers.

---

## Flags & Triage

Flags are set at IMAP level using standard markers:

- `\Seen` (read)
- `\Flagged` (starred)
- `\Answered`
- `\Deleted`
- `\Draft`

Most operations take a sequence of `EmailRef`.

### Mark as seen / unseen

```
mgr.mark_seen(refs)
mgr.mark_unseen(refs)
```

### Flag / unflag

```
mgr.flag(refs)
mgr.unflag(refs)
```

### Answered

```
mgr.mark_answered(refs)
mgr.clear_answered(refs)
```

### Bulk mark all seen

```
count = mgr.mark_all_seen(mailbox="INBOX", chunk_size=500)
```

---

## Deleting & Expunging

Mark messages as deleted:

```
mgr.delete(refs)
```

Undo delete:

```
mgr.undelete(refs)
```

Permanently remove `\Deleted` messages in a mailbox:

```
mgr.expunge(mailbox="INBOX")
```

---

## Moving & Copying Messages

Move between folders:

```
mgr.move(
    refs,
    src_mailbox="INBOX",
    dst_mailbox="Archive",
)
```

Copy instead of move:

```
mgr.copy(
    refs,
    src_mailbox="INBOX",
    dst_mailbox="Receipts",
)
```

---

## Mailbox Management

List mailboxes:

```
names = mgr.list_mailboxes()
```

Mailbox status (e.g. message count, unseen count):

```
status = mgr.mailbox_status("INBOX")
# {"messages": X, "unseen": Y}
```

Create or delete a mailbox:

```
mgr.create_mailbox("Newsletters")
mgr.delete_mailbox("OldStuff")
```

---

## Unsubscribe Utilities

EmailManager integrates with a subscription helper that looks at `List-Unsubscribe` headers.

### Finding unsubscribe candidates

```
candidates = mgr.list_unsubscribe_candidates(
    mailbox="INBOX",
    limit=200,
    since=None,       # optional IMAP SINCE filter
    unseen_only=False,
)
```

### Performing unsubscribe actions

```
results = mgr.unsubscribe_selected(
    candidates,
    prefer="mailto",          # or "http"
    from_addr="me@example.com",
)
```

---

## Health Check & Lifecycle

### Health check

Ping both IMAP and SMTP:

```
status = mgr.health_check()
# {"imap": True/False, "smtp": True/False}
```

### Context manager usage

EmailManager implements `__enter__` / `__exit__` and `close()` for clean resource handling:

```
with EmailManager(smtp=smtp, imap=imap) as mgr:
    msgs = mgr.fetch_latest(n=10)

# or manually:
mgr.close()
```

Both IMAP and SMTP clients are closed best-effort.