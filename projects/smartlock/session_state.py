import datetime
import random
import sqlite3
import string
import uuid
from collections import defaultdict

from flask import redirect, session, url_for

from app.site_admin import SITE_ADMIN_ROLE

from .activity import get_client_ip, get_device_icon, get_device_search_terms
from .config import MAGIC_LINK_TTL_SECONDS, SESSION_TIMEOUT
from .db import DB_PATH, get_db


_login_attempts = defaultdict(lambda: {"attempts": 0, "locked_until": None})


def get_request_actor_id():
    actor_id = session.get("cooldown_actor_id")
    if actor_id:
        return actor_id
    actor_id = uuid.uuid4().hex
    session["cooldown_actor_id"] = actor_id
    return actor_id


def actor_cooldown_key(base_key):
    return f"{base_key}:{get_request_actor_id()}"


def get_login_sync_channel():
    return f"smartlock-login-{get_request_actor_id()}"


def cooldown_remaining(key, seconds=MAGIC_LINK_TTL_SECONDS):
    row = get_db().execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    if not row:
        return 0
    try:
        recorded_at = datetime.datetime.fromisoformat(row["value"])
    except ValueError:
        return 0
    now = datetime.datetime.utcnow()
    if recorded_at > now + datetime.timedelta(seconds=seconds):
        return 0
    elapsed = (now - recorded_at).total_seconds()
    return max(0, int(seconds - elapsed))


def create_join_invite():
    token = "".join(random.choices(string.ascii_uppercase + string.digits, k=8))
    captcha_code = str(random.randint(10, 99))
    db = get_db()
    db.execute(
        "DELETE FROM join_tokens WHERE created_at < ?",
        ((datetime.datetime.utcnow() - datetime.timedelta(minutes=5)).isoformat(),),
    )
    db.execute(
        "INSERT OR REPLACE INTO join_tokens (token, number) VALUES (?, ?)",
        (token, captcha_code),
    )
    db.commit()
    join_url = url_for("smartlock_join", token=token, _external=True)
    session["smartlock_join_url"] = join_url
    session["smartlock_join_captcha"] = captcha_code
    session["smartlock_join_created_at"] = datetime.datetime.utcnow().isoformat()
    return {"join_url": join_url, "captcha_code": captcha_code}


def get_active_join_invite():
    join_url = session.get("smartlock_join_url")
    captcha_code = session.get("smartlock_join_captcha")
    created_at = session.get("smartlock_join_created_at")
    if not join_url or not captcha_code or not created_at:
        return None
    try:
        created = datetime.datetime.fromisoformat(created_at)
    except ValueError:
        session.pop("smartlock_join_url", None)
        session.pop("smartlock_join_captcha", None)
        session.pop("smartlock_join_created_at", None)
        return None
    remaining = max(
        0,
        MAGIC_LINK_TTL_SECONDS - int((datetime.datetime.utcnow() - created).total_seconds()),
    )
    if remaining <= 0:
        session.pop("smartlock_join_url", None)
        session.pop("smartlock_join_captcha", None)
        session.pop("smartlock_join_created_at", None)
        return None
    return {"join_url": join_url, "captcha_code": captcha_code, "remaining": remaining}


def create_admin_session():
    token = str(uuid.uuid4())
    ip = get_client_ip()
    now = datetime.datetime.utcnow().isoformat()
    icon = get_device_icon()
    db = sqlite3.connect(DB_PATH)
    db.execute(
        """
        INSERT INTO active_sessions (session_token, ip, created_at, last_active, user_agent)
        VALUES (?, ?, ?, ?, ?)
        """,
        (token, ip, now, now, icon),
    )
    db.commit()
    db.close()

    preserved = {
        "smartlock_cookies_probe": session.get("smartlock_cookies_probe"),
        "cooldown_actor_id": session.get("cooldown_actor_id"),
    }
    session.clear()
    for key, value in preserved.items():
        if value:
            session[key] = value
    session["role"] = SITE_ADMIN_ROLE
    session["session_token"] = token
    session["last_active"] = now

    cutoff = (datetime.datetime.utcnow() - datetime.timedelta(hours=1)).isoformat()
    cleanup_db = sqlite3.connect(DB_PATH)
    cleanup_db.execute("DELETE FROM active_sessions WHERE created_at < ?", (cutoff,))
    cleanup_db.execute("DELETE FROM match_numbers WHERE created_at < ?", (cutoff,))
    cleanup_db.execute("DELETE FROM join_tokens WHERE created_at < ?", (cutoff,))
    cleanup_db.execute("DELETE FROM used_tokens WHERE used_at < ?", (cutoff,))
    cleanup_db.commit()
    cleanup_db.close()


