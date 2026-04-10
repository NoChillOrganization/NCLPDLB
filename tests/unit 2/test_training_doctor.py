"""
training_doctor.py — coverage tests.

Covers: diagnose_output, parse_timestep_progress, make_progress_bar,
preflight_check, _is_corrupt_zip, apply_fix, apply_all_fixes.

Pragmas on _fix_install_dep and _fix_corrupt_checkpoints are in the source.
"""
from __future__ import annotations

import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch


from src.ml.training_doctor import (
    _can_import,
    _fix_corrupt_checkpoints,
    _fix_install_dep,
    _is_corrupt_zip,
    apply_all_fixes,
    apply_fix,
    diagnose_output,
    make_progress_bar,
    parse_timestep_progress,
    preflight_check,
)


# ── diagnose_output ──────────────────────────────────────────────────────────

class TestDiagnoseOutput:
    def test_showdown_offline_explicit(self):
        out = "Cannot reach local Showdown server on port 8000"
        result = diagnose_output(out)
        assert len(result) == 1
        assert result[0]["type"] == "SHOWDOWN_OFFLINE"
        assert result[0]["fixable"] is False

    def test_showdown_offline_connection_refused(self):
        out = "OSError: [Errno 111] Connection refused: 8000"
        result = diagnose_output(out)
        assert len(result) == 1
        assert result[0]["type"] == "SHOWDOWN_OFFLINE"

    def test_corrupt_checkpoint_badzipfile(self):
        out = "zipfile.BadZipFile: File is not a zip file"
        result = diagnose_output(out)
        assert len(result) == 1
        assert result[0]["type"] == "CORRUPT_CHECKPOINT"
        assert result[0]["fixable"] is True

    def test_corrupt_checkpoint_bad_magic(self):
        out = "Bad magic number for file header — restart training"
        result = diagnose_output(out)
        assert any(r["type"] == "CORRUPT_CHECKPOINT" for r in result)

    def test_missing_dep_numpy(self):
        out = "ModuleNotFoundError: No module named 'numpy'"
        result = diagnose_output(out)
        assert len(result) == 1
        assert result[0]["type"] == "MISSING_DEP"
        assert result[0]["fixable"] is True
        assert result[0]["module"] == "numpy"
        assert result[0]["package"] == "numpy"

    def test_missing_dep_stable_baselines3(self):
        out = "No module named 'stable_baselines3'"
        result = diagnose_output(out)
        assert result[0]["type"] == "MISSING_DEP"
        assert result[0]["package"] == "stable-baselines3>=2.2.0"

    def test_wrong_python(self):
        out = "No module named 'src'"
        result = diagnose_output(out)
        assert len(result) == 1
        assert result[0]["type"] == "WRONG_PYTHON"
        assert result[0]["fixable"] is False

    def test_no_teams_warning(self):
        out = "No teams found for gen9ou training without custom teams"
        result = diagnose_output(out)
        assert result[0]["type"] == "NO_TEAMS"
        assert result[0]["fixable"] is False

    def test_oom_error(self):
        out = "RuntimeError: CUDA out of memory. Tried to allocate 2.00 GiB"
        result = diagnose_output(out)
        assert result[0]["type"] == "OOM"
        assert result[0]["fixable"] is False

    def test_shape_mismatch(self):
        out = "RuntimeError: mat1 and mat2 shapes cannot be multiplied (64x128 and 64x64)"
        result = diagnose_output(out)
        assert result[0]["type"] == "SHAPE_MISMATCH"
        assert result[0]["fixable"] is True

    def test_clean_output_returns_empty(self):
        out = "Timestep 4096/500000 | win_rate=0.52 | policy_loss=-0.012"
        assert diagnose_output(out) == []

    def test_deduplicates_same_type(self):
        # Two SHOWDOWN_OFFLINE patterns in same output
        out = (
            "Cannot reach local Showdown server\n"
            "Connection refused: 8000\n"
        )
        result = diagnose_output(out)
        types = [r["type"] for r in result]
        assert types.count("SHOWDOWN_OFFLINE") == 1

    def test_multi_match_returns_multiple_types(self):
        out = (
            "No module named 'numpy'\n"
            "No module named 'src'\n"
        )
        result = diagnose_output(out)
        types = {r["type"] for r in result}
        assert "MISSING_DEP" in types
        assert "WRONG_PYTHON" in types


