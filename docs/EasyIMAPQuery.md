# EmailQuery

`EmailQuery` is a fluent IMAP query builder that lets you **compose filters in Python** without dealing directly with IMAP syntax.  
It integrates tightly with `EmailManager` and only executes the IMAP operation when you call `.search()` or `.fetch()`.

---

## Why It Exists

Raw IMAP queries are difficult to build, especially when combining:

- OR / AND nesting
- date filtering
- multi-field matching
- thread or participant filtering

`EmailQuery` provides a clean Python interface and returns standard `EmailMessage` objects when executed.

---

## Construction

You typically obtain an `EmailQuery` from `EmailManager`:

```
q = mgr.imap_query(mailbox="INBOX")
```

You can also omit the mailbox (defaults to `"INBOX"`):

```
q = mgr.imap_query()
```

---

## Execution Model

`EmailQuery` is “lazy” — meaning:

- Calling `.from_any(...)`, `.recent_unread(...)`, etc. **does not hit the server**
- Only `.search()` or `.fetch()` triggers IMAP operations

Example:

```
q = mgr.imap_query().from_any("alerts@example.com").recent_unread(7)

# No IMAP call yet

refs = q.search()  # IMAP SEARCH occurs here
msgs = q.fetch()   # IMAP SEARCH + FETCH occurs here
```

---

## Common Filters

Below are the most frequently used helpers:

### Sender matching

```
q = mgr.imap_query().from_any("billing@example.com", "support@example.com")
```

### Subject matching

```
q = mgr.imap_query().subject_any("invoice", "receipt")
```

### Recent unread

```
q = mgr.imap_query().recent_unread(days=3)
```

Equivalent to: `UNSEEN` + `SINCE <3 days ago>`

### Date filtering

```
q = mgr.imap_query().last_days(14)
```

Filters messages **since N days ago** (UTC).

### Thread-like matching

```
q = mgr.imap_query().thread_like(
    subject="Project X",
    participants=["alice@example.com", "bob@example.com"],
)
```

### By domain

```
q = mgr.imap_query().from_domain("github.com")
```

### Attachment hinting

```
q = mgr.imap_query().with_attachments_hint()
```

This uses IMAP header heuristics because IMAP lacks a reliable attachment filter.

### Newsletters

```
q = mgr.imap_query().newsletters()
```

Matches emails with `List-Unsubscribe` headers.

---

## Combining Filters

Filters can be chained:

```
q = (
    mgr.imap_query("INBOX")
       .from_any("noreply@github.com")
       .subject_any("alert", "summary")
       .last_days(30)
)
msgs = q.fetch()
```

---

## Thread Integration

If you have a message and want to fetch its thread:

```
root = msgs[0]

thread = mgr.fetch_thread(
    root=root,
    mailbox="INBOX",
    include_attachments=False,
)
```

Internally this uses IMAP headers via `.for_thread_root()`:

```
q = mgr.imap_query().for_thread_root(root)
```

---

## Search vs Fetch

### `search()`

Returns list of IMAP `EmailRef` identifiers:

```
refs = q.search()
```

### `fetch()`

Returns fully parsed `EmailMessage` objects:

```
msgs = q.fetch(include_attachments=False)
```

Use `include_attachments=True` for attachment access, at a performance cost.

---

## Natural Language Entry Point

`EmailQuery` also integrates with `EmailAssistant` for natural-language IMAP construction:

```
query, info = assistant.search_emails(
    "find unread security alerts from Google last week",
    provider="openai",
    model_name="gpt-4.1",
    manager=mgr,
)
msgs = query.fetch()
```

This enables user-facing search without exposing IMAP syntax.

---

## Fetch Overview

For list views and previews:

```
overviews = q.fetch_overview(preview_bytes=1024)
```

This returns lightweight `EmailOverview` records (faster than full fetch).

---

## Full Method Reference (High-Level)

| Method | Meaning |
|---|---|
| `.from_any(*senders)` | sender OR matching |
| `.to_any(*recipients)` | recipient OR matching |
| `.subject_any(*needles)` | subject OR matching |
| `.text_any(*needles)` | text body OR matching |
| `.recent_unread(days)` | `UNSEEN` + `SINCE days ago` |
| `.last_days(days)` | messages since N days ago |
| `.with_attachments_hint()` | attachment heuristics |
| `.security_alerts()` | match common security notifications |
| `.invoices_or_receipts()` | match billing/commerce keywords |
| `.from_domain(domain)` | sender domain matching |
| `.thread_like(...)` | approximate thread matching |
| `.for_thread_root(msg)` | match actual thread root by headers |
| `.newsletters()` | list-unsubscribe detection |
| `.header_contains(name, needle)` | raw header filtering |
| `.raw(*tokens)` | inject IMAP tokens directly |
| `.limit(n)` | restrict results |
