import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.api.errors import describe_error
from app.config import Settings, get_settings
from app.schemas import ChatRequest, LlmMessage, SummarizeRequest
from app.services.factory import get_llm_service, get_summarization_service
from app.services.interfaces import ChunkStarted, Done, LlmService, SummarizationService, Token
from app.services.summarization import CHARS_PER_TOKEN, FOLLOWUP_SYSTEM_PROMPT, format_for_llm
from app.utils.sse import sse_event, sse_response

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["llm"])

CONTEXT_WARNING_RATIO = 0.8

Llm = Annotated[LlmService, Depends(get_llm_service)]
Summarizer = Annotated[SummarizationService, Depends(get_summarization_service)]
AppSettings = Annotated[Settings, Depends(get_settings)]


@router.get("/llm/models")
async def llm_models(llm: Llm, settings: AppSettings) -> dict:
    try:
        installed, error = await llm.list_models(), None
    except Exception as ex:  # noqa: BLE001 - reported to the client
        installed, error = [], describe_error(ex)
    return {"default": settings.default_llm_model, "installed": installed, "error": error}


async def _context_warning(llm: LlmService, model: str, text: str) -> dict | None:
    """Same heuristic as the WPF client: chars/4 tokens vs. 80 % of the model's context."""
    est_tokens = len(text) // CHARS_PER_TOKEN
    ctx_limit = await llm.get_context_length(model)
    if ctx_limit and est_tokens > ctx_limit * CONTEXT_WARNING_RATIO:
        return {
            "message": f"Přepis (~{est_tokens} tokenů) se blíží limitu modelu {model} ({ctx_limit}). Zvaž větší model.",
            "est_tokens": est_tokens,
            "ctx_limit": ctx_limit,
        }
    return None


@router.post("/summarize")
async def summarize(req: SummarizeRequest, llm: Llm, summarizer: Summarizer, settings: AppSettings):
    """Map-reduce summary. Streams SSE events: optional `warning`, `chunk {current,total}`,
    `token {text}` ..., then `done {markdown, map_success_ratio}` or `error {message}`.
    """
    model = req.model or settings.default_llm_model
    segments = req.segments or None
    llm_input = format_for_llm(segments) if segments else req.transcript
    if not llm_input.strip():
        raise HTTPException(400, "Není k dispozici žádný přepis.")

    async def frames():
        try:
            if warning := await _context_warning(llm, model, llm_input):
                yield sse_event("warning", warning)
            async for event in summarizer.summarize(req.transcript, model, segments):
                match event:
                    case ChunkStarted(current=current, total=total):
                        yield sse_event("chunk", {"current": current, "total": total})
                    case Token(text=text):
                        yield sse_event("token", {"text": text})
                    case Done(result=result):
                        yield sse_event("done", result.model_dump())
        except Exception as ex:
            log.exception("summarization failed")
            yield sse_event("error", {"message": describe_error(ex, model)})

    return sse_response(frames())


@router.post("/chat")
async def chat(req: ChatRequest, summarizer: Summarizer, settings: AppSettings):
    """Follow-up question over the conversation. Streams `token {text}` ..., then `done {text}` or `error`."""
    model = req.model or settings.default_llm_model
    history = [m for m in req.messages if m.role != "system"]
    if not history:
        raise HTTPException(400, "Konverzace je prázdná.")
    messages = [LlmMessage(role="system", content=FOLLOWUP_SYSTEM_PROMPT), *history]

    async def frames():
        parts: list[str] = []
        try:
            async for token in summarizer.continue_chat(messages, model):
                parts.append(token)
                yield sse_event("token", {"text": token})
            yield sse_event("done", {"text": "".join(parts)})
        except Exception as ex:
            log.exception("chat failed")
            yield sse_event("error", {"message": describe_error(ex, model)})

    return sse_response(frames())
