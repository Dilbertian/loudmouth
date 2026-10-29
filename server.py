"""
Loudmouth audio server — a lightweight HTTP wrapper around pygame's music player.

Routes:
    GET  /health — service identity: version, protocol, bound port, uptime
    POST /play   — load and play an audio file or raw audio bytes
    GET  /status — check whether audio is currently playing
    POST /stop   — stop playback

Supported formats (via pygame/SDL_mixer): MP3, WAV, OGG, FLAC, OPUS, WV, MOD, MIDI

Network policy:
    Binds 127.0.0.1 by default (Loudmouth is an actuator — /play has a physical
    effect on the host machine; a LAN-open default would let any peer drive the
    speakers). Set LOUDMOUTH_HOST=0.0.0.0 for fleet/dev use.
    Ports: primary 8765, fallback 8766. Both occupied → clean exit.
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel
import base64
import io
import json
import socket
import sys
import pygame
import time
import os

# Single source of truth for the release version — the installer, /health, and
# any future update check all read this constant (pyproject.toml pulls it via
# setuptools dynamic metadata; packaging scripts parse it from this file).
__version__ = "1.1.0"

# API compatibility gate. IdeaLoom's detectLoudmouth() checks
# `protocol >= minimumProtocol` — an integer comparison, never a
# version-string comparison. Bump ONLY on breaking API changes.
PROTOCOL = 1

# Primary and fallback ports — fixed, permanent, documented in README.
# Port 8000 is abandoned (collision-prone dev-server favorite).
DEFAULT_PORTS = (8765, 8766)

# Loudmouth is an actuator, so CORS is a restricted allowlist — not "*".
# Override via LOUDMOUTH_CORS_ORIGINS (comma-separated).
DEFAULT_ALLOWED_ORIGINS = [
    "https://idealoom.ai",
    "https://www.idealoom.ai",
    "https://app.idealoom.ai",          # the production app origin
    "http://localhost:5173",            # loom dev
    "http://100.64.58.91:8910",         # tailnet clean-machine test path
]

# Callers may activate only an app/origin pair shipped in this trusted registry.
TRUSTED_APPLICATIONS = {
    "idealoom": set(DEFAULT_ALLOWED_ORIGINS),
    "zanmyo": {"https://zen.zanmyo.com"},
}

# In a PyInstaller onedir build, bundled data lives in _internal (sys._MEIPASS),
# not next to this source file. Otherwise: the audio/ folder next to this file,
# so the server works regardless of which directory it is launched from.
if getattr(sys, "frozen", False):
    AUDIO_DIR = os.path.join(sys._MEIPASS, "audio")
else:
    _here = os.path.dirname(os.path.abspath(__file__))
    _pkg_audio = os.path.join(_here, "loudmouth", "audio")
    if not os.path.isdir(os.path.join(_here, "audio")) and os.path.isdir(_pkg_audio):
        AUDIO_DIR = _pkg_audio
    else:
        AUDIO_DIR = os.path.join(_here, "audio")

# Kept at module level so Python's garbage collector does not free the BytesIO
# buffer while pygame is still streaming from it in the background.
# The leading underscore signals that this variable is internal to this module.
_audio_buffer = None

# Held at module level so the keep-alive Sound is never garbage-collected
# while its channel is still looping it.
_keepalive_sound = None

# Set when the mixer comes up (lifespan) — /health reports seconds since then.
_start_time = None

# Set by main() once a port is chosen. When the server is launched some other
# way (e.g. `uvicorn server:app --port N`), /health falls back to the port
# uvicorn reports in the request scope.
_bound_port = None


def _start_keepalive() -> None:
    """Loop an inaudible signal forever so the audio endpoint never sleeps.

    Many output devices (Realtek codec power saving, laptop smart amps,
    Bluetooth A2DP, HDMI receivers) mute or power down after a few seconds of
    digital silence and need 100-500 ms to wake once real samples arrive —
    which audibly clips the first word of each TTS clip. A ±1 LSB square wave
    (~ -90 dBFS, far below audibility) keeps the endpoint's silence detector
    from ever engaging, so playback reaches the speaker from sample one.
    """
    global _keepalive_sound
    freq, size, channels = pygame.mixer.get_init()
    # Defaults target external amps/soundbars with signal-sensing standby:
    # their broadband analog detectors need real energy (measured ~-25 dBFS
    # threshold on a typical unit) but 21 kHz is above human hearing, so a
    # loud-but-ultrasonic tone holds them awake silently. Quiet low-frequency
    # tones (-66 dBFS at 150 Hz) and LSB dither proved insufficient in
    # practice. Override per machine via env if a device misbehaves.
    import math
    import struct
    tone_hz = int(os.getenv("LOUDMOUTH_KEEPALIVE_HZ", "21000"))
    tone_db = float(os.getenv("LOUDMOUTH_KEEPALIVE_DBFS", "-20"))
    amp = int(32767 * (10 ** (tone_db / 20)))
    frames = []
    for i in range(freq):
        v = int(amp * math.sin(2 * math.pi * tone_hz * i / freq))
        frames.append(struct.pack("<h", v) * channels)
    _keepalive_sound = pygame.mixer.Sound(buffer=b"".join(frames))
    _keepalive_sound.play(loops=-1)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage the pygame mixer across the lifetime of the FastAPI application.

    ``asynccontextmanager`` turns this generator into a startup/shutdown hook.
    Everything before ``yield`` runs once when the server starts; everything
    after ``yield`` runs once when the server shuts down. FastAPI calls this
    automatically — you do not need to invoke it yourself.
    """
    global _start_time
    pygame.mixer.init()
    time.sleep(1.0)  # give the audio driver a moment to fully initialise
    _start_keepalive()
    _start_time = time.monotonic()
    yield
    pygame.mixer.quit()


