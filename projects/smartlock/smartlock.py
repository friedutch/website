import os
import sqlite3
import random
import string
import resend
import hashlib
import datetime
import uuid
import bleach
from collections import defaultdict
from flask import request, redirect, url_for, session, g, jsonify, current_app
from urllib.parse import urlencode
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature
from flask_wtf.csrf import generate_csrf
from app.rendering import render_page

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "smartlock.db")
SESSION_TIMEOUT = 3600
_login_attempts = defaultdict(lambda: {"attempts": 0, "locked_until": None})
serializer = None


def init_smartlock_config(secret_key):
    global serializer
    serializer = URLSafeTimedSerializer(secret_key)
    resend.api_key = get_resend_api_key()


def get_resend_api_key():
    return os.getenv("RESEND_API_KEY", "").strip()


def get_mail_from_address():
    return os.getenv("MAIL_FROM", "").strip()


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


def close_db(e=None):
    db = g.pop("db", None)
    if db:
        db.close()


def init_db():
    db = sqlite3.connect(DB_PATH)
    db.execute("""CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        passcode TEXT UNIQUE NOT NULL,
        rfid_enabled INTEGER DEFAULT 0,
        rfid_id TEXT DEFAULT NULL,
        fingerprint_enabled INTEGER DEFAULT 0,
        fingerprint_id TEXT DEFAULT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS used_tokens (
        token TEXT PRIMARY KEY,
        used_at TEXT DEFAULT CURRENT_TIMESTAMP
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS match_numbers (
        token_hash TEXT PRIMARY KEY,
        number TEXT NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS login_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        method TEXT NOT NULL,
        method_id TEXT,
        success INTEGER NOT NULL,
        user_name TEXT,
        ip TEXT,
        location TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        user_agent TEXT
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS active_sessions (
        session_token TEXT PRIMARY KEY,
        ip TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        last_active TEXT DEFAULT CURRENT_TIMESTAMP,
        user_agent TEXT
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS join_tokens (
        token TEXT PRIMARY KEY,
        number TEXT NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS number_attempts (
        token_hash TEXT PRIMARY KEY,
        attempts INTEGER DEFAULT 0
    )""")
    defaults = {"admin_email": os.getenv("MAIL_TO", "")}
    for key, val in defaults.items():
        if not db.execute("SELECT 1 FROM settings WHERE key = ?", (key,)).fetchone():
            db.execute("INSERT INTO settings (key, value) VALUES (?, ?)", (key, val))
    db.commit()
    db.close()


def get_setting(key):
    row = get_db().execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None


def set_setting(key, value):
    get_db().execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
    get_db().commit()


def pop_ui_message(key):
    value = session.get(key)
    if key in session:
        session.pop(key)
    return value


def get_admin_email():
    return get_setting("admin_email")


def get_pending_email():
    return get_setting("pending_admin_email")


def get_pending_sent_at():
    return get_setting("pending_admin_email_sent_at")


def cooldown_remaining(key, seconds=300):
    ts = get_setting(key)
    if not ts:
        return 0
    try:
        recorded_at = datetime.datetime.fromisoformat(ts)
    except ValueError:
        return 0
    now = datetime.datetime.utcnow()
    if recorded_at > now + datetime.timedelta(seconds=seconds):
        return 0
    elapsed = (now - recorded_at).total_seconds()
    return max(0, int(seconds - elapsed))


def is_admin():
    return session.get("role") == "admin"


def get_device_icon():
    ua = request.headers.get("User-Agent", "").lower()
    if "iphone" in ua or "android" in ua and "mobile" in ua:
        return "📱"
    elif "ipad" in ua or "tablet" in ua:
        return "📱"
    elif "mac" in ua and "mobile" not in ua:
        return "🖥️"
    elif "windows" in ua:
        return "💻"
    elif "linux" in ua:
        return "🖥️"
    elif "curl" in ua or "bot" in ua:
        return "🤖"
    else:
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


def get_request_actor_id():
    actor_id = session.get("cooldown_actor_id")
    if actor_id:
        return actor_id
    actor_id = uuid.uuid4().hex
    session["cooldown_actor_id"] = actor_id
    return actor_id


def actor_cooldown_key(base_key):
    return f"{base_key}:{get_request_actor_id()}"


def build_cookie_probe_url():
    args = request.args.to_dict(flat=True)
    args["_smartlock_cookie_probe"] = "1"
    query = urlencode(args)
    return f"{request.path}?{query}" if query else request.path


