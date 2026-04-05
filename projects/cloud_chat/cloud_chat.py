import datetime
import os
import sqlite3

from flask import abort, make_response, redirect, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from app.rendering import render_page
from app.site_admin import is_site_admin, require_site_admin


CLOUD_CHAT_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cloud_chat.db")
USERNAME_MAX_LENGTH = 32
PASSWORD_MIN_LENGTH = 12
MAX_LOGIN_ATTEMPTS = 5
LOGIN_LOCKOUT_SECONDS = 900


def _get_db():
    db = sqlite3.connect(CLOUD_CHAT_DB_PATH)
    db.row_factory = sqlite3.Row
    return db


def init_cloud_chat_db():
    db = sqlite3.connect(CLOUD_CHAT_DB_PATH)
    db.execute(
        """CREATE TABLE IF NOT EXISTS cloud_chat_users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        is_active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )"""
    )
    existing_columns = {row[1] for row in db.execute("PRAGMA table_info(cloud_chat_users)").fetchall()}
    if "is_active" not in existing_columns:
        db.execute("ALTER TABLE cloud_chat_users ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1")
    db.execute(
        """CREATE TABLE IF NOT EXISTS cloud_chat_login_attempts (
        subject_key TEXT PRIMARY KEY,
        attempts INTEGER NOT NULL DEFAULT 0,
        locked_until TEXT,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    )"""
    )
    db.commit()
    db.close()


def _normalize_username(raw_value):
    value = (raw_value or "").strip().lower()
    return "".join(ch for ch in value if ch.isalnum() or ch in "._-")[:USERNAME_MAX_LENGTH]


def _pop_notice(key):
    value = session.get(key)
    if key in session:
        session.pop(key)
    return value


def _clear_cloud_chat_session():
    session.pop("cloudchat_user_id", None)
    session.pop("cloudchat_username", None)


def _get_client_ip():
    return request.headers.get("CF-Connecting-IP") or request.remote_addr or "unknown"


def _login_subject_key(username):
    return f"{_normalize_username(username) or '_'}|{_get_client_ip()}"


def _format_lockout_message(remaining):
    minutes, seconds = divmod(max(0, remaining), 60)
    return f"Too many failed login attempts. Try again in {minutes}:{seconds:02d}."


def _login_lockout_remaining(username):
    subject_key = _login_subject_key(username)
    db = _get_db()
    try:
        row = db.execute(
            """
            SELECT locked_until
            FROM cloud_chat_login_attempts
            WHERE subject_key = ?
            """,
            (subject_key,),
        ).fetchone()
        if not row or not row["locked_until"]:
            return 0

        try:
            locked_until = datetime.datetime.fromisoformat(row["locked_until"])
        except ValueError:
            db.execute("DELETE FROM cloud_chat_login_attempts WHERE subject_key = ?", (subject_key,))
            db.commit()
            return 0

        remaining = int((locked_until - datetime.datetime.utcnow()).total_seconds())
        if remaining > 0:
            return remaining

        db.execute("DELETE FROM cloud_chat_login_attempts WHERE subject_key = ?", (subject_key,))
        db.commit()
        return 0
    finally:
        db.close()


def _record_failed_login(username):
    subject_key = _login_subject_key(username)
    now = datetime.datetime.utcnow()
    db = _get_db()
    try:
        row = db.execute(
            """
            SELECT attempts
            FROM cloud_chat_login_attempts
            WHERE subject_key = ?
            """,
            (subject_key,),
        ).fetchone()
        attempts = (row["attempts"] if row else 0) + 1
        locked_until = None
        if attempts >= MAX_LOGIN_ATTEMPTS:
            locked_until = (now + datetime.timedelta(seconds=LOGIN_LOCKOUT_SECONDS)).isoformat()

        db.execute(
            """
            INSERT INTO cloud_chat_login_attempts (subject_key, attempts, locked_until, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(subject_key) DO UPDATE SET
                attempts = excluded.attempts,
                locked_until = excluded.locked_until,
                updated_at = excluded.updated_at
            """,
            (subject_key, attempts, locked_until, now.isoformat()),
        )
        db.commit()
    finally:
        db.close()


