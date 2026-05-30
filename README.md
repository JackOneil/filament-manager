# Filament Manager 🧵

*Current version: **v1.91.0***

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
- **Project Management** — Track 3D print jobs as unified projects with client names, due dates, statuses (NEW → PRINTING → DONE), file attachments, and external links with rich preview cards.
- **Project TODO Checklists** — Per-project task checklists with optional due dates. Overdue and near-deadline tasks are highlighted with colour-coded badges and surfaced automatically on the overview page in the Action Center hot list.
- **Kanban Board** — Overview of all projects by status with paginated columns, due-date calendar strip, and estimate-vs-actual metrics.
- **Activity Timeline** — Dedicated project tab showing a chronological timeline of all project events (quotes, uploads, comments, tasks) with colour-coded icons.
- **File Versioning** — Re-uploading a file with the same name automatically creates a versioned history grouped under the root file.
- **Print Cost Calculator** — Enter model weight and print time, see exact material + electricity cost. Save quotes to projects with margin and customer pricing, and export them using fully self-hosted invoice templates (simple, detailed, or pro-forma) with sequential invoice numbering.
- **3D Model Viewer** — Interactive in-browser preview of `.stl` and `.3mf` files attached to projects.

### Multi-User Workspace
- **Role-Based Access** — Administrators have full read/write access; regular users see only permitted sections and their own projects.
- **Self-Registration & Invites** — Users register themselves or receive invite codes with pre-configured role and section permissions.
- **Operator Mode** — Admins can switch to a read-only Operator view without logging out; an amber indicator badge appears in the top bar.
- **Project Collaboration** — Project ownership, approval workflow (Pending → Approved/Rejected), per-project comments, and in-app notifications.
- **Admin Audit Log** — Successful administrator actions are recorded with user, IP/session, endpoint, target object, and before/after snapshots.

### Printer Integrations
- **Bambu Lab Cloud** — Sync print jobs from Bambu Cloud API. Assign filaments and projects, deduct stock per-AMS-slot, background auto-sync with configurable pre-job time offset. Intelligent project name suggestions from job titles with one-click project creation directly from the Bambu jobs page.
- **PrusaLink** — Poll local Prusa printers via REST API (no cloud required). Automatic job capture, progress tracking, and filament mapping.
- **Printer Maintenance Log** — Dedicated `/maintenance` module for logging nozzle changes, calibrations, services, and faults per printer, with overdue and due-soon badge indicators. Supports recurring schedules (hours/days/months) with auto-calculated next service dates and `.ics` calendar export for Google Calendar / Outlook.
- **Live Printer Dashboard** — Overview page shows active print jobs with real-time progress bars, ETA, material swatches, and brand badges.

### Analytics & Operations
- **Statistics Dashboard** — Executive KPI panel, usage/purchase trend charts, stock depletion forecast, reorder recommendations, profitable projects, color palette. Draggable sections with hide/show and per-card row limits, enhanced drag ghost, clearer drop zones, mini in-UI drag guide, and direct row links from key widgets to related filament/project detail.
- **Action Center** — Highlights low-stock alerts, overdue projects, unmapped print jobs, and printer sync issues in one place.
- **Automatic Purchase Recommendations** — Based on 30/90-day real usage, recommends what to order next with spool counts and purchase price.
- **Configurable Timezone** — All timestamps are displayed in the configured local timezone (default: Europe/Prague) while data is stored as UTC.

### Platform
- **Progressive Web App** — Install on desktop or mobile device with offline-capable shell.
- **Interactive Help System** — Floating `?` button on every page opens a slide-out panel with contextual tips for the current section, full-text search across all tips, and a bilingual accordion of all features. Automatically switches language with the app.
- **Dark Mode** — Full dark theme support with per-user persistence.
- **Bilingual** — Complete Czech and English translations (700+ keys).
- **Full Backup / Restore** — Compressed `.tar.gz` export with `manifest.json` plus real uploaded project files and waste record photos stored directly in the archive. Import also supports older `.json.gz` and legacy plain JSON backups.
- **Settings Tabs** — Settings page is organized into six tabs: General, Printers, Integrations, Company, Data, and Dictionaries.
- **Onboarding Checklist** — Guided setup checklist after first installation (currency, energy cost, printer connection, first filament) with auto-dismiss.
- **Toast Notifications** — Non-blocking pop-up notifications with auto-dismiss via Alpine.js.
- **Custom Dictionaries** — Pre-seeded brands, materials, and colors. All freely expandable, renamable, and safely deletable.

