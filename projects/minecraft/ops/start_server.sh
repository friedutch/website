#!/bin/bash
set -euo pipefail

SERVER_ROOT="${SERVER_ROOT:-/Users/administrator/Servers/minecraft}"
JAVA_BIN="${JAVA_BIN:-/opt/homebrew/opt/openjdk/bin/java}"
JAR_NAME="${JAR_NAME:-paper.jar}"
MIN_RAM="${MIN_RAM:-2G}"
MAX_RAM="${MAX_RAM:-4G}"

cd "$SERVER_ROOT"

if [ ! -x "$JAVA_BIN" ]; then
  echo "Java binary not found: $JAVA_BIN" >&2
  exit 1
fi

if [ ! -f "$JAR_NAME" ]; then
  echo "Missing server jar: $SERVER_ROOT/$JAR_NAME" >&2
  exit 1
fi

exec "$JAVA_BIN" \
  -Xms"$MIN_RAM" \
  -Xmx"$MAX_RAM" \
  -jar "$JAR_NAME" \
  --nogui
