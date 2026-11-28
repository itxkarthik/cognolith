"""Run a coroutine from synchronous code in a worker thread."""

import asyncio
from collections.abc import Coroutine
from typing import Any


def run_coroutine_sync[T](coro: Coroutine[Any, Any, T]) -> T:
    """
    Run `coro` to completion on a fresh event loop and return its result.

    For sync code that FastAPI or `asyncio.to_thread` runs in a worker thread, such as
    retrieval calling the async embedding client. On the event loop's own thread it
    would block every other request until the coroutine finished, so that raises.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    coro.close()
    raise RuntimeError(
        "run_coroutine_sync was called on the event loop; await the coroutine instead"
    )
