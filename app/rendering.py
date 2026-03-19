import os
import inspect
from flask import current_app, render_template, request


def build_github_file_url(project_root, source_path):
    if not source_path:
        return "unknown"
    try:
        relative_path = os.path.relpath(source_path, project_root)
    except ValueError:
        return source_path
    repo_url = current_app.config.get("GITHUB_REPO_URL", "").rstrip("/")
    branch_name = current_app.config.get("GITHUB_BRANCH", "main")
    if repo_url.endswith(".git"):
        repo_url = repo_url[:-4]
    if not repo_url:
        return relative_path
    return f"{repo_url}/blob/{branch_name}/{relative_path}"


def render_page(template_name, **context):
    project_root = os.path.dirname(current_app.root_path)
    template_local_path = os.path.join(project_root, "templates", *template_name.split("/"))
    github_file_path = "unknown"
    endpoint = request.endpoint
    if endpoint:
        view_func = current_app.view_functions.get(endpoint)
        if view_func:
            try:
                source_path = inspect.getsourcefile(view_func) or inspect.getfile(view_func)
            except (TypeError, OSError):
                source_path = None
            if source_path:
                github_file_path = build_github_file_url(project_root, source_path)
    page_name = context.pop("page_name", None)
    return render_template(
        template_name,
        page_name=page_name or current_app.jinja_env.globals.get("page_name", ""),
        request_url=request.url,
        template_local_path=template_local_path,
        github_file_path=github_file_path,
        last_deployment=current_app.config.get("LAST_DEPLOYMENT", "unknown"),
        **context,
    )
