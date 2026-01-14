from pydantic import BaseModel
from email.message import EmailMessage as PyEmailMessage

from email_management import EmailManager, EmailAssistant
import email_management.llm.model as model_mod
import email_management.email_assistant as assistants_mod
from email_management.email_assistant import EmailAssistantProfile
from email_management.models import EmailMessage
from email_management.types import EmailRef

from tests.fake_imap_client import FakeIMAPClient
from tests.fake_smtp_client import FakeSMTPClient


class FakeEasyQuery:
    def __init__(self):
        self.limits = []
        self.unseen_called = False
        self.fetch_calls = []

    def limit(self, n: int):
        self.limits.append(n)
        return self

    def unseen(self):
        self.unseen_called = True
        return self

    def fetch(self, *, include_attachments: bool = False):
        self.fetch_calls.append(include_attachments)

        msg1 = EmailMessage(
            ref=EmailRef(uid="1", mailbox="INBOX"),
            subject="First message",
            from_email="a@example.com",
            to=["me@example.com"],
            text="Body of first email",
        )
        msg2 = EmailMessage(
            ref=EmailRef(uid="2", mailbox="INBOX"),
            subject="Second message",
            from_email="b@example.com",
            to=["me@example.com"],
            text="Body of second email",
        )
        return [msg1, msg2]


class FakeOutModel(BaseModel):
    value: str


class FakePydanticChain:
    def __init__(self, data: dict):
        self.data = data

    def invoke(self, inputs, config=None):
        return self.data


def fake_get_base_llm_pydantic(
    provider,
    model_name,
    pydantic_model=None,
    temperature: float = 0.1,
    timeout: int = 120,
):
    return FakePydanticChain({"value": "hello"})


def test_get_model_with_pydantic(monkeypatch):
    import email_management.llm.model as model_mod

    model_mod._get_base_llm.cache_clear()
    monkeypatch.setattr(model_mod, "_get_base_llm", fake_get_base_llm_pydantic)

    class MySchema(BaseModel):
        value: str

    run = model_mod.get_model(
        provider="fake-provider",
        model_name="fake-model",
        pydantic_model=MySchema,
    )

    out, info = run("prompt")
    assert isinstance(out, MySchema)
    assert out.value == "hello"


class FakeChain:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def invoke(self, inputs, config=None):
        self.calls.append({"inputs": inputs, "config": config})

        class Out:
            def __init__(self, content):
                self.content = content

        return Out(self.response)


def fake_get_base_llm(
    model_name,
    pydantic_model=None,
    temperature: float = 0.1,
    timeout: int = 120,
):
    return FakeChain(response="fake-answer")


def _patch_fake_llm(monkeypatch):
    """
    Patch model_mod._get_base_llm so that any get_model(...) used by the
    llm_* helpers returns a fake chain instead of a real LLM.
    """
    model_mod._get_base_llm.cache_clear()

    def fake_get_base_llm_for_email_manager(
        provider,
        model_name,
        pydantic_model=None,
        temperature: float = 0.1,
        timeout: int = 120,
    ):
        # Raw string model (no pydantic) -> simple chain
        if pydantic_model is None:
            return FakeChain(response="fake raw answer")

        # Pydantic models: shape fake data by class name
        name = pydantic_model.__name__
        if "Reply" in name:
            data = {"reply": "fake reply body"}
        elif "Summary" in name or "Summarize" in name:
            data = {"summary": "fake summary text"}
        else:
            data = {"value": "fallback"}

        return FakePydanticChain(data)

    monkeypatch.setattr(model_mod, "_get_base_llm", fake_get_base_llm_for_email_manager)


def _make_mgr_with_fake_imap(monkeypatch):
    smtp = FakeSMTPClient()
    imap = FakeIMAPClient()
    mgr = EmailManager(smtp=smtp, imap=imap)
    fake_easy = FakeEasyQuery()

    def fake_imap_query(self, mailbox: str = "INBOX"):
        assert mailbox == "INBOX"
        return fake_easy

    # Force EmailManager.imap_query(...) to return our FakeEasyQuery
    monkeypatch.setattr(EmailManager, "imap_query", fake_imap_query)
    return mgr, fake_easy


