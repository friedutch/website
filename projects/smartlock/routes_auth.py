import datetime
import hashlib
import random
import sqlite3

import bleach
from flask import jsonify, redirect, request, session, url_for
from itsdangerous import BadSignature, SignatureExpired

from app.rendering import render_page
from app.site_admin import is_site_admin

from .activity import log_attempt
from .config import MAGIC_LINK_TTL_SECONDS, get_serializer
from .db import DB_PATH, get_admin_email, get_db, get_pending_email, set_setting
from .helpers import pop_ui_message
from .mail import send_admin_magic_link, send_verification_link
from .pages import (
    render_admin_panel,
    render_email_pending_page,
    render_login_page,
    render_verification_complete_page,
)
from .session_state import (
    actor_cooldown_key,
    check_brute_force,
    cooldown_remaining,
    create_admin_session,
    get_login_sync_channel,
    record_failed_attempt,
    reset_attempts,
)


def _captcha_options(correct):
    options = {correct}
    while len(options) < 3:
        options.add(str(random.randint(10, 99)))
    options = list(options)
    random.shuffle(options)
    return options


def _brute_force_message(remaining):
    minutes, seconds = divmod(max(0, remaining), 60)
    return f"Too many failed attempts. Try again in {minutes}:{seconds:02d}. 🚫"


