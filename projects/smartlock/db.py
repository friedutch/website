import os
import sqlite3

from flask import g


DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "smartlock.db")


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


def close_db(error=None):
    db = g.pop("db", None)
    if db:
        db.close()


def init_db():
    db = sqlite3.connect(DB_PATH)
    db.execute(
        """CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        passcode TEXT UNIQUE NOT NULL,
        rfid_enabled INTEGER DEFAULT 0,
        rfid_id TEXT DEFAULT NULL,
        fingerprint_enabled INTEGER DEFAULT 0,
        fingerprint_id TEXT DEFAULT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )"""
    )
    db.execute(
        """CREATE TABLE IF NOT EXISTS used_tokens (
        token TEXT PRIMARY KEY,
        used_at TEXT DEFAULT CURRENT_TIMESTAMP
    )"""
    )
    db.execute(
        """CREATE TABLE IF NOT EXISTS match_numbers (
        token_hash TEXT PRIMARY KEY,
        number TEXT NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )"""
    )
    db.execute(
        """CREATE TABLE IF NOT EXISTS login_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        method TEXT NOT NULL,
        method_id TEXT,
        success INTEGER NOT NULL,
        user_name TEXT,
        ip TEXT,
        location TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        user_agent TEXT
    )"""
    )
    db.execute(
        """CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    )"""
    )
    db.execute(
        """CREATE TABLE IF NOT EXISTS active_sessions (
        session_token TEXT PRIMARY KEY,
        ip TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        last_active TEXT DEFAULT CURRENT_TIMESTAMP,
        user_agent TEXT
    )"""
    )
    db.execute(
        """CREATE TABLE IF NOT EXISTS join_tokens (
        token TEXT PRIMARY KEY,
        number TEXT NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )"""
    )
    db.execute(
        """CREATE TABLE IF NOT EXISTS number_attempts (
        token_hash TEXT PRIMARY KEY,
        attempts INTEGER DEFAULT 0
    )"""
    )
    defaults = {"admin_email": os.getenv("MAIL_TO", "")}
    for key, value in defaults.items():
        if not db.execute("SELECT 1 FROM settings WHERE key = ?", (key,)).fetchone():
            db.execute("INSERT INTO settings (key, value) VALUES (?, ?)", (key, value))
    db.commit()
    db.close()


def get_setting(key):
    row = get_db().execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None


def set_setting(key, value):
    get_db().execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
    get_db().commit()


def get_admin_email():
    return get_setting("admin_email")


def get_pending_email():
    return get_setting("pending_admin_email")


def get_pending_sent_at():
    return get_setting("pending_admin_email_sent_at")
