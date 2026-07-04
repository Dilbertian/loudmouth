"""
Loudmouth — windowless launcher for Windows Task Scheduler.

Run with pythonw.exe so no console window appears. Under pythonw there is no
stdout/stderr, which crashes uvicorn's default logging — so this wrapper
points both at a log file before starting the server.

Usage (what the "Loudmouth Audio Server" scheduled task runs):
    pythonw.exe install/run_server.pyw
"""

import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

log = open(os.path.join(BASE_DIR, "loudmouth.log"), "a", buffering=1, encoding="utf-8")
sys.stdout = log
sys.stderr = log

os.chdir(BASE_DIR)
sys.path.insert(0, BASE_DIR)

import uvicorn

uvicorn.run(
    "server:app",
    host=os.getenv("LOUDMOUTH_HOST", "0.0.0.0"),
    port=int(os.getenv("LOUDMOUTH_PORT", "8000")),
)
