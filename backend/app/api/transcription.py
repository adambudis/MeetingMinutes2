import logging
import shutil
import tempfile
from pathlib import Path
from typing import Annotated, BinaryIO

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from starlette.background import BackgroundTask
from starlette.concurrency import run_in_threadpool

from app.api.errors import describe_error
from app.config import Settings, get_settings
from app.schemas import Language, TranscriptionModel
from app.services.audio import ALLOWED_EXTENSIONS, convert_to_wav
from app.services.factory import get_model_runner, get_transcription_service
from app.services.interfaces import ProgressCallback, TranscriptionService
from app.services.model_runner import ModelRunner, Progress
from app.utils.sse import sse_event, sse_response

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["transcription"])


@router.get("/transcribe/models")
def transcription_models(stt: Annotated[TranscriptionService, Depends(get_transcription_service)]) -> dict:
    files = stt.model_files()
    return {
        "models": [
            {
                "name": name,
                "available": files.get(name, False),
                "languages": ["cs", "en"] if name == "canary" else [],
            }
            for name in stt.available_models
        ]
    }


def _save_upload(source: BinaryIO, target: Path) -> int:
    with target.open("wb") as out:
        shutil.copyfileobj(source, out, length=1024 * 1024)
    return target.stat().st_size


@router.post("/transcribe")
async def transcribe(
    file: Annotated[UploadFile, File(description="Audio/video soubor")],
    stt: Annotated[TranscriptionService, Depends(get_transcription_service)],
    runner: Annotated[ModelRunner, Depends(get_model_runner)],
    settings: Annotated[Settings, Depends(get_settings)],
    model: Annotated[TranscriptionModel, Form()] = "canary",
    language: Annotated[Language, Form()] = "cs",
):
    """Transcribe + diarize an uploaded recording. Streams SSE events:
    `progress {message}` ..., then `result {segments}` or `error {message}`.
    """
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        allowed = ", ".join(sorted(ALLOWED_EXTENSIONS))
        raise HTTPException(400, f"Nepodporovaný typ souboru '{ext or '?'}'. Povoleno: {allowed}")
    max_bytes = settings.max_upload_mb * 1024 * 1024
    if file.size is not None and file.size > max_bytes:
        raise HTTPException(413, f"Soubor je větší než {settings.max_upload_mb} MB.")

    # The UploadFile is closed once this handler returns, so persist it before streaming starts.
    work_dir = Path(tempfile.mkdtemp(prefix="mm-upload-"))
    source = work_dir / f"input{ext}"
    try:
        size = await run_in_threadpool(_save_upload, file.file, source)
        if size == 0:
            raise HTTPException(400, "Soubor je prázdný.")
    except BaseException:
        shutil.rmtree(work_dir, ignore_errors=True)
        raise

    def job(report: ProgressCallback):
        report("Konvertuji soubor...")
        wav = work_dir / "audio.wav"
        convert_to_wav(source, wav)
        return stt.transcribe(str(wav), model, language if model == "canary" else None, report)

    handle = runner.submit(job, cleanup=lambda: shutil.rmtree(work_dir, ignore_errors=True))

    async def frames():
        try:
            async for event in handle.events():
                if isinstance(event, Progress):
                    yield sse_event("progress", {"message": event.message})
                else:
                    yield sse_event("result", {"segments": [s.model_dump() for s in event.value]})
        except Exception as ex:
            log.exception("transcription failed")
            yield sse_event("error", {"message": describe_error(ex)})

    # If the client is gone before streaming starts, drop the job while it is still queued.
    return sse_response(frames(), background=BackgroundTask(handle.cancel))