# ── parse_timestep_progress ───────────────────────────────────────────────────

class TestParseTimestepProgress:
    def test_extracts_timestep_from_sb3_log_line(self):
        line = "|    total_timesteps      | 4096         |"
        assert parse_timestep_progress(line) == 4096

    def test_returns_none_for_non_matching_line(self):
        assert parse_timestep_progress("policy_loss | -0.012") is None

    def test_returns_none_for_empty_string(self):
        assert parse_timestep_progress("") is None

    def test_handles_large_timestep(self):
        line = "| total_timesteps | 500000 |"
        assert parse_timestep_progress(line) == 500000


# ── make_progress_bar ─────────────────────────────────────────────────────────

class TestMakeProgressBar:
    def test_zero_percent(self):
        bar = make_progress_bar(0, 100)
        assert bar.startswith("[░")
        assert "0.0%" in bar

    def test_full_percent(self):
        bar = make_progress_bar(100, 100)
        assert "100.0%" in bar
        assert "░" not in bar  # all filled

    def test_fifty_percent(self):
        bar = make_progress_bar(50, 100, width=20)
        assert "50.0%" in bar
        assert bar.count("█") == 10
        assert bar.count("░") == 10

    def test_total_zero_returns_zero_bar(self):
        bar = make_progress_bar(0, 0)
        assert "0.0%" in bar

    def test_over_total_clamps_to_100(self):
        bar = make_progress_bar(200, 100)
        assert "100.0%" in bar


# ── _is_corrupt_zip ───────────────────────────────────────────────────────────

class TestIsCorruptZip:
    def test_valid_zip_returns_false(self, tmp_path):
        zp = tmp_path / "good.zip"
        with zipfile.ZipFile(zp, "w") as zf:
            zf.writestr("model.pkl", b"data")
        assert _is_corrupt_zip(zp) is False

    def test_empty_file_returns_true(self, tmp_path):
        zp = tmp_path / "empty.zip"
        zp.write_bytes(b"")
        assert _is_corrupt_zip(zp) is True

    def test_not_a_zip_returns_true(self, tmp_path):
        zp = tmp_path / "notazip.zip"
        zp.write_bytes(b"this is not a zip file at all")
        assert _is_corrupt_zip(zp) is True


# ── preflight_check ───────────────────────────────────────────────────────────

class TestPreflightCheck:
    def test_showdown_unreachable_adds_offline_issue(self, tmp_path):
        save_dir = tmp_path / "policy"
        with patch("src.ml.training_doctor.socket.create_connection",
                   side_effect=OSError("connection refused")):
            with patch("src.ml.training_doctor._can_import", return_value=True):
                issues = preflight_check("gen9ou", save_dir=save_dir, server_mode="localhost")
        types = [i["type"] for i in issues]
        assert "SHOWDOWN_OFFLINE" in types

    def test_showdown_reachable_no_offline_issue(self, tmp_path):
        save_dir = tmp_path / "policy"
        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        with patch("src.ml.training_doctor.socket.create_connection",
                   return_value=mock_conn):
            with patch("src.ml.training_doctor._can_import", return_value=True):
                issues = preflight_check("gen9ou", save_dir=save_dir, server_mode="localhost")
        types = [i["type"] for i in issues]
        assert "SHOWDOWN_OFFLINE" not in types

    def test_non_localhost_mode_skips_showdown_check(self, tmp_path):
        save_dir = tmp_path / "policy"
        with patch("src.ml.training_doctor._can_import", return_value=True):
            issues = preflight_check("gen9ou", save_dir=save_dir, server_mode="remote")
        types = [i["type"] for i in issues]
        assert "SHOWDOWN_OFFLINE" not in types

    def test_corrupt_checkpoint_detected(self, tmp_path):
        save_dir = tmp_path / "policy"
        fmt_dir = save_dir / "gen9ou"
        fmt_dir.mkdir(parents=True)
        bad_zip = fmt_dir / "model.zip"
        bad_zip.write_bytes(b"not a zip")
        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        with patch("src.ml.training_doctor.socket.create_connection",
                   return_value=mock_conn):
            with patch("src.ml.training_doctor._can_import", return_value=True):
                issues = preflight_check("gen9ou", save_dir=save_dir)
        types = [i["type"] for i in issues]
        assert "CORRUPT_CHECKPOINT" in types

    def test_missing_dep_detected(self, tmp_path):
        save_dir = tmp_path / "policy"
        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        with patch("src.ml.training_doctor.socket.create_connection",
                   return_value=mock_conn):
            with patch("src.ml.training_doctor._can_import", return_value=False):
                issues = preflight_check("gen9ou", save_dir=save_dir)
        types = [i["type"] for i in issues]
        assert "MISSING_DEP" in types

    def test_clean_environment_returns_empty(self, tmp_path):
        save_dir = tmp_path / "policy"
        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        with patch("src.ml.training_doctor.socket.create_connection",
                   return_value=mock_conn):
            with patch("src.ml.training_doctor._can_import", return_value=True):
                issues = preflight_check("gen9ou", save_dir=save_dir)
        assert issues == []