---

## 🛠️ Tech Stack

| Layer          | Technology                                               |
| -------------- | -------------------------------------------------------- |
| Backend        | Python 3.11, Flask 3.0, Gunicorn                        |
| Database       | SQLite via Flask-SQLAlchemy                              |
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
├── database.py             # Shared SQLAlchemy instance
├── migrations.py           # Database migrations and seed data
├── models.py               # All ORM models (~24 tables)
├── messages.py             # i18n dictionaries (cs + en)
├── auth.py                 # Multi-user auth, RBAC, sessions
├── utils.py                # Shared helpers (stock logic, encryption, link preview)
│
├── routes/                 # Flask Blueprints modular routing structure
│   ├── __init__.py         #   Central registration and fallback url_for builder
│   ├── inventory.py        #   Inventory CRUD, CSV import, overview
│   ├── api.py              #   AJAX filament list / search endpoints
│   ├── calculator.py       #   Print cost calculator
│   ├── history.py          #   Movement history
│   ├── projects.py         #   Projects CRUD, uploads, versioning, comments
│   ├── bambu.py            #   Bambu Lab Cloud integration
│   ├── prusa.py            #   PrusaLink integration
│   ├── maintenance.py      #   Printer maintenance log, recurring intervals, ICS export
│   ├── stats.py            #   Statistics dashboard
│   ├── storage.py          #   Physical shelf management
│   ├── settings.py         #   App settings, timezone, tabs
│   ├── backup.py           #   Full export / import (backup & restore)
│   ├── waste.py            #   Waste/scrap tracking
│   ├── auth.py             #   Auth routes (login, register, users)
│   └── pwa.py              #   PWA manifest and service worker
│
├── templates/              # Jinja2 HTML templates (~30 files)
├── tests/                  # Automated tests (pytest)
├── data/                   # Runtime data (DB + uploads, gitignored)
│
├── Dockerfile              # Production image (python:3.11-slim)
├── docker-compose.yml      # Single-service deployment
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
- The SQLite database is automatically created in `./data/filament.db`.
- Default dictionaries (brands, materials, colors) are seeded.
- **The first registered user automatically becomes an administrator.**

---

## 🔄 Upgrading

```bash
cd /opt/git/filament
git pull
docker compose up -d --build
```

Schema migrations run automatically on startup via `_safe_alter()` — no manual migration steps needed. Your data in `./data/` is preserved across rebuilds.

---

## 💾 Backups

### Automatic (recommended)

Use the built-in **Settings → Export** function to download a compressed `.tar.gz` backup of the entire application state, including uploaded project files stored directly in the archive.

Restore via **Settings → Import** (accepts `.tar.gz`, older `.json.gz`, and legacy `.json` formats).

### Manual

Simply back up the `./data/` directory:

```bash
cp -r /opt/git/filament/data /path/to/backup/
```

---

## 🧪 Running Tests

```bash
# Inside the project directory (or from the container)
pip install -r requirements.txt
python -m pytest tests/ -v
```

Tests cover: authentication flows, Bambu sync idempotency, stock deduction logic, backup/restore integrity, SSRF protection, calculator, statistics routes, waste record CRUD, printer maintenance CRUD and ICS export, `_clean_title` helper, and thumbnail MIME-type caching (S3 binary/octet-stream fallback).

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
- Fully self-hosted static assets (no CDN dependencies)
- Bilingual UI (CS/EN)

### 🔮 Potential Future Work
- OctoPrint integration
- Filament spool RFID/NFC pairing
- Public project sharing / client portal
- REST API for third-party integrations

---

## 📄 License

Private project — see repository settings for access and licensing information.

---

## 📚 Further Reading

- [`.github/copilot-instructions.md`](.github/copilot-instructions.md) — Technical manual for AI assistants and developers
- [`CHANGELOG.md`](CHANGELOG.md) — Detailed version history (Keep a Changelog format)