def _make_sample_messages():
    msg1 = EmailMessage(
        ref=EmailRef(uid="10", mailbox="INBOX"),
        subject="Hello",
        from_email="person1@example.com",
        to=["me@example.com"],
        text="First body",
    )
    msg2 = EmailMessage(
        ref=EmailRef(uid="11", mailbox="INBOX"),
        subject="Re: Hello",
        from_email="person2@example.com",
        to=["me@example.com"],
        text="Second body",
    )
    return [msg1, msg2]


# ---------------------------------------------------------------------------
# Existing tests
# ---------------------------------------------------------------------------

def test_fetch_latest_uses_imap_query_and_limit(monkeypatch):
    mgr, fake_easy = _make_mgr_with_fake_imap(monkeypatch)

    msgs = mgr.fetch_latest(
        mailbox="INBOX",
        n=2,
        unseen_only=False,
        include_attachments=True,
    )

    assert isinstance(msgs, list)
    assert len(msgs) == 2
    assert isinstance(msgs[0], EmailMessage)

    # Ensure EasyIMAPQuery-style chaining happened
    assert fake_easy.limits == [2]
    assert fake_easy.fetch_calls == [True]


def test_summarize_multi_emails_uses_llm(monkeypatch):
    _patch_fake_llm(monkeypatch)
    mgr, _ = _make_mgr_with_fake_imap(monkeypatch)
    assistant = EmailAssistant()

    msgs = mgr.fetch_latest(
        mailbox="INBOX",
        n=2,
        unseen_only=False,
        include_attachments=True,
    )

    text, info = assistant.summarize_multi_emails(
        msgs,
        provider="fake-provider",
        model_name="fake-model",
    )

    assert isinstance(text, str)
    assert text != ""
    assert info["model"] == "fake-model"


def test_summarize_single_email_uses_llm(monkeypatch):
    _patch_fake_llm(monkeypatch)
    mgr, _ = _make_mgr_with_fake_imap(monkeypatch)
    assistant = EmailAssistant()

    msgs = mgr.fetch_latest(
        mailbox="INBOX",
        n=2,
        unseen_only=False,
        include_attachments=True,
    )

    text, info = assistant.summarize_email(
        msgs[0],
        provider="fake-provider",
        model_name="fake-model",
    )
    assert isinstance(text, str)
    assert text != ""
    assert info["model"] == "fake-model"


def test_generate_reply_uses_llm(monkeypatch):
    _patch_fake_llm(monkeypatch)
    mgr, _ = _make_mgr_with_fake_imap(monkeypatch)
    assistant = EmailAssistant()

    msgs = mgr.fetch_latest(
        mailbox="INBOX",
        n=2,
        unseen_only=False,
        include_attachments=True,
    )

    text, info = assistant.generate_reply(
        "reply to this email politely.",
        msgs[0],
        provider="fake-provider",
        model_name="fake-model",
    )

    assert isinstance(text, str)
    assert text != ""
    assert info["model"] == "fake-model"


# ---------------------------------------------------------------------------
# New tests for additional functionality
# ---------------------------------------------------------------------------

def test_email_assistant_profile_generate_prompt():
    profile = EmailAssistantProfile(
        name="Alex",
        role="Support Engineer",
        company="Acme Corp",
        tone="friendly",
        locale="en-US",
        extra_context="Handle billing-related emails carefully.",
    )

    prompt = profile.generate_prompt()
    assert "You are Alex." in prompt
    assert "Your role is Support Engineer." in prompt
    assert "You represent Acme Corp." in prompt
    assert "Use a friendly tone." in prompt
    assert "Locale: en-US." in prompt
    assert "Handle billing-related emails carefully." in prompt


def test_summarize_multi_emails_empty_returns_default():
    assistant = EmailAssistant()
    text, info = assistant.summarize_multi_emails(
        [],
        provider="fake-provider",
        model_name="fake-model",
    )
    assert text == "No emails selected."
    assert info == {}


def test_summarize_thread_empty_returns_default():
    assistant = EmailAssistant()
    text, info = assistant.summarize_thread(
        [],
        provider="fake-provider",
        model_name="fake-model",
    )
    assert text == "No emails in thread."
    assert info == {}


