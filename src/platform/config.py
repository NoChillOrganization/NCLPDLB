"""Platform config — reuses src.config.settings, adds Postgres DSN."""

import os

from src.config import settings as _settings

PLATFORM_DATABASE_URL = os.environ.get("PLATFORM_DATABASE_URL") or (
    "postgresql://postgres:postgres@localhost:5432/nclpdlb_platform"
)

settings = _settings
