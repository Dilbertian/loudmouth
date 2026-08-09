# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for the Loudmouth Windows consumer build.

Deliberate choices (see consumer-readiness sprint brief):
  --onedir     Inno Setup already provides the single download; onedir avoids
               self-extraction, starts faster, debugs easier, and gives AV
               scanners less unusual loader behavior to flag.
  --noconsole  Consumers never see a console window (launcher.py redirects
               uvicorn logging to %LOCALAPPDATA%\\Loudmouth\\loudmouth.log).
  --noupx      UPX-packed executables are a classic AV false-positive trigger.

Build via packaging/build.ps1, or directly:
    pyinstaller --clean --noconfirm packaging/loudmouth.spec
(run from the repo root)
"""

import os

REPO_ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))

a = Analysis(
    [os.path.join(REPO_ROOT, "launcher.py")],
    pathex=[REPO_ROOT],
    binaries=[],
    # Bundled into _internal/audio — server.py resolves AUDIO_DIR via
    # sys._MEIPASS when frozen.
    datas=[(os.path.join(REPO_ROOT, "audio"), "audio")],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # pygame pulls these opportunistically; none are used by the server
        "tkinter",
        "numpy",
        "pygame.tests",
        "pygame.examples",
        "pygame.docs",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="loudmouth",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="Loudmouth",
)
