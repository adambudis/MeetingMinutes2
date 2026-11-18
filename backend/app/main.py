"""FastAPI entry point: `uvicorn app.main:app` (run with a single worker - models live in-process)."""

import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import Settings, get_settings

log = logging.getLogger("app")


def configure_environment(settings: Settings) -> None:
    """Port of python/app.py `_configure_environment`.

    Points the Hugging Face cache at the bundled pyannote models and switches the hub to
    offline mode when they are present. Must run before huggingface_hub is imported
    (the ML libraries are imported lazily, so module import time is early enough).
    """
    hf_home = Path(os.environ.setdefault("HF_HOME", str(settings.pyannote_dir)))
    if settings.hf_token:
        os.environ.setdefault("HF_TOKEN", settings.hf_token)
    offline = settings.hf_hub_offline
    if offline is None:
        offline = (hf_home / "hub" / "models--pyannote--speaker-diarization-3.1" / "snapshots").is_dir()
    if offline:
        os.environ["HF_HUB_OFFLINE"] = "1"


settings = get_settings()
logging.basicConfig(level=settings.log_level.upper(), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
configure_environment(settings)

# Imported after configure_environment on purpose (see its docstring).
from app.api import health, summarization, transcription  # noqa: E402
from app.services.factory import get_model_runner, get_transcription_service  # noqa: E402


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    log.info("models_dir=%s ollama=%s offline=%s", settings.models_dir, settings.ollama_base_url,
             os.environ.get("HF_HUB_OFFLINE") == "1")
    runner = get_model_runner()
    if models := settings.warmup_model_list:
        stt = get_transcription_service()
        runner.submit(lambda _report: stt.warmup(models, lambda msg: log.info("warmup: %s", msg)))
    yield
    runner.shutdown()


app = FastAPI(
    title="MeetingMinutes API",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
    redoc_url=None,
)

if settings.cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(transcription.router)
app.include_router(summarization.router)
app.include_router(health.router)
