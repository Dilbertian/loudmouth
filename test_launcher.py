"""
Tests for launcher.py — log timestamps (F18) and first-run notification (F14).

Pure-logic pieces only: the MessageBox itself is Windows UI and best-effort.
"""

import launcher


class TestTimestampedLogs:
    def test_uvicorn_formatters_gain_asctime(self):
        from uvicorn.config import LOGGING_CONFIG

        launcher._timestamp_uvicorn_logs()

        for name in ("default", "access"):
            fmt = LOGGING_CONFIG["formatters"][name]
            assert fmt["fmt"].startswith("%(asctime)s")
            assert fmt["datefmt"] == "%Y-%m-%d %H:%M:%S"

    def test_idempotent(self):
        """Running twice must not stack a second asctime prefix."""
        from uvicorn.config import LOGGING_CONFIG

        launcher._timestamp_uvicorn_logs()
        launcher._timestamp_uvicorn_logs()

        fmt = LOGGING_CONFIG["formatters"]["default"]["fmt"]
        assert fmt.count("%(asctime)s") == 1


class TestFirstRunMarker:
    def test_first_call_true_then_false(self, tmp_path):
        assert launcher._consume_first_run(str(tmp_path)) is True
        assert (tmp_path / launcher.FIRST_RUN_MARKER).exists()
        assert launcher._consume_first_run(str(tmp_path)) is False

    def test_unwritable_dir_fails_quiet(self, tmp_path):
        missing = str(tmp_path / "does" / "not" / "exist")
        assert launcher._consume_first_run(missing) is False
