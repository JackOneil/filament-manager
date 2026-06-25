# Filament Manager 🧵

*Current version: **v1.118.1***

A modern, self-hosted web application for managing 3D printer filament inventory, print projects, and printer integrations — built for makers, small studios, and print farms.

## ✨ Key Features

### Inventory Management
- **Filament Stock Browser** — Card/list/compact views with progress bars, low-stock indicators, filtering by brand/material/color/tag, sorting, pagination, and saved views at `/filaments`.
- **Filament Detail** — Per-spool timeline, quality log (stringing, adhesion, drying, profiles), min/max stock guardrails, automatic reorder recommendations, and a 6-month consumption bar chart.
- **Quick-View Filter Pills** — One-click filter buttons for *All*, *Low stock*, and *Reorder needed* inside the sticky filter bar.
- **CSV / Excel Import** — Two-step import wizard at `/filaments/import-csv` that parses CSV/TSV, shows a preview table, and auto-creates missing brands/materials/colors on confirm.
- **Bulk Operations** — Select multiple filaments and batch-apply spool changes, weight updates, tags, min-stock values, or deletion.
- **Smooth AJAX Skeleton Loading** — Inventory and project list reloads now render animated skeleton placeholders to avoid abrupt content jumps during filtering, sorting, and pagination.
- **Undo for Destructive Inventory Actions** — After filament deletion, bulk delete, or spool removal, a dedicated toast allows one-click rollback of the last destructive action.
- **Movement History** — Full audit log of every weight change with reasons, timestamps, and linked projects/jobs.
- **Waste / Scrap Tracker** — Record failed prints with categorised failure reason (stringing, warping, bed adhesion, clogging, layer shift, spaghetti, broken support), weight, linked filament, and optional project. Edit records in-place via a pre-filled modal. Attach one or more **photos** (JPG/PNG/GIF/WEBP) to each record to document the failure visually — thumbnails are shown inline with a click-to-open lightbox. Interactive filament and project search dropdowns in the add/edit modal. Filterable list at `/waste` with cumulative waste stats bar. Photos are included in full backup export/restore.
- **Storage Shelf Map** — Visual grid layout of physical shelf positions. Assign spools to named slots, drag-and-drop moves, and stock-level fill indicators.

### Projects & Client Workflow
- **Project Management** — Track 3D print jobs as unified projects with client names, contact details (email, phone), due dates, priority levels (Low/Medium/High/Urgent), statuses (NEW → PRINTING → DONE), file attachments, and external links with rich preview cards.
- **Project TODO Checklists** — Per-project task checklists with optional due dates. Overdue and near-deadline tasks are highlighted with colour-coded badges and surfaced automatically on the overview page in the Action Center hot list.
- **Kanban Board** — Overview of all projects by status with paginated columns, due-date calendar strip, and estimate-vs-actual metrics. Priority badges on each card and a quick text search filter.
- **Quick Status Advance** — One-click button in the project detail header moves a project to the next step in the workflow without using the status dropdown.
- **Clone Project** — Duplicate any project (filaments and print items included) with a single click. Useful for recurring client orders.
- **Public Share Link** — Generate a token-based read-only share URL for a project. Clients can view status, description, and print-item progress without logging in. Links can be revoked at any time.
- **Project Templates** — Save any project as a reusable template. When creating a new project, select a template to pre-fill the name, description, tags, and estimated print time.
- **Emoji Reactions on Comments** — React to project comments with 👍 ✅ 🔄 🎉 ❤️. Counts update instantly via AJAX.
- **Activity Timeline** — Dedicated project tab showing a chronological timeline of all project events (quotes, uploads, comments, tasks) with colour-coded icons.
- **File Versioning** — Re-uploading a file with the same name automatically creates a versioned history grouped under the root file.
- **Image Thumbnails** — Image attachments (JPG/PNG/GIF/WEBP) in the Files tab show a 40×40 clickable thumbnail that opens a full-screen lightbox.
- **Print Cost Calculator** — Enter model weight and print time, see exact material + electricity cost. Save quotes to projects with margin and customer pricing, and export them using fully self-hosted invoice templates (simple, detailed, or pro-forma) with sequential invoice numbering.
- **Central 3D Model Browser** — Central model browser featuring interactive 3D mesh rendering, material colors, timeline history, and WebGL canvas snapshots.

