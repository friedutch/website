import os
import subprocess
from pathlib import Path

from flask import Blueprint, redirect, url_for

from app.rendering import render_page


DEFAULT_SERVER_ROOT = Path(os.getenv("MINECRAFT_SERVER_ROOT", "/Users/administrator/Servers/minecraft"))
DEFAULT_WORLD_NAME = os.getenv("MINECRAFT_WORLD_NAME", "world")
DEFAULT_LAUNCH_AGENT_LABEL = os.getenv("MINECRAFT_LAUNCH_AGENT_LABEL", "friedutchplus.minecraft.server")
DEFAULT_LAUNCH_AGENT_PLIST = os.getenv(
    "MINECRAFT_LAUNCH_AGENT_PLIST",
    "/Users/administrator/Library/LaunchAgents/friedutchplus.minecraft.server.plist",
)


def _read_server_properties(server_root):
    properties = {}
    properties_path = Path(server_root) / "server.properties"
    try:
        for line in properties_path.read_text(encoding="utf-8").splitlines():
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            properties[key.strip()] = value.strip()
    except OSError:
        return {}
    return properties


def _human_size(path):
    total_bytes = 0
    try:
        path = Path(path)
        if path.is_file():
            total_bytes = path.stat().st_size
        elif path.exists():
            for child in path.rglob("*"):
                if child.is_file():
                    total_bytes += child.stat().st_size
    except OSError:
        return "Unknown"

    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(total_bytes)
    for unit in units:
        if size < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1024
    return "Unknown"


def _service_loaded(label):
    target = f"gui/{os.getuid()}/{label}"
    completed = subprocess.run(
        ["launchctl", "print", target],
        capture_output=True,
        text=True,
        check=False,
    )
    return completed.returncode == 0


def _access_status(properties):
    override = os.getenv("MINECRAFT_SERVER_ACCESS") or os.getenv("MINECRAFT_SERVER_WHITELIST")
    if override:
        return override
    if properties.get("white-list", "").lower() == "true" or properties.get("enforce-whitelist", "").lower() == "true":
        return "Whitelist only"
    return "Public"


def _edition_label():
    edition = os.getenv("MINECRAFT_SERVER_EDITION", "Java Edition").strip()
    if edition.lower().endswith(" edition"):
        return edition[:-8]
    return edition


def _minecraft_config():
    server_root = Path(os.getenv("MINECRAFT_SERVER_ROOT", str(DEFAULT_SERVER_ROOT)))
    properties = _read_server_properties(server_root)
    world_name = os.getenv("MINECRAFT_WORLD_NAME", properties.get("level-name", DEFAULT_WORLD_NAME))
    world_path = server_root / world_name
    service_label = os.getenv("MINECRAFT_LAUNCH_AGENT_LABEL", DEFAULT_LAUNCH_AGENT_LABEL)
    is_online = _service_loaded(service_label)
    return {
        "join_host": os.getenv("MINECRAFT_JOIN_HOST", "mc.friedutch.plus"),
        "join_port": os.getenv("MINECRAFT_JOIN_PORT", "25565"),
        "edition": _edition_label(),
        "version": os.getenv("MINECRAFT_SERVER_VERSION", "Set your live version in .env"),
        "status": "Online" if is_online else "Offline",
        "access": _access_status(properties),
        "world_name": world_name,
        "world_size": _human_size(world_path),
        "can_start": not is_online,
        "can_stop": is_online,
    }


def render_minecraft_page():
    return render_page(
        "minecraft.html",
        page_name="Minecraft Server — Friedutch Plus",
        minecraft=_minecraft_config(),
    )


def _launchctl(action):
    plist = os.getenv("MINECRAFT_LAUNCH_AGENT_PLIST", DEFAULT_LAUNCH_AGENT_PLIST)
    uid = str(os.getuid())
    if action == "start":
        subprocess.run(
            ["launchctl", "bootstrap", f"gui/{uid}", plist],
            check=False,
            capture_output=True,
            text=True,
        )
        return
    if action == "stop":
        subprocess.run(
            ["launchctl", "bootout", f"gui/{uid}", plist],
            check=False,
            capture_output=True,
            text=True,
        )
        return
    raise ValueError(f"Unsupported action: {action}")


def init_minecraft(flask_app, csrf):
    minecraft_bp = Blueprint("minecraft", __name__)

    @minecraft_bp.route("/minecraft", strict_slashes=False)
    @minecraft_bp.route("/minecraft/", strict_slashes=False)
    def minecraft():
        return render_minecraft_page()

    @minecraft_bp.route("/minecraft/server/start", methods=["POST"])
    @csrf.exempt
    def minecraft_server_start():
        _launchctl("start")
        return redirect(url_for("minecraft.minecraft"))

    @minecraft_bp.route("/minecraft/server/stop", methods=["POST"])
    @csrf.exempt
    def minecraft_server_stop():
        _launchctl("stop")
        return redirect(url_for("minecraft.minecraft"))

    flask_app.register_blueprint(minecraft_bp)
