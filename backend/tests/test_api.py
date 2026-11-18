import io
import shutil
import wave
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.services.summarization import FOLLOWUP_SYSTEM_PROMPT
from tests.conftest import parse_sse
from tests.fakes import FakeLlm, FakeStt

needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")


def _wav_bytes(seconds: float = 0.5, rate: int = 44100) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x00" * 2 * int(rate * seconds))
    return buf.getvalue()


class TestTranscribe:
    @needs_ffmpeg
    def test_streams_progress_and_segments_and_cleans_up(self, client: TestClient, fake_stt: FakeStt) -> None:
        res = client.post(
            "/api/transcribe",
            files={"file": ("schuzka.wav", _wav_bytes(), "audio/wav")},
            data={"model": "canary", "language": "en"},
        )
        assert res.status_code == 200
        assert res.headers["content-type"].startswith("text/event-stream")
        events = parse_sse(res.text)
        assert [e for e, _ in events] == ["progress", "progress", "result"]
        assert events[0][1] == {"message": "Konvertuji soubor..."}
        assert events[-1][1]["segments"][1]["text"] == "Petr připraví návrh do pátku."

        audio_path, model, language = fake_stt.calls[0]
        assert (model, language) == ("canary", "en")
        assert not Path(audio_path).parent.exists(), "upload work dir must be removed"

    @needs_ffmpeg
    def test_language_is_ignored_for_parakeet(self, client: TestClient, fake_stt: FakeStt) -> None:
        client.post("/api/transcribe", files={"file": ("a.wav", _wav_bytes())}, data={"model": "parakeet"})
        assert fake_stt.calls[0][1:] == ("parakeet", None)

    @needs_ffmpeg
    def test_undecodable_audio_reports_error_event(self, client: TestClient) -> None:
        res = client.post("/api/transcribe", files={"file": ("a.mp3", b"definitely not audio")})
        (event, data), = parse_sse(res.text)[-1:]
        assert event == "error" and "Konverze audia selhala" in data["message"]

    def test_rejects_unsupported_extension(self, client: TestClient) -> None:
        res = client.post("/api/transcribe", files={"file": ("notes.txt", b"hello")})
        assert res.status_code == 400

    def test_rejects_empty_file(self, client: TestClient) -> None:
        res = client.post("/api/transcribe", files={"file": ("empty.wav", b"")})
        assert res.status_code == 400

    def test_rejects_unknown_model(self, client: TestClient) -> None:
        res = client.post("/api/transcribe", files={"file": ("a.wav", b"x")}, data={"model": "whisper"})
        assert res.status_code == 422

    def test_models_endpoint(self, client: TestClient) -> None:
        models = client.get("/api/transcribe/models").json()["models"]
        assert models[0] == {"name": "canary", "available": True, "languages": ["cs", "en"]}


class TestSummarize:
    def test_event_sequence_with_context_warning(self, client: TestClient, fake_llm: FakeLlm) -> None:
        fake_llm.context_length = 10  # tiny limit -> warning
        fake_llm.json_responses = ['{"tasks": []}', "[]"]
        fake_llm.streams = [["# Souhrn", " schůzky\n"]]
        res = client.post("/api/summarize", json={
            "transcript": "",
            "model": "gemma3:4b",
            "segments": [{"start": 0, "speaker": "Petr", "text": "Ahoj všichni, dnes probereme rozpočet."}],
        })
        events = parse_sse(res.text)
        assert [e for e, _ in events] == ["warning", "chunk", "token", "token", "done"]
        assert "gemma3:4b" in events[0][1]["message"]
        assert events[1][1] == {"current": 1, "total": 1}
        assert events[-1][1]["markdown"].startswith("# Souhrn schůzky\n")
        assert events[-1][1]["map_success_ratio"] == 1.0

    def test_failure_becomes_error_event(self, client: TestClient, fake_llm: FakeLlm) -> None:
        fake_llm.json_responses = ["bad", "bad"]
        events = parse_sse(client.post("/api/summarize", json={"transcript": "A: ahoj"}).text)
        assert events[-1] == ("error", {"message": "Nepodařilo se zpracovat žádný chunk transkripce"})

    def test_empty_transcript_is_rejected(self, client: TestClient) -> None:
        assert client.post("/api/summarize", json={"transcript": "  "}).status_code == 400


class TestChat:
    def test_prepends_followup_prompt_and_streams(self, client: TestClient, fake_llm: FakeLlm) -> None:
        fake_llm.streams = [["Ano", "."]]
        res = client.post("/api/chat", json={"messages": [
            {"role": "system", "content": "client-supplied system prompts are dropped"},
            {"role": "user", "content": "Vytvoř shrnutí schůzky."},
            {"role": "assistant", "content": "# Souhrn"},
            {"role": "user", "content": "Kdo má úkoly?"},
        ]})
        assert parse_sse(res.text) == [("token", {"text": "Ano"}), ("token", {"text": "."}), ("done", {"text": "Ano."})]
        sent = fake_llm.calls[0][1]
        assert sent[0].role == "system" and sent[0].content == FOLLOWUP_SYSTEM_PROMPT
        assert [m.role for m in sent] == ["system", "user", "assistant", "user"]

    def test_empty_conversation_is_rejected(self, client: TestClient) -> None:
        assert client.post("/api/chat", json={"messages": []}).status_code == 400


def test_health_reports_components(client: TestClient) -> None:
    body = client.get("/api/health").json()
    assert body["ollama"]["reachable"] is True
    assert body["ollama"]["default_model_installed"] is True
    assert body["stt"]["models"] == {"canary": True, "parakeet": False}
    assert body["device"] in {"cpu", "cuda"}
    assert client.get("/api/health/live").json() == {"status": "ok"}


def test_llm_models(client: TestClient) -> None:
    assert client.get("/api/llm/models").json() == {"default": "gemma3:12b", "installed": ["gemma3:12b"], "error": None}
