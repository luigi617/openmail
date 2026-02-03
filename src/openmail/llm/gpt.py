from typing import Type

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_openai import ChatOpenAI
from pydantic import BaseModel


def get_openai(
    model_name: str,
    pydantic_model: Type[BaseModel],
    temperature: float = 0.1,
    timeout: int = 120,
):
   
    base_llm = ChatOpenAI(
        model=model_name,
        temperature=temperature,
        timeout=timeout,
    )

    llm_structured = base_llm.with_structured_output(pydantic_model)
    base_prompt = ChatPromptTemplate.from_messages([
        ("system", "Return ONLY valid JSON that matches the required schema. No extra text."),
        MessagesPlaceholder("messages")
    ])
    chain = base_prompt | llm_structured
    
    if chain is None:
        raise RuntimeError("LLM not available for the given model_name")

    return chain