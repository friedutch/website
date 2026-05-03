# Smart Lock

## Human Summary
- Smart Lock is the admin panel for managing people and access methods for a real smart lock setup.
- The admin signs in using a magic link plus a captcha-like confirmation step.
- The site-wide admin login at `/login` now uses a centered single-card auth screen inside the shared shell and keeps the shell utility area minimal.
- It also supports adding sessions on another device and changing the admin email with the same verification pattern.
- Add-session links are minted from the admin panel and can be regenerated there without changing any data directly.
- The Smart Lock pages now render inside the shared minimal site shell, while the admin panel keeps its own Users, Logs, and Arduino tabs.
- The admin panel uses vertical project tabs for Users, Logs, and Arduino on desktop.
- Smart Lock visual components inherit the site-wide design system from `static/css/base.css`; Smart Lock page CSS should only handle feature layout.
- The Users tab shows a large create card that opens a draft user setup page, plus access cards with passcode, RFID, and fingerprint details at a glance, and a Logs tab for sessions and attempts.
- The user detail page now includes an RFID `Scan` button that listens for the next badge read from the Arduino bridge, fills the RFID field automatically, and shows live validation feedback inline.
- The feature now uses a lightweight bootstrap plus focused Smart Lock modules for auth, admin, hardware, DB/state, and page composition.
- Another AI should read [`/Users/administrator/Sites/friedutchplus/AGENTS.md`](/Users/administrator/Sites/friedutchplus/AGENTS.md) before changing this feature.

## AI Copilot

### Purpose
- Admin-only access-control project under `/smartlock/`, with the site-wide admin login screen now served from `/login`.
- Supports physical smart-lock administration concepts:
  - users
  - passcodes
  - RFID badges
  - fingerprints
  - admin sessions
- Includes a hardware integration path for a real Arduino Uno controller through a dedicated Smart Lock API plus a macOS serial bridge.

### Module ownership
- Owning backend package:
  - [`projects/smartlock/`](/Users/administrator/Sites/friedutchplus/projects/smartlock)
- Lightweight entrypoint:
  - [`projects/smartlock/smartlock.py`](/Users/administrator/Sites/friedutchplus/projects/smartlock/smartlock.py)
- Route modules:
  - [`projects/smartlock/routes_auth.py`](/Users/administrator/Sites/friedutchplus/projects/smartlock/routes_auth.py)
  - [`projects/smartlock/routes_admin.py`](/Users/administrator/Sites/friedutchplus/projects/smartlock/routes_admin.py)
  - [`projects/smartlock/routes_hardware.py`](/Users/administrator/Sites/friedutchplus/projects/smartlock/routes_hardware.py)
- Internal support modules:
  - [`projects/smartlock/config.py`](/Users/administrator/Sites/friedutchplus/projects/smartlock/config.py)
  - [`projects/smartlock/db.py`](/Users/administrator/Sites/friedutchplus/projects/smartlock/db.py)
  - [`projects/smartlock/activity.py`](/Users/administrator/Sites/friedutchplus/projects/smartlock/activity.py)
  - [`projects/smartlock/helpers.py`](/Users/administrator/Sites/friedutchplus/projects/smartlock/helpers.py)
  - [`projects/smartlock/session_state.py`](/Users/administrator/Sites/friedutchplus/projects/smartlock/session_state.py)
  - [`projects/smartlock/mail.py`](/Users/administrator/Sites/friedutchplus/projects/smartlock/mail.py)
  - [`projects/smartlock/hardware.py`](/Users/administrator/Sites/friedutchplus/projects/smartlock/hardware.py)
  - [`projects/smartlock/pages.py`](/Users/administrator/Sites/friedutchplus/projects/smartlock/pages.py)
- Owning database:
  - [`projects/smartlock/smartlock.db`](/Users/administrator/Sites/friedutchplus/projects/smartlock/smartlock.db)