def registration_path() -> str:
    root = os.getenv("LOUDMOUTH_STATE_DIR") or os.path.join(
        os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "Loudmouth"
    )
    return os.path.join(root, "integrations.json")


def registered_origins() -> set[str]:
    try:
        with open(registration_path(), encoding="utf-8") as fh:
            apps = json.load(fh).get("applications", [])
    except (OSError, ValueError, TypeError):
        return set()
    return {origin for app_id in apps for origin in TRUSTED_APPLICATIONS.get(app_id, set())}


def allowed_origins() -> list[str]:
    """Configured defaults plus origins activated by trusted applications."""
    env = os.getenv("LOUDMOUTH_CORS_ORIGINS")
    configured = ([origin.strip() for origin in env.split(",") if origin.strip()]
                  if env else list(DEFAULT_ALLOWED_ORIGINS))
    return sorted(set(configured) | registered_origins())


def register_application(app_id: str, origin: str) -> bool:
    app_id = app_id.lower()
    if origin not in TRUSTED_APPLICATIONS.get(app_id, set()):
        return False
    path = registration_path()
    try:
        with open(path, encoding="utf-8") as fh:
            apps = set(json.load(fh).get("applications", []))
    except (OSError, ValueError, TypeError):
        apps = set()
    apps.add(app_id)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump({"applications": sorted(apps)}, fh)
    os.replace(tmp, path)
    return True


app = FastAPI(lifespan=lifespan)


@app.middleware("http")
async def trusted_cors(request: Request, call_next):
    """Dynamic exact-origin CORS with a bootstrap path for trusted apps."""
    origin = request.headers.get("origin")
    bootstrap = request.url.path == "/v1/integrations/register" and any(
        origin in origins for origins in TRUSTED_APPLICATIONS.values()
    )
    allowed = bool(origin and (origin in allowed_origins() or bootstrap))
    if request.method == "OPTIONS":
        if not allowed:
            return Response("Disallowed CORS origin", status_code=400)
        response = Response(status_code=200)
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = request.headers.get(
            "access-control-request-headers", "content-type"
        )
        response.headers["Access-Control-Max-Age"] = "600"
        response.headers["Access-Control-Allow-Private-Network"] = "true"
    else:
        response = await call_next(request)
    if allowed:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Vary"] = "Origin"
    return response


class IntegrationRequest(BaseModel):
    app_id: str
    protocol_version: int = PROTOCOL


@app.post("/v1/integrations/register")
async def register_integration(request: Request, registration: IntegrationRequest):
    origin = request.headers.get("origin", "")
    app_id = registration.app_id.lower()
    if registration.protocol_version > PROTOCOL:
        raise HTTPException(status_code=409, detail="Unsupported Loudmouth protocol")
    if not register_application(app_id, origin):
        raise HTTPException(status_code=403, detail="Application/origin is not trusted")
    return {"status": "registered", "app_id": app_id, "origin": origin,
            "protocol": PROTOCOL, "idempotent": True}


@app.get("/health")
async def health(request: Request):
    """Service identity for IdeaLoom's detectLoudmouth() and human debugging.

    Returns:
        ``status``   — always ``"ok"`` if this answers at all.
        ``version``  — release version string (single ``__version__`` source).
        ``protocol`` — integer API-compatibility constant; consumers gate on
                       ``protocol >= minimum``, never on version strings.
        ``port``     — the actually bound port (8765 or fallback 8766).
        ``uptime``   — seconds since the mixer came up.
    """
    port = _bound_port
    if port is None:
        server = request.scope.get("server")
        port = server[1] if server else None
    return {
        "status": "ok",
        "version": __version__,
        "protocol": PROTOCOL,
        "port": port,
        "uptime": int(time.monotonic() - _start_time) if _start_time is not None else 0,
    }


