from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, AsyncIterator, Protocol, Sequence

from sqlmodel import Session

from app.ai.http_client import get_llm_client
from app.core.config import settings
from app.models.user import UserSettings


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
    ) -> str: ...

    async def stream(
        self,
        *,
        messages: Sequence[ChatMessage],
        model: str,
        temperature: float,
        max_tokens: int,
    ) -> AsyncIterator[str]: ...


class OllamaLLMProvider:
    def __init__(
        self, *, base_url: str | None = None, timeout_seconds: float = 180.0
    ) -> None:
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

        # Use pooled HTTP client instead of creating new one per request
        client = await get_llm_client(timeout=self.timeout_seconds)
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

		# Use pooled HTTP client instead of creating new one per request
		client = await get_llm_client(timeout=self.timeout_seconds)
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
) -> LLMConfig:
    user_settings = session.get(UserSettings, user_id)

    resolved_provider = provider or (
        str(user_settings.llm_provider) if user_settings else "ollama"
    )
    resolved_model = model or (
        user_settings.llm_model if user_settings else "tinyllama"
    )
    temperature = user_settings.temperature if user_settings else 0.7
    max_tokens = user_settings.max_tokens if user_settings else 1000

    if resolved_provider != "ollama":
        raise ValueError(
            f"Unsupported LLM provider '{resolved_provider}'. Only ollama is implemented."
        )

    return LLMConfig(
        provider=resolved_provider,
        model=resolved_model,
        temperature=temperature,
        max_tokens=max_tokens,
    )


class LLMService:
    def __init__(
        self, *, session: Session, user_id: int, base_url: str | None = None
    ) -> None:
        self.session = session
        self.user_id = user_id
        self.provider: BaseLLMProvider = OllamaLLMProvider(base_url=base_url)

    async def generate_response(
        self,
        *,
        messages: Sequence[ChatMessage],
        provider: str | None = None,
        model: str | None = None,
    ) -> str:
        config = resolve_llm_config(
            session=self.session,
            user_id=self.user_id,
            provider=provider,
            model=model,
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
) -> list[ChatMessage]:
    messages: list[ChatMessage] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})

    if context_chunks:
        combined_context = "\n\n".join(context_chunks)
        messages.append(
            {
                "role": "system",
                "content": f"Use the following context to answer the user:\n\n{combined_context}",
            }
        )

    messages.append({"role": "user", "content": user_prompt})
    return messages
