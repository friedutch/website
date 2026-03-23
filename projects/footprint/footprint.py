import os
import datetime
import asyncio as _asyncio
import sqlite3 as _sqlite3
import aiohttp as _aiohttp
import re as _re
import requests as _requests
import bleach as _bleach
from flask import request, jsonify
from app.rendering import render_page

from projects.smartlock.smartlock import is_admin, require_admin_login

FOOTPRINT_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "footprint.db")
HIBP_API_KEY = os.getenv("HIBP_API_KEY", "")
HIBP_HEADERS = {"hibp-api-key": HIBP_API_KEY, "user-agent": "friedutch-footprint/1.0"}


def init_footprint_db():
    db = _sqlite3.connect(FOOTPRINT_DB_PATH)
    db.execute("""CREATE TABLE IF NOT EXISTS scans (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        target TEXT NOT NULL,
        scan_type TEXT NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS breaches (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        scan_id INTEGER NOT NULL,
        email TEXT NOT NULL,
        site TEXT NOT NULL,
        breach_date TEXT,
        severity TEXT,
        data_classes TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS probe_results (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        scan_id INTEGER NOT NULL,
        email TEXT NOT NULL,
        site TEXT NOT NULL,
        status TEXT NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS addresses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        scan_id INTEGER NOT NULL,
        email TEXT NOT NULL,
        breach_count INTEGER DEFAULT 0,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )""")
    db.commit()
    db.close()


