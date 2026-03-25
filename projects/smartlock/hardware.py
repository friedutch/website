import hmac
import json
from collections import deque

from flask import request

from .config import (
    HARDWARE_UNLOCK_SECONDS,
    get_hardware_api_key,
    get_hardware_event_log_path,
)
from .db import get_db


def mask_hardware_method_id(method, credential):
    if not credential:
        return None
    if method == "passcode":
        if len(credential) <= 2:
            return "*" * len(credential)
        return f"{'*' * (len(credential) - 2)}{credential[-2:]}"
    if len(credential) <= 8:
        return credential
    return f"{credential[:4]}...{credential[-4:]}"


def normalize_hardware_credential(method, raw_value):
    value = (raw_value or "").strip()
    if method == "passcode":
        return "".join(ch for ch in value if ch.isdigit())[:12]
    if method == "rfid":
        return "".join(ch for ch in value.upper() if ch.isalnum())[:64]
    if method == "fingerprint":
        return "".join(ch for ch in value if ch.isdigit())[:32]
    return ""


def find_hardware_user(method, credential):
    db = get_db()
    if method == "passcode":
        return db.execute("SELECT * FROM users WHERE passcode = ?", (credential,)).fetchone()
    if method == "rfid":
        return db.execute(
            """
            SELECT * FROM users
            WHERE rfid_enabled = 1 AND UPPER(COALESCE(rfid_id, '')) = ?
            """,
            (credential,),
        ).fetchone()
    if method == "fingerprint":
        return db.execute(
            """
            SELECT * FROM users
            WHERE fingerprint_enabled = 1 AND COALESCE(fingerprint_id, '') = ?
            """,
            (credential,),
        ).fetchone()
    return None


def evaluate_hardware_access(method, raw_value):
    credential = normalize_hardware_credential(method, raw_value)
    if not credential:
        return {
            "allowed": False,
            "credential": "",
            "user": None,
            "reason": "missing credential",
        }
    user = find_hardware_user(method, credential)
    return {
        "allowed": bool(user),
        "credential": credential,
        "user": user,
        "reason": None if user else "not allowed",
    }


def hardware_request_is_authorized():
    configured_key = get_hardware_api_key()
    provided_key = request.headers.get("X-SmartLock-Hardware-Key", "").strip()
    if not configured_key or not provided_key:
        return False
    return hmac.compare_digest(configured_key, provided_key)


def read_hardware_events(limit=200):
    path = get_hardware_event_log_path()
    entries = deque(maxlen=max(1, min(limit, 500)))
    try:
        with open(path, "r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except FileNotFoundError:
        return []
    return list(entries)
