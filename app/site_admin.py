from flask import redirect, session, url_for


SITE_ADMIN_ROLE = "admin"


def is_site_admin():
    return session.get("role") == SITE_ADMIN_ROLE


def require_site_admin(login_endpoint="smartlock_login"):
    if is_site_admin():
        return None
    return redirect(url_for(login_endpoint))
