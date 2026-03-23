# Friedutch Plus

## Human Summary
- This repo powers a personal website with a homepage plus two internal tools: Smart Lock and Footprint.
- `run.py` starts the site, `app/__init__.py` wires everything together, and each feature lives in its own project folder.
- The site is self-hosted on macOS and restarted through a LaunchAgent when deployments happen.
- If the site goes down, the most likely cause is the LaunchAgent-managed process not running.
- Another AI copilot should start with [`AGENTS.md`](/Users/administrator/Sites/friedutchplus/AGENTS.md), then this file.

## AI Copilot

### Purpose
- Personal self-hosted Flask web app for the `friedutch.plus` website.
- The repo contains one main Flask app shell plus feature modules:
  - Smart Lock
  - Footprint
  - Minecraft public landing page

### Entrypoints
- [`run.py`](/Users/administrator/Sites/friedutchplus/run.py): primary runtime entrypoint. Use this when starting the app intentionally.
- [`app/__init__.py`](/Users/administrator/Sites/friedutchplus/app/__init__.py): Flask app factory, homepage route, deploy webhook, and project registration.
- [`AGENTS.md`](/Users/administrator/Sites/friedutchplus/AGENTS.md): repo operating guide for another AI coding agent.

### Runtime model
- The app is a single Flask process running on `127.0.0.1:5001`.
- The process is managed by a macOS LaunchAgent outside the repo:
  - `/Users/administrator/Library/LaunchAgents/friedutchplus.server.plist`
- The LaunchAgent now points directly at [`run.py`](/Users/administrator/Sites/friedutchplus/run.py).
- Future AI coding copilots must not edit or operate that LaunchAgent, or any related `friedutch.plus` LaunchAgents, unless the human explicitly asks for operational changes.
- Deploys are expected to restart the existing LaunchAgent-managed service, not run ad hoc Python processes.

### How code becomes live
- GitHub webhook hits `POST /deploy`.
- [`app/__init__.py`](/Users/administrator/Sites/friedutchplus/app/__init__.py) verifies `X-Hub-Signature-256` using `GITHUB_WEBHOOK_SECRET`.
- On success it launches [`deploy.sh`](/Users/administrator/Sites/friedutchplus/deploy.sh).
- [`deploy.sh`](/Users/administrator/Sites/friedutchplus/deploy.sh) does:
  - `git pull origin main`
  - `launchctl kickstart -k` for the existing service when present
  - `launchctl bootstrap` only if the service is missing

### Key constraints for future edits
- Keep separation of concerns:
  - Python in `.py`
  - HTML in `templates/`
  - CSS in `static/css/`
  - JavaScript in `static/js/`
- Do not move frontend code back into embedded Python strings.
- Prefer updating [`run.py`](/Users/administrator/Sites/friedutchplus/run.py) and the app factory.
- Treat LaunchAgent changes as operational changes, not normal app-code changes.
- Unless explicitly instructed otherwise, another AI copilot should limit itself to repo edits plus `git commit`/`git push`, and should not reload or modify running `friedutch.plus` services.
- If changing deploy/restart behavior, preserve the current “kickstart if present, bootstrap if absent” pattern unless there is a deliberate replacement plan.
- Smart Lock requires session cookies:
  - no-cookie browsers should be shown the minimal cookies-required page instead of login/admin UI
  - Smart Lock POST failures from missing CSRF session state should render that same cookies-required page
- Smart Lock admin mutations are POST-only and CSRF-protected:
  - session logout
  - session purge
  - user deletion
  - RFID/fingerprint toggles

### Repo structure
- [`app/__init__.py`](/Users/administrator/Sites/friedutchplus/app/__init__.py): app factory, `/`, `/deploy`
- [`app/rendering.py`](/Users/administrator/Sites/friedutchplus/app/rendering.py): shared render helper that injects the template path and the footer timestamp
- [`templates/minecraft.html`](/Users/administrator/Sites/friedutchplus/templates/minecraft.html): public landing page for the self-hosted Minecraft server
- [`static/css/pages/minecraft.css`](/Users/administrator/Sites/friedutchplus/static/css/pages/minecraft.css): Minecraft page styling
- [`projects/smartlock/smartlock.py`](/Users/administrator/Sites/friedutchplus/projects/smartlock/smartlock.py): Smart Lock feature owner
- [`projects/footprint/footprint.py`](/Users/administrator/Sites/friedutchplus/projects/footprint/footprint.py): Footprint feature owner
- [`projects/minecraft/minecraft.py`](/Users/administrator/Sites/friedutchplus/projects/minecraft/minecraft.py): Minecraft landing page feature owner
- [`templates/`](/Users/administrator/Sites/friedutchplus/templates): Jinja templates
- [`static/`](/Users/administrator/Sites/friedutchplus/static): CSS and JS assets

### Project ownership boundaries
- Smart Lock owns:
  - [`projects/smartlock/smartlock.py`](/Users/administrator/Sites/friedutchplus/projects/smartlock/smartlock.py)
  - [`projects/smartlock/smartlock.db`](/Users/administrator/Sites/friedutchplus/projects/smartlock/smartlock.db)
  - [`templates/smartlock/`](/Users/administrator/Sites/friedutchplus/templates/smartlock)
  - `static/css/pages/smartlock/*`
  - `static/js/pages/smartlock/*`
