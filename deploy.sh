#!/bin/bash
set -e

PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
USER_UID="$(id -u)"
PLIST_PATH="/Users/administrator/Library/LaunchAgents/friedutchplus.server.plist"
LAUNCH_DOMAIN="gui/${USER_UID}"
SERVICE_NAME="friedutchplus.server"
SERVICE_TARGET="${LAUNCH_DOMAIN}/${SERVICE_NAME}"

cd "$PROJECT_ROOT"
git pull origin main

if launchctl print "$SERVICE_TARGET" >/dev/null 2>&1; then
  launchctl kickstart -k "$SERVICE_TARGET"
else
  launchctl bootstrap "$LAUNCH_DOMAIN" "$PLIST_PATH"
fi
