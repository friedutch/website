import os
from flask import Blueprint

from app.rendering import render_page


def _minecraft_config():
    return {
        "host": os.getenv("MINECRAFT_SERVER_HOST", "mc.friedutch.plus"),
        "join_host": os.getenv("MINECRAFT_JOIN_HOST", "mc.friedutch.plus"),
        "join_port": os.getenv("MINECRAFT_JOIN_PORT", "25565"),
        "port": os.getenv("MINECRAFT_SERVER_PORT", "25565"),
        "edition": os.getenv("MINECRAFT_SERVER_EDITION", "Java Edition"),
        "version": os.getenv("MINECRAFT_SERVER_VERSION", "Set your live version in .env"),
        "status": os.getenv("MINECRAFT_SERVER_STATUS", "Provisioning"),
        "whitelist": os.getenv("MINECRAFT_SERVER_WHITELIST", "Invite only"),
        "description": os.getenv(
            "MINECRAFT_SERVER_DESCRIPTION",
            "Self-hosted survival world running alongside the Friedutch Plus site.",
        ),
    }


def render_minecraft_page():
    return render_page(
        "minecraft.html",
        page_name="Minecraft Server — Friedutch Plus",
        minecraft=_minecraft_config(),
    )


def init_minecraft(flask_app):
    minecraft_bp = Blueprint("minecraft", __name__)

    @minecraft_bp.route("/minecraft", strict_slashes=False)
    @minecraft_bp.route("/minecraft/", strict_slashes=False)
    def minecraft():
        return render_minecraft_page()

    flask_app.register_blueprint(minecraft_bp)
