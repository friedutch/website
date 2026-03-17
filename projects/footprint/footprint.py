"""
footprint.py — Probe engine for the Footprint project.

For each site, we send a password-reset request and inspect the response
to determine if an account exists. Three possible outcomes:

  found        — response clearly indicates an account exists
  not_found    — response clearly indicates no account exists
  inconclusive — site rate-limited, blocked, or returns identical
                 responses regardless (e.g. Google, Apple)

Usage:
    from projects.footprint.footprint import probe_email, probe_domain
    results = probe_email("hello@friedutch.plus")   # → list of dicts
    results = probe_domain("friedutch.plus")        # → probes all known addresses
"""

import asyncio
import aiohttp
import re
from typing import Literal

# ── Types ──────────────────────────────────────────────────────────────────────

ProbeStatus = Literal["found", "not_found", "inconclusive"]

# ── Site definitions ───────────────────────────────────────────────────────────
#
# Each entry:
#   url        — POST/GET endpoint for password reset
#   method     — "post" or "get"
#   payload    — dict of form fields ({EMAIL} is replaced with the address)
#   found_re   — regex that matches response body when account EXISTS
#   not_found_re — regex that matches response body when account DOES NOT exist
#   headers    — optional extra headers
#   json       — if True, send payload as JSON instead of form data
#
# If neither regex matches → inconclusive.
# Sites marked inconclusive=True are skipped (always return inconclusive).

