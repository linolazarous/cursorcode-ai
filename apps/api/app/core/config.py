"""
Central configuration & settings for CursorCode AI API

Production-ready configuration system
Supports:

• Supabase
• Redis
• Stripe
• JWT Auth
• Resend Email
• xAI Grok
• Security hardening
• Local dev (Termux)
• Production deployment
"""

from functools import lru_cache
from typing import Any, Dict, List

import json
import logging

from pydantic import (
    AnyHttpUrl,
    EmailStr,
    Field,
    PostgresDsn,
    RedisDsn,
    SecretStr,
    field_validator,
    model_validator,
)

from pydantic_settings import BaseSettings, SettingsConfigDict


# ────────────────────────────────────────────────
# Logger
# ────────────────────────────────────────────────

logger = logging.getLogger("cursorcode.config")


# ────────────────────────────────────────────────
# Settings Class
# ────────────────────────────────────────────────


class Settings(BaseSettings):

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ────────────────────────────────────────────────
    # Environment
    # ────────────────────────────────────────────────

    ENVIRONMENT: str = Field(
        default="development",
        description="development | staging | production",
    )

    APP_VERSION: str = "1.0.0"

    LOG_LEVEL: str = Field(
        default="INFO"
    )


    # ────────────────────────────────────────────────
    # URLs
    # ────────────────────────────────────────────────

    FRONTEND_URL: AnyHttpUrl = Field(
        default="http://localhost:3000"
    )

    @property
    def api_url(self) -> str:
        return f"{str(self.FRONTEND_URL).rstrip('/')}/api"


    # ────────────────────────────────────────────────
    # Database
    # ────────────────────────────────────────────────

    DATABASE_URL: PostgresDsn


    @field_validator("DATABASE_URL")
    @classmethod
    def validate_db(cls, v):

        url = str(v)

        if "asyncpg" not in url:

            raise ValueError(
                "DATABASE_URL must use asyncpg driver"
            )

        return v


    # ────────────────────────────────────────────────
    # Redis
    # ────────────────────────────────────────────────

    REDIS_URL: RedisDsn


    # ────────────────────────────────────────────────
    # Stripe
    # ────────────────────────────────────────────────

    STRIPE_SECRET_KEY: SecretStr

    NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY: str

    STRIPE_WEBHOOK_SECRET: SecretStr

    FERNET_KEY: SecretStr


    STRIPE_PLAN_CREDITS_JSON: str | None = None


    @property
    def STRIPE_PLAN_CREDITS(self) -> Dict[str, int]:

        if self.STRIPE_PLAN_CREDITS_JSON:

            try:

                return json.loads(
                    self.STRIPE_PLAN_CREDITS_JSON
                )

            except Exception:

                logger.warning(
                    "Invalid STRIPE_PLAN_CREDITS_JSON"
                )

        return {

            "starter": 75,
            "standard": 200,
            "pro": 500,
            "premier": 1500,
            "ultra": 5000,

        }


    FREE_TIER_CREDITS: int = 10


    # ────────────────────────────────────────────────
    # Email
    # ────────────────────────────────────────────────

    RESEND_API_KEY: SecretStr

    EMAIL_FROM: EmailStr = "no-reply@cursorcode.ai"

    EMAIL_FROM_NAME: str = "CursorCode AI"


    # ────────────────────────────────────────────────
    # xAI
    # ────────────────────────────────────────────────

    XAI_API_KEY: SecretStr

    DEFAULT_XAI_MODEL: str = "grok-beta"

    FAST_REASONING_MODEL: str = "grok-beta-fast"

    FAST_NON_REASONING_MODEL: str = "grok-beta-fast"


    # ────────────────────────────────────────────────
    # JWT
    # ────────────────────────────────────────────────

    JWT_SECRET_KEY: SecretStr

    JWT_REFRESH_SECRET: SecretStr

    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15

    REFRESH_TOKEN_EXPIRE_DAYS: int = 30


    @field_validator(
        "JWT_SECRET_KEY",
        "JWT_REFRESH_SECRET",
        "FERNET_KEY",
    )

    @classmethod
    def validate_secret_length(cls, v):

        if len(v.get_secret_value()) < 32:

            raise ValueError(
                "Secret must be >= 32 chars"
            )

        return v


    # ────────────────────────────────────────────────
    # Cookies
    # ────────────────────────────────────────────────

    COOKIE_SECURE: bool = True


    COOKIE_DEFAULTS: dict = {

        "httponly": True,

        "secure": True,

        "samesite": "strict",

        "path": "/",

    }


    # ────────────────────────────────────────────────
    # CORS
    # ────────────────────────────────────────────────

    CORS_ORIGINS: List[AnyHttpUrl] = []


    @model_validator(mode="after")

    def cors_validator(self):

        if not self.CORS_ORIGINS:

            self.CORS_ORIGINS = [

                self.FRONTEND_URL

            ]

        return self


    # ────────────────────────────────────────────────
    # Environment validation
    # ────────────────────────────────────────────────

    @field_validator("ENVIRONMENT")

    @classmethod

    def validate_env(cls, v):

        v = v.lower()

        if v not in [

            "development",

            "staging",

            "production",

        ]:

            raise ValueError(

                "Invalid ENVIRONMENT"

            )

        return v


    # ────────────────────────────────────────────────
    # Helpers
    # ────────────────────────────────────────────────


    @property

    def is_production(self):

        return self.ENVIRONMENT == "production"


    @property

    def is_dev(self):

        return self.ENVIRONMENT == "development"


    def get_cookie_options(

        self,

        max_age: int | None = None,

    ):

        opts = self.COOKIE_DEFAULTS.copy()

        opts["secure"] = (

            self.COOKIE_SECURE

            and self.is_production

        )

        if max_age:

            opts["max_age"] = max_age

        return opts


# ────────────────────────────────────────────────
# Singleton
# ────────────────────────────────────────────────


@lru_cache

def get_settings():

    logger.info("Loading settings")

    return Settings()


settings = get_settings()
