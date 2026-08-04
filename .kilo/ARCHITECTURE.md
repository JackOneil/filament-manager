# Filament Manager — Architecture & Rules (Single Source of Truth)

> **Canonical architecture documentation.** All agents and developers **MUST** read this file first.
> Other documentation files (`AGENTS.md`, `.kilo/agent/filament-agent.md`, `README.md`) reference this document as the authoritative source.

---

## 1. Architecture Overview

**Filament Manager** is a self-hosted web application for managing 3D printer filament inventory, client print projects, and printer integrations (Bambu Lab Cloud, PrusaLink).

| Layer            | Technology                                               |
| ---------------- | -------------------------------------------------------- |
| Backend          | Python 3.11, Flask 3.0, Gunicorn (1 worker, 4 threads)  |
| Database         | SQLite (default) or PostgreSQL via `DATABASE_URL` env var |
| Templates        | Jinja2 (server-side rendering)                           |
| Reactive UI      | Alpine.js 3.x (local static bundle from npm)            |
| Styling          | TailwindCSS (local static bundle from npm)              |
| Charts           | Chart.js (local static bundle from npm)                 |
| 3D Preview       | Online3DViewer (local static bundle from npm)           |
| Icons            | FontAwesome (local static bundle from npm)              |
| Security         | Flask-WTF (CSRF), cryptography (Fernet), scrypt hashing  |
| Auth             | Session-based multi-user (roles: `admin`, `user`)        |
| Infrastructure   | Docker & Docker Compose, PWA (Service Worker + manifest) |

---

## 2. Project File Structure

The project uses a **modular Flask app factory pattern with Flask Blueprints**. Each module inside the `routes/` directory defines its own Blueprint. To maintain backward compatibility with legacy templates and `url_for("endpoint")` usage, a custom `BuildError` fallback handler is registered in `app.py`. If a global endpoint lookup fails, the fallback handler automatically resolves it to the correct blueprint-prefixed endpoint (e.g., `inventory.index`).

