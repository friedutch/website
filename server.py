import os
import sqlite3
import random
import string
import resend
import hashlib
import re as _re
import datetime
import uuid
import bleach
from collections import defaultdict
from flask import Flask, request, redirect, url_for, session, render_template_string, g, jsonify
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature
from dotenv import load_dotenv
from flask_wtf.csrf import CSRFProtect, generate_csrf
import subprocess
import hmac

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY")
csrf = CSRFProtect(app)

app.config.update(
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
)

resend.api_key = os.getenv("RESEND_API_KEY")
MAIL_FROM_ADDRESS = os.getenv("MAIL_FROM")
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "projects/smartlock/smartlock.db")
serializer = URLSafeTimedSerializer(app.secret_key)
SESSION_TIMEOUT = 3600

# ── DB ────────────────────────────────────────────────────────────────────────

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close_db(e=None):
    db = g.pop("db", None)
    if db: db.close()

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
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS active_sessions (
        session_token TEXT PRIMARY KEY,
        ip TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        last_active TEXT DEFAULT CURRENT_TIMESTAMP
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

def get_admin_email():     return get_setting("admin_email")
def get_pending_email():   return get_setting("pending_admin_email")
def get_pending_sent_at(): return get_setting("pending_admin_email_sent_at")

def cooldown_remaining(key, seconds=300):
    ts = get_setting(key)
    if not ts: return 0
    elapsed = (datetime.datetime.utcnow() - datetime.datetime.fromisoformat(ts)).total_seconds()
    return max(0, int(seconds - elapsed))

def is_admin(): return session.get("role") == "admin"

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

def get_client_ip():
    return request.headers.get("CF-Connecting-IP") or request.remote_addr

def sanitize(value, max_length=100):
    if not value: return ""
    return bleach.clean(value.strip(), tags=[], strip=True)[:max_length]

def log_attempt(method, method_id=None, success=False, user_name=None):
    ip = get_client_ip()
    icon = get_device_icon()
    db = sqlite3.connect(DB_PATH)
    db.execute(
        "INSERT INTO login_logs (method, method_id, success, user_name, ip, user_agent) VALUES (?, ?, ?, ?, ?, ?)",
        (method, method_id, 1 if success else 0, user_name, ip, icon)
    )
    db.commit()
    db.close()

# ── Sessions ──────────────────────────────────────────────────────────────────

def create_admin_session():
    token = str(uuid.uuid4())
    ip = get_client_ip()
    now = datetime.datetime.utcnow().isoformat()
    ua = request.headers.get("User-Agent", "")
    icon = get_device_icon()
    db = sqlite3.connect(DB_PATH)
    db.execute("INSERT INTO active_sessions (session_token, ip, created_at, last_active, user_agent) VALUES (?, ?, ?, ?, ?)",
               (token, ip, now, now, icon))
    db.commit()
    db.close()
    session["role"] = "admin"
    session["session_token"] = token
    session["last_active"] = now
    session.pop("admin_match_number", None)
    # Cleanup on every login
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
        elapsed = (now - created).total_seconds()
        remaining = max(0, int(SESSION_TIMEOUT - elapsed))
        m, sec = divmod(remaining, 60)
        result.append({
            "session_token": s["session_token"],
            "ip": s["ip"],
            "created_at": s["created_at"][:19].replace("T", " "),
            "remaining": remaining,
            "remaining_fmt": f"{m}:{sec:02d}",
            "expired": remaining == 0,
            "icon": s["user_agent"] if s["user_agent"] else "🌐",
        })
    return result

# Brute force
_login_attempts = defaultdict(lambda: {"attempts": 0, "locked_until": None})

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

@app.context_processor
def inject_csrf():
    return dict(csrf_token=generate_csrf)

@app.before_request
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

def send_admin_magic_link(email, match_number):
    token = serializer.dumps(email, salt="admin-magic-login")
    link = url_for("smartlock_verify", token=token, _external=True)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    db = sqlite3.connect(DB_PATH)
    db.execute("INSERT OR REPLACE INTO match_numbers (token_hash, number) VALUES (?, ?)", (token_hash, match_number))
    db.commit()
    db.close()
    resend.Emails.send({
        "from": MAIL_FROM_ADDRESS,
        "to": email,
        "subject": "Smart Lock — Admin Access 🔐",
        "html": f"<p>Click to access the admin panel. Expires in 5 minutes, single use.</p><p><a href='{link}'>{link}</a></p>"
    })

def send_verification_link(new_email, match_number):
    token = serializer.dumps(new_email, salt="admin-email-change")
    link = url_for("smartlock_verify_email_change", token=token, _external=True)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    db = sqlite3.connect(DB_PATH)
    db.execute("INSERT OR REPLACE INTO match_numbers (token_hash, number) VALUES (?, ?)", (token_hash, match_number))
    db.commit()
    db.close()
    resend.Emails.send({
        "from": MAIL_FROM_ADDRESS,
        "to": new_email,
        "subject": "Smart Lock — Verify new admin email ✉️",
        "html": f"<p>Click to verify. Expires in 5 minutes.</p><p><a href='{link}'>{link}</a></p>"
    })

# ── ROUTES ────────────────────────────────────────────────────────────────────

@app.route("/deploy", methods=["POST"])
@csrf.exempt
def deploy():
    sig = request.headers.get("X-Hub-Signature-256", "")
    secret = os.getenv("GITHUB_WEBHOOK_SECRET", "").encode()
    body = request.get_data()
    expected = "sha256=" + hmac.new(secret, body, "sha256").hexdigest()
    if not hmac.compare_digest(sig, expected):
        return jsonify({"error": "unauthorized"}), 401
    subprocess.Popen(
        ["/bin/bash", "/Users/administrator/Sites/friedutch-app/deploy.sh"],
        stdout=open("/tmp/deploy.log", "w"),
        stderr=subprocess.STDOUT
    )
    return jsonify({"status": "deploying"}), 200

@app.route("/")
def home():
    return render_template_string(HOME_PAGE)

@app.route("/smartlock/")
def smartlock_index():
    if is_admin(): return redirect(url_for("smartlock_admin"))
    return redirect(url_for("smartlock_login"))

@app.route("/smartlock/login", methods=["GET", "POST"])
def smartlock_login():
    remaining = cooldown_remaining("admin_link_cooldown")
    match_number = session.get("admin_match_number")
    if request.method == "POST":
        if remaining > 0:
            return render_template_string(ADMIN_LOGIN_PAGE, admin_sent=bool(match_number),
                                          link_cooldown=remaining, match_number=match_number)
        match_number = str(random.randint(10, 99))
        session["admin_match_number"] = match_number
        send_admin_magic_link(get_admin_email(), match_number)
        set_setting("admin_link_cooldown", datetime.datetime.utcnow().isoformat())
        return render_template_string(ADMIN_LOGIN_PAGE, admin_sent=True,
                                      link_cooldown=300, match_number=match_number)
    if remaining == 0 and match_number:
        session.pop("admin_match_number", None)
        match_number = None
    if is_admin():
        return redirect(url_for("smartlock_admin"))
    return render_template_string(ADMIN_LOGIN_PAGE, admin_sent=bool(match_number),
                                  link_cooldown=remaining, match_number=match_number)

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
        return render_template_string(ADMIN_LOGIN_PAGE, message="Link expired ⏱️",
                                      admin_sent=False, link_cooldown=0, match_number=None)
    except BadSignature:
        return render_template_string(ADMIN_LOGIN_PAGE, message="Invalid link 🚫",
                                      admin_sent=False, link_cooldown=0, match_number=None)
    db = get_db()
    if db.execute("SELECT 1 FROM used_tokens WHERE token = ?", (token,)).fetchone():
        return render_template_string(ADMIN_LOGIN_PAGE, message="Link already used 🚫",
                                      admin_sent=False, link_cooldown=0, match_number=None)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    db2 = sqlite3.connect(DB_PATH)
    db2.row_factory = sqlite3.Row
    row = db2.execute("SELECT number FROM match_numbers WHERE token_hash = ?", (token_hash,)).fetchone()
    db2.close()
    correct = row["number"] if row else None
    if not correct:
        return render_template_string(ADMIN_LOGIN_PAGE, message="Session expired 💨",
                                      admin_sent=False, link_cooldown=0, match_number=None)
    options = {correct}
    while len(options) < 3:
        options.add(str(random.randint(10, 99)))
    options = list(options)
    random.shuffle(options)
    return render_template_string(NUMBER_MATCH_PAGE, token=token, options=options,
                                  error=None, mode="login")

@app.route('/smartlock/verify-number', methods=['GET', 'POST'])
def smartlock_verify_number():
    token = request.form.get("token")
    chosen = request.form.get("number")
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    db2 = sqlite3.connect(DB_PATH)
    db2.row_factory = sqlite3.Row
    row = db2.execute("SELECT number FROM match_numbers WHERE token_hash = ?", (token_hash,)).fetchone()
    db2.close()
    correct = row["number"] if row else None
    if not correct or chosen != correct:
        log_attempt("admin_magic_link", method_id="number_match", success=False)
        db3 = sqlite3.connect(DB_PATH)
        db3.execute("DELETE FROM match_numbers WHERE token_hash = ?", (token_hash,))
        db3.commit()
        db3.close()
        return render_template_string(ADMIN_LOGIN_PAGE, message="Wrong number. Request a new link. 🚫",
                                      admin_sent=False, link_cooldown=1, match_number=None)
    db = get_db()
    if db.execute("SELECT 1 FROM used_tokens WHERE token = ?", (token,)).fetchone():
        return render_template_string(ADMIN_LOGIN_PAGE, message="Link already used 🚫",
                                      admin_sent=False, link_cooldown=0, match_number=None)
    db.execute("INSERT INTO used_tokens (token) VALUES (?)", (token,))
    db.commit()
    log_attempt("admin_magic_link", method_id="number_match", success=True, user_name="admin")
    session.pop("admin_match_number", None)
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
    number = str(random.randint(10, 99))
    db = get_db()
    db.execute("DELETE FROM join_tokens WHERE created_at < ?",
               ((datetime.datetime.utcnow() - datetime.timedelta(minutes=5)).isoformat(),))
    db.execute("INSERT OR REPLACE INTO join_tokens (token, number) VALUES (?, ?)", (token, number))
    db.commit()
    join_url = url_for("smartlock_join", token=token, _external=True)
    return render_template_string(ADD_SESSION_PAGE, number=number, token=token, join_url=join_url)

@app.route("/smartlock/join/<token>")
def smartlock_join(token):
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    row = db.execute("SELECT * FROM join_tokens WHERE token = ?", (token,)).fetchone()
    db.close()
    if not row:
        return render_template_string(ADMIN_LOGIN_PAGE, message="Join link expired or invalid 🚫",
                                      admin_sent=False, link_cooldown=0, match_number=None)
    created = datetime.datetime.fromisoformat(row["created_at"])
    if (datetime.datetime.utcnow() - created).total_seconds() > 300:
        db2 = sqlite3.connect(DB_PATH)
        db2.execute("DELETE FROM join_tokens WHERE token = ?", (token,))
        db2.commit()
        db2.close()
        return render_template_string(ADMIN_LOGIN_PAGE, message="Join link expired ⏱️",
                                      admin_sent=False, link_cooldown=0, match_number=None)
    correct = row["number"]
    options = {correct}
    while len(options) < 3:
        options.add(str(random.randint(10, 99)))
    options = list(options)
    random.shuffle(options)
    return render_template_string(NUMBER_MATCH_PAGE, token=token, options=options,
                                  error=None, mode="join")

@app.route("/smartlock/join-verify", methods=["POST"])
def smartlock_join_verify():
    token = request.form.get("token")
    chosen = request.form.get("number")
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    row = db.execute("SELECT * FROM join_tokens WHERE token = ?", (token,)).fetchone()
    db.close()
    if not row:
        return render_template_string(ADMIN_LOGIN_PAGE, message="Join link expired 🚫",
                                      admin_sent=False, link_cooldown=0, match_number=None)
    created = datetime.datetime.fromisoformat(row["created_at"])
    if (datetime.datetime.utcnow() - created).total_seconds() > 300:
        return render_template_string(ADMIN_LOGIN_PAGE, message="Join link expired ⏱️",
                                      admin_sent=False, link_cooldown=0, match_number=None)
    if chosen != row["number"]:
        log_attempt("join_session", method_id="number_match", success=False)
        db3 = sqlite3.connect(DB_PATH)
        db3.execute("DELETE FROM join_tokens WHERE token = ?", (token,))
        db3.commit()
        db3.close()
        return render_template_string(ADMIN_LOGIN_PAGE, message="Wrong number. Request a new link. 🚫",
                                      admin_sent=False, link_cooldown=0, match_number=None)
    db2 = sqlite3.connect(DB_PATH)
    db2.execute("DELETE FROM join_tokens WHERE token = ?", (token,))
    db2.commit()
    db2.close()
    log_attempt("join_session", method_id="number_match", success=True, user_name="admin")
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
    match_number = str(random.randint(10, 99))
    session["email_change_match_number"] = match_number
    db = get_db()
    db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('pending_admin_email', ?)", (new_email,))
    db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('pending_admin_email_sent_at', ?)", (now,))
    db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('admin_email_change_cooldown', ?)", (now,))
    db.commit()
    send_verification_link(new_email, match_number)
    return redirect(url_for("smartlock_email_pending"))

@app.route("/smartlock/change-email/resend")
def smartlock_resend_verification():
    if not is_admin(): return redirect(url_for("smartlock_login"))
    pending = get_pending_email()
    if not pending: return redirect(url_for("smartlock_admin"))
    now = datetime.datetime.utcnow().isoformat()
    match_number = str(random.randint(10, 99))
    session["email_change_match_number"] = match_number
    set_setting("pending_admin_email_sent_at", now)
    send_verification_link(pending, match_number)
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
    match_number = session.get("email_change_match_number")
    return render_template_string(EMAIL_PENDING_PAGE, pending_email=pending,
                                  sent_at=sent_at, error=None, match_number=match_number)

@app.route("/smartlock/verify-email-change")
def smartlock_verify_email_change():
    token = request.args.get("token")
    try:
        new_email = serializer.loads(token, salt="admin-email-change", max_age=300)
    except SignatureExpired:
        return render_template_string(EMAIL_PENDING_PAGE, pending_email=get_pending_email(),
                                      sent_at=get_pending_sent_at(), error="Link expired ⏱️", match_number=None)
    except BadSignature:
        return render_template_string(EMAIL_PENDING_PAGE, pending_email=get_pending_email(),
                                      sent_at=get_pending_sent_at(), error="Invalid link 🚫", match_number=None)
    pending = get_pending_email()
    if not pending or pending != new_email: return redirect(url_for("smartlock_admin"))
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    db2 = sqlite3.connect(DB_PATH)
    db2.row_factory = sqlite3.Row
    row = db2.execute("SELECT number FROM match_numbers WHERE token_hash = ?", (token_hash,)).fetchone()
    db2.close()
    correct = row["number"] if row else None
    if not correct:
        return render_template_string(EMAIL_PENDING_PAGE, pending_email=pending,
                                      sent_at=get_pending_sent_at(), error="Session expired 💨", match_number=None)
    options = {correct}
    while len(options) < 3:
        options.add(str(random.randint(10, 99)))
    options = list(options)
    random.shuffle(options)
    return render_template_string(NUMBER_MATCH_PAGE, token=token, options=options,
                                  error=None, mode="email_change")

@app.route("/smartlock/verify-email-number", methods=["POST"])
def smartlock_verify_email_number():
    token = request.form.get("token")
    chosen = request.form.get("number")
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
        return render_template_string(EMAIL_PENDING_PAGE, pending_email=get_pending_email(),
                                      sent_at=get_pending_sent_at(), error="Wrong number. Request a new link. 🚫", match_number=None)
    try:
        new_email = serializer.loads(token, salt="admin-email-change", max_age=300)
    except:
        return render_template_string(EMAIL_PENDING_PAGE, pending_email=get_pending_email(),
                                      sent_at=get_pending_sent_at(), error="Link expired ⏱️", match_number=None)
    db = get_db()
    pending = get_pending_email()
    if not pending or pending != new_email: return redirect(url_for("smartlock_admin"))
    db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('admin_email', ?)", (new_email,))
    db.execute("DELETE FROM settings WHERE key = 'pending_admin_email'")
    db.execute("DELETE FROM settings WHERE key = 'pending_admin_email_sent_at'")
    db.commit()
    session.pop("email_change_match_number", None)
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
    return render_template_string(ADMIN_PANEL, users=users, admin_email=admin_email,
                                  pending=pending, cooldown_remaining=email_cd,
                                  logs=logs, sessions=sessions, current_token=current_token,
                                  current_remaining=current_remaining)

@app.route("/smartlock/users/add", methods=["POST"])
def smartlock_add_user():
    if not is_admin(): return redirect(url_for("smartlock_login"))
    name = sanitize(request.form.get("name", ""))
    if name:
        if not get_db().execute("SELECT 1 FROM users WHERE name = ?", (name,)).fetchone():
            get_db().execute("INSERT INTO users (name, passcode) VALUES (?, ?)", (name, generate_passcode()))
            get_db().commit()
    return redirect(url_for("smartlock_admin"))

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
    return render_template_string(ADMIN_USER_DETAIL, user=user)

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

def generate_passcode():
    db = sqlite3.connect(DB_PATH)
    while True:
        code = str(random.randint(100000, 999999))
        if not db.execute("SELECT 1 FROM users WHERE passcode = ?", (code,)).fetchone():
            db.close()
            return code

# ── SHARED STYLES ─────────────────────────────────────────────────────────────

BASE_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Nunito:wght@400;600;700;800;900&family=Nunito+Sans:wght@400;600;700&display=swap');

*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

:root {
  --pink:    #FF3CAC;
  --purple:  #784BA0;
  --blue:    #2B86C5;
  --cyan:    #00D2FF;
  --green:   #00C882;
  --yellow:  #FFD60A;
  --orange:  #FF6B35;
  --radius:  20px;
  --radius-sm: 14px;
  --radius-xs: 10px;
}

[data-theme="light"] {
  --bg:       #F0F0FF;
  --surface:  #FFFFFF;
  --surface2: #F5F5FF;
  --card:     #FFFFFF;
  --border:   rgba(0,0,0,0.08);
  --text:     #1A1A2E;
  --text2:    #555570;
  --text3:    #9090B0;
  --shadow:   rgba(120,75,160,0.12);
  --green:    #00966A;
}

[data-theme="dark"] {
  --bg:       #0F0F1A;
  --surface:  #1A1A2E;
  --surface2: #16213E;
  --card:     #1E1E32;
  --border:   rgba(255,255,255,0.08);
  --text:     #F0F0FF;
  --text2:    #A0A0C0;
  --text3:    #606080;
  --shadow:   rgba(0,0,0,0.4);
}

html, body {
  font-family: 'Nunito', sans-serif;
  background: var(--bg);
  color: var(--text);
  min-height: 100vh;
  transition: background 0.3s, color 0.3s;
}

a { text-decoration: none; color: inherit; }

.theme-toggle {
  position: fixed;
  top: 16px; right: 16px;
  z-index: 1000;
  background: var(--surface);
  border: 2px solid var(--border);
  border-radius: 50px;
  padding: 8px 16px;
  font-size: 14px;
  font-weight: 700;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 6px;
  box-shadow: 0 4px 20px var(--shadow);
  color: var(--text);
  transition: all 0.2s;
  font-family: 'Nunito', sans-serif;
}
.theme-toggle:hover { transform: scale(1.05); }

.app-input {
  background: var(--surface2);
  border: 2px solid var(--border);
  border-radius: var(--radius-xs);
  color: var(--text);
  font-family: 'Nunito', sans-serif;
  font-size: 15px;
  font-weight: 600;
  padding: 12px 16px;
  outline: none;
  transition: all 0.2s;
  width: 100%;
}
.app-input:focus { border-color: var(--pink); box-shadow: 0 0 0 3px rgba(255,60,172,0.12); }
.app-input::placeholder { color: var(--text3); }

.big-btn {
  width: 100%;
  padding: 18px;
  border-radius: var(--radius-sm);
  border: none;
  font-family: 'Nunito', sans-serif;
  font-size: 18px;
  font-weight: 900;
  cursor: pointer;
  transition: all 0.2s;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  -webkit-background-clip: padding-box;
  background-clip: padding-box;
}
.big-btn:active { transform: scale(0.98); }
.big-btn:disabled { opacity: 0.3; pointer-events: none; cursor: not-allowed; box-shadow: none; }

.btn-primary {
  background: linear-gradient(135deg, var(--pink), var(--purple));
  color: white;
  box-shadow: 0 6px 24px rgba(255,60,172,0.45);
}
.btn-primary:hover { box-shadow: 0 8px 32px rgba(255,60,172,0.6); transform: translateY(-2px); }
.btn-ghost {
  background: var(--surface2);
  color: var(--text2);
  border: 2px solid var(--border);
}
.btn-ghost:hover { border-color: var(--pink); color: var(--pink); }

.sm-btn {
  padding: 12px 20px;
  border-radius: var(--radius-xs);
  border: none;
  font-family: 'Nunito', sans-serif;
  font-size: 14px;
  font-weight: 800;
  cursor: pointer;
  white-space: nowrap;
  transition: all 0.2s;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  -webkit-background-clip: padding-box;
  background-clip: padding-box;
}
.sm-btn:active { transform: scale(0.97); }
.sm-pink  { background: linear-gradient(135deg, var(--pink), var(--purple)); color: white; box-shadow: 0 4px 16px rgba(255,60,172,0.35); }
.sm-cyan  { background: linear-gradient(135deg, var(--cyan), var(--blue));   color: white; box-shadow: 0 4px 16px rgba(0,210,255,0.3); }
.sm-green { background: linear-gradient(135deg, var(--green), var(--cyan));  color: #0A2A20; box-shadow: 0 4px 16px rgba(0,200,130,0.3); }
.sm-orange{ background: linear-gradient(135deg, var(--orange), var(--yellow)); color: white; box-shadow: 0 4px 16px rgba(255,107,53,0.3); }
.sm-ghost { background: var(--surface2); color: var(--text2); border: 2px solid var(--border); box-shadow: none; }
.sm-ghost:hover { border-color: var(--orange); color: var(--orange); }

.zone {
  border-radius: var(--radius);
  padding: 20px;
  margin-bottom: 16px;
  border: 2px solid transparent;
}
.zone-pink   { background: linear-gradient(135deg, rgba(255,60,172,0.07), rgba(120,75,160,0.05)); border-color: rgba(255,60,172,0.15); }
.zone-cyan   { background: linear-gradient(135deg, rgba(0,210,255,0.07), rgba(43,134,197,0.05));  border-color: rgba(0,210,255,0.15); }
.zone-green  { background: linear-gradient(135deg, rgba(0,200,130,0.07), rgba(0,210,255,0.04));   border-color: rgba(0,200,130,0.15); }
.zone-orange { background: linear-gradient(135deg, rgba(255,107,53,0.07), rgba(255,214,10,0.04)); border-color: rgba(255,107,53,0.15); }

.zone-title {
  font-size: 13px;
  font-weight: 900;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  margin-bottom: 16px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.zone-title-left { display: flex; align-items: center; gap: 8px; }

.field-row { display: flex; gap: 10px; margin-bottom: 14px; }
.field-row .app-input { flex: 1; }

.chip {
  font-size: 10px;
  font-weight: 800;
  padding: 3px 9px;
  border-radius: 50px;
  letter-spacing: 0.06em;
}
.chip-on  { background: linear-gradient(135deg, rgba(0,200,130,0.15), rgba(0,210,255,0.1)); color: var(--green); border: 1px solid rgba(0,200,130,0.3); }
.chip-off { background: var(--surface2); color: var(--text3); border: 1px solid var(--border); }

.msg-err { font-size: 13px; font-weight: 700; color: var(--orange); margin-top: 12px; text-align: center; }
"""

THEME_JS = """
function getSystemTheme(){return window.matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light';}
function applyTheme(t){document.documentElement.setAttribute('data-theme',t==='system'?getSystemTheme():t);}
function themeIcon(t){return t==='dark'?'☀️':t==='light'?'🌙':'🔄';}
function toggleTheme(btn){
  const themes=['dark','light','system'];
  const cur=localStorage.getItem('theme')||'dark';
  const next=themes[(themes.indexOf(cur)+1)%3];
  localStorage.setItem('theme',next);
  applyTheme(next);
  btn.textContent=themeIcon(next);
}
(function(){
  const t=localStorage.getItem('theme')||'dark';
  applyTheme(t);
  document.addEventListener('DOMContentLoaded',function(){
    const btn=document.getElementById('theme-btn')||document.querySelector('.theme-toggle');
    if(btn)btn.textContent=themeIcon(t);
    if(t==='system'){window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change',()=>applyTheme('system'));}
  });
})();
"""

EARLY_THEME = """<script>
(function(){
  var t=localStorage.getItem('theme')||'dark';
  var eff=t==='system'?(window.matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light'):t;
  document.documentElement.setAttribute('data-theme',eff);
})();
</script>"""

# ── ADMIN LOGIN PAGE ──────────────────────────────────────────────────────────


HOME_PAGE = """<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
""" + EARLY_THEME + """
<title>Friedutch+</title>
<style>""" + BASE_CSS + """
body { max-width:720px; margin:0 auto; padding:56px 24px 100px; }
.site-header { margin-bottom:56px; }
.site-logo { font-size:36px; font-weight:900; margin-bottom:6px; }
.site-logo span { background:linear-gradient(135deg,var(--pink),var(--cyan));-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text; }
.site-sub { font-size:15px; color:var(--text2); font-weight:600; }
.projects-label { font-size:12px;font-weight:900;letter-spacing:0.12em;text-transform:uppercase;color:var(--text3);margin-bottom:20px; }
.projects-grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(280px,1fr)); gap:16px; }
.project-card {
  border-radius:var(--radius);
  padding:24px;
  border:2px solid transparent;
  cursor:pointer;
  transition:all 0.2s;
  text-decoration:none;
  display:block;
  color:var(--text);
}
.project-card:hover { transform:translateY(-4px); box-shadow:0 12px 40px var(--shadow); }
.project-card.active { background:linear-gradient(135deg,rgba(255,60,172,0.08),rgba(43,134,197,0.06)); border-color:rgba(255,60,172,0.2); }
.project-card.active:hover { border-color:rgba(255,60,172,0.4); }
.project-card.placeholder { background:var(--surface); border-color:var(--border); opacity:0.5; cursor:default; }
.project-card.placeholder:hover { transform:none; box-shadow:none; }
.project-icon { font-size:40px; margin-bottom:16px; display:block; }
.project-name { font-size:20px; font-weight:900; margin-bottom:6px; }
.project-desc { font-size:13px; color:var(--text2); font-weight:600; line-height:1.5; }
.project-tag {
  display:inline-flex; align-items:center; gap:4px;
  font-size:10px; font-weight:800; padding:3px 10px;
  border-radius:50px; margin-top:12px;
  letter-spacing:0.06em; text-transform:uppercase;
}
.tag-live { background:linear-gradient(135deg,rgba(0,200,130,0.15),rgba(0,210,255,0.1)); color:var(--green); border:1px solid rgba(0,200,130,0.3); }
.tag-soon { background:var(--surface2); color:var(--text3); border:1px solid var(--border); }
.footer { margin-top:56px; text-align:center; font-size:12px; color:var(--text3); font-weight:600; }
</style>
</head>
<body>
<button class="theme-toggle" onclick="toggleTheme(this)" id="theme-btn">🔄</button>
<div class="site-header">
  <div class="site-logo">🏠 <span>Friedutch+</span></div>
  <div class="site-sub">Personal projects & tools</div>
</div>
<p class="projects-label">Projects</p>
<div class="projects-grid">
  <a class="project-card active" href="/smartlock/">
    <span class="project-icon">🔐</span>
    <div class="project-name">Smart Lock</div>
    <div class="project-desc">Access control panel. Manage users, RFID badges, fingerprints and passcodes.</div>
    <span class="project-tag tag-live">✅ Live</span>
  </a>
  <div class="project-card placeholder">
    <span class="project-icon">📦</span>
    <div class="project-name">Coming soon</div>
    <div class="project-desc">Next project placeholder.</div>
    <span class="project-tag tag-soon">🔜 Soon</span>
  </div>
  <div class="project-card placeholder">
    <span class="project-icon">📦</span>
    <div class="project-name">Coming soon</div>
    <div class="project-desc">Next project placeholder.</div>
    <span class="project-tag tag-soon">🔜 Soon</span>
  </div>
</div>
<div class="footer">friedutch.plus · self-hosted on macOS</div>
<script>""" + THEME_JS + """</script>
</body>
</html>"""

ADMIN_LOGIN_PAGE = """<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
""" + EARLY_THEME + """
<title>Smart Lock — Access 🔐</title>
<style>""" + BASE_CSS + """
body { max-width:720px; margin:0 auto; padding:56px 24px 100px; }
.site-header { margin-bottom:48px; }
.site-logo { font-size:28px; font-weight:900; margin-bottom:4px; }
.site-logo span { background:linear-gradient(135deg,var(--pink),var(--cyan));-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text; }
.site-sub { font-size:14px; color:var(--text2); font-weight:600; }
.projects-label { font-size:12px;font-weight:900;letter-spacing:0.12em;text-transform:uppercase;color:var(--text3);margin-bottom:20px; }
.project-card {
  border-radius:var(--radius); padding:28px; border:2px solid rgba(255,60,172,0.2);
  background:linear-gradient(135deg,rgba(255,60,172,0.08),rgba(43,134,197,0.06));
  display:block; color:var(--text); max-width:360px;
}
.project-icon { font-size:48px; margin-bottom:16px; display:block; animation:float 3s ease-in-out infinite; }
@keyframes float{0%,100%{transform:translateY(0);}50%{transform:translateY(-8px);}}
.project-name { font-size:24px; font-weight:900; margin-bottom:6px; }
.project-desc { font-size:14px; color:var(--text2); font-weight:600; line-height:1.5; margin-bottom:20px; }
.number-box { border-radius:var(--radius-sm); padding:24px; text-align:center; background:linear-gradient(135deg,rgba(255,60,172,0.1),rgba(120,75,160,0.1)); border:2px solid rgba(255,60,172,0.25); margin-bottom:16px; }
.number-label { font-size:11px;font-weight:800;letter-spacing:0.12em;text-transform:uppercase;color:var(--text3);margin-bottom:12px; }
.number-display { font-size:80px;font-weight:900;background:linear-gradient(135deg,var(--pink),var(--cyan));-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;line-height:1;margin-bottom:8px; }
.number-hint { font-size:12px;color:var(--text2);font-weight:600; }
.cd-note { font-size:13px;font-weight:700;color:var(--text3);margin-top:12px; }
.cd-note span { color:var(--pink); }
.back-link { margin-top:24px; }
.back-link a { font-size:13px;font-weight:700;color:var(--text3); }
</style>
</head>
<body>
<button class="theme-toggle" onclick="toggleTheme(this)" id="theme-btn">🔄</button>
<div class="site-header">
  <div class="site-logo">🏠 <span>Friedutch+</span></div>
  <div class="site-sub">Personal projects & tools</div>
</div>
<p class="projects-label">Smart Lock · Admin Access</p>
<div class="project-card">
  <span class="project-icon">🔐</span>
  <div class="project-name">Smart Lock</div>
  <div class="project-desc">Access control panel · magic link login</div>
  {% if match_number %}
  <div class="number-box">
    <div class="number-label">✨ Your verification number</div>
    <div class="number-display">{{ match_number }}</div>
    <div class="number-hint">Select this when prompted in the email 👆</div>
  </div>
  {% endif %}
  {% if not admin_sent %}
  <form method="POST" action="/smartlock/login">
    <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
    <button class="big-btn btn-primary" type="submit" {% if link_cooldown > 0 %}disabled{% endif %}>
      📧 Send magic link
    </button>
  </form>
  {% endif %}
  {% if link_cooldown > 0 %}
  <p class="cd-note">Resend in <span id="lk-timer"></span></p>
  <script>
  let r={{ link_cooldown }};
  const el=document.getElementById("lk-timer");
  function tick(){if(r<=0){location.reload();clearInterval(iv);return;}el.textContent=Math.floor(r/60)+":"+String(r%60).padStart(2,"0");r--;}
  tick();const iv=setInterval(tick,1000);
  </script>
  {% endif %}
  {% if message %}<p class="msg-err" style="margin-top:12px;">{{ message }}</p>{% endif %}
</div>
{% if match_number %}
<script>
function poll(){fetch("/smartlock/poll-status").then(r=>r.json()).then(d=>{if(d.status==="logged_in"){window.close();document.body.innerHTML='<div style="font-family:Nunito,sans-serif;text-align:center;margin-top:40vh;font-size:16px;font-weight:800;color:#FF3CAC;">✅ Logged in! You can close this tab.</div>';}else{setTimeout(poll,2000);}}).catch(()=>setTimeout(poll,3000));}
setTimeout(poll,2000);
</script>
{% endif %}
<div class="back-link"><a href="/">← Back to Friedutch+</a></div>
<script>""" + THEME_JS + """</script>
</body>
</html>"""

# ── NUMBER MATCH PAGE ─────────────────────────────────────────────────────────

NUMBER_MATCH_PAGE = """<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
""" + EARLY_THEME + """
<title>Smart Lock — Pick your number 🎯</title>
<style>""" + BASE_CSS + """
body { display:flex; align-items:center; justify-content:center; min-height:100vh; padding:40px 24px; }
.wrap { width:100%; max-width:420px; animation:rise 0.4s cubic-bezier(0.16,1,0.3,1) both; }
@keyframes rise{from{opacity:0;transform:translateY(16px);}to{opacity:1;transform:translateY(0);}}
.app-icon { width:72px;height:72px;border-radius:22px;background:linear-gradient(135deg,var(--cyan),var(--blue));display:flex;align-items:center;justify-content:center;font-size:36px;margin:0 auto 14px;box-shadow:0 6px 24px rgba(0,210,255,0.4); }
.hero { text-align:center; margin-bottom:28px; }
.hero h1 { font-size:26px; font-weight:900; margin-bottom:6px; }
.hero p { font-size:14px; color:var(--text2); font-weight:600; }
.num-grid { display:grid; grid-template-columns:repeat(3,1fr); gap:12px; margin-bottom:16px; }
.num-btn {
  border-radius:var(--radius-sm); padding:24px 12px; font-size:48px; font-weight:900;
  text-align:center; cursor:pointer; border:2px solid var(--border);
  background:var(--card); color:var(--text); transition:all 0.2s;
  box-shadow:0 4px 16px var(--shadow); font-family:'Nunito',sans-serif;
  -webkit-background-clip:padding-box; background-clip:padding-box;
}
.num-btn:nth-child(1):hover{transform:translateY(-4px) scale(1.04);border-color:var(--pink);box-shadow:0 8px 28px rgba(255,60,172,0.35);}
.num-btn:nth-child(2):hover{transform:translateY(-4px) scale(1.04);border-color:var(--cyan);box-shadow:0 8px 28px rgba(0,210,255,0.35);}
.num-btn:nth-child(3):hover{transform:translateY(-4px) scale(1.04);border-color:var(--green);box-shadow:0 8px 28px rgba(0,200,130,0.35);}
</style>
</head>
<body>
<button class="theme-toggle" onclick="toggleTheme(this)" id="theme-btn">🔄</button>
<div class="wrap">
  <div class="hero">
    <div class="app-icon">🎯</div>
    <h1>Pick your number!</h1>
    <p>Which one is showing on your screen? 👀</p>
  </div>
  <div class="num-grid">
  {% for opt in options %}
  <form method="POST" action="{{ '/smartlock/verify-email-number' if mode == 'email_change' else '/smartlock/join-verify' if mode == 'join' else '/smartlock/verify-number' }}" style="display:contents;">
    <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
    <input type="hidden" name="token" value="{{ token }}">
    <input type="hidden" name="number" value="{{ opt }}">
    <button class="num-btn" type="submit">{{ opt }}</button>
  </form>
  {% endfor %}
  </div>
  {% if error %}<p class="msg-err">{{ error }}</p>{% endif %}
</div>
<script>""" + THEME_JS + """</script>
</body>
</html>"""

# ── ADD SESSION PAGE ──────────────────────────────────────────────────────────

ADD_SESSION_PAGE = """<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
""" + EARLY_THEME + """
<title>Smart Lock — Add Session 📲</title>
<style>""" + BASE_CSS + """
body { display:flex; align-items:center; justify-content:center; min-height:100vh; padding:40px 24px; }
.wrap { width:100%; max-width:420px; animation:rise 0.5s cubic-bezier(0.16,1,0.3,1) both; }
@keyframes rise{from{opacity:0;transform:translateY(20px);}to{opacity:1;transform:translateY(0);}}
.hero { text-align:center; margin-bottom:28px; }
.app-icon { width:80px;height:80px;border-radius:26px;background:linear-gradient(135deg,var(--cyan),var(--blue));display:flex;align-items:center;justify-content:center;font-size:40px;margin:0 auto 16px;box-shadow:0 8px 32px rgba(0,210,255,0.4); }
.hero h1 { font-size:26px; font-weight:900; margin-bottom:6px; }
.hero p { font-size:14px; color:var(--text2); font-weight:600; }
.number-box { border-radius:var(--radius);padding:28px;text-align:center;background:linear-gradient(135deg,rgba(0,210,255,0.1),rgba(43,134,197,0.08));border:2px solid rgba(0,210,255,0.25);margin-bottom:14px; }
.number-label { font-size:11px;font-weight:800;letter-spacing:0.12em;text-transform:uppercase;color:var(--text3);margin-bottom:12px; }
.number-display { font-size:88px;font-weight:900;background:linear-gradient(135deg,var(--cyan),var(--green));-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;line-height:1;margin-bottom:8px; }
.number-hint { font-size:13px;color:var(--text2);font-weight:600; }
.url-card { background:var(--card);border:2px solid var(--border);border-radius:var(--radius-sm);padding:16px;margin-bottom:14px; }
.url-label { font-size:11px;font-weight:800;letter-spacing:0.1em;text-transform:uppercase;color:var(--text3);margin-bottom:8px; }
.url-box { background:var(--surface2);border:2px solid var(--border);border-radius:var(--radius-xs);padding:10px 14px;font-size:12px;font-weight:700;color:var(--cyan);word-break:break-all;margin-bottom:10px; }
.cd-note { text-align:center;font-size:13px;font-weight:700;color:var(--text3);margin-bottom:14px; }
.cd-note span { color:var(--cyan); }
.back-link { text-align:center; }
.back-link a { font-size:13px;font-weight:700;color:var(--text3); }
</style>
</head>
<body>
<button class="theme-toggle" onclick="toggleTheme(this)" id="theme-btn">🔄</button>
<div class="wrap">
  <div class="hero">
    <div class="app-icon">📲</div>
    <h1>Add a session!</h1>
    <p>Open the link on your other device</p>
  </div>
  <div class="number-box">
    <div class="number-label">✨ Your verification number</div>
    <div class="number-display">{{ number }}</div>
    <div class="number-hint">Select this on the other device 👆</div>
  </div>
  <div class="url-card">
    <div class="url-label">🔗 Link for other device</div>
    <div class="url-box">{{ join_url }}</div>
    <button class="sm-btn sm-cyan" onclick="navigator.clipboard.writeText('{{ join_url }}');this.textContent='✅ Copied!'">📋 Copy link</button>
  </div>
  <p class="cd-note">Link expires in <span id="exp-timer">5:00</span></p>
  <div class="back-link"><a href="/smartlock/admin">← Back to panel</a></div>
</div>
<script>
let r=300;
const el=document.getElementById("exp-timer");
function tick(){if(r<=0){el.textContent="expired";clearInterval(iv);return;}el.textContent=Math.floor(r/60)+":"+String(r%60).padStart(2,"0");r--;}
tick();const iv=setInterval(tick,1000);
""" + THEME_JS + """
</script>
</body>
</html>"""

# ── ADMIN PANEL ───────────────────────────────────────────────────────────────

ADMIN_PANEL = """<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
""" + EARLY_THEME + """
<title>Smart Lock — Control Room ⚙️</title>
<style>""" + BASE_CSS + """
body { max-width:720px; margin:0 auto; padding:0 24px 100px; }
.top-bar-unified {
  position: sticky; top: 0; z-index: 100;
  display: flex; align-items: center; justify-content: space-between;
  padding: 12px 0; margin-bottom: 32px;
  backdrop-filter: blur(16px); -webkit-backdrop-filter: blur(16px);
  background: rgba(15,15,26,0.6);
  border-bottom: 1px solid rgba(255,255,255,0.07);
}
[data-theme="light"] .top-bar-unified {
  background: rgba(240,240,255,0.7);
  border-bottom: 1px solid rgba(0,0,0,0.07);
}
.app-brand { display:flex; align-items:center; gap:10px; }
.brand-icon { width:36px;height:36px;border-radius:10px;background:linear-gradient(135deg,var(--pink),var(--purple));display:flex;align-items:center;justify-content:center;font-size:18px; }
.brand-name { font-size:15px; font-weight:900; }
.brand-sub { font-size:10px; color:var(--text3); font-weight:600; }
.top-bar-right { display:flex; align-items:center; gap:8px; }
.sess-chip { display:flex;align-items:center;gap:5px;font-size:13px;font-weight:800;padding:6px 12px;border-radius:50px;border:2px solid transparent; }
.sess-chip.ok   { background:var(--surface); border-color:rgba(0,200,130,0.4); color:var(--green); }
.sess-chip.warn { background:var(--surface); border-color:rgba(255,107,53,0.6); color:var(--orange); animation:pulse-warn 2s ease-in-out infinite; }
@keyframes pulse-warn { 0%,100%{box-shadow:0 0 0 0 rgba(255,107,53,0.2);}50%{box-shadow:0 0 0 6px rgba(255,107,53,0);} }
.top-icon-btn { width:36px;height:36px;border-radius:10px;border:2px solid var(--border);background:var(--surface2);display:flex;align-items:center;justify-content:center;font-size:16px;cursor:pointer;font-family:'Nunito',sans-serif;font-weight:800;color:var(--text2);transition:all 0.2s;text-decoration:none; }
.top-icon-btn:hover { border-color:var(--pink); }
h1 { font-size:36px; font-weight:900; margin-bottom:32px; }
.user-card { background:var(--surface);border:2px solid var(--border);border-radius:var(--radius-sm);padding:14px 16px;margin-bottom:10px;display:flex;align-items:center;gap:14px;transition:all 0.2s; }
.user-card:hover { border-color:rgba(255,60,172,0.3); box-shadow:0 4px 20px var(--shadow); }
.user-avatar { width:44px;height:44px;border-radius:14px;display:flex;align-items:center;justify-content:center;font-size:22px;flex-shrink:0;background:linear-gradient(135deg,rgba(255,60,172,0.15),rgba(120,75,160,0.15)); }
.user-info { flex:1; min-width:0; }
.user-name { font-size:15px; font-weight:800; margin-bottom:2px; }
.user-code { font-size:15px;font-weight:800;color:var(--text2);letter-spacing:0.05em; }
.method-chips { display:flex; gap:5px; flex-wrap:wrap; margin-top:6px; }
.icon-btn { width:36px;height:36px;border-radius:10px;border:2px solid var(--border);background:var(--surface2);display:flex;align-items:center;justify-content:center;font-size:16px;cursor:pointer;transition:all 0.2s;text-decoration:none; }
.icon-btn:hover { transform:scale(1.1); }
.icon-btn.edit:hover { border-color:var(--cyan); }
.session-card { background:var(--surface);border:2px solid var(--border);border-radius:var(--radius-sm);padding:14px 16px;margin-bottom:10px;display:flex;align-items:center;gap:14px;transition:all 0.2s; }
.session-card.current { border-color:rgba(0,200,130,0.3); background:linear-gradient(135deg,rgba(0,200,130,0.05),rgba(0,210,255,0.03)); }
.session-card.allowed { border-color:rgba(0,200,130,0.15); opacity:0.7; }
.session-card.denied  { border-color:rgba(255,107,53,0.2); background:rgba(255,107,53,0.03); opacity:0.85; }
.timer-deny { background:rgba(255,107,53,0.1); color:var(--orange); font-size:13px; font-weight:800; padding:4px 10px; border-radius:50px; }
.session-icon { width:44px;height:44px;border-radius:14px;background:linear-gradient(135deg,rgba(0,200,130,0.15),rgba(0,210,255,0.1));display:flex;align-items:center;justify-content:center;font-size:22px;flex-shrink:0; }
.session-info { flex:1; min-width:0; }
.session-ip { font-size:14px;font-weight:800;margin-bottom:2px; }
.session-meta { font-size:12px;color:var(--text3);font-weight:600; }
.session-timer { font-size:13px;font-weight:800;padding:4px 10px;border-radius:50px; }
.timer-ok { background:linear-gradient(135deg,rgba(0,200,130,0.15),rgba(0,210,255,0.1));color:var(--green); }
.timer-warn { background:rgba(255,107,53,0.1);color:var(--orange); }
.current-badge { font-size:10px;font-weight:800;padding:2px 8px;border-radius:50px;background:linear-gradient(135deg,rgba(0,200,130,0.15),rgba(0,210,255,0.1));color:var(--green);letter-spacing:0.06em;margin-left:6px; }
.log-feed { display:flex;flex-direction:column;gap:8px;max-height:240px;overflow-y:auto;padding-right:4px; }
.log-feed::-webkit-scrollbar { width:4px; }
.log-feed::-webkit-scrollbar-thumb { background:var(--border);border-radius:4px; }
.log-item { background:var(--surface);border:2px solid var(--border);border-radius:var(--radius-xs);padding:10px 14px;display:flex;align-items:center;gap:10px;font-size:13px;font-weight:600; }
.log-item.ok   { border-left:3px solid var(--green); }
.log-item.fail { border-left:3px solid var(--orange); }
.log-badge { font-size:11px;font-weight:800;padding:3px 10px;border-radius:50px; }
.log-badge.ok   { background:linear-gradient(135deg,rgba(0,200,130,0.15),rgba(0,210,255,0.1));color:var(--green); }
.log-badge.fail { background:rgba(255,107,53,0.1);color:var(--orange); }
.log-ip   { color:var(--text2);font-size:12px; }
.log-time { color:var(--text3);font-size:12px;margin-left:auto; }
.setting-label { font-size:12px;font-weight:800;letter-spacing:0.1em;text-transform:uppercase;color:var(--text3);margin-bottom:6px; }
.setting-val   { font-size:14px;font-weight:800;color:var(--text2);margin-bottom:12px; }
.pending-tag { display:inline-flex;align-items:center;gap:6px;font-size:12px;font-weight:700;color:var(--yellow);border:2px solid rgba(255,214,10,0.3);padding:4px 12px;border-radius:50px;margin-bottom:10px; }
.pending-actions { display:flex;gap:8px;flex-wrap:wrap;margin-top:8px; }
.cd-note-sm { font-size:12px;font-weight:700;color:var(--text3);margin-top:8px; }
.cd-note-sm span { color:var(--pink); }
.no-items { font-size:14px;font-weight:600;color:var(--text3);text-align:center;padding:16px 0; }
</style>
</head>
<body>

<div class="top-bar-unified">
  <div class="app-brand">
    <div class="brand-icon">🔐</div>
    <div>
      <div class="brand-name">Smart Lock</div>
      <div class="brand-sub">friedutch.plus</div>
    </div>
  </div>
  <div class="top-bar-right">
    <a class="top-icon-btn" href="/smartlock/logout" onclick="return confirm('Log out from this session?')">👋</a>
    <div class="sess-chip ok" id="sess-notif-top" style="display:none;">
      <span id="notif-icon-top">🟢</span>
      <span id="notif-timer-top">--:--</span>
    </div>
    <button class="top-icon-btn" onclick="toggleTheme(this)" id="theme-btn">🔄</button>
  </div>
</div>

<h1>⚙️ Control Room</h1>

<div class="zone zone-pink">
  <div class="zone-title"><div class="zone-title-left"><span>⚙️</span> Settings</div></div>
  <p class="setting-label">📧 Admin Email</p>
  <p class="setting-val">{{ admin_email }}</p>
  {% if pending %}
  <div class="pending-tag">⏳ Awaiting verification</div>
  <p style="font-size:13px;font-weight:600;color:var(--text2);margin-bottom:8px;">Sent to <strong>{{ pending }}</strong></p>
  <div class="pending-actions">
    <a class="sm-btn sm-pink" href="/smartlock/change-email/pending">View status</a>
    <a class="sm-btn sm-ghost" href="/smartlock/change-email/cancel" style="border-color:rgba(255,60,172,0.3);color:var(--pink);">Cancel</a>
  </div>
  {% else %}
  <form class="field-row" method="POST" action="/smartlock/change-email" id="chg-form">
    <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
    <input class="app-input" type="email" name="new_email" placeholder="New email address" {% if cooldown_remaining > 0 %}disabled{% endif %}>
    <button class="sm-btn sm-pink" type="submit" id="chg-btn" {% if cooldown_remaining > 0 %}disabled{% endif %}>✉️ Save</button>
  </form>
  {% if cooldown_remaining > 0 %}
  <p class="cd-note-sm" id="chg-cd">Available in <span id="chg-t"></span></p>
  <script>
  let cr={{ cooldown_remaining }};
  const ct=document.getElementById("chg-t"),cb=document.getElementById("chg-btn"),ci=document.querySelector("#chg-form input[type=email]");
  function tickC(){if(cr<=0){cb.disabled=false;ci.disabled=false;document.getElementById("chg-cd").style.display="none";clearInterval(civ);return;}ct.textContent=Math.floor(cr/60)+":"+String(cr%60).padStart(2,"0");cr--;}
  tickC();const civ=setInterval(tickC,1000);
  </script>
  {% endif %}
  {% endif %}
</div>

<div class="zone zone-cyan">
  <div class="zone-title"><div class="zone-title-left"><span>👥</span> People</div></div>
  <form class="field-row" method="POST" action="/smartlock/users/add">
    <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
    <input class="app-input" type="text" name="name" placeholder="New user name" required>
    <button class="sm-btn sm-cyan" type="submit">➕ Add</button>
  </form>
  {% if users %}
  {% for user in users %}
  <div class="user-card">
    <div class="user-avatar">👤</div>
    <div class="user-info">
      <div class="user-name">{{ user['name'] }}</div>
      <div class="user-code">{{ user['passcode'] }}</div>
      <div class="method-chips">
        <span class="chip {{ 'chip-on' if user['rfid_enabled'] else 'chip-off' }}">💳 RFID</span>
        <span class="chip {{ 'chip-on' if user['fingerprint_enabled'] else 'chip-off' }}">🖐️ FP</span>
      </div>
    </div>
    <a class="icon-btn edit" href="/smartlock/user/{{ user['id'] }}">✏️</a>
  </div>
  {% endfor %}
  {% else %}
  <p class="no-items">No users yet 👆 Add one above</p>
  {% endif %}
</div>

<div class="zone zone-green">
  <div class="zone-title">
    <div class="zone-title-left"><span>📡</span> Sessions Log</div>
    <div style="display:flex;gap:8px;flex-wrap:wrap;justify-content:flex-end;">
      <a class="sm-btn sm-green" href="/smartlock/add-session">📲 Add</a>
      <a class="sm-btn sm-ghost" href="/smartlock/session/logout-all" onclick="return confirm('Log out all other sessions?')" style="border-color:rgba(0,200,130,0.3);color:var(--green);">🚪 All out</a>
    </div>
  </div>

  {% for s in sessions %}
  <div class="session-card {{ 'current' if s.session_token == current_token else '' }}">
    <div class="session-icon">{{ s.icon }}</div>
    <div class="session-info">
      <div class="session-ip">
        {{ s.ip }}
        {% if s.session_token == current_token %}<span class="current-badge">THIS DEVICE</span>{% endif %}
      </div>
      <div class="session-meta">{{ s.created_at }} UTC</div>
    </div>
    <span class="session-timer {{ 'timer-ok' if s.remaining > 600 else 'timer-warn' }}" id="stimer-{{ loop.index }}">{{ s.remaining_fmt }}</span>
    <a class="icon-btn" href="/smartlock/session/logout/{{ s.session_token }}" onclick="return confirm('Log out this session?')" style="flex-shrink:0;">🚪</a>
  </div>
  <script>
  (function(){
    let r={{ s.remaining }};
    const el=document.getElementById("stimer-{{ loop.index }}");
    function tick(){if(r<=0){el.textContent="expired";el.className="session-timer timer-warn";clearInterval(iv);return;}const m=Math.floor(r/60),s=String(r%60).padStart(2,"0");el.textContent=m+":"+s;if(r<=600)el.className="session-timer timer-warn";r--;}
    tick();const iv=setInterval(tick,1000);
  })();
  </script>
  {% endfor %}

  {% for log in logs %}
  <div class="session-card {{ 'allowed' if log['success'] else 'denied' }}">
    <div class="session-icon">{{ log['user_agent'] if log['user_agent'] else '🌐' }}</div>
    <div class="session-info">
      <div class="session-ip">{{ log['ip'] }}</div>
      <div class="session-meta">{{ log['created_at'][:19].replace('T',' ') }} UTC</div>
    </div>
    <span class="session-timer {{ 'timer-ok' if log['success'] else 'timer-deny' }}">{{ 'Allowed' if log['success'] else 'Denied' }}</span>
  </div>
  {% endfor %}

  {% if not sessions and not logs %}
  <p class="no-items">No sessions yet 👀</p>
  {% endif %}
</div>

<script>
""" + THEME_JS + """
(function(){
  let r = {{ current_remaining }};
  if (r <= 0) return;
  const notif = document.getElementById("sess-notif-top");
  const timerEl = document.getElementById("notif-timer-top");
  const iconEl = document.getElementById("notif-icon-top");
  notif.style.display = "flex";
  let warned = false;
  function tick() {
    if (r <= 0) {
      timerEl.textContent = "Expired";
      notif.className = "sess-chip warn";
      iconEl.textContent = "🔴";
      clearInterval(iv);
      setTimeout(() => { window.location.href = "/logout"; }, 5000);
      return;
    }
    const m = Math.floor(r/60), s = String(r%60).padStart(2,"0");
    timerEl.textContent = m + ":" + s;
    if (r <= 300) {
      notif.className = "sess-chip warn";
      iconEl.textContent = "⚠️";
      if (!warned) {
        warned = true;
        notif.style.transform = "scale(1.05)";
        setTimeout(() => notif.style.transform = "scale(1)", 400);
      }
    } else {
      notif.className = "sess-chip ok";
      iconEl.textContent = "🟢";
    }
    r--;
  }
  tick();
  const iv = setInterval(tick, 1000);
})();
</script>
</body>
</html>"""

# ── ADMIN USER DETAIL ─────────────────────────────────────────────────────────

ADMIN_USER_DETAIL = """<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
""" + EARLY_THEME + """
<title>{{ user['name'] }} — Friedutch</title>
<style>""" + BASE_CSS + """
body { max-width:520px; margin:0 auto; padding:48px 24px 100px; }
.back-link { display:inline-flex;align-items:center;gap:8px;font-size:14px;font-weight:800;color:var(--text2);margin-bottom:24px;cursor:pointer;transition:color 0.2s; }
.back-link:hover { color:var(--pink); }
.detail-header { display:flex;align-items:center;gap:16px;margin-bottom:28px; }
.detail-avatar { width:64px;height:64px;border-radius:20px;background:linear-gradient(135deg,var(--pink),var(--purple),var(--blue));display:flex;align-items:center;justify-content:center;font-size:32px;box-shadow:0 6px 24px rgba(255,60,172,0.35); }
.detail-name { font-size:26px;font-weight:900; }
.detail-sub { font-size:13px;color:var(--text2);font-weight:600; }
.method-zone { background:var(--card);border:2px solid var(--border);border-radius:var(--radius-sm);padding:18px;margin-bottom:12px; }
.method-head { display:flex;align-items:center;gap:10px;margin-bottom:14px; }
.method-emoji { font-size:24px; }
.method-label { flex:1;font-size:16px;font-weight:800; }
.method-toggle { font-size:12px;font-weight:800;padding:6px 14px;border-radius:50px;border:2px solid transparent;cursor:pointer;transition:all 0.2s;font-family:'Nunito',sans-serif; }
.method-toggle.on { background:linear-gradient(135deg,rgba(0,200,130,0.15),rgba(0,210,255,0.1));color:var(--green);border-color:rgba(0,200,130,0.3); }
.method-toggle.off { background:var(--surface2);color:var(--text3);border-color:var(--border); }
.method-toggle.locked { background:linear-gradient(135deg,rgba(0,200,130,0.15),rgba(0,210,255,0.1));color:var(--green);border-color:rgba(0,200,130,0.3);pointer-events:none; }
.code-big { font-size:24px;font-weight:800;color:var(--text2);letter-spacing:0.08em;margin-bottom:6px; }
.method-desc { font-size:12px;color:var(--text3);font-weight:600;margin-bottom:12px; }
.current-id { font-size:13px;color:var(--text2);font-weight:700;margin-bottom:10px; }
</style>
</head>
<body>
<button class="theme-toggle" onclick="toggleTheme(this)" id="theme-btn">🔄</button>
<a class="back-link" href="/smartlock/admin">← Back to panel</a>
<div class="detail-header">
  <div class="detail-avatar">👤</div>
  <div>
    <div class="detail-name">{{ user['name'] }}</div>
    <div class="detail-sub">Access profile</div>
  </div>
</div>

<div class="method-zone">
  <div class="method-head">
    <span class="method-emoji">🔢</span>
    <span class="method-label">Passcode</span>
    <span class="method-toggle locked">Default ✓</span>
  </div>
  <div class="code-big">{{ user['passcode'] }}</div>
  <div class="method-desc">Personal 6-digit code · not editable</div>
</div>

<div class="method-zone">
  <div class="method-head">
    <span class="method-emoji">💳</span>
    <span class="method-label">RFID Badge</span>
    <a class="method-toggle {{ 'on' if user['rfid_enabled'] else 'off' }}" href="/smartlock/user/{{ user['id'] }}/toggle/rfid">
      {{ 'Enabled ✓' if user['rfid_enabled'] else 'Disabled' }}
    </a>
  </div>
  {% if user['rfid_id'] %}<div class="current-id">Current: {{ user['rfid_id'] }}</div>{% endif %}
  <div class="method-desc">Set the badge identifier accepted for this user</div>
  <form class="field-row" method="POST" action="/smartlock/user/{{ user['id'] }}/set/rfid">
    <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
    <input class="app-input" type="text" name="id_value" placeholder="Badge ID" value="{{ user['rfid_id'] or '' }}">
    <button class="sm-btn sm-cyan" type="submit">💾 Save</button>
  </form>
</div>

<div class="method-zone">
  <div class="method-head">
    <span class="method-emoji">🖐️</span>
    <span class="method-label">Fingerprint</span>
    <a class="method-toggle {{ 'on' if user['fingerprint_enabled'] else 'off' }}" href="/smartlock/user/{{ user['id'] }}/toggle/fingerprint">
      {{ 'Enabled ✓' if user['fingerprint_enabled'] else 'Disabled' }}
    </a>
  </div>
  {% if user['fingerprint_id'] %}<div class="current-id">Current: {{ user['fingerprint_id'] }}</div>{% endif %}
  <div class="method-desc">Set the fingerprint identifier for biometric recognition</div>
  <form class="field-row" method="POST" action="/smartlock/user/{{ user['id'] }}/set/fingerprint">
    <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
    <input class="app-input" type="text" name="id_value" placeholder="Fingerprint ID" value="{{ user['fingerprint_id'] or '' }}">
    <button class="sm-btn sm-green" type="submit">💾 Save</button>
  </form>
</div>

<a class="big-btn" href="/smartlock/users/delete/{{ user['id'] }}"
   onclick="return confirm('Delete {{ user[\\'name\\'] }} permanently?')"
   style="background:linear-gradient(135deg,var(--orange),#FF4444);color:white;box-shadow:0 6px 24px rgba(255,107,53,0.4);margin-top:8px;display:flex;align-items:center;justify-content:center;gap:8px;text-decoration:none;">
  🗑️ Delete {{ user['name'] }}
</a>

<script>""" + THEME_JS + """</script>
</body>
</html>"""

# ── EMAIL PENDING PAGE ────────────────────────────────────────────────────────

EMAIL_PENDING_PAGE = """<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
""" + EARLY_THEME + """
<title>Smart Lock — Verify Email ✉️</title>
<style>""" + BASE_CSS + """
body { display:flex; align-items:center; justify-content:center; min-height:100vh; padding:40px 24px; }
.wrap { width:100%; max-width:420px; animation:rise 0.5s cubic-bezier(0.16,1,0.3,1) both; }
@keyframes rise{from{opacity:0;transform:translateY(20px);}to{opacity:1;transform:translateY(0);}}
.app-icon { width:72px;height:72px;border-radius:22px;background:linear-gradient(135deg,var(--pink),var(--purple));display:flex;align-items:center;justify-content:center;font-size:36px;margin:0 auto 16px;box-shadow:0 6px 24px rgba(255,60,172,0.4); }
.hero { text-align:center; margin-bottom:28px; }
.hero h1 { font-size:26px; font-weight:900; margin-bottom:6px; }
.hero p { font-size:14px; color:var(--text2); font-weight:600; }
.email-card { background:var(--card);border:2px solid var(--border);border-radius:var(--radius-sm);padding:16px;margin-bottom:14px; }
.email-label { font-size:11px;font-weight:800;letter-spacing:0.1em;text-transform:uppercase;color:var(--text3);margin-bottom:8px; }
.email-val { font-size:14px;font-weight:800;color:var(--cyan);word-break:break-all; }
.number-box { border-radius:var(--radius);padding:24px;text-align:center;background:linear-gradient(135deg,rgba(255,60,172,0.08),rgba(120,75,160,0.06));border:2px solid rgba(255,60,172,0.2);margin-bottom:14px; }
.number-label { font-size:11px;font-weight:800;letter-spacing:0.12em;text-transform:uppercase;color:var(--text3);margin-bottom:10px; }
.number-display { font-size:72px;font-weight:900;background:linear-gradient(135deg,var(--pink),var(--cyan));-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;line-height:1;margin-bottom:6px; }
.number-hint { font-size:12px;color:var(--text2);font-weight:600; }
.cd-row { font-size:13px;font-weight:700;color:var(--text3);margin-bottom:16px;text-align:center; }
.cd-row span { color:var(--pink); }
.actions { display:flex;gap:8px;flex-wrap:wrap;margin-bottom:14px; }
.back-link { text-align:center; }
.back-link a { font-size:13px;font-weight:700;color:var(--text3); }
</style>
</head>
<body>
<button class="theme-toggle" onclick="toggleTheme(this)" id="theme-btn">🔄</button>
<div class="wrap">
  <div class="hero">
    <div class="app-icon">📬</div>
    <h1>Check your inbox!</h1>
    <p>Verification link sent to:</p>
  </div>
  <div class="email-card">
    <div class="email-label">📧 Email address</div>
    <div class="email-val">{{ pending_email }}</div>
  </div>
  {% if match_number %}
  <div class="number-box">
    <div class="number-label">✨ Your verification number</div>
    <div class="number-display">{{ match_number }}</div>
    <div class="number-hint">Select this when prompted in the email 👆</div>
  </div>
  {% endif %}
  {% if error %}<p class="msg-err">{{ error }}</p>{% endif %}
  <p class="cd-row">Resend available in <span id="timer">5:00</span></p>
  <div class="actions">
    <a id="resend-btn" class="sm-btn sm-ghost" href="#" style="pointer-events:none;opacity:0.4;">🔄 Resend</a>
    <a class="sm-btn sm-ghost" href="/smartlock/change-email/cancel">❌ Wrong email?</a>
  </div>
  <div class="back-link"><a href="/smartlock/admin">← Back to panel</a></div>
</div>
<script>
const sentAt=new Date("{{ sent_at }}Z");
const INTERVAL=5*60*1000;
const btn=document.getElementById("resend-btn");
const timer=document.getElementById("timer");
function tick(){const rem=INTERVAL-(Date.now()-sentAt);if(rem<=0){timer.textContent="now";btn.style.pointerEvents="auto";btn.style.opacity="1";btn.href="/smartlock/change-email/resend";clearInterval(iv);return;}const m=Math.floor(rem/60000),s=String(Math.floor((rem%60000)/1000)).padStart(2,"0");timer.textContent=m+":"+s;}
tick();const iv=setInterval(tick,1000);
""" + THEME_JS + """
</script>
</body>
</html>"""

import aiohttp as _aiohttp
import re as _re
import bleach as _bleach

FOOTPRINT_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "projects/footprint/footprint.db")
HIBP_API_KEY = os.getenv("HIBP_API_KEY", "")
HIBP_HEADERS = {"hibp-api-key": HIBP_API_KEY, "user-agent": "friedutch-footprint/1.0"}

def _init_footprint_db():
    db = _sqlite3.connect(FOOTPRINT_DB_PATH)
    db.execute("""CREATE TABLE IF NOT EXISTS scans (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        target TEXT NOT NULL,
        scan_type TEXT NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS breaches (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        scan_id INTEGER NOT NULL,
        email TEXT NOT NULL,
        site TEXT NOT NULL,
        breach_date TEXT,
        severity TEXT,
        data_classes TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS probe_results (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        scan_id INTEGER NOT NULL,
        email TEXT NOT NULL,
        site TEXT NOT NULL,
        status TEXT NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS addresses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        scan_id INTEGER NOT NULL,
        email TEXT NOT NULL,
        breach_count INTEGER DEFAULT 0,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )""")
    db.commit()
    db.close()

_init_footprint_db()

# ── Probe site list ────────────────────────────────────────────────────────────

_SITES = [
    {"name":"GitHub",        "icon":"🐙", "url":"https://github.com/password_reset",                                           "method":"post","payload":{"email":"{EMAIL}"},                                                          "found_re":r"(If an account exists|reset password)","not_found_re":r"(No account|couldn't find)","inconclusive":True},
    {"name":"GitLab",        "icon":"🦊", "url":"https://gitlab.com/users/password",                                           "method":"post","payload":{"user[email]":"{EMAIL}"},                                                    "found_re":r"(Instructions have been sent)","not_found_re":r"(not found|no user)"},
    {"name":"Microsoft",     "icon":"🪟", "url":"https://login.live.com/GetCredentialType.srf",                                "method":"post","payload":{"username":"{EMAIL}"},                                                       "found_re":r'"IfExistsResult":0',"not_found_re":r'"IfExistsResult":1',"json":True},
    {"name":"Instagram",     "icon":"📸", "url":"https://www.instagram.com/accounts/account_recovery_send_ajax/",              "method":"post","payload":{"email_or_username":"{EMAIL}"},                                             "found_re":r'"email_sent":true',"not_found_re":r'"email_sent":false'},
    {"name":"Snapchat",      "icon":"👻", "url":"https://accounts.snapchat.com/accounts/password_reset_request",               "method":"post","payload":{"email":"{EMAIL}"},                                                          "found_re":r"(email sent|instructions sent)","not_found_re":r"(no account|not found)"},
    {"name":"Pinterest",     "icon":"📌", "url":"https://www.pinterest.com/password/reset/",                                   "method":"post","payload":{"username_or_email":"{EMAIL}"},                                             "found_re":r"(email sent|reset link)","not_found_re":r"(no account|not found)"},
    {"name":"Tumblr",        "icon":"📓", "url":"https://www.tumblr.com/forgot_password",                                      "method":"post","payload":{"email":"{EMAIL}"},                                                          "found_re":r"(email sent|reset link)","not_found_re":r"(no account|not found)"},
    {"name":"Discord",       "icon":"🎮", "url":"https://discord.com/api/v9/auth/forgot",                                      "method":"post","payload":{"email":"{EMAIL}"},                                                          "found_re":r"NEVER","not_found_re":r"NEVER","inconclusive":True},
    {"name":"Spotify",       "icon":"🎵", "url":"https://accounts.spotify.com/en/password-reset",                              "method":"post","payload":{"email":"{EMAIL}"},                                                          "found_re":r"(email.*sent|check your inbox)","not_found_re":r"(no account|doesn't exist)","inconclusive":True},
    {"name":"Netflix",       "icon":"🎬", "url":"https://www.netflix.com/LoginHelp",                                           "method":"post","payload":{"email":"{EMAIL}","flow":"pwd"},                                            "found_re":r"(email.*sent|reset link)","not_found_re":r"(no account|couldn't find)","inconclusive":True},
    {"name":"Google",        "icon":"🔍", "url":"https://accounts.google.com/signin/v2/identifier",                            "method":"post","payload":{"identifier":"{EMAIL}"},                                                    "found_re":r"(wrong password|enter your password)","not_found_re":r"(couldn't find|no account)","inconclusive":True},
    {"name":"Apple",         "icon":"🍎", "url":"https://iforgot.apple.com/password/verify/appleid",                           "method":"post","payload":{"id":"{EMAIL}"},                                                             "found_re":r"(verify|confirm)","not_found_re":r"(no account|not found)","inconclusive":True},
    {"name":"Twitter / X",   "icon":"🐦", "url":"https://twitter.com/i/flow/password_reset",                                   "method":"post","payload":{"email":"{EMAIL}"},                                                          "found_re":r"(reset instructions|email sent)","not_found_re":r"(no account|not found)","inconclusive":True},
    {"name":"Facebook",      "icon":"📘", "url":"https://www.facebook.com/login/identify/",                                    "method":"post","payload":{"email":"{EMAIL}"},                                                          "found_re":r"(account found|identify)","not_found_re":r"(no account|not found)","inconclusive":True},
    {"name":"LinkedIn",      "icon":"💼", "url":"https://www.linkedin.com/checkpoint/lg/forgot-password",                      "method":"post","payload":{"session_key":"{EMAIL}"},                                                   "found_re":r"(email.*sent|reset link)","not_found_re":r"(no account|not found)","inconclusive":True},
    {"name":"TikTok",        "icon":"🎵", "url":"https://www.tiktok.com/passport/web/account/password/reset/",                 "method":"post","payload":{"email":"{EMAIL}"},                                                          "found_re":r"(email sent|reset link)","not_found_re":r"(not registered|no account)","inconclusive":True},
    {"name":"Steam",         "icon":"🎮", "url":"https://store.steampowered.com/login/",                                       "method":"post","payload":{"email":"{EMAIL}","action":"forgotpassword"},                               "found_re":r"(email sent|reset link)","not_found_re":r"(no account|not found)","inconclusive":True},
    {"name":"Twitch",        "icon":"🟣", "url":"https://passport.twitch.tv/password_reset_request",                           "method":"post","payload":{"email":"{EMAIL}"},                                                          "found_re":r"(email sent|reset link)","not_found_re":r"(no account|not found)","inconclusive":True},
    {"name":"Reddit",        "icon":"🤖", "url":"https://www.reddit.com/api/v1/register",                                      "method":"post","payload":{"email":"{EMAIL}","verify":"true"},                                         "found_re":r'"email_verified":true',"not_found_re":r'"email_verified":false',"inconclusive":True},
    {"name":"Vercel",        "icon":"▲",  "url":"https://vercel.com/api/registration/login",                                   "method":"post","payload":{"email":"{EMAIL}","tokenName":"probe"},                                    "found_re":r"(email sent|magic link|token)","not_found_re":r"(not found|no account)"},
    {"name":"Netlify",       "icon":"🌿", "url":"https://app.netlify.com/forgot",                                              "method":"post","payload":{"email":"{EMAIL}"},                                                          "found_re":r"(email sent|reset link)","not_found_re":r"(no account|not found)"},
    {"name":"Heroku",        "icon":"☁️", "url":"https://id.heroku.com/account/password/reset",                                "method":"post","payload":{"email":"{EMAIL}"},                                                          "found_re":r"(email sent|reset link)","not_found_re":r"(no account|not found)"},
    {"name":"Cloudflare",    "icon":"🔥", "url":"https://dash.cloudflare.com/forgot-password",                                 "method":"post","payload":{"email":"{EMAIL}"},                                                          "found_re":r"(email sent|reset link)","not_found_re":r"(no account|not found)"},
    {"name":"DigitalOcean",  "icon":"🌊", "url":"https://cloud.digitalocean.com/users/forgot_password",                        "method":"post","payload":{"email":"{EMAIL}"},                                                          "found_re":r"(email sent|reset link)","not_found_re":r"(no account|not found)"},
    {"name":"Notion",        "icon":"📝", "url":"https://www.notion.so/api/v3/sendEmail",                                      "method":"post","payload":{"email":"{EMAIL}","type":"login"},                                          "found_re":r"(email sent|magic link)","not_found_re":r"(not found|no account)"},
    {"name":"Figma",         "icon":"🎨", "url":"https://www.figma.com/api/reset_password",                                    "method":"post","payload":{"email":"{EMAIL}"},                                                          "found_re":r"(email sent|reset link)","not_found_re":r"(not found|no account)"},
    {"name":"Slack",         "icon":"💬", "url":"https://slack.com/forgot",                                                    "method":"post","payload":{"email":"{EMAIL}"},                                                          "found_re":r"(email sent|reset link)","not_found_re":r"(no account|not found)"},
    {"name":"Trello",        "icon":"📋", "url":"https://trello.com/forgot",                                                   "method":"post","payload":{"email":"{EMAIL}"},                                                          "found_re":r"(email sent|reset link)","not_found_re":r"(no account|not found)"},
    {"name":"Asana",         "icon":"🗂️", "url":"https://app.asana.com/api/1.0/users/me/forgot_password",                     "method":"post","payload":{"email":"{EMAIL}"},                                                          "found_re":r"(email sent|reset link)","not_found_re":r"(no account|not found)"},
    {"name":"Jira",          "icon":"🔵", "url":"https://id.atlassian.com/login/resetpassword",                                "method":"post","payload":{"username":"{EMAIL}"},                                                       "found_re":r"(email sent|reset link)","not_found_re":r"(no account|not found)"},
    {"name":"Bitbucket",     "icon":"🪣", "url":"https://bitbucket.org/account/password/reset/",                               "method":"post","payload":{"email":"{EMAIL}"},                                                          "found_re":r"(email sent|reset link)","not_found_re":r"(no account|not found)"},
    {"name":"Replit",        "icon":"🔁", "url":"https://replit.com/forgot",                                                   "method":"post","payload":{"email":"{EMAIL}"},                                                          "found_re":r"(email sent|reset link)","not_found_re":r"(no account|not found)"},
    {"name":"CodePen",       "icon":"✏️", "url":"https://codepen.io/forgotpassword",                                           "method":"post","payload":{"email":"{EMAIL}"},                                                          "found_re":r"(email sent|reset link)","not_found_re":r"(no account|not found)"},
    {"name":"Stack Overflow","icon":"📚", "url":"https://stackoverflow.com/users/account-recovery",                            "method":"post","payload":{"email":"{EMAIL}"},                                                          "found_re":r"(email sent|reset link)","not_found_re":r"(no account|not found)"},
    {"name":"npm",           "icon":"📦", "url":"https://www.npmjs.com/forgot",                                                "method":"post","payload":{"email":"{EMAIL}"},                                                          "found_re":r"(email sent|reset link)","not_found_re":r"(no account|not found)"},
    {"name":"PyPI",          "icon":"🐍", "url":"https://pypi.org/account/request-password-reset/",                            "method":"post","payload":{"email_or_username":"{EMAIL}"},                                             "found_re":r"(email sent|reset link)","not_found_re":r"(no account|not found)"},
    {"name":"Amazon",        "icon":"📦", "url":"https://www.amazon.com/ap/forgotpassword",                                    "method":"post","payload":{"email":"{EMAIL}"},                                                          "found_re":r"(email sent|reset link|verify)","not_found_re":r"(no account|not found)","inconclusive":True},
    {"name":"eBay",          "icon":"🛒", "url":"https://signin.ebay.com/ws/eBayISAPI.dll?ForgotPassword",                     "method":"post","payload":{"userid":"{EMAIL}"},                                                        "found_re":r"(email sent|reset link)","not_found_re":r"(no account|not found)"},
    {"name":"Etsy",          "icon":"🧶", "url":"https://www.etsy.com/forgot_password",                                        "method":"post","payload":{"email":"{EMAIL}"},                                                          "found_re":r"(email sent|reset link)","not_found_re":r"(no account|not found)"},
    {"name":"Shopify",       "icon":"🛍️", "url":"https://accounts.shopify.com/lookup",                                        "method":"post","payload":{"email":"{EMAIL}"},                                                          "found_re":r"(email sent|reset link|account found)","not_found_re":r"(no account|not found)"},
    {"name":"PayPal",        "icon":"💳", "url":"https://www.paypal.com/authflow/forgotpassword",                              "method":"post","payload":{"email":"{EMAIL}"},                                                          "found_re":r"(email sent|reset link)","not_found_re":r"(no account|not found)","inconclusive":True},
    {"name":"Stripe",        "icon":"💰", "url":"https://dashboard.stripe.com/login/forgot-password",                          "method":"post","payload":{"email":"{EMAIL}"},                                                          "found_re":r"(email sent|reset link)","not_found_re":r"(no account|not found)"},
    {"name":"Wise",          "icon":"💸", "url":"https://wise.com/forgotPassword",                                             "method":"post","payload":{"email":"{EMAIL}"},                                                          "found_re":r"(email sent|reset link)","not_found_re":r"(no account|not found)"},
    {"name":"Coinbase",      "icon":"🪙", "url":"https://www.coinbase.com/forgot-password",                                    "method":"post","payload":{"email":"{EMAIL}"},                                                          "found_re":r"(email sent|reset link)","not_found_re":r"(no account|not found)"},
    {"name":"Airbnb",        "icon":"🏠", "url":"https://www.airbnb.com/forgot_password",                                      "method":"post","payload":{"email":"{EMAIL}"},                                                          "found_re":r"(email sent|reset link)","not_found_re":r"(no account|not found)"},
    {"name":"Booking.com",   "icon":"🏨", "url":"https://account.booking.com/accounts/password/reset",                        "method":"post","payload":{"email":"{EMAIL}"},                                                          "found_re":r"(email sent|reset link)","not_found_re":r"(no account|not found)"},
    {"name":"Dropbox",       "icon":"📦", "url":"https://www.dropbox.com/forgot",                                              "method":"post","payload":{"email":"{EMAIL}"},                                                          "found_re":r"(email sent|reset link)","not_found_re":r"(no account|not found)"},
    {"name":"Evernote",      "icon":"🐘", "url":"https://www.evernote.com/Registration.action",                                "method":"post","payload":{"email":"{EMAIL}","action":"send_pw_reset"},                               "found_re":r"(email sent|reset link)","not_found_re":r"(no account|not found)"},
    {"name":"Todoist",       "icon":"✅", "url":"https://todoist.com/Users/forgotPassword",                                    "method":"post","payload":{"email":"{EMAIL}"},                                                          "found_re":r"(email sent|reset link)","not_found_re":r"(no account|not found)"},
    {"name":"Airtable",      "icon":"🗃️", "url":"https://airtable.com/forgotPassword",                                        "method":"post","payload":{"email":"{EMAIL}"},                                                          "found_re":r"(email sent|reset link)","not_found_re":r"(no account|not found)"},
    {"name":"Monday.com",    "icon":"🗓️", "url":"https://auth.monday.com/auth/login_monday/forgot_password",                  "method":"post","payload":{"email":"{EMAIL}"},                                                          "found_re":r"(email sent|reset link)","not_found_re":r"(no account|not found)"},
    {"name":"ClickUp",       "icon":"🖱️", "url":"https://app.clickup.com/forgot",                                             "method":"post","payload":{"email":"{EMAIL}"},                                                          "found_re":r"(email sent|reset link)","not_found_re":r"(no account|not found)"},
    {"name":"Adobe",         "icon":"🎨", "url":"https://adobeid-na1.services.adobe.com/renga/public/initPasswordReset",       "method":"post","payload":{"email":"{EMAIL}"},                                                          "found_re":r"(email sent|reset link)","not_found_re":r"(no account|not found)"},
    {"name":"Canva",         "icon":"✏️", "url":"https://www.canva.com/api/account/forgot-password",                           "method":"post","payload":{"email":"{EMAIL}"},                                                          "found_re":r"(email sent|reset link)","not_found_re":r"(no account|not found)"},
    {"name":"Behance",       "icon":"🖼️", "url":"https://www.behance.net/accounts/forgotpassword",                            "method":"post","payload":{"email":"{EMAIL}"},                                                          "found_re":r"(email sent|reset link)","not_found_re":r"(no account|not found)"},
    {"name":"Dribbble",      "icon":"🏀", "url":"https://dribbble.com/password/resets",                                        "method":"post","payload":{"email":"{EMAIL}"},                                                          "found_re":r"(email sent|reset link)","not_found_re":r"(no account|not found)"},
    {"name":"Miro",          "icon":"🎯", "url":"https://miro.com/api/v1/accounts/request-password-reset/",                   "method":"post","payload":{"email":"{EMAIL}"},                                                          "found_re":r"(email sent|reset link)","not_found_re":r"(no account|not found)"},
    {"name":"Zoom",          "icon":"🎦", "url":"https://zoom.us/forgot_password",                                             "method":"post","payload":{"email":"{EMAIL}"},                                                          "found_re":r"(email sent|reset link)","not_found_re":r"(no account|not found)"},
    {"name":"Epic Games",    "icon":"🎮", "url":"https://www.epicgames.com/id/api/resetPassword",                              "method":"post","payload":{"email":"{EMAIL}"},                                                          "found_re":r"(email sent|reset link)","not_found_re":r"(no account|not found)"},
    {"name":"EA / Origin",   "icon":"🎯", "url":"https://signin.ea.com/p/web2/resetPassword",                                  "method":"post","payload":{"email":"{EMAIL}"},                                                          "found_re":r"(email sent|reset link)","not_found_re":r"(no account|not found)"},
    {"name":"Roblox",        "icon":"🟥", "url":"https://auth.roblox.com/v1/users/forgot-password",                            "method":"post","payload":{"targetUsername":"{EMAIL}"},                                                "found_re":r"(email sent|reset link)","not_found_re":r"(no account|not found)"},
    {"name":"Chess.com",     "icon":"♟️", "url":"https://www.chess.com/recover",                                              "method":"post","payload":{"email":"{EMAIL}"},                                                          "found_re":r"(email sent|reset link)","not_found_re":r"(no account|not found)"},
    {"name":"Duolingo",      "icon":"🦜", "url":"https://www.duolingo.com/api/1/requestPasswordReset",                         "method":"post","payload":{"email":"{EMAIL}"},                                                          "found_re":r"(email sent|reset link)","not_found_re":r"(no account|not found)"},
    {"name":"Coursera",      "icon":"🎓", "url":"https://www.coursera.org/api/passwordResetV2.v1",                             "method":"post","payload":{"email":"{EMAIL}"},                                                          "found_re":r"(email sent|reset link)","not_found_re":r"(no account|not found)"},
    {"name":"Udemy",         "icon":"📚", "url":"https://www.udemy.com/api-2.0/auth/forgotpassword/",                          "method":"post","payload":{"email":"{EMAIL}"},                                                          "found_re":r"(email sent|reset link)","not_found_re":r"(no account|not found)"},
    {"name":"Medium",        "icon":"✍️", "url":"https://medium.com/m/signin",                                                 "method":"post","payload":{"email":"{EMAIL}"},                                                          "found_re":r"(email sent|magic link)","not_found_re":r"(no account|not found)"},
    {"name":"Substack",      "icon":"📰", "url":"https://substack.com/api/v1/email-login",                                     "method":"post","payload":{"email":"{EMAIL}","redirect":"/"},                                          "found_re":r"(email sent|magic link)","not_found_re":r"(no account|not found)"},
    {"name":"Goodreads",     "icon":"📚", "url":"https://www.goodreads.com/user/forgot_password",                              "method":"post","payload":{"user[email]":"{EMAIL}"},                                                   "found_re":r"(email sent|reset link)","not_found_re":r"(no account|not found)"},
    {"name":"MyFitnessPal",  "icon":"🏃", "url":"https://www.myfitnesspal.com/api/auth/forgot-password",                       "method":"post","payload":{"email":"{EMAIL}"},                                                          "found_re":r"(email sent|reset link)","not_found_re":r"(no account|not found)"},
    {"name":"Strava",        "icon":"🚴", "url":"https://www.strava.com/password/new",                                         "method":"post","payload":{"email":"{EMAIL}"},                                                          "found_re":r"(email sent|reset link)","not_found_re":r"(no account|not found)"},
    {"name":"Garmin",        "icon":"🏅", "url":"https://sso.garmin.com/sso/forgotPassword",                                   "method":"post","payload":{"username":"{EMAIL}"},                                                       "found_re":r"(email sent|reset link)","not_found_re":r"(no account|not found)"},
    {"name":"OpenAI",        "icon":"🤖", "url":"https://auth0.openai.com/dbconnections/change_password",                      "method":"post","payload":{"email":"{EMAIL}","connection":"Username-Password-Authentication","client_id":"TdJIcbe16WoTHtN95nyywh5E4yOo6ItG"},"found_re":r"(We've just sent|email sent)","not_found_re":r"(no account|not found)"},
    {"name":"Hugging Face",  "icon":"🤗", "url":"https://huggingface.co/users/password-reset",                                 "method":"post","payload":{"email":"{EMAIL}"},                                                          "found_re":r"(email sent|reset link)","not_found_re":r"(no account|not found)"},
    {"name":"Salesforce",    "icon":"☁️", "url":"https://login.salesforce.com/secur/forgotpassword.jsp",                       "method":"post","payload":{"un":"{EMAIL}"},                                                             "found_re":r"(email sent|reset link)","not_found_re":r"(no account|not found)"},
    {"name":"HubSpot",       "icon":"🧡", "url":"https://app.hubspot.com/login/forgot-password",                               "method":"post","payload":{"email":"{EMAIL}"},                                                          "found_re":r"(email sent|reset link)","not_found_re":r"(no account|not found)"},
    {"name":"Mailchimp",     "icon":"🐒", "url":"https://login.mailchimp.com/forgot-password/",                                "method":"post","payload":{"email":"{EMAIL}"},                                                          "found_re":r"(email sent|reset link)","not_found_re":r"(no account|not found)"},
    {"name":"Zapier",        "icon":"⚡", "url":"https://zapier.com/accounts/forgot-password/",                                "method":"post","payload":{"email":"{EMAIL}"},                                                          "found_re":r"(email sent|reset link)","not_found_re":r"(no account|not found)"},
    {"name":"Webflow",       "icon":"🌊", "url":"https://webflow.com/api/1.0/account/reset",                                   "method":"post","payload":{"email":"{EMAIL}"},                                                          "found_re":r"(email sent|reset link)","not_found_re":r"(no account|not found)"},
    {"name":"WordPress.com", "icon":"🔷", "url":"https://wordpress.com/wp-login.php?action=lostpassword",                      "method":"post","payload":{"user_login":"{EMAIL}"},                                                    "found_re":r"(email sent|reset link)","not_found_re":r"(no account|not found)"},
    {"name":"1Password",     "icon":"🔑", "url":"https://my.1password.com/auth/forgot",                                        "method":"post","payload":{"email":"{EMAIL}"},                                                          "found_re":r"(email sent|reset link)","not_found_re":r"(no account|not found)"},
    {"name":"LastPass",      "icon":"🔐", "url":"https://lastpass.com/recover.php",                                            "method":"post","payload":{"email":"{EMAIL}"},                                                          "found_re":r"(email sent|reset link)","not_found_re":r"(no account|not found)"},
    {"name":"Bitwarden",     "icon":"🛡️", "url":"https://vault.bitwarden.com/api/accounts/password-hint",                     "method":"post","payload":{"email":"{EMAIL}"},                                                          "found_re":r"(email sent|hint sent)","not_found_re":r"(no account|not found)"},
    {"name":"Dashlane",      "icon":"🔒", "url":"https://ws1.dashlane.com/account/requestEmailTokenToResetMP",                 "method":"post","payload":{"login":"{EMAIL}"},                                                          "found_re":r'"code":"SUCCESS"',"not_found_re":r'"code":"UNKNOWN_USER"'},
    {"name":"NordVPN",       "icon":"🛡️", "url":"https://api.nordvpn.com/v1/users/auth/forgot-password",                      "method":"post","payload":{"email":"{EMAIL}"},                                                          "found_re":r"(email sent|reset link)","not_found_re":r"(no account|not found)"},
    {"name":"GoDaddy",       "icon":"🐢", "url":"https://sso.godaddy.com/v1/account/credentials/reset",                       "method":"post","payload":{"email":"{EMAIL}"},                                                          "found_re":r"(email sent|reset link)","not_found_re":r"(no account|not found)"},
    {"name":"Namecheap",     "icon":"🏷️", "url":"https://www.namecheap.com/myaccount/reset-password/",                        "method":"post","payload":{"EmailAddress":"{EMAIL}"},                                                  "found_re":r"(email sent|reset link)","not_found_re":r"(no account|not found)"},
    {"name":"Hetzner",       "icon":"🖥️", "url":"https://accounts.hetzner.com/forgot_password",                               "method":"post","payload":{"_username":"{EMAIL}"},                                                      "found_re":r"(email sent|reset link)","not_found_re":r"(no account|not found)"},
    {"name":"SoundCloud",    "icon":"🎧", "url":"https://soundcloud.com/api/v2/password/resets",                               "method":"post","payload":{"email":"{EMAIL}"},                                                          "found_re":r"(email sent|reset link)","not_found_re":r"(no account|not found)"},
    {"name":"Bandcamp",      "icon":"🎸", "url":"https://bandcamp.com/api/login/1/forgot_password",                            "method":"post","payload":{"email":"{EMAIL}"},                                                          "found_re":r"(email sent|reset link)","not_found_re":r"(no account|not found)"},
    {"name":"Vimeo",         "icon":"🎞️", "url":"https://vimeo.com/forgot_password",                                          "method":"post","payload":{"email":"{EMAIL}"},                                                          "found_re":r"(email sent|reset link)","not_found_re":r"(no account|not found)"},
]

# ── Async probe engine ─────────────────────────────────────────────────────────

_PROBE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/json,*/*;q=0.9",
}
_PROBE_TIMEOUT = _aiohttp.ClientTimeout(total=10)

async def _probe_site(session, site, email):
    if site.get("inconclusive"):
        return {"site": site["name"], "icon": site["icon"], "email": email, "status": "inconclusive"}
    url     = site["url"]
    payload = {k: v.replace("{EMAIL}", email) for k, v in site.get("payload", {}).items()}
    try:
        if site.get("json"):
            resp = await session.post(url, json=payload, headers=_PROBE_HEADERS, timeout=_PROBE_TIMEOUT, ssl=False)
        elif site["method"] == "post":
            resp = await session.post(url, data=payload, headers=_PROBE_HEADERS, timeout=_PROBE_TIMEOUT, ssl=False)
        else:
            resp = await session.get(url, params=payload, headers=_PROBE_HEADERS, timeout=_PROBE_TIMEOUT, ssl=False)
        body = await resp.text(errors="replace")
        if _re.search(site["found_re"],     body, _re.IGNORECASE): status = "found"
        elif _re.search(site["not_found_re"], body, _re.IGNORECASE): status = "not_found"
        else: status = "inconclusive"
    except Exception:
        status = "inconclusive"
    return {"site": site["name"], "icon": site["icon"], "email": email, "status": status}

async def _probe_all(email):
    connector = _aiohttp.TCPConnector(ssl=False, limit=20)
    async with _aiohttp.ClientSession(connector=connector) as session:
        results = await _asyncio.gather(*[_probe_site(session, s, email) for s in _SITES], return_exceptions=True)
    return [r for r in results if isinstance(r, dict)]

def _run_probe(email):
    return _asyncio.run(_probe_all(email))

# ── HIBP helpers ───────────────────────────────────────────────────────────────

_HIGH   = {"passwords","credit cards","cvv","bank account numbers","pins","social security numbers"}
_MEDIUM = {"phone numbers","physical addresses","dates of birth","ip addresses","health records"}
_ICONS  = {"linkedin":"💼","adobe":"🎨","canva":"✏️","dropbox":"📦","twitch":"🟣",
           "myfitnesspal":"🏃","gravatar":"👤","twitter":"🐦","facebook":"📘",
           "instagram":"📸","snapchat":"👻","spotify":"🎵","netflix":"🎬",
           "reddit":"🤖","github":"🐙","amazon":"📦","discord":"🎮","slack":"💬"}

def _sev(classes):
    low = [c.lower() for c in classes]
    if any(c in _HIGH   for c in low): return "high"
    if any(c in _MEDIUM for c in low): return "medium"
    return "low"

def _icon(name):
    k = name.lower().replace(" ","").replace(".","").replace("-","")
    for key, v in _ICONS.items():
        if key in k: return v
    return "🌐"

def _hibp_breaches(email):
    if not HIBP_API_KEY: return []
    try:
        r = _requests.get(
            f"https://haveibeenpwned.com/api/v3/breachedaccount/{email}?truncateResponse=false",
            headers=HIBP_HEADERS, timeout=10)
        if r.status_code != 200: return []
        return [{"email": email, "site": b["Name"],
                 "date": b.get("BreachDate","")[:7],
                 "severity": _sev(b.get("DataClasses",[])),
                 "tags": b.get("DataClasses",[]),
                 "icon": _icon(b["Name"])} for b in r.json()]
    except Exception: return []

def _hibp_addresses(domain):
    if not HIBP_API_KEY: return [f"hello@{domain}"]
    try:
        r = _requests.get(f"https://haveibeenpwned.com/api/v3/breacheddomain/{domain}",
                          headers=HIBP_HEADERS, timeout=15)
        if r.status_code == 200:
            return [f"{a}@{domain}" for a in r.json().keys()]
        return [f"hello@{domain}"]
    except Exception: return [f"hello@{domain}"]

# ── Footprint routes ───────────────────────────────────────────────────────────

FOOTPRINT_PAGE = """<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
""" + EARLY_THEME + """
<title>Footprint — Friedutch+</title>
<style>""" + BASE_CSS + """
body { max-width:720px; margin:0 auto; padding:0 24px 100px; }
.top-bar-unified { position:sticky;top:0;z-index:100;display:flex;align-items:center;justify-content:space-between;padding:12px 0;margin-bottom:32px;backdrop-filter:blur(16px);-webkit-backdrop-filter:blur(16px);background:rgba(15,15,26,0.6);border-bottom:1px solid rgba(255,255,255,0.07); }
[data-theme="light"] .top-bar-unified { background:rgba(240,240,255,0.7);border-bottom:1px solid rgba(0,0,0,0.07); }
.app-brand { display:flex;align-items:center;gap:10px; }
.brand-icon { width:36px;height:36px;border-radius:10px;background:linear-gradient(135deg,var(--purple),var(--blue));display:flex;align-items:center;justify-content:center;font-size:18px; }
.brand-name { font-size:15px;font-weight:900; }
.brand-sub  { font-size:10px;color:var(--text3);font-weight:600; }
.top-right  { display:flex;align-items:center;gap:8px; }
.top-icon-btn { width:36px;height:36px;border-radius:10px;border:2px solid var(--border);background:var(--surface2);display:flex;align-items:center;justify-content:center;font-size:16px;cursor:pointer;font-family:'Nunito',sans-serif;font-weight:800;color:var(--text2);transition:all 0.2s;text-decoration:none; }
.top-icon-btn:hover { border-color:var(--purple); }
h1 { font-size:36px;font-weight:900;margin-bottom:8px; }
.page-sub { font-size:14px;color:var(--text2);font-weight:600;margin-bottom:28px; }
.metrics { display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:24px; }
.metric { background:var(--surface);border:2px solid var(--border);border-radius:var(--radius-sm);padding:14px 16px; }
.metric-label { font-size:10px;font-weight:800;letter-spacing:0.1em;text-transform:uppercase;color:var(--text3);margin-bottom:6px; }
.metric-val { font-size:28px;font-weight:900; }
.metric-val.danger { color:var(--red); }
.metric-val.warn   { color:var(--orange); }
.metric-val.info   { font-size:13px;color:var(--cyan);padding-top:7px;font-weight:800; }
.scan-zone-title { font-size:12px;font-weight:900;letter-spacing:0.1em;text-transform:uppercase;color:var(--text3);margin-bottom:14px; }
.scan-row { display:flex;gap:10px; }
.scan-hint { font-size:12px;font-weight:600;color:var(--text3);margin-top:10px; }
.scan-hint span { color:var(--cyan); }
.tabs { display:flex;gap:6px;margin-bottom:20px;flex-wrap:wrap; }
.tab-btn { padding:10px 18px;border-radius:var(--radius-xs);border:2px solid var(--border);background:var(--surface2);color:var(--text2);font-family:'Nunito',sans-serif;font-size:13px;font-weight:800;cursor:pointer;transition:all 0.2s; }
.tab-btn.active { background:var(--surface);border-color:rgba(120,75,160,0.4);color:var(--text); }
.tab-count { font-size:10px;font-weight:900;padding:1px 7px;border-radius:50px;margin-left:4px;background:rgba(120,75,160,0.15);color:var(--purple); }
.tab-btn.active .tab-count { background:linear-gradient(135deg,rgba(255,60,172,0.2),rgba(120,75,160,0.2));color:var(--pink); }
.tab-panel { display:none; }
.tab-panel.active { display:block; }
.filter-row { display:flex;gap:8px;margin-bottom:16px;flex-wrap:wrap;align-items:center; }
.filter-chip { font-size:12px;font-weight:800;padding:6px 14px;border-radius:50px;border:2px solid var(--border);background:var(--surface2);color:var(--text2);cursor:pointer;transition:all 0.2s; }
.filter-chip.active { border-color:rgba(120,75,160,0.5);color:var(--purple);background:rgba(120,75,160,0.1); }
.filter-chip:hover  { border-color:var(--purple);color:var(--purple); }
.filter-search { flex:1;min-width:140px;background:var(--surface2);border:2px solid var(--border);border-radius:var(--radius-xs);color:var(--text);font-family:'Nunito',sans-serif;font-size:13px;font-weight:600;padding:8px 14px;outline:none;transition:all 0.2s; }
.filter-search:focus { border-color:var(--purple); }
.filter-search::placeholder { color:var(--text3); }
.breach-card { background:var(--card);border:2px solid var(--border);border-radius:var(--radius-sm);padding:14px 16px;margin-bottom:10px;display:flex;align-items:flex-start;gap:14px;transition:all 0.2s; }
.breach-card:hover { box-shadow:0 4px 20px var(--shadow); }
.breach-card.sev-high   { border-left:3px solid var(--red); }
.breach-card.sev-medium { border-left:3px solid var(--orange); }
.breach-card.sev-low    { border-left:3px solid var(--yellow); }
.breach-icon { width:44px;height:44px;border-radius:14px;background:linear-gradient(135deg,rgba(255,68,68,0.15),rgba(255,107,53,0.1));display:flex;align-items:center;justify-content:center;font-size:22px;flex-shrink:0; }
.breach-body { flex:1;min-width:0; }
.breach-top  { display:flex;align-items:center;gap:8px;margin-bottom:3px; }
.breach-site { font-size:15px;font-weight:800; }
.breach-date { font-size:11px;font-weight:700;color:var(--text3);margin-left:auto; }
.breach-email { font-size:12px;font-weight:700;color:var(--cyan);margin-bottom:8px; }
.tags { display:flex;gap:5px;flex-wrap:wrap; }
.tag { font-size:10px;font-weight:800;padding:3px 9px;border-radius:50px;letter-spacing:0.04em; }
.tag-red    { background:rgba(255,68,68,0.12);color:var(--red);border:1px solid rgba(255,68,68,0.25); }
.tag-orange { background:rgba(255,107,53,0.12);color:var(--orange);border:1px solid rgba(255,107,53,0.25); }
.tag-gray   { background:var(--surface2);color:var(--text3);border:1px solid var(--border); }
.probe-card { background:var(--card);border:2px solid var(--border);border-radius:var(--radius-sm);padding:12px 16px;margin-bottom:8px;display:flex;align-items:center;gap:12px;transition:all 0.2s; }
.probe-card:hover { border-color:rgba(120,75,160,0.3); }
.probe-icon  { width:38px;height:38px;border-radius:10px;background:var(--surface2);display:flex;align-items:center;justify-content:center;font-size:18px;flex-shrink:0; }
.probe-info  { flex:1;min-width:0; }
.probe-site  { font-size:14px;font-weight:800;margin-bottom:2px; }
.probe-email { font-size:12px;font-weight:700;color:var(--cyan); }
.probe-status { display:flex;align-items:center;gap:6px;font-size:12px;font-weight:800;white-space:nowrap; }
.probe-status.found        { color:var(--red); }
.probe-status.not_found    { color:var(--green); }
.probe-status.inconclusive { color:var(--text3); }
.status-dot { width:8px;height:8px;border-radius:50%;flex-shrink:0; }
.dot-found        { background:var(--red); }
.dot-not_found    { background:var(--green); }
.dot-inconclusive { background:var(--text3); }
.addr-card { background:var(--card);border:2px solid var(--border);border-radius:var(--radius-sm);padding:14px 16px;margin-bottom:8px;display:flex;align-items:center;gap:14px; }
.addr-email { font-size:14px;font-weight:800;color:var(--cyan);flex:1; }
.addr-stat  { font-size:11px;font-weight:800;padding:3px 10px;border-radius:50px; }
.addr-breach { background:rgba(255,68,68,0.12);color:var(--red);border:1px solid rgba(255,68,68,0.2); }
.addr-clean  { background:rgba(0,200,130,0.12);color:var(--green);border:1px solid rgba(0,200,130,0.2); }
.legend { display:flex;gap:14px;margin-bottom:16px;flex-wrap:wrap; }
.legend-item { display:flex;align-items:center;gap:5px;font-size:11px;font-weight:800;color:var(--text3); }
.legend-dot  { width:10px;height:10px;border-radius:50%; }
.empty { text-align:center;padding:32px 0; }
.empty-icon { font-size:40px;margin-bottom:12px; }
.empty-text { font-size:14px;font-weight:600;color:var(--text3); }
.no-items { font-size:14px;font-weight:600;color:var(--text3);text-align:center;padding:20px 0; }
@media(max-width:520px){.metrics{grid-template-columns:repeat(2,1fr);}}
</style>
</head>
<body>
<div class="top-bar-unified">
  <div class="app-brand">
    <div class="brand-icon">🔍</div>
    <div><div class="brand-name">Footprint</div><div class="brand-sub">friedutch.plus</div></div>
  </div>
  <div class="top-right">
    <a class="top-icon-btn" href="/">🏠</a>
    <a class="top-icon-btn" href="/smartlock/logout" onclick="return confirm('Log out?')">👋</a>
    <button class="top-icon-btn" onclick="toggleTheme(this)" id="theme-btn">🔄</button>
  </div>
</div>
<h1>🔍 Footprint</h1>
<p class="page-sub">Track every account tied to your @friedutch.plus domain</p>
<div class="metrics">
  <div class="metric"><div class="metric-label">Addresses</div><div class="metric-val" id="m-addresses">—</div></div>
  <div class="metric"><div class="metric-label">Breaches</div><div class="metric-val danger" id="m-breaches">—</div></div>
  <div class="metric"><div class="metric-label">Accounts found</div><div class="metric-val warn" id="m-accounts">—</div></div>
  <div class="metric"><div class="metric-label">Last scan</div><div class="metric-val info" id="m-lastscan">Never</div></div>
</div>
<div class="zone zone-purple">
  <div class="scan-zone-title">🔎 Run a scan</div>
  <div class="scan-row">
    <input class="app-input" type="text" id="scan-input" placeholder="@friedutch.plus or hello@friedutch.plus" value="@friedutch.plus" onkeydown="if(event.key==='Enter')runScan()">
    <button class="sm-btn sm-purple" onclick="runScan()" id="scan-btn" style="background:linear-gradient(135deg,var(--purple),var(--blue));color:white;box-shadow:0 4px 16px rgba(120,75,160,0.35);">🚀 Scan</button>
  </div>
  <p class="scan-hint"><span>@friedutch.plus</span> scans the whole domain · <span>hello@friedutch.plus</span> scans one address</p>
</div>
<div class="tabs">
  <button class="tab-btn active" onclick="switchTab('breaches',this)">🔴 Breaches <span class="tab-count" id="tc-breaches">0</span></button>
  <button class="tab-btn" onclick="switchTab('probe',this)">🌐 Account probe <span class="tab-count" id="tc-probe">0</span></button>
  <button class="tab-btn" onclick="switchTab('addresses',this)">📧 Addresses <span class="tab-count" id="tc-addresses">0</span></button>
</div>
<div class="tab-panel active" id="panel-breaches">
  <div class="zone zone-red" style="background:linear-gradient(135deg,rgba(255,68,68,0.07),rgba(255,107,53,0.04));border-color:rgba(255,68,68,0.2);">
    <div class="zone-title">
      <div class="zone-title-left"><span>🚨</span> Breach results</div>
      <div style="display:flex;gap:6px;flex-wrap:wrap;">
        <span class="filter-chip active" onclick="setBFilter('all',this)">All</span>
        <span class="filter-chip" onclick="setBFilter('high',this)">High</span>
        <span class="filter-chip" onclick="setBFilter('medium',this)">Medium</span>
        <span class="filter-chip" onclick="setBFilter('low',this)">Low</span>
      </div>
    </div>
    <div class="legend">
      <div class="legend-item"><div class="legend-dot" style="background:var(--red)"></div>Passwords / cards</div>
      <div class="legend-item"><div class="legend-dot" style="background:var(--orange)"></div>Personal data</div>
      <div class="legend-item"><div class="legend-dot" style="background:var(--yellow)"></div>Metadata</div>
    </div>
    <div id="breach-list"><div class="empty"><div class="empty-icon">🔐</div><div class="empty-text">Run a scan to check for breaches</div></div></div>
  </div>
</div>
<div class="tab-panel" id="panel-probe">
  <div class="zone zone-purple">
    <div class="zone-title">
      <div class="zone-title-left"><span>🌐</span> Account probe</div>
      <span style="font-size:11px;font-weight:700;color:var(--text3);">Top sites</span>
    </div>
    <div class="filter-row">
      <input class="filter-search" type="text" id="probe-search" placeholder="Search sites…" oninput="renderProbe()">
      <span class="filter-chip active" onclick="setPFilter('all',this)">All</span>
      <span class="filter-chip" onclick="setPFilter('found',this)">Found</span>
      <span class="filter-chip" onclick="setPFilter('not_found',this)">Clean</span>
      <span class="filter-chip" onclick="setPFilter('inconclusive',this)">Inconclusive</span>
    </div>
    <div id="probe-list"><div class="empty"><div class="empty-icon">🌐</div><div class="empty-text">Run a scan to probe accounts</div></div></div>
  </div>
</div>
<div class="tab-panel" id="panel-addresses">
  <div class="zone zone-cyan" style="background:linear-gradient(135deg,rgba(0,210,255,0.07),rgba(43,134,197,0.05));border-color:rgba(0,210,255,0.15);">
    <div class="zone-title"><div class="zone-title-left"><span>📧</span> Domain addresses</div></div>
    <div id="addr-list"><div class="empty"><div class="empty-icon">📭</div><div class="empty-text">Run a scan to discover addresses</div></div></div>
  </div>
</div>
<input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
<script>
""" + THEME_JS + """
const S={breaches:[],probes:[],addresses:[],bFilter:'all',pFilter:'all'};
function switchTab(name,btn){document.querySelectorAll('.tab-panel').forEach(p=>p.classList.remove('active'));document.querySelectorAll('.tab-btn').forEach(b=>b.classList.remove('active'));document.getElementById('panel-'+name).classList.add('active');btn.classList.add('active');}
async function runScan(){
  const val=document.getElementById('scan-input').value.trim();
  if(!val)return;
  const btn=document.getElementById('scan-btn');
  btn.textContent='⏳ Scanning…';btn.disabled=true;
  try{
    const res=await fetch('/footprint/scan',{method:'POST',headers:{'Content-Type':'application/json','X-CSRFToken':document.querySelector('input[name="csrf_token"]').value},body:JSON.stringify({target:val})});
    const data=await res.json();
    S.breaches=data.breaches||[];S.probes=data.probes||[];S.addresses=data.addresses||[];
    document.getElementById('m-lastscan').textContent=data.scanned_at||'just now';
    updateMetrics();renderBreaches();renderProbe();renderAddresses();
  }catch(e){console.error(e);}finally{btn.textContent='🚀 Scan';btn.disabled=false;}
}
function updateMetrics(){
  document.getElementById('m-addresses').textContent=S.addresses.length;
  document.getElementById('m-breaches').textContent=S.breaches.length;
  document.getElementById('m-accounts').textContent=S.probes.filter(p=>p.status==='found').length;
  document.getElementById('tc-breaches').textContent=S.breaches.length;
  document.getElementById('tc-probe').textContent=S.probes.length;
  document.getElementById('tc-addresses').textContent=S.addresses.length;
}
function tagClass(t){const l=t.toLowerCase();if(l.includes('password')||l.includes('credit'))return 'tag-red';if(l.includes('phone')||l.includes('birth')||l.includes('name')||l.includes('locat'))return 'tag-orange';return 'tag-gray';}
function renderBreaches(){
  let items=S.breaches;
  if(S.bFilter!=='all')items=items.filter(b=>b.severity===S.bFilter);
  const el=document.getElementById('breach-list');
  if(!items.length){el.innerHTML='<div class="no-items">No breaches match this filter 🎉</div>';return;}
  el.innerHTML=items.map(b=>`<div class="breach-card sev-${b.severity}"><div class="breach-icon">${b.icon}</div><div class="breach-body"><div class="breach-top"><span class="breach-site">${b.site}</span><span class="breach-date">${b.date}</span></div><div class="breach-email">${b.email}</div><div class="tags">${b.tags.map(t=>`<span class="tag ${tagClass(t)}">${t}</span>`).join('')}</div></div></div>`).join('');
}
function setBFilter(f,el){S.bFilter=f;document.querySelectorAll('#panel-breaches .filter-chip').forEach(c=>c.classList.remove('active'));el.classList.add('active');renderBreaches();}
const STATUS_LABEL={found:'Account found',not_found:'No account',inconclusive:'Inconclusive'};
function renderProbe(){
  const search=(document.getElementById('probe-search').value||'').toLowerCase();
  let items=S.probes;
  if(S.pFilter!=='all')items=items.filter(p=>p.status===S.pFilter);
  if(search)items=items.filter(p=>p.site.toLowerCase().includes(search)||p.email.toLowerCase().includes(search));
  const el=document.getElementById('probe-list');
  if(!items.length){el.innerHTML='<div class="no-items">No results match this filter</div>';return;}
  el.innerHTML=items.map(p=>`<div class="probe-card"><div class="probe-icon">${p.icon}</div><div class="probe-info"><div class="probe-site">${p.site}</div><div class="probe-email">${p.email}</div></div><div class="probe-status ${p.status}"><div class="status-dot dot-${p.status}"></div>${STATUS_LABEL[p.status]||p.status}</div></div>`).join('');
}
function setPFilter(f,el){S.pFilter=f;document.querySelectorAll('#panel-probe .filter-chip').forEach(c=>c.classList.remove('active'));el.classList.add('active');renderProbe();}
function renderAddresses(){
  const el=document.getElementById('addr-list');
  if(!S.addresses.length){el.innerHTML='<div class="no-items">No addresses found</div>';return;}
  el.innerHTML=S.addresses.map(a=>`<div class="addr-card"><span style="font-size:20px;">📧</span><span class="addr-email">${a.email}</span>${a.breaches>0?`<span class="addr-stat addr-breach">⚠️ ${a.breaches} breach${a.breaches>1?'es':''}</span>`:`<span class="addr-stat addr-clean">✅ Clean</span>`}</div>`).join('');
}
</script>
</body>
</html>"""

@app.route("/footprint/")
def footprint_index():
    if not is_admin(): return redirect(url_for("smartlock_login"))
    return render_template_string(FOOTPRINT_PAGE)

@app.route("/footprint/scan", methods=["POST"])
@csrf.exempt
def footprint_scan():
    if not is_admin(): return jsonify({"error": "unauthorized"}), 401
    target = _bleach.clean(request.json.get("target", "").strip().lower(), tags=[], strip=True)[:200]
    if not target: return jsonify({"error": "no target"}), 400
    is_domain = target.startswith("@") or "@" not in target
    domain    = target.lstrip("@") if is_domain else target.split("@")[1]
    addresses = _hibp_addresses(domain) if is_domain else [target]
    all_breaches = []
    for email in addresses:
        all_breaches.extend(_hibp_breaches(email))
    all_probes = []
    for email in addresses:
        all_probes.extend(_run_probe(email))
    breach_counts = {}
    for b in all_breaches:
        breach_counts[b["email"]] = breach_counts.get(b["email"], 0) + 1
    all_addresses = [{"email": e, "breaches": breach_counts.get(e, 0)} for e in addresses]
    db = _sqlite3.connect(FOOTPRINT_DB_PATH)
    cur = db.execute("INSERT INTO scans (target, scan_type) VALUES (?, ?)", (target, "domain" if is_domain else "address"))
    scan_id = cur.lastrowid
    for b in all_breaches:
        db.execute("INSERT INTO breaches (scan_id, email, site, breach_date, severity, data_classes) VALUES (?,?,?,?,?,?)",
                   (scan_id, b["email"], b["site"], b.get("date"), b.get("severity"), ",".join(b.get("tags",[]))))
    for p in all_probes:
        db.execute("INSERT INTO probe_results (scan_id, email, site, status) VALUES (?,?,?,?)",
                   (scan_id, p["email"], p["site"], p["status"]))
    db.commit()
    db.close()
    return jsonify({"breaches": all_breaches, "probes": all_probes, "addresses": all_addresses,
                    "scanned_at": datetime.datetime.utcnow().strftime("%d %b %Y, %H:%M UTC")})

if __name__ == "__main__":
    init_db()
    _init_footprint_db()
    app.run(host="127.0.0.1", port=5001)