- Hardware bridge assets:
  - [`projects/smartlock/hardware/smartlock_serial_bridge.py`](/Users/administrator/Sites/friedutchplus/projects/smartlock/hardware/smartlock_serial_bridge.py)
  - [`projects/smartlock/hardware/arduino_uno_smartlock/arduino_uno_smartlock.ino`](/Users/administrator/Sites/friedutchplus/projects/smartlock/hardware/arduino_uno_smartlock/arduino_uno_smartlock.ino)
  - [`projects/smartlock/hardware/upload_arduino_uno.sh`](/Users/administrator/Sites/friedutchplus/projects/smartlock/hardware/upload_arduino_uno.sh)
- Owning templates:
  - [`templates/smartlock/`](/Users/administrator/Sites/friedutchplus/templates/smartlock)
- Owning CSS:
  - `static/css/pages/smartlock/*`
- Owning JS:
  - `static/js/pages/smartlock/*`

### Boundary rule
- Other app modules should not open `smartlock.db` directly.
- If another part of the app needs Smart Lock behavior or data, route it through the exported Smart Lock package helpers or Smart Lock routes instead of reaching into internal modules casually.
- The Arduino bridge follows that same rule:
  - the macOS bridge calls `/smartlock/api/hardware/check`
  - only the Smart Lock module queries the `users` table

### Registration model
- This feature is not a Flask `Blueprint`.
- It is registered by calling `init_smartlock(app)` from [`app/__init__.py`](/Users/administrator/Sites/friedutchplus/app/__init__.py).
- [`smartlock.py`](/Users/administrator/Sites/friedutchplus/projects/smartlock/smartlock.py) now stays thin and wires route modules plus request hooks together.
- Shared site-wide helpers live outside the feature in:
  - [`app/forms.py`](/Users/administrator/Sites/friedutchplus/app/forms.py)
  - [`app/site_admin.py`](/Users/administrator/Sites/friedutchplus/app/site_admin.py)

### Authentication model
- Admin login flow:
  - request magic link
  - open magic link
  - solve captcha challenge
  - receive admin session
  - when the link is completed in the same browser profile as the login screen, the verification page should close itself and the original login screen should refresh into the admin panel
- Cross-device session flow:
  - submit add-session
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
  - browsers with cookies disabled should only see the cookies-required page and the Home link
  - CSRF failures on Smart Lock routes should also fall back to that cookies-required page
- The admin login page is intentionally separate from the Smart Lock project index:
  - `/login` is the canonical site-wide admin entrypoint
  - `/smartlock/login` remains only as a compatibility alias
- Session expiry is fixed-duration from login.
- Login cooldowns are stored in the `settings` table with browser-session-scoped keys.
- Login cooldowns are intentionally not global; one browser session should not block another person's login request.
- The browser-session actor id lives in the Flask session cookie as `cooldown_actor_id`.
- Successful same-browser magic-link verification should signal the original login page to continue into the admin panel instead of leaving the verified email tab on the panel.
- The page UI language now says `captcha`, but one DB table still uses the legacy name `match_numbers`.
- The admin panel is tabbed client-side with vertical desktop tabs; keep tab buttons and panel section ids/data attributes aligned.
- Smart Lock now uses the shared minimal site shell across its pages, with project switching in the Projects dropdown, admin login separated at `/login`, and the universal footer shared site-wide.
- The current session's remaining time lives in a persistent header island inside the shared app shell header.
- The selected admin panel tab persists across reloads using browser storage, with a cookie fallback when local storage is unavailable. The same storage layer also carries the shared theme preference.
- The admin panel's Users section is card-based and should keep the edit link pointing to the existing user detail page.
- The user detail page's RFID save flow should stay badge-first and low-friction:
  - `Scan` listens for the next `CHECK|rfid|...` event
  - the scanned badge ID is copied into the form field automatically
  - saving an RFID value for an existing user enables RFID for that user automatically
  - later RFID allow/deny results can be surfaced inline from the same hardware event feed