```
app.py                  # Entry point: create_app(), background workers, dialect detection
database.py             # Shared db = SQLAlchemy() instance + dialect detection + engine options
migrations.py           # Database migrations: run_migrations(), _safe_alter() — dialect-aware
models.py               # All ORM models (~35 tables): Brand, Color, Material, Filament,
                        #   MovementHistory, AppSetting, PrintHistory, Project, ProjectFile,
                        #   ProjectLink, ProjectFilament, ProjectQuote, ProjectComment, ProjectTodo,
                        #   ProjectPrintItem, ProjectTemplate, ProjectCommentReaction,
                        #   ModelCategory, ModelComment, UserSession,
                        #   StorageShelf, StoragePlacement, BambuPrinter, BambuPrintJob,
                        #   BambuJobMaterial, PrusaPrinter, PrusaPrintJob, User, UserInvite,
                        #   Notification, AuditLog, PrinterMaintenance, WasteRecord, WasteFile,
                        #   FilamentUndoLog
                        #   MovementHistory links to both BambuPrintJob and PrusaPrintJob
auth.py                 # Multi-user auth, RBAC, session management, invite system
messages.py             # i18n translations (cs + en), 1765+ keys per language
utils/                   # Shared helpers package (was utils.py in 1.105.x and earlier)
  __init__.py            # re-exports: utc_now(), translate(), get_settings(), log_movement(),
                        #   render_markdown(), escape_like(), encrypt/decrypt_token(),
                        #   stock status logic, action center builder
  markdown.py            # Standalone Markdown → HTML renderer
  breadcrumbs.py         # Translated, entity-aware breadcrumbs for the application shell
time_utils.py           # Custom UtcDateTime SQLAlchemy type for timezone-aware datetimes

static/
  css/
    app.css              # Core design tokens, dashboard primitives (≈1200 lines)
    skeleton.css         # Skeleton shimmer loaders for AJAX
    enhancements.css     # v1.119.0+ — theme tokens for charts, responsive table
                        #   cards, sparkline SVG, heatmap grid, micro-interaction
                        #   keyframes (stagger, bounce, ripple, slide-up, heart-pop)
  js/
    app-shell.js         # Global Alpine store, command palette, CSRF auto-inject,
                        #   showToast (now uses enh-slide-up), notification bell
    dashboard.js         # Shared widget layout manager (Overview / Projects / Stats)
    mobile-ux.js         # Pull-to-refresh, swipe gestures, collapsable topbar
    enhancements.js      # v1.119.0+ — window.enh API: registerChart/retheme,
                        #   animateCounter, initSparklines, initHeatmaps, ripple
                         #   effect, mobile long-press row actions, theme watcher
    modal.js              # Shared accessible plain-DOM modal manager
    ajax.js               # Shared AJAX response/error/retry UI helper
    help.js               # Interactive help system (HELP_SECTIONS — Rule 30)
    tour.js               # Guided tour / first-run wizard
    inventory.js          # Inventory page helpers (extracted from index.html)
    bambu-filter.js       # Bambu jobs filter pills
    markdown-editor.js    # Markdown editor for comments/descriptions
    o3dv.min.js           # Online3DViewer bundle (npm build output, also copied by Dockerfile)
routes/
  __init__.py           # register_all(app) — calls all register() functions
  inventory.py          # /, /filaments, /filament/<id>, /add, /edit, /use, /delete, bulk operations
  inventory_helpers.py  # Inventory helpers (query builders, stats, undo)
  api.py                # /api/filaments-list (AJAX endpoint for filtering/sorting)
  calculator.py         # /calculator, /calculator/history/<id>/delete, quote saving
  history.py            # /history, /clear_history
  projects.py           # /projects, /projects/create, /projects/<id>/*, comments, file upload,
                        #   link management, filament planning, status workflow
  projects_helpers.py   # Project helpers (job feed, notifications, files)
  bambu.py              # /bambu, /bambu/sync, /bambu/job/<id>/*, Bambu Cloud API integration
  bambu_helpers.py      # Bambu helpers (sync engine, thumbnails, mapping)
  prusa.py              # /prusa, /prusa/printer/<id>/*, /prusa/job/<id>/*, PrusaLink local API
  maintenance.py        # /maintenance, /maintenance/<id>/* — predictive due dates, SOP templates
  stats.py              # /stats — statistics dashboard (charts, forecast, stock health, color palette)
  storage.py            # /storage, /storage/shelf/*, /storage/slot/* — physical shelf management
  settings.py           # /settings — app config + dictionaries + integrations
  backup.py             # /export, /import — full database backup and restore
  backup_helpers.py     # Backup helpers (export/import serialization)
  waste.py              # Waste/scrap tracking with photos and failure reasons
  models.py             # Central 3D model browser, details, timeline, and thumbnails
  model_renderer.py     # STL → PNG thumbnail rendering (pure-Python 3D math + Pillow),
                        #   used by the auto-thumbnail background worker and upload handler
  auth.py               # Auth routes (login, register, users)
  pwa.py                # /manifest.json, /sw.js — Progressive Web App support
templates/
  base.html             # Shared layout (nav, toast, Alpine, local Tailwind/CSS assets, CSRF injection)
  overview.html         # Admin overview (Action Center, live printers, lowest stock, 9-widget dashboard)
  overview_user.html    # Regular user overview (own projects summary)
  index.html            # Filament inventory — admin (Alpine.js inventoryApp(), filters, bulk ops)
  index_user.html       # Filament inventory — user (read-only, paginated)
  stats.html            # Statistics dashboard — Chart.js, 6 draggable sections (see rule 16)
  storage.html          # Visual shelf grid map
  project_detail.html   # Tabbed workspace hosting project detail partial templates
  projects_index.html   # Kanban board + table
  bambu.html            # Bambu Cloud job list with filter pills
  prusa.html            # PrusaLink job list with filter pills
  settings.html         # Full settings + dictionaries + integrations
  _projects_layout.html # Kanban/table/calendar partial (Rule 31 DOMParser targets)
  _project_overview.html, _project_todos.html, _project_activity.html  # Project detail tab partials
  _models_cards.html, _models_rows.html, _bambu_job_cards.html,
    _live_printers_partial.html, _waste_records.html, _users_table.html,
    _filament_cards.html, _filament_list_rows.html, _filament_compact.html,
    _filament_context_menu.html, _skeleton_cards.html, _skeleton_rows.html,
    _toast_undo.html      # AJAX-targeted partials (56 templates total in templates/)
tests/                   # ~35 test modules (pytest + pytest-xdist, run with -n auto)
  test_auth.py, test_bambu.py, test_calculator.py, test_markdown.py, test_projects.py,
  test_refactors.py, test_settings.py, test_stats.py, test_utils.py,
  test_inventory.py, test_models.py, test_waste.py, test_maintenance.py
                        # Core per-module suites
  test_settings_integration.py, test_inventory_extended.py, test_calculator_extended.py,
    test_projects_extended.py, test_stats_extended.py, test_utils_extended.py,
    test_undo_system.py, test_bambu_extended.py, test_prusa_extended.py,
    test_backup_extended.py, test_models_core.py, test_security.py,
    test_waste_extended.py, test_performance.py, test_storage_history_pwa.py
                        # Extended coverage (v1.108.0+, ~440 new tests)
  test_ui_v119.py, test_ui_improvements.py, test_alpine_expressions.py,
    test_breadcrumbs.py, test_model_renderer.py, test_e2e_regressions.py,
    test_review_fixes.py  # UI/regression suites (v1.119.0–v1.121.0)
data/                   # Runtime data (gitignored)
  filament.db           # SQLite database
  uploads/              # Uploaded project files
  backup/               # Scheduled backup archives
```

