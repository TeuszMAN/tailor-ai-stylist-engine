"""LLM provider factory. Returns `None` when no usable key is configured (rule-based mode)."""

from __future__ import annotations

from dataclasses import dataclass

from langchain_core.language_models import BaseChatModel

from app.config import Settings, usable_secret


@dataclass(frozen=True)
class LLMBundle:
    model: BaseChatModel
    provider: str
    model_name: str


def build_llm(settings: Settings) -> LLMBundle | None:
    if settings.llm_provider == "none":
        return None

    anthropic_key = usable_secret(settings.anthropic_api_key)
    if settings.llm_provider in ("auto", "anthropic") and anthropic_key:
        from langchain_anthropic import ChatAnthropic

        chat = ChatAnthropic(
            model=settings.anthropic_model,
            api_key=anthropic_key,
            max_tokens=1500,
            timeout=settings.llm_timeout_seconds,
            max_retries=1,
        )
        return LLMBundle(model=chat, provider="anthropic", model_name=settings.anthropic_model)

    openai_key = usable_secret(settings.openai_api_key)
    if settings.llm_provider in ("auto", "openai") and openai_key:
        from langchain_openai import ChatOpenAI

        chat_openai = ChatOpenAI(
            model=settings.openai_model,
            api_key=openai_key,
            timeout=settings.llm_timeout_seconds,
            max_retries=1,
        )
        return LLMBundle(model=chat_openai, provider="openai", model_name=settings.openai_model)

    return None
