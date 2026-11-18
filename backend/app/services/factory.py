"""Equivalent of the C# ServiceFactory: one place that wires concrete services.

Each provider returns a process-wide singleton and doubles as a FastAPI dependency,
so tests can swap implementations via `app.dependency_overrides`.
"""

from functools import lru_cache

from app.config import get_settings
from app.services.interfaces import LlmService, SummarizationService, TranscriptionService
from app.services.model_runner import ModelRunner
from app.services.ollama_llm import OllamaLlmService
from app.services.summarization import MapReduceSummarizationService
from app.services.transcription import NemoTranscriptionService


@lru_cache
def get_llm_service() -> LlmService:
    s = get_settings()
    return OllamaLlmService(s.ollama_base_url, temperature=s.llm_temperature, num_ctx=s.llm_num_ctx)


@lru_cache
def get_summarization_service() -> SummarizationService:
    return MapReduceSummarizationService(get_llm_service())


@lru_cache
def get_transcription_service() -> TranscriptionService:
    s = get_settings()
    # Compose passes HF_TOKEN="" when unset; treat that as "no token".
    return NemoTranscriptionService(s.canary_path, s.parakeet_path, hf_token=s.hf_token or None)


@lru_cache
def get_model_runner() -> ModelRunner:
    return ModelRunner()
