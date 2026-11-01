"""Worker settings, read from config/local.env.

Spec: specs/02-architecture.md#storage-replaces-minio
"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    """Paths are relative to the project root unless absolute."""

    model_config = SettingsConfigDict(env_file=ROOT / "config" / "local.env", extra="ignore")

    backend_port: int = 8080
    worker_host: str = "127.0.0.1"
    worker_port: int = 8090
    ollama_url: str = "http://127.0.0.1:11500"
    media_dir: Path = Path("media")
    logs_dir: Path = Path("logs")
    models_dir: Path = Path("models")
    worker_token: str = Field(min_length=1)

    @property
    def backend_url(self) -> str:
        return f"http://127.0.0.1:{self.backend_port}"

    def resolved(self, path: Path) -> Path:
        return path if path.is_absolute() else ROOT / path