- Footprint owns:
  - [`projects/footprint/footprint.py`](/Users/administrator/Sites/friedutchplus/projects/footprint/footprint.py)
  - [`projects/footprint/footprint.db`](/Users/administrator/Sites/friedutchplus/projects/footprint/footprint.db)
  - [`templates/footprint.html`](/Users/administrator/Sites/friedutchplus/templates/footprint.html)
  - [`static/css/pages/footprint.css`](/Users/administrator/Sites/friedutchplus/static/css/pages/footprint.css)
  - [`static/js/pages/footprint.js`](/Users/administrator/Sites/friedutchplus/static/js/pages/footprint.js)
- Minecraft owns:
  - [`projects/minecraft/minecraft.py`](/Users/administrator/Sites/friedutchplus/projects/minecraft/minecraft.py)
  - [`templates/minecraft.html`](/Users/administrator/Sites/friedutchplus/templates/minecraft.html)
  - [`static/css/pages/minecraft.css`](/Users/administrator/Sites/friedutchplus/static/css/pages/minecraft.css)
- Smart Lock login cooldowns are actor-scoped, not global:
  - one browser/device should not block another from requesting its own magic link
  - the current actor identity is a browser-session token stored in the Flask session cookie
  - cooldown settings are keyed per browser session, not per IP

### Databases
- Smart Lock database:
  - [`projects/smartlock/smartlock.db`](/Users/administrator/Sites/friedutchplus/projects/smartlock/smartlock.db)
- Footprint database:
  - [`projects/footprint/footprint.db`](/Users/administrator/Sites/friedutchplus/projects/footprint/footprint.db)
- These are SQLite files committed/used as local runtime state.
- Do not rename or migrate DB tables casually. There are already legacy names in use, especially in Smart Lock.

### Environment variables
- Required or expected runtime variables:
  - `SECRET_KEY`
  - `GITHUB_WEBHOOK_SECRET`
  - `RESEND_API_KEY`
  - `MAIL_FROM`
  - `MAIL_TO`
  - `HIBP_API_KEY`
  - `MINECRAFT_JOIN_HOST`
  - `MINECRAFT_JOIN_PORT`
  - `MINECRAFT_SERVER_ROOT`
  - `MINECRAFT_WORLD_NAME`
  - `MINECRAFT_LAUNCH_AGENT_LABEL`
  - `MINECRAFT_LAUNCH_AGENT_PLIST`
  - `MINECRAFT_SERVER_EDITION`
  - `MINECRAFT_SERVER_VERSION`
  - `MINECRAFT_SERVER_ACCESS`
- `MAIL_TO` is only the bootstrap default for the Smart Lock admin email; after initialization, the live admin email is stored in the Smart Lock database settings.
- `.env` loading happens at import time in [`app/__init__.py`](/Users/administrator/Sites/friedutchplus/app/__init__.py) so project modules can see env config when initialized.
- [`.env.example`](/Users/administrator/Sites/friedutchplus/.env.example) provides the non-secret key list for bootstrapping another environment.

### Minecraft landing page
- The Minecraft landing page is served from `https://friedutch.plus/minecraft`.
- This page shows the live join hostname plus a server-details block sourced from the local Minecraft host when available.
- Minecraft start and stop controls are not public; they require either a local request on the host or an authenticated Smart Lock admin session.
- This page only publishes server details; it does not run the game server inside Flask.
- Run the actual Minecraft server as a separate process or service on your host.
- Point DNS such as `mc.friedutch.plus` to that host and keep the page config synchronized through the `MINECRAFT_SERVER_*` environment variables.

### Observability / debugging conventions
- The Flask app sets baseline security headers on responses:
  - Content-Security-Policy
  - X-Frame-Options
  - X-Content-Type-Options
  - Referrer-Policy
  - Cross-Origin-Opener-Policy
  - Cross-Origin-Resource-Policy
- Static CSS/JS URLs include an asset-version query string so browsers pick up new frontend files after deploys.
- Deploy output is written to:
  - `/tmp/deploy.log`
- LaunchAgent stdout/stderr logs are outside the repo:
  - `/Users/administrator/Library/Logs/friedutchplus.server.log`
  - `/Users/administrator/Library/Logs/friedutchplus.server.err.log`

### Operational caveats
- The app still runs on the Flask development server.
- That is acceptable for this personal self-hosted setup, but not equivalent to a production WSGI stack.
- LaunchAgent reloads on macOS can be flaky. If a `bootstrap` fails once, retrying the exact load command may succeed.
- A site-wide “Bad Gateway” usually means the LaunchAgent-managed process is not running, not necessarily that app code is broken.

### Recommended workflow for another AI copilot
- Read [`AGENTS.md`](/Users/administrator/Sites/friedutchplus/AGENTS.md) first.
- Then read this file.
- Then read:
  - [`projects/smartlock/README.md`](/Users/administrator/Sites/friedutchplus/projects/smartlock/README.md)
  - [`projects/footprint/README.md`](/Users/administrator/Sites/friedutchplus/projects/footprint/README.md)
  - [`projects/minecraft/README.md`](/Users/administrator/Sites/friedutchplus/projects/minecraft/README.md)
- For live/runtime issues, inspect:
  - [`deploy.sh`](/Users/administrator/Sites/friedutchplus/deploy.sh)
  - [`app/__init__.py`](/Users/administrator/Sites/friedutchplus/app/__init__.py)
  - LaunchAgent logs
- For normal feature work, do not operate any `friedutch.plus` LaunchAgent; make the repo change, commit it, and push it.
- For feature work, stay inside the owning module and its templates/static files.
