"""
Pytest test suite for server.py.

pygame is mocked throughout so tests run without audio hardware.
The ``client`` fixture patches both ``server.pygame`` and ``server.AUDIO_DIR``
before the FastAPI lifespan starts, so no real mixer calls are made.

Run with:
    pytest test_server.py -v
"""

import base64
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

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
