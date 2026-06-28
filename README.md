# Loudmouth

**A lightweight, always-on audio playback service for Python applications.**

> *"pygame, simplified. Two lines of code instead of an all-day project."*

Built by **Stark Technologies** — Lead Developer: Tim Stark  
Developed with assistance from Claude Code (Anthropic) and Walter (Hermes Agent, Nous Research)

---

## Why Loudmouth?

Playing audio reliably in Python is surprisingly painful. pygame's mixer needs to be initialized, kept alive, and managed carefully — or you get clipped playback, intermittent failures, and audio that cuts off mid-sentence.

**Loudmouth solves this by staying loaded.** It runs as a persistent HTTP service, keeping pygame's mixer warm and ready. Any application — a web app, an agent, a script — can trigger audio playback with a single HTTP call. No initialization overhead, no clipping, no surprises.

### Without Loudmouth
```python
import pygame
import time

pygame.mixer.init()
time.sleep(1.0)  # wait for driver to initialize
pygame.mixer.music.load("audio/announcement.mp3")
pygame.mixer.music.play()
while pygame.mixer.music.get_busy():
    time.sleep(0.1)
pygame.mixer.quit()
```

### With Loudmouth
```python
import httpx
httpx.post("http://localhost:8000/play", json={"file": "announcement.mp3"})
```

---

## Features

- **Always-on** — runs as a systemd service (Linux) or Windows Service; starts on boot
- **HTTP API** — play, stop, and check status from any language or tool
- **Multi-format** — MP3, WAV, OGG, FLAC, OPUS, WV, MOD, MIDI (via pygame/SDL_mixer)
- **Base64 audio** — stream raw audio bytes directly without touching the filesystem
- **Path-safe** — directory traversal attacks blocked at the API layer
- **CORS-enabled** — call it from a browser, desktop app, or another service
- **Lightweight** — FastAPI + pygame, no database, no config files

---

## Quick Start

### Install via pip

```bash
pip install loudmouth
```

### Install from source

```bash
pip install fastapi pygame-ce uvicorn
# or with uv:
uv sync
```

### Run manually

```bash
uvicorn server:app --host 0.0.0.0 --port 8000
```

### Install as a service (optional)

Service installation is optional — use it if you want Loudmouth to start automatically on boot and run in the background.

**Linux (systemd):**
```bash
sudo bash install/install.sh
```

This creates a `loudmouth` system user, installs to `/opt/loudmouth`, sets up a venv, and registers + starts the systemd service.

```bash
# Check status
systemctl status loudmouth

# View logs
journalctl -u loudmouth -f

# Uninstall
sudo bash install/uninstall.sh
```

**Windows:**
```bash
pip install pywin32
python install/install_service.py install
python install/install_service.py start
```

Other Windows service commands:
```bash
python install/install_service.py stop
python install/install_service.py remove
```

---

## API Reference

### `POST /play`

Play an audio file or raw audio bytes.

**Play a file from the `audio/` folder:**
```json
{ "file": "loudmouth-test.mp3" }
```

**MP3 files are auto-detected** — just pass the filename, no format hint needed.

For all other formats, pass the `format` field as a hint to pygame:
```json
{ "file": "sound.ogg", "format": "ogg" }
```

If you pass an unsupported format, Loudmouth returns a `400` with a clear error message telling you what went wrong.

**Play base64-encoded audio:**
```json
{ "audio": "<base64-string>", "format": "mp3" }
```

**Response:**
```json
{ "status": "playing" }
```

---

### `GET /status`

Check whether audio is currently playing.

**Response:**
```json
{ "playing": true }
```

---

### `POST /stop`

Stop playback immediately.

**Response:**
```json
{ "status": "stopped" }
```

---

## Test Your Installation

A sample audio file is included at `audio/loudmouth-test.mp3`. With the service running:

```bash
curl -X POST http://localhost:8000/play \
  -H "Content-Type: application/json" \
  -d '{"file": "loudmouth-test.mp3"}'
```

You should hear: *"Loudmouth audio test. If you can hear this complete sentence, your installation is working correctly. One. Two. Three."*

---

## Supported Audio Formats

| Format | Extension | Format Hint | Notes |
|--------|-----------|-------------|-------|
| MP3 | `.mp3` | Not required | Auto-detected from extension |
| WAV | `.wav` | `"wav"` | Uncompressed; best latency |
| OGG Vorbis | `.ogg` | `"ogg"` | Open format; recommended for web |
| FLAC | `.flac` | `"flac"` | Lossless |
| OPUS | `.opus` | `"opus"` | High quality at low bitrate |
| WavPack | `.wv` | `"wv"` | Lossless compression |
| MOD | `.mod` | `"mod"` | Tracker music |
| MIDI | `.mid` | `"mid"` | Requires system soundfont |

> **Tip:** When in doubt, always pass the `format` hint — it never hurts and prevents ambiguity.

---

## Use Cases

- **Confroom** — room audio announcements and TTS playback
- **ApexFuture.AI** — website audio and AI agent voice output
- **Home automation** — trigger audio from any smart home event
- **Any Python app** — add reliable audio in two lines

---

## License

MIT — see [LICENSE](LICENSE)

This project uses [pygame-ce](https://pyga.me/), distributed under LGPL-2.1.

---

## Contributing

PRs welcome. Open an issue first for anything beyond a bug fix.
