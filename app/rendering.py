from flask import current_app, g, render_template


def render_page(template_name, **context):
    page_name = context.pop("page_name", None)
    if context.pop("noindex", False):
        g.x_robots_tag = "noindex, nofollow"
    return render_template(
        template_name,
        page_name=page_name or current_app.jinja_env.globals.get("page_name", ""),
        asset_version=current_app.config.get("ASSET_VERSION", "dev"),
        **context,
    )
