# Friedutch Plus

Personal self-hosted web app with separate project modules for the homepage, smart lock, and footprint tools.

## Structure

- `run.py`: primary app entrypoint
- `server.py`: backward-compatible shim that points to `run.py`
- `app/__init__.py`: Flask app factory and project registration
- `projects/smartlock/smartlock.py`: smart lock backend
- `projects/footprint/footprint.py`: footprint backend
- `templates/`: Jinja templates for homepage and project pages
- `static/`: shared CSS and JavaScript assets

## Run

```bash
python3 run.py
```
