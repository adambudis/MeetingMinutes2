import json
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.factory import (
    get_llm_service,
    get_model_runner,
    get_summarization_service,
    get_transcription_service,
)
from app.services.model_runner import ModelRunner
from app.services.summarization import MapReduceSummarizationService
from tests.fakes import FakeLlm, FakeStt


@pytest.fixture
def fake_llm() -> FakeLlm:
    return FakeLlm()


@pytest.fixture
def fake_stt() -> FakeStt:
    return FakeStt()


@pytest.fixture
def client(fake_llm: FakeLlm, fake_stt: FakeStt) -> Iterator[TestClient]:
    runner = ModelRunner()
    app.dependency_overrides[get_llm_service] = lambda: fake_llm
    app.dependency_overrides[get_summarization_service] = lambda: MapReduceSummarizationService(fake_llm)
    app.dependency_overrides[get_transcription_service] = lambda: fake_stt
    app.dependency_overrides[get_model_runner] = lambda: runner
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()
        runner.shutdown()


def parse_sse(body: str) -> list[tuple[str, dict]]:
    """Parse an SSE body into (event, data) tuples, skipping comments/heartbeats."""
    events = []
    for block in body.split("\n\n"):
        name, data = "message", []
        for line in block.split("\n"):
            if not line or line.startswith(":"):
                continue
            field, _, value = line.partition(":")
            value = value.removeprefix(" ")
            if field == "event":
                name = value
            elif field == "data":
                data.append(value)
        if data:
            events.append((name, json.loads("\n".join(data))))
    return events
