# Cloud Storage

## Human Summary
- Cloud Storage is a private admin-only drop zone for moving files from the Mac to another device.
- It reuses Smart Lock admin login instead of introducing a new auth system.
- Uploaded files stay available until you delete them.

## AI Copilot

### Ownership
- [`projects/cloud_storage/cloud_storage.py`](/Users/administrator/Sites/friedutchplus/projects/cloud_storage/cloud_storage.py)
- [`templates/cloud_storage.html`](/Users/administrator/Sites/friedutchplus/templates/cloud_storage.html)
- [`static/css/pages/cloud_storage.css`](/Users/administrator/Sites/friedutchplus/static/css/pages/cloud_storage.css)
- [`static/js/pages/cloud_storage.js`](/Users/administrator/Sites/friedutchplus/static/js/pages/cloud_storage.js)
- [`projects/cloud_storage/cloud_storage.db`](/Users/administrator/Sites/friedutchplus/projects/cloud_storage/cloud_storage.db)

### Purpose
- Provide a private, single-admin file handoff page under `/cloud-storage/`.
- Allow the Smart Lock admin to upload, browse, download, and delete files.
- Keep uploaded file contents outside the Git repo.

### Access model
- Cloud Storage relies on Smart Lock admin state.
- Treat it as an admin-only internal tool.
- The `/cloud-storage/` page should redirect to Smart Lock login when there is no active admin session.

### Storage model
- File metadata is stored in `cloud_storage.db`.
- File contents are written to `CLOUD_STORAGE_ROOT`.
- The default storage root is `/Users/administrator/Storage/cloud_storage`.
- Uploaded files remain available until manually deleted.

### Registration model
- This feature is not a Flask `Blueprint`.
- It is registered by calling `init_cloud_storage(app)` from [`app/__init__.py`](/Users/administrator/Sites/friedutchplus/app/__init__.py).

### Routes
- `/cloud-storage/`
  - main UI
- `POST /cloud-storage/upload`
  - upload a file
- `/cloud-storage/download/<int:file_id>`
  - download a stored file
- `POST /cloud-storage/delete/<int:file_id>`
  - delete a stored file

### Database table
- `files`
  - original filename, stored filename, mime type, size, and created timestamp

### Environment variables
- `CLOUD_STORAGE_ROOT`

### Boundary rule
- Other modules should not open `cloud_storage.db` directly unless there is a deliberate cross-module design change.
- Do not move uploaded file contents into the repo.
