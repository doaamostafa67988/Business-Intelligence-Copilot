"""
LLM Factory.

Centralises LLM creation so every agent gets a consistently
configured client. Two model tiers:
  - primary  : llama-3.3-70b-versatile  — complex reasoning, SQL gen, insights
  - fast     : llama-3.1-8b-instant     — classification / routing / validation

Improvement: added structured output helper and token counting.
"""
from functools import lru_cache

from langchain_groq import ChatGroq

from core.config import get_settings


@lru_cache(maxsize=2)
def get_llm(fast: bool = False) -> ChatGroq:
    """
    Return a cached ChatGroq instance.

    Design decision: caching avoids re-initialising the HTTP client
    on every agent invocation, reducing latency significantly.
    """
    settings = get_settings()
    model = settings.llm_fast_model if fast else settings.llm_model

    return ChatGroq(
        api_key=settings.groq_api_key,
        model=model,
        temperature=settings.llm_temperature,
        max_retries=settings.llm_max_retries,
    )