_SITES = [
    {"name":"GitHub",        "icon":"🐙", "url":"https://github.com/password_reset",                                           "method":"post","payload":{"email":"{EMAIL}"},                                                          "found_re":r"(If an account exists|reset password)","not_found_re":r"(No account|couldn't find)","inconclusive":True},
    {"name":"GitLab",        "icon":"🦊", "url":"https://gitlab.com/users/password",                                           "method":"post","payload":{"user[email]":"{EMAIL}"},                                                    "found_re":r"(Instructions have been sent)","not_found_re":r"(not found|no user)"},
    {"name":"Microsoft",     "icon":"🪟", "url":"https://login.live.com/GetCredentialType.srf",                                "method":"post","payload":{"username":"{EMAIL}"},                                                       "found_re":r'"IfExistsResult":0',"not_found_re":r'"IfExistsResult":1',"json":True},
    {"name":"Instagram",     "icon":"📸", "url":"https://www.instagram.com/accounts/account_recovery_send_ajax/",              "method":"post","payload":{"email_or_username":"{EMAIL}"},                                             "found_re":r'"email_sent":true',"not_found_re":r'"email_sent":false'},
    {"name":"Snapchat",      "icon":"👻", "url":"https://accounts.snapchat.com/accounts/password_reset_request",               "method":"post","payload":{"email":"{EMAIL}"},                                                          "found_re":r"(email sent|instructions sent)","not_found_re":r"(no account|not found)"},
    {"name":"Pinterest",     "icon":"📌", "url":"https://www.pinterest.com/password/reset/",                                   "method":"post","payload":{"username_or_email":"{EMAIL}"},                                             "found_re":r"(email sent|reset link)","not_found_re":r"(no account|not found)"},
    {"name":"Tumblr",        "icon":"📓", "url":"https://www.tumblr.com/forgot_password",                                      "method":"post","payload":{"email":"{EMAIL}"},                                                          "found_re":r"(email sent|reset link)","not_found_re":r"(no account|not found)"},
    {"name":"Discord",       "icon":"🎮", "url":"https://discord.com/api/v9/auth/forgot",                                      "method":"post","payload":{"email":"{EMAIL}"},                                                          "found_re":r"NEVER","not_found_re":r"NEVER","inconclusive":True},
    {"name":"Spotify",       "icon":"🎵", "url":"https://accounts.spotify.com/en/password-reset",                              "method":"post","payload":{"email":"{EMAIL}"},                                                          "found_re":r"(email.*sent|check your inbox)","not_found_re":r"(no account|doesn't exist)","inconclusive":True},
    {"name":"Netflix",       "icon":"🎬", "url":"https://www.netflix.com/LoginHelp",                                           "method":"post","payload":{"email":"{EMAIL}","flow":"pwd"},                                            "found_re":r"(email.*sent|reset link)","not_found_re":r"(no account|couldn't find)","inconclusive":True},
    {"name":"Google",        "icon":"🔍", "url":"https://accounts.google.com/signin/v2/identifier",                            "method":"post","payload":{"identifier":"{EMAIL}"},                                                    "found_re":r"(wrong password|enter your password)","not_found_re":r"(couldn't find|no account)","inconclusive":True},
    {"name":"Apple",         "icon":"🍎", "url":"https://iforgot.apple.com/password/verify/appleid",                           "method":"post","payload":{"id":"{EMAIL}"},                                                             "found_re":r"(verify|confirm)","not_found_re":r"(no account|not found)","inconclusive":True},
    {"name":"Twitter / X",   "icon":"🐦", "url":"https://twitter.com/i/flow/password_reset",                                   "method":"post","payload":{"email":"{EMAIL}"},                                                          "found_re":r"(reset instructions|email sent)","not_found_re":r"(no account|not found)","inconclusive":True},
    {"name":"Facebook",      "icon":"📘", "url":"https://www.facebook.com/login/identify/",                                    "method":"post","payload":{"email":"{EMAIL}"},                                                          "found_re":r"(account found|identify)","not_found_re":r"(no account|not found)","inconclusive":True},
    {"name":"LinkedIn",      "icon":"💼", "url":"https://www.linkedin.com/checkpoint/lg/forgot-password",                      "method":"post","payload":{"session_key":"{EMAIL}"},                                                   "found_re":r"(email.*sent|reset link)","not_found_re":r"(no account|not found)","inconclusive":True},
    {"name":"TikTok",        "icon":"🎵", "url":"https://www.tiktok.com/passport/web/account/password/reset/",                 "method":"post","payload":{"email":"{EMAIL}"},                                                          "found_re":r"(email sent|reset link)","not_found_re":r"(not registered|no account)","inconclusive":True},
    {"name":"Steam",         "icon":"🎮", "url":"https://store.steampowered.com/login/",                                       "method":"post","payload":{"email":"{EMAIL}","action":"forgotpassword"},                               "found_re":r"(email sent|reset link)","not_found_re":r"(no account|not found)","inconclusive":True},
    {"name":"Twitch",        "icon":"🟣", "url":"https://passport.twitch.tv/password_reset_request",                           "method":"post","payload":{"email":"{EMAIL}"},                                                          "found_re":r"(email sent|reset link)","not_found_re":r"(no account|not found)","inconclusive":True},
    {"name":"Reddit",        "icon":"🤖", "url":"https://www.reddit.com/api/v1/register",                                      "method":"post","payload":{"email":"{EMAIL}","verify":"true"},                                         "found_re":r'"email_verified":true',"not_found_re":r'"email_verified":false',"inconclusive":True},
    {"name":"Vercel",        "icon":"▲",  "url":"https://vercel.com/api/registration/login",                                   "method":"post","payload":{"email":"{EMAIL}","tokenName":"probe"},                                    "found_re":r"(email sent|magic link|token)","not_found_re":r"(not found|no account)"},
    {"name":"Netlify",       "icon":"🌿", "url":"https://app.netlify.com/forgot",                                              "method":"post","payload":{"email":"{EMAIL}"},                                                          "found_re":r"(email sent|reset link)","not_found_re":r"(no account|not found)"},
    {"name":"Heroku",        "icon":"☁️", "url":"https://id.heroku.com/account/password/reset",                                "method":"post","payload":{"email":"{EMAIL}"},                                                          "found_re":r"(email sent|reset link)","not_found_re":r"(no account|not found)"},
    {"name":"Cloudflare",    "icon":"🔥", "url":"https://dash.cloudflare.com/forgot-password",                                 "method":"post","payload":{"email":"{EMAIL}"},                                                          "found_re":r"(email sent|reset link)","not_found_re":r"(no account|not found)"},
    {"name":"DigitalOcean",  "icon":"🌊", "url":"https://cloud.digitalocean.com/users/forgot_password",                        "method":"post","payload":{"email":"{EMAIL}"},                                                          "found_re":r"(email sent|reset link)","not_found_re":r"(no account|not found)"},
    {"name":"Notion",        "icon":"📝", "url":"https://www.notion.so/api/v3/sendEmail",                                      "method":"post","payload":{"email":"{EMAIL}","type":"login"},                                          "found_re":r"(email sent|magic link)","not_found_re":r"(not found|no account)"},
    {"name":"Figma",         "icon":"🎨", "url":"https://www.figma.com/api/reset_password",                                    "method":"post","payload":{"email":"{EMAIL}"},                                                          "found_re":r"(email sent|reset link)","not_found_re":r"(not found|no account)"},
    {"name":"Slack",         "icon":"💬", "url":"https://slack.com/forgot",                                                    "method":"post","payload":{"email":"{EMAIL}"},                                                          "found_re":r"(email sent|reset link)","not_found_re":r"(no account|not found)"},
    {"name":"Trello",        "icon":"📋", "url":"https://trello.com/forgot",                                                   "method":"post","payload":{"email":"{EMAIL}"},                                                          "found_re":r"(email sent|reset link)","not_found_re":r"(no account|not found)"},
    {"name":"Asana",         "icon":"🗂️", "url":"https://app.asana.com/api/1.0/users/me/forgot_password",                     "method":"post","payload":{"email":"{EMAIL}"},                                                          "found_re":r"(email sent|reset link)","not_found_re":r"(no account|not found)"},
    {"name":"Jira",          "icon":"🔵", "url":"https://id.atlassian.com/login/resetpassword",                                "method":"post","payload":{"username":"{EMAIL}"},                                                       "found_re":r"(email sent|reset link)","not_found_re":r"(no account|not found)"},
    {"name":"Bitbucket",     "icon":"🪣", "url":"https://bitbucket.org/account/password/reset/",                               "method":"post","payload":{"email":"{EMAIL}"},                                                          "found_re":r"(email sent|reset link)","not_found_re":r"(no account|not found)"},
    {"name":"Replit",        "icon":"🔁", "url":"https://replit.com/forgot",                                                   "method":"post","payload":{"email":"{EMAIL}"},                                                          "found_re":r"(email sent|reset link)","not_found_re":r"(no account|not found)"},
    {"name":"CodePen",       "icon":"✏️", "url":"https://codepen.io/forgotpassword",                                           "method":"post","payload":{"email":"{EMAIL}"},                                                          "found_re":r"(email sent|reset link)","not_found_re":r"(no account|not found)"},
    {"name":"Stack Overflow","icon":"📚", "url":"https://stackoverflow.com/users/account-recovery",                            "method":"post","payload":{"email":"{EMAIL}"},                                                          "found_re":r"(email sent|reset link)","not_found_re":r"(no account|not found)"},
    {"name":"npm",           "icon":"📦", "url":"https://www.npmjs.com/forgot",                                                "method":"post","payload":{"email":"{EMAIL}"},                                                          "found_re":r"(email sent|reset link)","not_found_re":r"(no account|not found)"},
    {"name":"PyPI",          "icon":"🐍", "url":"https://pypi.org/account/request-password-reset/",                            "method":"post","payload":{"email_or_username":"{EMAIL}"},                                             "found_re":r"(email sent|reset link)","not_found_re":r"(no account|not found)"},
    {"name":"Amazon",        "icon":"📦", "url":"https://www.amazon.com/ap/forgotpassword",                                    "method":"post","payload":{"email":"{EMAIL}"},                                                          "found_re":r"(email sent|reset link|verify)","not_found_re":r"(no account|not found)","inconclusive":True},
    {"name":"eBay",          "icon":"🛒", "url":"https://signin.ebay.com/ws/eBayISAPI.dll?ForgotPassword",                     "method":"post","payload":{"userid":"{EMAIL}"},                                                        "found_re":r"(email sent|reset link)","not_found_re":r"(no account|not found)"},
    {"name":"Etsy",          "icon":"🧶", "url":"https://www.etsy.com/forgot_password",                                        "method":"post","payload":{"email":"{EMAIL}"},                                                          "found_re":r"(email sent|reset link)","not_found_re":r"(no account|not found)"},
    {"name":"Shopify",       "icon":"🛍️", "url":"https://accounts.shopify.com/lookup",                                        "method":"post","payload":{"email":"{EMAIL}"},                                                          "found_re":r"(email sent|reset link|account found)","not_found_re":r"(no account|not found)"},
    {"name":"PayPal",        "icon":"💳", "url":"https://www.paypal.com/authflow/forgotpassword",                              "method":"post","payload":{"email":"{EMAIL}"},                                                          "found_re":r"(email sent|reset link)","not_found_re":r"(no account|not found)","inconclusive":True},
    {"name":"Stripe",        "icon":"💰", "url":"https://dashboard.stripe.com/login/forgot-password",                          "method":"post","payload":{"email":"{EMAIL}"},                                                          "found_re":r"(email sent|reset link)","not_found_re":r"(no account|not found)"},
    {"name":"Wise",          "icon":"💸", "url":"https://wise.com/forgotPassword",                                             "method":"post","payload":{"email":"{EMAIL}"},                                                          "found_re":r"(email sent|reset link)","not_found_re":r"(no account|not found)"},
    {"name":"Coinbase",      "icon":"🪙", "url":"https://www.coinbase.com/forgot-password",                                    "method":"post","payload":{"email":"{EMAIL}"},                                                          "found_re":r"(email sent|reset link)","not_found_re":r"(no account|not found)"},
    {"name":"Airbnb",        "icon":"🏠", "url":"https://www.airbnb.com/forgot_password",                                      "method":"post","payload":{"email":"{EMAIL}"},                                                          "found_re":r"(email sent|reset link)","not_found_re":r"(no account|not found)"},
    {"name":"Booking.com",   "icon":"🏨", "url":"https://account.booking.com/accounts/password/reset",                        "method":"post","payload":{"email":"{EMAIL}"},                                                          "found_re":r"(email sent|reset link)","not_found_re":r"(no account|not found)"},
    {"name":"Dropbox",       "icon":"📦", "url":"https://www.dropbox.com/forgot",                                              "method":"post","payload":{"email":"{EMAIL}"},                                                          "found_re":r"(email sent|reset link)","not_found_re":r"(no account|not found)"},
    {"name":"Evernote",      "icon":"🐘", "url":"https://www.evernote.com/Registration.action",                                "method":"post","payload":{"email":"{EMAIL}","action":"send_pw_reset"},                               "found_re":r"(email sent|reset link)","not_found_re":r"(no account|not found)"},
    {"name":"Todoist",       "icon":"✅", "url":"https://todoist.com/Users/forgotPassword",                                    "method":"post","payload":{"email":"{EMAIL}"},                                                          "found_re":r"(email sent|reset link)","not_found_re":r"(no account|not found)"},
    {"name":"Airtable",      "icon":"🗃️", "url":"https://airtable.com/forgotPassword",                                        "method":"post","payload":{"email":"{EMAIL}"},                                                          "found_re":r"(email sent|reset link)","not_found_re":r"(no account|not found)"},
    {"name":"Monday.com",    "icon":"🗓️", "url":"https://auth.monday.com/auth/login_monday/forgot_password",                  "method":"post","payload":{"email":"{EMAIL}"},                                                          "found_re":r"(email sent|reset link)","not_found_re":r"(no account|not found)"},
    {"name":"ClickUp",       "icon":"🖱️", "url":"https://app.clickup.com/forgot",                                             "method":"post","payload":{"email":"{EMAIL}"},                                                          "found_re":r"(email sent|reset link)","not_found_re":r"(no account|not found)"},
    {"name":"Adobe",         "icon":"🎨", "url":"https://adobeid-na1.services.adobe.com/renga/public/initPasswordReset",       "method":"post","payload":{"email":"{EMAIL}"},                                                          "found_re":r"(email sent|reset link)","not_found_re":r"(no account|not found)"},
    {"name":"Canva",         "icon":"✏️", "url":"https://www.canva.com/api/account/forgot-password",                           "method":"post","payload":{"email":"{EMAIL}"},                                                          "found_re":r"(email sent|reset link)","not_found_re":r"(no account|not found)"},
    {"name":"Behance",       "icon":"🖼️", "url":"https://www.behance.net/accounts/forgotpassword",                            "method":"post","payload":{"email":"{EMAIL}"},                                                          "found_re":r"(email sent|reset link)","not_found_re":r"(no account|not found)"},
    {"name":"Dribbble",      "icon":"🏀", "url":"https://dribbble.com/password/resets",                                        "method":"post","payload":{"email":"{EMAIL}"},                                                          "found_re":r"(email sent|reset link)","not_found_re":r"(no account|not found)"},
    {"name":"Miro",          "icon":"🎯", "url":"https://miro.com/api/v1/accounts/request-password-reset/",                   "method":"post","payload":{"email":"{EMAIL}"},                                                          "found_re":r"(email sent|reset link)","not_found_re":r"(no account|not found)"},
    {"name":"Zoom",          "icon":"🎦", "url":"https://zoom.us/forgot_password",                                             "method":"post","payload":{"email":"{EMAIL}"},                                                          "found_re":r"(email sent|reset link)","not_found_re":r"(no account|not found)"},
    {"name":"Epic Games",    "icon":"🎮", "url":"https://www.epicgames.com/id/api/resetPassword",                              "method":"post","payload":{"email":"{EMAIL}"},                                                          "found_re":r"(email sent|reset link)","not_found_re":r"(no account|not found)"},
    {"name":"EA / Origin",   "icon":"🎯", "url":"https://signin.ea.com/p/web2/resetPassword",                                  "method":"post","payload":{"email":"{EMAIL}"},                                                          "found_re":r"(email sent|reset link)","not_found_re":r"(no account|not found)"},
    {"name":"Roblox",        "icon":"🟥", "url":"https://auth.roblox.com/v1/users/forgot-password",                            "method":"post","payload":{"targetUsername":"{EMAIL}"},                                                "found_re":r"(email sent|reset link)","not_found_re":r"(no account|not found)"},
    {"name":"Chess.com",     "icon":"♟️", "url":"https://www.chess.com/recover",                                              "method":"post","payload":{"email":"{EMAIL}"},                                                          "found_re":r"(email sent|reset link)","not_found_re":r"(no account|not found)"},
    {"name":"Duolingo",      "icon":"🦜", "url":"https://www.duolingo.com/api/1/requestPasswordReset",                         "method":"post","payload":{"email":"{EMAIL}"},                                                          "found_re":r"(email sent|reset link)","not_found_re":r"(no account|not found)"},
    {"name":"Coursera",      "icon":"🎓", "url":"https://www.coursera.org/api/passwordResetV2.v1",                             "method":"post","payload":{"email":"{EMAIL}"},                                                          "found_re":r"(email sent|reset link)","not_found_re":r"(no account|not found)"},
    {"name":"Udemy",         "icon":"📚", "url":"https://www.udemy.com/api-2.0/auth/forgotpassword/",                          "method":"post","payload":{"email":"{EMAIL}"},                                                          "found_re":r"(email sent|reset link)","not_found_re":r"(no account|not found)"},
    {"name":"Medium",        "icon":"✍️", "url":"https://medium.com/m/signin",                                                 "method":"post","payload":{"email":"{EMAIL}"},                                                          "found_re":r"(email sent|magic link)","not_found_re":r"(no account|not found)"},
    {"name":"Substack",      "icon":"📰", "url":"https://substack.com/api/v1/email-login",                                     "method":"post","payload":{"email":"{EMAIL}","redirect":"/"},                                          "found_re":r"(email sent|magic link)","not_found_re":r"(no account|not found)"},
    {"name":"Goodreads",     "icon":"📚", "url":"https://www.goodreads.com/user/forgot_password",                              "method":"post","payload":{"user[email]":"{EMAIL}"},                                                   "found_re":r"(email sent|reset link)","not_found_re":r"(no account|not found)"},
    {"name":"MyFitnessPal",  "icon":"🏃", "url":"https://www.myfitnesspal.com/api/auth/forgot-password",                       "method":"post","payload":{"email":"{EMAIL}"},                                                          "found_re":r"(email sent|reset link)","not_found_re":r"(no account|not found)"},
    {"name":"Strava",        "icon":"🚴", "url":"https://www.strava.com/password/new",                                         "method":"post","payload":{"email":"{EMAIL}"},                                                          "found_re":r"(email sent|reset link)","not_found_re":r"(no account|not found)"},
    {"name":"Garmin",        "icon":"🏅", "url":"https://sso.garmin.com/sso/forgotPassword",                                   "method":"post","payload":{"username":"{EMAIL}"},                                                       "found_re":r"(email sent|reset link)","not_found_re":r"(no account|not found)"},
    {"name":"OpenAI",        "icon":"🤖", "url":"https://auth0.openai.com/dbconnections/change_password",                      "method":"post","payload":{"email":"{EMAIL}","connection":"Username-Password-Authentication","client_id":"TdJIcbe16WoTHtN95nyywh5E4yOo6ItG"},"found_re":r"(We've just sent|email sent)","not_found_re":r"(no account|not found)"},
    {"name":"Hugging Face",  "icon":"🤗", "url":"https://huggingface.co/users/password-reset",                                 "method":"post","payload":{"email":"{EMAIL}"},                                                          "found_re":r"(email sent|reset link)","not_found_re":r"(no account|not found)"},
    {"name":"Salesforce",    "icon":"☁️", "url":"https://login.salesforce.com/secur/forgotpassword.jsp",                       "method":"post","payload":{"un":"{EMAIL}"},                                                             "found_re":r"(email sent|reset link)","not_found_re":r"(no account|not found)"},
    {"name":"HubSpot",       "icon":"🧡", "url":"https://app.hubspot.com/login/forgot-password",                               "method":"post","payload":{"email":"{EMAIL}"},                                                          "found_re":r"(email sent|reset link)","not_found_re":r"(no account|not found)"},
    {"name":"Mailchimp",     "icon":"🐒", "url":"https://login.mailchimp.com/forgot-password/",                                "method":"post","payload":{"email":"{EMAIL}"},                                                          "found_re":r"(email sent|reset link)","not_found_re":r"(no account|not found)"},
    {"name":"Zapier",        "icon":"⚡", "url":"https://zapier.com/accounts/forgot-password/",                                "method":"post","payload":{"email":"{EMAIL}"},                                                          "found_re":r"(email sent|reset link)","not_found_re":r"(no account|not found)"},
    {"name":"Webflow",       "icon":"🌊", "url":"https://webflow.com/api/1.0/account/reset",                                   "method":"post","payload":{"email":"{EMAIL}"},                                                          "found_re":r"(email sent|reset link)","not_found_re":r"(no account|not found)"},
    {"name":"WordPress.com", "icon":"🔷", "url":"https://wordpress.com/wp-login.php?action=lostpassword",                      "method":"post","payload":{"user_login":"{EMAIL}"},                                                    "found_re":r"(email sent|reset link)","not_found_re":r"(no account|not found)"},
    {"name":"1Password",     "icon":"🔑", "url":"https://my.1password.com/auth/forgot",                                        "method":"post","payload":{"email":"{EMAIL}"},                                                          "found_re":r"(email sent|reset link)","not_found_re":r"(no account|not found)"},
    {"name":"LastPass",      "icon":"🔐", "url":"https://lastpass.com/recover.php",                                            "method":"post","payload":{"email":"{EMAIL}"},                                                          "found_re":r"(email sent|reset link)","not_found_re":r"(no account|not found)"},
    {"name":"Bitwarden",     "icon":"🛡️", "url":"https://vault.bitwarden.com/api/accounts/password-hint",                     "method":"post","payload":{"email":"{EMAIL}"},                                                          "found_re":r"(email sent|hint sent)","not_found_re":r"(no account|not found)"},
    {"name":"Dashlane",      "icon":"🔒", "url":"https://ws1.dashlane.com/account/requestEmailTokenToResetMP",                 "method":"post","payload":{"login":"{EMAIL}"},                                                          "found_re":r'"code":"SUCCESS"',"not_found_re":r'"code":"UNKNOWN_USER"'},
    {"name":"NordVPN",       "icon":"🛡️", "url":"https://api.nordvpn.com/v1/users/auth/forgot-password",                      "method":"post","payload":{"email":"{EMAIL}"},                                                          "found_re":r"(email sent|reset link)","not_found_re":r"(no account|not found)"},
    {"name":"GoDaddy",       "icon":"🐢", "url":"https://sso.godaddy.com/v1/account/credentials/reset",                       "method":"post","payload":{"email":"{EMAIL}"},                                                          "found_re":r"(email sent|reset link)","not_found_re":r"(no account|not found)"},
    {"name":"Namecheap",     "icon":"🏷️", "url":"https://www.namecheap.com/myaccount/reset-password/",                        "method":"post","payload":{"EmailAddress":"{EMAIL}"},                                                  "found_re":r"(email sent|reset link)","not_found_re":r"(no account|not found)"},
    {"name":"Hetzner",       "icon":"🖥️", "url":"https://accounts.hetzner.com/forgot_password",                               "method":"post","payload":{"_username":"{EMAIL}"},                                                      "found_re":r"(email sent|reset link)","not_found_re":r"(no account|not found)"},
    {"name":"SoundCloud",    "icon":"🎧", "url":"https://soundcloud.com/api/v2/password/resets",                               "method":"post","payload":{"email":"{EMAIL}"},                                                          "found_re":r"(email sent|reset link)","not_found_re":r"(no account|not found)"},
    {"name":"Bandcamp",      "icon":"🎸", "url":"https://bandcamp.com/api/login/1/forgot_password",                            "method":"post","payload":{"email":"{EMAIL}"},                                                          "found_re":r"(email sent|reset link)","not_found_re":r"(no account|not found)"},
    {"name":"Vimeo",         "icon":"🎞️", "url":"https://vimeo.com/forgot_password",                                          "method":"post","payload":{"email":"{EMAIL}"},                                                          "found_re":r"(email sent|reset link)","not_found_re":r"(no account|not found)"},
]

