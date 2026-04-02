import os
from dataclasses import dataclass

from dotenv import load_dotenv


load_dotenv()


def _as_bool(value: str, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    ANTHROPIC_API_KEY: str
    CLAUDE_MODEL: str
    LINKDAPI_API_KEY: str
    LINKDAPI_BASE_URL: str
    REDIS_URL: str
    SERPAPI_KEY: str
    OPIKA_LOGO_URL: str
    OUTPUT_DIR: str
    APP_HOST: str
    APP_PORT: int
    DEBUG: bool


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ValueError(f"Missing required environment variable: {name}")
    return value


def load_settings() -> Settings:
    return Settings(
        ANTHROPIC_API_KEY=os.getenv("ANTHROPIC_API_KEY", "").strip(),
        CLAUDE_MODEL=os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6").strip(),
        LINKDAPI_API_KEY=os.getenv("LINKDAPI_API_KEY", "").strip(),
        LINKDAPI_BASE_URL=os.getenv("LINKDAPI_BASE_URL", "https://linkdapi.com").strip(),
        REDIS_URL=os.getenv("REDIS_URL", "redis://localhost:6379/0").strip(),
        SERPAPI_KEY=os.getenv("SERPAPI_KEY", "").strip(),
        OPIKA_LOGO_URL=os.getenv("OPIKA_LOGO_URL", "").strip(),
        OUTPUT_DIR=os.getenv("OUTPUT_DIR", "./outputs").strip(),
        APP_HOST=os.getenv("APP_HOST", "0.0.0.0").strip(),
        APP_PORT=int(os.getenv("APP_PORT", "8000")),
        DEBUG=_as_bool(os.getenv("DEBUG"), default=False),
    )


settings = load_settings()
