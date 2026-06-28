#!/usr/bin/env bash
# Loudmouth — Linux systemd installer
# Usage: sudo bash install/install.sh
# Requires: Python 3.10+, pip, git

set -e

INSTALL_DIR="/opt/loudmouth"
SERVICE_USER="loudmouth"
SERVICE_FILE="/etc/systemd/system/loudmouth.service"

echo "======================================"
echo "  Loudmouth — Installation"
echo "  Stark Technologies"
echo "======================================"
echo ""

# Must run as root
if [[ $EUID -ne 0 ]]; then
  echo "ERROR: Run this script with sudo." >&2
  exit 1
fi

# Check Python
if ! command -v python3 &>/dev/null; then
  echo "ERROR: Python 3 is required but not installed." >&2
  exit 1
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo "Python $PYTHON_VERSION detected."

# Create service user if it doesn't exist
if ! id "$SERVICE_USER" &>/dev/null; then
  echo "Creating service user '$SERVICE_USER'..."
  useradd --system --no-create-home --shell /usr/sbin/nologin "$SERVICE_USER"
fi

# Create install directory
echo "Installing to $INSTALL_DIR..."
mkdir -p "$INSTALL_DIR/audio"
cp -r . "$INSTALL_DIR/"
chown -R "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR"

# Create virtual environment
echo "Creating virtual environment..."
python3 -m venv "$INSTALL_DIR/venv"
"$INSTALL_DIR/venv/bin/pip" install --upgrade pip -q
"$INSTALL_DIR/venv/bin/pip" install -r "$INSTALL_DIR/requirements.txt" -q

# Install systemd service
echo "Installing systemd service..."
cp "$INSTALL_DIR/install/loudmouth.service" "$SERVICE_FILE"
systemctl daemon-reload
systemctl enable loudmouth
systemctl start loudmouth

echo ""
echo "======================================"
echo "  Loudmouth installed and running!"
echo "======================================"
echo ""
echo "  Service status : systemctl status loudmouth"
echo "  Logs           : journalctl -u loudmouth -f"
echo "  Test           : curl -X POST http://localhost:8000/play \\"
echo "                     -H 'Content-Type: application/json' \\"
echo "                     -d '{\"file\": \"loudmouth-test.mp3\"}'"
echo ""
echo "  Install type   : Optional (--service flag)"
echo "  To uninstall   : sudo bash install/uninstall.sh"
echo ""