def _reset_failed_login(username):
    db = _get_db()
    try:
        db.execute("DELETE FROM cloud_chat_login_attempts WHERE subject_key = ?", (_login_subject_key(username),))
        db.commit()
    finally:
        db.close()


def _get_current_user():
    user_id = session.get("cloudchat_user_id")
    if not user_id:
        return None

    db = _get_db()
    try:
        row = db.execute(
            """
            SELECT id, username, is_active, created_at
            FROM cloud_chat_users
            WHERE id = ?
            """,
            (user_id,),
        ).fetchone()
    finally:
        db.close()

    if not row or not row["is_active"]:
        _clear_cloud_chat_session()
        return None
    return row


def _render_cloud_chat_login(error=None):
    return render_page(
        "cloud_chat_login.html",
        page_name="Cloud Chat — Login",
        error=error or _pop_notice("cloudchat_login_error"),
        admin_logged_in=is_site_admin(),
        noindex=True,
    )


def _render_cloud_chat_app(user):
    return render_page(
        "cloud_chat_app.html",
        page_name="Cloud Chat — Friedutch Plus",
        current_user=user,
        app_message=_pop_notice("cloudchat_app_message"),
        can_manage=is_site_admin(),
        noindex=True,
    )


def _list_cloud_chat_users():
    db = _get_db()
    try:
        rows = db.execute(
            """
            SELECT id, username, is_active, created_at
            FROM cloud_chat_users
            ORDER BY created_at DESC, id DESC
            """
        ).fetchall()
    finally:
        db.close()

    current_user_id = session.get("cloudchat_user_id")
    return [
        {
            "id": row["id"],
            "username": row["username"],
            "is_active": bool(row["is_active"]),
            "created_at": row["created_at"][:19].replace("T", " "),
            "is_current_user": current_user_id == row["id"],
        }
        for row in rows
    ]


def _render_cloud_chat_admin(error=None, username_value="", admin_message=None, password_preview=None):
    response = make_response(
        render_page(
        "cloud_chat_admin.html",
        page_name="Cloud Chat — Admin",
        users=_list_cloud_chat_users(),
        admin_message=admin_message if admin_message is not None else _pop_notice("cloudchat_admin_message"),
        password_preview=password_preview,
        error=error,
        username_value=username_value,
        password_min_length=PASSWORD_MIN_LENGTH,
        noindex=True,
        )
    )
    if password_preview:
        response.headers["Cache-Control"] = "no-store, max-age=0"
        response.headers["Pragma"] = "no-cache"
    return response


def _require_cloud_chat_admin_user(user_id):
    db = _get_db()
    try:
        row = db.execute(
            """
            SELECT id, username, is_active, created_at
            FROM cloud_chat_users
            WHERE id = ?
            """,
            (user_id,),
        ).fetchone()
    finally:
        db.close()

    if not row:
        abort(404)
    return row