### Multi-User Workspace
- **Role-Based Access** — Administrators have full read/write access; regular users see only permitted sections and their own projects.
- **Self-Registration & Invites** — Users register themselves or receive invite codes with pre-configured role and section permissions. Invite links can be cancelled and show expiration status.
- **User Management Page** — Admin-only `/users` page with paginated table, AJAX filtering (search, role, status, sort), and bulk actions (activate/deactivate/delete).
- **User Deletion** — Permanent account removal with safety checks (cannot delete self or last admin). Owned projects are automatically reassigned.
- **Enhanced User Detail** — Per-user activity view showing recent projects, comments, notification count, and audit trail with deep-link to full audit log.
- **Operator Mode** — Admins can switch to a read-only Operator view without logging out; an amber indicator badge appears in the top bar.
- **Project Collaboration** — Project ownership, approval workflow (Pending → Approved/Rejected), per-project comments, and in-app notifications.
- **Admin Audit Log** — Successful administrator actions are recorded with user, IP/session, endpoint, target object, and before/after snapshots.

### Printer Integrations
- **Bambu Lab Cloud** — Sync print jobs from Bambu Cloud API. Assign filaments and projects, deduct stock per-AMS-slot, background auto-sync with configurable pre-job time offset. Intelligent project name suggestions from job titles with one-click project creation directly from the Bambu jobs page.
- **PrusaLink** — Poll local Prusa printers via REST API (no cloud required). Automatic job capture, progress tracking, and filament mapping.
- **Printer Maintenance Log** — Dedicated `/maintenance` module for logging nozzle changes, calibrations, services, and faults per printer, with overdue and due-soon badge indicators. Supports recurring schedules (hours/days/months), predictive due dates from real operation metrics (print-hours/jobs/filament usage), SOP template prefills, quick card actions (duplicate/+30 days/resolve fault), optional Markdown maintenance notes, and `.ics` calendar export for Google Calendar / Outlook.
- **Live Printer Dashboard** — Overview page shows active print jobs with real-time progress bars, ETA, material swatches, and brand badges.

### Analytics & Operations
- **Statistics Dashboard** — Executive KPI panel, usage/purchase trend charts, stock depletion forecast, reorder recommendations, profitable projects, color palette. Draggable sections with hide/show and per-card row limits, enhanced drag ghost, clearer drop zones, mini in-UI drag guide, and direct row links from key widgets to related filament/project detail.
- **Action Center** — Highlights low-stock alerts, overdue projects, unmapped print jobs, and printer sync issues in one place.
- **Automatic Purchase Recommendations** — Based on 30/90-day real usage, recommends what to order next with spool counts and purchase price.
- **Configurable Timezone** — All timestamps are displayed in the configured local timezone (default: Europe/Prague) while data is stored as UTC.

### Platform
- **PostgreSQL or SQLite** — Local SQLite for simple single-user setups. PostgreSQL for production with better concurrency and point-in-time recovery. Auto-detected via `DATABASE_URL` env var.
- **Progressive Web App** — Install on desktop or mobile device with offline-capable shell.
- **Interactive Help System** — Floating `?` button on every page opens a slide-out panel with contextual tips for the current section, full-text search across all tips, and a bilingual accordion of all features. Automatically switches language with the app.
- **Dark Mode** — Full dark theme support with per-user persistence.
- **Bilingual** — Complete Czech and English translations (700+ keys).
- **Full Backup / Restore** — Compressed `.tar.gz` export with `manifest.json` plus real uploaded project files and waste record photos stored directly in the archive. Import also supports older `.json.gz` and legacy plain JSON backups.
- **Settings Tabs** — Settings page is organized into six tabs: General, Printers, Integrations, Company, Data, and Dictionaries.
- **Settings UX & Backup Safety** — Unified save/confirm/error toasts, printer health summary card, Bambu connection test without saving token, Prusa pre-save connectivity check, and Data-tab backup tooling with full/database-only export, backup metadata, dry-run import compatibility checks, and conflict modes (`skip`/`merge`/`overwrite`).
- **Onboarding Checklist** — Guided setup checklist after first installation (currency, energy cost, printer connection, first filament) with auto-dismiss.
- **Toast Notifications** — Non-blocking pop-up notifications with auto-dismiss via Alpine.js.
- **Custom Dictionaries** — Pre-seeded brands, materials, and colors. All freely expandable, renamable, and safely deletable.

