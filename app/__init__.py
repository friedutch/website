import os
import hmac
import subprocess
from dotenv import load_dotenv
from flask import Flask, request, render_template, jsonify
from flask_wtf.csrf import CSRFProtect

from projects.smartlock import init_smartlock, init_db
from projects.footprint import init_footprint, init_footprint_db


def create_app():
    load_dotenv()

    flask_app = Flask(__name__)
    flask_app.secret_key = os.getenv("SECRET_KEY")
    csrf = CSRFProtect(flask_app)

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
            ["/bin/bash", "/Users/administrator/Sites/friedutch-app/deploy.sh"],
            stdout=open("/tmp/deploy.log", "w"),
            stderr=subprocess.STDOUT,
        )
        return jsonify({"status": "deploying"}), 200

    @flask_app.route("/")
    def home():
        return render_template("home.html")

    return flask_app


def init_project_dbs():
    init_db()
    init_footprint_db()
