from typing import Dict
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult

OPENAI_PRICES_PER_1M: Dict[str, Dict[str, float]] = {
    "gpt-5-mini": {"input": 0.25, "cached_input": 0.025, "output": 2.00},
    "gpt-5-nano": {"input": 0.05, "cached_input": 0.005, "output": 0.40},
    "gpt-5.2": {"input": 1.75, "cached_input": 0.175, "output": 14.00},
    "gpt-4o": {"input": 2.50, "cached_input": 1.25, "output": 10.00},
    "gpt-4o-mini": {"input": 0.15, "cached_input": 0.075, "output": 0.60},
}

XAI_PRICES_PER_1M: Dict[str, Dict[str, float]] = {
    "grok-4-1-fast-reasoning": {"input": 0.20, "cached_input": 0.05, "output": 0.50},
    "grok-4-1-fast-non-reasoning": {"input": 0.20, "cached_input": 0.05, "output": 0.50},
    "grok-4": {"input": 3.00, "cached_input": 0.75, "output": 15.00},
    "grok-4-fast-reasoning": {"input": 0.20, "cached_input": 0.05, "output": 0.50},
    "grok-4-fast-non-reasoning": {"input": 0.20, "cached_input": 0.05, "output": 0.50},
    "grok-3-mini": {"input": 0.30, "cached_input": 0.075, "output": 0.50},
    "grok-3": {"input": 3.00, "cached_input": 0.75, "output": 15.00},
}
GROQ_PRICES_PER_1M: Dict[str, Dict[str, float]] = {
    "openai/gpt-oss-20b": {"input": 0.075, "cached_input": 0.037, "output": 0.30},
    "openai/gpt-oss-120b": {"input": 0.15, "cached_input": 0.075, "output": 0.60},
    "moonshotai/kimi-k2-instruct-0905": {"input": 1.00, "cached_input": 0.50, "output": 3.00},
    "meta-llama/llama-4-scout-17b-16e-instruct": {"input": 0.11, "cached_input": 0.00, "output": 0.34},
    "meta-llama/llama-4-maverick-17b-128e-instruct": {"input": 0.20, "cached_input": 0.00, "output": 0.60},
    "qwen/qwen3-32b": {"input": 0.29, "cached_input": 0.00, "output": 0.59},
    "llama-3.1-8b-instant": {"input": 0.05, "cached_input": 0.00, "output": 0.08},
}

GEMINI_PRICES_PER_1M: Dict[str, Dict[str, float]] = {
    "gemini-3-flash-preview": {"input": 0.50, "cached_input": 0.05, "output": 3.00},
    "gemini-2.5-flash": {"input": 0.30, "cached_input": 0.03, "output": 2.50},
    "gemini-2.5-flash-lite": {"input": 0.10, "cached_input": 0.01, "output": 0.40},
}

CLAUDE_PRICES_PER_1M: Dict[str, Dict[str, float]] = {
    "claude-opus-4.5": {"input": 5.00,  "cached_input": 0.50, "output": 25.00},
    "claude-opus-4.1": {"input": 15.00, "cached_input": 1.50, "output": 75.00},
    "claude-opus-4": {"input": 15.00, "cached_input": 1.50, "output": 75.00},
    "claude-sonnet-4.5": {"input": 3.00,  "cached_input": 0.30, "output": 15.00},
    "claude-sonnet-4": {"input": 3.00,  "cached_input": 0.30, "output": 15.00},
    "claude-haiku-4.5": {"input": 1.00,  "cached_input": 0.10, "output": 5.00},
    "claude-haiku-3.5": {"input": 0.80,  "cached_input": 0.08, "output": 4.00},
    "claude-haiku-3": {"input": 0.25,  "cached_input": 0.03, "output": 1.25},
}

class TokenUsageCallback(BaseCallbackHandler):
    """Collect token usage from a single LLM call."""
    def __init__(self) -> None:
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.total_tokens = 0
        self.cached_prompt_tokens = 0

    def on_llm_end(self, response: LLMResult, **kwargs) -> None:
        
        usage = (response.llm_output or {}).get("token_usage")
        if usage:
            self.prompt_tokens += usage.get("prompt_tokens", 0)
            self.completion_tokens += usage.get("completion_tokens", 0)
            self.total_tokens += usage.get("total_tokens", 0)

            prompt_details = usage.get("prompt_tokens_details") or {}
            self.cached_prompt_tokens += prompt_details.get("cached_tokens", 0)
            return


def _lookup_price(provider: str, model_name: str) -> Dict[str, float]:
    if provider == "openai":
        return OPENAI_PRICES_PER_1M[model_name]
    if provider == "gemini":
        return GEMINI_PRICES_PER_1M[model_name]
    if provider == "xai":
        return XAI_PRICES_PER_1M[model_name]
    if provider == "groq":
        return GROQ_PRICES_PER_1M[model_name]
    if provider == "claude":
        return CLAUDE_PRICES_PER_1M[model_name]

    return {"input": 0.0, "cached_input": 0.0, "output": 0.0}


def compute_cost_usd(
        provider: str,
        model_name: str,
        prompt_tokens: int,
        completion_tokens: int,
        cached_prompt_tokens: int = 0,) -> float:
    prices = _lookup_price(provider, model_name)
    return (
        ((prompt_tokens - cached_prompt_tokens) / 1000000.0) * prices["input"]
        + (cached_prompt_tokens / 1000000.0) * prices["cached_input"]
        + (completion_tokens / 1000000.0) * prices["output"]
    )
