import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.database_url import DatabaseTarget, normalize_database_url

REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND_ROOT = Path(__file__).resolve().parents[2]


def _settings_env_files() -> tuple[Path, ...]:
    # Never load a shipped .env on Vercel; process env is the source of truth.
    if os.environ.get("VERCEL") == "1":
        return ()
    return (REPO_ROOT / ".env", BACKEND_ROOT / ".env")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_settings_env_files(),
        env_file_encoding="utf-8",
        extra="ignore",
        enable_decoding=False,
        env_ignore_empty=True,
    )

    app_name: str = "job-agent"
    app_env: Literal["development", "production", "test"] = "development"
    app_version: str = "0.1.0"
    log_level: str = "INFO"
    log_json: bool = False
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    cors_origins: str = "http://localhost:3000"

    database_url: str = "postgresql+asyncpg://jobagent:jobagent@localhost:5434/jobagent"
    redis_url: str | None = None

    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    score_notify_threshold: int = 80
    score_apply_threshold: int = 80
    score_review_threshold: int = 60
    evidence_half_life_days: int = 180
    http_timeout_seconds: float = 20.0
    collector_pause_seconds: float = 0.35
    # ATS detection probes many dead subdomains, so it uses a tighter timeout
    # and a small amount of concurrency across different ATS hosts.
    detect_timeout_seconds: float = 8.0
    detect_pause_seconds: float = 0.25
    detect_concurrency: int = 2

    @field_validator("log_level")
    @classmethod
    def normalize_log_level(cls, value: str) -> str:
        return value.upper()

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: object) -> object:
        if value is None:
            return "http://localhost:3000"
        if isinstance(value, list):
            return ",".join(str(part) for part in value)
        return value

    @property
    def cors_origin_list(self) -> list[str]:
        stripped = self.cors_origins.strip()
        if stripped.startswith("["):
            import json

            try:
                parsed = json.loads(stripped)
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, list):
                return [str(part).strip() for part in parsed if str(part).strip()]
        return [part.strip() for part in stripped.split(",") if part.strip()]

    @field_validator("redis_url", mode="before")
    @classmethod
    def empty_redis_url(cls, value: object) -> object:
        if value == "":
            return None
        return value

    @property
    def database_target(self) -> DatabaseTarget:
        return normalize_database_url(self.database_url)

    @property
    def database_url_str(self) -> str:
        return self.database_target.url

    @property
    def redis_configured(self) -> bool:
        return bool(self.redis_url)

    @property
    def redis_url_str(self) -> str:
        if not self.redis_url:
            raise RuntimeError("REDIS_URL is not configured")
        return self.redis_url

    @property
    def is_development(self) -> bool:
        return self.app_env == "development"


@lru_cache
def get_settings() -> Settings:
    return Settings()
