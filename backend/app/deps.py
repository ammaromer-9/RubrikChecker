from functools import lru_cache

from app.config import get_settings
from app.db import SessionLocal
from app.services.llm_client import DbCallRecorder, LLMClient, build_llm_client


@lru_cache
def get_llm_client() -> LLMClient:
    """FastAPI dependency. Tests override it with a client built on a fake provider."""
    return build_llm_client(get_settings(), DbCallRecorder(SessionLocal))
