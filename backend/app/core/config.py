"""
app/core/config.py — Application Settings (Pydantic v2)

All configuration is loaded from environment variables (and .env file).
Pydantic validates types and enforces required fields at startup.
"""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",        # Silently ignore undeclared env vars
    )

    # ── App ───────────────────────────────────────────────────────────────────
    PROJECT_NAME: str = "Omni ERP — Modular ERP & Trust Network"
    API_V1_PREFIX: str = "/api/v1"
    ENVIRONMENT: str = "development"       # development | staging | production
    DEBUG: bool = True

    # ── Database ──────────────────────────────────────────────────────────────
    DATABASE_URL: str = (
        "postgresql+asyncpg://postgres:postgres@localhost:5432/omni_erp"
    )

    # ── Redis ─────────────────────────────────────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379/0"

    # ── Security ──────────────────────────────────────────────────────────────
    # Generate with: python -c "import secrets; print(secrets.token_hex(64))"
    SECRET_KEY: str = Field(
        default="CHANGE-ME-IN-PRODUCTION-use-openssl-rand-hex-64",
        min_length=32,
    )
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # ── CORS ──────────────────────────────────────────────────────────────────
    CORS_ORIGINS: list[str] = [
        "http://localhost:3000",    # React / Next.js dev
        "http://localhost:5173",    # Vite dev
        "http://localhost:8080",    # Vue dev
        "http://localhost:8000",    # FastAPI docs (for Swagger UI)
    ]

    # ── EventBus ──────────────────────────────────────────────────────────────
    # "memory" → InMemoryEventBus (asyncio tasks, dev/test only)
    # "redis"  → RedisEventBus (Celery/pub-sub, production)
    EVENT_BUS_BACKEND: str = "memory"

    @field_validator("ENVIRONMENT")
    @classmethod
    def validate_environment(cls, v: str) -> str:
        allowed = {"development", "staging", "production", "test"}
        if v not in allowed:
            raise ValueError(f"ENVIRONMENT must be one of {allowed}, got '{v}'")
        return v

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached Settings instance (parsed once at startup)."""
    return Settings()


# Module-level singleton — import directly: `from app.core.config import settings`
settings: Settings = get_settings()
