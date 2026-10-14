"""
app/core/config.py — Application Settings (Pydantic v2)

All configuration is loaded from environment variables (and .env file).
Pydantic validates types and enforces required fields at startup.
"""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_DEFAULT_SECRET_KEY = "CHANGE-ME-IN-PRODUCTION-use-openssl-rand-hex-64"
_DEFAULT_TRUST_PEPPER = "CHANGE-ME-IN-PRODUCTION-use-openssl-rand-hex-64"


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
        default=_DEFAULT_SECRET_KEY,
        min_length=32,
    )
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    # Password-reset tokens (Redis-backed, single-use — see
    # app/core/security/security.py::create_password_reset_token). Kept
    # short-lived by design: a forgot-password email sitting unused in an
    # inbox for days is a bigger risk than a legitimate user occasionally
    # needing to re-request the link.
    RESET_TOKEN_EXPIRE_MINUTES: int = 30
    # Trust Network HMAC pepper (app.modules.trust.services.hashing).
    # Application-wide secret mixed into every phone-number hash before it
    # is persisted, on top of the fact that HMAC-SHA256 already keys the
    # hash — without a real secret here, anyone who reads this source tree
    # can compute the same phone hashes the Trust Network stores, defeating
    # the whole point of hashing instead of storing plaintext. Same
    # generate-and-set discipline as SECRET_KEY above.
    TRUST_PEPPER: str = Field(
        default=_DEFAULT_TRUST_PEPPER,
        min_length=32,
    )

    # ── CORS ──────────────────────────────────────────────────────────────────
    CORS_ORIGINS: list[str] = [
        "http://localhost:3000",    # Next.js dev (default port)
        "http://localhost:3001",    # Next.js dev (fallback port when 3000 is busy)
        "http://localhost:5173",    # Vite dev
        "http://localhost:8080",    # Vue dev
        "http://localhost:8000",    # FastAPI docs (for Swagger UI)
    ]

    # --- EventBus ──────────────────────────────────────────────────────────────
    # "memory" → InMemoryEventBus (asyncio tasks, dev/test only)
    # "redis"  → RedisEventBus (Celery/pub-sub, production)
    EVENT_BUS_BACKEND: str = "memory"
    REDIS_CHANNEL: str = "omni_erp:events"

    # ── Payment Gateway (Paymob Accept — Egypt) ─────────────────────────────────
    # None by default: app.modules.billing.services.gateway refuses to
    # attempt a real charge when these aren't configured (fails loudly with
    # a clear error), rather than silently no-op'ing or fabricating a fake
    # success — same discipline as the Vault-reference stubs elsewhere in
    # this codebase. A real merchant deployment MUST set these three plus
    # PAYMOB_HMAC_SECRET (used to verify the inbound webhook is really from
    # Paymob) via environment variables before subscriptions can actually
    # be charged.
    PAYMOB_API_KEY: str | None = None
    PAYMOB_INTEGRATION_ID: str | None = None
    PAYMOB_IFRAME_ID: str | None = None
    PAYMOB_HMAC_SECRET: str | None = None
    PAYMOB_BASE_URL: str = "https://accept.paymob.com"

    # ── Email (fallback notification channel) ───────────────────────────────────
    # None by default: app.core.notifications.email refuses to attempt a
    # send when these aren't configured (logs and returns False, same
    # discipline as the Paymob/Vault stubs above) rather than pretending a
    # notification went out. Used as the fallback path when WhatsApp send
    # fails or a tenant has no WhatsApp integration configured — see
    # app.core.notifications.dispatch.notify_contact.
    SMTP_HOST: str | None = None
    SMTP_PORT: int = 587
    SMTP_USERNAME: str | None = None
    SMTP_PASSWORD: str | None = None
    SMTP_USE_TLS: bool = True
    SMTP_FROM_EMAIL: str | None = None
    SMTP_FROM_NAME: str = "Nexus ERP"

    # ── AI Provider (app.core.ai.adapter — Copilot / Reporting Bot) ─────────────
    # Deliberately NOT the vendor `openai` SDK — talks to any
    # OpenAI-compatible /chat/completions endpoint over plain httpx (already
    # a dependency), so switching provider is an env-var change, not a code
    # change or a new dependency:
    #   Groq   (free tier, OpenAI-compatible) → https://api.groq.com/openai/v1
    #   OpenAI (paid)                          → https://api.openai.com/v1
    # AI_API_KEY is None by default: app.core.ai.adapter refuses to attempt a
    # call when it isn't configured (raises AIProviderNotConfigured, which
    # app.modules.ai.router turns into a clear Arabic message) rather than
    # crashing or silently returning a fabricated answer — same discipline
    # as the Paymob/SMTP/Vault stubs above. Never commit a real key here;
    # set it via the environment or an untracked .env.
    AI_PROVIDER: str = "groq"
    AI_API_KEY: str | None = None
    AI_BASE_URL: str = "https://api.groq.com/openai/v1"
    # "llama-3.3-70b-versatile" 404'd as model_not_found against this
    # account's actual Groq key during live verification (2026-09-11) even
    # though Groq's own docs still list it — model availability appears to
    # be account/tier-gated in practice, not just documentation-accurate.
    # openai/gpt-oss-120b is Groq's own recommended production model for
    # tool/function-calling use, which is exactly what app.modules.ai.router
    # needs — switched to it after the above failure; re-verify live after
    # any future model swap the same way (this account's access can differ
    # from what the docs list).
    AI_MODEL: str = "openai/gpt-oss-120b"
    AI_TIMEOUT_SECONDS: float = 30.0

    # ── Observability ─────────────────────────────────────────────────────────
    SENTRY_DSN: str | None = None
    OTLP_ENDPOINT: str | None = None

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

    @model_validator(mode="after")
    def _guard_production_misconfiguration(self) -> "Settings":
        """
        Refuse to boot with known-unsafe defaults in production. Every JWT
        is forgeable with the placeholder SECRET_KEY (it's public, it's
        right there in this file's default), and the default CORS_ORIGINS
        list is entirely localhost dev origins — either one left unset in
        a real deploy is a silent, catastrophic misconfiguration, not a
        style nit. Fails fast at process startup instead of shipping a
        production instance that "works" until someone finds the default
        key on GitHub.
        """
        if self.ENVIRONMENT != "production":
            return self

        errors: list[str] = []
        if self.SECRET_KEY == _DEFAULT_SECRET_KEY:
            errors.append(
                "SECRET_KEY is still the placeholder default. Every JWT issued "
                "would be forgeable by anyone who has read this file. Generate "
                "one with: python -c \"import secrets; print(secrets.token_hex(64))\" "
                "and set it via the SECRET_KEY environment variable."
            )
        if self.TRUST_PEPPER == _DEFAULT_TRUST_PEPPER:
            errors.append(
                "TRUST_PEPPER is still the placeholder default. Every Trust "
                "Network phone hash would be computable by anyone who has "
                "read this file. Generate one with: python -c \"import secrets; "
                "print(secrets.token_hex(64))\" and set it via the TRUST_PEPPER "
                "environment variable."
            )
        if all(origin.startswith("http://localhost") or origin.startswith("http://127.0.0.1") for origin in self.CORS_ORIGINS):
            errors.append(
                "CORS_ORIGINS is still the default localhost-only dev list. Set "
                "the CORS_ORIGINS environment variable to your real frontend "
                "origin(s) (comma-separated), e.g. https://app.yourdomain.com."
            )
        if self.DEBUG:
            errors.append(
                "DEBUG is still True. Running with debug mode on in production "
                "leaks stack traces and internal state to clients. Set the "
                "DEBUG environment variable to false."
            )
        if errors:
            raise ValueError(
                "Refusing to start with ENVIRONMENT=production and unsafe defaults:\n- "
                + "\n- ".join(errors)
            )
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached Settings instance (parsed once at startup)."""
    return Settings()


# Module-level singleton — import directly: `from app.core.config import settings`
settings: Settings = get_settings()
