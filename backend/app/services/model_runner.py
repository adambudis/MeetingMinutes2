"""Runs blocking model jobs on one dedicated thread and streams their progress to async code.

A single worker means only one model job uses the GPU at a time; further requests wait in the
queue. Jobs are submitted eagerly (before the HTTP response starts streaming), so a job always
runs its own cleanup even if the client disconnects. A job that is still queued when its client
goes away is skipped.
"""

import asyncio
import logging
import threading
from collections.abc import AsyncIterator, Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Generic, TypeVar

from app.services.interfaces import ProgressCallback

log = logging.getLogger(__name__)

T = TypeVar("T")

QUEUED_MESSAGE = "Server zpracovává jiný požadavek, čekám ve frontě..."


class JobCancelledError(Exception):
    """The job was cancelled before it started executing."""


@dataclass(frozen=True, slots=True)
class Progress:
    message: str


@dataclass(frozen=True)
class Finished(Generic[T]):
    value: T


class ModelJob(Generic[T]):
    """Handle for a submitted job: progress events + result, consumable once via `events()`."""

    def __init__(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._cancelled = threading.Event()
        self.future: asyncio.Future[T] | None = None

    @property
    def cancelled(self) -> bool:
        return self._cancelled.is_set()

    def cancel(self) -> None:
        """Skip the job if it has not started yet (a running job always finishes)."""
        self._cancelled.set()

    def report(self, message: str) -> None:
        """Thread-safe progress reporting, called from the worker thread."""
        try:
            self._loop.call_soon_threadsafe(self._queue.put_nowait, message)
        except RuntimeError:  # event loop already closed (shutdown)
            log.debug("progress dropped: %s", message)

    async def events(self) -> AsyncIterator[Progress | Finished[T]]:
        """Yield Progress events, then one Finished (re-raises the job's exception)."""
        assert self.future is not None, "job was not submitted"
        future = self.future
        getter: asyncio.Future[str] | None = None
        try:
            while not future.done():
                getter = asyncio.ensure_future(self._queue.get())
                done, _ = await asyncio.wait({getter, future}, return_when=asyncio.FIRST_COMPLETED)
                if getter in done:
                    message = getter.result()
                    getter = None
                    yield Progress(message)
            while not self._queue.empty():
                yield Progress(self._queue.get_nowait())
            yield Finished(future.result())
        finally:
            if getter is not None and not getter.done():
                getter.cancel()
            self.cancel()


class ModelRunner:
    def __init__(self) -> None:
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="model-worker")
        self._pending = 0  # only touched from the event-loop thread

    @property
    def busy(self) -> bool:
        return self._pending > 0

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)

    def submit(
        self,
        job: Callable[[ProgressCallback], T],
        cleanup: Callable[[], None] | None = None,
    ) -> ModelJob[T]:
        """Queue `job(report)` on the worker thread. `cleanup` always runs on the worker afterwards."""
        loop = asyncio.get_running_loop()
        handle: ModelJob[T] = ModelJob(loop)

        def execute() -> T:
            try:
                if handle.cancelled:
                    raise JobCancelledError()
                return job(handle.report)
            finally:
                if cleanup is not None:
                    try:
                        cleanup()
                    except Exception:
                        log.exception("job cleanup failed")

        if self._pending > 0:
            handle.report(QUEUED_MESSAGE)
        self._pending += 1
        handle.future = loop.run_in_executor(self._executor, execute)
        handle.future.add_done_callback(self._on_done)
        return handle

    def _on_done(self, future: asyncio.Future) -> None:
        self._pending -= 1
        # Retrieve the exception so abandoned jobs don't log "exception was never retrieved".
        ex = None if future.cancelled() else future.exception()
        if ex is not None and not isinstance(ex, JobCancelledError):
            log.error("model job failed: %s", ex)
