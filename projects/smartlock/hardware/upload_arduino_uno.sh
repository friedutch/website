#!/bin/bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
SKETCH_DIR="$PROJECT_ROOT/projects/smartlock/hardware/arduino_uno_smartlock"
ARDUINO_CLI="/Applications/Arduino IDE.app/Contents/Resources/app/lib/backend/resources/arduino-cli"
BUILD_DIR="/tmp/friedutchplus-arduino-uno-build"
FQBN="${ARDUINO_FQBN:-arduino:avr:uno}"
PORT="${ARDUINO_PORT:-}"

if [[ ! -x "$ARDUINO_CLI" ]]; then
  echo "Arduino CLI not found at: $ARDUINO_CLI" >&2
  echo "Install Arduino IDE or update ARDUINO_CLI in this script." >&2
  exit 1
fi

if [[ -z "$PORT" ]]; then
  while IFS= read -r candidate; do
    [[ -n "$candidate" ]] || continue
    PORT="$candidate"
    break
  done < <("$ARDUINO_CLI" board list | awk '/Arduino UNO/ { print $1; exit }')
fi

if [[ -z "$PORT" ]]; then
  echo "No Arduino UNO port detected." >&2
  echo "Set ARDUINO_PORT=/dev/cu.usbmodemXXXX and retry." >&2
  exit 1
fi

mkdir -p "$BUILD_DIR"

echo "Compiling $SKETCH_DIR for $FQBN..."
"$ARDUINO_CLI" compile --fqbn "$FQBN" --build-path "$BUILD_DIR" "$SKETCH_DIR"

echo "Uploading to $PORT..."
set +e
UPLOAD_OUTPUT="$("$ARDUINO_CLI" upload -p "$PORT" --fqbn "$FQBN" --verbose --input-dir "$BUILD_DIR" 2>&1)"
UPLOAD_STATUS=$?
set -e

echo "$UPLOAD_OUTPUT"

if [[ $UPLOAD_STATUS -ne 0 ]]; then
  cat >&2 <<EOF

Upload failed.

The sketch compiled successfully, so this is likely a bootloader/reset/serial issue rather than a sketch syntax issue.
This Smart Lock sketch does not use D0/D1 in code, so if upload works only after
unplugging the lock hardware, an attached relay/keypad/RFID/fingerprint/power path
is probably loading the board during reset.

Check these before retrying:
1. Stop anything holding the serial port, including the Smart Lock serial bridge and Serial Monitor.
2. Disconnect any wiring from pins D0/RX and D1/TX while uploading.
3. If upload still fails, unplug the Smart Lock peripherals from D2-D9 and A0-A3, upload, then reconnect one subsystem at a time.
4. Retry once while pressing reset just before the "Uploading to $PORT..." step.
5. If this is not actually an Uno bootloader target, override the board with ARDUINO_FQBN.

Examples:
  ARDUINO_PORT=/dev/cu.usbmodem1201 $0
  ARDUINO_FQBN=arduino:avr:nano:cpu=atmega328old ARDUINO_PORT=/dev/cu.usbmodem1201 $0
EOF
  exit $UPLOAD_STATUS
fi

echo "Upload completed."
