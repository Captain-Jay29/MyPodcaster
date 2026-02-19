"""
Configuration management via pydantic-settings.
Validates env vars at startup — fails fast with clear error messages.
"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # --- Required ---
    openai_api_key: str

    # --- LLM Agent ---
    openai_model: str = "gpt-5-mini"
    agent_max_turns: int = 15
    agent_max_tokens: int = 100_000
    agent_timeout_seconds: int = 120

    # --- TTS ---
    openai_tts_model: str = "tts-1"
    openai_tts_voice: str = "onyx"
    openai_tts_speed: float = 1.05
    tts_max_workers: int = 6

    # --- Jina Reader ---
    jina_api_key: str = ""
    max_article_content_length: int = 4000  # chars, truncation for read_url

    # --- Briefing defaults ---
    default_num_articles: int = 10

    # --- Storage ---
    audio_cache_dir: str = "/tmp/briefings"
    audio_cache_ttl_hours: int = 24

    # --- Server ---
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "INFO"
    sentry_dsn: str = ""

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


# Singleton — import this everywhere
settings = Settings()  # type: ignore[call-arg]  # populated from .env at runtime