def test_summarize_thread_uses_llm(monkeypatch):
    msgs = _make_sample_messages()

    def fake_llm_summarize_thread_emails(messages, provider, model_name):
        assert messages == msgs
        assert provider == "fake-provider"
        assert model_name == "fake-model"
        return "thread summary", {"model": model_name}

    monkeypatch.setattr(
        assistants_mod, "llm_summarize_thread_emails", fake_llm_summarize_thread_emails
    )

    assistant = EmailAssistant()
    text, info = assistant.summarize_thread(
        msgs,
        provider="fake-provider",
        model_name="fake-model",
    )

    assert text == "thread summary"
    assert info["model"] == "fake-model"


def test_generate_reply_suggestions_uses_llm(monkeypatch):
    msgs = _make_sample_messages()
    message = msgs[0]

    def fake_llm_reply_suggestions_for_email(message_arg, provider, model_name):
        assert message_arg == message
        assert provider == "fake-provider"
        assert model_name == "fake-model"
        return ["opt1", "opt2"], {"model": model_name}

    monkeypatch.setattr(
        assistants_mod,
        "llm_reply_suggestions_for_email",
        fake_llm_reply_suggestions_for_email,
    )

    assistant = EmailAssistant()
    suggestions, info = assistant.generate_reply_suggestions(
        message,
        provider="fake-provider",
        model_name="fake-model",
    )

    assert suggestions == ["opt1", "opt2"]
    assert info["model"] == "fake-model"


def test_generate_reply_includes_profile_prompt(monkeypatch):
    msgs = _make_sample_messages()
    message = msgs[0]
    captured = {}

    def fake_llm_concise_reply_for_email(
        enriched_context,
        msg_arg,
        provider,
        model_name,
        previous_reply=None,
    ):
        captured["context"] = enriched_context
        captured["previous_reply"] = previous_reply
        assert msg_arg == message
        assert provider == "fake-provider"
        assert model_name == "fake-model"
        return "generated reply", {"model": model_name}

    monkeypatch.setattr(
        assistants_mod,
        "llm_concise_reply_for_email",
        fake_llm_concise_reply_for_email,
    )

    profile = EmailAssistantProfile(name="Alex", tone="formal")
    assistant = EmailAssistant(profile=profile)

    text, info = assistant.generate_reply(
        "Please respond to this customer.",
        message,
        previous_reply="old reply",
        provider="fake-provider",
        model_name="fake-model",
    )

    assert text == "generated reply"
    assert info["model"] == "fake-model"
    ctx = captured["context"]
    assert "You are Alex." in ctx
    assert "Use a formal tone." in ctx
    assert "Please respond to this customer." in ctx
    assert captured["previous_reply"] == "old reply"


def test_search_emails_uses_llm(monkeypatch):
    mgr, _ = _make_mgr_with_fake_imap(monkeypatch)
    fake_query = object()

    def fake_llm_easy_imap_query_from_nl(
        user_request,
        provider,
        model_name,
        manager,
        mailbox,
    ):
        assert user_request == "find unread updates"
        assert provider == "fake-provider"
        assert model_name == "fake-model"
        assert manager is mgr
        assert mailbox == "INBOX"
        return fake_query, {"model": model_name}

    monkeypatch.setattr(
        assistants_mod,
        "llm_easy_imap_query_from_nl",
        fake_llm_easy_imap_query_from_nl,
    )

    assistant = EmailAssistant()
    query, info = assistant.search_emails(
        "find unread updates",
        provider="fake-provider",
        model_name="fake-model",
        manager=mgr,
        mailbox="INBOX",
    )

    assert query is fake_query
    assert info["model"] == "fake-model"


def test_classify_emails_empty_returns_default():
    assistant = EmailAssistant()
    out, info = assistant.classify_emails(
        [],
        classes=["support", "sales"],
        provider="fake-provider",
        model_name="fake-model",
    )
    assert out == []
    assert info == {}


def test_classify_emails_uses_llm(monkeypatch):
    msgs = _make_sample_messages()
    classes = ["support", "sales"]

    def fake_llm_classify_emails(messages, classes, provider, model_name):
        assert messages == msgs
        assert classes == ["support", "sales"]
        assert provider == "fake-provider"
        assert model_name == "fake-model"
        # Return one label per message, in order
        return ["support", "sales"], {"model": model_name}

    monkeypatch.setattr(
        assistants_mod,
        "llm_classify_emails",
        fake_llm_classify_emails,
    )

    assistant = EmailAssistant()
    labels, info = assistant.classify_emails(
        msgs,
        classes=classes,
        provider="fake-provider",
        model_name="fake-model",
    )

    assert labels == ["support", "sales"]
    assert len(labels) == len(msgs)
    assert info["model"] == "fake-model"


