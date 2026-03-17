# Smart Lock

Access control panel for a physical smart lock system. Admin-only web interface hosted at friedutch.plus/smartlock/.

## What it does
- Manages users and their access methods
- Supports three authentication methods per user: Passcode, RFID badge, Fingerprint
- Admin authenticates via magic link + number matching (MFA)
- Cross-device sessions via "Add session" QR/link flow

## Stack
- **Flask Blueprint** — modular routing under /smartlock/
- **SQLite** (smartlock.db) — stores users, sessions, login logs, tokens
- **Resend** — sends magic link emails from magiclink@email.friedutch.plus
- **Flask-WTF** — CSRF protection
- **Bleach** — input sanitization

## Security
- Magic link login (5 min expiry, single use)
- Number matching MFA (1 attempt, token destroyed on failure)
- Brute force lockout (5 attempts → 5 min ban)
- Session expiry (1 hour fixed from login)
- CSRF tokens on all forms
- Secure, HttpOnly, Lax cookies
- Cloudflare WAF + Bot Fight Mode
- Security headers via Caddy (X-Frame-Options, HSTS, etc.)

## Routes
| Route | Description |
|-------|-------------|
| /smartlock/ | Hub, redirects to login or admin |
| /smartlock/login | Admin magic link login |
| /smartlock/admin | Admin control room |
| /smartlock/user/<id> | User detail & method config |
| /smartlock/add-session | Cross-device login |
| /smartlock/verify | Magic link verification |
| /smartlock/verify-number | Number match verification |
| /deploy | GitHub webhook (auto-deploy) |

## Database tables
- `users` — name, passcode, RFID/fingerprint IDs and enabled flags
- `active_sessions` — live sessions with IP and device icon
- `login_logs` — all login attempts (success/fail, IP, device, timestamp)
- `match_numbers` — pending number match tokens
- `join_tokens` — cross-device session tokens
- `used_tokens` — consumed magic links (prevent replay)
- `settings` — admin email, cooldowns, pending changes
