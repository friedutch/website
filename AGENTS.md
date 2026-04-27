# Friedutch Plus Agent Guide

## Human Summary
- Read this first, then read the feature README for the area you are changing.
- The app is a self-hosted Flask site with three internal tools: Smart Lock, Cloud Storage, and Chat.

## AI Copilot

### Read order
1. Read this file.
2. Read [`README.md`](/Users/administrator/Sites/friedutchplus/README.md).
3. If touching Smart Lock, read [`projects/smartlock/README.md`](/Users/administrator/Sites/friedutchplus/projects/smartlock/README.md).
4. If touching Cloud Storage, read [`projects/cloud_storage/README.md`](/Users/administrator/Sites/friedutchplus/projects/cloud_storage/README.md).
5. If touching Chat, read [`projects/cloud_chat/README.md`](/Users/administrator/Sites/friedutchplus/projects/cloud_chat/README.md).

### Primary goals
- Keep the website working.
- Keep features separated by ownership.
- Prefer small, reversible edits.
- Preserve runtime data.
- Keep docs synchronized with code.

### Hard safety rules
- Do not delete, recreate, replace, or directly edit the live SQLite databases unless explicitly asked:
  - [`projects/smartlock/smartlock.db`](/Users/administrator/Sites/friedutchplus/projects/smartlock/smartlock.db)
- Never stage or commit runtime databases or other live state files:
  - `*.db`
  - `*.sqlite`
  - `*.sqlite3`
  - local caches, logs, upload payloads, temp files, or machine-specific runtime artifacts
- Do not move HTML/CSS/JS back into Python strings.
- Do not rename DB tables casually.
- Treat Smart Lock as sensitive admin functionality.

### Repo map
- [`run.py`](/Users/administrator/Sites/friedutchplus/run.py)
  - main app entrypoint
- [`app/__init__.py`](/Users/administrator/Sites/friedutchplus/app/__init__.py)
  - app factory and top-level routes
- [`app/rendering.py`](/Users/administrator/Sites/friedutchplus/app/rendering.py)
  - shared render helper for template rendering, asset-version injection, and project-rail state
- [`app/forms.py`](/Users/administrator/Sites/friedutchplus/app/forms.py)
  - site-wide CSRF template helper
- [`app/site_admin.py`](/Users/administrator/Sites/friedutchplus/app/site_admin.py)
  - site-wide admin-session helpers
- [`templates/_app_frame.html`](/Users/administrator/Sites/friedutchplus/templates/_app_frame.html)
  - shared Discord-like site shell used by all rendered pages
- [`static/css/site_shell.css`](/Users/administrator/Sites/friedutchplus/static/css/site_shell.css)
  - shared cross-project shell styling
- [`projects/smartlock/smartlock.py`](/Users/administrator/Sites/friedutchplus/projects/smartlock/smartlock.py)
  - lightweight Smart Lock bootstrap
- [`projects/cloud_storage/cloud_storage.py`](/Users/administrator/Sites/friedutchplus/projects/cloud_storage/cloud_storage.py)
  - Cloud Storage owner
- [`projects/cloud_chat/chat.py`](/Users/administrator/Sites/friedutchplus/projects/cloud_chat/chat.py)
  - Chat owner

### Feature ownership
- Smart Lock owns:
  - [`projects/smartlock/`](/Users/administrator/Sites/friedutchplus/projects/smartlock)
  - [`templates/smartlock/`](/Users/administrator/Sites/friedutchplus/templates/smartlock)
  - `static/css/pages/smartlock/*`
  - `static/js/pages/smartlock/*`
- Cloud Storage owns:
  - [`projects/cloud_storage/cloud_storage.py`](/Users/administrator/Sites/friedutchplus/projects/cloud_storage/cloud_storage.py)
  - [`templates/cloud_storage.html`](/Users/administrator/Sites/friedutchplus/templates/cloud_storage.html)
  - [`static/css/pages/cloud_storage.css`](/Users/administrator/Sites/friedutchplus/static/css/pages/cloud_storage.css)
  - [`static/js/pages/cloud_storage.js`](/Users/administrator/Sites/friedutchplus/static/js/pages/cloud_storage.js)
- Chat owns:
  - [`projects/cloud_chat/`](/Users/administrator/Sites/friedutchplus/projects/cloud_chat)
  - [`templates/chat_login.html`](/Users/administrator/Sites/friedutchplus/templates/chat_login.html)
  - [`templates/chat_app.html`](/Users/administrator/Sites/friedutchplus/templates/chat_app.html)
  - [`templates/chat_admin.html`](/Users/administrator/Sites/friedutchplus/templates/chat_admin.html)
  - [`static/css/pages/chat.css`](/Users/administrator/Sites/friedutchplus/static/css/pages/chat.css)
  - [`static/js/pages/chat.js`](/Users/administrator/Sites/friedutchplus/static/js/pages/chat.js)

### Separation rules
- Python belongs in `.py`
- HTML belongs in `templates/`
- CSS belongs in `static/css/`
- JS belongs in `static/js/`

### Runtime model
- App listens on `127.0.0.1:5001`.
- The whole site uses one shared Discord-like shell:
  - left rail for project switching
  - shared main content frame
  - separate admin login entry at `/login`

### Frontend behavior notes
- Shared theme and confirm behavior lives in:
  - [`static/js/early-theme.js`](/Users/administrator/Sites/friedutchplus/static/js/early-theme.js)
  - [`static/js/theme.js`](/Users/administrator/Sites/friedutchplus/static/js/theme.js)
- Browser storage uses a resilient wrapper with cookie fallback when local storage is unavailable.
- Smart Lock admin tab memory uses that same browser storage layer.
- Avoid `min-height: 100%` on cards inside auto-sized CSS grid layouts unless the parent track has an explicit fixed height.

### Commands another AI will likely need
- Validate Python syntax:
  - `python3 -m py_compile run.py app/*.py projects/smartlock/*.py projects/cloud_storage/cloud_storage.py projects/cloud_chat/chat.py`
- Inspect changed files:
  - `git status --short`
  - `git diff -- <paths>`
- Check that no database files are tracked before committing:
  - `git ls-files '*.db' '*.sqlite' '*.sqlite3'`
- Search code:
  - `rg "pattern"`

### Documentation rule
- After any code change, review every `README.md` in the repo and update the relevant ones if behavior, ownership, routes, or workflow changed.

### Environment template
- Use [`.env.example`](/Users/administrator/Sites/friedutchplus/.env.example) as the non-secret reference for expected environment variables.
