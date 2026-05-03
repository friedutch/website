from flask import current_app, g, render_template, request


SITE_PROJECTS = [
    {"key": "smartlock", "label": "Smart Lock", "short": "Smart Lock", "href": "/smartlock/"},
    {"key": "cloud_storage", "label": "Cloud Storage", "short": "Storage", "href": "/cloud-storage/"},
    {"key": "chat", "label": "Chat", "short": "Chat", "href": "/chat/"},
]


def _project_key_for_path(path):
    if path in {"/", "/about"}:
        return "home"
    if path.startswith("/smartlock/"):
        return "smartlock"
    if path.startswith("/cloud-storage/"):
        return "cloud_storage"
    if path.startswith("/chat/"):
        return "chat"
    if path == "/login":
        return "login"
    return ""


def get_site_brand_name():
    return current_app.config.get("SITE_BRAND_NAME", "jehpok")


def get_site_brand_mark():
    brand_name = get_site_brand_name()
    letters = "".join(ch for ch in brand_name if ch.isalnum())
    return (letters[:2] or "JP").upper()


def format_site_title(section=None):
    brand_name = get_site_brand_name()
    if section:
        return f"{section} — {brand_name}"
    return brand_name


def render_page(template_name, **context):
    page_name = context.pop("page_name", None)
    current_project = context.pop("current_project", _project_key_for_path(request.path))
    show_admin_utility = context.pop("show_admin_utility", True)
    if context.pop("noindex", False):
        g.x_robots_tag = "noindex, nofollow"
    brand_name = get_site_brand_name()
    return render_template(
        template_name,
        page_name=page_name or brand_name,
        asset_version=current_app.config.get("ASSET_VERSION", "dev"),
        current_project=current_project,
        site_projects=SITE_PROJECTS,
        site_admin_login_url="/login",
        site_brand_name=brand_name,
        site_brand_mark=get_site_brand_mark(),
        show_admin_utility=show_admin_utility,
        **context,
    )