def test_prioritize_emails_empty_returns_default():
    assistant = EmailAssistant()
    out, info = assistant.prioritize_emails(
        [],
        provider="fake-provider",
        model_name="fake-model",
    )
    assert out == []
    assert info == {}


def test_prioritize_emails_uses_llm(monkeypatch):
    msgs = _make_sample_messages()

    def fake_llm_prioritize_emails(messages, provider, model_name):
        assert messages == msgs
        assert provider == "fake-provider"
        assert model_name == "fake-model"
        # One score per message, in order
        return [0.9, 0.1], {"model": model_name}

    monkeypatch.setattr(
        assistants_mod,
        "llm_prioritize_emails",
        fake_llm_prioritize_emails,
    )

    assistant = EmailAssistant()
    scores, info = assistant.prioritize_emails(
        msgs,
        provider="fake-provider",
        model_name="fake-model",
    )

    assert scores == [0.9, 0.1]
    assert len(scores) == len(msgs)
    assert info["model"] == "fake-model"

def test_generate_follow_up_uses_llm(monkeypatch):
    msgs = _make_sample_messages()
    message = msgs[0]

    def fake_llm_generate_follow_up_for_email(message_arg, provider, model_name):
        assert message_arg == message
        assert provider == "fake-provider"
        assert model_name == "fake-model"
        return "follow-up text", {"model": model_name}

    monkeypatch.setattr(
        assistants_mod,
        "llm_generate_follow_up_for_email",
        fake_llm_generate_follow_up_for_email,
    )

    assistant = EmailAssistant()
    text, info = assistant.generate_follow_up(
        message,
        provider="fake-provider",
        model_name="fake-model",
    )

    assert text == "follow-up text"
    assert info["model"] == "fake-model"


def test_compose_email_includes_profile_prompt(monkeypatch):
    captured = {}

    def fake_llm_compose_email(instructions, provider, model_name):
        captured["instructions"] = instructions
        assert provider == "fake-provider"
        assert model_name == "fake-model"
        return "subject", "composed email", {"model": model_name}

    monkeypatch.setattr(
        assistants_mod,
        "llm_compose_email",
        fake_llm_compose_email,
    )

    profile = EmailAssistantProfile(name="Sam", tone="friendly")
    assistant = EmailAssistant(profile=profile)

    subject, text, info = assistant.compose_email(
        "Write a welcome email for a new customer.",
        provider="fake-provider",
        model_name="fake-model",
    )

    assert subject == "subject"
    assert text == "composed email"
    assert info["model"] == "fake-model"
    instr = captured["instructions"]
    assert "You are Sam." in instr
    assert "Use a friendly tone." in instr
    assert "Write a welcome email for a new customer." in instr


def test_rewrite_email_uses_llm(monkeypatch):
    def fake_llm_rewrite_email(draft_text, style, provider, model_name):
        assert draft_text == "hi there"
        assert style == "formal"
        assert provider == "fake-provider"
        assert model_name == "fake-model"
        return "Dear Sir or Madam...", {"model": model_name}

    monkeypatch.setattr(
        assistants_mod,
        "llm_rewrite_email",
        fake_llm_rewrite_email,
    )

    assistant = EmailAssistant()
    text, info = assistant.rewrite_email(
        "hi there",
        "formal",
        provider="fake-provider",
        model_name="fake-model",
    )

    assert text.startswith("Dear")
    assert info["model"] == "fake-model"


def test_translate_email_uses_llm(monkeypatch):
    def fake_llm_translate_email(
        text,
        target_language,
        source_language,
        provider,
        model_name,
    ):
        assert text == "hola"
        assert target_language == "en"
        assert source_language is None
        assert provider == "fake-provider"
        assert model_name == "fake-model"
        return "hello", {"model": model_name}

    monkeypatch.setattr(
        assistants_mod,
        "llm_translate_email",
        fake_llm_translate_email,
    )

    assistant = EmailAssistant()
    text, info = assistant.translate_email(
        "hola",
        "en",
        provider="fake-provider",
        model_name="fake-model",
    )

    assert text == "hello"
    assert info["model"] == "fake-model"


