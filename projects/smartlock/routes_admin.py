import random
import sqlite3

from flask import abort, redirect, request, session, url_for

from app.site_admin import is_site_admin

from .db import DB_PATH, get_db
from .helpers import sanitize
from .pages import render_admin_panel, render_user_detail_page
from .session_state import create_join_invite


def _generate_passcode():
    db = sqlite3.connect(DB_PATH)
    try:
        while True:
            code = str(random.randint(100000, 999999))
            if not db.execute("SELECT 1 FROM users WHERE passcode = ?", (code,)).fetchone():
                return code
    finally:
        db.close()


def _require_user(user_id):
    user = get_db().execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if not user:
        abort(404)
    return user


def register_admin_routes(app):
    @app.route("/smartlock/")
    def smartlock_index():
        if is_site_admin():
            return redirect(url_for("smartlock_admin"))
        return redirect(url_for("smartlock_login"))

    @app.route("/smartlock/add-session", methods=["POST"])
    def smartlock_add_session():
        if not is_site_admin():
            return redirect(url_for("smartlock_login"))
        create_join_invite()
        return redirect(url_for("smartlock_admin"))

    @app.route("/smartlock/session/logout/<session_token>", methods=["POST"])
    def smartlock_session_logout(session_token):
        if not is_site_admin():
            return redirect(url_for("smartlock_login"))
        db = get_db()
        db.execute("DELETE FROM active_sessions WHERE session_token = ?", (session_token,))
        db.commit()
        if session.get("session_token") == session_token:
            session.clear()
            return redirect(url_for("smartlock_login"))
        return redirect(url_for("smartlock_admin"))

    @app.route("/smartlock/session/logout-all", methods=["POST"])
    def smartlock_session_logout_all():
        if not is_site_admin():
            return redirect(url_for("smartlock_login"))
        current = session.get("session_token")
        db = get_db()
        db.execute("DELETE FROM active_sessions WHERE session_token != ?", (current,))
        db.commit()
        return redirect(url_for("smartlock_admin"))

    @app.route("/smartlock/admin")
    def smartlock_admin():
        if not is_site_admin():
            return redirect(url_for("smartlock_login"))
        return render_admin_panel()

    @app.route("/smartlock/users/new")
    def smartlock_new_user():
        if not is_site_admin():
            return redirect(url_for("smartlock_login"))
        draft_user = {
            "id": None,
            "name": "",
            "passcode": None,
            "rfid_enabled": 0,
            "rfid_id": "",
            "fingerprint_enabled": 0,
            "fingerprint_id": "",
        }
        return render_user_detail_page(draft_user, is_new_user=True, error=None)

    @app.route("/smartlock/users/add", methods=["POST"])
    def smartlock_add_user():
        return redirect(url_for("smartlock_new_user"))

    @app.route("/smartlock/users/create", methods=["POST"])
    def smartlock_create_user():
        if not is_site_admin():
            return redirect(url_for("smartlock_login"))

        name = sanitize(request.form.get("name", ""))
        rfid_enabled = 1 if request.form.get("rfid_enabled") == "on" else 0
        fingerprint_enabled = 1 if request.form.get("fingerprint_enabled") == "on" else 0
        rfid_id = sanitize(request.form.get("rfid_id", ""))
        fingerprint_id = sanitize(request.form.get("fingerprint_id", ""))
        draft_user = {
            "id": None,
            "name": name,
            "passcode": None,
            "rfid_enabled": rfid_enabled,
            "rfid_id": rfid_id,
            "fingerprint_enabled": fingerprint_enabled,
            "fingerprint_id": fingerprint_id,
        }
        if not name:
            return render_user_detail_page(
                draft_user,
                is_new_user=True,
                error="Enter a user name before creating this profile.",
            )

        db = get_db()
        if db.execute("SELECT 1 FROM users WHERE name = ?", (name,)).fetchone():
            return render_user_detail_page(
                draft_user,
                is_new_user=True,
                error="A user with that name already exists.",
            )

        cursor = db.execute(
            """
            INSERT INTO users (name, passcode, rfid_enabled, rfid_id, fingerprint_enabled, fingerprint_id)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                name,
                _generate_passcode(),
                rfid_enabled,
                rfid_id or None,
                fingerprint_enabled,
                fingerprint_id or None,
            ),
        )
        db.commit()
        return redirect(url_for("smartlock_user_detail", user_id=cursor.lastrowid))

    @app.route("/smartlock/users/delete/<int:user_id>", methods=["POST"])
    def smartlock_delete_user(user_id):
        if not is_site_admin():
            return redirect(url_for("smartlock_login"))
        _require_user(user_id)
        get_db().execute("DELETE FROM users WHERE id = ?", (user_id,))
        get_db().commit()
        return redirect(url_for("smartlock_admin"))

    @app.route("/smartlock/user/<int:user_id>")
    def smartlock_user_detail(user_id):
        if not is_site_admin():
            return redirect(url_for("smartlock_login"))
        return render_user_detail_page(_require_user(user_id), is_new_user=False, error=None, noindex=True)

    @app.route("/smartlock/user/<int:user_id>/toggle/<method>", methods=["POST"])
    def smartlock_toggle_method(user_id, method):
        if not is_site_admin():
            return redirect(url_for("smartlock_login"))
        if method not in ("rfid", "fingerprint"):
            return redirect(url_for("smartlock_user_detail", user_id=user_id))
        user = _require_user(user_id)
        column = f"{method}_enabled"
        db = get_db()
        db.execute(f"UPDATE users SET {column} = ? WHERE id = ?", (0 if user[column] else 1, user_id))
        db.commit()
        return redirect(url_for("smartlock_user_detail", user_id=user_id))

    @app.route("/smartlock/user/<int:user_id>/set/<method>", methods=["POST"])
    def smartlock_set_method_id(user_id, method):
        if not is_site_admin():
            return redirect(url_for("smartlock_login"))
        if method not in ("rfid", "fingerprint"):
            return redirect(url_for("smartlock_user_detail", user_id=user_id))
        _require_user(user_id)
        value = sanitize(request.form.get("id_value", ""))
        get_db().execute(f"UPDATE users SET {method}_id = ? WHERE id = ?", (value or None, user_id))
        get_db().commit()
        return redirect(url_for("smartlock_user_detail", user_id=user_id))

    @app.route("/smartlock/logout", methods=["POST"])
    def smartlock_logout():
        token = session.get("session_token")
        if token:
            db = sqlite3.connect(DB_PATH)
            db.execute("DELETE FROM active_sessions WHERE session_token = ?", (token,))
            db.commit()
            db.close()
        session.clear()
        return redirect(url_for("smartlock_login"))