---

## 3. Data Flow

### 3.1 HTTP Request Lifecycle

```
Browser
   │
   ▼
Gunicorn (1 worker, 4 threads)
   │
   ▼
Flask App (app.py → create_app())
   │
   ├── @app.before_request → auth.ensure_endpoint_access()
   │       ├── Session lookup → get_current_user()
   │       ├── Endpoint → Section mapping (auth.SECTION_BY_ENDPOINT)
   │       └── Role check (admin = full RW, user = read + own projects)
   │
   ├── @app.context_processor → inject_globals()
   │       ├── t() translator, currency, theme, app_version
   │       ├── nav_bambu_enabled, nav_prusa_enabled
   │       └── current_user, auth helpers
   │
   ├── Route handler (routes/*.py)
   │       ├── DB query via Flask-SQLAlchemy ORM
   │       ├── Business logic (utils.py helpers)
   │       └── render_template() / redirect() / JSON response
   │
   └── @app.after_request → add_security_headers()
```

### 3.2 AJAX Flow (Inventory — simple partial swap)

```
Alpine.js inventoryApp() → fetchContent()
   │
   ▼
GET /api/filaments-list?brand=X&sort_by=Y&view=card
   │
   ▼
routes/api.py → returns HTML partial (_filament_cards.html / _filament_list_rows.html)
   │
   ▼
Alpine updates wrapper.innerHTML + synchronous classList update
```

### 3.3 AJAX Flow (Projects — targeted DOM update)

For complex pages where the AJAX response contains multiple independently-updatable sections (e.g. Kanban columns, table body, pagination bar, calendar), the old pattern of `wrapper.innerHTML = data.html` causes full DOM destruction — flickering inputs, lost focus, re-created widget instances.

**The fix** uses `DOMParser` to surgically update only dynamic inner containers:

```
User types in search input (stable, not replaced)
   │
   ▼
Alpine $watch → fetchContent() (deduplicated + AbortController)
   │
   ▼
Server returns full _projects_layout.html as JSON {html: "..."}
   │
   ▼
Client parses HTML into off-DOM document via DOMParser
   │
   ├── doc.querySelector('#project-table-body').innerHTML     → wrapper#project-table-body
   ├── doc.querySelector('#kanban-items-*').innerHTML          → wrapper#kanban-items-*
   ├── doc.querySelector('#kanban-pagination-*').outerHTML     → wrapper#kanban-pagination-*
   ├── doc.querySelector('#projects-calendar-items').innerHTML → wrapper#projects-calendar-items
   ├── doc.querySelector('#project-bottom-pagination').outerHTML → wrapper#project-bottom-pagination
   │
   ▼
Widget shells and search inputs remain stable — no flicker
```

**Key patterns:**
- Every dynamic container in the template has a stable `id` attribute
- `AbortController` cancels previous in-flight request on new filter change
- `_fetchPending` boolean guard prevents concurrent fetches
- `DOMParser.parseFromString()` works on an in-memory document, never touches live DOM until extraction
- `.outerHTML` swap preserves the container element (for pagination wrappers); `.innerHTML` swap replaces only contents (for items lists)

`static/js/ajax.js` provides the shared non-2xx handling pattern. A failed
request replaces the affected dynamic container with a translated error state
and a retry button; intentional `AbortError` filter cancellations are not
shown as user-facing errors.

### 3.4 Shared modal behavior

Plain DOM modals use `static/js/modal.js`. Opening a modal sets dialog ARIA
attributes, traps focus, locks the scrollable `<main>` element, and remembers
the previously focused control. Escape and backdrop clicks close the topmost
modal and restore focus. Alpine-owned overlays remain controlled by Alpine.

### 3.5 Background Workers

Four daemon threads start in `create_app()`:

