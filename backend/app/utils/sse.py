"""Server-Sent Events helpers."""

import asyncio
import contextlib
import json
from collections.abc import AsyncIterator
from typing import Any

from fastapi.responses import StreamingResponse
from starlette.background import BackgroundTask

HEARTBEAT_INTERVAL_S = 15.0
HEARTBEAT = ": keep-alive\n\n"
_END = object()


def sse_event(event: str, data: Any) -> str:
    """Format one SSE frame. `json.dumps` never emits raw newlines, so one data line suffices."""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def _with_heartbeat(frames: AsyncIterator[str], interval: float) -> AsyncIterator[str]:
    """Forward `frames`, inserting an SSE comment whenever the source is silent for `interval` s.

    Long model steps (loading a model, one map chunk) can be silent for minutes; periodic
    traffic keeps reverse proxies from dropping the idle connection. The source generator
    runs inside a single producer task for its whole life, and is cancelled when the client
    disconnects (the consumer is cancelled by Starlette).
    """
    queue: asyncio.Queue[Any] = asyncio.Queue()

    async def produce() -> None:
        try:
            async for frame in frames:
                queue.put_nowait(frame)
        finally:
            queue.put_nowait(_END)

    producer = asyncio.create_task(produce())
    try:
        while True:
            try:
                frame = await asyncio.wait_for(queue.get(), timeout=interval)
            except TimeoutError:
                yield HEARTBEAT
                continue
            if frame is _END:
                break
            yield frame
        await producer  # re-raise unexpected producer errors
    finally:
        if not producer.done():
            producer.cancel()
            with contextlib.suppress(BaseException):
                await producer


def sse_response(
    frames: AsyncIterator[str],
    background: BackgroundTask | None = None,
    heartbeat_interval: float = HEARTBEAT_INTERVAL_S,
) -> StreamingResponse:
    return StreamingResponse(
        _with_heartbeat(frames, heartbeat_interval),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        background=background,
    )
