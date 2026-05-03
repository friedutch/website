import os
import hmac
import subprocess
from datetime import datetime, timedelta, UTC
from dotenv import load_dotenv
from flask import Flask, request, jsonify, g
from flask_wtf.csrf import CSRFProtect, CSRFError

from app.forms import inject_csrf_token
from app.rendering import format_site_title, get_site_brand_name, render_page
from app.site_admin import is_site_admin


load_dotenv()


def get_git_output(project_root, *args):
    if os.getenv("FRIEDUTCH_SKIP_GIT_METADATA") == "1":
        return ""
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
    git_remote = get_git_output(project_root, "remote", "get-url", "origin")
    git_branch = get_git_output(project_root, "rev-parse", "--abbrev-ref", "HEAD")
    git_revision = get_git_output(project_root, "rev-parse", "--short", "HEAD")
    flask_app.config["GITHUB_REPO_URL"] = os.getenv("GITHUB_REPO_URL", git_remote)
    flask_app.config["GITHUB_BRANCH"] = os.getenv("GITHUB_BRANCH", git_branch or "main")
    flask_app.config["ASSET_VERSION"] = os.getenv("ASSET_VERSION", git_revision or flask_app.config["LAST_DEPLOYMENT"])
    flask_app.config["SITE_BRAND_NAME"] = os.getenv("SITE_BRAND_NAME", "jehpok")
    flask_app.config.update(
        SESSION_COOKIE_SECURE=True,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SEND_FILE_MAX_AGE_DEFAULT=timedelta(days=365),
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
            "img-src 'self' data:; "
            "font-src 'self' data:; "
            "connect-src 'self'; "
            "object-src 'none'; "
            "base-uri 'self'; "
            "form-action 'self'; "
            "frame-ancestors 'none'",
        )
        return response

    @flask_app.route("/deploy", methods=["POST"])
    @csrf.exempt
    def deploy():
        body = request.get_data()
        sig = request.headers.get("X-Hub-Signature-256", "")
        secret = os.getenv("GITHUB_WEBHOOK_SECRET", "")
        token = os.getenv("DEPLOY_WEBHOOK_TOKEN", "")
        supplied_token = request.args.get("token", "") or request.headers.get("X-Deploy-Token", "")

        authorized = False
        if secret:
            expected = "sha256=" + hmac.new(secret.encode(), body, "sha256").hexdigest()
            authorized = hmac.compare_digest(sig, expected)
        elif token:
            authorized = hmac.compare_digest(supplied_token, token)

        if not authorized:
            return jsonify({"error": "unauthorized"}), 401

        payload = request.get_json(silent=True) or {}
        ref = payload.get("ref", "")
        if ref and ref != "refs/heads/main":
            return jsonify({"status": "ignored", "reason": "non-main ref"}), 202

        deploy_script = os.path.join(project_root, "deploy.sh")
        with open("/tmp/deploy.log", "w") as deploy_log:
            subprocess.Popen(
                ["/bin/bash", deploy_script],
                stdout=deploy_log,
                stderr=subprocess.STDOUT,
            )
        return jsonify({"status": "deploying"}), 200

    @flask_app.route("/")
    def landing():
        return render_page("landing.html", page_name=get_site_brand_name())

    @flask_app.route("/about")
    def about():
        return render_page("about.html", page_name=format_site_title("About"))

    return flask_app


def init_project_dbs():
    from projects.cloud_chat import init_chat_db
    from projects.cloud_storage import init_cloud_storage_db
    from projects.smartlock import init_db

    init_db()
    init_cloud_storage_db()
    init_chat_db()