| Worker               | Interval                  | Function                                      |
| -------------------- | ------------------------- | --------------------------------------------- |
| `bambu-sync-worker`  | 60s (backoff → max 3600s) | `routes.bambu.do_sync()` — Bambu Cloud API    |
| `prusa-sync-worker`  | 60s (backoff → max 900s)  | `routes.prusa.do_poll()` — PrusaLink local API|
| `auto-backup-worker` | 60s (check only)           | Scheduled backup to `data/backup/` directory  |
| `model-thumbnail-worker` | 60s (check only) | Background regeneration of missing model thumbnails |

### 3.6 DB Schema Migration Strategy

- **No Alembic.** Migrations are handled via `_safe_alter()` in `migrations.py`.
- Every new column requires a `_safe_alter(app, 'ALTER TABLE ...')` line in `run_migrations()` inside `migrations.py`.
- `duplicate column name` / `already exists` exceptions are silently ignored → safe on reruns.
- `db.create_all()` creates new tables; `_safe_alter()` adds columns to existing ones.
- **PostgreSQL compatibility**: `_safe_alter()` works for both SQLite and PostgreSQL. Column types use `TIMESTAMP` (not `DATETIME`) and `BOOLEAN` for cross-engine compatibility. SQLite-only operations (`PRAGMA`, table recreation) are guarded with dialect checks (`if dialect != 'sqlite': return`). Table names that are PostgreSQL reserved words (e.g. `user`) must be quoted with double quotes in raw SQL.
- **Fresh PostgreSQL deployments**: `db.create_all()` creates all tables from model definitions. The `run_migrations()` function runs `_safe_alter()` calls that fail harmlessly for already-existing columns. `_migrate_nullable_project_id()` and `_migrate_waste_record_fk()` are skipped for PostgreSQL (schema is already correct).

---

## 4. Key Dependencies

| Package            | Version      | Purpose                                                   |
| ------------------ | ------------ | --------------------------------------------------------- |
| `Flask`            | 3.0.2        | Web framework                                             |
| `Flask-SQLAlchemy` | 3.1.1        | ORM layer over SQLite / PostgreSQL              |
| `psycopg2-binary`   | ≥2.9         | PostgreSQL driver (optional — only when using PG) |
| `Flask-WTF`        | 1.2.1        | CSRF protection (auto-injected into forms)                |
| `Werkzeug`         | ≥3.0.6, <4   | WSGI utilities, password hashing, ProxyFix                |
| `gunicorn`         | 21.2.0       | Production WSGI server                                    |
| `requests`         | ≥2.31, <3    | HTTP client for Bambu Cloud, PrusaLink, link previews     |
| `beautifulsoup4`   | ≥4.12, <5    | HTML parsing for OpenGraph/link preview metadata          |
| `cryptography`     | ≥42, <46     | Fernet encryption (Bambu token, Prusa API key at rest)    |
| `Flask-Compress`   | 1.14         | Response compression (gzip/brotli)                       |
| `Pillow`           | ≥10, <12     | STL thumbnail rendering (routes/model_renderer.py)        |
| `pytest` / `pytest-xdist` | ≥8 / ≥3 | Dev/test: parallel test execution (`-n auto`)            |

### Local Frontend Assets (Docker build)

Frontend assets are generated during `docker build` from local npm dependencies in `package.json` and copied into `static/` for runtime serving:

| Library           | Purpose                                   |
| ----------------- | ----------------------------------------- |
| TailwindCSS       | Utility-first CSS framework               |
| Alpine.js 3.x     | Lightweight reactive JS framework         |
| Chart.js          | Charts on Statistics dashboard            |
| FontAwesome       | Icons throughout the application          |
| Online3DViewer    | In-browser STL/3MF preview in projects    |

---

## 5. Security Layer

| Measure                      | Implementation                                          |
| ---------------------------- | ------------------------------------------------------- |
| CSRF                         | Flask-WTF `CSRFProtect`, auto-injected JS snippet       |
| Session hardening            | `HttpOnly`, `SameSite=Lax`, rotation on login/logout    |
| Password hashing             | `scrypt` (Werkzeug)                                     |
| Token encryption             | Fernet (`FERNET_KEY` env var) for Bambu + Prusa secrets |
| SSRF protection              | `is_safe_external_url()` in `utils/__init__.py` — applied to link previews, project link addition, link metadata fetch, and Bambu cover image caching |
| Path traversal               | Upload validation + resolved-path check                 |
| Security headers             | X-Content-Type-Options, X-Frame-Options (SAMEORIGIN), X-XSS-Protection, CSP, HSTS |
| Open redirect prevention     | `is_safe_redirect_target()` for `?next=` parameter      |
| SQLite configuration         | WAL mode, synchronous=NORMAL, `connect_args={'timeout': 30}` |

