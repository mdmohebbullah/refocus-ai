"""Application settings, read from environment variables (see .env.example)."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Re-Focus AI"
    environment: str = "development"
    database_url: str = "sqlite:///./refocus.db"
    secret_key: str = "change-me-in-production-please-use-a-long-random-value"
    token_encryption_key: str = ""  # Fernet key; derived from secret_key if empty
    access_token_minutes: int = 60 * 24 * 7
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    frontend_url: str = "http://localhost:5173"
    public_api_url: str = "http://localhost:8000"

    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    openai_transcribe_model: str = "whisper-1"

    google_client_id: str = ""
    google_client_secret: str = ""
    microsoft_client_id: str = ""
    microsoft_client_secret: str = ""
    microsoft_tenant: str = "common"

    render_external_url: str = ""  # set automatically by Render

    def model_post_init(self, __context) -> None:
        # On Render, use the service's own public address unless set explicitly.
        ext = self.render_external_url.rstrip("/")
        if ext:
            if self.frontend_url.startswith("http://localhost"):
                self.frontend_url = ext
            if self.public_api_url.startswith("http://localhost"):
                self.public_api_url = ext
            if ext not in self.cors_origins:
                self.cors_origins = f"{self.cors_origins},{ext}"
        # Hosts such as Render give postgres:// or postgresql:// URLs; use the installed psycopg2 driver explicitly.
        for prefix in ("postgres://", "postgresql://"):
            if self.database_url.startswith(prefix):
                self.database_url = "postgresql+psycopg2://" + self.database_url[len(prefix):]

    @property
    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def ai_enabled(self) -> bool:
        return bool(self.openai_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