- The Users tab includes a client-side search bar for filtering cards by name, passcode, RFID id, or fingerprint id.
- The Users tab places search first, then a dedicated add-user card that links to `/smartlock/users/new` and matches the visible user-card height.
- New-user creation happens on the user detail screen in a draft mode; the name is editable only during creation, and the user row is only inserted when the create form is submitted.
- The admin panel's Logs area includes a client-side search bar plus a small add-session card above the combined log feed, and when used it reveals the invite row directly in the admin panel.
- The Arduino tab shows a live console of hardware bridge events so keypad, RFID, fingerprint, and API checks can be debugged without a physical lock actuator.
- The email-change controls now live in their own Admin card above the tabbed panels; the idle state starts as a single wide `Change email` button and expands inline into a single-row editable form with the email field followed by cancel/save actions.
- Log search also matches stored device aliases, so terms like phone, tablet, computer, pc, and browser can find matching entries.
- The combined log feed merges active sessions with their corresponding successful login events, while still showing denied attempts as separate entries.
- Active log cards for other devices show logout followed by an `Active` badge.
- The current device log card should not show a logout control; it should show `THIS DEVICE` immediately before the `Active` badge.
- When an active session reaches its limit in the current page view, the card should flip to `Allowed` without removing the `THIS DEVICE` badge.
- The add-session route mints the invite and returns to the admin panel, where the inline invite row shows copy first, a fixed join-link field, the captcha code, and a regenerate action.
- Opening a join link on a device that already has an active admin session must close or leave the invite page and return to the admin panel without consuming the token.
- The hardware integration is split into two layers:
  - the Arduino sketch reads keypad, RFID, and fingerprint hardware and sends line-based checks over USB serial
  - the macOS bridge forwards those checks to Smart Lock and returns allow/deny responses back to the Arduino
- The merged Arduino sketch is currently tuned for a ZFM-708SA50H-style UART fingerprint sensor and tries `57600` first, then `9600`, during startup.
- The current merged pin plan keeps the keypad on `D3-D9`, uses `D2` for the relay, reads a one-wire RFID signal on `A0`, and uses `A1/A2` for the fingerprint sensor UART. `A3` is reserved only as the unused SoftwareSerial TX pin for the RFID reader.

### Routes
- Main:
  - `/smartlock/`
  - `/login`
  - `/login/poll-status`
  - `/smartlock/verify`
  - `POST /smartlock/verify-captcha`
  - legacy aliases still exist at `/smartlock/login` and `/smartlock/poll-status`
- Cross-device session:
  - `POST /smartlock/add-session`
  - `/smartlock/join/<token>`
  - `POST /smartlock/join-captcha`
- Email change:
  - `POST /smartlock/change-email`
  - `POST /smartlock/change-email/resend`
  - `POST /smartlock/change-email/cancel`
  - `/smartlock/change-email/pending`
  - `/smartlock/verify-email-change`
  - `POST /smartlock/verify-email-captcha`
- Admin/session management:
  - `/smartlock/admin`
  - `POST /smartlock/session/logout/<session_token>`
  - `POST /smartlock/session/logout-all`
  - `POST /smartlock/logout`
- Hardware integration:
  - `POST /smartlock/api/hardware/check`
  - `GET /smartlock/api/hardware/events`
- User management:
  - `/smartlock/users/new`
  - `POST /smartlock/users/add`
  - `POST /smartlock/users/create`
  - `POST /smartlock/users/delete/<int:user_id>`
  - `/smartlock/user/<int:user_id>`
  - `POST /smartlock/user/<int:user_id>/toggle/<method>`
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

### Hardware API behavior
- `POST /smartlock/api/hardware/check` accepts JSON with:
  - `method`: `passcode`, `rfid`, or `fingerprint`
  - `value`: credential value coming from the Arduino bridge