---

## 🛠️ Tech Stack

| Layer          | Technology                                               |
| -------------- | -------------------------------------------------------- |
| Backend        | Python 3.11, Flask 3.0, Gunicorn                        |
| Database       | SQLite (default) or PostgreSQL via `DATABASE_URL` env var  |
| Templates      | Jinja2 (server-side rendering)                           |
| Frontend       | TailwindCSS (self-hosted), Alpine.js 3.x (self-hosted)   |
| Charts         | Chart.js (self-hosted)                                   |
| 3D Viewer      | Online3DViewer (self-hosted)                             |
| Icons          | FontAwesome (self-hosted)                                |
| Security       | Flask-WTF (CSRF), cryptography (Fernet), scrypt hashing  |
| Infrastructure | Docker & Docker Compose                                  |

---

## 📦 Project Structure

```
filament/
├── app.py                  # App factory, background workers
├── database.py             # Shared SQLAlchemy instance + dialect detection
├── migrations.py           # Database migrations and seed data
├── models.py               # All ORM models (~24 tables)
├── messages.py             # i18n dictionaries (cs + en)
├── auth.py                 # Multi-user auth, RBAC, sessions
├── utils.py                # Shared helpers (stock logic, encryption, link preview)
│
├── routes/                 # Flask Blueprints modular routing structure
│   ├── __init__.py         #   Central registration and fallback url_for builder
│   ├── inventory.py        #   Inventory CRUD, CSV import, overview
│   ├── inventory_helpers.py#   Inventory helpers (query builders, stats, undo)
│   ├── api.py              #   AJAX filament list / search endpoints
│   ├── calculator.py       #   Print cost calculator
│   ├── history.py          #   Movement history
│   ├── projects.py         #   Projects CRUD, uploads, versioning, comments
│   ├── projects_helpers.py #   Project helpers (job feed, notifications, files)
│   ├── bambu.py            #   Bambu Lab Cloud integration
│   ├── bambu_helpers.py    #   Bambu helpers (sync engine, thumbnails, mapping)
│   ├── prusa.py            #   PrusaLink integration
│   ├── maintenance.py      #   Printer maintenance log, recurring intervals, ICS export
│   ├── stats.py            #   Statistics dashboard
│   ├── storage.py          #   Physical shelf management
│   ├── settings.py         #   App settings, timezone, tabs
│   ├── backup.py           #   Full export / import (backup & restore)
│   ├── backup_helpers.py   #   Backup helpers (export/import serialization)
│   ├── waste.py            #   Waste/scrap tracking
│   ├── models.py           #   Central 3D model browser, details, timeline, and thumbnails
│   ├── auth.py             #   Auth routes (login, register, users)
│   └── pwa.py              #   PWA manifest and service worker
│
├── templates/              # Jinja2 HTML templates (~30 files)
├── tests/                  # Automated tests (pytest)
├── data/                   # Runtime data (DB + uploads, gitignored)
│
├── Dockerfile              # Production image (python:3.11-slim)
├── docker-compose.yml      # App + PostgreSQL deployment
├── requirements.txt        # Python dependencies
├── .env                    # Environment variables
├── CHANGELOG.md            # Detailed version history
└── README.md               # This file
```

