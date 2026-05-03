from flask import session

from app.rendering import format_site_title, render_page

from .db import get_admin_email, get_db, get_pending_email, get_pending_sent_at
from .hardware import read_hardware_events
from .helpers import pop_ui_message
from .session_state import (
    build_log_entries,
    cooldown_remaining,
    get_active_join_invite,
    get_active_sessions,
)


def render_login_page(
    *,
    admin_sent,
    link_cooldown,
    captcha_code,
    message,
    login_sync_channel,
    noindex=False,
):
    return render_page(
        "smartlock/admin_login.html",
        page_name="Smart Lock — Access",
        current_project="login",
        show_admin_utility=False,
        admin_sent=admin_sent,
        link_cooldown=link_cooldown,
        captcha_code=captcha_code,
        message=message,
        login_sync_channel=login_sync_channel,
        noindex=noindex,
    )


def render_email_pending_page(*, error=None, captcha_code=None, noindex=False):
    return render_page(
        "smartlock/email_pending.html",
        page_name="Smart Lock — Verify Email",
        current_project="login",
        show_admin_utility=False,
        pending_email=get_pending_email(),
        sent_at=get_pending_sent_at(),
        error=error,
        captcha_code=captcha_code,
        noindex=noindex,
    )


def render_verification_complete_page(
    *,
    redirect_url,
    page_name,
    heading=None,
    description=None,
    fallback_copy=None,
    login_sync_channel="",
    noindex=False,
):
    return render_page(
        "smartlock/verification_complete.html",
        page_name=page_name,
        current_project="login",
        show_admin_utility=False,
        redirect_url=redirect_url,
        heading=heading,
        description=description,
        fallback_copy=fallback_copy,
        login_sync_channel=login_sync_channel,
        noindex=noindex,
    )


def render_user_detail_page(user, *, is_new_user, error=None, page_name=None, noindex=False):
    return render_page(
        "smartlock/admin_user_detail.html",
        page_name=page_name or format_site_title("New User" if is_new_user else user["name"]),
        current_project="smartlock",
        user=user,
        is_new_user=is_new_user,
        error=error,
        noindex=noindex,
    )


def render_admin_panel(*, email_error=None):
    users = get_db().execute("SELECT * FROM users ORDER BY created_at DESC").fetchall()
    logs = get_db().execute("SELECT * FROM login_logs ORDER BY created_at DESC LIMIT 100").fetchall()
    sessions = get_active_sessions()
    current_token = session.get("session_token", "")
    current_remaining = next(
        (item["remaining"] for item in sessions if item["session_token"] == current_token),
        0,
    )
    log_entries = build_log_entries(logs, sessions, current_token)
    return render_page(
        "smartlock/admin_panel.html",
        page_name="Smart Lock",
        current_project="smartlock",
        users=users,
        admin_email=get_admin_email(),
        pending=get_pending_email(),
        cooldown_remaining=cooldown_remaining("admin_email_change_cooldown"),
        logs=logs,
        sessions=sessions,
        log_entries=log_entries,
        current_token=current_token,
        current_remaining=current_remaining,
        panel_message=pop_ui_message("smartlock_admin_message"),
        join_invite=get_active_join_invite(),
        hardware_events=read_hardware_events(),
        email_error=email_error,
    )
