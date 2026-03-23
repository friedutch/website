# Smart Lock

## Human Summary
- Smart Lock is the admin panel for managing people and access methods for a real smart lock setup.
- The admin signs in using a magic link plus a captcha-like confirmation step.
- It also supports adding sessions on another device and changing the admin email with the same verification pattern.
- Add-session links are minted from the admin panel and can be regenerated there without changing any data directly.
- The admin panel uses top tabs for Settings, Users, and Logs.
- The Users tab shows a large create card that opens a draft user setup page, plus access cards with passcode, RFID, and fingerprint details at a glance, and a Logs tab for sessions and attempts.
- Everything for this feature lives in one module, one SQLite database, and its own templates/static files.
- Another AI should read [`/Users/administrator/Sites/friedutchplus/AGENTS.md`](/Users/administrator/Sites/friedutchplus/AGENTS.md) before changing this feature.

## AI Copilot

### Purpose
- Admin-only access-control web interface under `/smartlock/`.
- Supports physical smart-lock administration concepts:
  - users
  - passcodes
  - RFID badges
  - fingerprints
  - admin sessions

### Module ownership
- Owning backend module:
  - [`projects/smartlock/smartlock.py`](/Users/administrator/Sites/friedutchplus/projects/smartlock/smartlock.py)
- Owning database:
  - [`projects/smartlock/smartlock.db`](/Users/administrator/Sites/friedutchplus/projects/smartlock/smartlock.db)
- Owning templates:
  - [`templates/smartlock/`](/Users/administrator/Sites/friedutchplus/templates/smartlock)
- Owning CSS:
  - `static/css/pages/smartlock/*`
- Owning JS:
  - `static/js/pages/smartlock/*`

### Boundary rule
- Other app modules should not open `smartlock.db` directly.
- If another part of the app needs Smart Lock behavior or data, route it through functions or routes in [`smartlock.py`](/Users/administrator/Sites/friedutchplus/projects/smartlock/smartlock.py).

### Registration model
- This feature is not a Flask `Blueprint`.
- It is registered by calling `init_smartlock(app)` from [`app/__init__.py`](/Users/administrator/Sites/friedutchplus/app/__init__.py).
- Route definitions live directly inside `init_smartlock(app)`.

### Authentication model
- Admin login flow:
  - request magic link
  - open magic link
  - solve captcha challenge
  - receive admin session
  - when the link is completed in the same browser profile as the login screen, the verification page should close itself and the original login screen should refresh into the admin panel
- Cross-device session flow:
  - create add-session link
  - open on other device
  - solve captcha challenge
  - create admin session on that device
- Admin email-change flow:
  - submit new email
  - receive verification link
  - solve captcha challenge
  - commit new admin email

### Important implementation details
- Email sending uses Resend.
- Smart Lock reads `RESEND_API_KEY` and `MAIL_FROM` dynamically at runtime.
- Email failures should not 500 the page; they should render a normal page error.
- Admin session state is stored in the `active_sessions` table plus Flask session cookies.
- Smart Lock requires session cookies even before login:
  - a cookie probe runs on Smart Lock requests
  - browsers with cookies disabled should only see the cookies-required page, the Home link, and the debug footer
  - CSRF failures on Smart Lock routes should also fall back to that cookies-required page
