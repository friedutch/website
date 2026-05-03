# Chat

## Human Summary
- Chat is a private username/password project zone with its own login at `/chat/login`.
- Chat users are specific to this project and are managed by a Smart Lock admin.
- The Chat login screen is a stripped centered auth card with a separate admin path for managing users.

## AI Copilot

### Ownership
- [`projects/cloud_chat/chat.py`](/Users/administrator/Sites/friedutchplus/projects/cloud_chat/chat.py)
- [`templates/chat_login.html`](/Users/administrator/Sites/friedutchplus/templates/chat_login.html)
- [`templates/chat_app.html`](/Users/administrator/Sites/friedutchplus/templates/chat_app.html)
- [`templates/chat_admin.html`](/Users/administrator/Sites/friedutchplus/templates/chat_admin.html)
- [`static/css/pages/chat.css`](/Users/administrator/Sites/friedutchplus/static/css/pages/chat.css)
- [`static/js/pages/chat.js`](/Users/administrator/Sites/friedutchplus/static/js/pages/chat.js)
- local runtime database path [`projects/cloud_chat/cloud_chat.db`](/Users/administrator/Sites/friedutchplus/projects/cloud_chat/cloud_chat.db)

### Purpose
- Provide a dedicated `/chat/` zone with project-specific username/password accounts.
- Keep Chat account management inside the Chat project instead of reusing Smart Lock users directly.
- Require a Smart Lock admin session for Chat user administration.
- Provide private authenticated direct messages for signed-in Chat users.
- Keep the selected DM thread updating live while both participants are signed in.
- Present the signed-in app as a minimal direct-message client without server/channel features.
- Render the project inside the same shared minimal shell used across the whole site.
- Chat visual components inherit the site-wide design system from `static/css/base.css`; Chat page CSS should only handle auth, admin, and DM layout.
- Keep the login view visually minimal while leaving the shared horizontal project navigation available.

### Access model
- Regular Chat users sign in with:
  - username
  - password
- Chat admin access is separate:
  - the `Admin login` path uses the site-wide Smart Lock login at `/login`
  - the Chat admin screen is under `/chat/admin`
- New and reset passwords are revealed only in the immediate admin response and are not shown again later.
- Chat user accounts only apply to the Chat project zone.

### Registration model
- This feature is not a Flask `Blueprint`.
- It is registered by calling `init_chat(app)` from [`app/__init__.py`](/Users/administrator/Sites/friedutchplus/app/__init__.py).

### Routes
- `/chat/`
  - authenticated direct-message view for active Chat users
- `/chat/login`
  - username/password login screen for Chat users
- `POST /chat/login`
  - username/password login submission
- `POST /chat/logout`
  - logout the current Chat user session
- `POST /chat/messages/send/<int:partner_id>`
  - post a new direct message to the selected Chat user
- `/chat/messages/live/<int:partner_id>`
  - return the currently selected DM thread as authenticated no-store JSON for live refresh
- `/chat/admin`
  - Smart Lock admin-only user management screen
- `POST /chat/admin/users/create`
  - create a Chat user
- `POST /chat/admin/users/password/<int:user_id>`
  - reset a Chat user's password
- `POST /chat/admin/users/toggle/<int:user_id>`
  - disable or re-enable a Chat user
- `POST /chat/admin/users/delete/<int:user_id>`
  - delete a Chat user

### Database table
- Local runtime database file:
  - [`projects/cloud_chat/cloud_chat.db`](/Users/administrator/Sites/friedutchplus/projects/cloud_chat/cloud_chat.db)
  - this file is runtime state only and must stay untracked/ignored in git
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
- Chat requires at least 12 characters for newly created or reset passwords.
- Chat login attempts are throttled per username and client IP after repeated failures.
- Direct messages are posted through normal CSRF-protected form submissions inside the authenticated `/chat/` zone.
- Live DM polling stays same-origin, authenticated, and marked `no-store`.
- Unread counts are derived from server-side thread read markers instead of client-only state.
- Chat admin actions are POST-only and CSRF-protected.
- Chat private pages should remain `noindex`.

### Boundary rule
- Smart Lock remains the site-wide admin authority.
- Chat owns its own project users and should not store them inside Smart Lock tables.
