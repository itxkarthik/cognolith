import asyncio
from collections.abc import AsyncGenerator

from app.services.chat_generation import SSE_KEEPALIVE, with_sse_keepalive


async def _slow_events(log: list[str]) -> AsyncGenerator[str, None]:
    try:
        yield "first"
        await asyncio.sleep(0.05)
        yield "second"
    except (asyncio.CancelledError, GeneratorExit):
        log.append("cancelled")
        raise


def test_keepalive_is_sent_while_the_stream_is_silent() -> None:
    async def collect() -> list[str]:
        return [event async for event in with_sse_keepalive(_slow_events([]), interval=0.01)]

    events = asyncio.run(collect())

    assert events[0] == "first"
    assert events[-1] == "second"
    assert SSE_KEEPALIVE in events[1:-1]


def test_events_pass_through_unchanged_when_fast() -> None:
    async def fast() -> AsyncGenerator[str, None]:
        for event in ["a", "b", "c"]:
            yield event

    async def collect() -> list[str]:
        return [event async for event in with_sse_keepalive(fast(), interval=1)]

    assert asyncio.run(collect()) == ["a", "b", "c"]


def test_closing_the_stream_cancels_the_generator() -> None:
    log: list[str] = []

    async def disconnect_after_first_keepalive() -> None:
        stream = with_sse_keepalive(_slow_events(log), interval=0.01)
        assert await anext(stream) == "first"
        assert await anext(stream) == SSE_KEEPALIVE
        await stream.aclose()

    asyncio.run(disconnect_after_first_keepalive())

    assert log == ["cancelled"]
