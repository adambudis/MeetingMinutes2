from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# <repo>/models when running from a checkout; resolves to /models inside the container (/app/app/config.py).
_DEFAULT_MODELS_DIR = Path(__file__).resolve().parents[2] / "models"


class Settings(BaseSettings):
    """Runtime configuration from environment variables (or backend/.env for local development)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    ollama_base_url: str = "http://localhost:11434"
    default_llm_model: str = "gemma3:12b"
    llm_temperature: float = 0.3
    llm_num_ctx: int = 65536

    models_dir: Path = _DEFAULT_MODELS_DIR
    hf_token: str | None = None
    # None = auto: go offline when the pyannote cache is present (same rule as the original app.py).
    hf_hub_offline: bool | None = None

    max_upload_mb: int = 500
    # Comma-separated ASR models to preload at startup, e.g. "canary" or "canary,parakeet". Empty = lazy.
    warmup_models: str = ""

    cors_origins: list[str] = []
    log_level: str = "INFO"

    @property
    def pyannote_dir(self) -> Path:
        return self.models_dir / "pyannote"

    @property
    def canary_path(self) -> Path:
        return self.models_dir / "canary-1b-v2.nemo"

    @property
    def parakeet_path(self) -> Path:
        return self.models_dir / "parakeet-tdt-0.6b-v3.nemo"

    @property
    def warmup_model_list(self) -> list[str]:
        return [m.strip() for m in self.warmup_models.split(",") if m.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