---

## 🚀 Quick Start

### Prerequisites

- **Docker** and **Docker Compose** installed on a Linux server (or local machine).

### 1. Clone the Repository

```bash
git clone <repository-url> /opt/git/filament
cd /opt/git/filament
```

### 2. Configure Environment

Copy or edit the `.env` file:

```bash
# Required — generate a strong random secret:
SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")

# Optional — enable token encryption at rest:
FERNET_KEY=$(python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")

# Optional — if behind a reverse proxy (nginx, Traefik):
# BEHIND_PROXY=1

# Optional — PostgreSQL (recommended for production):
# DATABASE_URL=postgresql://filament:CHANGE_ME@postgres:5432/filament
# POSTGRES_USER=filament
# POSTGRES_PASSWORD=CHANGE_ME
# POSTGRES_DB=filament
#
# If DATABASE_URL is not set, SQLite is used automatically (default).
```

### 3. Build & Run

```bash
docker compose up -d --build
```

### 4. Access the Application

Open your browser and navigate to:

```
http://localhost:5050
```

On the first launch:
- If `DATABASE_URL` is not set, the SQLite database is automatically created in `./data/filament.db`.
- If `DATABASE_URL` points to a PostgreSQL instance, the schema is created there automatically.
- Default dictionaries (brands, materials, colors) are seeded.
- **The first registered user automatically becomes an administrator.**

---

## 🔄 Upgrading

```bash
cd /opt/git/filament
git pull
docker compose up -d --build
```

Schema migrations run automatically on startup via `_safe_alter()` — no manual migration steps needed. Your data in `./data/` (SQLite) or the PostgreSQL volume is preserved across rebuilds.

---

## 💾 Backups

### Automatic (recommended)

Configure scheduled automatic backups in **Settings → Data**: choose daily/weekly/monthly frequency, a time of day, and whether to include project files. Backups are saved as compressed `.tar.gz` archives to `./data/backup/` on the server. You can manage existing backup files (download/delete) and trigger a manual backup anytime from the same settings panel.

For one-off exports, use **Settings → Export** to download a compressed `.tar.gz` backup of the entire application state.

Restore via **Settings → Import** (accepts `.tar.gz`, older `.json.gz`, and legacy `.json` formats).

### Manual

Simply back up the `./data/` directory:

```bash
cp -r /opt/git/filament/data /path/to/backup/
```

---

## 🐘 Migrating from SQLite to PostgreSQL

PostgreSQL offers better concurrency, point-in-time recovery, and replication — recommended for production deployments and multi-user environments.

### Migration Steps

1. **Export your SQLite data**  
   Go to **Settings → Data** and click **Export Database**. Download the `.tar.gz` backup.

2. **Stop the application**  
   ```bash
   cd /opt/git/filament
   docker compose down
   ```

3. **Configure PostgreSQL in `.env`**  
   ```bash
   DATABASE_URL=postgresql://filament:YOUR_STRONG_PASSWORD@postgres:5432/filament
   POSTGRES_USER=filament
   POSTGRES_PASSWORD=YOUR_STRONG_PASSWORD
   POSTGRES_DB=filament
   ```

4. **Start with PostgreSQL**  
   ```bash
   docker compose up -d --build
   ```
   The `postgres` container starts first (healthcheck), then the app creates all tables automatically.

5. **Import your backup**  
   Go to **Settings → Data → Import** and upload your `.tar.gz` backup.  
   Choose **Skip existing** mode to preserve the newly-created empty schema.

6. **Verify**  
   Check your inventory, projects, and settings are all present. The app is now running on PostgreSQL.

### Switching Back to SQLite

Remove or comment out `DATABASE_URL`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` from `.env`, then rebuild. Export/import the data the same way.

### PostgreSQL Performance Tuning

The application configures optimal defaults:
- Connection pool: 10 base + 20 overflow connections
- Connection recycling every 1 hour
- Pre-ping health checks before each use

For large deployments, tune `postgres` service in `docker-compose.yml`:
```yaml
postgres:
  command: >
    -c shared_buffers=256MB
    -c effective_cache_size=1GB
    -c work_mem=16MB
    -c maintenance_work_mem=128MB
