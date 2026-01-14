# EmailAssistant

`EmailAssistant` is the main interface for LLM-powered email operations such as summarization, reply generation, prioritization, follow-up suggestions, natural-language search construction, phishing evaluation, and task extraction.

This component works alongside `EmailManager` (for IMAP/SMTP) and optionally uses `EmailAssistantProfile` to adapt generated content to the user’s persona and tone.

---

## 🔑 Requirements for LLM Usage

Using `EmailAssistant` requires two things:

1. **An API key set in your environment**
2. **A supported `provider` and `model_name`**

Example environment variables:

```
export OPENAI_API_KEY="sk-..."
export GOOGLE_API_KEY="..."
export ANTHROPIC_API_KEY="..."
export XAI_API_KEY="..."
export GROQ_API_KEY="..."
```

If the key is missing for the selected provider, assistant calls will fail.

---

## 🤝 Supported Providers & Models

Below are valid `(provider, model_name)` combinations you may pass to `EmailAssistant` methods:

### **OpenAI** → `provider="openai"`
```
gpt-5-mini  
gpt-5-nano  
gpt-5.2  
gpt-4o  
gpt-4o-mini  
```

### **XAI** → `provider="xai"`
```
grok-4-1-fast-reasoning  
grok-4-1-fast-non-reasoning  
grok-4  
grok-4-fast-reasoning  
grok-4-fast-non-reasoning  
grok-3-mini  
grok-3  
```

### **Groq** → `provider="groq"`
```
openai/gpt-oss-20b  
openai/gpt-oss-120b  
moonshotai/kimi-k2-instruct-0905  
meta-llama/llama-4-scout-17b-16e-instruct  
meta-llama/llama-4-maverick-17b-128e-instruct  
qwen/qwen3-32b  
llama-3.1-8b-instant  
```

### **Gemini** → `provider="gemini"`
```
gemini-3-flash-preview  
gemini-2.5-flash  
gemini-2.5-flash-lite  
```

### **Claude** → `provider="claude"`
```
claude-opus-4.5  
claude-opus-4.1  
claude-opus-4  
claude-sonnet-4.5  
claude-sonnet-4  
claude-haiku-4.5  
claude-haiku-3.5  
claude-haiku-3  
```

---

## What EmailAssistant Does

`EmailAssistant` provides structured methods for:

- **Summarizing emails** (single, multi, threaded)
- **Generating replies** (concise or contextual)
- **Suggesting replies** (multiple choices)
- **Generating follow-ups** (for stalled threads)
- **Extracting tasks** (turn messages into actionable items)
- **Prioritizing emails** (numeric scores)
- **Classifying emails** (category assignment)
- **Evaluating sender trust**
- **Detecting phishing**
- **Summarizing attachments**
- **Building IMAP queries from natural language**

It does **not** send, fetch, or modify mailboxes — those responsibilities belong to `EmailManager`.

---

## Basic Construction

```
from email_assistant import EmailAssistant

assistant = EmailAssistant()
```

This creates an assistant without persona adjustments.

---

## Persona & Tone with EmailAssistantProfile

Although optional, `EmailAssistantProfile` allows the assistant to generate content that **better matches the user’s writing style**, role, and organizational context.  
This results in replies and summaries that are **more suitable and consistent** for real-world workflows (e.g., support, sales, academic, executive).

```
from email_assistant import EmailAssistant, EmailAssistantProfile

profile = EmailAssistantProfile(
    name="Alex",
    role="Support Engineer",
    company="ExampleCorp",
    tone="friendly",
)

assistant = EmailAssistant(profile=profile)
```

When generating outputs, persona + tone info is embedded automatically.

---

## Summarizing Email

Summarize a single email:

```
summary, meta = assistant.summarize_email(
    message=email,
    provider="openai",
    model_name="gpt-4o",
)
```

Summarize multiple:

```
summary, meta = assistant.summarize_multi_emails(
    messages=emails,
    provider="openai",
    model_name="gpt-4o",
)
```

Summarize a thread:

```
summary, meta = assistant.summarize_thread(
    thread_messages=thread,
    provider="openai",
    model_name="gpt-4o",
)
```

---

## Reply Generation

Contextual replies:

```
reply_text, meta = assistant.generate_reply(
    reply_context="Confirm resolution and next steps.",
    message=email,
    provider="openai",
    model_name="gpt-4o",
)
```

Reply suggestions (multiple choices):

```
suggestions, meta = assistant.generate_reply_suggestions(
    message=email,
    provider="openai",
    model_name="gpt-4o",
)
```

Follow-up messages:

```
followup, meta = assistant.generate_follow_up(
    message=email,
    provider="openai",
    model_name="gpt-4o",
)
```

If a profile is attached, these outputs will reflect persona and tone.

---

## Task Extraction

Convert emails into structured tasks:

```
tasks, meta = assistant.extract_tasks(
    messages=emails,
    provider="openai",
    model_name="gpt-4o",
)
```

Useful for CRM, PM tools, ticketing, triage dashboards, etc.

---

## Prioritization & Classification

Assign numeric priority:

```
scores, meta = assistant.prioritize_emails(
    messages=emails,
    provider="openai",
    model_name="gpt-4o",
)
```

Classify into categories:

```
labels, meta = assistant.classify_emails(
    messages=emails,
    classes=["invoice", "notification", "personal"],
    provider="openai",
    model_name="gpt-4o",
)
```

---

## Threat & Trust Evaluation

Detect phishing:

```
is_phish, meta = assistant.detect_phishing(
    message=email,
    provider="openai",
    model_name="gpt-4o",
)
```

Evaluate sender trust:

```
score, meta = assistant.evaluate_sender_trust(
    message=email,
    provider="openai",
    model_name="gpt-4o",
)
```

---

## Natural-Language Search Builder

Convert English requests into IMAP queries:

```
query, info = assistant.search_emails(
    "find unread security alerts from Google last week",
    provider="openai",
    model_name="gpt-4o",
    manager=mgr,  # EmailManager instance
)
msgs = query.fetch()
```

This allows high-level filtering without knowing IMAP syntax.

```
