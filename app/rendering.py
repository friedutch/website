import os
from flask import current_app, render_template, request


def render_page(template_name, **context):
    project_root = os.path.dirname(current_app.root_path)
    template_local_path = os.path.join(project_root, "templates", *template_name.split("/"))
    page_name = context.pop("page_name", None)
    return render_template(
        template_name,
        page_name=page_name or current_app.jinja_env.globals.get("page_name", ""),
        request_url=request.url,
        template_local_path=template_local_path,
        last_deployment=current_app.config.get("LAST_DEPLOYMENT", "unknown"),
        **context,
    )
