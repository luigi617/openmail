# tests/test_llm_model_and_costs.py

from typing import Any, Dict, List, Tuple, Type

import pytest
from pydantic import BaseModel

from openmail.llm.costs import (
    _lookup_price,
    compute_cost_usd,
)
from openmail.llm.model import _get_base_llm, get_model

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

# Important: clear the lru_cache on _get_base_llm between tests so our
# monkeypatching of get_openai/get_gemini/etc behaves as expected.
@pytest.fixture(autouse=True)
def clear_llm_cache():
    _get_base_llm.cache_clear()
    yield
    _get_base_llm.cache_clear()


class DummyModel(BaseModel):
    message: str

class DummyTransientError(Exception):
    """Simple stand-in for openai transient errors in tests."""
    pass


class FakeLLMResult:
    """Minimal object that looks like langchain_core.outputs.LLMResult for TokenUsageCallback."""
    def __init__(self, token_usage: Dict[str, Any]):
        self.llm_output = {"token_usage": token_usage}


class FakeChain:
    """Fake chain that returns a fixed Pydantic model and fires callbacks."""

    def __init__(self, result_obj: BaseModel, token_usage: Dict[str, Any]):
        self._result_obj = result_obj
        self._token_usage = token_usage
        self.calls: List[Tuple[Dict[str, Any], Dict[str, Any]]] = []

    def invoke(self, inputs: Dict[str, Any], config: Dict[str, Any]) -> BaseModel:
        self.calls.append((inputs, config))
        callbacks = config.get("callbacks", [])
        for cb in callbacks:
            cb.on_llm_end(FakeLLMResult(self._token_usage))
        return self._result_obj


class AlwaysFailChain:
    """Fake chain that always raises a given exception type."""

    def __init__(self, exc_type: Type[BaseException]):
        self.exc_type = exc_type
        self.calls = 0

    def invoke(self, inputs: Dict[str, Any], config: Dict[str, Any]) -> BaseModel:
        self.calls += 1
        raise self.exc_type()


class FlakyChain:
    """
    Fake chain that fails with a transient error for 'fail_times' calls,
    then returns a fixed model and triggers callbacks.
    """

    def __init__(
        self,
        exc_type: Type[BaseException],
        fail_times: int,
        result_obj: BaseModel,
        token_usage: Dict[str, Any],
    ):
        self.exc_type = exc_type
        self.fail_times = fail_times
        self.result_obj = result_obj
        self.token_usage = token_usage
        self.calls = 0

    def invoke(self, inputs: Dict[str, Any], config: Dict[str, Any]) -> BaseModel:
        self.calls += 1
        if self.calls <= self.fail_times:
            raise self.exc_type()
        callbacks = config.get("callbacks", [])
        for cb in callbacks:
            cb.on_llm_end(FakeLLMResult(self.token_usage))
        return self.result_obj


# ---------------------------------------------------------------------------
# Tests for _get_base_llm (correct & wrong providers)
# ---------------------------------------------------------------------------

def test_get_base_llm_openai(monkeypatch):
    from openmail.llm import model as model_mod

    captured_args: Dict[str, Any] = {}

    def fake_get_openai(model_name, pydantic_model, temperature, timeout):
        captured_args["model_name"] = model_name
        captured_args["pydantic_model"] = pydantic_model
        captured_args["temperature"] = temperature
        captured_args["timeout"] = timeout
        return "OPENAI_CHAIN"

    monkeypatch.setattr(model_mod, "get_openai", fake_get_openai)

    chain = _get_base_llm("openai", "gpt-5-mini", DummyModel, temperature=0.2, timeout=10)
    assert chain == "OPENAI_CHAIN"
    assert captured_args == {
        "model_name": "gpt-5-mini",
        "pydantic_model": DummyModel,
        "temperature": 0.2,
        "timeout": 10,
    }


def test_get_base_llm_gemini(monkeypatch):
    from openmail.llm import model as model_mod

    called: Dict[str, Any] = {}

    def fake_get_gemini(model_name, pydantic_model, temperature, timeout):
        called["called"] = (model_name, pydantic_model)
        return "GEMINI_CHAIN"

    monkeypatch.setattr(model_mod, "get_gemini", fake_get_gemini)

    chain = _get_base_llm("gemini", "gemini-2.5-flash", DummyModel)
    assert chain == "GEMINI_CHAIN"
    assert called["called"] == ("gemini-2.5-flash", DummyModel)


