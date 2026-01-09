
from pydantic import BaseModel
from email.message import EmailMessage as PyEmailMessage

from email_management.email_manager import EmailManager
import email_management.llm.model as model_mod
from email_management.models import EmailMessage
from email_management.types import EmailRef

class FakeSMTPClient:
    def __init__(self):
        self.sent = []

    def send(self, msg: PyEmailMessage):
        self.sent.append(msg)
        return "send-result"


class FakeIMAPClient:
    def __init__(self):
        self.add_flags_calls = []
        self.remove_flags_calls = []

    def add_flags(self, refs, flags):
        self.add_flags_calls.append((list(refs), set(flags)))

    def remove_flags(self, refs, flags):
        self.remove_flags_calls.append((list(refs), set(flags)))



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
    
def fake_get_base_llm_pydantic(model_name, pydantic_model=None, temperature=0.1, timeout=120):
    return FakePydanticChain({"value": "hello"})

def test_get_model_with_pydantic(monkeypatch):
    import email_management.llm.model as model_mod
    model_mod._get_base_llm.cache_clear()
    monkeypatch.setattr(model_mod, "_get_base_llm", fake_get_base_llm_pydantic)

    class MySchema(BaseModel):
        value: str

    run = model_mod.get_model(
        model_name="fake-model",
        pydantic_model=MySchema,
    )

    out, info = run("prompt")
    assert out == {"value": "hello"}

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

def fake_get_base_llm(model_name, pydantic_model=None, temperature=0.1, timeout=120):
    return FakeChain(response="fake-answer")

def _patch_fake_llm(monkeypatch):
    """
    Patch model_mod._get_base_llm so that any get_model(...) used by the
    llm_* helpers returns a fake chain instead of a real LLM.
    """
    model_mod._get_base_llm.cache_clear()

    def fake_get_base_llm_for_email_manager(
        model_name,
        pydantic_model=None,
        temperature: float = 0.1,
        timeout: int = 120,
    ):
        if pydantic_model is None:
            return FakeChain(response="fake raw answer")

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

    def fake_imap_query(self, mailbox="INBOX"):
        assert mailbox == "INBOX"
        return fake_easy

    monkeypatch.setattr(EmailManager, "imap_query", fake_imap_query)
    return mgr, fake_easy

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

    assert fake_easy.limits == [2]
    assert fake_easy.fetch_calls == [True]


def test_summarize_multi_emails_uses_llm(monkeypatch):
    _patch_fake_llm(monkeypatch)
    mgr, _ = _make_mgr_with_fake_imap(monkeypatch)

    msgs = mgr.fetch_latest(
        mailbox="INBOX",
        n=2,
        unseen_only=False,
        include_attachments=True,
    )

    text, info = mgr.summarize_multi_emails(msgs, model_path="fake-model")

    assert isinstance(text, str)
    assert text != ""
    assert info["model"] == "fake-model"


def test_summarize_single_email_uses_llm(monkeypatch):
    _patch_fake_llm(monkeypatch)
    mgr, _ = _make_mgr_with_fake_imap(monkeypatch)

    msgs = mgr.fetch_latest(
        mailbox="INBOX",
        n=2,
        unseen_only=False,
        include_attachments=True,
    )

    text, info = mgr.summarize_email(msgs[0], model_path="fake-model")
    assert isinstance(text, str)
    assert text != ""
    assert info["model"] == "fake-model"


def test_generate_reply_uses_llm(monkeypatch):
    _patch_fake_llm(monkeypatch)
    mgr, _ = _make_mgr_with_fake_imap(monkeypatch)

    msgs = mgr.fetch_latest(
        mailbox="INBOX",
        n=2,
        unseen_only=False,
        include_attachments=True,
    )

    text, info = mgr.generate_reply(msgs[0], model_path="fake-model")

    assert isinstance(text, str)
    assert text != ""
    assert info["model"] == "fake-model"