import asyncio
import os
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends
from starlette.concurrency import run_in_threadpool

from app.api.errors import describe_error
from app.config import Settings, get_settings
from app.services.device import get_device, gpu_name
from app.services.diarization import PIPELINE_NAME
from app.services.factory import get_llm_service, get_model_runner, get_transcription_service
from app.services.interfaces import LlmService, TranscriptionService
from app.services.model_runner import ModelRunner

router = APIRouter(prefix="/api/health", tags=["health"])


@router.get("/live")
def live() -> dict:
    """Cheap liveness probe (used by the Docker healthcheck)."""
    return {"status": "ok"}


def pyannote_cache_present(settings: Settings) -> bool:
    hf_home = Path(os.environ.get("HF_HOME", settings.pyannote_dir))
    repo_dir = "models--" + PIPELINE_NAME.replace("/", "--")
    return (hf_home / "hub" / repo_dir / "snapshots").is_dir()


@router.get("")
async def health(
    settings: Annotated[Settings, Depends(get_settings)],
    llm: Annotated[LlmService, Depends(get_llm_service)],
    stt: Annotated[TranscriptionService, Depends(get_transcription_service)],
    runner: Annotated[ModelRunner, Depends(get_model_runner)],
) -> dict:
    """Full diagnostics: GPU, model files, Ollama reachability and installed LLMs."""
    device = await run_in_threadpool(get_device)
    gpu = await run_in_threadpool(gpu_name)

    try:
        installed, ollama_error = await asyncio.wait_for(llm.list_models(), timeout=5), None
    except Exception as ex:  # noqa: BLE001 - reported to the client
        installed, ollama_error = [], describe_error(ex)

    model_files = stt.model_files()
    pyannote_ok = pyannote_cache_present(settings)
    default_installed = settings.default_llm_model in installed
    healthy = ollama_error is None and default_installed and pyannote_ok and any(model_files.values())

    return {
        "status": "ok" if healthy else "degraded",
        "device": device,
        "gpu": gpu,
        "busy": runner.busy,
        "stt": {
            "models_dir": str(settings.models_dir),
            "models": model_files,
            "pyannote_cached": pyannote_ok,
            "hf_hub_offline": os.environ.get("HF_HUB_OFFLINE") == "1",
        },
        "ollama": {
            "url": settings.ollama_base_url,
            "reachable": ollama_error is None,
            "error": ollama_error,
            "models": installed,
            "default_model": settings.default_llm_model,
            "default_model_installed": default_installed,
        },
    }
