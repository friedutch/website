import os
import sqlite3
import uuid
import hashlib
import datetime
from pathlib import Path

from flask import abort, current_app, redirect, request, send_file, url_for
from werkzeug.utils import secure_filename

from app.rendering import render_page
from projects.smartlock.smartlock import require_admin_login


CLOUD_STORAGE_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cloud_storage.db")
DEFAULT_STORAGE_ROOT = "/Users/administrator/Storage/cloud_storage"
MAX_UPLOAD_BYTES = 1024 * 1024 * 1024
MAX_TOTAL_STORAGE_BYTES = 10 * 1024 * 1024 * 1024


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
        checksum_sha256 TEXT,
        download_count INTEGER NOT NULL DEFAULT 0,
        last_downloaded_at TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )"""
    )
    existing_columns = {
        row[1] for row in db.execute("PRAGMA table_info(files)").fetchall()
    }
    if "checksum_sha256" not in existing_columns:
        db.execute("ALTER TABLE files ADD COLUMN checksum_sha256 TEXT")
    if "download_count" not in existing_columns:
        db.execute("ALTER TABLE files ADD COLUMN download_count INTEGER NOT NULL DEFAULT 0")
    if "last_downloaded_at" not in existing_columns:
        db.execute("ALTER TABLE files ADD COLUMN last_downloaded_at TEXT")
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


def _sha256_for_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _list_files():
    db = _get_db()
    rows = db.execute("SELECT * FROM files ORDER BY created_at DESC, id DESC").fetchall()
    db.close()
    storage_root = get_storage_root()
    files = []
    for row in rows:
        file_path = storage_root / row["stored_name"]
        checksum = row["checksum_sha256"] or ""
        files.append(
            {
                "id": row["id"],
                "original_name": row["original_name"],
                "mime_type": row["mime_type"] or "Unknown",
                "size_bytes": row["size_bytes"],
                "size_label": _human_size(row["size_bytes"]),
                "created_at": row["created_at"][:19].replace("T", " "),
                "download_count": row["download_count"] or 0,
                "last_downloaded_at": (
                    row["last_downloaded_at"][:19].replace("T", " ") + " UTC"
                    if row["last_downloaded_at"]
                    else "Never"
                ),
                "checksum_sha256": checksum,
                "checksum_short": checksum[:12] if checksum else "Pending",
                "missing": not file_path.is_file(),
            }
        )
    return files


def _storage_metrics(files):
    total_bytes = sum(file["size_bytes"] for file in files)
    return {
        "file_count": len(files),
        "total_size_bytes": total_bytes,
        "total_size_label": _human_size(total_bytes),
        "latest_upload": files[0]["created_at"] + " UTC" if files else "Never",
        "missing_count": sum(1 for file in files if file["missing"]),
        "storage_limit_label": _human_size(MAX_TOTAL_STORAGE_BYTES),
        "remaining_size_label": _human_size(max(0, MAX_TOTAL_STORAGE_BYTES - total_bytes)),
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


def _validate_upload_file(uploaded_file):
    if not uploaded_file or not uploaded_file.filename:
        return None, "Choose at least one file to upload."

    original_name = secure_filename(uploaded_file.filename).strip()
    if not original_name:
        return None, "One of the selected filenames is not allowed."

    return original_name, None


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

        uploaded_files = [file for file in request.files.getlist("file") if file and file.filename]
        if not uploaded_files:
            return _render_cloud_storage(error="Choose at least one file to upload.")

        content_length = request.content_length or 0
        if content_length > MAX_TOTAL_STORAGE_BYTES:
            return _render_cloud_storage(error="That request is too large for Cloud Storage.")

        current_usage = _storage_metrics(_list_files())["total_size_bytes"]
        if current_usage >= MAX_TOTAL_STORAGE_BYTES:
            return _render_cloud_storage(error="Cloud Storage is full. Delete files before uploading more.")

        storage_root = get_storage_root()
        pending_inserts = []
        saved_paths = []
        total_new_usage = current_usage

        try:
            for uploaded_file in uploaded_files:
                original_name, validation_error = _validate_upload_file(uploaded_file)
                if validation_error:
                    raise ValueError(validation_error)

                stored_name = f"{uuid.uuid4().hex}_{original_name}"
                destination = storage_root / stored_name
                uploaded_file.save(destination)
                saved_paths.append(destination)

                saved_size = destination.stat().st_size
                if saved_size > MAX_UPLOAD_BYTES:
                    raise ValueError(f"{original_name} is too large. Individual files must stay within 1.0 GB.")

                total_new_usage += saved_size
                if total_new_usage > MAX_TOTAL_STORAGE_BYTES:
                    raise ValueError("That upload would exceed the 10.0 GB storage limit.")

                checksum_sha256 = _sha256_for_file(destination)
                pending_inserts.append(
                    (original_name, stored_name, (uploaded_file.mimetype or "").strip(), saved_size, checksum_sha256)
                )
        except ValueError as error:
            for path in saved_paths:
                path.unlink(missing_ok=True)
            return _render_cloud_storage(error=str(error))
        except OSError:
            current_app.logger.exception("Failed to save uploaded cloud storage files")
            for path in saved_paths:
                path.unlink(missing_ok=True)
            return _render_cloud_storage(error="Upload failed while saving one of the files.")

        db = _get_db()
        db.executemany(
            """
            INSERT INTO files (original_name, stored_name, mime_type, size_bytes, checksum_sha256)
            VALUES (?, ?, ?, ?, ?)
            """,
            pending_inserts,
        )
        db.commit()
        db.close()
        file_count = len(pending_inserts)
        return _render_cloud_storage(message=f"Uploaded {file_count} file{'s' if file_count != 1 else ''}.")

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
            return _render_cloud_storage(error="That file is missing on disk. Delete the entry or upload it again.")

        db = _get_db()
        db.execute(
            """
            UPDATE files
            SET download_count = COALESCE(download_count, 0) + 1,
                last_downloaded_at = ?
            WHERE id = ?
            """,
            (datetime.datetime.utcnow().isoformat(), file_id),
        )
        db.commit()
        db.close()

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