def init_cloud_chat(app):
    @app.route("/cloudchat/")
    def cloud_chat_index():
        user = _get_current_user()
        if user:
            return _render_cloud_chat_app(user)
        return _render_cloud_chat_login()

    @app.route("/cloudchat/login", methods=["POST"])
    def cloud_chat_login():
        username = _normalize_username(request.form.get("username", ""))
        password = request.form.get("password", "")
        if not username or not password:
            return _render_cloud_chat_login(error="Enter both a username and password.")
        lockout_remaining = _login_lockout_remaining(username)
        if lockout_remaining > 0:
            return _render_cloud_chat_login(error=_format_lockout_message(lockout_remaining))

        db = _get_db()
        try:
            row = db.execute(
                """
                SELECT id, username, password_hash, is_active, created_at
                FROM cloud_chat_users
                WHERE username = ?
                """,
                (username,),
            ).fetchone()
        finally:
            db.close()

        if not row or not row["is_active"] or not check_password_hash(row["password_hash"], password):
            _record_failed_login(username)
            return _render_cloud_chat_login(error="Invalid Cloud Chat credentials.")

        _reset_failed_login(username)
        session["cloudchat_user_id"] = row["id"]
        session["cloudchat_username"] = row["username"]
        session["cloudchat_app_message"] = f"Welcome back, {row['username']}."
        return redirect(url_for("cloud_chat_index"))

    @app.route("/cloudchat/logout", methods=["POST"])
    def cloud_chat_logout():
        _clear_cloud_chat_session()
        session["cloudchat_login_error"] = "You have been logged out of Cloud Chat."
        return redirect(url_for("cloud_chat_index"))

    @app.route("/cloudchat/admin")
    def cloud_chat_admin():
        admin_redirect = require_site_admin()
        if admin_redirect:
            return admin_redirect
        return _render_cloud_chat_admin()

    @app.route("/cloudchat/admin/users/create", methods=["POST"])
    def cloud_chat_create_user():
        admin_redirect = require_site_admin()
        if admin_redirect:
            return admin_redirect

        username = _normalize_username(request.form.get("username", ""))
        password = request.form.get("password", "")
        if not username:
            return _render_cloud_chat_admin(
                error="Enter a username using letters, numbers, dots, dashes, or underscores.",
                username_value=request.form.get("username", ""),
            )
        if len(password) < PASSWORD_MIN_LENGTH:
            return _render_cloud_chat_admin(
                error=f"Passwords must be at least {PASSWORD_MIN_LENGTH} characters long.",
                username_value=username,
            )

        db = _get_db()
        try:
            db.execute(
                """
                INSERT INTO cloud_chat_users (username, password_hash)
                VALUES (?, ?)
                """,
                (username, generate_password_hash(password)),
            )
            db.commit()
        except sqlite3.IntegrityError:
            db.close()
            return _render_cloud_chat_admin(
                error="That Cloud Chat username already exists.",
                username_value=username,
            )
        db.close()
        return _render_cloud_chat_admin(
            admin_message=f"Created Cloud Chat user {username}.",
            password_preview={
                "username": username,
                "password": password,
                "action": "created",
            },
        )

    @app.route("/cloudchat/admin/users/password/<int:user_id>", methods=["POST"])
    def cloud_chat_reset_user_password(user_id):
        admin_redirect = require_site_admin()
        if admin_redirect:
            return admin_redirect

        user = _require_cloud_chat_admin_user(user_id)
        password = request.form.get("password", "")
        if len(password) < PASSWORD_MIN_LENGTH:
            return _render_cloud_chat_admin(
                error=f"New passwords must be at least {PASSWORD_MIN_LENGTH} characters long."
            )

        db = _get_db()
        db.execute(
            """
            UPDATE cloud_chat_users
            SET password_hash = ?
            WHERE id = ?
            """,
            (generate_password_hash(password), user_id),
        )
        db.commit()
        db.close()
        return _render_cloud_chat_admin(
            admin_message=f"Reset the password for {user['username']}.",
            password_preview={
                "username": user["username"],
                "password": password,
                "action": "reset",
            },
        )

    @app.route("/cloudchat/admin/users/toggle/<int:user_id>", methods=["POST"])
    def cloud_chat_toggle_user(user_id):
        admin_redirect = require_site_admin()
        if admin_redirect:
            return admin_redirect

        user = _require_cloud_chat_admin_user(user_id)
        next_state = 0 if user["is_active"] else 1
        db = _get_db()
        db.execute(
            """
            UPDATE cloud_chat_users
            SET is_active = ?
            WHERE id = ?
            """,
            (next_state, user_id),
        )
        db.commit()
        db.close()

        if not next_state and session.get("cloudchat_user_id") == user_id:
            _clear_cloud_chat_session()

        session["cloudchat_admin_message"] = (
            f"{'Disabled' if not next_state else 'Re-enabled'} {user['username']}."
        )
        return redirect(url_for("cloud_chat_admin"))

    @app.route("/cloudchat/admin/users/delete/<int:user_id>", methods=["POST"])
    def cloud_chat_delete_user(user_id):
        admin_redirect = require_site_admin()
        if admin_redirect:
            return admin_redirect

        user = _require_cloud_chat_admin_user(user_id)
        db = _get_db()
        db.execute("DELETE FROM cloud_chat_users WHERE id = ?", (user_id,))
        db.commit()
        db.close()

        if session.get("cloudchat_user_id") == user_id:
            _clear_cloud_chat_session()

        session["cloudchat_admin_message"] = f"Deleted {user['username']} from Cloud Chat."
        return redirect(url_for("cloud_chat_admin"))
