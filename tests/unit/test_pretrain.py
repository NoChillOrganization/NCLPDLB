"""
Unit tests for src/ml/pretrain.py — check_mapping_gap function.
"""
import logging
import pytest

from src.ml.pretrain import check_mapping_gap, WARN_THRESHOLD, ABORT_THRESHOLD


class TestCheckMappingGap:

    def test_zero_total_returns_zero(self):
        result = check_mapping_gap(0, 0)
        assert result == 0.0

    def test_below_warn_threshold_returns_fraction(self):
        # 1/100 = 1% < WARN_THRESHOLD (5%)
        result = check_mapping_gap(1, 100)
        assert abs(result - 0.01) < 1e-9

    def test_above_warn_threshold_logs_warning(self, caplog):
        # 6/100 = 6% > WARN_THRESHOLD (5%)
        with caplog.at_level(logging.WARNING, logger="src.ml.pretrain"):
            result = check_mapping_gap(6, 100)
        assert abs(result - 0.06) < 1e-9
        assert any("warn" in r.message.lower() or "gap" in r.message.lower()
                   for r in caplog.records)

    def test_above_abort_threshold_without_force_raises(self):
        # 20/100 = 20% > ABORT_THRESHOLD (15%)
        with pytest.raises(RuntimeError, match="abort threshold"):
            check_mapping_gap(20, 100)

    def test_above_abort_threshold_with_force_logs_warning(self, caplog):
        with caplog.at_level(logging.WARNING, logger="src.ml.pretrain"):
            result = check_mapping_gap(20, 100, force=True)
        assert abs(result - 0.20) < 1e-9
        assert any("abort threshold" in r.message for r in caplog.records)

    def test_exactly_at_warn_threshold_no_warning(self, caplog):
        # Exactly WARN_THRESHOLD (5%) — should NOT warn (uses strict >)
        with caplog.at_level(logging.WARNING, logger="src.ml.pretrain"):
            check_mapping_gap(int(WARN_THRESHOLD * 100), 100)
        assert not caplog.records

    def test_exactly_at_abort_threshold_no_raise(self):
        # Exactly ABORT_THRESHOLD (15%) — should NOT raise (uses strict >)
        result = check_mapping_gap(int(ABORT_THRESHOLD * 100), 100)
        assert result == pytest.approx(ABORT_THRESHOLD, abs=1e-9)
