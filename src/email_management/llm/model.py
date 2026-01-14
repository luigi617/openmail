from functools import lru_cache
import time
from typing import Any, Callable, Dict, List, Tuple, Type, Optional, TypeVar
from time import sleep
from random import random
from json import JSONDecodeError
from pydantic import BaseModel, ValidationError
from openai import APIConnectionError, APITimeoutError, RateLimitError

from langchain_core.exceptions import OutputParserException

from email_management.llm.gpt import get_openai
from email_management.llm.gemini import get_gemini
from email_management.llm.groq import get_groq
from email_management.llm.xai import get_xai
from email_management.llm.claude import get_claude
from email_management.llm.costs import TokenUsageCallback, compute_cost_usd

TModel = TypeVar("TModel", bound=BaseModel)

@lru_cache(maxsize=None)
def _get_base_llm(
    provider: str,
    model_name: str,
    pydantic_model: Type[TModel],
    temperature: float = 0.1,
    timeout: int = 120,
):
    if provider == "openai":
        return get_openai(model_name, pydantic_model, temperature, timeout)
    if provider == "gemini":
        return get_gemini(model_name, pydantic_model, temperature, timeout)
    if provider == "xai":
        return get_xai(model_name, pydantic_model, temperature, timeout)
    if provider == "groq":
        return get_groq(model_name, pydantic_model, temperature, timeout)
    if provider == "claude":
        return get_claude(model_name, pydantic_model, temperature, timeout)

    raise RuntimeError("LLM not available for the given model_name")

def get_model(
    provider: str,
    model_name: str,
    pydantic_model: Type[TModel],
    temperature: float = 0.1,
    retries: int = 5, # -1 for infinite retries
    base_delay: float = 1.5,
    max_delay: float = 30.0,
    timeout: int = 120,
    all_fail_raise: bool = True,
) -> Callable[[str], Tuple[TModel, Dict[str, Any]]]:

    chain = _get_base_llm(provider, model_name, pydantic_model, temperature, timeout)

    TRANSIENT_EXC = (APIConnectionError, APITimeoutError, RateLimitError)
    PARSE_EXC = (JSONDecodeError, OutputParserException, ValidationError)
    
    history: List[Dict[str, str]] = []
    
    def run(prompt_text: str) -> Tuple[TModel, Dict[str, Any]]:
        nonlocal history
        infinite = (retries == -1)
        max_tries = float("inf") if infinite else max(1, retries)
        delay = base_delay
        last_exc: Optional[BaseException] = None
        
        
        attempt = 0
        while attempt < max_tries:
            try:
                messages = history + [
                    {"role": "user", "content": prompt_text},
                ]

                usage_cb = TokenUsageCallback()
                t0 = time.perf_counter()
                out = chain.invoke(
                    {"messages": messages},
                    config={"callbacks": [usage_cb]},
                )
                t1 = time.perf_counter()

                model_obj = out if isinstance(out, BaseModel) else pydantic_model.model_validate(out)
                out_dict = model_obj.model_dump()

                history = messages + [
                    {"role": "assistant", "content": model_obj.model_dump_json()}
                ]

                cost_usd = compute_cost_usd(
                    provider,
                    model_name,
                    prompt_tokens=usage_cb.prompt_tokens,
                    completion_tokens=usage_cb.completion_tokens,
                    cached_prompt_tokens=usage_cb.cached_prompt_tokens,
                )
                llm_call_info = {
                    "model": model_name,
                    "prompt": prompt_text,
                    "response": out_dict,
                    "call_time": t1 - t0,
                    "timestamp": time.strftime("%m/%d/%Y_%H:%M:%S"),
                    "prompt_tokens": usage_cb.prompt_tokens,
                    "completion_tokens": usage_cb.completion_tokens,
                    "cached_prompt_tokens": usage_cb.cached_prompt_tokens,
                    "cost_usd": cost_usd
                }
                
                return model_obj, llm_call_info

            except (*TRANSIENT_EXC, *PARSE_EXC) as e:
                last_exc = e
            except Exception as e:
                last_exc = e
            
            attempt += 1
            if not infinite and attempt >= max_tries:
                if all_fail_raise and last_exc is not None:
                    raise last_exc

            sleep(delay + random() * 0.5)
            delay = min(delay * 2, max_delay)

    return run
