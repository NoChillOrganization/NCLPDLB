"""Central settings — every env var in the project is read through here, never os.environ directly."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Database
    database_url: str = "postgresql+asyncpg://pipeline:pipeline@localhost:5433/pokemon_pipeline"

    # Redis / Celery
    redis_url: str = "redis://localhost:6380/0"

    # Source base URLs
    limitless_api_base: str = "https://play.limitlesstcg.com/api"
    smogon_forum_base: str = "https://www.smogon.com/forums"
    labmaus_base: str = "https://labmaus.net"
    rk9_base: str = "https://rk9.gg"

    # Node classifier microservice
    node_classifier_url: str = "http://localhost:3001"

    # YouTube Data API v3
    youtube_api_key: str = ""

    # Discord bot
    discord_bot_token: str = ""
    bot_prefix: str = "!"
    admin_role_id: int = 0
    import_role_id: int = 0

    # API
    api_secret_key: str = "change-me-to-a-random-secret"
    api_base_url: str = "http://localhost:8000"

    # Backfill
    backfill_start_date: str = "2026-04-01"

    # Per-domain scrape delays (seconds)
    labmaus_delay: float = 3.0
    rk9_delay: float = 2.0


settings = Settings()
