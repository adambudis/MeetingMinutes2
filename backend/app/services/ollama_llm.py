"""Port of OllamaLlmService.cs."""

import logging
from collections.abc import AsyncIterator

from ollama import AsyncClient

from app.schemas import LlmMessage

log = logging.getLogger(__name__)

# Used when Ollama's /api/show does not report a context length.
_FALLBACK_CONTEXT: tuple[tuple[str, int], ...] = (
    ("gemma3:", 131072),
    ("qwen2.5:", 32768),
    ("llama3.1:", 131072),
    ("llama3.2:", 131072),
    ("mistral:", 32768),
    ("phi3.5:", 131072),
    ("phi3:", 4096),
)


class OllamaLlmService:
    def __init__(self, base_url: str, temperature: float = 0.3, num_ctx: int = 65536) -> None:
        self._client = AsyncClient(host=base_url, timeout=None)
        self._options = {"temperature": temperature, "num_ctx": num_ctx}

    @staticmethod
    def _to_wire(messages: list[LlmMessage]) -> list[dict[str, str]]:
        return [{"role": m.role, "content": m.content} for m in messages]

    async def stream(self, messages: list[LlmMessage], model: str) -> AsyncIterator[str]:
        response = await self._client.chat(
            model=model,
            messages=self._to_wire(messages),
            stream=True,
            options=self._options,
        )
        async for chunk in response:
            content = chunk.message.content if chunk.message else None
            if content:
                yield content

    async def complete_json(self, messages: list[LlmMessage], model: str, schema: dict | None = None) -> str:
        # A JSON schema makes Ollama constrain decoding to that exact shape (structured outputs);
        # plain "json" only guarantees syntactically valid JSON.
        response = await self._client.chat(
            model=model,
            messages=self._to_wire(messages),
            stream=False,
            format=schema or "json",
            options=self._options,
        )
        return response.message.content or ""

    async def get_context_length(self, model: str) -> int | None:
        try:
            info = await self._client.show(model)
            for key, value in (info.modelinfo or {}).items():
                if key == "context_length" or key.endswith(".context_length"):
                    try:
                        return int(value)
                    except (TypeError, ValueError):
                        pass
        except Exception as ex:  # noqa: BLE001 - fall back to the static map
            log.debug("show(%s) failed: %s", model, ex)

        for prefix, ctx in _FALLBACK_CONTEXT:
            if model.lower().startswith(prefix):
                return ctx
        log.debug("Unknown model %s, context limit unavailable", model)
        return None

    async def list_models(self) -> list[str]:
        response = await self._client.list()
        return [m.model for m in response.models if m.model]
