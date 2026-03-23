import os
import json
import socket
import subprocess
from pathlib import Path

from flask import Blueprint, redirect, url_for

from app.rendering import render_page
from projects.smartlock import is_admin, require_admin_login


DEFAULT_SERVER_ROOT = Path(os.getenv("MINECRAFT_SERVER_ROOT", "/Users/administrator/Servers/minecraft"))
DEFAULT_WORLD_NAME = os.getenv("MINECRAFT_WORLD_NAME", "world")
DEFAULT_LAUNCH_AGENT_LABEL = os.getenv("MINECRAFT_LAUNCH_AGENT_LABEL", "friedutchplus.minecraft.server")
DEFAULT_LAUNCH_AGENT_PLIST = os.getenv(
    "MINECRAFT_LAUNCH_AGENT_PLIST",
    "/Users/administrator/Library/LaunchAgents/friedutchplus.minecraft.server.plist",
)


def _read_varint(sock):
    value = 0
    position = 0
    while True:
        current = sock.recv(1)
        if not current:
            raise OSError("Connection closed while reading VarInt")
        current_byte = current[0]
        value |= (current_byte & 0x7F) << position
        if not current_byte & 0x80:
            return value
        position += 7
        if position >= 35:
            raise ValueError("VarInt too large")


def _write_varint(value):
    payload = bytearray()
    while True:
        temp = value & 0x7F
        value >>= 7
        if value:
            temp |= 0x80
        payload.append(temp)
        if not value:
            return bytes(payload)


def _minecraft_status(host, port):
    address = host or "127.0.0.1"
    try:
        with socket.create_connection((address, port), timeout=1.5) as sock:
            host_bytes = address.encode("utf-8")
            handshake_data = (
                _write_varint(0)
                + _write_varint(765)
                + _write_varint(len(host_bytes))
                + host_bytes
                + port.to_bytes(2, "big")
                + _write_varint(1)
            )
            sock.sendall(_write_varint(len(handshake_data)) + handshake_data)

            request_data = _write_varint(0)
            sock.sendall(_write_varint(len(request_data)) + request_data)

            _read_varint(sock)
            packet_id = _read_varint(sock)
            if packet_id != 0:
                return {}
            payload_length = _read_varint(sock)
            payload = bytearray()
            while len(payload) < payload_length:
                chunk = sock.recv(payload_length - len(payload))
                if not chunk:
                    break
                payload.extend(chunk)
            if len(payload) != payload_length:
                return {}
            return json.loads(payload.decode("utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return {}


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
    edition = os.getenv("MINECRAFT_SERVER_EDITION", "").strip()
    if not edition:
        return "Unknown"
    if edition.lower().endswith(" edition"):
        return edition[:-8]
    return edition


def _modloader_label():
    modloader = os.getenv("MINECRAFT_SERVER_MODLOADER", "").strip()
    if not modloader or modloader.lower() == "none":
        return "Vanilla"
    return modloader


def _join_address(join_host, join_port):
    if join_host == "Unavailable":
        return join_host
    if join_port in {"", "25565", "Unavailable"}:
        return join_host
    return f"{join_host}:{join_port}"


def _player_count(status, properties, is_online):
    if not is_online or not isinstance(status, dict):
        return "Unavailable"
    players = status.get("players", {})
    online = players.get("online")
    maximum = players.get("max") or properties.get("max-players")
    if online is None or maximum is None:
        return "Unavailable"
    return f"{online} / {maximum}"


def _minecraft_config():
    server_root = Path(os.getenv("MINECRAFT_SERVER_ROOT", str(DEFAULT_SERVER_ROOT)))
    properties = _read_server_properties(server_root)
    world_name = os.getenv("MINECRAFT_WORLD_NAME", properties.get("level-name", DEFAULT_WORLD_NAME))
    service_label = os.getenv("MINECRAFT_LAUNCH_AGENT_LABEL", DEFAULT_LAUNCH_AGENT_LABEL)
    is_online = _service_loaded(service_label)
    join_host = os.getenv("MINECRAFT_JOIN_HOST", "").strip() or "Unavailable"
    join_port = os.getenv("MINECRAFT_JOIN_PORT", "").strip() or "Unavailable"
    status_payload = _minecraft_status("127.0.0.1", int(properties.get("server-port", "25565") or 25565)) if is_online else {}
    return {
        "join_host": join_host,
        "join_port": join_port,
        "join_address": _join_address(join_host, join_port),
        "server_name": "FP SMP",
        "host": "macOS",
        "edition": _edition_label(),
        "modloader": _modloader_label(),
        "version": os.getenv("MINECRAFT_SERVER_VERSION", "").strip() or "Unknown",
        "status": "Online" if is_online else "Offline",
        "player_count": _player_count(status_payload, properties, is_online),
        "access": _access_status(properties),
        "world_name": world_name,
        "can_manage": _can_manage_server(),
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


def _can_manage_server():
    return is_admin()


def init_minecraft(flask_app, csrf):
    minecraft_bp = Blueprint("minecraft", __name__)

    @minecraft_bp.route("/minecraft/")
    def minecraft():
        return render_minecraft_page()

    @minecraft_bp.route("/minecraft/server/start", methods=["POST"])
    def minecraft_server_start():
        admin_redirect = require_admin_login()
        if admin_redirect:
            return admin_redirect
        _launchctl("start")
        return redirect(url_for("minecraft.minecraft"))

    @minecraft_bp.route("/minecraft/server/stop", methods=["POST"])
    def minecraft_server_stop():
        admin_redirect = require_admin_login()
        if admin_redirect:
            return admin_redirect
        _launchctl("stop")
        return redirect(url_for("minecraft.minecraft"))

    flask_app.register_blueprint(minecraft_bp)