SITES = [
    # ── Tier 1: Major platforms ────────────────────────────────────────────
    {"name": "GitHub",       "icon": "🐙", "tier": 1,
     "url": "https://github.com/password_reset",
     "method": "post",
     "payload": {"email": "{EMAIL}"},
     "found_re": r"(If an account exists|reset password instructions)",
     "not_found_re": r"(No account|couldn't find)",
     "inconclusive": True},   # GitHub returns same message for both

    {"name": "GitLab",       "icon": "🦊", "tier": 1,
     "url": "https://gitlab.com/users/password",
     "method": "post",
     "payload": {"user[email]": "{EMAIL}"},
     "found_re": r"(Instructions have been sent|reset link)",
     "not_found_re": r"(not found|no user)"},

    {"name": "Spotify",      "icon": "🎵", "tier": 1,
     "url": "https://accounts.spotify.com/en/password-reset",
     "method": "post",
     "payload": {"email": "{EMAIL}", "continue": "https://www.spotify.com"},
     "found_re": r"(email.*sent|check your inbox)",
     "not_found_re": r"(no account|doesn't exist)",
     "inconclusive": True},

    {"name": "Netflix",      "icon": "🎬", "tier": 1,
     "url": "https://www.netflix.com/LoginHelp",
     "method": "post",
     "payload": {"email": "{EMAIL}", "flow": "pwd"},
     "found_re": r"(email.*sent|reset link)",
     "not_found_re": r"(no account|couldn't find)",
     "inconclusive": True},

    {"name": "Google",       "icon": "🔍", "tier": 1,
     "url": "https://accounts.google.com/signin/v2/identifier",
     "method": "post",
     "payload": {"identifier": "{EMAIL}"},
     "found_re": r"(wrong password|enter your password)",
     "not_found_re": r"(couldn't find|no account)",
     "inconclusive": True},

    {"name": "Apple",        "icon": "🍎", "tier": 1,
     "url": "https://iforgot.apple.com/password/verify/appleid",
     "method": "post",
     "payload": {"id": "{EMAIL}"},
     "found_re": r"(verify|confirm)",
     "not_found_re": r"(no account|not found)",
     "inconclusive": True},

    {"name": "Microsoft",    "icon": "🪟", "tier": 1,
     "url": "https://login.live.com/GetCredentialType.srf",
     "method": "post",
     "payload": {"username": "{EMAIL}"},
     "found_re": r'"IfExistsResult":0',
     "not_found_re": r'"IfExistsResult":1',
     "json": True},

    {"name": "Twitter / X",  "icon": "🐦", "tier": 1,
     "url": "https://twitter.com/i/flow/password_reset",
     "method": "post",
     "payload": {"email": "{EMAIL}"},
     "found_re": r"(reset instructions|email sent)",
     "not_found_re": r"(no account|not found)",
     "inconclusive": True},

    {"name": "Facebook",     "icon": "📘", "tier": 1,
     "url": "https://www.facebook.com/login/identify/",
     "method": "post",
     "payload": {"email": "{EMAIL}"},
     "found_re": r"(account found|identify your account)",
     "not_found_re": r"(no account|not found)",
     "inconclusive": True},

    {"name": "Instagram",    "icon": "📸", "tier": 1,
     "url": "https://www.instagram.com/accounts/account_recovery_send_ajax/",
     "method": "post",
     "payload": {"email_or_username": "{EMAIL}"},
     "found_re": r'"email_sent":true',
     "not_found_re": r'"email_sent":false'},

    {"name": "LinkedIn",     "icon": "💼", "tier": 1,
     "url": "https://www.linkedin.com/checkpoint/lg/forgot-password",
     "method": "post",
     "payload": {"session_key": "{EMAIL}"},
     "found_re": r"(email.*sent|reset link sent)",
     "not_found_re": r"(no account|not found)",
     "inconclusive": True},

    {"name": "Reddit",       "icon": "🤖", "tier": 1,
     "url": "https://www.reddit.com/api/v1/register",
     "method": "post",
     "payload": {"email": "{EMAIL}", "verify": "true"},
     "found_re": r'"email_verified":true',
     "not_found_re": r'"email_verified":false',
     "inconclusive": True},

    {"name": "TikTok",       "icon": "🎵", "tier": 1,
     "url": "https://www.tiktok.com/passport/web/account/password/reset/",
     "method": "post",
     "payload": {"email": "{EMAIL}"},
     "found_re": r"(email sent|reset link)",
     "not_found_re": r"(not registered|no account)",
     "inconclusive": True},

    {"name": "Snapchat",     "icon": "👻", "tier": 1,
     "url": "https://accounts.snapchat.com/accounts/password_reset_request",
     "method": "post",
     "payload": {"email": "{EMAIL}"},
     "found_re": r"(email sent|instructions sent)",
     "not_found_re": r"(no account|not found)"},

    {"name": "Pinterest",    "icon": "📌", "tier": 1,
     "url": "https://www.pinterest.com/password/reset/",
     "method": "post",
     "payload": {"username_or_email": "{EMAIL}"},
     "found_re": r"(email sent|reset link)",
     "not_found_re": r"(no account|not found)"},

    {"name": "Tumblr",       "icon": "📓", "tier": 1,
     "url": "https://www.tumblr.com/forgot_password",
     "method": "post",
     "payload": {"email": "{EMAIL}"},
     "found_re": r"(email sent|reset link)",
     "not_found_re": r"(no account|not found)"},

    {"name": "Discord",      "icon": "🎮", "tier": 1,
     "url": "https://discord.com/api/v9/auth/forgot",
     "method": "post",
     "payload": {"email": "{EMAIL}"},
     "found_re": r"({})",   # Discord always returns 200 {}
     "not_found_re": r"NEVER_MATCH",
     "inconclusive": True},

    {"name": "Twitch",       "icon": "🟣", "tier": 1,
     "url": "https://passport.twitch.tv/password_reset_request",
     "method": "post",
     "payload": {"email": "{EMAIL}"},
     "found_re": r"(email sent|reset link)",
     "not_found_re": r"(no account|not found)",
     "inconclusive": True},

    {"name": "Steam",        "icon": "🎮", "tier": 1,
     "url": "https://store.steampowered.com/login/",
     "method": "post",
     "payload": {"email": "{EMAIL}", "action": "forgotpassword"},
     "found_re": r"(email sent|reset link)",
     "not_found_re": r"(no account|not found)",
     "inconclusive": True},

    # ── Tier 2: Developer / productivity ──────────────────────────────────
    {"name": "Vercel",       "icon": "▲", "tier": 2,
     "url": "https://vercel.com/api/registration/login",
     "method": "post",
     "payload": {"email": "{EMAIL}", "tokenName": "probe"},
     "found_re": r"(email sent|magic link|token)",
     "not_found_re": r"(not found|no account)"},

    {"name": "Netlify",      "icon": "🌿", "tier": 2,
     "url": "https://app.netlify.com/forgot",
     "method": "post",
     "payload": {"email": "{EMAIL}"},
     "found_re": r"(email sent|reset link)",
     "not_found_re": r"(no account|not found)"},

    {"name": "Heroku",       "icon": "☁️", "tier": 2,
     "url": "https://id.heroku.com/account/password/reset",
     "method": "post",
     "payload": {"email": "{EMAIL}"},
     "found_re": r"(email sent|reset link)",
     "not_found_re": r"(no account|not found)"},

    {"name": "Cloudflare",   "icon": "🔥", "tier": 2,
     "url": "https://dash.cloudflare.com/forgot-password",
     "method": "post",
     "payload": {"email": "{EMAIL}"},
     "found_re": r"(email sent|reset link)",
     "not_found_re": r"(no account|not found)"},

    {"name": "DigitalOcean", "icon": "🌊", "tier": 2,
     "url": "https://cloud.digitalocean.com/users/forgot_password",
     "method": "post",
     "payload": {"email": "{EMAIL}"},
     "found_re": r"(email sent|reset link)",
     "not_found_re": r"(no account|not found)"},

    {"name": "AWS",          "icon": "☁️", "tier": 2,
     "url": "https://signin.aws.amazon.com/forgotpassword",
     "method": "post",
     "payload": {"email": "{EMAIL}"},
     "found_re": r"(email sent|reset link)",
     "not_found_re": r"(no account|not found)",
     "inconclusive": True},

    {"name": "Notion",       "icon": "📝", "tier": 2,
     "url": "https://www.notion.so/api/v3/sendEmail",
     "method": "post",
     "payload": {"email": "{EMAIL}", "type": "login"},
     "found_re": r"(email sent|magic link)",
     "not_found_re": r"(not found|no account)"},

    {"name": "Figma",        "icon": "🎨", "tier": 2,
     "url": "https://www.figma.com/api/reset_password",
     "method": "post",
     "payload": {"email": "{EMAIL}"},
     "found_re": r"(email sent|reset link)",
     "not_found_re": r"(not found|no account)"},

    {"name": "Slack",        "icon": "💬", "tier": 2,
     "url": "https://slack.com/forgot",
     "method": "post",
     "payload": {"email": "{EMAIL}"},
     "found_re": r"(email sent|reset link)",
     "not_found_re": r"(no account|not found)"},

    {"name": "Trello",       "icon": "📋", "tier": 2,
     "url": "https://trello.com/forgot",
     "method": "post",
     "payload": {"email": "{EMAIL}"},
     "found_re": r"(email sent|reset link)",
     "not_found_re": r"(no account|not found)"},

    {"name": "Asana",        "icon": "🗂️", "tier": 2,
     "url": "https://app.asana.com/api/1.0/users/me/forgot_password",
     "method": "post",
     "payload": {"email": "{EMAIL}"},
     "found_re": r"(email sent|reset link)",
     "not_found_re": r"(no account|not found)"},

    {"name": "Jira",         "icon": "🔵", "tier": 2,
     "url": "https://id.atlassian.com/login/resetpassword",
     "method": "post",
     "payload": {"username": "{EMAIL}"},
     "found_re": r"(email sent|reset link)",
     "not_found_re": r"(no account|not found)"},

    {"name": "Confluence",   "icon": "📄", "tier": 2,
     "url": "https://id.atlassian.com/login/resetpassword",
     "method": "post",
     "payload": {"username": "{EMAIL}"},
     "found_re": r"(email sent|reset link)",
     "not_found_re": r"(no account|not found)"},

    {"name": "GitHub Copilot", "icon": "🤖", "tier": 2,
     "url": "https://github.com/password_reset",
     "method": "post",
     "payload": {"email": "{EMAIL}"},
     "found_re": r"(If an account exists)",
     "not_found_re": r"NEVER_MATCH",
     "inconclusive": True},

    {"name": "Bitbucket",    "icon": "🪣", "tier": 2,
     "url": "https://bitbucket.org/account/password/reset/",
     "method": "post",
     "payload": {"email": "{EMAIL}"},
     "found_re": r"(email sent|reset link)",
     "not_found_re": r"(no account|not found)"},

    {"name": "CircleCI",     "icon": "⭕", "tier": 2,
     "url": "https://circleci.com/auth/forgot-password",
     "method": "post",
     "payload": {"email": "{EMAIL}"},
     "found_re": r"(email sent|reset link)",
     "not_found_re": r"(no account|not found)"},

    {"name": "Render",       "icon": "🟣", "tier": 2,
     "url": "https://dashboard.render.com/forgot-password",
     "method": "post",
     "payload": {"email": "{EMAIL}"},
     "found_re": r"(email sent|reset link)",
     "not_found_re": r"(no account|not found)"},

    {"name": "Railway",      "icon": "🚂", "tier": 2,
     "url": "https://railway.app/forgot-password",
     "method": "post",
     "payload": {"email": "{EMAIL}"},
     "found_re": r"(email sent|reset link)",
     "not_found_re": r"(no account|not found)"},

    {"name": "Supabase",     "icon": "⚡", "tier": 2,
     "url": "https://app.supabase.com/api/profile/forgot-password",
     "method": "post",
     "payload": {"email": "{EMAIL}"},
     "found_re": r"(email sent|reset link)",
     "not_found_re": r"(no account|not found)"},

    {"name": "PlanetScale",  "icon": "🪐", "tier": 2,
     "url": "https://auth.planetscale.com/password/forgot",
     "method": "post",
     "payload": {"email": "{EMAIL}"},
     "found_re": r"(email sent|reset link)",
     "not_found_re": r"(no account|not found)"},

    {"name": "MongoDB Atlas", "icon": "🍃", "tier": 2,
     "url": "https://account.mongodb.com/account/forgotPassword",
     "method": "post",
     "payload": {"email": "{EMAIL}"},
     "found_re": r"(email sent|reset link)",
     "not_found_re": r"(no account|not found)"},

    {"name": "npm",          "icon": "📦", "tier": 2,
     "url": "https://www.npmjs.com/forgot",
     "method": "post",
     "payload": {"email": "{EMAIL}"},
     "found_re": r"(email sent|reset link)",
     "not_found_re": r"(no account|not found)"},

    {"name": "PyPI",         "icon": "🐍", "tier": 2,
     "url": "https://pypi.org/account/request-password-reset/",
     "method": "post",
     "payload": {"email_or_username": "{EMAIL}"},
     "found_re": r"(email sent|reset link)",
     "not_found_re": r"(no account|not found)"},

    {"name": "Replit",       "icon": "🔁", "tier": 2,
     "url": "https://replit.com/forgot",
     "method": "post",
     "payload": {"email": "{EMAIL}"},
     "found_re": r"(email sent|reset link)",
     "not_found_re": r"(no account|not found)"},

    {"name": "CodePen",      "icon": "✏️", "tier": 2,
     "url": "https://codepen.io/forgotpassword",
     "method": "post",
     "payload": {"email": "{EMAIL}"},
     "found_re": r"(email sent|reset link)",
     "not_found_re": r"(no account|not found)"},

    {"name": "Stack Overflow", "icon": "📚", "tier": 2,
     "url": "https://stackoverflow.com/users/account-recovery",
     "method": "post",
     "payload": {"email": "{EMAIL}"},
     "found_re": r"(email sent|reset link)",
     "not_found_re": r"(no account|not found)"},

    # ── Tier 3: Shopping / finance ─────────────────────────────────────────
    {"name": "Amazon",       "icon": "📦", "tier": 3,
     "url": "https://www.amazon.com/ap/forgotpassword",
     "method": "post",
     "payload": {"email": "{EMAIL}"},
     "found_re": r"(email sent|reset link|verify)",
     "not_found_re": r"(no account|not found)",
     "inconclusive": True},

    {"name": "eBay",         "icon": "🛒", "tier": 3,
     "url": "https://signin.ebay.com/ws/eBayISAPI.dll?ForgotPassword",
     "method": "post",
     "payload": {"userid": "{EMAIL}"},
     "found_re": r"(email sent|reset link)",
     "not_found_re": r"(no account|not found)"},

    {"name": "Etsy",         "icon": "🧶", "tier": 3,
     "url": "https://www.etsy.com/forgot_password",
     "method": "post",
     "payload": {"email": "{EMAIL}"},
     "found_re": r"(email sent|reset link)",
     "not_found_re": r"(no account|not found)"},

    {"name": "Shopify",      "icon": "🛍️", "tier": 3,
     "url": "https://accounts.shopify.com/lookup",
     "method": "post",
     "payload": {"email": "{EMAIL}"},
     "found_re": r"(email sent|reset link|account found)",
     "not_found_re": r"(no account|not found)"},

    {"name": "PayPal",       "icon": "💳", "tier": 3,
     "url": "https://www.paypal.com/authflow/forgotpassword",
     "method": "post",
     "payload": {"email": "{EMAIL}"},
     "found_re": r"(email sent|reset link)",
     "not_found_re": r"(no account|not found)",
     "inconclusive": True},

    {"name": "Stripe",       "icon": "💰", "tier": 3,
     "url": "https://dashboard.stripe.com/login/forgot-password",
     "method": "post",
     "payload": {"email": "{EMAIL}"},
     "found_re": r"(email sent|reset link)",
     "not_found_re": r"(no account|not found)"},

    {"name": "Wise",         "icon": "💸", "tier": 3,
     "url": "https://wise.com/forgotPassword",
     "method": "post",
     "payload": {"email": "{EMAIL}"},
     "found_re": r"(email sent|reset link)",
     "not_found_re": r"(no account|not found)"},

    {"name": "Revolut",      "icon": "🔵", "tier": 3,
     "url": "https://app.revolut.com/api/retail/user/current/password/forgotten",
     "method": "post",
     "payload": {"phone": "{EMAIL}"},
     "found_re": r"(email sent|reset link)",
     "not_found_re": r"(no account|not found)",
     "inconclusive": True},

    {"name": "Coinbase",     "icon": "🪙", "tier": 3,
     "url": "https://www.coinbase.com/forgot-password",
     "method": "post",
     "payload": {"email": "{EMAIL}"},
     "found_re": r"(email sent|reset link)",
     "not_found_re": r"(no account|not found)"},

    {"name": "Binance",      "icon": "🟡", "tier": 3,
     "url": "https://accounts.binance.com/en/forgot-password",
     "method": "post",
     "payload": {"email": "{EMAIL}"},
     "found_re": r"(email sent|reset link)",
     "not_found_re": r"(no account|not found)",
     "inconclusive": True},

    # ── Tier 4: Media / entertainment ─────────────────────────────────────
    {"name": "YouTube",      "icon": "▶️", "tier": 4,
     "url": "https://accounts.google.com/signin/v2/identifier",
     "method": "post",
     "payload": {"identifier": "{EMAIL}"},
     "found_re": r"(wrong password|enter your password)",
     "not_found_re": r"(couldn't find|no account)",
     "inconclusive": True},

    {"name": "Twitch",       "icon": "🟣", "tier": 4,
     "url": "https://passport.twitch.tv/password_reset_request",
     "method": "post",
     "payload": {"email": "{EMAIL}"},
     "found_re": r"(email sent|reset link)",
     "not_found_re": r"(no account|not found)",
     "inconclusive": True},

    {"name": "SoundCloud",   "icon": "🎧", "tier": 4,
     "url": "https://soundcloud.com/api/v2/password/resets",
     "method": "post",
     "payload": {"email": "{EMAIL}"},
     "found_re": r"(email sent|reset link)",
     "not_found_re": r"(no account|not found)"},

    {"name": "Deezer",       "icon": "🎵", "tier": 4,
     "url": "https://www.deezer.com/ajax/action.php",
     "method": "post",
     "payload": {"type": "forgot_password", "mail": "{EMAIL}"},
     "found_re": r"(email sent|reset link)",
     "not_found_re": r"(no account|not found)"},

    {"name": "Bandcamp",     "icon": "🎸", "tier": 4,
     "url": "https://bandcamp.com/api/login/1/forgot_password",
     "method": "post",
     "payload": {"email": "{EMAIL}"},
     "found_re": r"(email sent|reset link)",
     "not_found_re": r"(no account|not found)"},

    {"name": "Vimeo",        "icon": "🎞️", "tier": 4,
     "url": "https://vimeo.com/forgot_password",
     "method": "post",
     "payload": {"email": "{EMAIL}"},
     "found_re": r"(email sent|reset link)",
     "not_found_re": r"(no account|not found)"},

    {"name": "Duolingo",     "icon": "🦜", "tier": 4,
     "url": "https://www.duolingo.com/api/1/requestPasswordReset",
     "method": "post",
     "payload": {"email": "{EMAIL}"},
     "found_re": r"(email sent|reset link)",
     "not_found_re": r"(no account|not found)"},

    {"name": "Coursera",     "icon": "🎓", "tier": 4,
     "url": "https://www.coursera.org/api/passwordResetV2.v1",
     "method": "post",
     "payload": {"email": "{EMAIL}"},
     "found_re": r"(email sent|reset link)",
     "not_found_re": r"(no account|not found)"},

    {"name": "Udemy",        "icon": "📚", "tier": 4,
     "url": "https://www.udemy.com/api-2.0/auth/forgotpassword/",
     "method": "post",
     "payload": {"email": "{EMAIL}"},
     "found_re": r"(email sent|reset link)",
     "not_found_re": r"(no account|not found)"},

    {"name": "Medium",       "icon": "✍️", "tier": 4,
     "url": "https://medium.com/m/signin",
     "method": "post",
     "payload": {"email": "{EMAIL}"},
     "found_re": r"(email sent|magic link)",
     "not_found_re": r"(no account|not found)"},

    {"name": "Substack",     "icon": "📰", "tier": 4,
     "url": "https://substack.com/api/v1/email-login",
     "method": "post",
     "payload": {"email": "{EMAIL}", "redirect": "/"},
     "found_re": r"(email sent|magic link)",
     "not_found_re": r"(no account|not found)"},

    {"name": "Dev.to",       "icon": "👩‍💻", "tier": 4,
     "url": "https://dev.to/users/password",
     "method": "post",
     "payload": {"user[email]": "{EMAIL}"},
     "found_re": r"(email sent|reset link)",
     "not_found_re": r"(no account|not found)"},

    # ── Tier 5: Travel / food / lifestyle ─────────────────────────────────
    {"name": "Airbnb",       "icon": "🏠", "tier": 5,
     "url": "https://www.airbnb.com/forgot_password",
     "method": "post",
     "payload": {"email": "{EMAIL}"},
     "found_re": r"(email sent|reset link)",
     "not_found_re": r"(no account|not found)"},

    {"name": "Booking.com",  "icon": "🏨", "tier": 5,
     "url": "https://account.booking.com/accounts/password/reset",
     "method": "post",
     "payload": {"email": "{EMAIL}"},
     "found_re": r"(email sent|reset link)",
     "not_found_re": r"(no account|not found)"},

    {"name": "Uber",         "icon": "🚗", "tier": 5,
     "url": "https://auth.uber.com/v2/",
     "method": "post",
     "payload": {"email": "{EMAIL}"},
     "found_re": r"(email sent|reset link)",
     "not_found_re": r"(no account|not found)",
     "inconclusive": True},

    {"name": "Deliveroo",    "icon": "🛵", "tier": 5,
     "url": "https://api.deliveroo.com/auth/password_resets",
     "method": "post",
     "payload": {"email": "{EMAIL}"},
     "found_re": r"(email sent|reset link)",
     "not_found_re": r"(no account|not found)"},

    {"name": "Uber Eats",    "icon": "🍔", "tier": 5,
     "url": "https://auth.uber.com/v2/",
     "method": "post",
     "payload": {"email": "{EMAIL}"},
     "found_re": r"(email sent|reset link)",
     "not_found_re": r"(no account|not found)",
     "inconclusive": True},

    {"name": "Just Eat",     "icon": "🍕", "tier": 5,
     "url": "https://api.je-apis.com/account/forgotten-password",
     "method": "post",
     "payload": {"email": "{EMAIL}"},
     "found_re": r"(email sent|reset link)",
     "not_found_re": r"(no account|not found)"},

    # ── Tier 6: Productivity / storage ────────────────────────────────────
    {"name": "Dropbox",      "icon": "📦", "tier": 6,
     "url": "https://www.dropbox.com/forgot",
     "method": "post",
     "payload": {"email": "{EMAIL}"},
     "found_re": r"(email sent|reset link)",
     "not_found_re": r"(no account|not found)"},

    {"name": "Box",          "icon": "📂", "tier": 6,
     "url": "https://account.box.com/forgot_password",
     "method": "post",
     "payload": {"login": "{EMAIL}"},
     "found_re": r"(email sent|reset link)",
     "not_found_re": r"(no account|not found)"},

    {"name": "Google Drive", "icon": "📁", "tier": 6,
     "url": "https://accounts.google.com/signin/v2/identifier",
     "method": "post",
     "payload": {"identifier": "{EMAIL}"},
     "found_re": r"(wrong password|enter your password)",
     "not_found_re": r"(couldn't find|no account)",
     "inconclusive": True},

    {"name": "iCloud",       "icon": "☁️", "tier": 6,
     "url": "https://iforgot.apple.com/password/verify/appleid",
     "method": "post",
     "payload": {"id": "{EMAIL}"},
     "found_re": r"(verify|confirm)",
     "not_found_re": r"(no account|not found)",
     "inconclusive": True},

    {"name": "OneDrive",     "icon": "🔷", "tier": 6,
     "url": "https://login.live.com/GetCredentialType.srf",
     "method": "post",
     "payload": {"username": "{EMAIL}"},
     "found_re": r'"IfExistsResult":0',
     "not_found_re": r'"IfExistsResult":1',
     "json": True},

    {"name": "Evernote",     "icon": "🐘", "tier": 6,
     "url": "https://www.evernote.com/Registration.action",
     "method": "post",
     "payload": {"email": "{EMAIL}", "action": "send_pw_reset"},
     "found_re": r"(email sent|reset link)",
     "not_found_re": r"(no account|not found)"},

    {"name": "Todoist",      "icon": "✅", "tier": 6,
     "url": "https://todoist.com/Users/forgotPassword",
     "method": "post",
     "payload": {"email": "{EMAIL}"},
     "found_re": r"(email sent|reset link)",
     "not_found_re": r"(no account|not found)"},

    {"name": "Airtable",     "icon": "🗃️", "tier": 6,
     "url": "https://airtable.com/forgotPassword",
     "method": "post",
     "payload": {"email": "{EMAIL}"},
     "found_re": r"(email sent|reset link)",
     "not_found_re": r"(no account|not found)"},

    {"name": "Monday.com",   "icon": "🗓️", "tier": 6,
     "url": "https://auth.monday.com/auth/login_monday/forgot_password",
     "method": "post",
     "payload": {"email": "{EMAIL}"},
     "found_re": r"(email sent|reset link)",
     "not_found_re": r"(no account|not found)"},

    {"name": "ClickUp",      "icon": "🖱️", "tier": 6,
     "url": "https://app.clickup.com/forgot",
     "method": "post",
     "payload": {"email": "{EMAIL}"},
     "found_re": r"(email sent|reset link)",
     "not_found_re": r"(no account|not found)"},

    {"name": "Linear",       "icon": "📐", "tier": 6,
     "url": "https://linear.app/forgot-password",
     "method": "post",
     "payload": {"email": "{EMAIL}"},
     "found_re": r"(email sent|reset link)",
     "not_found_re": r"(no account|not found)"},

    {"name": "Basecamp",     "icon": "🏕️", "tier": 6,
     "url": "https://launchpad.37signals.com/sessions/forgot",
     "method": "post",
     "payload": {"email_address": "{EMAIL}"},
     "found_re": r"(email sent|reset link)",
     "not_found_re": r"(no account|not found)"},

    # ── Tier 7: Design / creative ──────────────────────────────────────────
    {"name": "Adobe",        "icon": "🎨", "tier": 7,
     "url": "https://adobeid-na1.services.adobe.com/renga/public/initPasswordReset",
     "method": "post",
     "payload": {"email": "{EMAIL}"},
     "found_re": r"(email sent|reset link)",
     "not_found_re": r"(no account|not found)"},

    {"name": "Canva",        "icon": "✏️", "tier": 7,
     "url": "https://www.canva.com/api/account/forgot-password",
     "method": "post",
     "payload": {"email": "{EMAIL}"},
     "found_re": r"(email sent|reset link)",
     "not_found_re": r"(no account|not found)"},

    {"name": "Behance",      "icon": "🖼️", "tier": 7,
     "url": "https://www.behance.net/accounts/forgotpassword",
     "method": "post",
     "payload": {"email": "{EMAIL}"},
     "found_re": r"(email sent|reset link)",
     "not_found_re": r"(no account|not found)"},

    {"name": "Dribbble",     "icon": "🏀", "tier": 7,
     "url": "https://dribbble.com/password/resets",
     "method": "post",
     "payload": {"email": "{EMAIL}"},
     "found_re": r"(email sent|reset link)",
     "not_found_re": r"(no account|not found)"},

    {"name": "Sketch",       "icon": "💎", "tier": 7,
     "url": "https://www.sketch.com/api/forgot-password",
     "method": "post",
     "payload": {"email": "{EMAIL}"},
     "found_re": r"(email sent|reset link)",
     "not_found_re": r"(no account|not found)"},

    {"name": "InVision",     "icon": "🔮", "tier": 7,
     "url": "https://projects.invisionapp.com/api/auth/forgot-password",
     "method": "post",
     "payload": {"email": "{EMAIL}"},
     "found_re": r"(email sent|reset link)",
     "not_found_re": r"(no account|not found)"},

    {"name": "Miro",         "icon": "🎯", "tier": 7,
     "url": "https://miro.com/api/v1/accounts/request-password-reset/",
     "method": "post",
     "payload": {"email": "{EMAIL}"},
     "found_re": r"(email sent|reset link)",
     "not_found_re": r"(no account|not found)"},

    {"name": "Loom",         "icon": "🎥", "tier": 7,
     "url": "https://www.loom.com/api/auth/forgot-password",
     "method": "post",
     "payload": {"email": "{EMAIL}"},
     "found_re": r"(email sent|reset link)",
     "not_found_re": r"(no account|not found)"},

    # ── Tier 8: Communication ──────────────────────────────────────────────
    {"name": "Zoom",         "icon": "🎦", "tier": 8,
     "url": "https://zoom.us/forgot_password",
     "method": "post",
     "payload": {"email": "{EMAIL}"},
     "found_re": r"(email sent|reset link)",
     "not_found_re": r"(no account|not found)"},

    {"name": "Teams",        "icon": "👥", "tier": 8,
     "url": "https://login.live.com/GetCredentialType.srf",
     "method": "post",
     "payload": {"username": "{EMAIL}"},
     "found_re": r'"IfExistsResult":0',
     "not_found_re": r'"IfExistsResult":1',
     "json": True},

    {"name": "Skype",        "icon": "🔵", "tier": 8,
     "url": "https://login.live.com/GetCredentialType.srf",
     "method": "post",
     "payload": {"username": "{EMAIL}"},
     "found_re": r'"IfExistsResult":0',
     "not_found_re": r'"IfExistsResult":1',
     "json": True},

    {"name": "Telegram",     "icon": "✈️", "tier": 8,
     "url": "https://my.telegram.org/auth/send_password",
     "method": "post",
     "payload": {"phone": "{EMAIL}"},
     "found_re": r"(sent|ok)",
     "not_found_re": r"(not found|error)",
     "inconclusive": True},

    {"name": "Signal",       "icon": "🔒", "tier": 8,
     "url": "https://textsecure-service.whispersystems.org/v1/accounts/sms/code",
     "method": "get",
     "payload": {"number": "{EMAIL}"},
     "found_re": r"(ok|success)",
     "not_found_re": r"(error|not found)",
     "inconclusive": True},

    {"name": "WhatsApp",     "icon": "💬", "tier": 8,
     "url": "https://www.whatsapp.com/",
     "method": "get",
     "payload": {},
     "found_re": r"NEVER_MATCH",
     "not_found_re": r"NEVER_MATCH",
     "inconclusive": True},

    {"name": "Intercom",     "icon": "💬", "tier": 8,
     "url": "https://app.intercom.com/admins/password_reset",
     "method": "post",
     "payload": {"email": "{EMAIL}"},
     "found_re": r"(email sent|reset link)",
     "not_found_re": r"(no account|not found)"},

    {"name": "Zendesk",      "icon": "🎫", "tier": 8,
     "url": "https://support.zendesk.com/hc/en-us/requests/new",
     "method": "post",
     "payload": {"email": "{EMAIL}"},
     "found_re": r"(email sent|reset link)",
     "not_found_re": r"(no account|not found)"},

    # ── Tier 9: Gaming ─────────────────────────────────────────────────────
    {"name": "Epic Games",   "icon": "🎮", "tier": 9,
     "url": "https://www.epicgames.com/id/api/resetPassword",
     "method": "post",
     "payload": {"email": "{EMAIL}"},
     "found_re": r"(email sent|reset link)",
     "not_found_re": r"(no account|not found)"},

    {"name": "EA / Origin",  "icon": "🎯", "tier": 9,
     "url": "https://signin.ea.com/p/web2/resetPassword",
     "method": "post",
     "payload": {"email": "{EMAIL}"},
     "found_re": r"(email sent|reset link)",
     "not_found_re": r"(no account|not found)"},

    {"name": "Ubisoft",      "icon": "🎮", "tier": 9,
     "url": "https://account.ubisoft.com/api/users/sendpasswordreset",
     "method": "post",
     "payload": {"email": "{EMAIL}"},
     "found_re": r"(email sent|reset link)",
     "not_found_re": r"(no account|not found)"},

    {"name": "Battle.net",   "icon": "⚔️", "tier": 9,
     "url": "https://us.battle.net/login/en/forgotPassword",
     "method": "post",
     "payload": {"email": "{EMAIL}"},
     "found_re": r"(email sent|reset link)",
     "not_found_re": r"(no account|not found)"},

    {"name": "PlayStation",  "icon": "🎮", "tier": 9,
     "url": "https://ca.account.sony.com/api/v1/ssocookie",
     "method": "post",
     "payload": {"loginId": "{EMAIL}"},
     "found_re": r"(email sent|reset link)",
     "not_found_re": r"(no account|not found)",
     "inconclusive": True},

    {"name": "Xbox",         "icon": "🎮", "tier": 9,
     "url": "https://login.live.com/GetCredentialType.srf",
     "method": "post",
     "payload": {"username": "{EMAIL}"},
     "found_re": r'"IfExistsResult":0',
     "not_found_re": r'"IfExistsResult":1',
     "json": True},

    {"name": "Nintendo",     "icon": "🕹️", "tier": 9,
     "url": "https://accounts.nintendo.com/api/2.0/forgotPassword",
     "method": "post",
     "payload": {"loginId": "{EMAIL}"},
     "found_re": r"(email sent|reset link)",
     "not_found_re": r"(no account|not found)"},

    {"name": "Roblox",       "icon": "🟥", "tier": 9,
     "url": "https://auth.roblox.com/v1/users/forgot-password",
     "method": "post",
     "payload": {"targetUsername": "{EMAIL}"},
     "found_re": r"(email sent|reset link)",
     "not_found_re": r"(no account|not found)"},

    {"name": "Chess.com",    "icon": "♟️", "tier": 9,
     "url": "https://www.chess.com/recover",
     "method": "post",
     "payload": {"email": "{EMAIL}"},
     "found_re": r"(email sent|reset link)",
     "not_found_re": r"(no account|not found)"},

    # ── Tier 10: News / reading ────────────────────────────────────────────
    {"name": "New York Times", "icon": "🗞️", "tier": 10,
     "url": "https://myaccount.nytimes.com/auth/forgot-password",
     "method": "post",
     "payload": {"email": "{EMAIL}"},
     "found_re": r"(email sent|reset link)",
     "not_found_re": r"(no account|not found)"},

    {"name": "The Guardian", "icon": "📰", "tier": 10,
     "url": "https://profile.theguardian.com/password/send-password-reset",
     "method": "post",
     "payload": {"email": "{EMAIL}"},
     "found_re": r"(email sent|reset link)",
     "not_found_re": r"(no account|not found)"},

    {"name": "Pocket",       "icon": "📥", "tier": 10,
     "url": "https://getpocket.com/forgot",
     "method": "post",
     "payload": {"feed_id": "{EMAIL}"},
     "found_re": r"(email sent|reset link)",
     "not_found_re": r"(no account|not found)"},

    {"name": "Goodreads",    "icon": "📚", "tier": 10,
     "url": "https://www.goodreads.com/user/forgot_password",
     "method": "post",
     "payload": {"user[email]": "{EMAIL}"},
     "found_re": r"(email sent|reset link)",
     "not_found_re": r"(no account|not found)"},

    {"name": "Feedly",       "icon": "📡", "tier": 10,
     "url": "https://feedly.com/i/forgot",
     "method": "post",
     "payload": {"email": "{EMAIL}"},
     "found_re": r"(email sent|reset link)",
     "not_found_re": r"(no account|not found)"},

    # ── Tier 11: Health / fitness ──────────────────────────────────────────
    {"name": "MyFitnessPal", "icon": "🏃", "tier": 11,
     "url": "https://www.myfitnesspal.com/api/auth/forgot-password",
     "method": "post",
     "payload": {"email": "{EMAIL}"},
     "found_re": r"(email sent|reset link)",
     "not_found_re": r"(no account|not found)"},

    {"name": "Strava",       "icon": "🚴", "tier": 11,
     "url": "https://www.strava.com/password/new",
     "method": "post",
     "payload": {"email": "{EMAIL}"},
     "found_re": r"(email sent|reset link)",
     "not_found_re": r"(no account|not found)"},

    {"name": "Fitbit",       "icon": "⌚", "tier": 11,
     "url": "https://www.fitbit.com/api/1/user/-/password/reset.json",
     "method": "post",
     "payload": {"email": "{EMAIL}"},
     "found_re": r"(email sent|reset link)",
     "not_found_re": r"(no account|not found)"},

    {"name": "Garmin",       "icon": "🏅", "tier": 11,
     "url": "https://sso.garmin.com/sso/forgotPassword",
     "method": "post",
     "payload": {"username": "{EMAIL}"},
     "found_re": r"(email sent|reset link)",
     "not_found_re": r"(no account|not found)"},

    {"name": "Peloton",      "icon": "🚵", "tier": 11,
     "url": "https://api.onepeloton.com/auth/forgot_password",
     "method": "post",
     "payload": {"email": "{EMAIL}"},
     "found_re": r"(email sent|reset link)",
     "not_found_re": r"(no account|not found)"},

    # ── Tier 12: AI / tech tools ───────────────────────────────────────────
    {"name": "OpenAI",       "icon": "🤖", "tier": 12,
     "url": "https://auth0.openai.com/dbconnections/change_password",
     "method": "post",
     "payload": {"email": "{EMAIL}", "connection": "Username-Password-Authentication", "client_id": "TdJIcbe16WoTHtN95nyywh5E4yOo6ItG"},
     "found_re": r"(email sent|reset link|We've just sent)",
     "not_found_re": r"(no account|not found)"},

    {"name": "Anthropic",    "icon": "🧠", "tier": 12,
     "url": "https://claude.ai/api/auth/forgot-password",
     "method": "post",
     "payload": {"email": "{EMAIL}"},
     "found_re": r"(email sent|reset link)",
     "not_found_re": r"(no account|not found)"},

    {"name": "Hugging Face", "icon": "🤗", "tier": 12,
     "url": "https://huggingface.co/users/password-reset",
     "method": "post",
     "payload": {"email": "{EMAIL}"},
     "found_re": r"(email sent|reset link)",
     "not_found_re": r"(no account|not found)"},

    {"name": "Replicate",    "icon": "🔄", "tier": 12,
     "url": "https://replicate.com/forgot-password",
     "method": "post",
     "payload": {"email": "{EMAIL}"},
     "found_re": r"(email sent|reset link)",
     "not_found_re": r"(no account|not found)"},

    {"name": "Weights & Biases", "icon": "📊", "tier": 12,
     "url": "https://api.wandb.ai/oidc/reset_password",
     "method": "post",
     "payload": {"email": "{EMAIL}"},
     "found_re": r"(email sent|reset link)",
     "not_found_re": r"(no account|not found)"},

    # ── Tier 13: Business / SaaS ───────────────────────────────────────────
    {"name": "Salesforce",   "icon": "☁️", "tier": 13,
     "url": "https://login.salesforce.com/secur/forgotpassword.jsp",
     "method": "post",
     "payload": {"un": "{EMAIL}"},
     "found_re": r"(email sent|reset link)",
     "not_found_re": r"(no account|not found)"},

    {"name": "HubSpot",      "icon": "🧡", "tier": 13,
     "url": "https://app.hubspot.com/login/forgot-password",
     "method": "post",
     "payload": {"email": "{EMAIL}"},
     "found_re": r"(email sent|reset link)",
     "not_found_re": r"(no account|not found)"},

    {"name": "Mailchimp",    "icon": "🐒", "tier": 13,
     "url": "https://login.mailchimp.com/forgot-password/",
     "method": "post",
     "payload": {"email": "{EMAIL}"},
     "found_re": r"(email sent|reset link)",
     "not_found_re": r"(no account|not found)"},

    {"name": "Zapier",       "icon": "⚡", "tier": 13,
     "url": "https://zapier.com/accounts/forgot-password/",
     "method": "post",
     "payload": {"email": "{EMAIL}"},
     "found_re": r"(email sent|reset link)",
     "not_found_re": r"(no account|not found)"},

    {"name": "Make",         "icon": "🔧", "tier": 13,
     "url": "https://www.make.com/en/login/forgot-password",
     "method": "post",
     "payload": {"email": "{EMAIL}"},
     "found_re": r"(email sent|reset link)",
     "not_found_re": r"(no account|not found)"},

    {"name": "Typeform",     "icon": "📋", "tier": 13,
     "url": "https://api.typeform.com/accounts/password/reset",
     "method": "post",
     "payload": {"email": "{EMAIL}"},
     "found_re": r"(email sent|reset link)",
     "not_found_re": r"(no account|not found)"},

    {"name": "ConvertKit",   "icon": "📧", "tier": 13,
     "url": "https://app.convertkit.com/users/forgot_password",
     "method": "post",
     "payload": {"email": "{EMAIL}"},
     "found_re": r"(email sent|reset link)",
     "not_found_re": r"(no account|not found)"},

    {"name": "Webflow",      "icon": "🌊", "tier": 13,
     "url": "https://webflow.com/api/1.0/account/reset",
     "method": "post",
     "payload": {"email": "{EMAIL}"},
     "found_re": r"(email sent|reset link)",
     "not_found_re": r"(no account|not found)"},

    {"name": "Ghost",        "icon": "👻", "tier": 13,
     "url": "https://ghost.org/api/v2/admin/authentication/password_reset",
     "method": "post",
     "payload": {"email": "{EMAIL}"},
     "found_re": r"(email sent|reset link)",
     "not_found_re": r"(no account|not found)"},

    {"name": "Squarespace",  "icon": "⬛", "tier": 13,
     "url": "https://account.squarespace.com/api/1/auth/password-recovery",
     "method": "post",
     "payload": {"email": "{EMAIL}"},
     "found_re": r"(email sent|reset link)",
     "not_found_re": r"(no account|not found)"},

    {"name": "Wix",          "icon": "🔵", "tier": 13,
     "url": "https://manage.wix.com/forgot-password",
     "method": "post",
     "payload": {"email": "{EMAIL}"},
     "found_re": r"(email sent|reset link)",
     "not_found_re": r"(no account|not found)"},

    {"name": "WordPress.com", "icon": "🔷", "tier": 13,
     "url": "https://wordpress.com/wp-login.php?action=lostpassword",
     "method": "post",
     "payload": {"user_login": "{EMAIL}"},
     "found_re": r"(email sent|reset link)",
     "not_found_re": r"(no account|not found)"},

    # ── Tier 14: Security / identity ──────────────────────────────────────
    {"name": "1Password",    "icon": "🔑", "tier": 14,
     "url": "https://my.1password.com/auth/forgot",
     "method": "post",
     "payload": {"email": "{EMAIL}"},
     "found_re": r"(email sent|reset link)",
     "not_found_re": r"(no account|not found)"},

    {"name": "LastPass",     "icon": "🔐", "tier": 14,
     "url": "https://lastpass.com/recover.php",
     "method": "post",
     "payload": {"email": "{EMAIL}"},
     "found_re": r"(email sent|reset link)",
     "not_found_re": r"(no account|not found)"},

    {"name": "Bitwarden",    "icon": "🛡️", "tier": 14,
     "url": "https://vault.bitwarden.com/api/accounts/password-hint",
     "method": "post",
     "payload": {"email": "{EMAIL}"},
     "found_re": r"(email sent|hint sent)",
     "not_found_re": r"(no account|not found)"},

    {"name": "Dashlane",     "icon": "🔒", "tier": 14,
     "url": "https://ws1.dashlane.com/account/requestEmailTokenToResetMP",
     "method": "post",
     "payload": {"login": "{EMAIL}"},
     "found_re": r'"code":"SUCCESS"',
     "not_found_re": r'"code":"UNKNOWN_USER"'},

    {"name": "Authy",        "icon": "🔑", "tier": 14,
     "url": "https://api.authy.com/protected/json/users/new",
     "method": "post",
     "payload": {"user[email]": "{EMAIL}"},
     "found_re": r"(success|registered)",
     "not_found_re": r"(not found|error)",
     "inconclusive": True},

    {"name": "NordVPN",      "icon": "🛡️", "tier": 14,
     "url": "https://api.nordvpn.com/v1/users/auth/forgot-password",
     "method": "post",
     "payload": {"email": "{EMAIL}"},
     "found_re": r"(email sent|reset link)",
     "not_found_re": r"(no account|not found)"},

    {"name": "ExpressVPN",   "icon": "🔒", "tier": 14,
     "url": "https://www.expressvpn.com/api/reset-password",
     "method": "post",
     "payload": {"email": "{EMAIL}"},
     "found_re": r"(email sent|reset link)",
     "not_found_re": r"(no account|not found)"},

    # ── Tier 15: Domain / hosting ──────────────────────────────────────────
    {"name": "GoDaddy",      "icon": "🐢", "tier": 15,
     "url": "https://sso.godaddy.com/v1/account/credentials/reset",
     "method": "post",
     "payload": {"email": "{EMAIL}"},
     "found_re": r"(email sent|reset link)",
     "not_found_re": r"(no account|not found)"},

    {"name": "Namecheap",    "icon": "🏷️", "tier": 15,
     "url": "https://www.namecheap.com/myaccount/reset-password/",
     "method": "post",
     "payload": {"EmailAddress": "{EMAIL}"},
     "found_re": r"(email sent|reset link)",
     "not_found_re": r"(no account|not found)"},

    {"name": "OVH",          "icon": "☁️", "tier": 15,
     "url": "https://www.ovhcloud.com/auth/forgot-password",
     "method": "post",
     "payload": {"email": "{EMAIL}"},
     "found_re": r"(email sent|reset link)",
     "not_found_re": r"(no account|not found)"},

    {"name": "Hetzner",      "icon": "🖥️", "tier": 15,
     "url": "https://accounts.hetzner.com/forgot_password",
     "method": "post",
     "payload": {"_username": "{EMAIL}"},
     "found_re": r"(email sent|reset link)",
     "not_found_re": r"(no account|not found)"},

    # ── Tier 16: Social / dating ───────────────────────────────────────────
    {"name": "Meetup",       "icon": "🤝", "tier": 16,
     "url": "https://api.meetup.com/sessions/forgot_password",
     "method": "post",
     "payload": {"email": "{EMAIL}"},
     "found_re": r"(email sent|reset link)",
     "not_found_re": r"(no account|not found)"},

    {"name": "Bumble",       "icon": "🐝", "tier": 16,
     "url": "https://bumble.com/forgot-password",
     "method": "post",
     "payload": {"email": "{EMAIL}"},
     "found_re": r"(email sent|reset link)",
     "not_found_re": r"(no account|not found)",
     "inconclusive": True},

    {"name": "Tinder",       "icon": "🔥", "tier": 16,
     "url": "https://api.gotinder.com/v2/auth/sms/send",
     "method": "post",
     "payload": {"phone_number": "{EMAIL}"},
     "found_re": r"(sent|success)",
     "not_found_re": r"(error|not found)",
     "inconclusive": True},

    {"name": "Strava",       "icon": "🚴", "tier": 16,
     "url": "https://www.strava.com/password/new",
     "method": "post",
     "payload": {"email": "{EMAIL}"},
     "found_re": r"(email sent|reset link)",
     "not_found_re": r"(no account|not found)"},
]

