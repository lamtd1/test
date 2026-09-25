from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings

_DEFAULT_CORS_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]


def parse_cors_origins(raw: str | None) -> list[str]:
    if not raw or not raw.strip():
        return list(_DEFAULT_CORS_ORIGINS)
    return [origin.strip().rstrip("/") for origin in raw.split(",") if origin.strip()]


class Settings(BaseSettings):
    app_name: str = "ai-agent"
    app_env: Literal["development", "staging", "production"] = "development"
    debug: bool = False
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    api_host: str = "0.0.0.0"
    api_port: int = Field(default=8000, ge=1024, le=65535)
    api_prefix: str = "/api/v1"

    llm_provider: Literal["openai", "anthropic", "google", "gemini"] = "gemini"
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    openai_model: str = "gpt-4o-mini"
    openai_temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    openai_max_tokens: int = Field(default=2048, ge=1, le=128000)

    # Discovery agent — xem docs/adr/0002-gemini-for-discovery-agent.md
    google_api_key: str = Field(default="", alias="GOOGLE_API_KEY")
    llm_model_discovery: str = "gemini-flash-lite-latest"

    cors_origins_raw: str = Field(default="", alias="CORS_ORIGINS")
    # Optional regex for platforms that mint a new origin per deploy (e.g. Vercel preview
    # URLs). Example: ^https://test-.*\.vercel\.app$ covers every deployment of one project.
    cors_origin_regex: str | None = Field(default=None, alias="CORS_ORIGIN_REGEX")

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
        "extra": "ignore",
    }

    @property
    def cors_origins(self) -> list[str]:
        return parse_cors_origins(self.cors_origins_raw)


settings = Settings()


def get_settings():
    return settings


if __name__ == "__main__":
    for i, v in settings:
        print(f"{i, v}")
