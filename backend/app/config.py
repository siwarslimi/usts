from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Every secret comes from the environment; nothing sensitive is hard-coded."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./data/app.db"
    app_timezone: str = "Europe/Paris"

    # Authentication of the web UI
    jwt_secret: str = Field(min_length=16)
    jwt_ttl_hours: int = 12
    cookie_secure: bool = False
    admin_email: str = "admin@example.com"
    admin_password: str | None = None

    # Shared secret between the backend and n8n (both directions)
    webhook_secret: str = Field(min_length=16)
    # When true, every n8n -> backend call must also carry a valid HMAC signature
    webhook_hmac_required: bool = False

    # Outgoing replies: "n8n" triggers the send workflow, "mock" simulates Gmail (demo)
    reply_transport: Literal["n8n", "mock"] = "mock"
    n8n_send_webhook_url: str = "http://n8n:5678/webhook/send-reply"

    # AI provider (OpenAI-compatible API, Groq by default)
    groq_api_key: str | None = None
    groq_model: str = "qwen/qwen3.8-27b"
    groq_base_url: str = "https://api.groq.com/openai/v1"

    cors_origins: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
