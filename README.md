# Filament Manager 🧵

*Current version: **v1.55.0***

A modern, self-hosted web application for managing 3D printer filament inventory, print projects, and printer integrations — built for makers, small studios, and print farms.

## ✨ Key Features

### Inventory Management
- **Filament Stock Browser** — Card/list views with progress bars, low-stock indicators, filtering by brand/material/color/tag, sorting, pagination, and saved views at `/filaments`.
- **Filament Detail** — Per-spool timeline, quality log (stringing, adhesion, drying, profiles), min/max stock guardrails, and automatic reorder recommendations.
- **Bulk Operations** — Select multiple filaments and batch-apply spool changes, weight updates, tags, min-stock values, or deletion.
- **Movement History** — Full audit log of every weight change with reasons, timestamps, and linked projects/jobs.
- **Storage Shelf Map** — Visual grid layout of physical shelf positions. Assign spools to named slots, drag-and-drop moves, and stock-level fill indicators.

### Projects & Client Workflow
- **Project Management** — Track 3D print jobs as unified projects with client names, due dates, statuses (NEW → PRINTING → DONE), file attachments, and external links with rich preview cards.
- **Kanban Board** — Overview of all projects by status with paginated columns, due-date calendar strip, and estimate-vs-actual metrics.
- **Print Cost Calculator** — Enter model weight and print time, see exact material + electricity cost. Save quotes to projects with margin and customer pricing, and export them into customized basic, detailed, or fully compliant invoice PDF templates.
- **3D Model Viewer** — Interactive in-browser preview of `.stl` and `.3mf` files attached to projects.

### Multi-User Workspace
- **Role-Based Access** — Administrators have full read/write access; regular users see only permitted sections and their own projects.
- **Self-Registration & Invites** — Users register themselves or receive invite codes with pre-configured role and section permissions.
- **Project Collaboration** — Project ownership, approval workflow (Pending → Approved/Rejected), per-project comments, and in-app notifications.

### Printer Integrations
- **Bambu Lab Cloud** — Sync print jobs from Bambu Cloud API. Assign filaments and projects, deduct stock per-AMS-slot, background auto-sync.
- **PrusaLink** — Poll local Prusa printers via REST API (no cloud required). Automatic job capture, progress tracking, and filament mapping.
- **Live Printer Dashboard** — Overview page shows active print jobs with real-time progress bars, ETA, material swatches, and brand badges.

### Analytics & Operations
- **Statistics Dashboard** — Executive KPI panel, usage/purchase trend charts, stock depletion forecast, reorder recommendations, profitable projects, color palette. Draggable sections with hide/show and per-card row limits.
- **Action Center** — Highlights low-stock alerts, overdue projects, unmapped print jobs, and printer sync issues in one place.
- **Automatic Purchase Recommendations** — Based on 30/90-day real usage, recommends what to order next with spool counts and purchase price.

### Platform
- **Progressive Web App** — Install on desktop or mobile device with offline-capable shell.
- **Dark Mode** — Full dark theme support with per-user persistence.
- **Bilingual** — Complete Czech and English translations (700+ keys).
- **Full Backup / Restore** — Compressed `.tar.gz` export with `manifest.json` plus real uploaded project files stored directly in the archive. Import also supports older `.json.gz` and legacy plain JSON backups.
- **Toast Notifications** — Non-blocking pop-up notifications with auto-dismiss via Alpine.js.
- **Custom Dictionaries** — Pre-seeded brands, materials, and colors. All freely expandable, renamable, and safely deletable.

---

## 🛠️ Tech Stack

| Layer          | Technology                                               |
| -------------- | -------------------------------------------------------- |
| Backend        | Python 3.11, Flask 3.0, Gunicorn                        |
| Database       | SQLite via Flask-SQLAlchemy                              |
| Templates      | Jinja2 (server-side rendering)                           |
| Frontend       | TailwindCSS (CDN), Alpine.js 3.x (CDN)                  |
| Charts         | Chart.js (CDN)                                           |
| 3D Viewer      | Online3DViewer (CDN)                                     |
| Icons          | FontAwesome                                              |
| Security       | Flask-WTF (CSRF), cryptography (Fernet), scrypt hashing  |
| Infrastructure | Docker & Docker Compose                                  |

---

## 📦 Project Structure

```
filament/
├── app.py                  # App factory, DB migrations, background workers
├── database.py             # Shared SQLAlchemy instance
├── models.py               # All ORM models (~20 tables)
├── messages.py             # i18n dictionaries (cs + en)
├── auth.py                 # Multi-user auth, RBAC, sessions
├── utils.py                # Shared helpers (stock logic, encryption, link preview)
│
├── routes/                 # HTTP route modules (no Blueprints)
│   ├── __init__.py         #   Central registration
│   ├── inventory.py        #   Inventory CRUD and overview
│   ├── api.py              #   AJAX filament list endpoint
│   ├── calculator.py       #   Print cost calculator
│   ├── history.py          #   Movement history
│   ├── projects.py         #   Projects CRUD, uploads, comments
│   ├── bambu.py            #   Bambu Lab Cloud integration
│   ├── prusa.py            #   PrusaLink integration
│   ├── stats.py            #   Statistics dashboard
│   ├── storage.py          #   Physical shelf management
│   ├── settings.py         #   App settings, export/import
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

Tests cover: authentication flows, Bambu sync idempotency, stock deduction logic, backup/restore integrity, SSRF protection, calculator, and statistics routes.

---

## 🗺️ Roadmap / Current Status

### ✅ Completed
- Core inventory management with progress tracking and stock alerts
- Multi-user authentication with RBAC and invite system
- Project management with Kanban, files, links, quotes, and comments
- Bambu Lab Cloud integration (auto-sync, per-AMS deduction)
- PrusaLink integration (local network, auto-poll)
- Statistics dashboard with drag-and-drop layout
- Storage shelf visualization
- Full backup/restore system
- PWA support
- CSRF protection and security hardening
- Bilingual UI (CS/EN)

### 🔮 Potential Future Work
- OctoPrint integration
- Multi-printer energy cost tracking
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
