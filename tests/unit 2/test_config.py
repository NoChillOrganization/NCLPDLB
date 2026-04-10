"""Tests for src/config.py — Settings validation."""
import pytest
from src.config import Settings


@pytest.fixture
def base_settings():
    """A Settings instance with required fields filled in; reads rest from .env."""
    return Settings()


def test_settings_has_required_fields(base_settings):
    assert base_settings.discord_token
    assert base_settings.discord_client_id
    assert base_settings.google_sheets_spreadsheet_id


def test_spreadsheet_id_extracted_from_url():
    s = Settings(
        discord_token="tok",
        discord_client_id="123",
        google_sheets_spreadsheet_id=(
            "https://docs.google.com/spreadsheets/d/ABC123/edit"
        ),
    )
    assert s.google_sheets_spreadsheet_id == "ABC123"


def test_spreadsheet_bare_id_unchanged():
    s = Settings(
        discord_token="tok",
        discord_client_id="123",
        google_sheets_spreadsheet_id="BAREID",
    )
    assert s.google_sheets_spreadsheet_id == "BAREID"


def test_data_dir_property(base_settings):
    assert base_settings.data_dir.name == "data"
