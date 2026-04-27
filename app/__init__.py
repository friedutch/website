import os
import subprocess
from datetime import datetime, UTC
from dotenv import load_dotenv
from flask import Flask, request, jsonify, g
from flask_wtf.csrf import CSRFProtect, CSRFError

from app.forms import inject_csrf_token
from app.rendering import render_page
from app.site_admin import is_site_admin


load_dotenv()


def get_git_output(project_root, *args):
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=project_root,
            check=True,
            capture_output=True,
            text=True,
        )
        return completed.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""


def create_app():
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    from projects.cloud_chat import init_chat
    from projects.cloud_storage import init_cloud_storage
    from projects.smartlock import init_smartlock, render_cookies_required

    flask_app = Flask(
        __name__,
        template_folder=os.path.join(project_root, "templates"),
        static_folder=os.path.join(project_root, "static"),
    )
    flask_app.secret_key = os.getenv("SECRET_KEY")
    csrf = CSRFProtect(flask_app)
    flask_app.config["LAST_DEPLOYMENT"] = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
    flask_app.config["GITHUB_REPO_URL"] = get_git_output(project_root, "remote", "get-url", "origin")
    flask_app.config["GITHUB_BRANCH"] = get_git_output(project_root, "rev-parse", "--abbrev-ref", "HEAD") or "main"
    flask_app.config["ASSET_VERSION"] = get_git_output(project_root, "rev-parse", "--short", "HEAD") or flask_app.config["LAST_DEPLOYMENT"]
    flask_app.config.update(
        SESSION_COOKIE_SECURE=True,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
    )

    @flask_app.context_processor
    def inject_nav_state():
        return {"show_logout_button": is_site_admin()}

    flask_app.context_processor(inject_csrf_token)

    init_smartlock(flask_app, csrf)
    init_cloud_storage(flask_app)
    init_chat(flask_app)

    @flask_app.errorhandler(CSRFError)
    def handle_csrf_error(error):
        if request.path == "/login" or request.path.startswith("/smartlock"):
            return render_cookies_required(), 400
        return jsonify({"error": "bad request", "reason": error.description}), 400

    @flask_app.after_request
    def apply_security_headers(response):
        x_robots_tag = getattr(g, "x_robots_tag", None)
        if x_robots_tag:
            response.headers["X-Robots-Tag"] = x_robots_tag
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        response.headers.setdefault("Cross-Origin-Resource-Policy", "same-origin")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: https:; "
            "font-src 'self' data: https:; "
            "connect-src 'self'; "
            "object-src 'none'; "
            "base-uri 'self'; "
            "form-action 'self'; "
            "frame-ancestors 'none'",
        )
        return response

    @flask_app.route("/")
    def landing():
        return render_page("landing.html", page_name="Friedutch Plus")

    @flask_app.route("/about")
    def about():
        return render_page("about.html", page_name="Friedutch Plus")

    return flask_app


def init_project_dbs():
    from projects.cloud_chat import init_chat_db
    from projects.cloud_storage import init_cloud_storage_db
    from projects.smartlock import init_db

    init_db()
    init_cloud_storage_db()
    init_chat_db()