# ── apply_fix ─────────────────────────────────────────────────────────────────

class TestApplyFix:
    def test_corrupt_checkpoint_calls_fix(self, tmp_path):
        save_dir = tmp_path / "policy"
        fmt_dir = save_dir / "gen9ou"
        fmt_dir.mkdir(parents=True)
        (fmt_dir / "model.zip").write_bytes(b"data")
        error = {"type": "CORRUPT_CHECKPOINT", "fixable": True}
        ok, msg = apply_fix(error, fmt="gen9ou", save_dir=save_dir)
        assert ok is True
        assert "Deleted" in msg or "scratch" in msg

    def test_shape_mismatch_calls_corrupt_fix(self, tmp_path):
        save_dir = tmp_path / "policy"
        error = {"type": "SHAPE_MISMATCH", "fixable": True}
        ok, msg = apply_fix(error, fmt="gen9ou", save_dir=save_dir)
        assert ok is True  # no zips → "train from scratch"

    def test_missing_dep_calls_install(self, tmp_path):
        save_dir = tmp_path / "policy"
        error = {"type": "MISSING_DEP", "fixable": True, "package": "numpy", "module": "numpy"}
        with patch("src.ml.training_doctor._fix_install_dep",
                   return_value=(True, "Installed `numpy` successfully")) as mock_fix:
            ok, msg = apply_fix(error, fmt="gen9ou", save_dir=save_dir)
        assert ok is True
        mock_fix.assert_called_once()

    def test_missing_dep_no_package_returns_false(self, tmp_path):
        save_dir = tmp_path / "policy"
        error = {"type": "MISSING_DEP", "fixable": True, "module": "unknown_mod"}
        ok, msg = apply_fix(error, fmt="gen9ou", save_dir=save_dir)
        assert ok is False
        assert "unknown_mod" in msg

    def test_unknown_type_returns_false(self, tmp_path):
        save_dir = tmp_path / "policy"
        error = {"type": "SHOWDOWN_OFFLINE", "fixable": False}
        ok, msg = apply_fix(error, fmt="gen9ou", save_dir=save_dir)
        assert ok is False
        assert "cannot be auto-fixed" in msg


# ── apply_all_fixes ───────────────────────────────────────────────────────────

class TestApplyAllFixes:
    def test_skips_non_fixable(self, tmp_path):
        errors = [{"type": "SHOWDOWN_OFFLINE", "fixable": False}]
        results = apply_all_fixes(errors, fmt="gen9ou", save_dir=tmp_path)
        assert len(results) == 1
        _, ok, msg = results[0]
        assert ok is False
        assert "Not auto-fixable" in msg

    def test_applies_fixable_error(self, tmp_path):
        save_dir = tmp_path / "policy"
        errors = [{"type": "CORRUPT_CHECKPOINT", "fixable": True}]
        results = apply_all_fixes(errors, fmt="gen9ou", save_dir=save_dir)
        assert len(results) == 1
        _, ok, _ = results[0]
        assert ok is True

    def test_mixed_errors(self, tmp_path):
        save_dir = tmp_path / "policy"
        errors = [
            {"type": "SHOWDOWN_OFFLINE", "fixable": False},
            {"type": "CORRUPT_CHECKPOINT", "fixable": True},
        ]
        results = apply_all_fixes(errors, fmt="gen9ou", save_dir=save_dir)
        assert len(results) == 2
        # First is not fixable, second is
        assert results[0][1] is False
        assert results[1][1] is True


