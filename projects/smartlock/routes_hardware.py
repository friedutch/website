from flask import jsonify, request

from app.site_admin import is_site_admin

from .activity import log_attempt
from .config import HARDWARE_UNLOCK_SECONDS, get_hardware_api_key
from .hardware import (
    evaluate_hardware_access,
    hardware_request_is_authorized,
    mask_hardware_method_id,
    read_hardware_events,
)
from .helpers import sanitize


def register_hardware_routes(app, csrf=None):
    @app.route("/smartlock/api/hardware/check", methods=["POST"])
    def smartlock_hardware_check():
        api_key = get_hardware_api_key()
        if not api_key:
            return jsonify({"error": "hardware api disabled"}), 503
        if not hardware_request_is_authorized():
            return jsonify({"error": "unauthorized"}), 401

        payload = request.get_json(silent=True) or {}
        method = sanitize(payload.get("method", ""), max_length=32).lower().replace("-", "_")
        if method not in ("passcode", "rfid", "fingerprint"):
            return jsonify({"error": "unsupported method"}), 400

        result = evaluate_hardware_access(method, payload.get("value", ""))
        credential = result["credential"]
        user = result["user"]
        log_attempt(
            f"hardware_{method}",
            method_id=mask_hardware_method_id(method, credential),
            success=result["allowed"],
            user_name=user["name"] if user else None,
        )
        return jsonify(
            {
                "allowed": result["allowed"],
                "method": method,
                "credential": credential,
                "user_id": user["id"] if user else None,
                "user_name": user["name"] if user else None,
                "unlock_seconds": HARDWARE_UNLOCK_SECONDS if result["allowed"] else 0,
                "reason": result["reason"],
            }
        )

    if csrf is not None:
        csrf.exempt(smartlock_hardware_check)

    @app.route("/smartlock/api/hardware/events")
    def smartlock_hardware_events():
        if not is_site_admin():
            return jsonify({"error": "unauthorized"}), 401
        try:
            limit = int(request.args.get("limit", "200"))
        except ValueError:
            limit = 200
        return jsonify({"events": read_hardware_events(limit=limit)})
