import os
import json
import sqlite3
import uuid
import hashlib
import datetime
from pathlib import Path

from flask import abort, current_app, jsonify, redirect, request, send_file, url_for
from werkzeug.utils import secure_filename

from app.rendering import format_site_title, render_page
from app.site_admin import require_site_admin


CLOUD_STORAGE_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cloud_storage.db")
DEFAULT_STORAGE_ROOT = "/Users/administrator/Storage/cloud_storage"
MAX_TOTAL_STORAGE_BYTES = 10 * 1024 * 1024 * 1024
UPLOAD_CHUNK_BYTES = 8 * 1024 * 1024
UPLOAD_SESSION_TTL = datetime.timedelta(hours=24)


def get_storage_root():
    root = os.getenv("CLOUD_STORAGE_ROOT", DEFAULT_STORAGE_ROOT).strip() or DEFAULT_STORAGE_ROOT
    path = Path(root)
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_upload_session_root():
    path = get_storage_root() / ".upload_sessions"
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


def _storage_usage_bytes():
    db = _get_db()
    total = db.execute("SELECT COALESCE(SUM(size_bytes), 0) FROM files").fetchone()[0] or 0
    db.close()
    return total


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


def _upload_session_paths(upload_id):
    session_root = get_upload_session_root()
    return session_root / f"{upload_id}.json", session_root / f"{upload_id}.part"


def _purge_stale_upload_sessions():
    now = datetime.datetime.utcnow()
    for manifest_path in get_upload_session_root().glob("*.json"):
        try:
            manifest = json.loads(manifest_path.read_text())
            created_at = datetime.datetime.fromisoformat(manifest["created_at"])
        except (OSError, ValueError, KeyError, json.JSONDecodeError):
            created_at = now - (UPLOAD_SESSION_TTL + datetime.timedelta(seconds=1))

        if now - created_at <= UPLOAD_SESSION_TTL:
            continue

        data_path = manifest_path.with_suffix(".part")
        manifest_path.unlink(missing_ok=True)
        data_path.unlink(missing_ok=True)


def _load_upload_session(upload_id):
    manifest_path, data_path = _upload_session_paths(upload_id)
    if not manifest_path.is_file():
        return None, manifest_path, data_path

    try:
        return json.loads(manifest_path.read_text()), manifest_path, data_path
    except (OSError, json.JSONDecodeError):
        manifest_path.unlink(missing_ok=True)
        data_path.unlink(missing_ok=True)
        return None, manifest_path, data_path


def _save_upload_session(upload_id, manifest):
    manifest_path, _ = _upload_session_paths(upload_id)
    manifest_path.write_text(json.dumps(manifest))


def _delete_upload_session(upload_id):
    manifest_path, data_path = _upload_session_paths(upload_id)
    manifest_path.unlink(missing_ok=True)
    data_path.unlink(missing_ok=True)


def _reserved_upload_bytes(exclude_upload_id=None):
    _purge_stale_upload_sessions()
    total = 0
    for manifest_path in get_upload_session_root().glob("*.json"):
        try:
            manifest = json.loads(manifest_path.read_text())
        except (OSError, json.JSONDecodeError):
            manifest_path.unlink(missing_ok=True)
            manifest_path.with_suffix(".part").unlink(missing_ok=True)
            continue
        if exclude_upload_id and manifest.get("upload_id") == exclude_upload_id:
            continue
        total += max(0, int(manifest.get("expected_size", 0)))
    return total


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
        page_name=format_site_title("Cloud Storage"),
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


def _validate_upload_name(filename):
    original_name = secure_filename((filename or "")).strip()
    if not original_name:
        return None, "One of the selected filenames is not allowed."
    return original_name, None


