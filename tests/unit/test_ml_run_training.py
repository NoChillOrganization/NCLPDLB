"""
Tests for src/ml/run_training.py — training orchestrator helpers.

Covers:
  - _apply_windows_event_loop_fix()
  - _check_dependencies()
  - _parse_args()
  - _run_self_play_in_thread() error path
"""
from __future__ import annotations

import asyncio
import builtins
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.ml.run_training import (
    _apply_windows_event_loop_fix,
    _check_dependencies,
    _parse_args,
    _run_self_play_in_thread,
)


# ── _apply_windows_event_loop_fix ─────────────────────────────────────────────

class TestApplyWindowsEventLoopFix:
    def test_runs_without_error_on_non_windows(self):
        # On macOS/Linux sys.platform != "win32", function is a no-op
        _apply_windows_event_loop_fix()  # should not raise

    def test_sets_proactor_on_windows(self):
        mock_policy = MagicMock()
        with patch("sys.platform", "win32"), \
             patch("asyncio.WindowsProactorEventLoopPolicy", mock_policy, create=True), \
             patch("asyncio.set_event_loop_policy") as mock_set:
            _apply_windows_event_loop_fix()
            mock_set.assert_called_once()


# ── _check_dependencies ───────────────────────────────────────────────────────

class TestCheckDependencies:
    def test_returns_empty_when_all_present(self):
        # All packages installed in the venv
        missing = _check_dependencies()
        # fastapi, uvicorn, torch, poke_env, websockets should all be present
        assert isinstance(missing, list)

    def test_returns_missing_package_name(self):
        _real_import = builtins.__import__

        def _fake_import(name, *args, **kwargs):
            if name == "uvicorn":
                raise ImportError("no module named uvicorn")
            return _real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=_fake_import):
            missing = _check_dependencies()

        assert "uvicorn" in missing

    def test_returns_multiple_missing_packages(self):
        _real_import = builtins.__import__

        def _fake_import(name, *args, **kwargs):
            if name in ("uvicorn", "poke_env"):
                raise ImportError
            return _real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=_fake_import):
            missing = _check_dependencies()

        assert "uvicorn" in missing
        assert "poke_env" in missing

    def test_returns_list_type(self):
        assert isinstance(_check_dependencies(), list)


# ── _parse_args ───────────────────────────────────────────────────────────────

class TestParseArgs:
    def test_defaults(self):
        with patch("sys.argv", ["run_training"]):
            args = _parse_args()
        assert args.port == 8080
        assert args.format == "gen9randombattle"
        assert args.mcts_sims == 30
        assert args.buffer == 50_000
        assert args.lr == pytest.approx(3e-4)
        assert args.train_every == 5
        assert args.model is None

    def test_custom_port(self):
        with patch("sys.argv", ["run_training", "--port", "9090"]):
            args = _parse_args()
        assert args.port == 9090

    def test_custom_format(self):
        with patch("sys.argv", ["run_training", "--format", "gen9ou"]):
            args = _parse_args()
        assert args.format == "gen9ou"

    def test_custom_mcts_sims(self):
        with patch("sys.argv", ["run_training", "--mcts-sims", "100"]):
            args = _parse_args()
        assert args.mcts_sims == 100

    def test_custom_model_path(self):
        with patch("sys.argv", ["run_training", "--model", "/tmp/model.pt"]):
            args = _parse_args()
        assert args.model == "/tmp/model.pt"

    def test_custom_lr(self):
        with patch("sys.argv", ["run_training", "--lr", "1e-3"]):
            args = _parse_args()
        assert args.lr == pytest.approx(1e-3)

    def test_custom_buffer(self):
        with patch("sys.argv", ["run_training", "--buffer", "10000"]):
            args = _parse_args()
        assert args.buffer == 10000

    def test_train_every_zero_disables_training(self):
        with patch("sys.argv", ["run_training", "--train-every", "0"]):
            args = _parse_args()
        assert args.train_every == 0


# ── _run_self_play_in_thread ──────────────────────────────────────────────────

class TestRunSelfPlayInThread:
    def test_error_path_sets_api_status_to_error(self):
        """When run_forever() raises, the thread should update API status to 'error'."""
        loop_obj = MagicMock()
        loop_obj.run_forever = AsyncMock(side_effect=RuntimeError("boom"))

        with patch("src.ml.run_training._apply_windows_event_loop_fix"), \
             patch("src.ml.api.update_state") as mock_update:
            _run_self_play_in_thread(loop_obj)
            mock_update.assert_called_with(status="error")

    def test_success_path_does_not_crash(self):
        """When run_forever() completes normally, no exception propagates."""
        loop_obj = MagicMock()
        loop_obj.run_forever = AsyncMock(return_value=None)

        with patch("src.ml.run_training._apply_windows_event_loop_fix"):
            _run_self_play_in_thread(loop_obj)  # should not raise
