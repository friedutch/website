import hashlib
import sqlite3

import resend
from flask import current_app, url_for

from .config import get_mail_from_address, get_resend_api_key, get_serializer
from .db import DB_PATH


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


def send_admin_magic_link(email, captcha_code):
    token = get_serializer().dumps(email, salt="admin-magic-login")
    link = url_for("smartlock_verify", token=token, _external=True)
    error = send_smartlock_email(
        {
            "from": get_mail_from_address(),
            "to": email,
            "subject": "Smart Lock — Admin Access 🔐",
            "html": (
                "<p>Click to access the admin panel. Expires in 5 minutes, single use.</p>"
                f"<p><a href='{link}'>{link}</a></p>"
            ),
        }
    )
    if error:
        return error
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    db = sqlite3.connect(DB_PATH)
    db.execute(
        "INSERT OR REPLACE INTO match_numbers (token_hash, number) VALUES (?, ?)",
        (token_hash, captcha_code),
    )
    db.commit()
    db.close()
    return None


def send_verification_link(new_email, captcha_code):
    token = get_serializer().dumps(new_email, salt="admin-email-change")
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
    db.execute(
        "INSERT OR REPLACE INTO match_numbers (token_hash, number) VALUES (?, ?)",
        (token_hash, captcha_code),
    )
    db.commit()
    db.close()
    return None