_PROBE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/json,*/*;q=0.9",
}
_PROBE_TIMEOUT = _aiohttp.ClientTimeout(total=10)


async def _probe_site(session, site, email):
    if site.get("inconclusive"):
        return {"site": site["name"], "icon": site["icon"], "email": email, "status": "inconclusive"}
    url = site["url"]
    payload = {k: v.replace("{EMAIL}", email) for k, v in site.get("payload", {}).items()}
    try:
        if site.get("json"):
            resp = await session.post(url, json=payload, headers=_PROBE_HEADERS, timeout=_PROBE_TIMEOUT, ssl=False)
        elif site["method"] == "post":
            resp = await session.post(url, data=payload, headers=_PROBE_HEADERS, timeout=_PROBE_TIMEOUT, ssl=False)
        else:
            resp = await session.get(url, params=payload, headers=_PROBE_HEADERS, timeout=_PROBE_TIMEOUT, ssl=False)
        body = await resp.text(errors="replace")
        if _re.search(site["found_re"], body, _re.IGNORECASE):
            status = "found"
        elif _re.search(site["not_found_re"], body, _re.IGNORECASE):
            status = "not_found"
        else:
            status = "inconclusive"
    except Exception:
        status = "inconclusive"
    return {"site": site["name"], "icon": site["icon"], "email": email, "status": status}


async def _probe_all(email):
    connector = _aiohttp.TCPConnector(ssl=False, limit=20)
    async with _aiohttp.ClientSession(connector=connector) as session:
        results = await _asyncio.gather(*[_probe_site(session, s, email) for s in _SITES], return_exceptions=True)
    return [r for r in results if isinstance(r, dict)]


def _run_probe(email):
    return _asyncio.run(_probe_all(email))


_HIGH = {"passwords","credit cards","cvv","bank account numbers","pins","social security numbers"}
_MEDIUM = {"phone numbers","physical addresses","dates of birth","ip addresses","health records"}
_ICONS = {"linkedin":"💼","adobe":"🎨","canva":"✏️","dropbox":"📦","twitch":"🟣",
          "myfitnesspal":"🏃","gravatar":"👤","twitter":"🐦","facebook":"📘",
          "instagram":"📸","snapchat":"👻","spotify":"🎵","netflix":"🎬",
          "reddit":"🤖","github":"🐙","amazon":"📦","discord":"🎮","slack":"💬"}


def _sev(classes):
    low = [c.lower() for c in classes]
    if any(c in _HIGH for c in low):
        return "high"
    if any(c in _MEDIUM for c in low):
        return "medium"
    return "low"


def _icon(name):
    key = name.lower().replace(" ", "").replace(".", "").replace("-", "")
    for site_key, value in _ICONS.items():
        if site_key in key:
            return value
    return "🌐"


def _hibp_breaches(email):
    if not HIBP_API_KEY:
        return []
    try:
        response = _requests.get(
            f"https://haveibeenpwned.com/api/v3/breachedaccount/{email}?truncateResponse=false",
            headers=HIBP_HEADERS,
            timeout=10,
        )
        if response.status_code != 200:
            return []
        return [
            {
                "email": email,
                "site": breach["Name"],
                "date": breach.get("BreachDate", "")[:7],
                "severity": _sev(breach.get("DataClasses", [])),
                "tags": breach.get("DataClasses", []),
                "icon": _icon(breach["Name"]),
            }
            for breach in response.json()
        ]
    except Exception:
        return []


def _hibp_addresses(domain):
    if not HIBP_API_KEY:
        return [f"hello@{domain}"]
    try:
        response = _requests.get(
            f"https://haveibeenpwned.com/api/v3/breacheddomain/{domain}",
            headers=HIBP_HEADERS,
            timeout=15,
        )
        if response.status_code == 200:
            return [f"{address}@{domain}" for address in response.json().keys()]
        return [f"hello@{domain}"]
    except Exception:
        return [f"hello@{domain}"]


def init_footprint(app, csrf):
    @app.route("/footprint/")
    def footprint_index():
        admin_redirect = require_admin_login()
        if admin_redirect:
            return admin_redirect
        return render_page("footprint.html")

    @app.route("/footprint/scan", methods=["POST"])
    @csrf.exempt
    def footprint_scan():
        if not is_admin():
            return jsonify({"error": "unauthorized"}), 401
        target = _bleach.clean(request.json.get("target", "").strip().lower(), tags=[], strip=True)[:200]
        if not target:
            return jsonify({"error": "no target"}), 400
        is_domain = target.startswith("@") or "@" not in target
        domain = target.lstrip("@") if is_domain else target.split("@")[1]
        addresses = _hibp_addresses(domain) if is_domain else [target]
        all_breaches = []
        for email in addresses:
            all_breaches.extend(_hibp_breaches(email))
        all_probes = []
        for email in addresses:
            all_probes.extend(_run_probe(email))
        breach_counts = {}
        for breach in all_breaches:
            breach_counts[breach["email"]] = breach_counts.get(breach["email"], 0) + 1
        all_addresses = [{"email": email, "breaches": breach_counts.get(email, 0)} for email in addresses]
        db = _sqlite3.connect(FOOTPRINT_DB_PATH)
        cur = db.execute(
            "INSERT INTO scans (target, scan_type) VALUES (?, ?)",
            (target, "domain" if is_domain else "address"),
        )
        scan_id = cur.lastrowid
        for breach in all_breaches:
            db.execute(
                "INSERT INTO breaches (scan_id, email, site, breach_date, severity, data_classes) VALUES (?,?,?,?,?,?)",
                (
                    scan_id,
                    breach["email"],
                    breach["site"],
                    breach.get("date"),
                    breach.get("severity"),
                    ",".join(breach.get("tags", [])),
                ),
            )
        for probe in all_probes:
            db.execute(
                "INSERT INTO probe_results (scan_id, email, site, status) VALUES (?,?,?,?)",
                (scan_id, probe["email"], probe["site"], probe["status"]),
            )
        db.commit()
        db.close()
        return jsonify(
            {
                "breaches": all_breaches,
                "probes": all_probes,
                "addresses": all_addresses,
                "scanned_at": datetime.datetime.utcnow().strftime("%d %b %Y, %H:%M UTC"),
            }
        )
