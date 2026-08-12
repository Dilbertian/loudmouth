"""
Loudmouth — entry point for the packaged Windows build (PyInstaller onedir).

Built with --noconsole, so there is no stdout/stderr — uvicorn's default
logging would crash. This wrapper points both at a per-user log file before
starting the server, mirroring the install/run_server.pyw pattern without
the pythonw dependency.

Log location: %LOCALAPPDATA%\\Loudmouth\\loudmouth.log
(per-user and writable — the install dir under Program Files is not)
"""

import ctypes
import os
import sys
import threading

FIRST_RUN_MARKER = "first_run_notified"

FIRST_RUN_MESSAGE = (
    "Loudmouth is now running in the background.\n\n"
    "IdeaLoom will find it automatically — you don't need to do anything.\n"
    "It also starts by itself each time you sign in to Windows."
)


def _log_dir() -> str:
    return os.path.join(
        os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "Loudmouth"
    )


def _open_log():
    log_dir = _log_dir()
    os.makedirs(log_dir, exist_ok=True)
    return open(
        os.path.join(log_dir, "loudmouth.log"), "a", buffering=1, encoding="utf-8"
    )


def _timestamp_uvicorn_logs() -> None:
    """Prepend asctime to uvicorn's formatters (F18).

    The packaged build's only output is the log file, and uvicorn's default
    format carries no timestamps — field debugging without them is pain.
    Mutating LOGGING_CONFIG before uvicorn.run() reads it applies the format
    to both the error and access loggers.
    """
    from uvicorn.config import LOGGING_CONFIG

    for name in ("default", "access"):
        formatter = LOGGING_CONFIG["formatters"][name]
        if not formatter["fmt"].startswith("%(asctime)s"):
            formatter["fmt"] = "%(asctime)s " + formatter["fmt"]
        formatter["datefmt"] = "%Y-%m-%d %H:%M:%S"


def _consume_first_run(log_dir: str) -> bool:
    """True exactly once per install: the marker file is created on the first
    call and checked on every later one. Uninstall removes the log dir, so a
    reinstall notifies again — intended."""
    marker = os.path.join(log_dir, FIRST_RUN_MARKER)
    if os.path.exists(marker):
        return False
    try:
        with open(marker, "w", encoding="utf-8") as fh:
            fh.write("shown\n")
    except OSError:
        return False
    return True


def _notify_first_run() -> None:
    """One-time visible feedback that the install worked (F14).

    Without this the app runs headless and a fresh consumer sees "nothing
    happens". A plain MessageBox needs no tray icon, message pump, or extra
    dependency; it runs on a daemon thread so the server never waits on OK.
    """
    if not _consume_first_run(_log_dir()):
        return

    def show():
        try:
            # F41 (field run 2026-08-12): the box popped BEHIND other windows
            # on a real install. TOPMOST alone can lose to the installer's own
            # elevation context; SYSTEMMODAL forces the WS_EX_TOPMOST z-order
            # from a background process (the classic reliable combination).
            MB_ICONINFORMATION, MB_SYSTEMMODAL = 0x40, 0x1000
            MB_SETFOREGROUND, MB_TOPMOST = 0x10000, 0x40000
            ctypes.windll.user32.MessageBoxW(
                None, FIRST_RUN_MESSAGE, "Loudmouth is running",
                MB_ICONINFORMATION | MB_SYSTEMMODAL | MB_SETFOREGROUND | MB_TOPMOST,
            )
        except Exception:
            pass  # notification is best-effort — never take the server down

    threading.Thread(target=show, daemon=True).start()


def run() -> None:
    log = _open_log()
    sys.stdout = log
    sys.stderr = log

    _timestamp_uvicorn_logs()
    _notify_first_run()

    from server import main

    main()


if __name__ == "__main__":
    run()
