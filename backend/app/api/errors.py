"""Turn exceptions into short, user-facing (Czech) messages for SSE `error` events."""

import httpx
from ollama import ResponseError

from app.config import get_settings
from app.services.audio import AudioConversionError
from app.services.summarization import SummarizationFailedError


def describe_error(ex: BaseException, llm_model: str | None = None) -> str:
    match ex:
        case SummarizationFailedError() | AudioConversionError() | FileNotFoundError() | ValueError():
            return str(ex)
        case ResponseError(status_code=404):
            return f"Model '{llm_model}' není v Ollama stažen. ({ex.error})"
        case ResponseError():
            return f"Ollama vrátila chybu: {ex.error}"
        case httpx.ConnectError() | httpx.ConnectTimeout() | ConnectionError():
            return f"Nelze se připojit k Ollama ({get_settings().ollama_base_url}). Běží služba?"
        case _:
            return f"{type(ex).__name__}: {ex}"
