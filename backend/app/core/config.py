from __future__ import annotations

from typing import List
from pydantic import AnyUrl
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", case_sensitive=False)

    # Core
    DATABASE_URL: str
    ALLOWED_ORIGINS: str | None = "*"

    # Auth
    AUTH_TOKEN_SECRET: str
    AUTH_TOKEN_TTL_SECONDS: int = 86400

    # Misc
    DEBUGPY: int | None = None
    AUTOGEN_MIGRATIONS_DEV: bool = False
    AUTOGEN_MIGRATIONS_PROD: bool = False

    # Default administrator bootstrap
    ADMIN_EMAIL: str | None = None
    ADMIN_PASSWORD: str | None = None
    ADMIN_FULL_NAME: str | None = None

    @property
    def cors_origins(self) -> List[str]:
        if not self.ALLOWED_ORIGINS:
            return []
        raw = self.ALLOWED_ORIGINS
        if isinstance(raw, str):
            return [o.strip() for o in raw.split(",") if o.strip()]
        return list(raw)

    @property
    def is_dev(self) -> bool:
        try:
            return bool(int(self.DEBUGPY or 0))
        except Exception:
            return False


settings = Settings()  # type: ignore[call-arg]
