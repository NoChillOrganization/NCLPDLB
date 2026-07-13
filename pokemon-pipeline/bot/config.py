"""Discord bot config — all env vars read through the shared pydantic-settings Settings."""

from config import settings

BOT_TOKEN = settings.discord_bot_token
BOT_PREFIX = settings.bot_prefix
ADMIN_ROLE_ID = settings.admin_role_id
IMPORT_ROLE_ID = settings.import_role_id
API_BASE_URL = settings.api_base_url
API_SECRET_KEY = settings.api_secret_key

COLOR_SUCCESS = 0x2ECC71
COLOR_ERROR = 0xE74C3C
COLOR_INFO = 0x3498DB
COLOR_PENDING = 0xE67E22