def register_auth_routes(app):
    @app.route("/smartlock/login", methods=["GET", "POST"])
    def smartlock_login():
        cooldown_key = actor_cooldown_key("admin_link_cooldown")
        link_cooldown = cooldown_remaining(cooldown_key)
        captcha_code = session.get("admin_captcha_code")
        message = pop_ui_message("smartlock_login_message")
        login_sync_channel = get_login_sync_channel()
        brute_force_remaining = check_brute_force()

        if request.method == "POST":
            if brute_force_remaining > 0:
                return render_login_page(
                    admin_sent=bool(captcha_code),
                    link_cooldown=link_cooldown,
                    captcha_code=captcha_code,
                    message=_brute_force_message(brute_force_remaining),
                    login_sync_channel=login_sync_channel,
                )
            if link_cooldown > 0:
                return render_login_page(
                    admin_sent=bool(captcha_code),
                    link_cooldown=link_cooldown,
                    captcha_code=captcha_code,
                    message=message,
                    login_sync_channel=login_sync_channel,
                )
            captcha_code = str(random.randint(10, 99))
            error = send_admin_magic_link(get_admin_email(), captcha_code)
            if error:
                session.pop("admin_captcha_code", None)
                return render_login_page(
                    admin_sent=False,
                    link_cooldown=0,
                    captcha_code=None,
                    message=error,
                    login_sync_channel=login_sync_channel,
                )
            session["admin_captcha_code"] = captcha_code
            set_setting(cooldown_key, datetime.datetime.utcnow().isoformat())
            return render_login_page(
                admin_sent=True,
                link_cooldown=MAGIC_LINK_TTL_SECONDS,
                captcha_code=captcha_code,
                message=None,
                login_sync_channel=login_sync_channel,
            )

        if link_cooldown == 0 and captcha_code:
            session.pop("admin_captcha_code", None)
            captcha_code = None
        if is_site_admin():
            return redirect(url_for("smartlock_admin"))
        return render_login_page(
            admin_sent=bool(captcha_code),
            link_cooldown=link_cooldown,
            captcha_code=captcha_code,
            message=message,
            login_sync_channel=login_sync_channel,
        )

    @app.route("/smartlock/poll-status")
    def smartlock_poll_status():
        return jsonify({"status": "logged_in" if is_site_admin() else "waiting"})

    @app.route("/smartlock/verify")
    def smartlock_verify():
        token = request.args.get("token")
        try:
            get_serializer().loads(token, salt="admin-magic-login", max_age=MAGIC_LINK_TTL_SECONDS)
        except SignatureExpired:
            return render_login_page(
                admin_sent=False,
                link_cooldown=0,
                captcha_code=None,
                message="Link expired ⏱️",
                login_sync_channel="",
                noindex=True,
            )
        except BadSignature:
            return render_login_page(
                admin_sent=False,
                link_cooldown=0,
                captcha_code=None,
                message="Invalid link 🚫",
                login_sync_channel="",
                noindex=True,
            )

        db = get_db()
        if db.execute("SELECT 1 FROM used_tokens WHERE token = ?", (token,)).fetchone():
            return render_login_page(
                admin_sent=False,
                link_cooldown=0,
                captcha_code=None,
                message="Link already used 🚫",
                login_sync_channel="",
                noindex=True,
            )

        token_hash = hashlib.sha256(token.encode()).hexdigest()
        lookup_db = sqlite3.connect(DB_PATH)
        lookup_db.row_factory = sqlite3.Row
        row = lookup_db.execute(
            "SELECT number FROM match_numbers WHERE token_hash = ?",
            (token_hash,),
        ).fetchone()
        lookup_db.close()
        correct = row["number"] if row else None
        if not correct:
            return render_login_page(
                admin_sent=False,
                link_cooldown=0,
                captcha_code=None,
                message="Session expired 💨",
                login_sync_channel="",
                noindex=True,
            )
        return render_page(
            "smartlock/captcha.html",
            page_name="Smart Lock — Solve captcha",
            token=token,
            options=_captcha_options(correct),
            error=None,
            mode="login",
            noindex=True,
        )

    @app.route("/smartlock/verify-captcha", methods=["POST"])
    def smartlock_verify_captcha():
        token = request.form.get("token")
        chosen = request.form.get("captcha_code")
        if not token or not chosen:
            return render_login_page(
                admin_sent=False,
                link_cooldown=0,
                captcha_code=None,
                message="Invalid verification request 🚫",
                login_sync_channel="",
            )

        brute_force_remaining = check_brute_force()
        if brute_force_remaining > 0:
            session["smartlock_login_message"] = _brute_force_message(brute_force_remaining)
            return redirect(url_for("smartlock_login"))

        token_hash = hashlib.sha256(token.encode()).hexdigest()
        lookup_db = sqlite3.connect(DB_PATH)
        lookup_db.row_factory = sqlite3.Row
        row = lookup_db.execute(
            "SELECT number FROM match_numbers WHERE token_hash = ?",
            (token_hash,),
        ).fetchone()
        lookup_db.close()
        correct = row["number"] if row else None
        if not correct or chosen != correct:
            log_attempt("admin_magic_link", method_id="captcha", success=False)
            record_failed_attempt()
            cleanup_db = sqlite3.connect(DB_PATH)
            cleanup_db.execute("DELETE FROM match_numbers WHERE token_hash = ?", (token_hash,))
            cleanup_db.commit()
            cleanup_db.close()
            set_setting(actor_cooldown_key("admin_link_cooldown"), datetime.datetime.utcnow().isoformat())
            session["smartlock_login_message"] = "Wrong captcha. Request a new link. 🚫"
            return redirect(url_for("smartlock_login"))

        db = get_db()
        if db.execute("SELECT 1 FROM used_tokens WHERE token = ?", (token,)).fetchone():
            return render_login_page(
                admin_sent=False,
                link_cooldown=0,
                captcha_code=None,
                message="Link already used 🚫",
                login_sync_channel="",
            )
        db.execute("INSERT INTO used_tokens (token) VALUES (?)", (token,))
        db.commit()
        log_attempt("admin_magic_link", method_id="captcha", success=True, user_name="admin")
        reset_attempts()
        session.pop("admin_captcha_code", None)
        cleanup_db = sqlite3.connect(DB_PATH)
        cleanup_db.execute("DELETE FROM match_numbers WHERE token_hash = ?", (token_hash,))
        cleanup_db.commit()
        cleanup_db.close()
        create_admin_session()
        return render_verification_complete_page(
            redirect_url=url_for("smartlock_admin"),
            page_name="Smart Lock — Access Granted",
            login_sync_channel=get_login_sync_channel(),
        )

    @app.route("/smartlock/join/<token>")
    def smartlock_join(token):
        if is_site_admin():
            return render_verification_complete_page(
                redirect_url=url_for("smartlock_admin"),
                page_name="Smart Lock — Session Active",
                heading="Session already active",
                description="Closing this invite page and returning to the existing admin session.",
                fallback_copy="If this page stays open, continue here.",
                noindex=True,
            )

        db = sqlite3.connect(DB_PATH)
        db.row_factory = sqlite3.Row
        row = db.execute("SELECT * FROM join_tokens WHERE token = ?", (token,)).fetchone()
        db.close()
        if not row:
            return render_login_page(
                admin_sent=False,
                link_cooldown=0,
                captcha_code=None,
                message="Join link expired or invalid 🚫",
                login_sync_channel="",
                noindex=True,
            )

        created = datetime.datetime.fromisoformat(row["created_at"])
        if (datetime.datetime.utcnow() - created).total_seconds() > MAGIC_LINK_TTL_SECONDS:
            cleanup_db = sqlite3.connect(DB_PATH)
            cleanup_db.execute("DELETE FROM join_tokens WHERE token = ?", (token,))
            cleanup_db.commit()
            cleanup_db.close()
            return render_login_page(
                admin_sent=False,
                link_cooldown=0,
                captcha_code=None,
                message="Join link expired ⏱️",
                login_sync_channel="",
                noindex=True,
            )

        return render_page(
            "smartlock/captcha.html",
            page_name="Smart Lock — Solve captcha",
            token=token,
            options=_captcha_options(row["number"]),
            error=None,
            mode="join",
            noindex=True,
        )

    @app.route("/smartlock/join-captcha", methods=["POST"])
    def smartlock_join_captcha():
        if is_site_admin():
            return render_verification_complete_page(
                redirect_url=url_for("smartlock_admin"),
                page_name="Smart Lock — Session Active",
                heading="Session already active",
                description="Closing this invite page and returning to the existing admin session.",
                fallback_copy="If this page stays open, continue here.",
                noindex=True,
            )

        token = request.form.get("token")
        chosen = request.form.get("captcha_code")
        db = sqlite3.connect(DB_PATH)
        db.row_factory = sqlite3.Row
        row = db.execute("SELECT * FROM join_tokens WHERE token = ?", (token,)).fetchone()
        db.close()
        if not row:
            return render_login_page(
                admin_sent=False,
                link_cooldown=0,
                captcha_code=None,
                message="Join link expired 🚫",
                login_sync_channel="",
                noindex=True,
            )

        created = datetime.datetime.fromisoformat(row["created_at"])
        if (datetime.datetime.utcnow() - created).total_seconds() > MAGIC_LINK_TTL_SECONDS:
            return render_login_page(
                admin_sent=False,
                link_cooldown=0,
                captcha_code=None,
                message="Join link expired ⏱️",
                login_sync_channel="",
                noindex=True,
            )
        if chosen != row["number"]:
            log_attempt("join_session", method_id="captcha", success=False)
            cleanup_db = sqlite3.connect(DB_PATH)
            cleanup_db.execute("DELETE FROM join_tokens WHERE token = ?", (token,))
            cleanup_db.commit()
            cleanup_db.close()
            return render_login_page(
                admin_sent=False,
                link_cooldown=0,
                captcha_code=None,
                message="Wrong captcha. Request a new link. 🚫",
                login_sync_channel="",
                noindex=True,
            )

        cleanup_db = sqlite3.connect(DB_PATH)
        cleanup_db.execute("DELETE FROM join_tokens WHERE token = ?", (token,))
        cleanup_db.commit()
        cleanup_db.close()
        log_attempt("join_session", method_id="captcha", success=True, user_name="admin")
        create_admin_session()
        return redirect(url_for("smartlock_admin"))

    @app.route("/smartlock/change-email", methods=["POST"])
    def smartlock_change_email():
        if not is_site_admin():
            return redirect(url_for("smartlock_login"))

        if cooldown_remaining("admin_email_change_cooldown") > 0:
            return redirect(url_for("smartlock_admin"))

        new_email = request.form.get("new_email", "").strip().lower()
        new_email = bleach.clean(new_email, tags=[], strip=True)[:200]
        if not new_email:
            return redirect(url_for("smartlock_admin"))

        now = datetime.datetime.utcnow().isoformat()
        captcha_code = str(random.randint(10, 99))
        error = send_verification_link(new_email, captcha_code)
        if error:
            session.pop("email_change_captcha_code", None)
            return render_admin_panel(email_error=error)

        session["email_change_captcha_code"] = captcha_code
        db = get_db()
        db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('pending_admin_email', ?)", (new_email,))
        db.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES ('pending_admin_email_sent_at', ?)",
            (now,),
        )
        db.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES ('admin_email_change_cooldown', ?)",
            (now,),
        )
        db.commit()
        return redirect(url_for("smartlock_email_pending"))

    @app.route("/smartlock/change-email/resend", methods=["POST"])
    def smartlock_resend_verification():
        if not is_site_admin():
            return redirect(url_for("smartlock_login"))
        pending = get_pending_email()
        if not pending:
            return redirect(url_for("smartlock_admin"))
        now = datetime.datetime.utcnow().isoformat()
        captcha_code = str(random.randint(10, 99))
        error = send_verification_link(pending, captcha_code)
        if error:
            return render_email_pending_page(
                error=error,
                captcha_code=session.get("email_change_captcha_code"),
            )
        session["email_change_captcha_code"] = captcha_code
        set_setting("pending_admin_email_sent_at", now)
        return redirect(url_for("smartlock_email_pending"))

    @app.route("/smartlock/change-email/cancel", methods=["POST"])
    def smartlock_cancel_email_change():
        if not is_site_admin():
            return redirect(url_for("smartlock_login"))
        db = get_db()
        db.execute("DELETE FROM settings WHERE key = 'pending_admin_email'")
        db.execute("DELETE FROM settings WHERE key = 'pending_admin_email_sent_at'")
        db.commit()
        return redirect(url_for("smartlock_admin"))

    @app.route("/smartlock/change-email/pending")
    def smartlock_email_pending():
        if not is_site_admin():
            return redirect(url_for("smartlock_login"))
        if not get_pending_email():
            return redirect(url_for("smartlock_admin"))
        return render_email_pending_page(
            captcha_code=session.get("email_change_captcha_code"),
        )

    @app.route("/smartlock/verify-email-change")
    def smartlock_verify_email_change():
        token = request.args.get("token")
        try:
            new_email = get_serializer().loads(
                token,
                salt="admin-email-change",
                max_age=MAGIC_LINK_TTL_SECONDS,
            )
        except SignatureExpired:
            return render_email_pending_page(error="Link expired ⏱️", noindex=True)
        except BadSignature:
            return render_email_pending_page(error="Invalid link 🚫", noindex=True)

        pending = get_pending_email()
        if not pending or pending != new_email:
            return redirect(url_for("smartlock_admin"))

        token_hash = hashlib.sha256(token.encode()).hexdigest()
        lookup_db = sqlite3.connect(DB_PATH)
        lookup_db.row_factory = sqlite3.Row
        row = lookup_db.execute(
            "SELECT number FROM match_numbers WHERE token_hash = ?",
            (token_hash,),
        ).fetchone()
        lookup_db.close()
        correct = row["number"] if row else None
        if not correct:
            return render_email_pending_page(error="Session expired 💨", noindex=True)

        return render_page(
            "smartlock/captcha.html",
            page_name="Smart Lock — Solve captcha",
            token=token,
            options=_captcha_options(correct),
            error=None,
            mode="email_change",
            noindex=True,
        )

    @app.route("/smartlock/verify-email-captcha", methods=["POST"])
    def smartlock_verify_email_captcha():
        token = request.form.get("token")
        chosen = request.form.get("captcha_code")
        token_hash = hashlib.sha256((token or "").encode()).hexdigest()
        lookup_db = sqlite3.connect(DB_PATH)
        lookup_db.row_factory = sqlite3.Row
        row = lookup_db.execute(
            "SELECT number FROM match_numbers WHERE token_hash = ?",
            (token_hash,),
        ).fetchone()
        lookup_db.close()
        correct = row["number"] if row else None
        if not correct or chosen != correct:
            cleanup_db = sqlite3.connect(DB_PATH)
            cleanup_db.execute("DELETE FROM match_numbers WHERE token_hash = ?", (token_hash,))
            cleanup_db.commit()
            cleanup_db.close()
            return render_email_pending_page(
                error="Wrong captcha. Request a new link. 🚫",
                noindex=True,
            )

        try:
            new_email = get_serializer().loads(
                token,
                salt="admin-email-change",
                max_age=MAGIC_LINK_TTL_SECONDS,
            )
        except Exception:
            return render_email_pending_page(error="Link expired ⏱️", noindex=True)

        pending = get_pending_email()
        if not pending or pending != new_email:
            return redirect(url_for("smartlock_admin"))

        db = get_db()
        db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('admin_email', ?)", (new_email,))
        db.execute("DELETE FROM settings WHERE key = 'pending_admin_email'")
        db.execute("DELETE FROM settings WHERE key = 'pending_admin_email_sent_at'")
        db.commit()
        session.pop("email_change_captcha_code", None)

        cleanup_db = sqlite3.connect(DB_PATH)
        cleanup_db.execute("DELETE FROM match_numbers WHERE token_hash = ?", (token_hash,))
        cleanup_db.commit()
        cleanup_db.close()
        return redirect(url_for("smartlock_admin"))
