#!/usr/bin/env python3
import argparse
import glob
import json
import os
import sys
import time
from datetime import datetime, UTC
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

try:
    import serial
    from serial.tools import list_ports
except ImportError as exc:
    raise SystemExit("pyserial is required. Install it with: python3 -m pip install pyserial") from exc


class SmartLockSerialBridge:
    def __init__(self, port, baudrate, api_url, api_key, timeout, event_log_path):
        self.api_url = api_url
        self.api_key = api_key
        self.event_log_path = event_log_path
        self.serial_port = serial.Serial(port, baudrate, timeout=timeout)

    def run(self):
        self.record_event("system", "bridge started", port=self.serial_port.port, baudrate=self.serial_port.baudrate)
        print(f"bridge listening on {self.serial_port.port} at {self.serial_port.baudrate} baud", flush=True)
        while True:
            raw_line = self.serial_port.readline()
            if not raw_line:
                continue
            line = raw_line.decode("utf-8", errors="ignore").strip()
            if not line:
                continue
            self.record_event("arduino_rx", line)
            print(f"arduino -> {line}", flush=True)
            response = self.handle_line(line)
            if response:
                self.serial_port.write((response + "\n").encode("utf-8"))
                self.serial_port.flush()
                self.record_event("arduino_tx", response)
                print(f"arduino <- {response}", flush=True)

    def handle_line(self, line):
        if line == "PING":
            return "PONG"
        if not line.startswith("CHECK|"):
            return None

        parts = line.split("|", 2)
        if len(parts) != 3:
            return "RESULT|ERROR|bad protocol"

        _, method, value = parts
        result = self.check_access(method.strip().lower(), value.strip())
        if result["allowed"]:
            safe_name = (result.get("user_name") or "").replace("|", "/")
            return f"RESULT|ALLOW|{safe_name}"
        reason = (result.get("reason") or "denied").replace("|", "/")
        return f"RESULT|DENY|{reason}"

    def check_access(self, method, value):
        payload = json.dumps({"method": method, "value": value}).encode("utf-8")
        request = Request(
            self.api_url,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "X-SmartLock-Hardware-Key": self.api_key,
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=10) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="ignore")
            self.record_event("bridge_error", f"http {exc.code}", body=body[:300])
            return {"allowed": False, "reason": f"http {exc.code}: {body[:120] or 'request failed'}"}
        except URLError as exc:
            self.record_event("bridge_error", "network error", detail=str(exc.reason))
            return {"allowed": False, "reason": f"network error: {exc.reason}"}
        except Exception as exc:
            self.record_event("bridge_error", "bridge error", detail=str(exc))
            return {"allowed": False, "reason": f"bridge error: {exc}"}

    def record_event(self, kind, line, **extra):
        payload = {
            "timestamp": datetime.now(UTC).isoformat(),
            "kind": kind,
            "line": line,
        }
        if extra:
            payload.update(extra)
        try:
            os.makedirs(os.path.dirname(self.event_log_path), exist_ok=True)
            with open(self.event_log_path, "a", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, ensure_ascii=True) + "\n")
        except Exception:
            pass


def detect_serial_port():
    preferred_ports = []
    fallback_ports = []

    for port in list_ports.comports():
        description = f"{port.description or ''} {port.manufacturer or ''} {port.product or ''}".lower()
        device = port.device or ""
        if "arduino" in description and "uno" in description:
            preferred_ports.append(device)
            continue
        if "arduino" in description:
            fallback_ports.append(device)
            continue
        if device.startswith("/dev/cu.usbmodem") or device.startswith("/dev/tty.usbmodem"):
            fallback_ports.append(device)

    for candidate in preferred_ports + fallback_ports:
        if candidate:
            return candidate

    for pattern in ("/dev/cu.usbmodem*", "/dev/tty.usbmodem*"):
        matches = sorted(glob.glob(pattern))
        if matches:
            return matches[0]
    return ""


def parse_args():
    parser = argparse.ArgumentParser(
        description="Bridge an Arduino Uno smart lock over USB to the Smart Lock API."
    )
    parser.add_argument(
        "--port",
        default=os.getenv("SMARTLOCK_ARDUINO_PORT", "").strip(),
        help="Serial device path. If omitted, the bridge auto-detects the connected Arduino Uno.",
    )
    parser.add_argument("--baudrate", type=int, default=115200, help="Arduino serial baud rate")
    parser.add_argument(
        "--api-url",
        default="http://127.0.0.1:5001/smartlock/api/hardware/check",
        help="Smart Lock hardware API endpoint",
    )
    parser.add_argument("--api-key", required=True, help="SMARTLOCK_HARDWARE_API_KEY value")
    parser.add_argument("--timeout", type=float, default=0.2, help="Serial read timeout in seconds")
    parser.add_argument(
        "--event-log",
        default=os.getenv("SMARTLOCK_HARDWARE_EVENT_LOG", "/tmp/friedutchplus_smartlock_hardware_events.jsonl"),
        help="NDJSON log file for Arduino bridge events",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    while True:
        port = args.port or detect_serial_port()
        if not port:
            payload = {
                "timestamp": datetime.now(UTC).isoformat(),
                "kind": "bridge_error",
                "line": "serial port unavailable",
                "detail": "No Arduino Uno serial port detected",
            }
            try:
                os.makedirs(os.path.dirname(args.event_log), exist_ok=True)
                with open(args.event_log, "a", encoding="utf-8") as handle:
                    handle.write(json.dumps(payload, ensure_ascii=True) + "\n")
            except Exception:
                pass
            print("serial error: no Arduino Uno serial port detected", file=sys.stderr, flush=True)
            time.sleep(2)
            continue

        bridge = SmartLockSerialBridge(
            port=port,
            baudrate=args.baudrate,
            api_url=args.api_url,
            api_key=args.api_key,
            timeout=args.timeout,
            event_log_path=args.event_log,
        )
        try:
            bridge.run()
        except serial.SerialException as exc:
            bridge.record_event("bridge_error", "serial error", detail=str(exc))
            print(f"serial error: {exc}", file=sys.stderr, flush=True)
            time.sleep(2)
        except KeyboardInterrupt:
            bridge.record_event("system", "bridge stopped")
            print("bridge stopped", flush=True)
            return 0


if __name__ == "__main__":
    raise SystemExit(main())