---

## 6. Development Rules

When modifying this project, always follow these rules:

### Rule 1 — Translation (i18n)
- Never hardcode text inside Jinja2 templates. Always use `{{ t("key") }}`.
- Add new key/value pairs to **both** `cs` and `en` dictionaries in `messages.py`.

### Rule 2 — Database Schema
- Models live in `models.py`. When adding a new column, also add a `_safe_alter()` call in `migrations.py`'s `run_migrations()`:
  ```python
  _safe_alter(app, "ALTER TABLE tablename ADD COLUMN column_name TYPE DEFAULT value")
  ```
- When adding/removing/restructuring any table or column, also update the backup schema (see rule 15).

### Rule 3 — Routes / Modularization
- **Use Flask Blueprints for routing.** Each module in `routes/*.py` defines and registers its own Blueprint (e.g., `routes/inventory.py` defines `bp = Blueprint('inventory', __name__)` and registers routes using `@bp.route`).
- All blueprints are registered in `routes/__init__.py` inside `register_all(app)`.
- To avoid breaking legacy templates, **the app registers a custom `url_for` build error handler** in `app.py`. When a template calls `url_for("route_name")` without a blueprint prefix (e.g., `url_for("index")` instead of `url_for("inventory.index")`), the handler automatically resolves it to the correct blueprint-prefixed endpoint.

### Rule 4 — Authentication & Authorization
- The project has session-based multi-user auth. New endpoints must be mapped in `auth.SECTION_BY_ENDPOINT` to one of the sections defined in `auth.py`: `overview`, `filaments`, `projects`, `history`, `storage`, `calculator`, `printers`, `stats`, `settings`, `users`, `notifications`. Feature modules reuse these sections: maintenance endpoints → `printers`, model endpoints → `projects`, waste endpoints → `filaments`. Endpoints mapped to `notifications` (account, notifications, theme toggle) are auto-allowed for every logged-in user.
- Write operations require `_require_inventory_admin()` or `require_admin` decorator.
- Project routes must respect ownership for non-admin users.

### Rule 5 — Frontend State (Alpine.js)
- Inventory page state (filters, sort, view mode) is managed by `inventoryApp()` in `index.html`.
- Use `x-data`, `x-model`, `x-on:click`, `x-show`, `:class` directives for reactive UI.
- The Alpine instance is exposed globally via `window.__inv = $data` so AJAX-reloaded partials can call `window.__inv.toggleSort("field")`.
- Modal helpers (`openUseFilamentModal`, etc.) remain as plain global JS functions.

### Rule 6 — Alpine.js AJAX + classList Timing
- Alpine 3 schedules reactive DOM updates as a `queueMicrotask`. When `fetchContent()` runs `await fetch(...)`, the microtask ordering is not guaranteed.
- **Always update `wrapper.classList` synchronously before setting `wrapper.innerHTML`**.

### Rule 7 — Fulltext Filter Dropdown Pattern
- Inventory filters use custom Alpine.js fulltext search dropdowns, NOT native `<select>`.
- Each filter has: `<field>Q` (search text), `<field>Open` (dropdown state), `filtered<Field>s` (computed), `select<Field>(id, name)`.
- `resetFilters()` must clear **both** the ID and the text for all filters.

### Rule 8 — Jinja2 Variable Scoping
- Variables set with `{% set %}` inside a `{% for %}` loop are scoped to that iteration.
- When card and list views both need computed variables, define them at the start of **each** loop independently.

### Rule 9 — HTML Tag Closing in Jinja2 Loops
- Every `<div>` opened in a `{% for %}` loop **must** be closed within the same iteration. Missing closings cause catastrophic DOM nesting.
- **Count opening and closing `<div>` tags** for every loop body.

### Rule 10 — Alpine.js `x-cloak`
- Elements using `x-show` that should be hidden before Alpine initializes must also have `x-cloak`.
- The CSS rule `[x-cloak] { display: none !important; }` must be present in `base.html` `<head>` `<style>` tag, BEFORE any external CSS `<link>` tags.

### Rule 11 — CSS / Design
- Do not alter existing CSS classes (spacing, baseline colors) unless explicitly asked.
- Prioritize flexbox and grid for alignment. Preserve `hover:bg-... transition-all` on buttons.

