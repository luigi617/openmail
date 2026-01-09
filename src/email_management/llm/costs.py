from typing import Dict
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult

OPENAI_PRICES_PER_1M: Dict[str, Dict[str, float]] = {
    "gpt-5-mini": {"input": 0.25, "cached_input": 0.025, "output": 2.00},
    "gpt-5-nano": {"input": 0.05, "cached_input": 0.005, "output": 0.40},
    "gpt-5.2": {"input": 1.75, "cached_input": 0.175, "output": 14.00},
}

DEEPSEEK_PRICES_PER_1M: Dict[str, Dict[str, float]] = {
    "deepseek-chat": {"input": 0.28, "cached_input": 0.028, "output": 0.42},
    "deepseek-reasoner": {"input": 0.28, "cached_input": 0.028, "output": 0.42},
}

GEMINI_PRICES_PER_1M: Dict[str, Dict[str, float]] = {
    "gemini-2.5-flash-lite": {"input": 0.10, "cached_input": 0.01, "output": 0.40},
    "gemini-2.5-flash": {"input": 0.30, "cached_input": 0.03, "output": 2.50},
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


def _lookup_price(model_name: str) -> Dict[str, float]:
    if "gpt" in model_name:
        return OPENAI_PRICES_PER_1M[model_name]
    if "deepseek" in model_name:
        return DEEPSEEK_PRICES_PER_1M[model_name]

    return {"input": 0.0, "cached_input": 0.0, "output": 0.0}


def compute_cost_usd(
        model_name: str,
        prompt_tokens: int,
        completion_tokens: int,
        cached_prompt_tokens: int = 0,) -> float:
    prices = _lookup_price(model_name)
    return (
        ((prompt_tokens - cached_prompt_tokens) / 1000000.0) * prices["input"]
        + (cached_prompt_tokens / 1000000.0) * prices["cached_input"]
        + (completion_tokens / 1000000.0) * prices["output"]
    )
