from functools import lru_cache
import time
from typing import Type, Optional
from time import sleep
from random import random
from json import JSONDecodeError

from pydantic import BaseModel, ValidationError
from openai import APIConnectionError, APITimeoutError, RateLimitError

from langchain_core.exceptions import OutputParserException

from email_management.llm.gpt import get_openai

from email_management.llm.costs import TokenUsageCallback, compute_cost_usd



@lru_cache(maxsize=None)
def _get_base_llm(
    model_name: str,
    pydantic_model: Type[BaseModel] = None,
    temperature: float = 0.1,
    timeout: int = 120,
):
    if "gpt" in model_name:
        return get_openai(model_name, pydantic_model, temperature, timeout)
    raise RuntimeError("LLM not available for the given model_name")

def get_model(
    model_name: str,
    pydantic_model: Type[BaseModel] = None,
    temperature: float = 0.1,
    retries: int = 5, # -1 for infinite retries
    base_delay: float = 1.5,
    max_delay: float = 30.0,
    timeout: int = 120,
    all_fail_raise: bool = True,
):

    chain = _get_base_llm(model_name, pydantic_model, temperature, timeout)

    TRANSIENT_EXC = (APIConnectionError, APITimeoutError, RateLimitError)
    PARSE_EXC = (JSONDecodeError, OutputParserException, ValidationError)

    def run(prompt_text: str):
        infinite = (retries == -1)
        max_tries = float("inf") if infinite else max(1, retries)
        delay = base_delay
        last_exc: Optional[BaseException] = None
        
        
        attempt = 0
        while attempt < max_tries:
            try:
                usage_cb = TokenUsageCallback()
                t0 = time.perf_counter()
                out = chain.invoke(
                    {"prompt": prompt_text},
                    config={"callbacks": [usage_cb]},
                )
                t1 = time.perf_counter()

                if pydantic_model is not None:
                    model_obj = out if isinstance(out, BaseModel) else pydantic_model.model_validate(out)
                    out_dict = model_obj.model_dump()
                else:
                    out_dict = out.content

                cost_usd = compute_cost_usd(
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
                
                if pydantic_model is not None:
                    return model_obj.model_dump(), llm_call_info
                
                return out_dict, llm_call_info

            except (*TRANSIENT_EXC, *PARSE_EXC) as e:
                last_exc = e
            except Exception as e:
                last_exc = e
            
            attempt += 1
            if not infinite and attempt >= max_tries:
                if all_fail_raise and last_exc is not None:
                    raise last_exc
                llm_error_info = {
                    "model": model_name,
                    "prompt": prompt_text,
                    "timestamp": time.strftime("%m/%d/%Y_%H:%M:%S"),
                    "error": str(last_exc)
                }
                return None, llm_error_info

            sleep(delay + random() * 0.5)
            delay = min(delay * 2, max_delay)

    return run
