# Cloud Chat

## Human Summary
- Cloud Chat is a private username/password project zone under `/cloudchat/`.
- Cloud Chat users are specific to this project and are managed by a Smart Lock admin.
- The Cloud Chat login screen has a normal user login plus an admin path for managing users.

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
- Provide a dedicated `/cloudchat/` zone with project-specific username/password accounts.
- Keep Cloud Chat account management inside the Cloud Chat project instead of reusing Smart Lock users directly.
- Require a Smart Lock admin session for Cloud Chat user administration.

### Access model
- Regular Cloud Chat users sign in with:
  - username
  - password
- Cloud Chat admin access is separate:
  - the `Admin login` path uses the existing Smart Lock admin session
  - the Cloud Chat admin screen is under `/cloudchat/admin`
- Cloud Chat user accounts only apply to the Cloud Chat project zone.

### Registration model
- This feature is not a Flask `Blueprint`.
- It is registered by calling `init_cloud_chat(app)` from [`app/__init__.py`](/Users/administrator/Sites/friedutchplus/app/__init__.py).

### Routes
- `/cloudchat/`
  - login screen for Cloud Chat users
  - logged-in app page for active Cloud Chat users
- `POST /cloudchat/login`
  - username/password login
- `POST /cloudchat/logout`
  - logout the current Cloud Chat user session
- `/cloudchat/admin`
  - Smart Lock admin-only user management screen
- `POST /cloudchat/admin/users/create`
  - create a Cloud Chat user
- `POST /cloudchat/admin/users/password/<int:user_id>`
  - reset a Cloud Chat user's password
- `POST /cloudchat/admin/users/toggle/<int:user_id>`
  - disable or re-enable a Cloud Chat user
- `POST /cloudchat/admin/users/delete/<int:user_id>`
  - delete a Cloud Chat user

### Database table
- `cloud_chat_users`
  - username, password hash, active state, and created timestamp

### Security notes
- Passwords are stored as Werkzeug password hashes, not plaintext.
- Cloud Chat admin actions are POST-only and CSRF-protected.
- Cloud Chat private pages should remain `noindex`.

### Boundary rule
- Smart Lock remains the site-wide admin authority.
- Cloud Chat owns its own project users and should not store them inside Smart Lock tables.