def test_get_base_llm_xai(monkeypatch):
    from openmail.llm import model as model_mod

    called: Dict[str, Any] = {}

    def fake_get_xai(model_name, pydantic_model, temperature, timeout):
        called["called"] = (model_name, pydantic_model)
        return "XAI_CHAIN"

    monkeypatch.setattr(model_mod, "get_xai", fake_get_xai)
    chain = _get_base_llm("xai", "grok-4", DummyModel)
    assert chain == "XAI_CHAIN"
    assert called["called"] == ("grok-4", DummyModel)


def test_get_base_llm_groq(monkeypatch):
    from openmail.llm import model as model_mod

    called: Dict[str, Any] = {}

    def fake_get_groq(model_name, pydantic_model, temperature, timeout):
        called["called"] = (model_name, pydantic_model)
        return "GROQ_CHAIN"

    monkeypatch.setattr(model_mod, "get_groq", fake_get_groq)
    chain = _get_base_llm("groq", "llama-3.1-8b-instant", DummyModel)
    assert chain == "GROQ_CHAIN"
    assert called["called"] == ("llama-3.1-8b-instant", DummyModel)


def test_get_base_llm_unknown_provider_raises():
    with pytest.raises(RuntimeError):
        _get_base_llm("unknown-provider", "some-model", DummyModel)


def test_lookup_price_known_model_openai():
    prices = _lookup_price("openai", "gpt-5-mini")
    assert prices["input"] > 0
    assert prices["output"] > 0
    assert "cached_input" in prices


def test_lookup_price_unknown_provider_returns_zero_price():
    prices = _lookup_price("nonexistent", "whatever")
    assert prices == {"input": 0.0, "cached_input": 0.0, "output": 0.0}


def test_compute_cost_usd_with_cached_prompt_tokens():
    provider = "openai"
    model_name = "gpt-5-mini"

    prices = _lookup_price(provider, model_name)
    prompt_tokens = 10_000
    cached_prompt_tokens = 2_000
    completion_tokens = 5_000

    expected = (
        ((prompt_tokens - cached_prompt_tokens) / 1_000_000.0) * prices["input"]
        + (cached_prompt_tokens / 1_000_000.0) * prices["cached_input"]
        + (completion_tokens / 1_000_000.0) * prices["output"]
    )

    cost = compute_cost_usd(
        provider=provider,
        model_name=model_name,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cached_prompt_tokens=cached_prompt_tokens,
    )

    assert cost == pytest.approx(expected)


def test_compute_cost_usd_unknown_provider_zero_cost():
    cost = compute_cost_usd(
        provider="nonexistent",
        model_name="whatever",
        prompt_tokens=1000,
        completion_tokens=2000,
        cached_prompt_tokens=0,
    )
    assert cost == 0.0


def test_get_model_success_with_valid_provider_and_model(monkeypatch):
    """
    Test that:
    - get_model wires provider/model_name into _get_base_llm
    - TokenUsageCallback collects usage
    - compute_cost_usd is used to fill cost_usd
    - history grows across calls
    """
    from openmail.llm import model as model_mod

    # Avoid actual sleeping in retry loop
    monkeypatch.setattr(model_mod, "sleep", lambda *_a, **_kw: None)

    token_usage = {
        "prompt_tokens": 1000,
        "completion_tokens": 2000,
        "total_tokens": 3000,
        "prompt_tokens_details": {"cached_tokens": 100},
    }

    fake_chain = FakeChain(
        result_obj=DummyModel(message="hello"),
        token_usage=token_usage,
    )

    def fake_get_base_llm(provider, model_name, pydantic_model, temperature, timeout):
        # Ensure parameters are passed correctly
        assert provider == "openai"
        assert model_name == "gpt-5-mini"
        assert pydantic_model is DummyModel
        return fake_chain

    monkeypatch.setattr(model_mod, "_get_base_llm", fake_get_base_llm)

    run = get_model(
        provider="openai",
        model_name="gpt-5-mini",
        pydantic_model=DummyModel,
        temperature=0.1,
        retries=1,
        timeout=30,
    )

    prompt_text_1 = "first prompt"
    model_obj_1, info_1 = run(prompt_text_1)

    # First call checks
    assert isinstance(model_obj_1, DummyModel)
    assert model_obj_1.message == "hello"
    assert info_1["model"] == "gpt-5-mini"
    assert info_1["prompt"] == prompt_text_1
    assert info_1["response"] == model_obj_1.model_dump()
    assert info_1["prompt_tokens"] == 1000
    assert info_1["completion_tokens"] == 2000
    assert info_1["cached_prompt_tokens"] == 100
    assert info_1["cost_usd"] > 0.0
    assert isinstance(info_1["call_time"], float)
    assert info_1["call_time"] >= 0.0

    # FakeChain should have been called exactly once
    assert len(fake_chain.calls) == 1
    first_inputs, _first_config = fake_chain.calls[0]
    # history at first call = only current user message
    assert len(first_inputs["messages"]) == 1
    assert first_inputs["messages"][0]["role"] == "user"
    assert first_inputs["messages"][0]["content"] == prompt_text_1

    # Second call: history should now contain previous user & assistant messages
    prompt_text_2 = "second prompt"
    model_obj_2, info_2 = run(prompt_text_2)

    assert isinstance(model_obj_2, DummyModel)
    assert model_obj_2.message == "hello"
    assert info_2["model"] == "gpt-5-mini"

    assert len(fake_chain.calls) == 2
    second_inputs, _second_config = fake_chain.calls[1]
    # history (user, assistant) + new user => 3 messages
    assert len(second_inputs["messages"]) == 3
    assert second_inputs["messages"][0]["role"] == "user"
    assert second_inputs["messages"][1]["role"] == "assistant"
    assert second_inputs["messages"][2]["role"] == "user"
    assert second_inputs["messages"][2]["content"] == prompt_text_2