def cookies_enabled_for_smartlock():
    return session.get("smartlock_cookies_probe") == "ok"


def render_cookies_required():
    return render_page(
        "smartlock/cookies_required.html",
        page_name="Smart Lock — Cookies Required",
    )


def sanitize(value, max_length=100):
    if not value:
        return ""
    return bleach.clean(value.strip(), tags=[], strip=True)[:max_length]


def log_attempt(method, method_id=None, success=False, user_name=None):
    ip = get_client_ip()
    icon = get_device_icon()
    db = sqlite3.connect(DB_PATH)
    db.execute(
        "INSERT INTO login_logs (method, method_id, success, user_name, ip, user_agent) VALUES (?, ?, ?, ?, ?, ?)",
        (method, method_id, 1 if success else 0, user_name, ip, icon),
    )
    db.commit()
    db.close()


def create_admin_session():
    token = str(uuid.uuid4())
    ip = get_client_ip()
    now = datetime.datetime.utcnow().isoformat()
    icon = get_device_icon()
    db = sqlite3.connect(DB_PATH)
    db.execute(
        "INSERT INTO active_sessions (session_token, ip, created_at, last_active, user_agent) VALUES (?, ?, ?, ?, ?)",
        (token, ip, now, now, icon),
    )
    db.commit()
    db.close()
    session["role"] = "admin"
    session["session_token"] = token
    session["last_active"] = now
    session.pop("admin_captcha_code", None)
    cutoff = (datetime.datetime.utcnow() - datetime.timedelta(hours=1)).isoformat()
    db2 = sqlite3.connect(DB_PATH)
    db2.execute("DELETE FROM active_sessions WHERE created_at < ?", (cutoff,))
    db2.execute("DELETE FROM match_numbers WHERE created_at < ?", (cutoff,))
    db2.execute("DELETE FROM join_tokens WHERE created_at < ?", (cutoff,))
    db2.execute("DELETE FROM used_tokens WHERE used_at < ?", (cutoff,))
    db2.commit()
    db2.close()


