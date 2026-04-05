from flask import current_app, g, render_template, request


SITE_PROJECTS = [
    {"key": "home", "label": "Home", "short": "🏠", "href": "/"},
    {"key": "smartlock", "label": "Smart Lock", "short": "🔐", "href": "/smartlock/"},
    {"key": "cloud_storage", "label": "Cloud Storage", "short": "☁️", "href": "/cloud-storage/"},
    {"key": "privatechat", "label": "Private Chat", "short": "💬", "href": "/privatechat/"},
    {"key": "minecraft", "label": "Minecraft", "short": "⛏️", "href": "/minecraft/"},
]


def _project_key_for_path(path):
    if path in {"/", "/about"}:
        return "home"
    if path.startswith("/smartlock/"):
        return "smartlock"
    if path.startswith("/cloud-storage/"):
        return "cloud_storage"
    if path.startswith("/privatechat/") or path.startswith("/cloudchat/"):
        return "privatechat"
    if path.startswith("/minecraft/"):
        return "minecraft"
    if path == "/login":
        return "login"
    return ""


def render_page(template_name, **context):
    page_name = context.pop("page_name", None)
    current_project = context.pop("current_project", _project_key_for_path(request.path))
    if context.pop("noindex", False):
        g.x_robots_tag = "noindex, nofollow"
    return render_template(
        template_name,
        page_name=page_name or current_app.jinja_env.globals.get("page_name", ""),
        asset_version=current_app.config.get("ASSET_VERSION", "dev"),
        current_project=current_project,
        site_projects=SITE_PROJECTS,
        site_admin_login_url="/login",
        **context,
    )