```

---

## 🧪 Running Tests

```bash
# Install test runner (includes pytest-xdist for parallel execution)
pip install -r requirements.txt
pip install pytest-xdist

# Run full suite (parallel, auto-detects CPU cores — ~35s on 12 cores)
python -m pytest tests/ -n auto -v

# Run a single file
python -m pytest tests/test_bambu.py -v

Run the full suite in parallel (via pytest-xdist):

```bash
python -m pytest tests/ -v -n auto
```

Tests cover: authentication flows, Bambu sync idempotency, stock deduction logic, backup/restore integrity, SSRF protection, calculator, statistics routes, waste record CRUD, printer maintenance CRUD and ICS export, `_clean_title` helper, thumbnail MIME-type caching (S3 binary/octet-stream fallback), settings CRUD (dictionaries, Bambu Cloud, company, auto-backup), extended inventory CRUD and bulk ops, project status workflow and templates, undo system, model integrity, security (XSS/SSRF/path traversal), and performance benchmarks.

**Test suite statistics (v1.108.0):**
- **622 tests** across **31 test files**
- **~35 seconds** parallel (12 workers) vs **~168 seconds** sequential
- Covers **13 new test files** with ~440 new tests added

---

## 🗺️ Roadmap / Current Status

### ✅ Completed
- Core inventory management with progress tracking, stock alerts, and compact view
- CSV/Excel filament import wizard
- Multi-user authentication with RBAC, invite system, and operator mode
- Project management with Kanban, files, versioning, links, quotes, and comments
- Project activity timeline
- Sequential invoice numbering with fully self-hosted export templates
- Bambu Lab Cloud integration (auto-sync, per-AMS deduction, pre-job time offset)
- PrusaLink integration (local network, auto-poll)
- Multi-printer energy cost tracking (per-printer wattage and power draw configuration)
- Printer maintenance log module
- Statistics dashboard with drag-and-drop layout
- Storage shelf visualization
- Configurable display timezone
- Full backup/restore system with `.tar.gz` archive and legacy JSON support
- Admin audit log for privileged actions
- Onboarding checklist for first-time setup
- Tabbed settings page
- PWA support
- Interactive help system with contextual tips and full-text search
- Waste/scrap tracking with failure reason codes and filament linkage
- Printer maintenance recurring intervals and ICS calendar export
- CSRF protection and security hardening
- Docker-built local static assets for the main app shell (no page-load CDN dependency)
- Bilingual UI (CS/EN)
- Project priority levels, client contact fields (email/phone), quick text search on project list
- One-click status advance, project cloning, and project templates
- Public share links for client-facing read-only project views
- Emoji reactions on project comments
- Image thumbnails with lightbox in project file attachments
- Central 3D Model Browser with interactive previewer, material colors, timeline versioning, and canvas-to-thumbnail snapshots

### 🔮 Potential Future Work
- OctoPrint integration
- Filament spool RFID/NFC pairing
- REST API for third-party integrations

---

## 📄 License

Private project — see repository settings for access and licensing information.

---

## 📚 Further Reading

- [`.kilo/ARCHITECTURE.md`](.kilo/ARCHITECTURE.md) — Canonical architecture documentation (single source of truth for all rules and conventions)
- [`.github/copilot-instructions.md`](.github/copilot-instructions.md) — Technical manual for AI assistants and developers
- [`.kilo/BACKLOG.md`](.kilo/BACKLOG.md) — Implementation backlog with features, bugs, and technical debt
- [`CHANGELOG.md`](CHANGELOG.md) — Recent version history (Keep a Changelog format)
- [`CHANGELOG-ARCHIVE.md`](CHANGELOG-ARCHIVE.md) — Archived changelog entries (v1.100.0 and older)
