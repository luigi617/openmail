from __future__ import annotations
from typing import Any, Optional, Tuple
from pydantic import BaseModel, Field
from email_management.llm import get_model


TRANSLATE_EMAIL_PROMPT = """
You are a translation assistant.

Instructions:
- Translate the text into the target language.
- Preserve tone and level of formality as much as reasonable.
- Do not add explanations, comments, or notes—only output the translated text.
- Keep formatting (line breaks, bullet points) where it makes sense.

Target language: {target_language}
{source_line}

Text to translate:
{text}
"""

class TranslateEmailSchema(BaseModel):
    translated_text: str = Field(
        description="The translated text in the target language."
    )

def llm_translate_email(
    text: str,
    *,
    target_language: str,
    source_language: Optional[str],
    provider: str,
    model_name: str,
) -> Tuple[str, dict[str, Any]]:
    """
    Translate arbitrary text to a target language.
    """
    if source_language:
        source_line = f"Source language: {source_language}"
    else:
        source_line = "Source language: auto-detect"

    chain = get_model(provider, model_name, TranslateEmailSchema)
    result, llm_call_info = chain(
        TRANSLATE_EMAIL_PROMPT.format(
            target_language=target_language,
            source_line=source_line,
            text=text,
        )
    )
    return result.translated_text, llm_call_info
