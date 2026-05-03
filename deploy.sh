#!/bin/bash
set -e

PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
USER_UID="$(id -u)"
PLIST_PATH="/Users/administrator/Library/LaunchAgents/friedutchplus.server.plist"
LAUNCH_DOMAIN="gui/${USER_UID}"

cd "$PROJECT_ROOT"
git pull origin main
pkill -f "python3.*run.py" || true
pkill -f "python3.*server.py" || true
launchctl kickstart -k "$LAUNCH_DOMAIN/friedutchplus.server"
