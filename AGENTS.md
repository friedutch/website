# Friedutch Plus Agent Guide

## Human Summary
- This file tells an AI coding agent how to safely operate inside the Friedutch Plus repo.
- Read this first, then read the feature README for the area you are changing.
- The app is a self-hosted personal Flask site with three internal tools: Smart Lock, Cloud Storage, and Private Chat.
- The app also contains a public Minecraft landing page module.

## AI Copilot

### Read order
1. Read this file.
2. Read [`README.md`](/Users/administrator/Sites/friedutchplus/README.md).
3. If touching Smart Lock, read [`projects/smartlock/README.md`](/Users/administrator/Sites/friedutchplus/projects/smartlock/README.md).
4. If touching Cloud Storage, read [`projects/cloud_storage/README.md`](/Users/administrator/Sites/friedutchplus/projects/cloud_storage/README.md).
5. If touching Private Chat, read [`projects/cloud_chat/README.md`](/Users/administrator/Sites/friedutchplus/projects/cloud_chat/README.md).
6. If touching Minecraft, read [`projects/minecraft/README.md`](/Users/administrator/Sites/friedutchplus/projects/minecraft/README.md).

### Primary goals
- Keep the website working.
- Keep features separated by ownership.
- Prefer small, reversible edits.
- Preserve runtime data.
- Keep docs synchronized with code.

### Hard safety rules
- Do not delete, recreate, replace, or directly edit the live SQLite databases unless explicitly asked:
  - [`projects/smartlock/smartlock.db`](/Users/administrator/Sites/friedutchplus/projects/smartlock/smartlock.db)
- Do not move HTML/CSS/JS back into Python strings.
- Do not rename DB tables casually.
- Do not assume LaunchAgent changes are normal code changes.
- Do not edit, reload, kickstart, bootstrap, bootout, or otherwise touch any `friedutch.plus` LaunchAgent or its plist unless explicitly asked.
- For repo work, stop at repo edits, commit, and push to GitHub unless the human explicitly asks for operational intervention.
- Do not commit any live Minecraft server instance files, world data, Paper jars, plugin jars, or copied server roots into this repo.
- Treat Smart Lock as sensitive admin functionality.

### Repo map
- [`run.py`](/Users/administrator/Sites/friedutchplus/run.py)
  - main app entrypoint
- [`app/__init__.py`](/Users/administrator/Sites/friedutchplus/app/__init__.py)
  - app factory, homepage, deploy webhook, project registration
- [`app/rendering.py`](/Users/administrator/Sites/friedutchplus/app/rendering.py)
  - shared render helper for template rendering and asset-version injection
- [`app/forms.py`](/Users/administrator/Sites/friedutchplus/app/forms.py)
  - site-wide CSRF template helper
- [`app/site_admin.py`](/Users/administrator/Sites/friedutchplus/app/site_admin.py)
  - site-wide admin-session helpers
- [`projects/smartlock/smartlock.py`](/Users/administrator/Sites/friedutchplus/projects/smartlock/smartlock.py)
  - lightweight Smart Lock bootstrap
- [`projects/cloud_storage/cloud_storage.py`](/Users/administrator/Sites/friedutchplus/projects/cloud_storage/cloud_storage.py)
  - Cloud Storage owner
- [`projects/cloud_chat/cloud_chat.py`](/Users/administrator/Sites/friedutchplus/projects/cloud_chat/cloud_chat.py)
  - Private Chat owner
- [`projects/minecraft/minecraft.py`](/Users/administrator/Sites/friedutchplus/projects/minecraft/minecraft.py)
  - Minecraft landing page owner
- [`templates/`](/Users/administrator/Sites/friedutchplus/templates)
  - Jinja templates
