# Footprint

## Human Summary
- Footprint is a private scanning tool for checking where an email or domain appears across breaches and account-recovery flows.
- It stores results in its own SQLite database and is meant for internal/admin use.
- The page shows breach lists, account-probe results, and discovered addresses from one scan target.
- Another AI should read [`/Users/administrator/Sites/friedutchplus/AGENTS.md`](/Users/administrator/Sites/friedutchplus/AGENTS.md) before changing this feature.

## AI Copilot

### Purpose
- OSINT-style account and breach scanning tool under `/footprint/`.
- Designed to inspect a single email address or an entire domain, with emphasis on `@friedutch.plus`.

### Module ownership
- Owning backend module:
  - [`projects/footprint/footprint.py`](/Users/administrator/Sites/friedutchplus/projects/footprint/footprint.py)
- Owning database:
  - [`projects/footprint/footprint.db`](/Users/administrator/Sites/friedutchplus/projects/footprint/footprint.db)
- Owning template:
  - [`templates/footprint.html`](/Users/administrator/Sites/friedutchplus/templates/footprint.html)
- Owning CSS:
  - [`static/css/pages/footprint.css`](/Users/administrator/Sites/friedutchplus/static/css/pages/footprint.css)
- Owning JS:
  - [`static/js/pages/footprint.js`](/Users/administrator/Sites/friedutchplus/static/js/pages/footprint.js)

### Boundary rule
- Other modules should not open `footprint.db` directly unless there is a deliberate cross-module design change.
- Smart Lock is only used here for access control via `is_admin()`.

### Registration model
- This feature is not a Flask `Blueprint`.
- It is registered by calling `init_footprint(app, csrf)` from [`app/__init__.py`](/Users/administrator/Sites/friedutchplus/app/__init__.py).

### Access model
- Footprint relies on Smart Lock admin state.
- Treat it as an admin-only internal tool.
- The `/footprint/` page should redirect to Smart Lock login when there is no active admin session.

### What the feature does
- Accepts a scan target:
  - an email address
  - a domain
- Queries / computes:
  - breach results
  - account-probe results across many third-party services
  - discovered addresses for a domain
- Persists scan results in SQLite.

### Routes
- `/footprint/`
  - main UI
- `/footprint/scan`
  - POST endpoint for running scans

### Database tables
- `scans`
  - scan metadata and target type
- `breaches`
  - breach records linked to a scan
- `probe_results`
  - per-site account probe results linked to a scan
- `addresses`
  - discovered addresses linked to a scan

### External dependencies / services
- Have I Been Pwned:
  - uses `HIBP_API_KEY`
- `aiohttp`
  - async parallel probing
- `requests`
  - HIBP requests
- `bleach`
  - sanitization

### Important implementation details
- The module contains a very large `_SITES` probe definition list.
- Some probes are intentionally marked `inconclusive`.
- Network failures are common and should be treated as expected operational cases, not necessarily bugs.
- UI rendering and interaction are split into:
  - [`templates/footprint.html`](/Users/administrator/Sites/friedutchplus/templates/footprint.html)
  - [`static/js/pages/footprint.js`](/Users/administrator/Sites/friedutchplus/static/js/pages/footprint.js)
  - [`static/css/pages/footprint.css`](/Users/administrator/Sites/friedutchplus/static/css/pages/footprint.css)

### Known pitfalls for future changes
- Do not move the large `_SITES` list into templates or JS.
- Be careful with probe semantics; some “found” / “not_found” regex rules are heuristic.
- Do not assume every outbound request is reliable.
- Keep Smart Lock dependency limited to admin gating unless intentionally expanding the integration.
