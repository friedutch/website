#!/bin/bash
set -euo pipefail

USER_UID="$(id -u)"
LAUNCH_DOMAIN="gui/${USER_UID}"
MC_LABEL="friedutchplus.minecraft.server"
MC_PLIST_TARGET="/Users/administrator/Library/LaunchAgents/${MC_LABEL}.plist"
WEB_LABEL="friedutchplus.server"
WEB_TARGET="${LAUNCH_DOMAIN}/${WEB_LABEL}"
MC_TARGET="${LAUNCH_DOMAIN}/${MC_LABEL}"
SERVER_ROOT="${SERVER_ROOT:-/Users/administrator/Servers/minecraft}"

/bin/bash /Users/administrator/Sites/friedutchplus/projects/minecraft/ops/install_paper.sh

cp /Users/administrator/Sites/friedutchplus/projects/minecraft/ops/friedutchplus.minecraft.server.plist.example "$MC_PLIST_TARGET"

if launchctl print "$MC_TARGET" >/dev/null 2>&1; then
  launchctl bootout "$MC_TARGET"
fi
launchctl bootstrap "$LAUNCH_DOMAIN" "$MC_PLIST_TARGET"

if launchctl print "$WEB_TARGET" >/dev/null 2>&1; then
  launchctl kickstart -k "$WEB_TARGET"
fi

echo "Minecraft provisioned at $SERVER_ROOT"
