"""Environment-backed application configuration with safe defaults."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv


load_dotenv(Path(__file__).resolve().parents[2] / ".env")


def _origins(value: str) -> tuple[str, ...]:
    return tuple(origin.strip() for origin in value.split(",") if origin.strip())


@dataclass(frozen=True)
class Settings:
    app_name: str
    environment: str
    cors_origins: tuple[str, ...]
    max_upload_mb: int
    orchestrator_provider: str
    draft_provider: str
    azure_openai_endpoint: str
    azure_openai_api_key: str
    azure_openai_deployment: str
    copilot_model: str
    github_token: str

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    max_upload_mb = int(os.getenv("MAX_UPLOAD_MB", "10"))
    if not 1 <= max_upload_mb <= 100:
        raise RuntimeError("MAX_UPLOAD_MB는 1~100 사이여야 합니다.")
    return Settings(
        app_name="FabriQ 양산기술 AI 워크벤치",
        environment=os.getenv("APP_ENV", "development"),
        cors_origins=_origins(
            os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
        ),
        max_upload_mb=max_upload_mb,
        orchestrator_provider=os.getenv("ORCHESTRATOR_PROVIDER", "local").lower(),
        draft_provider=os.getenv("DRAFT_PROVIDER", "local").lower(),
        azure_openai_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT", ""),
        azure_openai_api_key=os.getenv("AZURE_OPENAI_API_KEY", ""),
        azure_openai_deployment=os.getenv("AZURE_OPENAI_DEPLOYMENT", ""),
        copilot_model=os.getenv("COPILOT_MODEL", "gpt-5"),
        github_token=os.getenv("GITHUB_TOKEN", ""),
    )
