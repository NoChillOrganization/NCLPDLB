"""
Tests for src/ml/pretrain.py — check_mapping_gap and module constants.
"""
from __future__ import annotations

import logging

import pytest

from src.ml.pretrain import (
    ABORT_THRESHOLD,
    WARN_THRESHOLD,
    check_mapping_gap,
)


class TestCheckMappingGap:
    def test_zero_total_returns_zero(self):
        gap = check_mapping_gap(unmappable=0, total=0)
        assert gap == 0.0

    def test_no_gap_returns_zero(self):
        gap = check_mapping_gap(unmappable=0, total=100)
        assert gap == pytest.approx(0.0)

    def test_gap_below_warn_threshold_no_warning(self, caplog):
        with caplog.at_level(logging.WARNING, logger="src.ml.pretrain"):
            gap = check_mapping_gap(unmappable=3, total=100)  # 3 % < 5 %
        assert gap == pytest.approx(0.03)
        assert not caplog.records

    def test_gap_above_warn_threshold_logs_warning(self, caplog):
        with caplog.at_level(logging.WARNING, logger="src.ml.pretrain"):
            gap = check_mapping_gap(unmappable=8, total=100)  # 8 % > 5 %
        assert gap == pytest.approx(0.08)
        assert caplog.records  # at least one warning emitted

    def test_gap_at_warn_threshold_not_logged(self, caplog):
        """Exactly at warn threshold is NOT > threshold, so no warning."""
        with caplog.at_level(logging.WARNING, logger="src.ml.pretrain"):
            gap = check_mapping_gap(
                unmappable=int(WARN_THRESHOLD * 100),
                total=100,
            )
        assert gap == pytest.approx(WARN_THRESHOLD)
        assert not caplog.records

    def test_gap_above_abort_threshold_raises(self):
        with pytest.raises(RuntimeError, match="abort threshold"):
            check_mapping_gap(unmappable=20, total=100)  # 20 % > 15 %

    def test_gap_above_abort_threshold_force_only_warns(self, caplog):
        with caplog.at_level(logging.WARNING, logger="src.ml.pretrain"):
            gap = check_mapping_gap(unmappable=20, total=100, force=True)
        assert gap == pytest.approx(0.20)
        assert caplog.records  # warning instead of exception

    def test_gap_exactly_at_abort_threshold_raises(self):
        """Exactly at abort threshold is NOT > threshold, so no raise."""
        # 15 / 100 == ABORT_THRESHOLD — should not raise
        gap = check_mapping_gap(
            unmappable=int(ABORT_THRESHOLD * 100),
            total=100,
        )
        assert gap == pytest.approx(ABORT_THRESHOLD)

    def test_returns_float(self):
        result = check_mapping_gap(unmappable=5, total=50)
        assert isinstance(result, float)

    def test_warn_threshold_constant(self):
        assert WARN_THRESHOLD == pytest.approx(0.05)

    def test_abort_threshold_constant(self):
        assert ABORT_THRESHOLD == pytest.approx(0.15)
