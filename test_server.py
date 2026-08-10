"""
Pytest test suite for server.py.

pygame is mocked throughout so tests run without audio hardware.
The ``client`` fixture patches both ``server.pygame`` and ``server.AUDIO_DIR``
before the FastAPI lifespan starts, so no real mixer calls are made.

Run with:
    pytest test_server.py -v
"""

import base64
import socket

import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

import server
from server import app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def mock_pygame():
    """Replace the pygame module used by server.py with a MagicMock.

    This prevents any real audio driver calls during tests and lets us
    assert that the correct pygame functions were called.
    """
    with patch("server.pygame") as mock_pg:
        mock_pg.mixer.music.get_busy.return_value = False
        # _start_keepalive() unpacks (freq, size, channels) at lifespan startup
        mock_pg.mixer.get_init.return_value = (44100, -16, 2)
        yield mock_pg


@pytest.fixture()
def client(mock_pygame, tmp_path):
    """FastAPI TestClient with pygame mocked and AUDIO_DIR set to a temp directory.

    ``tmp_path`` is a built-in pytest fixture that provides a fresh, empty
    temporary directory for each test. We point AUDIO_DIR at it so file-based
    tests can create files there without touching the real audio/ folder.
    """
    with patch("server.AUDIO_DIR", str(tmp_path)):
        with TestClient(app) as c:
            yield c


# ---------------------------------------------------------------------------
# POST /play  —  file path
# ---------------------------------------------------------------------------

class TestPlayFile:
    def test_success(self, client, mock_pygame, tmp_path):
        (tmp_path / "song.mp3").write_bytes(b"fake mp3 data")

        resp = client.post("/play", json={"file": "song.mp3"})

        assert resp.status_code == 200
        assert resp.json() == {"status": "playing"}
        mock_pygame.mixer.music.load.assert_called_once()
        mock_pygame.mixer.music.play.assert_called_once()

    def test_file_not_found_returns_404(self, client):
        resp = client.post("/play", json={"file": "missing.mp3"})

        assert resp.status_code == 404
        assert "File not found" in resp.json()["detail"]

    def test_path_traversal_is_blocked(self, client):
        """A caller supplying '../../etc/passwd' must not escape AUDIO_DIR."""
        resp = client.post("/play", json={"file": "../../etc/passwd"})

        # os.path.basename reduces it to 'passwd', which won't exist in tmp_path
        assert resp.status_code == 404

    def test_unsupported_format_returns_400(self, client, mock_pygame, tmp_path):
        (tmp_path / "track.xyz").write_bytes(b"garbage")
        mock_pygame.mixer.music.load.side_effect = Exception("Not a supported format")

        resp = client.post("/play", json={"file": "track.xyz"})

        assert resp.status_code == 400
        assert "Unsupported audio format" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# POST /play  —  base64 audio blob
# ---------------------------------------------------------------------------

class TestPlayAudio:
    def test_success(self, client, mock_pygame):
        payload = base64.b64encode(b"fake audio bytes").decode()

        resp = client.post("/play", json={"audio": payload})

        assert resp.status_code == 200
        assert resp.json() == {"status": "playing"}
        mock_pygame.mixer.music.load.assert_called_once()
        mock_pygame.mixer.music.play.assert_called_once()

    def test_format_hint_is_passed_as_namehint(self, client, mock_pygame):
        """The ``format`` field must reach pygame as the namehint argument."""
        payload = base64.b64encode(b"fake ogg bytes").decode()

        client.post("/play", json={"audio": payload, "format": "ogg"})

        # load() is called as load(BytesIO, namehint) — check the second arg
        call_args = mock_pygame.mixer.music.load.call_args
        assert call_args.args[1] == "ogg"

    def test_no_format_hint_passes_empty_string(self, client, mock_pygame):
        """Omitting ``format`` must pass '' so pygame attempts auto-detection."""
        payload = base64.b64encode(b"fake bytes").decode()

        client.post("/play", json={"audio": payload})

        call_args = mock_pygame.mixer.music.load.call_args
        assert call_args.args[1] == ""

    def test_invalid_base64_returns_400(self, client):
        resp = client.post("/play", json={"audio": "not valid base64!!!"})

        assert resp.status_code == 400
        assert "Invalid base64" in resp.json()["detail"]

    def test_unsupported_format_returns_400(self, client, mock_pygame):
        payload = base64.b64encode(b"garbage").decode()
        mock_pygame.mixer.music.load.side_effect = Exception("Unknown format")

        resp = client.post("/play", json={"audio": payload})

        assert resp.status_code == 400
        assert "Unsupported audio format" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# POST /play  —  missing body fields