def test_get_model_retries_and_succeeds_on_transient_error(monkeypatch):
    from openmail.llm import model as model_mod

    # Avoid real sleeping
    monkeypatch.setattr(model_mod, "APIConnectionError", DummyTransientError)
    monkeypatch.setattr(model_mod, "sleep", lambda *_a, **_kw: None)

    token_usage = {
        "prompt_tokens": 500,
        "completion_tokens": 500,
        "total_tokens": 1000,
        "prompt_tokens_details": {"cached_tokens": 0},
    }

    result_obj = DummyModel(message="eventual success")

    flaky_chain = FlakyChain(
        exc_type=DummyTransientError,
        fail_times=2,  # two failures, then success
        result_obj=result_obj,
        token_usage=token_usage,
    )

    def fake_get_base_llm(provider, model_name, pydantic_model, temperature, timeout):
        return flaky_chain

    monkeypatch.setattr(model_mod, "_get_base_llm", fake_get_base_llm)

    run = get_model(
        provider="openai",
        model_name="gpt-5-mini",
        pydantic_model=DummyModel,
        retries=5,  # more than fail_times
        base_delay=0.1,
        max_delay=0.2,
        timeout=30,
        all_fail_raise=True,
    )

    model_obj, info = run("prompt text")

    # Should have failed twice then succeeded
    assert flaky_chain.calls == 3
    assert isinstance(model_obj, DummyModel)
    assert model_obj.message == "eventual success"
    assert info["prompt_tokens"] == 500
    assert info["completion_tokens"] == 500
    assert info["cost_usd"] > 0.0


def test_get_model_all_retries_fail_and_raise(monkeypatch):
    from openmail.llm import model as model_mod
    monkeypatch.setattr(model_mod, "APIConnectionError", DummyTransientError)
    monkeypatch.setattr(model_mod, "sleep", lambda *_a, **_kw: None)

    always_fail_chain = AlwaysFailChain(exc_type=DummyTransientError)

    def fake_get_base_llm(provider, model_name, pydantic_model, temperature, timeout):
        return always_fail_chain

    monkeypatch.setattr(model_mod, "_get_base_llm", fake_get_base_llm)

    run = get_model(
        provider="openai",
        model_name="gpt-5-mini",
        pydantic_model=DummyModel,
        retries=3,
        base_delay=0.1,
        max_delay=0.2,
        timeout=30,
        all_fail_raise=True,
    )

    with pytest.raises(DummyTransientError):
        run("some prompt")

    # Should have tried exactly 3 times
    assert always_fail_chain.calls == 3


def test_get_model_all_retries_fail_no_raise_returns_none(monkeypatch):
    from openmail.llm import model as model_mod
    monkeypatch.setattr(model_mod, "APIConnectionError", DummyTransientError)
    monkeypatch.setattr(model_mod, "sleep", lambda *_a, **_kw: None)

    always_fail_chain = AlwaysFailChain(exc_type=DummyTransientError)

    def fake_get_base_llm(provider, model_name, pydantic_model, temperature, timeout):
        return always_fail_chain

    monkeypatch.setattr(model_mod, "_get_base_llm", fake_get_base_llm)

    run = get_model(
        provider="openai",
        model_name="gpt-5-mini",
        pydantic_model=DummyModel,
        retries=2,
        base_delay=0.1,
        max_delay=0.2,
        timeout=30,
        all_fail_raise=False,
    )

    # Function should return None after retries are exhausted when all_fail_raise=False
    result = run("some prompt")
    assert result is None
    assert always_fail_chain.calls == 2
