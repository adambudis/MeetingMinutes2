"""Test doubles for the LLM and STT services."""

from collections.abc import AsyncIterator
from pathlib import Path
from typing import ClassVar

from app.schemas import LlmMessage, TranscriptSegment


class FakeLlm:
    def __init__(
        self,
        json_responses: list[str] | None = None,
        streams: list[list[str]] | None = None,
        context_length: int | None = 131072,
        models: tuple[str, ...] = ("gemma3:12b",),
    ) -> None:
        self.json_responses = list(json_responses or [])
        self.streams = list(streams or [])
        self.context_length = context_length
        self.models = models
        self.calls: list[tuple[str, list[LlmMessage]]] = []
        self.schemas: list[dict | None] = []

    async def complete_json(self, messages: list[LlmMessage], model: str, schema: dict | None = None) -> str:
        self.calls.append(("json", messages))
        self.schemas.append(schema)
        return self.json_responses.pop(0)

    async def stream(self, messages: list[LlmMessage], model: str) -> AsyncIterator[str]:
        self.calls.append(("stream", messages))
        for token in self.streams.pop(0):
            yield token

    async def get_context_length(self, model: str) -> int | None:
        return self.context_length

    async def list_models(self) -> list[str]:
        return list(self.models)


SEGMENTS = [
    TranscriptSegment(start=0.0, end=2.0, speaker="SPEAKER_00", text="Dobrý den, začneme."),
    TranscriptSegment(start=2.5, end=6.0, speaker="SPEAKER_01", text="Petr připraví návrh do pátku."),
]


class FakeStt:
    available_models: ClassVar[list[str]] = ["canary", "parakeet"]

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str | None]] = []

    def model_files(self) -> dict[str, bool]:
        return {"canary": True, "parakeet": False}

    def warmup(self, models, on_progress) -> None:
        pass

    def transcribe(self, audio_path: str, model: str, language: str | None, on_progress) -> list[TranscriptSegment]:
        assert Path(audio_path).is_file(), "converted WAV must exist while the job runs"
        self.calls.append((audio_path, model, language))
        on_progress("Diarizuji audio...")
        return SEGMENTS
