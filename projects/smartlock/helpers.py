from urllib.parse import urlencode

import bleach
from flask import redirect, request, session

from app.rendering import render_page


def pop_ui_message(key):
    value = session.get(key)
    if key in session:
        session.pop(key)
    return value


def sanitize(value, max_length=100):
    if not value:
        return ""
    return bleach.clean(value.strip(), tags=[], strip=True)[:max_length]


def build_cookie_probe_url():
    args = request.args.to_dict(flat=True)
    args["_smartlock_cookie_probe"] = "1"
    query = urlencode(args)
    return f"{request.path}?{query}" if query else request.path


def cookies_enabled_for_smartlock():
    return session.get("smartlock_cookies_probe") == "ok"


def render_cookies_required():
    return render_page(
        "smartlock/cookies_required.html",
        page_name="Smart Lock — Cookies Required",
    )


def ensure_smartlock_cookies():
    if not request.path.startswith("/smartlock"):
        return None
    if request.endpoint == "static":
        return None
    if request.path.startswith("/smartlock/api/"):
        return None
    if cookies_enabled_for_smartlock():
        if "_smartlock_cookie_probe" in request.args:
            args = request.args.to_dict(flat=True)
            args.pop("_smartlock_cookie_probe", None)
            query = urlencode(args)
            target = f"{request.path}?{query}" if query else request.path
            return redirect(target)
        return None
    if request.args.get("_smartlock_cookie_probe") == "1":
        return render_cookies_required()
    session["smartlock_cookies_probe"] = "ok"
    return redirect(build_cookie_probe_url())
