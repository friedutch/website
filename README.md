# Project Guide

## Human Summary
- This repo powers a personal website with a simple home page plus three internal tools: Smart Lock, Cloud Storage, and Chat.
- `run.py` starts the Flask app, and each feature stays in its own project area.
- Another AI copilot should start with [`AGENTS.md`](/Users/administrator/Sites/friedutchplus/AGENTS.md), then this file.

## AI Copilot

### Purpose
- Personal self-hosted Flask app on `friedutch.plus`.
- The whole site renders inside one shared minimal shell.
- The project list is horizontal and text-based.
- Set `SITE_BRAND_NAME` to rename the visible site brand everywhere at once.
- The canonical site-wide admin login is `/login`.
- Chat uses its own project login at `/chat/login`.
- The home route `/` shows a minimal personal tools title inside the shared shell.

### Current features
- Smart Lock
  - site-wide admin auth and admin management
- Cloud Storage
  - private admin-only file handoff
- Chat
  - project-scoped username/password chat users and private DMs

### Entrypoints
- [`run.py`](/Users/administrator/Sites/friedutchplus/run.py)
  - main runtime entrypoint
- [`app/__init__.py`](/Users/administrator/Sites/friedutchplus/app/__init__.py)
  - app factory and top-level routes
- [`app/rendering.py`](/Users/administrator/Sites/friedutchplus/app/rendering.py)
  - shared render helper and project navigation state
- [`app/site_admin.py`](/Users/administrator/Sites/friedutchplus/app/site_admin.py)
  - shared admin-session helpers

### Repo structure
- [`templates/_app_frame.html`](/Users/administrator/Sites/friedutchplus/templates/_app_frame.html)
  - shared app shell
- [`static/css/base.css`](/Users/administrator/Sites/friedutchplus/static/css/base.css)
  - global visual system for tokens, typography, cards, buttons, inputs, chips, and shared components
- [`static/css/site_shell.css`](/Users/administrator/Sites/friedutchplus/static/css/site_shell.css)
  - shared shell and horizontal project navigation layout
- [`projects/smartlock/`](/Users/administrator/Sites/friedutchplus/projects/smartlock)
  - Smart Lock owner
- [`projects/cloud_storage/cloud_storage.py`](/Users/administrator/Sites/friedutchplus/projects/cloud_storage/cloud_storage.py)
  - Cloud Storage owner
- [`projects/cloud_chat/chat.py`](/Users/administrator/Sites/friedutchplus/projects/cloud_chat/chat.py)
  - Chat owner

### Runtime model
- The app listens on `127.0.0.1:5001`.
- Static assets use an asset-version query string from `ASSET_VERSION`, git metadata, or the deployment timestamp fallback.
- Static assets are configured for long-lived cache headers.
  - `POST /deploy` runs [`deploy.sh`](/Users/administrator/Sites/friedutchplus/deploy.sh), which pulls `main` and restarts the LaunchAgent-backed site in place.

### Security and state
- Never commit runtime databases or other live state:
  - `*.db`
  - `*.sqlite`
  - `*.sqlite3`
  - caches, temp files, logs, upload payloads, or machine-specific artifacts
- Current local runtime database paths:
  - [`projects/smartlock/smartlock.db`](/Users/administrator/Sites/friedutchplus/projects/smartlock/smartlock.db)
  - [`projects/cloud_storage/cloud_storage.db`](/Users/administrator/Sites/friedutchplus/projects/cloud_storage/cloud_storage.db)
  - [`projects/cloud_chat/cloud_chat.db`](/Users/administrator/Sites/friedutchplus/projects/cloud_chat/cloud_chat.db)
- Those DB files are runtime-only and must stay untracked.

### Environment variables
- `SECRET_KEY`
- `RESEND_API_KEY`
- `MAIL_FROM`
- `MAIL_TO`
- `SMARTLOCK_HARDWARE_API_KEY`
- `CLOUD_STORAGE_ROOT`
- `ASSET_VERSION`
- `GITHUB_REPO_URL`
- `GITHUB_BRANCH`
- `SITE_BRAND_NAME`
- `FRIEDUTCH_SKIP_GIT_METADATA`

### Feature notes
- Performance
  - The client UI uses local system fonts and no remote font requests.
  - Versioned static assets can be cached long-term.
  - The content security policy allows only local scripts/styles/fonts/images plus data URLs for images/fonts.
  - Set `ASSET_VERSION`, `GITHUB_REPO_URL`, and `GITHUB_BRANCH`, or set `FRIEDUTCH_SKIP_GIT_METADATA=1`, to avoid Git subprocess metadata lookups at startup.
  - The shared top menu keeps project and utility buttons on one visual style, and auth pages hide the admin shortcut.
- Smart Lock
  - canonical login is `/login`
  - `/smartlock/login` remains a compatibility alias
  - Smart Lock hardware validation uses `SMARTLOCK_HARDWARE_API_KEY`
- Cloud Storage
  - requires Smart Lock admin state
  - stores file contents outside the repo in `CLOUD_STORAGE_ROOT`
- Chat
  - users sign in at `/chat/login`
  - users are separate from Smart Lock users
  - passwords are stored as hashes
  - login attempts are throttled
  - direct messages, presence, and unread state live in the project runtime DB

### Recommended workflow
- Read:
  - [`AGENTS.md`](/Users/administrator/Sites/friedutchplus/AGENTS.md)
  - [`projects/smartlock/README.md`](/Users/administrator/Sites/friedutchplus/projects/smartlock/README.md)
  - [`projects/cloud_storage/README.md`](/Users/administrator/Sites/friedutchplus/projects/cloud_storage/README.md)
  - [`projects/cloud_chat/README.md`](/Users/administrator/Sites/friedutchplus/projects/cloud_chat/README.md)
- Validate Python syntax with:
  - `python3 -m py_compile run.py app/*.py projects/smartlock/*.py projects/cloud_storage/cloud_storage.py projects/cloud_chat/chat.py`
- Before committing, verify that no runtime DB files are tracked:
  - `git ls-files '*.db' '*.sqlite' '*.sqlite3'`
