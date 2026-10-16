from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings, read from environment variables / a .env file."""

    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore")

    database_url: str = "postgresql+asyncpg://rubriccheck:rubriccheck@localhost:5432/rubriccheck"
    test_database_url: str = (
        "postgresql+asyncpg://rubriccheck:rubriccheck@localhost:5432/rubriccheck_test"
    )
    anthropic_api_key: str = ""
    anthropic_model: str = ""
    llm_timeout_seconds: float = 60.0
    llm_max_retries: int = 3
    grading_runs: int = 3
    grading_temperature: float = 0.7
    grading_concurrency: int = 5
    feedback_max_quoted_words: int = 25
    max_draft_chars: int = 50_000
    max_assignment_text_chars: int = 20_000
    max_upload_bytes: int = 5 * 1024 * 1024
    cors_origins: str = "http://localhost:5173"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
