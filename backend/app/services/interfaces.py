"""Service contracts mirroring the C# interfaces (ITranscriptionService, ILlmService, ISummarizationService).

The C# versions report progress through callbacks (Action<string>, Action<int,int>).
In Python the async parts are async generators that yield events instead, which makes
cancellation on client disconnect automatic.
"""

from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from typing import Protocol

from app.schemas import LlmMessage, SummarizationResult, TranscriptSegment

ProgressCallback = Callable[[str], None]


@dataclass(frozen=True, slots=True)
class ChunkStarted:
    current: int
    total: int


@dataclass(frozen=True, slots=True)
class Token:
    text: str


@dataclass(frozen=True, slots=True)
class Done:
    result: SummarizationResult


SummaryEvent = ChunkStarted | Token | Done


class TranscriptionService(Protocol):
    @property
    def available_models(self) -> list[str]: ...

    def model_files(self) -> dict[str, bool]:
        """Model name -> whether its weights file is present on disk."""
        ...

    def warmup(self, models: list[str], on_progress: ProgressCallback) -> None:
        """Preload the diarization pipeline and the given ASR models (blocking)."""
        ...

    def transcribe(
        self,
        audio_path: str,
        model: str,
        language: str | None,
        on_progress: ProgressCallback,
    ) -> list[TranscriptSegment]:
        """Blocking call; run it on the model worker thread (see ModelRunner)."""
        ...


class LlmService(Protocol):
    def stream(self, messages: list[LlmMessage], model: str) -> AsyncIterator[str]: ...

    async def complete_json(self, messages: list[LlmMessage], model: str, schema: dict | None = None) -> str:
        """Non-streaming completion constrained to JSON (to `schema` when given)."""
        ...

    async def get_context_length(self, model: str) -> int | None: ...

    async def list_models(self) -> list[str]: ...


class SummarizationService(Protocol):
    def summarize(
        self,
        transcript: str,
        model: str,
        segments: list[TranscriptSegment] | None,
    ) -> AsyncIterator[SummaryEvent]: ...

    def continue_chat(self, messages: list[LlmMessage], model: str) -> AsyncIterator[str]: ...