# ---------------------------------------------------------------------------

class TestPlayValidation:
    def test_empty_body_returns_400(self, client):
        resp = client.post("/play", json={})

        assert resp.status_code == 400
        assert "Provide either" in resp.json()["detail"]

    def test_null_fields_returns_400(self, client):
        resp = client.post("/play", json={"file": None, "audio": None})

        assert resp.status_code == 400
        assert "Provide either" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# GET /status
# ---------------------------------------------------------------------------

class TestStatus:
    def test_not_playing(self, client, mock_pygame):
        mock_pygame.mixer.music.get_busy.return_value = False

        resp = client.get("/status")

        assert resp.status_code == 200
        assert resp.json() == {"playing": False}

    def test_is_playing(self, client, mock_pygame):
        mock_pygame.mixer.music.get_busy.return_value = True

        resp = client.get("/status")

        assert resp.status_code == 200
        assert resp.json() == {"playing": True}


# ---------------------------------------------------------------------------
# POST /stop
# ---------------------------------------------------------------------------

class TestStop:
    def test_stop_returns_stopped(self, client, mock_pygame):
        resp = client.post("/stop")

        assert resp.status_code == 200
        assert resp.json() == {"status": "stopped"}

    def test_stop_calls_pygame_stop(self, client, mock_pygame):
        client.post("/stop")

        mock_pygame.mixer.music.stop.assert_called_once()


# ---------------------------------------------------------------------------
# GET /health
# ---------------------------------------------------------------------------

class TestHealth:
    def test_shape(self, client):
        """The exact contract IdeaLoom's detectLoudmouth() gates on."""
        with patch("server._bound_port", 8765):
            resp = client.get("/health")

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert body["version"] == server.__version__
        assert isinstance(body["protocol"], int)
        assert body["protocol"] == server.PROTOCOL
        assert body["port"] == 8765
        assert isinstance(body["uptime"], int)
        assert body["uptime"] >= 0

    def test_port_falls_back_to_request_scope(self, client):
        """Launched via bare uvicorn (no main()), /health still reports a port."""
        resp = client.get("/health")

        # TestClient's ASGI scope advertises ("testserver", 80)
        assert resp.json()["port"] == 80


# ---------------------------------------------------------------------------
# CORS — restricted allowlist + Private Network Access preflight
# ---------------------------------------------------------------------------

ALLOWED_ORIGIN = "http://localhost:5173"
EVIL_ORIGIN = "https://evil.example.com"