### Rule 12 — Low-Stock Indicators
- Filaments with **0 quantity** or **< 20% remaining weight** show visual warnings:
  - **Card view**: absolute-positioned badge (red `bg-red-600` for out-of-stock, orange `bg-orange-500` for low stock).
  - **List view**: icon badge next to the filament name.
- Define `pct` variable **before** the low-stock check in both server-rendered views and partials.

### Rule 13 — Link Preview Security (SSRF)
- Server-side URL fetches must allow only `http`/`https` and reject localhost, loopback, and private address ranges.
- Redirect targets must be re-validated before following.

### Rule 14 — Project Uploads
- Validate against an allowlist of image + 3D printing file extensions.
- Stored filenames must include a unique identifier (no overwrites).

### Rule 15 — Backup Schema (Export / Import)

The `/export` and `/import` functions in `routes/backup.py` must cover the **entire persistent application state**:

| Category             | Tables / Data                                                          |
|----------------------|------------------------------------------------------------------------|
| Enumerations         | `Brand` (+ `shop_url`), `Color` (+ `hex_value`), `Material`           |
| Inventory            | `Filament` (all columns, resolved by name)                             |
| Movement history     | `MovementHistory`                                                      |
| App settings         | `AppSetting` (language, currency, theme, energy, sync config, etc.)    |
| Calculator records   | `PrintHistory`                                                         |
| Projects             | `Project` (+ `share_token`), `ProjectFile` (with file content), `ProjectLink`, `ProjectFilament`, `ProjectQuote`, `ProjectComment`, `ProjectTodo`, `ProjectTemplate`, `ProjectCommentReaction` |
| Bambu integration    | `BambuPrinter` (+ `power_draw_watts`), `BambuPrintJob` (+ `raw_payload`), `BambuJobMaterial` |
| Prusa integration    | `PrusaPrinter` (API keys excluded, + `power_draw_watts`), `PrusaPrintJob` (+ `raw_payload`) |
| Storage              | `StorageShelf`, `StoragePlacement`                                     |
| Users & auth         | `User` (+ `last_login_at`), `UserInvite`, `Notification`, `AuditLog`   |
| Undo system          | `FilamentUndoLog` (+ `target_type`, `target_key`)                      |
| Maintenance          | `PrinterMaintenance`                                                   |
| Waste tracking       | `WasteRecord`, `WasteFile`                                             |

- **Any new model or column must be reflected in both export and import in the same commit.**
- **Import safety**: `/import` supports dry-run compatibility checks and conflict mode selection (`skip`, `merge`, `overwrite`).

### Rule 16 — Stats Page Draggable Layout
- The Statistics page has **6 named sections**: `section_overview`, `section_charts_primary`, `section_charts_secondary`, `section_tables`, `section_detail`, `section_colors`.
- Layout is persisted in `localStorage` key `stats_layout_v2`.
- **Row limit display**: use `row.style.display = 'none'` / `''` — **never `row.hidden`** — because Tailwind's `display:flex` overrides the `[hidden]` attribute.
- Color palette sorted by HSL hue via `_hex_to_hsl_sort_key()`.

### Rule 17 — Docker & Deployment
- After modifying backend logic, templates, or translations: `docker compose up -d --build`.
- Code is NOT mounted via volumes — a rebuild is required for changes to take effect.

### Rule 18 — Versioning & Documentation
- Bump `APP_VERSION` in `app.py` when introducing feature additions or structural fixes.
- Record changes in `CHANGELOG.md` under the new version (Keep a Changelog format).
- Update the version tag at the top of `README.md`.
- When adding or significantly modifying major functionality, update `README.md` content as well.

### Rule 19 — Testing
- Security-sensitive helpers require automated regression tests under `tests/`.
- Use `unittest` with `unittest.mock` for HTTP mocking.
- Run: `python -m pytest tests/ -v -n auto` (parallel execution via pytest-xdist)

### Rule 20 — Error Handling
- Use `request.form.get()` with `type=` conversion + `try/except (TypeError, ValueError)`.
- **Never** use `request.form['key']` (causes HTTP 500 on missing input).
- Always `db.session.commit()` after mutations; `db.session.rollback()` in catch blocks.

### Rule 21 — Naming Conventions
- Models: `PascalCase` (SQLAlchemy classes).
- Endpoints: `snake_case` function names.
- Templates: `snake_case.html`, partials prefixed with `_` (e.g. `_filament_cards.html`).
- i18n keys: `snake_case` with namespace prefix (e.g. `bambu_`, `stats_`, `project_`).

