import os
import hmac
import subprocess
from datetime import datetime, UTC
from dotenv import load_dotenv
from flask import Flask, request, jsonify
from flask_wtf.csrf import CSRFProtect

from app.rendering import render_page


load_dotenv()


def create_app():
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    from projects.smartlock import init_smartlock
    from projects.footprint import init_footprint

    flask_app = Flask(
        __name__,
        template_folder=os.path.join(project_root, "templates"),
        static_folder=os.path.join(project_root, "static"),
    )
    flask_app.secret_key = os.getenv("SECRET_KEY")
    csrf = CSRFProtect(flask_app)
    flask_app.config["LAST_DEPLOYMENT"] = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")

    flask_app.config.update(
        SESSION_COOKIE_SECURE=True,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
    )

    init_smartlock(flask_app)
    init_footprint(flask_app, csrf)

    @flask_app.route("/deploy", methods=["POST"])
    @csrf.exempt
    def deploy():
        sig = request.headers.get("X-Hub-Signature-256", "")
        secret = os.getenv("GITHUB_WEBHOOK_SECRET", "").encode()
        body = request.get_data()
        expected = "sha256=" + hmac.new(secret, body, "sha256").hexdigest()
        if not hmac.compare_digest(sig, expected):
            return jsonify({"error": "unauthorized"}), 401
        subprocess.Popen(
            ["/bin/bash", os.path.join(project_root, "deploy.sh")],
            stdout=open("/tmp/deploy.log", "w"),
            stderr=subprocess.STDOUT,
        )
        return jsonify({"status": "deploying"}), 200

    @flask_app.route("/")
    def home():
        return render_page("home.html", page_name="Friedutch+")

    return flask_app


def init_project_dbs():
    from projects.smartlock import init_db
    from projects.footprint import init_footprint_db

    init_db()
    init_footprint_db()