# ── Async probe engine ─────────────────────────────────────────────────────────

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/json,*/*;q=0.9",
    "Accept-Language": "en-US,en;q=0.9",
}

TIMEOUT = aiohttp.ClientTimeout(total=10)


async def _probe_site(session: aiohttp.ClientSession, site: dict, email: str) -> dict:
    """Probe a single site and return a result dict."""
    if site.get("inconclusive"):
        return {
            "site":   site["name"],
            "icon":   site["icon"],
            "email":  email,
            "status": "inconclusive",
            "tier":   site["tier"],
        }

    url     = site["url"]
    method  = site["method"]
    payload = {k: v.replace("{EMAIL}", email) for k, v in site.get("payload", {}).items()}
    headers = {**HEADERS, **site.get("headers", {})}
    use_json = site.get("json", False)

    try:
        if method == "post":
            if use_json:
                resp = await session.post(url, json=payload, headers=headers, timeout=TIMEOUT, ssl=False)
            else:
                resp = await session.post(url, data=payload, headers=headers, timeout=TIMEOUT, ssl=False)
        else:
            resp = await session.get(url, params=payload, headers=headers, timeout=TIMEOUT, ssl=False)

        body = await resp.text(errors="replace")

        found_re     = site.get("found_re", "")
        not_found_re = site.get("not_found_re", "")

        if found_re     and re.search(found_re,     body, re.IGNORECASE):
            status = "found"
        elif not_found_re and re.search(not_found_re, body, re.IGNORECASE):
            status = "not_found"
        else:
            status = "inconclusive"

    except Exception:
        status = "inconclusive"

    return {
        "site":   site["name"],
        "icon":   site["icon"],
        "email":  email,
        "status": status,
        "tier":   site["tier"],
    }


async def _probe_all(email: str) -> list[dict]:
    """Probe all sites for a single email address."""
    # Deduplicate sites by name
    seen  = set()
    sites = []
    for s in SITES:
        if s["name"] not in seen:
            seen.add(s["name"])
            sites.append(s)

    connector = aiohttp.TCPConnector(ssl=False, limit=20)
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = [_probe_site(session, site, email) for site in sites]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    return [r for r in results if isinstance(r, dict)]


# ── Public API ─────────────────────────────────────────────────────────────────

def probe_email(email: str) -> list[dict]:
    """
    Probe all sites for a single email address.
    Returns a list of result dicts with keys: site, icon, email, status, tier.
    """
    return asyncio.run(_probe_all(email))


def probe_domain(domain: str, addresses: list[str]) -> list[dict]:
    """
    Probe all sites for a list of known addresses on the domain.
    domain: e.g. "friedutch.plus"
    addresses: list of full email addresses, e.g. ["hello@friedutch.plus"]
    """
    all_results = []
    for email in addresses:
        results = probe_email(email)
        all_results.extend(results)
    return all_results


def get_site_count() -> int:
    """Return the number of unique sites in the probe list."""
    return len({s["name"] for s in SITES})