### Rule 22 — Dashboard Consistency (Overview, Projects, Statistics)
- All three dashboard pages must expose **identical capabilities**: widget drag-to-reorder, resize handles, row-limit selectors, and inline per-widget hide button.
- Shared dashboard logic lives exclusively in **`static/js/dashboard.js`** (loaded by `base.html`):
  - `createWidgetLayoutManager(config)` — used by Overview and Projects pages.
  - `createCardResizeManager(config)` — used by the Statistics page.
- localStorage keys: `overview_layout_v1`, `projects_layout_v1`, `stats_layout_v2`.

### Rule 23 — Dashboard Mobile Layout (Widget col-span and localStorage)

**`mdGridCols` config parameter** controls mobile layout behaviour in `dashboard.js`:
- `mdGridCols: 1` (default) — `spanClass()` emits only `xl:col-span-N`. When restoring from localStorage, `col-span-*` and `md:col-span-*` are stripped.
- `mdGridCols: 2` — `spanClass()` emits `col-span-1 md:col-span-N xl:col-span-N`.

**Current configuration:**
| Page | Grid container class | `mdGridCols` |
|---|---|---|
| Overview (`overview.html`) | `grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4` | `2` |
| Projects (`projects_index.html`) | `grid grid-cols-1 xl:grid-cols-4` | `1` (default) |

**CSS override as safety net:** For grids that must be single-column on mobile regardless of JS/localStorage, add a scoped `!important` rule:
```html
<style>
@media (max-width: 1279px) {
    #projects-layout > .dashboard-widget {
        grid-column: 1 / -1 !important;
    }
}
</style>
```

### Rule 24 — Time Handling (utc_now)
- Never use `datetime.utcnow()` directly, as it is deprecated and will be removed in Python 3.14.
- Always use the `utc_now()` helper from `utils/__init__.py`.
- For model definitions, `models.py` uses its own internal `_utc_now()` helper to avoid circular imports.

### Rule 25 — Backend Translation (translate)
- Jinja2 templates use the `t("key")` context processor.
- Python code (e.g. background tasks, route handlers) must use `translate("key")` from `utils/__init__.py`.

### Rule 26 — Alpine.js Global Store (appState)
- Shared frontend states (theme, sidebar, mobile menu, command palette) must be stored in `$store.appState` defined in `static/js/app-shell.js`.
- Always reference these in templates via `$store.appState` (e.g., `$store.appState.theme`).

### Rule 27 — Lazy Loading of Heavy JS Libraries
- Heavy third-party JS (Chart.js, Online3DViewer) must not be loaded statically via `<script>` tags in the page header.
- Always use `window.loadScript(src)` async helper defined in `static/js/app-shell.js`.

### Rule 28 — Bambu Project Naming Suggestions
- When creating print projects, clean suggestions from unmapped Bambu print jobs can be provided using the `_clean_title` helper from the Bambu module.

### Rule 29 — Architecture Documentation Updates
- After implementing new features or refactoring, always update:
  - `.kilo/ARCHITECTURE.md` (this file) — if architecture, rules, or patterns changed
  - `.kilo/agent/filament-agent.md` and root `AGENTS.md` (mirrors) — if agent workflow changed
  - `README.md` — if features, project structure, or roadmap changed
  - `.kilo/BACKLOG.md` — if a bug was fixed or a feature delivered (Rule 32)

### Rule 30 — Interactive Help System (`static/js/help.js`)
- Whenever a new page, feature, or endpoint is added, update `HELP_SECTIONS` in `static/js/help.js`:
  - Add the endpoint name to the section's `endpoints[]` array
  - Add a contextual tip in **both** `cs` and `en`
  - New pages need a new section object

### Rule 31 — Targeted AJAX DOM Updates (DOMParser)
- For AJAX-driven auto-filter pages with multiple independently-updatable sections, **never replace the entire wrapper via `innerHTML`**.
- Use `DOMParser.parseFromString(data.html, 'text/html')` to parse server response in off-DOM document, then surgically update only specific containers by `id`.
- Always pair with `AbortController` + deduplication guard (`_fetchPending` boolean).
- Keep widget shells, search inputs, and layout manager instances stable.

### Rule 33 — UI Enhancements Module (`window.enh` + `static/css/enhancements.css`)
- All non-essential visual polish lives in `static/css/enhancements.css` + `static/js/enhancements.js`. Never pollute `app.css` (≈1200 lines) with new utility classes.
- Charts MUST register via `window.enh.registerChart(instance)` after creation so theme switching re-themes them automatically. The `window.enh.palette()` helper returns the current light/dark colour tokens.
- Page-transition / stagger animations use the `[data-animate]` + `[data-stagger="N"]` attribute pattern — pure CSS, no JS animation loops.
- Buttons opt into ripple effect via `data-enh-ripple`. Sparklines via `data-enh-sparkline="1,2,3,..."`. Heatmaps via `data-enh-heatmap='{...JSON...}'`.
- Theme reactivity is driven by a `MutationObserver` on `<html>` class — never set theme colours directly from JS, always read from CSS custom properties.