- The route requires the `X-SmartLock-Hardware-Key` header to match `SMARTLOCK_HARDWARE_API_KEY`.
- Successful checks return the matching Smart Lock user and `unlock_seconds`.
- Failed checks return `allowed: false` and still write a hardware attempt into `login_logs`.
- `GET /smartlock/api/hardware/events` is admin-session-only and returns recent bridge events for the Arduino console tab.
- Passcodes are checked directly against `users.passcode`.
- RFID checks only allow rows where `rfid_enabled = 1` and `rfid_id` matches.
- Fingerprint checks only allow rows where `fingerprint_enabled = 1` and `fingerprint_id` matches.
- The bridge appends those events to `/tmp/friedutchplus_smartlock_hardware_events.jsonl`.
- The serial bridge can auto-detect the current Arduino Uno port when `--port` is omitted, and it retries detection after serial disconnects so replugging the Uno does not require hardcoding a new `/dev/cu.usbmodemXXXX` path.

### External dependencies / services
- Resend email API:
  - requires `RESEND_API_KEY`
  - requires `MAIL_FROM`
  - initial admin email defaults from `MAIL_TO`
  - after initialization, the active admin email lives in the Smart Lock `settings` table and can diverge from `.env`
- Flask-WTF for CSRF
- Bleach for sanitization
- `pyserial` for the optional macOS USB bridge script
- Arduino IDE or a compatible `arduino-cli` install for compiling/uploading the Uno sketch

### Arduino upload notes
- The Uno sketch compiles for `arduino:avr:uno`.
- The repo now includes [`upload_arduino_uno.sh`](/Users/administrator/Sites/friedutchplus/projects/smartlock/hardware/upload_arduino_uno.sh) to compile with the installed Arduino IDE tooling and upload using a temp build directory.
- The current Smart Lock Uno wiring map is:
  - `D2`: lock relay
  - `D3-D9`: keypad
  - `A0`: RFID reader receive line
  - `A1/A2`: fingerprint sensor SoftwareSerial
  - `A3`: reserved as the unused RFID SoftwareSerial transmit pin
- The sketch does not use the Uno hardware UART pins `D0/D1`, so if upload only succeeds after unplugging everything, the attached Smart Lock hardware is likely loading reset, power, or one of the active Smart Lock pins during bootloader entry.
- The practical recovery workflow is:
  - stop the Smart Lock serial bridge and any Serial Monitor
  - unplug Smart Lock peripherals
  - upload the sketch
  - reconnect the relay, keypad, RFID reader, and fingerprint sensor one subsystem at a time until the interfering connection is identified
- If upload fails with `not in sync` or `programmer is not responding`, treat that as a bootloader/reset/serial-path issue first:
  - stop the Smart Lock serial bridge and any Serial Monitor
  - disconnect anything on pins `D0` and `D1`
  - if that is not enough, disconnect the Smart Lock peripherals from `D2-D9` and `A0-A3`
  - retry with a manual reset just before upload starts
  - if the target is not actually using the Uno bootloader, override `ARDUINO_FQBN`

### Security notes
- Magic links expire after 5 minutes.
- Captcha challenge is single-attempt and destructive on failure.
- Join links should only be consumed when a new device actually completes the join flow.
- Brute-force lockout exists for repeated attempts.
- Cookies are `Secure`, `HttpOnly`, `SameSite=Lax`.
- Admin login clears and rebuilds the Flask session before elevating it.
- Admin-side destructive actions and toggles are POST-only and CSRF-protected.
- Add-session and email-change resend/cancel actions are also POST-only and CSRF-protected.
- Tokenized and user-id Smart Lock pages are marked `X-Robots-Tag: noindex, nofollow`.
- Smart Lock should be treated as sensitive/admin-only functionality.
- The hardware API is machine-facing and must stay protected by a strong `SMARTLOCK_HARDWARE_API_KEY`.

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
- If changing hardware credential behavior, keep the Arduino sketch, the serial bridge, the Smart Lock route, and this README in sync.
