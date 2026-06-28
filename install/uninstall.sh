#!/usr/bin/env bash
# Loudmouth — Linux uninstaller
# Usage: sudo bash install/uninstall.sh

set -e

INSTALL_DIR="/opt/loudmouth"
SERVICE_USER="loudmouth"
SERVICE_FILE="/etc/systemd/system/loudmouth.service"

if [[ $EUID -ne 0 ]]; then
  echo "ERROR: Run this script with sudo." >&2
  exit 1
fi

echo "Stopping and disabling Loudmouth service..."
systemctl stop loudmouth 2>/dev/null || true
systemctl disable loudmouth 2>/dev/null || true

echo "Removing service file..."
rm -f "$SERVICE_FILE"
systemctl daemon-reload

echo "Removing install directory..."
rm -rf "$INSTALL_DIR"

echo "Removing service user..."
userdel "$SERVICE_USER" 2>/dev/null || true

echo "Loudmouth uninstalled."