def init_cloud_storage(app):
    @app.route("/cloud-storage/")
    def cloud_storage_index():
        admin_redirect = require_site_admin()
        if admin_redirect:
            return admin_redirect
        return _render_cloud_storage()

    @app.route("/cloud-storage/upload", methods=["POST"])
    def cloud_storage_upload():
        admin_redirect = require_site_admin()
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

    @app.route("/cloud-storage/upload/start", methods=["POST"])
    def cloud_storage_upload_start():
        admin_redirect = require_site_admin()
        if admin_redirect:
            return jsonify({"error": "login required"}), 401

        _purge_stale_upload_sessions()

        original_name, validation_error = _validate_upload_name(request.form.get("name", ""))
        if validation_error:
            return jsonify({"error": validation_error}), 400

        try:
            expected_size = int(request.form.get("size", "0"))
        except ValueError:
            expected_size = 0
        if expected_size <= 0:
            return jsonify({"error": "Choose a valid file to upload."}), 400

        current_usage = _storage_usage_bytes()
        reserved_usage = _reserved_upload_bytes()
        if current_usage + reserved_usage + expected_size > MAX_TOTAL_STORAGE_BYTES:
            return jsonify({"error": "That upload would exceed the 10.0 GB storage limit."}), 400

        upload_id = uuid.uuid4().hex
        manifest = {
            "upload_id": upload_id,
            "original_name": original_name,
            "stored_name": f"{uuid.uuid4().hex}_{original_name}",
            "mime_type": (request.form.get("mime_type", "") or "").strip(),
            "expected_size": expected_size,
            "received_size": 0,
            "created_at": datetime.datetime.utcnow().isoformat(),
        }
        _, data_path = _upload_session_paths(upload_id)
        data_path.touch()
        _save_upload_session(upload_id, manifest)

        return jsonify(
            {
                "upload_id": upload_id,
                "chunk_size": UPLOAD_CHUNK_BYTES,
                "original_name": original_name,
            }
        )

    @app.route("/cloud-storage/upload/chunk/<upload_id>", methods=["POST"])
    def cloud_storage_upload_chunk(upload_id):
        admin_redirect = require_site_admin()
        if admin_redirect:
            return jsonify({"error": "login required"}), 401

        manifest, _, data_path = _load_upload_session(upload_id)
        if not manifest:
            return jsonify({"error": "Upload session not found."}), 404

        try:
            offset = int(request.form.get("offset", "-1"))
        except ValueError:
            offset = -1
        if offset != int(manifest["received_size"]):
            return jsonify({"error": "Upload offset mismatch.", "expected_offset": manifest["received_size"]}), 409

        chunk_file = request.files.get("chunk")
        if not chunk_file:
            return jsonify({"error": "Missing upload chunk."}), 400

        chunk_bytes = chunk_file.stream.read()
        if not chunk_bytes:
            return jsonify({"error": "Received an empty upload chunk."}), 400
        if len(chunk_bytes) > UPLOAD_CHUNK_BYTES:
            return jsonify({"error": "Chunk exceeded the allowed upload size."}), 400

        next_size = int(manifest["received_size"]) + len(chunk_bytes)
        if next_size > int(manifest["expected_size"]):
            return jsonify({"error": "That upload exceeded the announced file size."}), 400

        try:
            with data_path.open("ab") as handle:
                handle.write(chunk_bytes)
        except OSError:
            current_app.logger.exception("Failed to append cloud storage upload chunk")
            return jsonify({"error": "Upload failed while writing a chunk."}), 500

        manifest["received_size"] = next_size
        _save_upload_session(upload_id, manifest)
        return jsonify(
            {
                "received_size": next_size,
                "expected_size": int(manifest["expected_size"]),
                "complete": next_size == int(manifest["expected_size"]),
            }
        )

    @app.route("/cloud-storage/upload/finish/<upload_id>", methods=["POST"])
    def cloud_storage_upload_finish(upload_id):
        admin_redirect = require_site_admin()
        if admin_redirect:
            return jsonify({"error": "login required"}), 401

        manifest, manifest_path, data_path = _load_upload_session(upload_id)
        if not manifest:
            return jsonify({"error": "Upload session not found."}), 404

        expected_size = int(manifest["expected_size"])
        received_size = int(manifest["received_size"])
        if received_size != expected_size or not data_path.is_file():
            return jsonify({"error": "Upload is incomplete."}), 400

        final_path = get_storage_root() / manifest["stored_name"]
        try:
            data_path.replace(final_path)
            checksum_sha256 = _sha256_for_file(final_path)
        except OSError:
            current_app.logger.exception("Failed to finalize cloud storage upload")
            return jsonify({"error": "Upload failed while finalizing the file."}), 500

        db = _get_db()
        try:
            db.execute(
                """
                INSERT INTO files (original_name, stored_name, mime_type, size_bytes, checksum_sha256)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    manifest["original_name"],
                    manifest["stored_name"],
                    manifest["mime_type"],
                    expected_size,
                    checksum_sha256,
                ),
            )
            db.commit()
        except sqlite3.Error:
            db.close()
            final_path.unlink(missing_ok=True)
            current_app.logger.exception("Failed to record finalized cloud storage upload")
            return jsonify({"error": "Upload finished, but metadata could not be saved."}), 500
        db.close()

        manifest_path.unlink(missing_ok=True)
        return jsonify(
            {
                "message": f"Uploaded {manifest['original_name']}.",
                "file": {
                    "original_name": manifest["original_name"],
                    "size_label": _human_size(expected_size),
                },
            }
        )

    @app.route("/cloud-storage/upload/cancel/<upload_id>", methods=["POST"])
    def cloud_storage_upload_cancel(upload_id):
        admin_redirect = require_site_admin()
        if admin_redirect:
            return jsonify({"error": "login required"}), 401

        _delete_upload_session(upload_id)
        return jsonify({"status": "cancelled"})

    @app.route("/cloud-storage/download/<int:file_id>")
    def cloud_storage_download(file_id):
        admin_redirect = require_site_admin()
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
        admin_redirect = require_site_admin()
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