- Session expiry is fixed-duration from login.
- Login cooldowns are stored in the `settings` table with browser-session-scoped keys.
- Login cooldowns are intentionally not global; one browser session should not block another person's login request.
- The browser-session actor id lives in the Flask session cookie as `cooldown_actor_id`.
- Successful same-browser magic-link verification should signal the original login page to continue into the admin panel instead of leaving the verified email tab on the panel.
- The page UI language now says `captcha`, but one DB table still uses the legacy name `match_numbers`.
- The admin panel is tabbed client-side from the top action bar; keep tab buttons and panel section ids/data attributes aligned.
- Theme toggle and session logout live inside the Settings tab, not the top bar.
- The current session's remaining time now lives in a centered Settings card instead of the top bar.
- The selected admin panel tab persists across reloads using browser storage, with a cookie fallback when local storage is unavailable.
- The admin panel's Users section is card-based and should keep the edit link pointing to the existing user detail page.
- The Users tab includes a client-side search bar for filtering cards by name, passcode, RFID id, or fingerprint id.
- The Users tab places search first, then a dedicated add-user card that links to `/smartlock/users/new` and matches the visible user-card height.
- New-user creation happens on the user detail screen in a draft mode; the name is editable only during creation, and the user row is only inserted when the create form is submitted.
- The admin panel's Logs area includes a client-side search bar plus a small add-session card above the combined log feed, and when used it reveals the invite row directly in the admin panel.
- In Settings, email change starts as a single wide `Change email` button and expands inline into a single-row editable form with the email field followed by cancel/save actions.
- Log search also matches stored device aliases, so terms like phone, tablet, computer, pc, and browser can find matching entries.
- The combined log feed merges active sessions with their corresponding successful login events, while still showing denied attempts as separate entries.
- Active log cards for other devices show logout followed by an `Active` badge.
- The current device log card should not show a logout control; it should show `THIS DEVICE` immediately before the `Active` badge.
- When an active session reaches its limit in the current page view, the card should flip to `Allowed` without removing the `THIS DEVICE` badge.
- The add-session route mints the invite and returns to the admin panel, where the inline invite row shows copy first, a fixed join-link field, the captcha code, and a regenerate action.
- Opening a join link on a device that already has an active admin session must close or leave the invite page and return to the admin panel without consuming the token.

### Routes
- Main:
  - `/smartlock/`
  - `/smartlock/login`
  - `/smartlock/poll-status`
  - `/smartlock/verify`
  - `/smartlock/verify-captcha`
- Cross-device session:
  - `/smartlock/join/<token>`
  - `/smartlock/join-captcha`
- Email change:
  - `/smartlock/change-email`
  - `/smartlock/change-email/resend`
  - `/smartlock/change-email/cancel`
  - `/smartlock/change-email/pending`
  - `/smartlock/verify-email-change`
  - `/smartlock/verify-email-captcha`
- Admin/session management:
  - `/smartlock/admin`
  - `/smartlock/session/logout/<session_token>`
  - `/smartlock/session/logout-all`
  - `/smartlock/logout`
- User management:
  - `/smartlock/users/new`
  - `/smartlock/users/add`
  - `/smartlock/users/create`
  - `/smartlock/users/delete/<int:user_id>`
  - `/smartlock/user/<int:user_id>`
  - `/smartlock/user/<int:user_id>/toggle/<method>`
  - `/smartlock/user/<int:user_id>/set/<method>`

### Database tables
- `users`
  - smart-lock users and their passcode/RFID/fingerprint configuration
- `used_tokens`
  - consumed magic links
- `match_numbers`
  - pending captcha tokens
  - legacy table name; do not rename casually without a migration plan
- `login_logs`
  - admin and session-related attempts
- `settings`
  - admin email, pending admin email, cooldown timestamps
- `active_sessions`
  - active admin sessions
- `join_tokens`
  - cross-device login tokens
- `number_attempts`
  - currently present in schema; treat as reserved/internal

### External dependencies / services
- Resend email API:
  - requires `RESEND_API_KEY`
  - requires `MAIL_FROM`
  - initial admin email defaults from `MAIL_TO`
  - after initialization, the active admin email lives in the Smart Lock `settings` table and can diverge from `.env`
- Flask-WTF for CSRF
- Bleach for sanitization

### Security notes
- Magic links expire after 5 minutes.
- Captcha challenge is single-attempt and destructive on failure.
- Join links should only be consumed when a new device actually completes the join flow.
- Brute-force lockout exists for repeated attempts.
- Cookies are `Secure`, `HttpOnly`, `SameSite=Lax`.
- Smart Lock should be treated as sensitive/admin-only functionality.

### Known pitfalls for future changes
- Do not rename `match_numbers` at the DB layer without an explicit migration.
- Do not reintroduce inline HTML/CSS/JS into Python.
- If changing login flow names, update:
  - route names
  - template form actions
  - session keys
  - log labels
  - README docs
- `verify-captcha` must remain POST-only to avoid follow-up GET crashes.
