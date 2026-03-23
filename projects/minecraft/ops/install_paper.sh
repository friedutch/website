#!/bin/bash
set -euo pipefail

SERVER_ROOT="${SERVER_ROOT:-/Users/administrator/Servers/minecraft}"
PAPER_PROJECT="${PAPER_PROJECT:-paper}"
MINECRAFT_VERSION="${MINECRAFT_VERSION:-1.21.11}"
USER_AGENT="${USER_AGENT:-friedutchplus-minecraft-setup/1.0 ([email protected])}"

mkdir -p "$SERVER_ROOT"
cd "$SERVER_ROOT"

BUILDS_JSON="$(curl -fsSL -H "User-Agent: $USER_AGENT" \
  "https://fill.papermc.io/v3/projects/${PAPER_PROJECT}/versions/${MINECRAFT_VERSION}/builds")"

PAPER_URL="$(
  BUILDS_JSON="$BUILDS_JSON" python3 - <<'PY'
import json
import os

builds = json.loads(os.environ["BUILDS_JSON"])
stable_url = None
for build in builds:
    if build.get("channel") == "STABLE":
        stable_url = build.get("downloads", {}).get("server:default", {}).get("url")
        if stable_url:
            break

if not stable_url:
    raise SystemExit("No stable Paper build found for requested version")

print(stable_url)
PY
)"

curl -fsSL -H "User-Agent: $USER_AGENT" -o paper.jar "$PAPER_URL"

cp /Users/administrator/Sites/friedutchplus/projects/minecraft/ops/server.properties.example \
  "$SERVER_ROOT/server.properties"

cat > "$SERVER_ROOT/eula.txt" <<'EOF'
eula=true
EOF

echo "Installed Paper into $SERVER_ROOT"
