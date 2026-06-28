"""
Loudmouth audio server — a lightweight HTTP wrapper around pygame's music player.

Routes:
    POST /play   — load and play an audio file or raw audio bytes
    GET  /status — check whether audio is currently playing
    POST /stop   — stop playback

Supported formats (via pygame/SDL_mixer): MP3, WAV, OGG, FLAC, OPUS, WV, MOD, MIDI
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import base64
import io
import pygame
import time
import os

# Absolute path to the audio/ folder next to this file, so the server works
# regardless of which directory it is launched from.
AUDIO_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "audio")

# Kept at module level so Python's garbage collector does not free the BytesIO
# buffer while pygame is still streaming from it in the background.
# The leading underscore signals that this variable is internal to this module.
_audio_buffer = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage the pygame mixer across the lifetime of the FastAPI application.

    ``asynccontextmanager`` turns this generator into a startup/shutdown hook.
    Everything before ``yield`` runs once when the server starts; everything
    after ``yield`` runs once when the server shuts down. FastAPI calls this
    automatically — you do not need to invoke it yourself.
    """
    pygame.mixer.init()
    time.sleep(1.0)  # give the audio driver a moment to fully initialise
    yield
    pygame.mixer.quit()


app = FastAPI(lifespan=lifespan)

# Allow requests from any origin so the server can be called from a browser,
# desktop app, or another service without CORS errors.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


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
