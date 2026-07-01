from __future__ import annotations

import json
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from sqlmodel import Session

from app.ai.http_client import create_llm_client
from app.core.config import settings
from app.models.user import LlmProvider, UserSettings

ChatMessage = dict[str, str]


@dataclass(slots=True)
class LLMConfig:
    provider: str
    model: str
    temperature: float
    max_tokens: int


class BaseLLMProvider(Protocol):
    async def complete(
        self,
        *,
        messages: Sequence[ChatMessage],
        model: str,
        temperature: float,
        max_tokens: int,
    ) -> str:
        ...

    def stream(
        self,
        *,
        messages: Sequence[ChatMessage],
        model: str,
        temperature: float,
        max_tokens: int,
    ) -> AsyncIterator[str]:
        ...


class OllamaLLMProvider:
    def __init__(self, *, base_url: str | None = None, timeout_seconds: float = 180.0) -> None:
        self.base_url = (base_url or settings.OLLAMA_BASE_URL).rstrip("/")
        self.timeout_seconds = timeout_seconds

    async def complete(
        self,
        *,
        messages: Sequence[ChatMessage],
        model: str,
        temperature: float,
        max_tokens: int,
    ) -> str:
        payload = self._build_payload(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=False,
        )

        async with create_llm_client(timeout=self.timeout_seconds) as client:
            response = await client.post(f"{self.base_url}/api/chat", json=payload)
            response.raise_for_status()
            data = response.json()

        message = data.get("message")
        if not isinstance(message, dict):
            raise ValueError("Invalid Ollama chat response: missing message object")

        content = message.get("content")
        if not isinstance(content, str):
            raise ValueError("Invalid Ollama chat response: missing content")

        return content

    async def stream(
        self,
        *,
        messages: Sequence[ChatMessage],
        model: str,
        temperature: float,
        max_tokens: int,
    ) -> AsyncIterator[str]:
        payload = self._build_payload(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
        )

        async with create_llm_client(timeout=self.timeout_seconds) as client:
            async with client.stream("POST", f"{self.base_url}/api/chat", json=payload) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    data = json.loads(line)
                    message = data.get("message")
                    if not isinstance(message, dict):
                        continue
                    chunk = message.get("content")
                    if isinstance(chunk, str) and chunk:
                        yield chunk

    @staticmethod
    def _build_payload(
        *,
        messages: Sequence[ChatMessage],
        model: str,
        temperature: float,
        max_tokens: int,
        stream: bool,
    ) -> dict[str, Any]:
        return {
            "model": model,
            "messages": list(messages),
            "stream": stream,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }


def resolve_llm_config(
    *,
    session: Session,
    user_id: int,
    provider: str | None = None,
    model: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> LLMConfig:
    user_settings = session.get(UserSettings, user_id)

    resolved_provider = provider or (
        user_settings.llm_provider.value
        if user_settings and isinstance(user_settings.llm_provider, LlmProvider)
        else (str(user_settings.llm_provider) if user_settings else "ollama")
    )
    resolved_model = model or (
        user_settings.llm_model if user_settings else settings.OLLAMA_CHAT_MODEL
    )
    resolved_temperature = (
        temperature
        if temperature is not None
        else (user_settings.temperature if user_settings else 0.7)
    )
    resolved_max_tokens = (
        max_tokens
        if max_tokens is not None
        else (user_settings.max_tokens if user_settings else 1000)
    )

    if resolved_provider != "ollama":
        raise ValueError(
            f"Unsupported LLM provider '{resolved_provider}'. Only ollama is implemented."
        )

    return LLMConfig(
        provider=resolved_provider,
        model=resolved_model,
        temperature=resolved_temperature,
        max_tokens=resolved_max_tokens,
    )


class LLMService:
    def __init__(self, *, session: Session, user_id: int, base_url: str | None = None) -> None:
        self.session = session
        self.user_id = user_id
        self.provider: BaseLLMProvider = OllamaLLMProvider(base_url=base_url)

    async def generate_response(
        self,
        *,
        messages: Sequence[ChatMessage],
        provider: str | None = None,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        config = resolve_llm_config(
            session=self.session,
            user_id=self.user_id,
            provider=provider,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return await self.provider.complete(
            messages=messages,
            model=config.model,
            temperature=config.temperature,
            max_tokens=config.max_tokens,
        )

    async def stream_response(
        self,
        *,
        messages: Sequence[ChatMessage],
        provider: str | None = None,
        model: str | None = None,
    ) -> AsyncIterator[str]:
        config = resolve_llm_config(
            session=self.session,
            user_id=self.user_id,
            provider=provider,
            model=model,
        )
        async for chunk in self.provider.stream(
            messages=messages,
            model=config.model,
            temperature=config.temperature,
            max_tokens=config.max_tokens,
        ):
            yield chunk


def build_chat_messages(
    *,
    user_prompt: str,
    context_chunks: Sequence[str] | None = None,
    system_prompt: str | None = None,
    conversation_history: Sequence[ChatMessage] | None = None,
) -> list[ChatMessage]:
    messages: list[ChatMessage] = []
    system_parts: list[str] = []
    if system_prompt:
        system_parts.append(system_prompt)
    if system_parts:
        messages.append({"role": "system", "content": "\n\n".join(system_parts)})

    if conversation_history:
        messages.extend(conversation_history)

    if context_chunks:
        combined_context = "\n\n".join(context_chunks)
        final_prompt = (
            "REFERENCE CONTEXT (use internally; do not repeat it in full):\n"
            f"{combined_context}\n\nCURRENT QUESTION:\n{user_prompt}\n\nDIRECT ANSWER:"
        )
    else:
        final_prompt = user_prompt

    messages.append({"role": "user", "content": final_prompt})
    return messages
