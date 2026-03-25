import sqlite3

from flask import request

from .db import DB_PATH


def get_device_icon():
    user_agent = request.headers.get("User-Agent", "").lower()
    if "iphone" in user_agent or ("android" in user_agent and "mobile" in user_agent):
        return "📱"
    if "ipad" in user_agent or "tablet" in user_agent:
        return "📱"
    if "mac" in user_agent and "mobile" not in user_agent:
        return "🖥️"
    if "windows" in user_agent:
        return "💻"
    if "linux" in user_agent:
        return "🖥️"
    if "curl" in user_agent or "bot" in user_agent:
        return "🤖"
    return "🌐"


def get_device_search_terms(icon):
    aliases = {
        "📱": "phone mobile smartphone tablet",
        "💻": "computer laptop pc",
        "🖥️": "computer desktop pc workstation",
        "🤖": "bot curl automation script cli",
        "🌐": "browser web internet",
    }
    return aliases.get(icon, "browser web device")


def get_client_ip():
    return request.headers.get("CF-Connecting-IP") or request.remote_addr


def log_attempt(method, method_id=None, success=False, user_name=None):
    db = sqlite3.connect(DB_PATH)
    db.execute(
        """
        INSERT INTO login_logs (method, method_id, success, user_name, ip, user_agent)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            method,
            method_id,
            1 if success else 0,
            user_name,
            get_client_ip(),
            get_device_icon(),
        ),
    )
    db.commit()
    db.close()
