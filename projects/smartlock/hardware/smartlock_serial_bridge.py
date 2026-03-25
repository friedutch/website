#!/usr/bin/env python3
import argparse
import json
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

try:
    import serial
except ImportError as exc:
    raise SystemExit("pyserial is required. Install it with: python3 -m pip install pyserial") from exc


class SmartLockSerialBridge:
    def __init__(self, port, baudrate, api_url, api_key, timeout):
        self.api_url = api_url
        self.api_key = api_key
        self.serial_port = serial.Serial(port, baudrate, timeout=timeout)

    def run(self):
        print(f"bridge listening on {self.serial_port.port} at {self.serial_port.baudrate} baud", flush=True)
        while True:
            raw_line = self.serial_port.readline()
            if not raw_line:
                continue
            line = raw_line.decode("utf-8", errors="ignore").strip()
            if not line:
                continue
            print(f"arduino -> {line}", flush=True)
            response = self.handle_line(line)
            if response:
                self.serial_port.write((response + "\n").encode("utf-8"))
                self.serial_port.flush()
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
            return {"allowed": False, "reason": f"http {exc.code}: {body[:120] or 'request failed'}"}
        except URLError as exc:
            return {"allowed": False, "reason": f"network error: {exc.reason}"}
        except Exception as exc:
            return {"allowed": False, "reason": f"bridge error: {exc}"}


def parse_args():
    parser = argparse.ArgumentParser(
        description="Bridge an Arduino Uno smart lock over USB to the Friedutch Plus Smart Lock API."
    )
    parser.add_argument("--port", required=True, help="Serial device path, for example /dev/cu.usbmodem1101")
    parser.add_argument("--baudrate", type=int, default=115200, help="Arduino serial baud rate")
    parser.add_argument(
        "--api-url",
        default="http://127.0.0.1:5001/smartlock/api/hardware/check",
        help="Smart Lock hardware API endpoint",
    )
    parser.add_argument("--api-key", required=True, help="SMARTLOCK_HARDWARE_API_KEY value")
    parser.add_argument("--timeout", type=float, default=0.2, help="Serial read timeout in seconds")
    return parser.parse_args()


def main():
    args = parse_args()
    bridge = SmartLockSerialBridge(
        port=args.port,
        baudrate=args.baudrate,
        api_url=args.api_url,
        api_key=args.api_key,
        timeout=args.timeout,
    )
    while True:
        try:
            bridge.run()
        except serial.SerialException as exc:
            print(f"serial error: {exc}", file=sys.stderr, flush=True)
            time.sleep(2)
        except KeyboardInterrupt:
            print("bridge stopped", flush=True)
            return 0


if __name__ == "__main__":
    raise SystemExit(main())
