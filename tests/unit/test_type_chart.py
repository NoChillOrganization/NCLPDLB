"""Tests for src.ml.type_chart — get_type_effectiveness_float()."""
import math
from unittest.mock import MagicMock

import pytest

from src.ml.type_chart import get_type_effectiveness_float


def _target(mult: float) -> MagicMock:
    t = MagicMock()
    t.damage_multiplier = MagicMock(return_value=mult)
    return t


def _move() -> MagicMock:
    return MagicMock()


def test_immune_returns_minus_one():
    assert get_type_effectiveness_float(_move(), _target(0)) == -1.0


def test_quarter_resist_returns_minus_one():
    result = get_type_effectiveness_float(_move(), _target(0.25))
    assert result == -1.0


def test_half_resist_returns_minus_half():
    result = get_type_effectiveness_float(_move(), _target(0.5))
    assert result == pytest.approx(-0.5)


def test_neutral_returns_zero():
    result = get_type_effectiveness_float(_move(), _target(1.0))
    assert result == pytest.approx(0.0)


def test_two_x_weak_returns_half():
    result = get_type_effectiveness_float(_move(), _target(2.0))
    assert result == pytest.approx(0.5)


def test_four_x_weak_returns_one():
    result = get_type_effectiveness_float(_move(), _target(4.0))
    assert result == pytest.approx(1.0)


def test_extreme_mult_clamped_to_one():
    # 8x would log2=3, /2=1.5, clamped to 1.0
    result = get_type_effectiveness_float(_move(), _target(8.0))
    assert result == 1.0


def test_very_low_mult_clamped_to_minus_one():
    # 0.125x would log2=-3, /2=-1.5, clamped to -1.0
    result = get_type_effectiveness_float(_move(), _target(0.125))
    assert result == -1.0