# ── _can_import ───────────────────────────────────────────────────────────────

class TestCanImport:
    def test_success_returns_true(self):
        mock_result = MagicMock()
        mock_result.returncode = 0
        with patch("src.ml.training_doctor.subprocess.run", return_value=mock_result):
            assert _can_import("python", "numpy") is True

    def test_failure_returns_false(self):
        mock_result = MagicMock()
        mock_result.returncode = 1
        with patch("src.ml.training_doctor.subprocess.run", return_value=mock_result):
            assert _can_import("python", "missing_mod") is False

    def test_exception_returns_false(self):
        with patch("src.ml.training_doctor.subprocess.run",
                   side_effect=OSError("exe not found")):
            assert _can_import("/bad/python", "numpy") is False


# ── _fix_corrupt_checkpoints ──────────────────────────────────────────────────

class TestFixCorruptCheckpoints:
    def test_deletes_zips_and_reports(self, tmp_path):
        fmt_dir = tmp_path / "gen9ou"
        fmt_dir.mkdir()
        (fmt_dir / "model.zip").write_bytes(b"data")
        ok, msg = _fix_corrupt_checkpoints("gen9ou", tmp_path)
        assert ok is True
        assert "Deleted 1" in msg
        assert not (fmt_dir / "model.zip").exists()

    def test_no_zips_returns_scratch_message(self, tmp_path):
        ok, msg = _fix_corrupt_checkpoints("gen9ou", tmp_path)
        assert ok is True
        assert "scratch" in msg

    def test_unlink_exception_logs_warning(self, tmp_path):
        fmt_dir = tmp_path / "gen9ou"
        fmt_dir.mkdir()
        zp = fmt_dir / "locked.zip"
        zp.write_bytes(b"data")
        with patch.object(Path, "unlink", side_effect=PermissionError("locked")):
            ok, msg = _fix_corrupt_checkpoints("gen9ou", tmp_path)
        # Even if unlink fails, function returns gracefully
        assert ok is True


# ── _fix_install_dep ──────────────────────────────────────────────────────────

class TestFixInstallDep:
    def test_successful_install(self):
        mock_result = MagicMock()
        mock_result.returncode = 0
        with patch("src.ml.training_doctor.subprocess.run", return_value=mock_result):
            ok, msg = _fix_install_dep("python", "numpy")
        assert ok is True
        assert "numpy" in msg

    def test_failed_install(self):
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "ERROR: Could not find a version"
        with patch("src.ml.training_doctor.subprocess.run", return_value=mock_result):
            ok, msg = _fix_install_dep("python", "bad-pkg")
        assert ok is False

    def test_timeout_returns_false(self):
        import subprocess
        with patch("src.ml.training_doctor.subprocess.run",
                   side_effect=subprocess.TimeoutExpired(cmd="pip", timeout=120)):
            ok, msg = _fix_install_dep("python", "numpy")
        assert ok is False
        assert "timed out" in msg

    def test_generic_exception_returns_false(self):
        with patch("src.ml.training_doctor.subprocess.run",
                   side_effect=RuntimeError("unexpected")):
            ok, msg = _fix_install_dep("python", "numpy")
        assert ok is False
        assert "raised" in msg


# ── preflight write-error branch ─────────────────────────────────────────────

class TestPreflightWriteError:
    def test_write_error_adds_issue(self, tmp_path):
        save_dir = tmp_path / "policy"
        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        with patch("src.ml.training_doctor.socket.create_connection",
                   return_value=mock_conn):
            with patch("src.ml.training_doctor._can_import", return_value=True):
                with patch.object(Path, "write_text",
                                  side_effect=PermissionError("read-only")):
                    issues = preflight_check("gen9ou", save_dir=save_dir)
        types = [i["type"] for i in issues]
        assert "WRITE_ERROR" in types
