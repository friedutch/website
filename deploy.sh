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
sleep 1
launchctl bootout "$LAUNCH_DOMAIN" "$PLIST_PATH" 2>/dev/null || true
sleep 1
launchctl bootstrap "$LAUNCH_DOMAIN" "$PLIST_PATH"
