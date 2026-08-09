"""
Loudmouth — entry point for the packaged Windows build (PyInstaller onedir).

Built with --noconsole, so there is no stdout/stderr — uvicorn's default
logging would crash. This wrapper points both at a per-user log file before
starting the server, mirroring the install/run_server.pyw pattern without
the pythonw dependency.

Log location: %LOCALAPPDATA%\\Loudmouth\\loudmouth.log
(per-user and writable — the install dir under Program Files is not)
"""

import os
import sys


def _open_log():
    log_dir = os.path.join(
        os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "Loudmouth"
    )
    os.makedirs(log_dir, exist_ok=True)
    return open(
        os.path.join(log_dir, "loudmouth.log"), "a", buffering=1, encoding="utf-8"
    )


def run() -> None:
    log = _open_log()
    sys.stdout = log
    sys.stderr = log

    from server import main

    main()


if __name__ == "__main__":
    run()