def get_active_sessions():
    sessions = get_db().execute("SELECT * FROM active_sessions ORDER BY created_at DESC").fetchall()
    result = []
    now = datetime.datetime.utcnow()
    for s in sessions:
        created = datetime.datetime.fromisoformat(s["created_at"])
        elapsed = max(0, int((now - created).total_seconds()))
        remaining = max(0, int(SESSION_TIMEOUT - elapsed))
        minutes, seconds = divmod(remaining, 60)
        result.append(
            {
                "session_token": s["session_token"],
                "ip": s["ip"],
                "created_at": s["created_at"][:19].replace("T", " "),
                "remaining": remaining,
                "remaining_fmt": f"{minutes}:{seconds:02d}",
                "expired": remaining == 0,
                "icon": s["user_agent"] if s["user_agent"] else "🌐",
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
            "device_search_terms": get_device_search_terms(log["user_agent"] if log["user_agent"] else "🌐"),
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
        session_created = datetime.datetime.fromisoformat(session_row["created_at"].replace(" ", "T"))
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

    def sort_key(entry):
        return entry["created_at"]

    return sorted(combined, key=sort_key, reverse=True)


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
        _login_attempts[ip]["locked_until"] = datetime.datetime.utcnow() + datetime.timedelta(seconds=300)


def reset_attempts():
    _login_attempts[get_client_ip()] = {"attempts": 0, "locked_until": None}


def inject_csrf():
    return dict(csrf_token=generate_csrf)


def check_session():
    if session.get("role") == "admin":
        token = session.get("session_token")
        if token:
            db = sqlite3.connect(DB_PATH)
            db.row_factory = sqlite3.Row
            row = db.execute("SELECT created_at FROM active_sessions WHERE session_token = ?", (token,)).fetchone()
            db.close()
            if not row:
                session.clear()
                return redirect(url_for("smartlock_login"))
            last = datetime.datetime.fromisoformat(row["created_at"])
            if (datetime.datetime.utcnow() - last).total_seconds() > SESSION_TIMEOUT:
                db2 = sqlite3.connect(DB_PATH)
                db2.execute("DELETE FROM active_sessions WHERE session_token = ?", (token,))
                db2.commit()
                db2.close()
                session.clear()
                return redirect(url_for("smartlock_login"))
    return None


def ensure_smartlock_cookies():
    if not request.path.startswith("/smartlock"):
        return None
    if request.endpoint == "static":
        return None
    if cookies_enabled_for_smartlock():
        if "_smartlock_cookie_probe" in request.args:
            args = request.args.to_dict(flat=True)
            args.pop("_smartlock_cookie_probe", None)
            query = urlencode(args)
            target = f"{request.path}?{query}" if query else request.path
            return redirect(target)
        return None
    if request.args.get("_smartlock_cookie_probe") == "1":
        return render_cookies_required()
    session["smartlock_cookies_probe"] = "ok"
    return redirect(build_cookie_probe_url())


def send_admin_magic_link(email, captcha_code):
    token = serializer.dumps(email, salt="admin-magic-login")
    link = url_for("smartlock_verify", token=token, _external=True)
    error = send_smartlock_email(
        {
            "from": get_mail_from_address(),
            "to": email,
            "subject": "Smart Lock — Admin Access 🔐",
            "html": f"<p>Click to access the admin panel. Expires in 5 minutes, single use.</p><p><a href='{link}'>{link}</a></p>",
        }
    )
    if error:
        return error
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    db = sqlite3.connect(DB_PATH)
    db.execute("INSERT OR REPLACE INTO match_numbers (token_hash, number) VALUES (?, ?)", (token_hash, captcha_code))
    db.commit()
    db.close()
    return None


def send_verification_link(new_email, captcha_code):
    token = serializer.dumps(new_email, salt="admin-email-change")
    link = url_for("smartlock_verify_email_change", token=token, _external=True)
    error = send_smartlock_email(
        {
            "from": get_mail_from_address(),
            "to": new_email,
            "subject": "Smart Lock — Verify new admin email ✉️",
            "html": f"<p>Click to verify. Expires in 5 minutes.</p><p><a href='{link}'>{link}</a></p>",
        }
    )
    if error:
        return error
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    db = sqlite3.connect(DB_PATH)
    db.execute("INSERT OR REPLACE INTO match_numbers (token_hash, number) VALUES (?, ?)", (token_hash, captcha_code))
    db.commit()
    db.close()
    return None


def send_smartlock_email(payload):
    resend.api_key = get_resend_api_key()
    if not payload.get("to"):
        return "Email sending failed: no destination email is configured."
    if not payload.get("from"):
        return "Email sending failed: MAIL_FROM is missing."
    if not resend.api_key:
        return "Email sending failed: RESEND_API_KEY is missing."
    try:
        resend.Emails.send(payload)
        return None
    except Exception as exc:
        current_app.logger.exception("Failed to send smart lock email")
        if "API key is invalid" in str(exc):
            return "Email sending failed: RESEND_API_KEY is invalid."
        return "Email sending failed. Check the mail configuration and try again."




def generate_passcode():
    db = sqlite3.connect(DB_PATH)
    try:
        while True:
            code = str(random.randint(100000, 999999))
            if not db.execute("SELECT 1 FROM users WHERE passcode = ?", (code,)).fetchone():
                return code
    finally:
        db.close()


def init_smartlock(app):
    init_smartlock_config(app.secret_key)
    app.teardown_appcontext(close_db)
    app.context_processor(inject_csrf)
    app.before_request(ensure_smartlock_cookies)
    app.before_request(check_session)
    @app.route("/smartlock/")
    def smartlock_index():
        if is_admin(): return redirect(url_for("smartlock_admin"))
        return redirect(url_for("smartlock_login"))
    
    @app.route("/smartlock/login", methods=["GET", "POST"])
    def smartlock_login():
        cooldown_key = actor_cooldown_key("admin_link_cooldown")
        remaining = cooldown_remaining(cooldown_key)
        captcha_code = session.get("admin_captcha_code")
        message = pop_ui_message("smartlock_login_message")
        if request.method == "POST":
            if remaining > 0:
                return render_page("smartlock/admin_login.html", page_name="Smart Lock — Access", admin_sent=bool(captcha_code),
                                              link_cooldown=remaining, captcha_code=captcha_code, message=message)
            captcha_code = str(random.randint(10, 99))
            error = send_admin_magic_link(get_admin_email(), captcha_code)
            if error:
                session.pop("admin_captcha_code", None)
                return render_page("smartlock/admin_login.html", page_name="Smart Lock — Access", admin_sent=False,
                                              link_cooldown=0, captcha_code=None, message=error)
            session["admin_captcha_code"] = captcha_code
            set_setting(cooldown_key, datetime.datetime.utcnow().isoformat())
            return render_page("smartlock/admin_login.html", page_name="Smart Lock — Access", admin_sent=True,
                                          link_cooldown=300, captcha_code=captcha_code)
        if remaining == 0 and captcha_code:
            session.pop("admin_captcha_code", None)
            captcha_code = None
        if is_admin():
            return redirect(url_for("smartlock_admin"))
        return render_page("smartlock/admin_login.html", page_name="Smart Lock — Access", admin_sent=bool(captcha_code),
                                      link_cooldown=remaining, captcha_code=captcha_code, message=message)
    
    @app.route("/smartlock/poll-status")
    def smartlock_poll_status():
        if is_admin(): return jsonify({"status": "logged_in"})
        return jsonify({"status": "waiting"})
    
    @app.route("/smartlock/verify")
    def smartlock_verify():
        token = request.args.get("token")
        try:
            serializer.loads(token, salt="admin-magic-login", max_age=300)
        except SignatureExpired:
            return render_page("smartlock/admin_login.html", page_name="Smart Lock — Access", message="Link expired ⏱️",
                                          admin_sent=False, link_cooldown=0, captcha_code=None)
        except BadSignature:
            return render_page("smartlock/admin_login.html", page_name="Smart Lock — Access", message="Invalid link 🚫",
                                          admin_sent=False, link_cooldown=0, captcha_code=None)
        db = get_db()
        if db.execute("SELECT 1 FROM used_tokens WHERE token = ?", (token,)).fetchone():
            return render_page("smartlock/admin_login.html", page_name="Smart Lock — Access", message="Link already used 🚫",
                                          admin_sent=False, link_cooldown=0, captcha_code=None)
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        db2 = sqlite3.connect(DB_PATH)
        db2.row_factory = sqlite3.Row
        row = db2.execute("SELECT number FROM match_numbers WHERE token_hash = ?", (token_hash,)).fetchone()
        db2.close()
        correct = row["number"] if row else None
        if not correct:
            return render_page("smartlock/admin_login.html", page_name="Smart Lock — Access", message="Session expired 💨",
                                          admin_sent=False, link_cooldown=0, captcha_code=None)
        options = {correct}
        while len(options) < 3:
            options.add(str(random.randint(10, 99)))
        options = list(options)
        random.shuffle(options)
        return render_page("smartlock/captcha.html", page_name="Smart Lock — Solve captcha", token=token, options=options,
                                      error=None, mode="login")
    
    @app.route('/smartlock/verify-captcha', methods=['POST'])
    def smartlock_verify_captcha():
        token = request.form.get("token")
        chosen = request.form.get("captcha_code")
        if not token or not chosen:
            return render_page("smartlock/admin_login.html", page_name="Smart Lock — Access", message="Invalid verification request 🚫",
                                          admin_sent=False, link_cooldown=0, captcha_code=None)
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        db2 = sqlite3.connect(DB_PATH)
        db2.row_factory = sqlite3.Row
        row = db2.execute("SELECT number FROM match_numbers WHERE token_hash = ?", (token_hash,)).fetchone()
        db2.close()
        correct = row["number"] if row else None
        if not correct or chosen != correct:
            log_attempt("admin_magic_link", method_id="captcha", success=False)
            db3 = sqlite3.connect(DB_PATH)
            db3.execute("DELETE FROM match_numbers WHERE token_hash = ?", (token_hash,))
            db3.commit()
            db3.close()
            set_setting(actor_cooldown_key("admin_link_cooldown"), datetime.datetime.utcnow().isoformat())
            session["smartlock_login_message"] = "Wrong captcha. Request a new link. 🚫"
            return redirect(url_for("smartlock_login"))
        db = get_db()
        if db.execute("SELECT 1 FROM used_tokens WHERE token = ?", (token,)).fetchone():
            return render_page("smartlock/admin_login.html", page_name="Smart Lock — Access", message="Link already used 🚫",
                                          admin_sent=False, link_cooldown=0, captcha_code=None)
        db.execute("INSERT INTO used_tokens (token) VALUES (?)", (token,))
        db.commit()
        log_attempt("admin_magic_link", method_id="captcha", success=True, user_name="admin")
        session.pop("admin_captcha_code", None)
        db3 = sqlite3.connect(DB_PATH)
        db3.execute("DELETE FROM match_numbers WHERE token_hash = ?", (token_hash,))
        db3.commit()
        db3.close()
        create_admin_session()
        return redirect(url_for("smartlock_admin"))
    
    # ── Add session (cross-device login) ─────────────────────────────────────────
    
    @app.route("/smartlock/add-session")
    def smartlock_add_session():
        if not is_admin(): return redirect(url_for("smartlock_login"))
        token = "".join(random.choices(string.ascii_uppercase + string.digits, k=8))
        captcha_code = str(random.randint(10, 99))
        db = get_db()
        db.execute("DELETE FROM join_tokens WHERE created_at < ?",
                   ((datetime.datetime.utcnow() - datetime.timedelta(minutes=5)).isoformat(),))
        db.execute("INSERT OR REPLACE INTO join_tokens (token, number) VALUES (?, ?)", (token, captcha_code))
        db.commit()
        join_url = url_for("smartlock_join", token=token, _external=True)
        return render_page("smartlock/add_session.html", page_name="Smart Lock — Add Session", captcha_code=captcha_code, token=token, join_url=join_url)
    
    @app.route("/smartlock/join/<token>")
    def smartlock_join(token):
        if is_admin():
            session["smartlock_admin_message"] = "This device already has an active session. Use another device or regenerate the link."
            return redirect(url_for("smartlock_admin"))
        db = sqlite3.connect(DB_PATH)
        db.row_factory = sqlite3.Row
        row = db.execute("SELECT * FROM join_tokens WHERE token = ?", (token,)).fetchone()
        db.close()
        if not row:
            return render_page("smartlock/admin_login.html", page_name="Smart Lock — Access", message="Join link expired or invalid 🚫",
                                          admin_sent=False, link_cooldown=0, captcha_code=None)
        created = datetime.datetime.fromisoformat(row["created_at"])
        if (datetime.datetime.utcnow() - created).total_seconds() > 300:
            db2 = sqlite3.connect(DB_PATH)
            db2.execute("DELETE FROM join_tokens WHERE token = ?", (token,))
            db2.commit()
            db2.close()
            return render_page("smartlock/admin_login.html", page_name="Smart Lock — Access", message="Join link expired ⏱️",
                                          admin_sent=False, link_cooldown=0, captcha_code=None)
        correct = row["number"]
        options = {correct}
        while len(options) < 3:
            options.add(str(random.randint(10, 99)))
        options = list(options)
        random.shuffle(options)
        return render_page("smartlock/captcha.html", page_name="Smart Lock — Solve captcha", token=token, options=options,
                                      error=None, mode="join")
    
    @app.route("/smartlock/join-captcha", methods=["POST"])
    def smartlock_join_captcha():
        if is_admin():
            session["smartlock_admin_message"] = "This device already has an active session. Use another device or regenerate the link."
            return redirect(url_for("smartlock_admin"))
        token = request.form.get("token")
        chosen = request.form.get("captcha_code")
        db = sqlite3.connect(DB_PATH)
        db.row_factory = sqlite3.Row
        row = db.execute("SELECT * FROM join_tokens WHERE token = ?", (token,)).fetchone()
        db.close()
        if not row:
            return render_page("smartlock/admin_login.html", page_name="Smart Lock — Access", message="Join link expired 🚫",
                                          admin_sent=False, link_cooldown=0, captcha_code=None)
        created = datetime.datetime.fromisoformat(row["created_at"])
        if (datetime.datetime.utcnow() - created).total_seconds() > 300:
            return render_page("smartlock/admin_login.html", page_name="Smart Lock — Access", message="Join link expired ⏱️",
                                          admin_sent=False, link_cooldown=0, captcha_code=None)
        if chosen != row["number"]:
            log_attempt("join_session", method_id="captcha", success=False)
            db3 = sqlite3.connect(DB_PATH)
            db3.execute("DELETE FROM join_tokens WHERE token = ?", (token,))
            db3.commit()
            db3.close()
            return render_page("smartlock/admin_login.html", page_name="Smart Lock — Access", message="Wrong captcha. Request a new link. 🚫",
                                          admin_sent=False, link_cooldown=0, captcha_code=None)
        db2 = sqlite3.connect(DB_PATH)
        db2.execute("DELETE FROM join_tokens WHERE token = ?", (token,))
        db2.commit()
        db2.close()
        log_attempt("join_session", method_id="captcha", success=True, user_name="admin")
        create_admin_session()
        return redirect(url_for("smartlock_admin"))
    
    @app.route("/smartlock/session/logout/<session_token>")
    def smartlock_session_logout(session_token):
        if not is_admin(): return redirect(url_for("smartlock_login"))
        db = get_db()
        db.execute("DELETE FROM active_sessions WHERE session_token = ?", (session_token,))
        db.commit()
        if session.get("session_token") == session_token:
            session.clear()
            return redirect(url_for("smartlock_login"))
        return redirect(url_for("smartlock_admin"))
    
    @app.route("/smartlock/session/logout-all")
    def smartlock_session_logout_all():
        if not is_admin(): return redirect(url_for("smartlock_login"))
        current = session.get("session_token")
        db = get_db()
        db.execute("DELETE FROM active_sessions WHERE session_token != ?", (current,))
        db.commit()
        return redirect(url_for("smartlock_admin"))
    
    # ── Email change ──────────────────────────────────────────────────────────────
    
    @app.route("/smartlock/change-email", methods=["POST"])
    def smartlock_change_email():
        if not is_admin(): return redirect(url_for("smartlock_login"))
        if cooldown_remaining("admin_email_change_cooldown") > 0:
            return redirect(url_for("smartlock_admin"))
        new_email = bleach.clean(request.form.get("new_email", "").strip().lower(), tags=[], strip=True)[:200]
        if not new_email: return redirect(url_for("smartlock_admin"))
        now = datetime.datetime.utcnow().isoformat()
        captcha_code = str(random.randint(10, 99))
        error = send_verification_link(new_email, captcha_code)
        if error:
            session.pop("email_change_captcha_code", None)
            return render_page("smartlock/admin_panel.html", page_name="Smart Lock — Control Room", users=get_db().execute("SELECT * FROM users ORDER BY created_at DESC").fetchall(),
                                          admin_email=get_admin_email(), pending=get_pending_email(),
                                          cooldown_remaining=cooldown_remaining("admin_email_change_cooldown"),
                                          logs=get_db().execute("SELECT * FROM login_logs ORDER BY created_at DESC LIMIT 100").fetchall(),
                                          sessions=get_active_sessions(), current_token=session.get("session_token", ""),
                                          current_remaining=next((s["remaining"] for s in get_active_sessions() if s["session_token"] == session.get("session_token", "")), 0),
                                          email_error=error)
        session["email_change_captcha_code"] = captcha_code
        db = get_db()
        db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('pending_admin_email', ?)", (new_email,))
        db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('pending_admin_email_sent_at', ?)", (now,))
        db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('admin_email_change_cooldown', ?)", (now,))
        db.commit()
        return redirect(url_for("smartlock_email_pending"))
    
    @app.route("/smartlock/change-email/resend")
    def smartlock_resend_verification():
        if not is_admin(): return redirect(url_for("smartlock_login"))
        pending = get_pending_email()
        if not pending: return redirect(url_for("smartlock_admin"))
        now = datetime.datetime.utcnow().isoformat()
        captcha_code = str(random.randint(10, 99))
        error = send_verification_link(pending, captcha_code)
        if error:
            return render_page("smartlock/email_pending.html", page_name="Smart Lock — Verify Email", pending_email=pending,
                                          sent_at=get_pending_sent_at(), error=error,
                                          captcha_code=session.get("email_change_captcha_code"))
        session["email_change_captcha_code"] = captcha_code
        set_setting("pending_admin_email_sent_at", now)
        return redirect(url_for("smartlock_email_pending"))
    
    @app.route("/smartlock/change-email/cancel")
    def smartlock_cancel_email_change():
        if not is_admin(): return redirect(url_for("smartlock_login"))
        db = get_db()
        db.execute("DELETE FROM settings WHERE key = 'pending_admin_email'")
        db.execute("DELETE FROM settings WHERE key = 'pending_admin_email_sent_at'")
        db.commit()
        return redirect(url_for("smartlock_admin"))
    
    @app.route("/smartlock/change-email/pending")
    def smartlock_email_pending():
        if not is_admin(): return redirect(url_for("smartlock_login"))
        pending = get_pending_email()
        sent_at = get_pending_sent_at()
        if not pending: return redirect(url_for("smartlock_admin"))
        captcha_code = session.get("email_change_captcha_code")
        return render_page("smartlock/email_pending.html", page_name="Smart Lock — Verify Email", pending_email=pending,
                                      sent_at=sent_at, error=None, captcha_code=captcha_code)
    
    @app.route("/smartlock/verify-email-change")
    def smartlock_verify_email_change():
        token = request.args.get("token")
        try:
            new_email = serializer.loads(token, salt="admin-email-change", max_age=300)
        except SignatureExpired:
            return render_page("smartlock/email_pending.html", page_name="Smart Lock — Verify Email", pending_email=get_pending_email(),
                                          sent_at=get_pending_sent_at(), error="Link expired ⏱️", captcha_code=None)
        except BadSignature:
            return render_page("smartlock/email_pending.html", page_name="Smart Lock — Verify Email", pending_email=get_pending_email(),
                                          sent_at=get_pending_sent_at(), error="Invalid link 🚫", captcha_code=None)
        pending = get_pending_email()
        if not pending or pending != new_email: return redirect(url_for("smartlock_admin"))
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        db2 = sqlite3.connect(DB_PATH)
        db2.row_factory = sqlite3.Row
        row = db2.execute("SELECT number FROM match_numbers WHERE token_hash = ?", (token_hash,)).fetchone()
        db2.close()
        correct = row["number"] if row else None
        if not correct:
            return render_page("smartlock/email_pending.html", page_name="Smart Lock — Verify Email", pending_email=pending,
                                          sent_at=get_pending_sent_at(), error="Session expired 💨", captcha_code=None)
        options = {correct}
        while len(options) < 3:
            options.add(str(random.randint(10, 99)))
        options = list(options)
        random.shuffle(options)
        return render_page("smartlock/captcha.html", page_name="Smart Lock — Solve captcha", token=token, options=options,
                                      error=None, mode="email_change")
    
    @app.route("/smartlock/verify-email-captcha", methods=["POST"])
    def smartlock_verify_email_captcha():
        token = request.form.get("token")
        chosen = request.form.get("captcha_code")
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        db2 = sqlite3.connect(DB_PATH)
        db2.row_factory = sqlite3.Row
        row = db2.execute("SELECT number FROM match_numbers WHERE token_hash = ?", (token_hash,)).fetchone()
        db2.close()
        correct = row["number"] if row else None
        if not correct or chosen != correct:
            db3 = sqlite3.connect(DB_PATH)
            db3.execute("DELETE FROM match_numbers WHERE token_hash = ?", (token_hash,))
            db3.commit()
            db3.close()
            return render_page("smartlock/email_pending.html", page_name="Smart Lock — Verify Email", pending_email=get_pending_email(),
                                          sent_at=get_pending_sent_at(), error="Wrong captcha. Request a new link. 🚫", captcha_code=None)
        try:
            new_email = serializer.loads(token, salt="admin-email-change", max_age=300)
        except:
            return render_page("smartlock/email_pending.html", page_name="Smart Lock — Verify Email", pending_email=get_pending_email(),
                                          sent_at=get_pending_sent_at(), error="Link expired ⏱️", captcha_code=None)
        db = get_db()
        pending = get_pending_email()
        if not pending or pending != new_email: return redirect(url_for("smartlock_admin"))
        db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('admin_email', ?)", (new_email,))
        db.execute("DELETE FROM settings WHERE key = 'pending_admin_email'")
        db.execute("DELETE FROM settings WHERE key = 'pending_admin_email_sent_at'")
        db.commit()
        session.pop("email_change_captcha_code", None)
        db3 = sqlite3.connect(DB_PATH)
        db3.execute("DELETE FROM match_numbers WHERE token_hash = ?", (token_hash,))
        db3.commit()
        db3.close()
        return redirect(url_for("smartlock_admin"))
    
    # ── Admin panel ───────────────────────────────────────────────────────────────
    
    @app.route("/smartlock/admin")
    def smartlock_admin():
        if not is_admin(): return redirect(url_for("smartlock_login"))
        users = get_db().execute("SELECT * FROM users ORDER BY created_at DESC").fetchall()
        admin_email = get_admin_email()
        pending = get_pending_email()
        email_cd = cooldown_remaining("admin_email_change_cooldown")
        logs = get_db().execute("SELECT * FROM login_logs ORDER BY created_at DESC LIMIT 100").fetchall()
        sessions = get_active_sessions()
        current_token = session.get("session_token", "")
        current_remaining = next((s["remaining"] for s in sessions if s["session_token"] == current_token), 0)
        log_entries = build_log_entries(logs, sessions, current_token)
        panel_message = pop_ui_message("smartlock_admin_message")
        return render_page("smartlock/admin_panel.html", page_name="Smart Lock — Control Room", users=users, admin_email=admin_email,
                                      pending=pending, cooldown_remaining=email_cd,
                                      logs=logs, sessions=sessions, log_entries=log_entries, current_token=current_token,
                                      current_remaining=current_remaining, panel_message=panel_message)
    
    @app.route("/smartlock/users/new")
    def smartlock_new_user():
        if not is_admin(): return redirect(url_for("smartlock_login"))
        draft_user = {
            "id": None,
            "name": "",
            "passcode": None,
            "rfid_enabled": 0,
            "rfid_id": "",
            "fingerprint_enabled": 0,
            "fingerprint_id": "",
        }
        return render_page("smartlock/admin_user_detail.html", page_name="New User — Friedutch Plus",
                                      user=draft_user, is_new_user=True, error=None)

    @app.route("/smartlock/users/add", methods=["POST"])
    def smartlock_add_user():
        return redirect(url_for("smartlock_new_user"))

    @app.route("/smartlock/users/create", methods=["POST"])
    def smartlock_create_user():
        if not is_admin(): return redirect(url_for("smartlock_login"))
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
            return render_page("smartlock/admin_user_detail.html", page_name="New User — Friedutch Plus",
                                          user=draft_user, is_new_user=True, error="Enter a user name before creating this profile.")
        db = get_db()
        if db.execute("SELECT 1 FROM users WHERE name = ?", (name,)).fetchone():
            return render_page("smartlock/admin_user_detail.html", page_name="New User — Friedutch Plus",
                                          user=draft_user, is_new_user=True, error="A user with that name already exists.")
        cursor = db.execute(
            """
            INSERT INTO users (name, passcode, rfid_enabled, rfid_id, fingerprint_enabled, fingerprint_id)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (name, generate_passcode(), rfid_enabled, rfid_id or None, fingerprint_enabled, fingerprint_id or None),
        )
        db.commit()
        return redirect(url_for("smartlock_user_detail", user_id=cursor.lastrowid))
    
    @app.route("/smartlock/users/delete/<int:user_id>")
    def smartlock_delete_user(user_id):
        if not is_admin(): return redirect(url_for("smartlock_login"))
        get_db().execute("DELETE FROM users WHERE id = ?", (user_id,))
        get_db().commit()
        return redirect(url_for("smartlock_admin"))
    
    @app.route("/smartlock/user/<int:user_id>")
    def smartlock_user_detail(user_id):
        if not is_admin(): return redirect(url_for("smartlock_login"))
        user = get_db().execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return render_page("smartlock/admin_user_detail.html", page_name=f"{user['name']} — Friedutch Plus", user=user,
                                      is_new_user=False, error=None)
    
    @app.route("/smartlock/user/<int:user_id>/toggle/<method>")
    def smartlock_toggle_method(user_id, method):
        if not is_admin(): return redirect(url_for("smartlock_login"))
        if method not in ("rfid", "fingerprint"): return redirect(url_for("smartlock_user_detail", user_id=user_id))
        col = f"{method}_enabled"
        db = get_db()
        user = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        db.execute(f"UPDATE users SET {col} = ? WHERE id = ?", (0 if user[col] else 1, user_id))
        db.commit()
        return redirect(url_for("smartlock_user_detail", user_id=user_id))
    
    @app.route("/smartlock/user/<int:user_id>/set/<method>", methods=["POST"])
    def smartlock_set_method_id(user_id, method):
        if not is_admin(): return redirect(url_for("smartlock_login"))
        if method not in ("rfid", "fingerprint"): return redirect(url_for("smartlock_user_detail", user_id=user_id))
        value = sanitize(request.form.get("id_value", ""))
        get_db().execute(f"UPDATE users SET {method}_id = ? WHERE id = ?", (value or None, user_id))
        get_db().commit()
        return redirect(url_for("smartlock_user_detail", user_id=user_id))
    
    @app.route("/smartlock/logout")
    def smartlock_logout():
        token = session.get("session_token")
        if token:
            db = sqlite3.connect(DB_PATH)
            db.execute("DELETE FROM active_sessions WHERE session_token = ?", (token,))
            db.commit()
            db.close()
        session.clear()
        return redirect(url_for("smartlock_login"))