class TestCors:
    @pytest.mark.parametrize("path,method", [("/play", "POST"), ("/health", "GET")])
    def test_preflight_allowed_origin(self, client, path, method):
        resp = client.options(path, headers={
            "Origin": ALLOWED_ORIGIN,
            "Access-Control-Request-Method": method,
        })

        assert resp.status_code == 200
        assert resp.headers["access-control-allow-origin"] == ALLOWED_ORIGIN
        assert resp.headers["access-control-allow-private-network"] == "true"

    def test_preflight_disallowed_origin_gets_no_cors_headers(self, client):
        resp = client.options("/play", headers={
            "Origin": EVIL_ORIGIN,
            "Access-Control-Request-Method": "POST",
        })

        assert "access-control-allow-origin" not in resp.headers
        assert "access-control-allow-private-network" not in resp.headers

    def test_simple_request_disallowed_origin_gets_no_cors_headers(self, client):
        resp = client.get("/status", headers={"Origin": EVIL_ORIGIN})

        # The request itself succeeds (server-to-server callers have no
        # origin), but the browser gets no CORS grant to read it.
        assert resp.status_code == 200
        assert "access-control-allow-origin" not in resp.headers

    def test_simple_request_allowed_origin_gets_cors_headers(self, client):
        resp = client.get("/status", headers={"Origin": ALLOWED_ORIGIN})

        assert resp.headers["access-control-allow-origin"] == ALLOWED_ORIGIN

    def test_pna_header_absent_on_non_preflight(self, client):
        resp = client.get("/status", headers={"Origin": ALLOWED_ORIGIN})

        assert "access-control-allow-private-network" not in resp.headers

    def test_allowlist_env_override(self, monkeypatch):
        monkeypatch.setenv("LOUDMOUTH_CORS_ORIGINS", " https://a.example , https://b.example ")

        assert server.allowed_origins() == ["https://a.example", "https://b.example"]

    def test_allowlist_default(self, monkeypatch):
        monkeypatch.delenv("LOUDMOUTH_CORS_ORIGINS", raising=False)

        origins = server.allowed_origins()

        assert "https://idealoom.ai" in origins
        assert "*" not in origins

    def test_production_app_origin_allowed(self, client):
        """F13 regression: https://app.idealoom.ai is where the production
        SPA actually runs — a healthy server was CORS-blocking it."""
        resp = client.options("/play", headers={
            "Origin": "https://app.idealoom.ai",
            "Access-Control-Request-Method": "POST",
        })

        assert resp.status_code == 200
        assert resp.headers["access-control-allow-origin"] == "https://app.idealoom.ai"
        assert resp.headers["access-control-allow-private-network"] == "true"


# ---------------------------------------------------------------------------
# Bind address + port policy (8765 → 8766 → clean exit)
# ---------------------------------------------------------------------------

def _free_port() -> int:
    """Grab a port the OS considers free right now."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _occupied_socket() -> socket.socket:
    """Return a listening socket holding a port; caller must close it."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    s.listen(1)
    return s


class TestBindPolicy:
    def test_default_host_is_loopback(self, monkeypatch):
        monkeypatch.delenv("LOUDMOUTH_HOST", raising=False)

        assert server.resolve_host() == "127.0.0.1"

    def test_host_env_override(self, monkeypatch):
        monkeypatch.setenv("LOUDMOUTH_HOST", "0.0.0.0")

        assert server.resolve_host() == "0.0.0.0"

    def test_default_port_candidates(self):
        assert server.DEFAULT_PORTS == (8765, 8766)

    def test_first_port_free(self, monkeypatch):
        monkeypatch.delenv("LOUDMOUTH_PORT", raising=False)
        p1, p2 = _free_port(), _free_port()

        assert server.pick_port("127.0.0.1", (p1, p2)) == p1

    def test_falls_back_when_primary_occupied(self, monkeypatch):
        monkeypatch.delenv("LOUDMOUTH_PORT", raising=False)
        held = _occupied_socket()
        p2 = _free_port()
        try:
            assert server.pick_port("127.0.0.1", (held.getsockname()[1], p2)) == p2
        finally:
            held.close()

    def test_exits_when_all_occupied(self, monkeypatch, capsys):
        monkeypatch.delenv("LOUDMOUTH_PORT", raising=False)
        held1, held2 = _occupied_socket(), _occupied_socket()
        try:
            with pytest.raises(SystemExit) as exc:
                server.pick_port("127.0.0.1", (held1.getsockname()[1], held2.getsockname()[1]))
        finally:
            held1.close()
            held2.close()

        assert exc.value.code == 1
        assert "in use" in capsys.readouterr().err

    def test_port_env_override_skips_probing(self, monkeypatch):
        monkeypatch.setenv("LOUDMOUTH_PORT", "9999")

        assert server.pick_port("127.0.0.1") == 9999