- [`static/`](/Users/administrator/Sites/friedutchplus/static)
  - CSS and JS assets

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
- Private Chat owns:
  - [`projects/cloud_chat/`](/Users/administrator/Sites/friedutchplus/projects/cloud_chat)
  - [`templates/cloud_chat_login.html`](/Users/administrator/Sites/friedutchplus/templates/cloud_chat_login.html)
  - [`templates/cloud_chat_app.html`](/Users/administrator/Sites/friedutchplus/templates/cloud_chat_app.html)
  - [`templates/cloud_chat_admin.html`](/Users/administrator/Sites/friedutchplus/templates/cloud_chat_admin.html)
  - [`static/css/pages/cloud_chat.css`](/Users/administrator/Sites/friedutchplus/static/css/pages/cloud_chat.css)
  - [`static/js/pages/cloud_chat.js`](/Users/administrator/Sites/friedutchplus/static/js/pages/cloud_chat.js)
- Minecraft owns:
  - [`projects/minecraft/minecraft.py`](/Users/administrator/Sites/friedutchplus/projects/minecraft/minecraft.py)
  - [`templates/minecraft.html`](/Users/administrator/Sites/friedutchplus/templates/minecraft.html)
  - [`static/css/pages/minecraft.css`](/Users/administrator/Sites/friedutchplus/static/css/pages/minecraft.css)
  - [`static/img/pages/minecraft/background.jpg`](/Users/administrator/Sites/friedutchplus/static/img/pages/minecraft/background.jpg)

### Separation rules
- Python belongs in `.py`
- HTML belongs in `templates/`
- CSS belongs in `static/css/`
- JS belongs in `static/js/`

### Runtime model
- App listens on `127.0.0.1:5001`.
- It is self-hosted on macOS.
- The process is managed by LaunchAgent outside the repo:
  - `/Users/administrator/Library/LaunchAgents/friedutchplus.server.plist`
- Another AI copilot must treat that LaunchAgent, and any related `friedutch.plus` LaunchAgents, as hands-off operational infrastructure.
- `POST /deploy` runs [`deploy.sh`](/Users/administrator/Sites/friedutchplus/deploy.sh), which pulls `main` and restarts the app service.

### Minecraft page notes
- The Minecraft page is currently a stacked list of full-width cards.
- The top card is a `Server ID` card showing:
  - public server name `FP SMP`
  - join address
  - online status
  - live player count when available
- Public details live in `Game Details`.
- Start/stop and other operational controls live only in the `Admin Controls` card and only render for a Smart Lock admin session.
- The page background image is served from [`static/img/pages/minecraft/background.jpg`](/Users/administrator/Sites/friedutchplus/static/img/pages/minecraft/background.jpg).
- The live Minecraft server-list name comes from the server `motd`, which is currently `FP SMP`.

### Frontend behavior notes
- Shared theme and confirm behavior lives in:
  - [`static/js/early-theme.js`](/Users/administrator/Sites/friedutchplus/static/js/early-theme.js)
  - [`static/js/theme.js`](/Users/administrator/Sites/friedutchplus/static/js/theme.js)
- Browser storage uses a resilient wrapper with cookie fallback when local storage is unavailable.
- Smart Lock admin tab memory uses that same browser storage layer.
- Avoid `min-height: 100%` on cards inside auto-sized CSS grid layouts unless the parent track has an explicit fixed height.
- That pattern can create hover/focus relayout loops where cards keep growing during interaction.

### Debugging notes
- Static assets use versioned URLs to reduce stale-cache problems.

### Commands another AI will likely need
- Validate Python syntax:
  - `python3 -m py_compile run.py app/*.py projects/smartlock/*.py projects/cloud_storage/cloud_storage.py projects/cloud_chat/cloud_chat.py projects/minecraft/minecraft.py`
- Inspect changed files:
  - `git status --short`
  - `git diff -- <paths>`
- Search code:
  - `rg "pattern"`

### Documentation rule
- After any code change, review every `README.md` in the repo and update the relevant ones if behavior, ownership, routes, or workflow changed.

### Environment template
- Use [`.env.example`](/Users/administrator/Sites/friedutchplus/.env.example) as the non-secret reference for expected environment variables.
