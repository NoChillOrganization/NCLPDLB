"""Regression tests for sync_all's CLI-key -> DB-source-name mapping.

Covers the bug from CI run #29008635041: sync_all.py's "replays" branch
passed the raw CLI arg "replays" into with_ingest_run/land_and_normalize
instead of the `source` table's canonical name "showdown", so the daily
replay sync landed data fine but never recorded a health row (silent
INSERT...SELECT no-op in orchestrate.with_ingest_run), leaving showdown's
STALE_SYNC monitor frozen at its last manually-run success.
"""

from src.platform.sync_all import _db_source_name


def test_replays_maps_to_showdown():
    assert _db_source_name("replays") == "showdown"


def test_unmapped_sources_pass_through():
    for source in ("smogon", "pikalytics", "limitless"):
        assert _db_source_name(source) == source


def test_unknown_source_passes_through_unchanged():
    """No mapping entry -> identity, not an error (validity is _run_source's job)."""
    assert _db_source_name("not_a_real_source") == "not_a_real_source"
