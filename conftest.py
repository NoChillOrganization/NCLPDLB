"""
Root conftest.py — sets required env vars before any src module is imported.

pytest loads this file first (before tests/conftest.py and before test collection),
so Settings() sees these values instead of failing with ValidationError.
Real credentials are never needed in the test suite.
"""
import os

os.environ.setdefault("DISCORD_TOKEN", "test_token_placeholder")
os.environ.setdefault("DISCORD_CLIENT_ID", "000000000000000000")
os.environ.setdefault("GOOGLE_SHEETS_SPREADSHEET_ID", "test_spreadsheet_id")
