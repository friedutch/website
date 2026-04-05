import datetime
import os
import sqlite3

from flask import abort, jsonify, make_response, redirect, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from app.rendering import render_page
from app.site_admin import is_site_admin, require_site_admin


CLOUD_CHAT_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cloud_chat.db")
USERNAME_MAX_LENGTH = 32
PASSWORD_MIN_LENGTH = 12
MAX_LOGIN_ATTEMPTS = 5
LOGIN_LOCKOUT_SECONDS = 900
CHAT_MESSAGE_MAX_LENGTH = 2000
CHAT_THREAD_LIMIT = 120
PRESENCE_ONLINE_WINDOW_SECONDS = 90
PRESENCE_IDLE_WINDOW_SECONDS = 900


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
    db.execute(
        """CREATE TABLE IF NOT EXISTS cloud_chat_messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        recipient_user_id INTEGER,
        message_text TEXT NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES cloud_chat_users(id),
        FOREIGN KEY(recipient_user_id) REFERENCES cloud_chat_users(id)
    )"""
    )
    existing_columns = {row[1] for row in db.execute("PRAGMA table_info(cloud_chat_messages)").fetchall()}
    if "recipient_user_id" not in existing_columns:
        db.execute("ALTER TABLE cloud_chat_messages ADD COLUMN recipient_user_id INTEGER")
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_cloud_chat_messages_thread
        ON cloud_chat_messages (user_id, recipient_user_id, id)
        """
    )
    db.execute(
        """CREATE TABLE IF NOT EXISTS cloud_chat_thread_state (
        user_id INTEGER NOT NULL,
        partner_user_id INTEGER NOT NULL,
        last_read_message_id INTEGER NOT NULL DEFAULT 0,
        opened_at TEXT DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (user_id, partner_user_id),
        FOREIGN KEY(user_id) REFERENCES cloud_chat_users(id),
        FOREIGN KEY(partner_user_id) REFERENCES cloud_chat_users(id)
    )"""
    )
    db.execute(
        """CREATE TABLE IF NOT EXISTS cloud_chat_presence (
        user_id INTEGER PRIMARY KEY,
        last_seen_at TEXT NOT NULL,
        open_partner_id INTEGER,
        FOREIGN KEY(user_id) REFERENCES cloud_chat_users(id),
        FOREIGN KEY(open_partner_id) REFERENCES cloud_chat_users(id)
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


def _normalize_message_text(raw_value):
    value = (raw_value or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    value = "\n".join(line.rstrip() for line in value.split("\n"))
    return value[:CHAT_MESSAGE_MAX_LENGTH]


def _utcnow():
    return datetime.datetime.utcnow()


def _utc_iso():
    return _utcnow().replace(microsecond=0).isoformat()


def _parse_iso_datetime(value):
    if not value:
        return None
    try:
        return datetime.datetime.fromisoformat(value)
    except ValueError:
        return None


def _format_timestamp(value):
    return value[:19].replace("T", " ") if value else ""


def _presence_status(last_seen_at):
    seen = _parse_iso_datetime(last_seen_at)
    if not seen:
        return "offline"

    age_seconds = (_utcnow() - seen).total_seconds()
    if age_seconds <= PRESENCE_ONLINE_WINDOW_SECONDS:
        return "online"
    if age_seconds <= PRESENCE_IDLE_WINDOW_SECONDS:
        return "idle"
    return "offline"


def _touch_presence(user_id, open_partner_id=None):
    if not user_id:
        return

    db = _get_db()
    try:
        db.execute(
            """
            INSERT INTO cloud_chat_presence (user_id, last_seen_at, open_partner_id)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                last_seen_at = excluded.last_seen_at,
                open_partner_id = excluded.open_partner_id
            """,
            (user_id, _utc_iso(), open_partner_id),
        )
        db.commit()
    finally:
        db.close()


def _presence_map(db, user_ids):
    ids = [int(user_id) for user_id in user_ids if user_id]
    if not ids:
        return {}

    placeholders = ", ".join("?" for _ in ids)
    rows = db.execute(
        f"""
        SELECT user_id, last_seen_at, open_partner_id
        FROM cloud_chat_presence
        WHERE user_id IN ({placeholders})
        """,
        ids,
    ).fetchall()

    presence = {}
    for row in rows:
        presence[row["user_id"]] = {
            "status": _presence_status(row["last_seen_at"]),
            "last_seen_at": _format_timestamp(row["last_seen_at"]),
            "open_partner_id": row["open_partner_id"],
        }
    return presence


def _latest_thread_message_id(db, current_user_id, partner_id):
    row = db.execute(
        """
        SELECT id
        FROM cloud_chat_messages
        WHERE recipient_user_id IS NOT NULL
          AND (
            (user_id = ? AND recipient_user_id = ?)
            OR
            (user_id = ? AND recipient_user_id = ?)
          )
        ORDER BY id DESC
        LIMIT 1
        """,
        (current_user_id, partner_id, partner_id, current_user_id),
    ).fetchone()
    return row["id"] if row else 0


def _mark_thread_read(user_id, partner_id):
    if not user_id or not partner_id:
        return 0

    db = _get_db()
    try:
        latest_message_id = _latest_thread_message_id(db, user_id, partner_id)
        db.execute(
            """
            INSERT INTO cloud_chat_thread_state (user_id, partner_user_id, last_read_message_id, opened_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id, partner_user_id) DO UPDATE SET
                last_read_message_id = excluded.last_read_message_id,
                opened_at = excluded.opened_at
            """,
            (user_id, partner_id, latest_message_id, _utc_iso()),
        )
        db.commit()
        return latest_message_id
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


def _require_cloud_chat_user():
    user = _get_current_user()
    if user:
        return user, None
    session["cloudchat_login_error"] = "Sign in to continue in Private Chat."
    return None, redirect(url_for("cloud_chat_index"))


def _get_active_chat_user(user_id):
    if not user_id:
        return None
    db = _get_db()
    try:
        row = db.execute(
            """
            SELECT id, username, is_active, created_at
            FROM cloud_chat_users
            WHERE id = ? AND is_active = 1
            """,
            (user_id,),
        ).fetchone()
    finally:
        db.close()

    if not row:
        return None

    return {
        "id": row["id"],
        "username": row["username"],
        "created_at": _format_timestamp(row["created_at"]),
    }


def _list_dm_partners(current_user_id):
    db = _get_db()
    try:
        rows = db.execute(
            """
            SELECT id, username, created_at
            FROM cloud_chat_users
            WHERE is_active = 1 AND id != ?
            ORDER BY username COLLATE NOCASE ASC, id ASC
            """,
            (current_user_id,),
        ).fetchall()
        presence = _presence_map(db, [row["id"] for row in rows])
        state_rows = db.execute(
            """
            SELECT partner_user_id, last_read_message_id
            FROM cloud_chat_thread_state
            WHERE user_id = ?
            """,
            (current_user_id,),
        ).fetchall()
        state_map = {
            row["partner_user_id"]: row["last_read_message_id"]
            for row in state_rows
        }

        partners = []
        for row in rows:
            latest = db.execute(
                """
                SELECT id, message_text, created_at, user_id
                FROM cloud_chat_messages
                WHERE recipient_user_id IS NOT NULL
                  AND (
                    (user_id = ? AND recipient_user_id = ?)
                    OR
                    (user_id = ? AND recipient_user_id = ?)
                  )
                ORDER BY id DESC
                LIMIT 1
                """,
                (current_user_id, row["id"], row["id"], current_user_id),
            ).fetchone()

            unread_row = db.execute(
                """
                SELECT COUNT(*) AS unread_count
                FROM cloud_chat_messages
                WHERE user_id = ?
                  AND recipient_user_id = ?
                  AND id > ?
                """,
                (row["id"], current_user_id, state_map.get(row["id"], 0)),
            ).fetchone()

            preview = ""
            latest_at = ""
            latest_from_current = False
            latest_message_id = 0
            if latest:
                preview = latest["message_text"][:72]
                latest_at = _format_timestamp(latest["created_at"])
                latest_from_current = latest["user_id"] == current_user_id
                latest_message_id = latest["id"]

            partner_presence = presence.get(row["id"], {"status": "offline", "last_seen_at": "", "open_partner_id": None})
            unread_count = unread_row["unread_count"] if unread_row else 0
            sort_key = latest_message_id or 0

            partners.append(
                {
                    "id": row["id"],
                    "username": row["username"],
                    "created_at": _format_timestamp(row["created_at"]),
                    "latest_preview": preview,
                    "latest_at": latest_at,
                    "latest_from_current": latest_from_current,
                    "latest_message_id": latest_message_id,
                    "unread_count": unread_count,
                    "status": partner_presence["status"],
                    "last_seen_at": partner_presence["last_seen_at"],
                    "is_watching_thread": partner_presence["open_partner_id"] == current_user_id,
                    "sort_key": sort_key,
                }
            )
    finally:
        db.close()

    partners.sort(
        key=lambda item: (
            item["latest_message_id"] == 0,
            -(item["unread_count"] > 0),
            -item["sort_key"],
            item["username"],
        )
    )
    return partners


def _select_dm_partner(current_user_id, requested_partner_id):
    partners = _list_dm_partners(current_user_id)
    partner = None
    if requested_partner_id:
        partner = next((item for item in partners if item["id"] == requested_partner_id), None)
    if partner is None and partners:
        partner = partners[0]
    for item in partners:
        item["selected"] = bool(partner and item["id"] == partner["id"])
    return partner, partners


def _list_dm_messages(current_user_id, partner_id, limit=CHAT_THREAD_LIMIT):
    if not partner_id:
        return []

    db = _get_db()
    try:
        rows = db.execute(
            """
            SELECT messages.id, messages.message_text, messages.created_at,
                   messages.user_id AS author_id, author.username AS author_username
            FROM cloud_chat_messages AS messages
            JOIN cloud_chat_users AS author ON author.id = messages.user_id
            WHERE messages.recipient_user_id IS NOT NULL
              AND (
                (messages.user_id = ? AND messages.recipient_user_id = ?)
                OR
                (messages.user_id = ? AND messages.recipient_user_id = ?)
              )
            ORDER BY messages.id DESC
            LIMIT ?
            """,
            (current_user_id, partner_id, partner_id, current_user_id, max(1, min(limit, 200))),
        ).fetchall()
    finally:
        db.close()

    messages = []
    for row in reversed(rows):
        messages.append(
            {
                "id": row["id"],
                "message_text": row["message_text"],
                "created_at": _format_timestamp(row["created_at"]),
                "author_id": row["author_id"],
                "author_username": row["author_username"],
            }
        )
    return messages


def _json_no_store(payload, status=200):
    response = make_response(jsonify(payload), status)
    response.headers["Cache-Control"] = "no-store, max-age=0"
    response.headers["Pragma"] = "no-cache"
    return response


def _render_cloud_chat_login(error=None):
    return render_page(
        "cloud_chat_login.html",
        page_name="Private Chat — Login",
        error=error or _pop_notice("cloudchat_login_error"),
        admin_logged_in=is_site_admin(),
        noindex=True,
    )


def _render_cloud_chat_app(user, error=None, draft_message="", requested_partner_id=None):
    selected_partner, partners = _select_dm_partner(user["id"], requested_partner_id)
    selected_partner_id = selected_partner["id"] if selected_partner else None

    _touch_presence(user["id"], selected_partner_id)
    if selected_partner_id:
        _mark_thread_read(user["id"], selected_partner_id)
        selected_partner, partners = _select_dm_partner(user["id"], selected_partner_id)

    messages = _list_dm_messages(user["id"], selected_partner["id"] if selected_partner else None)
    return render_page(
        "cloud_chat_app.html",
        page_name="Private Chat — Friedutch Plus",
        current_user=user,
        app_message=_pop_notice("cloudchat_app_message"),
        app_error=error,
        draft_message=draft_message,
        dm_partners=partners,
        selected_partner=selected_partner,
        chat_messages=messages,
        chat_message_limit=CHAT_MESSAGE_MAX_LENGTH,
        chat_message_count=len(messages),
        current_user_status="online",
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
        page_name="Private Chat — Admin",
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
    def legacy_cloud_chat_index():
        requested_partner_id = request.args.get("dm", type=int)
        if requested_partner_id:
            return redirect(url_for("cloud_chat_index", dm=requested_partner_id), code=302)
        return redirect(url_for("cloud_chat_index"), code=302)

    @app.route("/privatechat/")
    def cloud_chat_index():
        user = _get_current_user()
        if user:
            requested_partner_id = request.args.get("dm", type=int)
            return _render_cloud_chat_app(user, requested_partner_id=requested_partner_id)
        return _render_cloud_chat_login()

    @app.route("/cloudchat/login", methods=["POST"])
    @app.route("/privatechat/login", methods=["POST"])
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
            return _render_cloud_chat_login(error="Invalid Private Chat credentials.")

        _reset_failed_login(username)
        session["cloudchat_user_id"] = row["id"]
        session["cloudchat_username"] = row["username"]
        session["cloudchat_app_message"] = f"Welcome back, {row['username']}."
        return redirect(url_for("cloud_chat_index"))

    @app.route("/cloudchat/logout", methods=["POST"])
    @app.route("/privatechat/logout", methods=["POST"])
    def cloud_chat_logout():
        _clear_cloud_chat_session()
        session["cloudchat_login_error"] = "You have been logged out of Private Chat."
        return redirect(url_for("cloud_chat_index"))

    @app.route("/cloudchat/messages/send/<int:partner_id>", methods=["POST"])
    @app.route("/privatechat/messages/send/<int:partner_id>", methods=["POST"])
    def cloud_chat_send_message(partner_id):
        user, redirect_response = _require_cloud_chat_user()
        if redirect_response:
            return redirect_response

        if partner_id == user["id"]:
            return _render_cloud_chat_app(user, error="You cannot open a direct message with yourself.")

        partner = _get_active_chat_user(partner_id)
        if not partner:
            return _render_cloud_chat_app(user, error="That Private Chat user is unavailable for direct messages.")

        _touch_presence(user["id"], partner_id)

        message_text = _normalize_message_text(request.form.get("message", ""))
        if not message_text:
            return _render_cloud_chat_app(
                user,
                error="Write a message before sending it.",
                draft_message=request.form.get("message", ""),
                requested_partner_id=partner_id,
            )

        db = _get_db()
        db.execute(
            """
            INSERT INTO cloud_chat_messages (user_id, recipient_user_id, message_text)
            VALUES (?, ?, ?)
            """,
            (user["id"], partner_id, message_text),
        )
        db.commit()
        db.close()
        _mark_thread_read(user["id"], partner_id)
        session["cloudchat_app_message"] = f"Message sent to {partner['username']}."
        return redirect(url_for("cloud_chat_index", dm=partner_id))

    @app.route("/cloudchat/messages/live/<int:partner_id>")
    @app.route("/privatechat/messages/live/<int:partner_id>")
    def cloud_chat_live_messages(partner_id):
        user = _get_current_user()
        if not user:
            return _json_no_store({"error": "auth_required"}, status=401)

        if partner_id == user["id"]:
            return _json_no_store({"error": "invalid_partner"}, status=400)

        partner = _get_active_chat_user(partner_id)
        if not partner:
            return _json_no_store({"error": "partner_unavailable"}, status=404)

        _touch_presence(user["id"], partner_id)
        _mark_thread_read(user["id"], partner_id)
        partners = _list_dm_partners(user["id"])
        partner = next((item for item in partners if item["id"] == partner_id), None)
        if not partner:
            return _json_no_store({"error": "partner_unavailable"}, status=404)
        messages = _list_dm_messages(user["id"], partner_id)
        latest_message_id = messages[-1]["id"] if messages else 0
        return _json_no_store(
            {
                "messages": messages,
                "message_count": len(messages),
                "latest_message_id": latest_message_id,
                "partners": partners,
                "partner": {
                    "id": partner["id"],
                    "username": partner["username"],
                    "status": partner["status"],
                    "last_seen_at": partner["last_seen_at"],
                    "unread_count": 0,
                },
            }
        )

    @app.route("/cloudchat/admin")
    def legacy_cloud_chat_admin():
        return redirect(url_for("cloud_chat_admin"), code=302)

    @app.route("/privatechat/admin")
    def cloud_chat_admin():
        admin_redirect = require_site_admin()
        if admin_redirect:
            return admin_redirect
        return _render_cloud_chat_admin()

    @app.route("/cloudchat/admin/users/create", methods=["POST"])
    @app.route("/privatechat/admin/users/create", methods=["POST"])
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
                error="That Private Chat username already exists.",
                username_value=username,
            )
        db.close()
        return _render_cloud_chat_admin(
            admin_message=f"Created Private Chat user {username}.",
            password_preview={
                "username": username,
                "password": password,
                "action": "created",
            },
        )

    @app.route("/cloudchat/admin/users/password/<int:user_id>", methods=["POST"])
    @app.route("/privatechat/admin/users/password/<int:user_id>", methods=["POST"])
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
    @app.route("/privatechat/admin/users/toggle/<int:user_id>", methods=["POST"])
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
    @app.route("/privatechat/admin/users/delete/<int:user_id>", methods=["POST"])
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

        session["cloudchat_admin_message"] = f"Deleted {user['username']} from Private Chat."
        return redirect(url_for("cloud_chat_admin"))