def get_active_sessions():
    rows = get_db().execute("SELECT * FROM active_sessions ORDER BY created_at DESC").fetchall()
    result = []
    now = datetime.datetime.utcnow()
    for row in rows:
        created = datetime.datetime.fromisoformat(row["created_at"])
        elapsed = max(0, int((now - created).total_seconds()))
        remaining = max(0, int(SESSION_TIMEOUT - elapsed))
        minutes, seconds = divmod(remaining, 60)
        result.append(
            {
                "session_token": row["session_token"],
                "ip": row["ip"],
                "created_at": row["created_at"][:19].replace("T", " "),
                "remaining": remaining,
                "remaining_fmt": f"{minutes}:{seconds:02d}",
                "expired": remaining == 0,
                "icon": row["user_agent"] if row["user_agent"] else "🌐",
            }
        )
    return result


def build_log_entries(logs, sessions, current_token):
    unmatched_success_logs = []
    denied_logs = []
    for log in logs:
        entry = {
            "ip": log["ip"],
            "created_at": log["created_at"][:19].replace("T", " "),
            "icon": log["user_agent"] if log["user_agent"] else "🌐",
            "device_search_terms": get_device_search_terms(
                log["user_agent"] if log["user_agent"] else "🌐"
            ),
            "success": bool(log["success"]),
            "remaining": 0,
            "remaining_fmt": "",
            "current": False,
            "session_token": None,
            "state": "allowed" if log["success"] else "denied",
            "active": False,
        }
        if log["success"]:
            unmatched_success_logs.append((log, entry))
        else:
            denied_logs.append((log, entry))

    combined = []
    for session_row in sessions:
        matched_index = None
        session_created = datetime.datetime.fromisoformat(
            session_row["created_at"].replace(" ", "T")
        )
        for index, (log, entry) in enumerate(unmatched_success_logs):
            if log["ip"] != session_row["ip"]:
                continue
            if (log["user_agent"] if log["user_agent"] else "🌐") != session_row["icon"]:
                continue
            log_created = datetime.datetime.fromisoformat(log["created_at"])
            if abs((session_created - log_created).total_seconds()) <= 10:
                matched_index = index
                break
        if matched_index is not None:
            _, base_entry = unmatched_success_logs.pop(matched_index)
        else:
            base_entry = {
                "ip": session_row["ip"],
                "created_at": session_row["created_at"],
                "icon": session_row["icon"],
                "device_search_terms": get_device_search_terms(session_row["icon"]),
                "success": True,
                "state": "allowed",
            }
        base_entry.update(
            {
                "remaining": session_row["remaining"],
                "remaining_fmt": session_row["remaining_fmt"],
                "current": session_row["session_token"] == current_token,
                "session_token": session_row["session_token"],
                "active": not session_row["expired"],
                "state": "active" if not session_row["expired"] else "allowed",
                "device_search_terms": get_device_search_terms(session_row["icon"]),
            }
        )
        combined.append(base_entry)

    for _, entry in unmatched_success_logs:
        combined.append(entry)
    for _, entry in denied_logs:
        combined.append(entry)

    return sorted(combined, key=lambda entry: entry["created_at"], reverse=True)


def check_brute_force():
    ip = get_client_ip()
    record = _login_attempts[ip]
    if record["locked_until"] and datetime.datetime.utcnow() < record["locked_until"]:
        return int((record["locked_until"] - datetime.datetime.utcnow()).total_seconds())
    if record["locked_until"]:
        _login_attempts[ip] = {"attempts": 0, "locked_until": None}
    return 0


def record_failed_attempt():
    ip = get_client_ip()
    _login_attempts[ip]["attempts"] += 1
    if _login_attempts[ip]["attempts"] >= 5:
        _login_attempts[ip]["locked_until"] = datetime.datetime.utcnow() + datetime.timedelta(
            seconds=MAGIC_LINK_TTL_SECONDS
        )


def reset_attempts():
    _login_attempts[get_client_ip()] = {"attempts": 0, "locked_until": None}


def check_session():
    if session.get("role") != SITE_ADMIN_ROLE:
        return None
    token = session.get("session_token")
    if not token:
        return None

    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    row = db.execute(
        "SELECT created_at FROM active_sessions WHERE session_token = ?",
        (token,),
    ).fetchone()
    db.close()
    if not row:
        session.clear()
        return redirect(url_for("smartlock_login"))

    created_at = datetime.datetime.fromisoformat(row["created_at"])
    if (datetime.datetime.utcnow() - created_at).total_seconds() > SESSION_TIMEOUT:
        cleanup_db = sqlite3.connect(DB_PATH)
        cleanup_db.execute("DELETE FROM active_sessions WHERE session_token = ?", (token,))
        cleanup_db.commit()
        cleanup_db.close()
        session.clear()
        return redirect(url_for("smartlock_login"))
    return None