### Rule 34 — Shared modal and AJAX UX
- Use `window.modal.open()` / `window.modal.close()` for plain DOM dialogs. Do
  not add page-specific focus-trap, Escape, or scroll-lock implementations.
- Use `window.ajaxUi.assertOk()` before parsing AJAX responses and
  `window.ajaxUi.renderError()` for retryable failures. Never show an error for
  an intentional `AbortError`, and preserve targeted DOM updates on Rule 31
  pages.

### Rule 32 — Backlog Tracking (`.kilo/BACKLOG.md`)
- **MANDATORY**: Every time a bug is fixed or a feature is implemented, the `.kilo/BACKLOG.md` file **MUST** be updated.
- When fixing a bug from the backlog:
  1. Change the status column from `**Open**` to `Fixed in vX.Y.Z` (where X.Y.Z is the version being released)
  2. Ensure the description includes `**Fix:**` followed by a summary of what was changed
- When adding a new bug or feature request:
  1. Add a new row with a unique ID (BUG-XXX for bugs, BL-XXX for feature requests)
  2. Set status to `**Open**`
  3. Include file paths and line numbers where applicable
  4. Assign appropriate criticality (🔴 Critical, 🟠 High, 🟡 Medium, 🟢 Low) and effort (XS, S, M, L, XL)
- Update the **Summary Statistics** section at the bottom to reflect the current state
- Add completed items to the **📋 Completed** table with version and date
- This rule applies to ALL implementations — no exceptions. Even small fixes must update the backlog.

---

## 7. Constants / Hard Rules

- App URL: `http://localhost:5050` (container port 5000)
- Test command: `cd /opt/git/filament && source .venv/bin/activate && python -m pytest tests/ -v --tb=short -n auto 2>&1` (parallel execution via pytest-xdist)
- Build command: `cd /opt/git/filament && docker compose up -d --build 2>&1`
- Version file: `app.py` (variable `APP_VERSION`)
- Changelog: `CHANGELOG.md` (Keep a Changelog format); archive at `CHANGELOG-ARCHIVE.md`
- Readme: `README.md` (line 3: `*Current version: **vX.Y.Z***`)
- Backlog: `.kilo/BACKLOG.md`

---

## 8. Post-Implementation Checklist

After every set of feature additions or structural fixes:

1. ✅ Bump `APP_VERSION` in `app.py`
2. ✅ Update `CHANGELOG.md` under the new version section
3. ✅ Update `README.md` version tag
4. ✅ If major functionality added/changed → update `README.md` content
5. ✅ `docker compose up -d --build` — MANDATORY
6. ✅ Verify HTTP 200 on `/login` and all static assets
7. ✅ Launch code quality auditor via `task` tool (mandatory after non-trivial changes)
8. ✅ If DB schema changed → verify `/export` and `/import` updated (rule 15)
9. ✅ If user-facing text added → verify `messages.py` updated in both languages (rule 1)
10. ✅ If routes added/modified → verify `SECTION_BY_ENDPOINT` in `auth.py` (rule 4)
11. ✅ If inventory rendering changed → verify low-stock indicators (rule 12) and `<div>` closings (rule 9)
12. ✅ If external URL fetching added → verify SSRF protection (rule 13)
13. ✅ If file upload added → verify validation and unique naming (rule 14)
14. ✅ If security-sensitive code added → verify tests exist (rule 19)
15. ✅ If Stats page modified → verify compliance with rule 16
16. ✅ If any dashboard page modified → verify compliance with rule 22
17. ✅ Keep this ARCHITECTURE.md up to date with any new rules or patterns
18. ✅ Update all architecture-related documents (rule 29)
19. ✅ **Update `.kilo/BACKLOG.md`** (rule 32) — mark fixed bugs as `Fixed in vX.Y.Z`, add new findings with `**Open**` status, update summary statistics
19. ✅ Document any refactoring in changelog and architecture docs
20. ✅ Update help system if new page/feature/workflow added (rule 30)

**CRITICAL: Docker build is mandatory after ANY code change. Never skip it.**
**CRITICAL: Keep `.kilo/ARCHITECTURE.md` as the canonical source of truth.**
