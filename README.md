# Loudmouth

**A lightweight, always-on audio playback service.**

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
httpx.post("http://127.0.0.1:8765/play", json={"file": "announcement.mp3"})
```

---

## Features

- **Always-on** — Windows consumer installer (starts at logon), systemd service (Linux), or Windows Service; zero babysitting
- **Zero-dependency Windows install** — one download, one installer; no Python, no pip, no console window
- **HTTP API** — play, stop, check status, and health-check from any language or tool
- **Multi-format** — MP3, WAV, OGG, FLAC, OPUS, WV, MOD, MIDI (via pygame/SDL_mixer)
- **Base64 audio** — stream raw audio bytes directly without touching the filesystem
- **Path-safe** — directory traversal attacks blocked at the API layer
- **Secure by default** — binds loopback only; CORS restricted to an explicit allowlist
- **Lightweight** — FastAPI + pygame, no database, no config files

---

## Install (Windows — consumers)

1. Download the installer: **[idealoom.ai/download/loudmouth](https://idealoom.ai/download/loudmouth)** (redirects to the latest [GitHub Release](https://github.com/Dilbertian/loudmouth/releases) asset `LoudmouthSetup-<version>.exe`)
2. Run it — installs to `%ProgramFiles%\Stark\Loudmouth`, registers a logon task, and starts Loudmouth immediately
3. Verify: open `http://127.0.0.1:8765/health` — you should see JSON with `"status": "ok"`

Uninstall from **Settings → Apps** — removes the scheduled task, the install directory, and log files. No leftovers.

**Known limitation:** the logon task is per-user, so Loudmouth runs only while that Windows user is logged in. This is the correct behavior for consumer machines.

Silent install (fleet/enterprise):
```
LoudmouthSetup-<version>.exe /VERYSILENT /SUPPRESSMSGBOXES /NORESTART
```

---

## Install (developers / fleet)

### From PyPI

```bash
pip install loudmouth
loudmouth
```

### From source

```bash
pip install fastapi pygame-ce uvicorn
python server.py
```

`python server.py` applies the standard policy: bind `127.0.0.1`, port `8765` (fallback `8766`). Override via environment:

