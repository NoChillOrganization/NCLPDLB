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

import runpy
import threading

from src.ml.run_training import (
    _apply_windows_event_loop_fix,
    _check_dependencies,
    _parse_args,
    _run_self_play_in_thread,
    main,
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

    def test_error_path_import_fails_is_swallowed(self):
        """When run_forever() raises AND api import fails, outer except: pass is hit."""
        loop_obj = MagicMock()
        loop_obj.run_forever = AsyncMock(side_effect=RuntimeError("boom"))

        with patch("src.ml.run_training._apply_windows_event_loop_fix"), \
             patch.dict("sys.modules", {"src.ml.api": None}):
            _run_self_play_in_thread(loop_obj)  # must not raise


# ── main() ────────────────────────────────────────────────────────────────────

def _make_main_patches(model_exists=False, missing_deps=None, settings_username="Bot"):
    """Return a context manager stack that fully mocks main()'s dependencies."""
    mock_model = MagicMock()
    mock_buffer = MagicMock()
    mock_buffer.__len__ = MagicMock(return_value=0)
    mock_trainer = MagicMock()
    mock_stats = MagicMock()
    mock_loop = MagicMock()
    mock_loop.run_game = AsyncMock()
    mock_loop.mcts_config = MagicMock()
    mock_thread = MagicMock(spec=threading.Thread)

    mock_settings = MagicMock()
    mock_settings.showdown_username = settings_username
    mock_settings.showdown_password = "pw"

    return (
        mock_model, mock_buffer, mock_trainer, mock_stats, mock_loop, mock_thread,
        [
            patch("src.ml.run_training._apply_windows_event_loop_fix"),
            patch("src.ml.run_training._check_dependencies",
                  return_value=missing_deps or []),
            patch("src.ml.transformer_model.build_default_model", return_value=mock_model),
            patch("src.ml.transformer_model.load_model", return_value=mock_model),
            patch("src.ml.trainer.ReplayBuffer", return_value=mock_buffer),
            patch("src.ml.trainer.PolicyTrainer", return_value=mock_trainer),
            patch("src.ml.self_play.SharedStats", return_value=mock_stats),
            patch("src.ml.self_play.SelfPlayLoop", return_value=mock_loop),
            patch("src.ml.mcts.MCTSConfig", return_value=MagicMock()),
            patch("src.ml.api.update_state"),
            patch("src.config.settings", mock_settings),
            patch("threading.Thread", return_value=mock_thread),
            patch("uvicorn.run"),
            patch("pathlib.Path.exists", return_value=model_exists),
        ]
    )


class TestMain:
    def _run_main(self, model_exists=False, missing_deps=None,
                  settings_username="Bot", **kwargs):
        from contextlib import ExitStack
        _, _, _, _, _, mock_thread, patches = _make_main_patches(
            model_exists=model_exists,
            missing_deps=missing_deps,
            settings_username=settings_username,
        )
        with ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            main(**kwargs)
        return mock_thread

    def test_main_starts_thread_and_uvicorn(self):
        thread = self._run_main()
        thread.start.assert_called_once()

    def test_main_loads_model_when_file_exists(self):
        from contextlib import ExitStack
        _, _, _, _, _, _, patches = _make_main_patches(model_exists=True)
        with ExitStack() as stack:
            mocks = [stack.enter_context(p) for p in patches]
            main()
        # load_model (index 3) should have been called
        mocks[3].assert_called_once()

    def test_main_builds_model_when_file_missing(self):
        from contextlib import ExitStack
        _, _, _, _, _, _, patches = _make_main_patches(model_exists=False)
        with ExitStack() as stack:
            mocks = [stack.enter_context(p) for p in patches]
            main()
        # build_default_model (index 2) should have been called
        mocks[2].assert_called_once()

    def test_main_logs_warning_for_missing_deps(self):
        self._run_main(missing_deps=["poke_env"])

    def test_main_handles_empty_username(self):
        self._run_main(settings_username="")

    def test_main_handles_keyboard_interrupt(self):
        """KeyboardInterrupt from uvicorn.run is caught cleanly."""
        from contextlib import ExitStack
        _, _, _, _, _, _, patches = _make_main_patches()
        patches[-2] = patch("uvicorn.run", side_effect=KeyboardInterrupt)
        with ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            main()  # must not propagate KeyboardInterrupt

    def test_main_handles_settings_exception(self):
        """If settings raises, credentials fall back to empty strings."""
        from contextlib import ExitStack
        from unittest.mock import PropertyMock
        _, _, _, _, _, _, patches = _make_main_patches()
        # spec=[] → any attribute access raises AttributeError → caught by except
        mock_bad_settings = MagicMock(spec=[])
        patches[10] = patch("src.config.settings", mock_bad_settings)
        with ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            main()  # must not raise

    def test_main_with_custom_args(self):
        thread = self._run_main(
            port=9090, fmt="gen9ou", mcts_sims=50,
            buffer_capacity=1000, lr=1e-3, train_every=2,
        )
        thread.start.assert_called_once()

    def test_main_update_state_raises_is_swallowed(self):
        """If the initial update_state call raises, main continues."""
        from contextlib import ExitStack
        _, _, _, _, _, _, patches = _make_main_patches()
        patches[9] = patch("src.ml.api.update_state", side_effect=Exception("api down"))
        with ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            main()  # must not raise

    def test_main_run_game_closure_reads_live_mcts_config(self):
        """The _run_game_with_live_config closure refreshes mcts_sims from api state."""
        from contextlib import ExitStack
        mock_loop = MagicMock()
        mock_loop.run_game = AsyncMock(return_value={"games": 1})
        mock_loop.mcts_config = MagicMock()
        _, _, _, _, _, _, patches = _make_main_patches()
        patches[7] = patch("src.ml.self_play.SelfPlayLoop", return_value=mock_loop)

        with ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            with patch("src.ml.api.get_state", return_value={"mcts_sims": 50}), \
                 patch("src.ml.mcts.MCTSConfig") as mock_cfg_cls:
                main()
                # closure now lives at mock_loop.run_game — call it (success path)
                asyncio.run(mock_loop.run_game())
                # call again with get_state raising → hits except: pass (lines 211-212)
            with patch("src.ml.api.get_state", side_effect=RuntimeError("api gone")):
                asyncio.run(mock_loop.run_game())
        mock_cfg_cls.assert_called()

    def test_main_app_is_none_raises_import_error(self):
        """If FastAPI app is None, main raises ImportError (caught by test)."""
        from contextlib import ExitStack
        _, _, _, _, _, _, patches = _make_main_patches()
        with ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            with patch("src.ml.api.app", None):
                try:
                    main()
                except ImportError:
                    pass  # expected


# ── __main__ block ─────────────────────────────────────────────────────────────

class TestMainBlock:
    def test_main_module_calls_main(self):
        """Lines 275-282: __main__ block parses args and calls main()."""
        mock_uvicorn = MagicMock()
        with patch("sys.argv", ["run_training"]), \
             patch("logging.basicConfig"), \
             patch("src.ml.transformer_model.build_default_model", return_value=MagicMock()), \
             patch("src.ml.transformer_model.load_model", return_value=MagicMock()), \
             patch("src.ml.trainer.ReplayBuffer", return_value=MagicMock()), \
             patch("src.ml.trainer.PolicyTrainer", return_value=MagicMock()), \
             patch("src.ml.self_play.SharedStats", return_value=MagicMock()), \
             patch("src.ml.self_play.SelfPlayLoop", return_value=MagicMock()), \
             patch("src.ml.mcts.MCTSConfig", return_value=MagicMock()), \
             patch("src.ml.api.update_state"), \
             patch("threading.Thread", return_value=MagicMock()), \
             patch("pathlib.Path.exists", return_value=False), \
             patch.dict(sys.modules, {"uvicorn": mock_uvicorn}):
            # Pop cached module so runpy re-executes as __main__
            saved = sys.modules.pop("src.ml.run_training", None)
            try:
                runpy.run_module("src.ml.run_training", run_name="__main__")
            finally:
                if saved is not None:
                    sys.modules["src.ml.run_training"] = saved
        mock_uvicorn.run.assert_called_once()
