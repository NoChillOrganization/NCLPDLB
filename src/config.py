"""
Central configuration management using pydantic-settings.
Cross-platform: uses pathlib for all file paths.
"""
import re
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Project root — works on Windows, macOS, Linux
PROJECT_ROOT = Path(__file__).parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Discord
    discord_token: str
    discord_client_id: str
    discord_guild_id: str | None = None
    bot_name: str = "DraftBot"           # Display name shown in presence and embeds
    bot_status: str = "Pokemon Draft League"  # Activity text shown under bot name
    sync_commands_on_startup: bool = False   # Set SYNC_COMMANDS_ON_STARTUP=true in .env to force sync

    # Google Sheets
    google_sheets_credentials_file: Path = PROJECT_ROOT / "credentials.json"
    google_sheets_spreadsheet_id: str

    @field_validator("google_sheets_spreadsheet_id", mode="before")
    @classmethod
    def extract_spreadsheet_id(cls, v: str) -> str:
        """Accept either a bare ID or a full Google Sheets URL."""
        match = re.search(r"/spreadsheets/d/([a-zA-Z0-9_-]+)", v)
        return match.group(1) if match else v

    # Database
    database_url: str = f"sqlite+aiosqlite:///{PROJECT_ROOT / 'pokemon_draft.db'}"

    # PokéAPI
    pokeapi_base_url: str = "https://pokeapi.co/api/v2"
    pokeapi_rate_limit: int = 100

    # Showdown data URLs
    showdown_data_url: str = "https://raw.githubusercontent.com/smogon/pokemon-showdown/master/config/formats.ts"
    showdown_tiers_url: str = "https://raw.githubusercontent.com/smogon/pokemon-showdown/master/data/formats-data.ts"

    # Showdown bot account (used by /spar for live challenges)
    showdown_username: str = ""
    showdown_password: str = ""

    # GitHub — used by /admin-pull-models to download trained models from releases
    github_token: str = ""          # Personal access token (optional for public repos)
    github_repo: str = "NoChillModeOnline/NCLPDLB"

    # ML policy models directory
    ml_policy_dir: str = "data/ml/policy"

    # Master learning spreadsheet (separate from the league sheet; stores replay URLs)
    ml_learning_spreadsheet_id: str = ""

    # Smogon / VGC
    smogon_strategy_url: str = "https://www.smogon.com/dex"
    vgc_format: str = "reg-h"

    # ELO
    elo_k_factor: int = 32
    elo_default_rating: int = 1000

    # Logging
    log_level: str = "INFO"
    log_file: Path = PROJECT_ROOT / "logs" / "bot.log"

    @property
    def data_dir(self) -> Path:
        """Cross-platform path to local data files."""
        return PROJECT_ROOT / "data"


# Singleton instance — import this everywhere
settings = Settings()
