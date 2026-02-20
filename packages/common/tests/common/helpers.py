import asyncio
import inspect
import time
from collections.abc import AsyncIterator

import httpx


class Stream(httpx.AsyncByteStream):
    async def __aiter__(self) -> AsyncIterator[bytes]:
        yield b"data: one\n\n"
        await asyncio.sleep(0)
        yield b"data: two\n\n"

    async def aclose(self) -> None:
        pass


class ErrorStream(httpx.AsyncByteStream):
    async def __aiter__(self) -> AsyncIterator[bytes]:
        yield b'{"error": "chunk1'
        yield b'chunk2"}'

    async def aclose(self) -> None:
        pass


original_perf_counter = time.perf_counter


def selective_perf_counter() -> float:
    """A perf_counter that returns mocked times only when
    called from log_request or log_response."""
    stack = inspect.stack()
    for frame in stack:
        if "log_request" in frame.function:
            return 0.0
        if "log_response" in frame.function:
            return 0.5
    return original_perf_counter()
