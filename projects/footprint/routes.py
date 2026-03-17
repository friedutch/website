import os
import sqlite3
import datetime
import bleach
import requests as http
from flask import (Blueprint, request, redirect, url_for, session,
                   render_template_string, g, jsonify)
from flask_wtf.csrf import generate_csrf
from dotenv import load_dotenv

load_dotenv()

HIBP_API_KEY = os.getenv("HIBP_API_KEY", "")
HIBP_HEADERS = {
    "hibp-api-key": HIBP_API_KEY,
    "user-agent":   "friedutch-footprint/1.0",
}

footprint_bp = Blueprint("footprint", __name__)

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "footprint.db")

# ── DB ─────────────────────────────────────────────────────────────────────────

def get_db():
    if "footprint_db" not in g:
        g.footprint_db = sqlite3.connect(DB_PATH)
        g.footprint_db.row_factory = sqlite3.Row
    return g.footprint_db

@footprint_bp.teardown_app_request
def close_db(e=None):
    db = g.pop("footprint_db", None)
    if db:
        db.close()

def init_db():
    db = sqlite3.connect(DB_PATH)
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
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (scan_id) REFERENCES scans(id)
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS probe_results (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        scan_id INTEGER NOT NULL,
        email TEXT NOT NULL,
        site TEXT NOT NULL,
        status TEXT NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (scan_id) REFERENCES scans(id)
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS addresses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        scan_id INTEGER NOT NULL,
        email TEXT NOT NULL,
        breach_count INTEGER DEFAULT 0,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (scan_id) REFERENCES scans(id)
    )""")
    db.commit()
    db.close()

@footprint_bp.context_processor
def inject_csrf():
    return dict(csrf_token=generate_csrf)

# ── Routes ─────────────────────────────────────────────────────────────────────

from projects.footprint.templates import FOOTPRINT_PAGE

@footprint_bp.route("/")
def index():
    from projects.smartlock.routes import is_admin
    if not is_admin():
        return redirect(url_for("smartlock.login"))
    return render_template_string(FOOTPRINT_PAGE)

@footprint_bp.route("/scan", methods=["POST"])
def scan():
    from projects.smartlock.routes import is_admin
    if not is_admin():
        return jsonify({"error": "unauthorized"}), 401

    target = bleach.clean(request.json.get("target", "").strip().lower(), tags=[], strip=True)[:200]
    if not target:
        return jsonify({"error": "no target"}), 400

    # target is "@friedutch.plus" → domain scan
    # target is "hello@friedutch.plus" → single address scan
    is_domain = target.startswith("@") or "@" not in target
    domain    = target.lstrip("@") if is_domain else target.split("@")[1]
    addresses = _hibp_domain_addresses(domain) if is_domain else [target]

    # ── 1. HIBP breach lookup ──────────────────────────────────────────────
    all_breaches = []
    for email in addresses:
        all_breaches.extend(_hibp_breaches_for_email(email))

    # ── 2. Probe engine ────────────────────────────────────────────────────
    from projects.footprint.footprint import probe_email
    all_probes = []
    for email in addresses:
        all_probes.extend(probe_email(email))

    # ── 3. Build address summary ───────────────────────────────────────────
    breach_counts = {}
    for b in all_breaches:
        breach_counts[b["email"]] = breach_counts.get(b["email"], 0) + 1
    all_addresses = [
        {"email": e, "breaches": breach_counts.get(e, 0)}
        for e in addresses
    ]

    # ── 4. Persist to DB ───────────────────────────────────────────────────
    db = get_db()
    scan_type = "domain" if is_domain else "address"
    cur = db.execute(
        "INSERT INTO scans (target, scan_type) VALUES (?, ?)",
        (target, scan_type)
    )
    scan_id = cur.lastrowid
    for b in all_breaches:
        db.execute(
            "INSERT INTO breaches (scan_id, email, site, breach_date, severity, data_classes) VALUES (?,?,?,?,?,?)",
            (scan_id, b["email"], b["site"], b.get("date"), b.get("severity"), ",".join(b.get("tags", [])))
        )
    for p in all_probes:
        db.execute(
            "INSERT INTO probe_results (scan_id, email, site, status) VALUES (?,?,?,?)",
            (scan_id, p["email"], p["site"], p["status"])
        )
    for a in all_addresses:
        db.execute(
            "INSERT INTO addresses (scan_id, email, breach_count) VALUES (?,?,?)",
            (scan_id, a["email"], a["breaches"])
        )
    db.commit()

    return jsonify({
        "breaches":   all_breaches,
        "probes":     all_probes,
        "addresses":  all_addresses,
        "scanned_at": datetime.datetime.utcnow().strftime("%d %b %Y, %H:%M UTC"),
    })


# ── HIBP helpers ───────────────────────────────────────────────────────────────

# Maps HIBP data class names → severity tier
_HIGH_CLASSES   = {"passwords", "credit cards", "cvv", "bank account numbers",
                   "pins", "social security numbers", "passport numbers"}
_MEDIUM_CLASSES = {"phone numbers", "physical addresses", "dates of birth",
                   "government issued ids", "health records", "ip addresses",
                   "device information"}

def _severity(data_classes: list[str]) -> str:
    low = [c.lower() for c in data_classes]
    if any(c in _HIGH_CLASSES   for c in low): return "high"
    if any(c in _MEDIUM_CLASSES for c in low): return "medium"
    return "low"

# Site name → emoji icon (best-effort)
_ICONS = {
    "linkedin": "💼", "adobe": "🎨", "canva": "✏️", "dropbox": "📦",
    "twitch": "🟣", "myfitnesspal": "🏃", "gravatar": "👤",
    "twitter": "🐦", "facebook": "📘", "instagram": "📸",
    "snapchat": "👻", "tumblr": "📓", "last.fm": "🎵",
    "spotify": "🎵", "netflix": "🎬", "reddit": "🤖",
    "github": "🐙", "bitbucket": "🪣", "trello": "📋",
    "slack": "💬", "vercel": "▲", "cloudflare": "🔥",
    "amazon": "📦", "ebay": "🛒", "paypal": "💳",
    "steam": "🎮", "epicgames": "🎮", "discord": "🎮",
    "duolingo": "🦜", "coursera": "🎓", "udemy": "📚",
    "medium": "✍️", "wordpress": "🔷", "wix": "🔵",
    "shopify": "🛍️", "squarespace": "⬛", "mailchimp": "🐒",
    "hubspot": "🧡", "stripe": "💰", "coinbase": "🪙",
    "zoom": "🎦", "skype": "🔵",
}

def _icon_for(name: str) -> str:
    key = name.lower().replace(" ", "").replace(".", "").replace("-", "")
    for k, v in _ICONS.items():
        if k in key:
            return v
    return "🌐"

def _hibp_breaches_for_email(email: str) -> list[dict]:
    """Fetch breaches for a single email from HIBP API v3."""
    if not HIBP_API_KEY:
        return []
    try:
        url  = f"https://haveibeenpwned.com/api/v3/breachedaccount/{email}?truncateResponse=false"
        resp = http.get(url, headers=HIBP_HEADERS, timeout=10)
        if resp.status_code == 404:
            return []   # no breaches
        if resp.status_code == 401:
            return [{"email": email, "site": "HIBP auth error", "date": "", "severity": "low",
                     "tags": ["Check HIBP_API_KEY in .env"], "icon": "⚠️"}]
        if resp.status_code != 200:
            return []
        results = []
        for breach in resp.json():
            data_classes = breach.get("DataClasses", [])
            results.append({
                "email":    email,
                "site":     breach.get("Name", "Unknown"),
                "date":     breach.get("BreachDate", "")[:7],   # "YYYY-MM" → strip day
                "severity": _severity(data_classes),
                "tags":     data_classes,
                "icon":     _icon_for(breach.get("Name", "")),
            })
        return results
    except Exception:
        return []

def _hibp_domain_addresses(domain: str) -> list[str]:
    """
    Use HIBP domain search to get all breached addresses on the domain.
    Requires the HIBP domain search subscription (separate from basic API).
    Falls back to just the domain's catch-all address if unavailable.
    """
    if not HIBP_API_KEY:
        return [f"hello@{domain}"]
    try:
        url  = f"https://haveibeenpwned.com/api/v3/breacheddomain/{domain}"
        resp = http.get(url, headers=HIBP_HEADERS, timeout=15)
        if resp.status_code == 200:
            # Returns { "alias": ["BreachName", ...], ... }
            aliases  = resp.json().keys()
            return [f"{alias}@{domain}" for alias in aliases]
        # 404 = domain not found in any breach, still probe it
        return [f"hello@{domain}"]
    except Exception:
        return [f"hello@{domain}"]
