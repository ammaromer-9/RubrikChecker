from functools import lru_cache
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

EFFORT_LEVELS = ("low", "medium", "high", "xhigh", "max")


class Settings(BaseSettings):
    """Application settings, read from environment variables / a .env file.

    Bad values fail at startup with a clear message instead of misbehaving later.
    """

    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore")

    database_url: str = "postgresql+asyncpg://rubriccheck:rubriccheck@localhost:5432/rubriccheck"
    test_database_url: str = (
        "postgresql+asyncpg://rubriccheck:rubriccheck@localhost:5432/rubriccheck_test"
    )
    anthropic_api_key: str = ""
    anthropic_model: str = ""
    # Thinking depth: low | medium | high | xhigh | max. Empty uses the model's default.
    anthropic_effort: str = "medium"
    llm_timeout_seconds: Annotated[float, Field(gt=0, le=900)] = 120.0
    llm_max_retries: Annotated[int, Field(ge=0, le=10)] = 3
    grading_runs: Annotated[int, Field(ge=1, le=7)] = 3
    grading_concurrency: Annotated[int, Field(ge=1, le=50)] = 5
    # A grading still "running" after this long is assumed dead (e.g. the server restarted).
    grading_stale_minutes: Annotated[int, Field(ge=1)] = 30
    feedback_max_quoted_words: Annotated[int, Field(ge=5)] = 25
    max_draft_chars: Annotated[int, Field(ge=100)] = 50_000
    max_assignment_text_chars: Annotated[int, Field(ge=100)] = 20_000
    max_upload_bytes: Annotated[int, Field(ge=1024)] = 5 * 1024 * 1024
    cors_origins: str = "http://localhost:5173"
    log_level: str = "INFO"

    @field_validator("anthropic_effort")
    @classmethod
    def _valid_effort(cls, value: str) -> str:
        value = value.strip().lower()
        if value and value not in EFFORT_LEVELS:
            raise ValueError(f"must be empty or one of: {', '.join(EFFORT_LEVELS)}")
        return value

    @field_validator("log_level")
    @classmethod
    def _valid_log_level(cls, value: str) -> str:
        value = value.strip().upper()
        if value not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError("must be DEBUG, INFO, WARNING, ERROR or CRITICAL")
        return value

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def max_request_bytes(self) -> int:
        """Largest request body accepted: the biggest upload plus room for form overhead."""
        return self.max_upload_bytes + 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()
