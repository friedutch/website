import os
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path

from flask import abort, current_app, redirect, request, send_file, url_for
from werkzeug.utils import secure_filename

from app.rendering import render_page
from projects.smartlock.smartlock import require_admin_login


CLOUD_STORAGE_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cloud_storage.db")
DEFAULT_STORAGE_ROOT = "/Users/administrator/Storage/cloud_storage"
MAX_UPLOAD_BYTES = 1024 * 1024 * 1024


def get_storage_root():
    root = os.getenv("CLOUD_STORAGE_ROOT", DEFAULT_STORAGE_ROOT).strip() or DEFAULT_STORAGE_ROOT
    path = Path(root)
    path.mkdir(parents=True, exist_ok=True)
    return path


def init_cloud_storage_db():
    db = sqlite3.connect(CLOUD_STORAGE_DB_PATH)
    db.execute(
        """CREATE TABLE IF NOT EXISTS files (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        original_name TEXT NOT NULL,
        stored_name TEXT UNIQUE NOT NULL,
        mime_type TEXT,
        size_bytes INTEGER NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )"""
    )
    db.commit()
    db.close()


def _human_size(size_bytes):
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(size_bytes)
    for unit in units:
        if size < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1024
    return "Unknown"


def _get_db():
    db = sqlite3.connect(CLOUD_STORAGE_DB_PATH)
    db.row_factory = sqlite3.Row
    return db


def _list_files():
    db = _get_db()
    rows = db.execute("SELECT * FROM files ORDER BY created_at DESC, id DESC").fetchall()
    db.close()
    files = []
    for row in rows:
        files.append(
            {
                "id": row["id"],
                "original_name": row["original_name"],
                "mime_type": row["mime_type"] or "Unknown",
                "size_bytes": row["size_bytes"],
                "size_label": _human_size(row["size_bytes"]),
                "created_at": row["created_at"][:19].replace("T", " "),
            }
        )
    return files


def _storage_metrics(files):
    total_bytes = sum(file["size_bytes"] for file in files)
    return {
        "file_count": len(files),
        "total_size_label": _human_size(total_bytes),
        "latest_upload": files[0]["created_at"] + " UTC" if files else "Never",
    }


def _render_cloud_storage(message=None, error=None):
    files = _list_files()
    metrics = _storage_metrics(files)
    return render_page(
        "cloud_storage.html",
        page_name="Cloud Storage — Friedutch Plus",
        files=files,
        metrics=metrics,
        storage_root=str(get_storage_root()),
        message=message,
        error=error,
        noindex=True,
    )


def init_cloud_storage(app):
    @app.route("/cloud-storage/")
    def cloud_storage_index():
        admin_redirect = require_admin_login()
        if admin_redirect:
            return admin_redirect
        return _render_cloud_storage()

    @app.route("/cloud-storage/upload", methods=["POST"])
    def cloud_storage_upload():
        admin_redirect = require_admin_login()
        if admin_redirect:
            return admin_redirect

        uploaded_file = request.files.get("file")
        if not uploaded_file or not uploaded_file.filename:
            return _render_cloud_storage(error="Choose a file to upload.")

        original_name = secure_filename(uploaded_file.filename).strip()
        if not original_name:
            return _render_cloud_storage(error="That filename is not allowed.")

        content_length = request.content_length or 0
        if content_length > MAX_UPLOAD_BYTES:
            return _render_cloud_storage(error="That file is too large for this page.")

        stored_name = f"{uuid.uuid4().hex}_{original_name}"
        destination = get_storage_root() / stored_name

        try:
            uploaded_file.save(destination)
            saved_size = destination.stat().st_size
        except OSError:
            current_app.logger.exception("Failed to save uploaded cloud storage file")
            return _render_cloud_storage(error="Upload failed while saving the file.")

        db = _get_db()
        db.execute(
            """
            INSERT INTO files (original_name, stored_name, mime_type, size_bytes)
            VALUES (?, ?, ?, ?)
            """,
            (original_name, stored_name, (uploaded_file.mimetype or "").strip(), saved_size),
        )
        db.commit()
        db.close()
        return _render_cloud_storage(message="File uploaded.")

    @app.route("/cloud-storage/download/<int:file_id>")
    def cloud_storage_download(file_id):
        admin_redirect = require_admin_login()
        if admin_redirect:
            return admin_redirect

        db = _get_db()
        row = db.execute("SELECT * FROM files WHERE id = ?", (file_id,)).fetchone()
        db.close()
        if not row:
            abort(404)

        file_path = get_storage_root() / row["stored_name"]
        if not file_path.is_file():
            abort(404)

        return send_file(
            file_path,
            as_attachment=True,
            download_name=row["original_name"],
            mimetype=(row["mime_type"] or "application/octet-stream"),
        )

    @app.route("/cloud-storage/delete/<int:file_id>", methods=["POST"])
    def cloud_storage_delete(file_id):
        admin_redirect = require_admin_login()
        if admin_redirect:
            return admin_redirect

        db = _get_db()
        row = db.execute("SELECT * FROM files WHERE id = ?", (file_id,)).fetchone()
        if not row:
            db.close()
            return redirect(url_for("cloud_storage_index"))

        file_path = get_storage_root() / row["stored_name"]
        db.execute("DELETE FROM files WHERE id = ?", (file_id,))
        db.commit()
        db.close()

        try:
            if file_path.exists():
                file_path.unlink()
        except OSError:
            current_app.logger.exception("Failed to delete cloud storage file from disk")
            return _render_cloud_storage(error="Metadata was removed, but the file could not be deleted from disk.")

        return redirect(url_for("cloud_storage_index"))
