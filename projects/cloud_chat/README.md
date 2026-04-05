# Private Chat

## Human Summary
- Private Chat is a private username/password project zone under `/privatechat/`.
- Private Chat users are specific to this project and are managed by a Smart Lock admin.
- The Private Chat login screen has a normal user login plus an admin path for managing users.

## AI Copilot

### Ownership
- [`projects/cloud_chat/cloud_chat.py`](/Users/administrator/Sites/friedutchplus/projects/cloud_chat/cloud_chat.py)
- [`templates/cloud_chat_login.html`](/Users/administrator/Sites/friedutchplus/templates/cloud_chat_login.html)
- [`templates/cloud_chat_app.html`](/Users/administrator/Sites/friedutchplus/templates/cloud_chat_app.html)
- [`templates/cloud_chat_admin.html`](/Users/administrator/Sites/friedutchplus/templates/cloud_chat_admin.html)
- [`static/css/pages/cloud_chat.css`](/Users/administrator/Sites/friedutchplus/static/css/pages/cloud_chat.css)
- [`static/js/pages/cloud_chat.js`](/Users/administrator/Sites/friedutchplus/static/js/pages/cloud_chat.js)
- [`projects/cloud_chat/cloud_chat.db`](/Users/administrator/Sites/friedutchplus/projects/cloud_chat/cloud_chat.db)

### Purpose
- Provide a dedicated `/privatechat/` zone with project-specific username/password accounts.
- Keep Private Chat account management inside the Private Chat project instead of reusing Smart Lock users directly.
- Require a Smart Lock admin session for Private Chat user administration.
- Provide private authenticated direct messages for signed-in Private Chat users.
- Keep the selected DM thread updating live while both participants are signed in.
- Present the signed-in app as a Discord-style DM client without server/channel features.

### Access model
- Regular Private Chat users sign in with:
  - username
  - password
- Private Chat admin access is separate:
  - the `Admin login` path uses the existing Smart Lock admin session
  - the Private Chat admin screen is under `/privatechat/admin`
- New and reset passwords are revealed only in the immediate admin response and are not shown again later.
- Private Chat user accounts only apply to the Private Chat project zone.

### Registration model
- This feature is not a Flask `Blueprint`.
- It is registered by calling `init_cloud_chat(app)` from [`app/__init__.py`](/Users/administrator/Sites/friedutchplus/app/__init__.py).

### Routes
- `/privatechat/`
  - login screen for Private Chat users
  - logged-in direct-message view for active Private Chat users
- `POST /privatechat/login`
  - username/password login
- `POST /privatechat/logout`
  - logout the current Private Chat user session
- `POST /privatechat/messages/send/<int:partner_id>`
  - post a new direct message to the selected Private Chat user
- `/privatechat/messages/live/<int:partner_id>`
  - return the currently selected DM thread as authenticated no-store JSON for live refresh
- `/privatechat/admin`
  - Smart Lock admin-only user management screen
- `POST /privatechat/admin/users/create`
  - create a Private Chat user
- `POST /privatechat/admin/users/password/<int:user_id>`
  - reset a Private Chat user's password
- `POST /privatechat/admin/users/toggle/<int:user_id>`
  - disable or re-enable a Private Chat user
- `POST /privatechat/admin/users/delete/<int:user_id>`
  - delete a Private Chat user

### Database table
- `cloud_chat_users`
  - username, password hash, active state, and created timestamp
- `cloud_chat_login_attempts`
  - failed-login counters and temporary lockout windows keyed by username plus client IP
- `cloud_chat_messages`
  - direct messages with sender user id, recipient user id, message text, and created timestamp
- `cloud_chat_thread_state`
  - per-user read markers for unread-count tracking in each DM thread
- `cloud_chat_presence`
  - lightweight live-presence state for the active DM client

### Security notes
- Passwords are stored as Werkzeug password hashes, not plaintext.
- Passwords are only revealed once, immediately after create/reset, and are not recoverable later from storage.
- The one-time password reveal is rendered directly in the admin response and marked `Cache-Control: no-store`.
- Private Chat requires at least 12 characters for newly created or reset passwords.
- Private Chat login attempts are throttled per username and client IP after repeated failures.
- Direct messages are posted through normal CSRF-protected form submissions inside the authenticated `/privatechat/` zone.
- Live DM polling stays same-origin, authenticated, and marked `no-store`.
- Unread counts are derived from server-side thread read markers instead of client-only state.
- Private Chat admin actions are POST-only and CSRF-protected.
- Private Chat private pages should remain `noindex`.

### Boundary rule
- Smart Lock remains the site-wide admin authority.
- Private Chat owns its own project users and should not store them inside Smart Lock tables.