def test_extract_tasks_empty_returns_default():
    assistant = EmailAssistant()
    tasks, info = assistant.extract_tasks(
        [],
        provider="fake-provider",
        model_name="fake-model",
    )
    assert tasks == []
    assert info == {}


def test_extract_tasks_uses_llm(monkeypatch):
    msgs = _make_sample_messages()

    def fake_llm_extract_tasks_from_emails(messages, provider, model_name):
        assert messages == msgs
        assert provider == "fake-provider"
        assert model_name == "fake-model"
        # We don't care about exact Task type here, just that we pass it through.
        return ["task-1", "task-2"], {"model": model_name}

    monkeypatch.setattr(
        assistants_mod,
        "llm_extract_tasks_from_emails",
        fake_llm_extract_tasks_from_emails,
    )

    assistant = EmailAssistant()
    tasks, info = assistant.extract_tasks(
        msgs,
        provider="fake-provider",
        model_name="fake-model",
    )

    assert tasks == ["task-1", "task-2"]
    assert info["model"] == "fake-model"


def test_summarize_attachments_uses_llm(monkeypatch):
    msgs = _make_sample_messages()
    message = msgs[0]

    def fake_llm_summarize_attachments_for_email(message_arg, provider, model_name):
        assert message_arg == message
        assert provider == "fake-provider"
        assert model_name == "fake-model"
        return {"file.pdf": "summary of file"}, {"model": model_name}

    monkeypatch.setattr(
        assistants_mod,
        "llm_summarize_attachments_for_email",
        fake_llm_summarize_attachments_for_email,
    )

    assistant = EmailAssistant()
    summaries, info = assistant.summarize_attachments(
        message,
        provider="fake-provider",
        model_name="fake-model",
    )

    assert summaries == {"file.pdf": "summary of file"}
    assert info["model"] == "fake-model"


def test_detect_missing_attachment_true_when_mention_without_actual():
    msg = PyEmailMessage()
    msg.set_content("Please find attached the report for this month.")
    # No attachments added

    assistant = EmailAssistant()
    assert assistant.detect_missing_attachment(msg) is True


def test_detect_missing_attachment_false_when_attachment_present():
    msg = PyEmailMessage()
    msg.set_content("Please find attached the report for this month.")
    msg.add_attachment(
        b"fake-data",
        maintype="application",
        subtype="octet-stream",
        filename="report.pdf",
    )

    assistant = EmailAssistant()
    assert assistant.detect_missing_attachment(msg) is False


def test_detect_missing_attachment_false_when_no_mention():
    msg = PyEmailMessage()
    msg.set_content("Here is the report in the body, no attachment mentioned.")

    assistant = EmailAssistant()
    assert assistant.detect_missing_attachment(msg) is False


def test_detect_phishing_uses_llm(monkeypatch):
    msgs = _make_sample_messages()
    message = msgs[0]

    def fake_llm_detect_phishing_for_email(message_arg, provider, model_name):
        assert message_arg == message
        assert provider == "fake-provider"
        assert model_name == "fake-model"
        return True, {"model": model_name}

    monkeypatch.setattr(
        assistants_mod,
        "llm_detect_phishing_for_email",
        fake_llm_detect_phishing_for_email,
    )

    assistant = EmailAssistant()
    is_phishing, info = assistant.detect_phishing(
        message,
        provider="fake-provider",
        model_name="fake-model",
    )

    assert is_phishing is True
    assert info["model"] == "fake-model"


def test_evaluate_sender_trust_uses_llm(monkeypatch):
    msgs = _make_sample_messages()
    message = msgs[0]

    def fake_llm_evaluate_sender_trust_for_email(message_arg, provider, model_name):
        assert message_arg == message
        assert provider == "fake-provider"
        assert model_name == "fake-model"
        return 0.75, {"model": model_name}

    monkeypatch.setattr(
        assistants_mod,
        "llm_evaluate_sender_trust_for_email",
        fake_llm_evaluate_sender_trust_for_email,
    )

    assistant = EmailAssistant()
    score, info = assistant.evaluate_sender_trust(
        message,
        provider="fake-provider",
        model_name="fake-model",
    )

    assert score == 0.75
    assert info["model"] == "fake-model"
