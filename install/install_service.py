"""
Loudmouth — Windows Service Installer
Requires: pip install pywin32

Usage:
  Install:   python install/install_service.py install
  Start:     python install/install_service.py start
  Stop:      python install/install_service.py stop
  Remove:    python install/install_service.py remove
"""

import sys
import os
import subprocess

try:
    import win32serviceutil
    import win32service
    import win32event
    import servicemanager
except ImportError:
    print("ERROR: pywin32 is required. Run: pip install pywin32")
    sys.exit(1)


class LoudmouthService(win32serviceutil.ServiceFramework):
    _svc_name_ = "Loudmouth"
    _svc_display_name_ = "Loudmouth Audio Service"
    _svc_description_ = (
        "Loudmouth — always-on audio playback service by Stark Technologies. "
        "Keeps pygame mixer loaded for reliable, clip-free audio playback."
    )

    def __init__(self, args):
        win32serviceutil.ServiceFramework.__init__(self, args)
        self.stop_event = win32event.CreateEvent(None, 0, 0, None)
        self.process = None

    def SvcStop(self):
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        win32event.SetEvent(self.stop_event)
        if self.process:
            self.process.terminate()

    def SvcDoRun(self):
        servicemanager.LogMsg(
            servicemanager.EVENTLOG_INFORMATION_TYPE,
            servicemanager.PYS_SERVICE_STARTED,
            (self._svc_name_, ""),
        )

        # Resolve paths relative to this file's location
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        python_exe = sys.executable
        server_path = os.path.join(base_dir, "server.py")

        self.process = subprocess.Popen(
            [
                python_exe, "-m", "uvicorn",
                "server:app",
                "--host", "0.0.0.0",
                "--port", "8000",
            ],
            cwd=base_dir,
        )

        # Wait for stop signal
        win32event.WaitForSingleObject(self.stop_event, win32event.INFINITE)


if __name__ == "__main__":
    if len(sys.argv) == 1:
        print(__doc__)
        sys.exit(0)
    win32serviceutil.HandleCommandLine(LoudmouthService)
