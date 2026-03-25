from .config import init_smartlock_config
from .db import close_db, init_db
from .helpers import ensure_smartlock_cookies, render_cookies_required
from .routes_admin import register_admin_routes
from .routes_auth import register_auth_routes
from .routes_hardware import register_hardware_routes
from .session_state import check_session


def init_smartlock(app, csrf=None):
    init_smartlock_config(app.secret_key)
    app.teardown_appcontext(close_db)
    app.before_request(ensure_smartlock_cookies)
    app.before_request(check_session)
    register_auth_routes(app)
    register_admin_routes(app)
    register_hardware_routes(app, csrf=csrf)
