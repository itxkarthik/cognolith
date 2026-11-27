"""Token counts come from Ollama's eval_count, not from counting words (issue #23)."""

import json
from typing import Any

import httpx
import pytest

from app.ai import llm
from app.ai.llm import OllamaLLMProvider, TokenUsage

MESSAGES = [{"role": "user", "content": "Hi"}]


def _serve(monkeypatch: pytest.MonkeyPatch, body: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/chat"
        return httpx.Response(200, content=body.encode())

    monkeypatch.setattr(
        llm,
        "create_llm_client",
        lambda timeout: httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )


def _lines(*objects: dict[str, Any]) -> str:
    return "\n".join(json.dumps(item) for item in objects) + "\n"


async def _collect(provider: OllamaLLMProvider, usage: TokenUsage) -> str:
    chunks = [
        chunk
        async for chunk in provider.stream(
            messages=MESSAGES, model="m", temperature=0.1, max_tokens=50, usage=usage
        )
    ]
    return "".join(chunks)


@pytest.mark.asyncio
async def test_stream_records_the_final_eval_count(monkeypatch: pytest.MonkeyPatch) -> None:
    _serve(
        monkeypatch,
        _lines(
            {"message": {"role": "assistant", "content": "Two words"}, "done": False},
            {"message": {"role": "assistant", "content": " here"}, "done": False},
            {
                "message": {"role": "assistant", "content": ""},
                "done": True,
                "prompt_eval_count": 120,
                "eval_count": 7,
            },
        ),
    )
    usage = TokenUsage()

    text = await _collect(OllamaLLMProvider(base_url="http://ollama"), usage)

    assert text == "Two words here"
    assert usage.generated_tokens == 7  # generated tokens, not 3 words or the prompt


@pytest.mark.asyncio
async def test_complete_records_eval_count(monkeypatch: pytest.MonkeyPatch) -> None:
    _serve(
        monkeypatch,
        json.dumps(
            {
                "message": {"role": "assistant", "content": "Answer"},
                "done": True,
                "eval_count": 18,
            }
        ),
    )
    usage = TokenUsage()

    answer = await OllamaLLMProvider(base_url="http://ollama").complete(
        messages=MESSAGES, model="m", temperature=0.1, max_tokens=50, usage=usage
    )

    assert answer == "Answer"
    assert usage.generated_tokens == 18


@pytest.mark.asyncio
async def test_missing_count_stays_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    _serve(
        monkeypatch,
        _lines(
            {"message": {"role": "assistant", "content": "Hi"}, "done": False},
            {"message": {"role": "assistant", "content": ""}, "done": True},
        ),
    )
    usage = TokenUsage()

    await _collect(OllamaLLMProvider(base_url="http://ollama"), usage)

    assert usage.generated_tokens is None


def test_usage_sums_every_call_of_a_reply() -> None:
    usage = TokenUsage()

    usage.record({"eval_count": 40})  # draft
    usage.record({"eval_count": 25})  # grounding repair

    assert usage.generated_tokens == 65