class PlayRequest(BaseModel):
    """Request body for POST /play.

    Pydantic's BaseModel validates incoming JSON automatically and maps each
    key to a typed Python attribute. If a required type doesn't match, FastAPI
    returns a 422 Unprocessable Entity before your code even runs.

    Provide exactly one of ``file`` or ``audio``.

    Attributes:
        file:   Filename (no directory path) of an audio file inside audio/.
        audio:  Raw audio data encoded as a base64 string.
        format: Format hint for base64 audio (e.g. ``"mp3"``, ``"ogg"``).
                When omitted, pygame tries to detect the format automatically.
    """

    file: str | None = None
    audio: str | None = None
    format: str | None = None


@app.post("/play")
async def play(request: PlayRequest):
    """Load and immediately begin playing audio.

    Only one audio stream can be active at a time. Calling this endpoint while
    audio is already playing will replace the current track.

    Args:
        request: JSON body matching :class:`PlayRequest`.

    Returns:
        ``{"status": "playing"}`` on success.

    Raises:
        400: Invalid base64 data, unsupported format, or missing body fields.
        404: The requested filename does not exist in ``audio/``.
    """
    global _audio_buffer  # declare intent to update the module-level variable
    if request.audio:
        try:
            data = base64.b64decode(request.audio)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid base64 audio data")

        _audio_buffer = io.BytesIO(data)
        try:
            # Pass an empty string when no format hint is supplied so pygame
            # attempts to detect the format from the stream content itself.
            pygame.mixer.music.load(_audio_buffer, request.format or "")
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Unsupported audio format: {e}")

    elif request.file:
        # os.path.basename strips any directory components (e.g. "../../etc/passwd")
        # from the supplied name, preventing a path-traversal attack.
        filename = os.path.basename(request.file)
        path = os.path.join(AUDIO_DIR, filename)
        if not os.path.isfile(path):
            raise HTTPException(status_code=404, detail=f"File not found: {filename}")

        _audio_buffer = None  # release any previously held buffer
        try:
            pygame.mixer.music.load(path)  # format is inferred from file extension
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Unsupported audio format: {e}")

    else:
        raise HTTPException(status_code=400, detail="Provide either 'file' or 'audio'")

    pygame.mixer.music.play()
    return {"status": "playing"}


@app.get("/status")
async def status():
    """Return whether audio is currently playing.

    Returns:
        ``{"playing": true}`` while audio is active, ``{"playing": false}`` otherwise.
    """
    return {"playing": bool(pygame.mixer.music.get_busy())}


@app.post("/stop")
async def stop():
    """Stop audio playback immediately.

    Returns:
        ``{"status": "stopped"}``
    """
    pygame.mixer.music.stop()
    return {"status": "stopped"}


def resolve_host() -> str:
    """Bind address: loopback-only unless LOUDMOUTH_HOST overrides (fleet/dev)."""
    return os.getenv("LOUDMOUTH_HOST", "127.0.0.1")


def pick_port(host: str, candidates: tuple[int, ...] = DEFAULT_PORTS) -> int:
    """Return the first bindable port from ``candidates``.

    LOUDMOUTH_PORT skips probing entirely — an explicit port is used as-is so
    a misconfiguration fails loudly instead of silently moving ports.

    Raises:
        SystemExit: every candidate is occupied. The message names the ports
            so a support log line is enough to diagnose.
    """
    env = os.getenv("LOUDMOUTH_PORT")
    if env:
        return int(env)
    for port in candidates:
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            probe.bind((host, port))
        except OSError:
            continue
        finally:
            probe.close()
        return port
    ports = ", ".join(str(p) for p in candidates)
    print(f"Loudmouth: ports {ports} are all in use — exiting.", file=sys.stderr, flush=True)
    raise SystemExit(1)


def main() -> None:
    """Run the server with the consumer port policy (8765, fallback 8766).

    This is the entry point for the packaged Windows build and run scripts.
    The probe in pick_port() and uvicorn's own bind are not atomic; the tiny
    race is acceptable — uvicorn still fails cleanly if the port is stolen.
    """
    global _bound_port
    import uvicorn

    host = resolve_host()
    _bound_port = pick_port(host)
    uvicorn.run(app, host=host, port=_bound_port)


if __name__ == "__main__":
    main()
