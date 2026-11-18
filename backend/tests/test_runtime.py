"""ModelRunner (single GPU worker) and the SSE heartbeat wrapper."""

import asyncio
import threading

from app.services.model_runner import QUEUED_MESSAGE, Finished, JobCancelledError, ModelRunner, Progress
from app.services.transcription import merge_adjacent_turns, merge_short_turns
from app.utils.sse import HEARTBEAT, _with_heartbeat


def test_runner_streams_progress_then_result() -> None:
    async def main() -> list:
        runner = ModelRunner()
        try:
            def job(report):
                report("a")
                report("b")
                return 42

            return [e async for e in runner.submit(job).events()]
        finally:
            runner.shutdown()

    assert asyncio.run(main()) == [Progress("a"), Progress("b"), Finished(42)]


def test_queued_job_is_skipped_after_cancel_but_still_cleaned_up() -> None:
    async def main() -> tuple[list[str], list]:
        runner = ModelRunner()
        release = threading.Event()
        ran: list[str] = []
        cleaned: list[str] = []
        try:
            first = runner.submit(lambda _r: release.wait(5) and ran.append("first"))
            second = runner.submit(lambda _r: ran.append("second"), cleanup=lambda: cleaned.append("second"))
            second.cancel()
            release.set()
            [e async for e in first.events()]
            events = []
            try:
                async for e in second.events():
                    events.append(e)
            except JobCancelledError:
                events.append("cancelled")
            return ran + cleaned, events
        finally:
            runner.shutdown()

    log, events = asyncio.run(main())
    assert log == ["first", "second"]  # "second" here comes from cleanup only
    assert events == [Progress(QUEUED_MESSAGE), "cancelled"]


def test_heartbeat_fills_silence() -> None:
    async def slow():
        await asyncio.sleep(0.35)
        yield "data"

    async def main() -> list[str]:
        return [f async for f in _with_heartbeat(slow(), interval=0.1)]

    frames = asyncio.run(main())
    assert frames[-1] == "data"
    assert frames.count(HEARTBEAT) >= 2


def test_turn_merging_rules() -> None:
    turns = [(0.0, 1.0, "A"), (1.0, 1.1, "B"), (1.5, 3.0, "A"), (5.0, 6.0, "A"), (6.2, 7.0, "B")]
    short_merged = merge_short_turns(turns)  # the 0.1 s "B" blip is folded into the previous turn
    assert short_merged == [(0.0, 1.1, "A"), (1.5, 3.0, "A"), (5.0, 6.0, "A"), (6.2, 7.0, "B")]
    # same speaker, gap < 1.5 s -> merged; gap of 2 s -> kept apart
    assert merge_adjacent_turns(short_merged) == [(0.0, 3.0, "A"), (5.0, 6.0, "A"), (6.2, 7.0, "B")]
