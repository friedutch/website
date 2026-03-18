import os
from flask import current_app, render_template


def render_page(template_name, **context):
    project_root = os.path.dirname(current_app.root_path)
    template_local_path = os.path.join(project_root, "templates", *template_name.split("/"))
    return render_template(
        template_name,
        template_local_path=template_local_path,
        last_deployment=current_app.config.get("LAST_DEPLOYMENT", "unknown"),
        **context,
    )