| Variable | Default | Purpose |
|----------|---------|---------|
| `LOUDMOUTH_HOST` | `127.0.0.1` | Set `0.0.0.0` for fleet/LAN use — deliberate opt-in, since `/play` drives the machine's speakers |
| `LOUDMOUTH_PORT` | `8765` → `8766` | Explicit port; skips the fallback probe entirely |
| `LOUDMOUTH_CORS_ORIGINS` | see [CORS](#cors--browser-access) | Comma-separated origin allowlist |
| `LOUDMOUTH_KEEPALIVE_HZ` | `21000` | Keep-alive tone frequency |
| `LOUDMOUTH_KEEPALIVE_DBFS` | `-20` | Keep-alive tone level |

### As a service

**Linux (systemd):**
```bash
sudo bash install/install.sh
systemctl status loudmouth     # check
journalctl -u loudmouth -f     # logs
sudo bash install/uninstall.sh # remove
```

**Windows (from source, pywin32 service):**
```bash
pip install pywin32
python install/install_service.py install
python install/install_service.py start
```

---

## Port policy

**Primary `8765`, fallback `8766`. Fixed and permanent.**

- On startup Loudmouth tries `8765`; if occupied it tries `8766`; if both are occupied it logs clearly and exits.
- `GET /health` always reports the **actual bound port**.
- Clients should probe `8765` first, then `8766`.
- Port `8000` (pre-1.0) is abandoned.

---

## API Reference

### `GET /health`

Service identity — used by IdeaLoom's `detectLoudmouth()` and by humans debugging "voice isn't working."

**Response:**
```json
{
  "status": "ok",
  "version": "1.1.0",
  "protocol": 1,
  "port": 8765,
  "uptime": 18342
}
```

- `protocol` is an **integer** API-compatibility constant. Consumers must gate on `protocol >= minimumProtocol` — never compare version strings. It bumps only on breaking API changes.
- `version` is the human-readable release version (single source: `server.__version__`).
- `uptime` is seconds since the audio mixer came up.

### `POST /play`

Play an audio file or raw audio bytes. Only one stream at a time; a new call replaces the current track.

**Play a file from the `audio/` folder:**
```json
{ "file": "loudmouth-test.mp3" }
```

**MP3 files are auto-detected** — just pass the filename. For other formats, pass the `format` hint:
```json
{ "file": "sound.ogg", "format": "ogg" }
```

**Play base64-encoded audio:**
```json
{ "audio": "<base64-string>", "format": "mp3" }
```

**Response:** `{ "status": "playing" }`
**Errors:** `400` invalid base64 / unsupported format / missing fields, `404` file not found.

### `GET /status`

**Response:** `{ "playing": true }`

### `POST /stop`

**Response:** `{ "status": "stopped" }`

---

## Detection contract (for IdeaLoom and other web clients)

The browser-side `detectLoudmouth()` flow consumes these states:

```
GET http://127.0.0.1:8765/health  (fallback :8766)
  → 200 + JSON          → AVAILABLE (check protocol >= minimum)
  → 200, old protocol   → INCOMPATIBLE_VERSION
  → connection refused  → NOT_FOUND (not installed or not running)
  → LNA prompt pending  → PERMISSION_REQUIRED (browser-side state)
  → user denied         → PERMISSION_DENIED (browser-side state)
  → wrong browser       → UNSUPPORTED_BROWSER (Safari/macOS)
```

### Supported browsers (v1)

| Browser | Windows | macOS |
|---------|---------|-------|
| Chrome | ✅ (LNA permission prompt on first use, Chrome 142+) | ❌ |
| Edge | ✅ | ❌ |
| Firefox | ✅ (no LNA prompt; failures surface as network errors) | ❌ |
| Safari | — | ❌ unsupported until a macOS package exists |

---

## CORS & browser access

Loudmouth is an **actuator** — `/play` has a physical effect on the machine — so CORS is a restricted allowlist, not `*`. Default allowed origins:

```
https://idealoom.ai
https://www.idealoom.ai
https://app.idealoom.ai
http://localhost:5173            (loom dev)
http://100.64.58.91:8910         (tailnet clean-machine test path)
```

Trusted applications (`idealoom`, `zanmyo`) can also activate their shipped origin via `POST /v1/integrations/register` (`{"app_id": "zanmyo", "protocol_version": 1}`).

Override with `LOUDMOUTH_CORS_ORIGINS` (comma-separated). Requests from non-allowlisted origins get no CORS headers.

Preflights (`OPTIONS`) are answered for all endpoints, including the `Access-Control-Allow-Private-Network: true` response header — required for public-site → loopback requests under Chrome's Private Network Access / Local Network Access model.

---

## Test Your Installation

A sample audio file ships with every install. With the service running:

```bash
curl -X POST http://127.0.0.1:8765/play \
  -H "Content-Type: application/json" \
  -d '{"file": "loudmouth-test.mp3"}'
```

You should hear: *"Loudmouth audio test. If you can hear this complete sentence, your installation is working correctly. One. Two. Three."*

Logs (packaged Windows build): `%LOCALAPPDATA%\Loudmouth\loudmouth.log`

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

## Building the Windows package

Requires Python 3.10+, PyInstaller, and Inno Setup 6:

```powershell
powershell -ExecutionPolicy Bypass -File packaging\build.ps1
```

Produces `dist\Loudmouth\` (onedir app) and `dist\LoudmouthSetup-<version>.exe` plus `dist\SHA256SUMS.txt`. See [packaging/](packaging/) for the spec, installer script, and signing wiring (Azure Trusted Signing — unsigned builds are fine for internal testing).

Releases are automated: push a tag `v<version>` matching `server.__version__` and CI builds, signs (when secrets are configured), and publishes the GitHub Release. Manual pre-release smoke test checklist: [docs/smoke-test.md](docs/smoke-test.md).

---

## Use Cases

- **Confroom** — room audio announcements and TTS playback
- **IdeaLoom / ApexFuture.AI** — website audio and AI agent voice output
- **Home automation** — trigger audio from any smart home event
- **Any Python app** — add reliable audio in two lines

---

## License

MIT — see [LICENSE](LICENSE)

This project uses [pygame-ce](https://pyga.me/), distributed under LGPL-2.1.

---

## Contributing

PRs welcome. Open an issue first for anything beyond a bug fix.
