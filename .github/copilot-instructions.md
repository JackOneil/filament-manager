# Filament Manager — AI & Developer Instructions

> Single source of truth for architecture, conventions, data flow, and development rules.
> Always keep this context in mind when working on the project.

---

## 1. Architecture Overview

**Filament Manager** is a self-hosted web application for managing 3D printer filament inventory, client print projects, and printer integrations (Bambu Lab Cloud, PrusaLink).

| Layer            | Technology                                               |
| ---------------- | -------------------------------------------------------- |
| Backend          | Python 3.11, Flask 3.0, Gunicorn (1 worker, 4 threads)  |
| Database         | SQLite via Flask-SQLAlchemy 3.1 (`./data/filament.db`)   |
| Templates        | Jinja2 (server-side rendering)                           |
| Reactive UI      | Alpine.js 3.x (CDN)                                     |
| Styling          | TailwindCSS (CDN)                                        |
| Charts           | Chart.js (CDN)                                           |
| 3D Preview       | Online3DViewer (CDN) for `.stl` and `.3mf`               |
| Icons            | FontAwesome                                              |
| Security         | Flask-WTF (CSRF), cryptography (Fernet), scrypt hashing  |
| Auth             | Session-based multi-user (roles: `admin`, `user`)        |
| Infrastructure   | Docker & Docker Compose, PWA (Service Worker + manifest) |

---

## 2. Project File Structure

The project uses a **modular Flask app factory pattern — no Blueprints**. Routes are registered directly on the `app` object via `register(app)` functions, so `url_for("index")` works in templates without any prefix.

```
app.py                  # Entry point: create_app(), _setup_database(), _safe_alter(), background workers
database.py             # Shared db = SQLAlchemy() instance
models.py               # All ORM models (~23 tables): Brand, Color, Material, Filament,
                        #   MovementHistory, AppSetting, PrintHistory, Project, ProjectFile,
                        #   ProjectLink, ProjectFilament, ProjectQuote, ProjectComment, ProjectTodo,
                        #   StorageShelf, StoragePlacement, BambuPrinter, BambuPrintJob,
                        #   BambuJobMaterial, PrusaPrinter, PrusaPrintJob, User, UserInvite, Notification
auth.py                 # Multi-user auth, RBAC, session management, invite system
messages.py             # i18n translations (cs + en), ~700 keys per language
utils.py                # Shared helpers: get_settings(), utc_now(), translate(), log_movement(),
                        #   encrypt/decrypt_token(), escape_like(), link preview (SSRF-safe),
                        #   stock status logic, action center builder
routes/
  __init__.py           # register_all(app) — calls all register() functions
  inventory.py          # /, /filaments, /filament/<id>, /add, /edit, /use, /delete, bulk operations
  api.py                # /api/filaments-list (AJAX endpoint for filtering/sorting)
  calculator.py         # /calculator, /calculator/history/<id>/delete, quote saving
  history.py            # /history, /clear_history
  projects.py           # /projects, /projects/create, /projects/<id>/*, comments, file upload,
                        #   link management, filament planning, status workflow
  bambu.py              # /bambu, /bambu/sync, /bambu/job/<id>/*, Bambu Cloud API integration
  prusa.py              # /prusa, /prusa/printer/<id>/*, /prusa/job/<id>/*, PrusaLink local API
  stats.py              # /stats — statistics dashboard (charts, forecast, stock health, color palette)
  storage.py            # /storage, /storage/shelf/*, /storage/slot/* — physical shelf management
  settings.py           # /settings, /export, /import, /toggle-theme — app config + full backup
  auth.py               # /login, /logout, /register, /activate, /account, /users/* — auth routes
  pwa.py                # /manifest.json, /sw.js — Progressive Web App support
templates/
  base.html             # Shared layout (nav, toast, Alpine, Tailwind CDN, CSRF injection)
  overview.html         # Admin overview (Action Center, live printers)
  overview_user.html    # Regular user overview (own projects summary)
  index.html            # Filament inventory — admin (Alpine.js inventoryApp(), filters, bulk ops)
  index_user.html       # Filament inventory — user (read-only, paginated)
  stats.html            # Statistics dashboard — Chart.js, 6 draggable sections (see rule 16)
  storage.html          # Visual shelf grid map
  project_detail.html   # Tabbed workspace (overview, materials, files, jobs)
  projects_index.html   # Kanban board + table
  bambu.html            # Bambu Cloud job list with filter pills
  prusa.html            # PrusaLink job list with filter pills
  settings.html         # Full settings + dictionaries + integrations
  ...                   # Auth pages, forms, partials (_filament_cards.html, _filament_list_rows.html)
tests/
  test_auth.py          # Auth flows, sessions, RBAC
  test_bambu.py         # Bambu sync, deduction, idempotency
  test_calculator.py    # Calculator, quote creation
  test_projects.py      # Project CRUD, uploads, link previews
  test_settings.py      # Export/import, full backup restore
  test_stats.py         # Statistics route
  test_utils.py         # URL validation, SSRF protection
data/                   # Runtime data (gitignored)
  filament.db           # SQLite database
  uploads/              # Uploaded project files
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

### 3.2 AJAX Flow (Inventory)

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

### 3.3 Background Workers

Two daemon threads start in `create_app()`:

| Worker               | Interval                  | Function                                      |
| -------------------- | ------------------------- | --------------------------------------------- |
| `bambu-sync-worker`  | 60s (backoff → max 3600s) | `routes.bambu.do_sync()` — Bambu Cloud API    |
| `prusa-sync-worker`  | 60s (backoff → max 900s)  | `routes.prusa.do_poll()` — PrusaLink local API|

### 3.4 DB Schema Migration Strategy

- **No Alembic.** Migrations are handled via `_safe_alter()` in `app.py`.
- Every new column requires a `_safe_alter(app, 'ALTER TABLE ...')` line in `_setup_database()`.
- `duplicate column name` exceptions are silently ignored → safe on reruns.
- `db.create_all()` creates new tables; `_safe_alter()` adds columns to existing ones.

---

## 4. Key Dependencies

| Package            | Version      | Purpose                                                   |
| ------------------ | ------------ | --------------------------------------------------------- |
| `Flask`            | 3.0.2        | Web framework                                             |
| `Flask-SQLAlchemy` | 3.1.1        | ORM layer over SQLite                                     |
| `Flask-WTF`        | 1.2.1        | CSRF protection (auto-injected into forms)                |
| `Werkzeug`         | 3.0.1        | WSGI utilities, password hashing, ProxyFix                |
| `gunicorn`         | 21.2.0       | Production WSGI server                                    |
| `requests`         | ≥2.31, <3    | HTTP client for Bambu Cloud, PrusaLink, link previews     |
| `beautifulsoup4`   | ≥4.12, <5    | HTML parsing for OpenGraph/link preview metadata           |
| `cryptography`     | ≥42          | Fernet encryption (Bambu token, Prusa API key at rest)    |

### CDN Dependencies (Frontend)

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
| SSRF protection              | `is_safe_external_url()` in `utils.py`                  |
| Path traversal               | Upload validation + resolved-path check                 |
| Security headers             | X-Content-Type-Options, X-Frame-Options, HSTS           |
| Open redirect prevention     | `is_safe_redirect_target()` for `?next=` parameter      |
| SQLite timeout               | `connect_args={'timeout': 30}`                          |

---

## 6. Development Rules

When modifying this project, always follow these rules:

### Rule 1 — Translation (i18n)
- Never hardcode text inside Jinja2 templates. Always use `{{ t("key") }}`.
- Add new key/value pairs to **both** `cs` and `en` dictionaries in `messages.py`.

### Rule 2 — Database Schema
- Models live in `models.py`. When adding a new column, also add a `_safe_alter()` call in `app.py`:
  ```python
  _safe_alter(app, "ALTER TABLE tablename ADD COLUMN column_name TYPE DEFAULT value")
  ```
- When adding/removing/restructuring any table or column, also update the backup schema (see rule 15).

### Rule 3 — Routes / Modularization
- **Never use Flask Blueprints.** They require `url_for("blueprint.route")` prefixes and have caused breakage.
- Add routes inside the appropriate `routes/*.py` `register(app)` function. For new features, create a new file and register it in `routes/__init__.py`.
- `url_for("index")`, `url_for("add")`, etc. work as-is in templates — no prefix needed.

### Rule 4 — Authentication & Authorization
- The project has session-based multi-user auth. New endpoints must be mapped in `auth.SECTION_BY_ENDPOINT` to the correct section: `overview`, `filaments`, `projects`, `history`, `storage`, `calculator`, `printers`, `stats`, `settings`, `users`.
- Write operations require `_require_inventory_admin()` or `require_admin` decorator.
- Project routes must respect ownership for non-admin users.

### Rule 5 — Frontend State (Alpine.js)
- Inventory page state (filters, sort, view mode) is managed by `inventoryApp()` in `index.html`.
- Use `x-data`, `x-model`, `x-on:click`, `x-show`, `:class` directives for reactive UI.
- The Alpine instance is exposed globally via `window.__inv = $data` so AJAX-reloaded partials can call `window.__inv.toggleSort("field")`.
- Modal helpers (`openUseFilamentModal`, etc.) remain as plain global JS functions (invoked from AJAX-loaded HTML).

### Rule 6 — Alpine.js AJAX + classList Timing
- Alpine 3 schedules reactive DOM updates as a `queueMicrotask`. When `fetchContent()` runs `await fetch(...)`, the microtask ordering is not guaranteed.
- **Always update `wrapper.classList` synchronously before setting `wrapper.innerHTML`**, then Alpine's `:class` binding stays idempotent:
  ```js
  if (this.viewMode === 'list') {
      wrapper.classList.remove('grid', 'grid-cols-1', 'md:grid-cols-2', 'lg:grid-cols-3', 'gap-6');
      wrapper.classList.add('space-y-0');
  } else { ... }
  wrapper.innerHTML = html;
  ```

### Rule 7 — Fulltext Filter Dropdown Pattern
- Inventory filters use custom Alpine.js fulltext search dropdowns, NOT native `<select>`.
- Option data is embedded via Jinja2 at render time. Use `|tojson` for string values.
- Each filter has: `<field>Q` (search text), `<field>Open` (dropdown state), `filtered<Field>s` (computed), `select<Field>(id, name)`.
- `resetFilters()` must clear **both** the ID and the text for all filters.
- Color filter includes a `hex` field for rendering colored swatches.

### Rule 8 — Jinja2 Variable Scoping
- Variables set with `{% set %}` inside a `{% for %}` loop are scoped to that iteration.
- When card and list views both need computed variables (e.g. `capacity_all`, `pct`), define them at the start of **each** loop independently.
- Partials (`_filament_cards.html`, `_filament_list_rows.html`) handle their own variable definitions.

### Rule 9 — HTML Tag Closing in Jinja2 Loops
- Every `<div>` opened in a `{% for %}` loop **must** be closed within the same iteration. Missing closings cause catastrophic DOM nesting — items overlap and modals break.
- **Count opening and closing `<div>` tags** for every loop body.

### Rule 10 — Alpine.js `x-cloak`
- Elements using `x-show` that should be hidden before Alpine initializes must also have `x-cloak`.
- The CSS rule `[x-cloak] { display: none !important; }` must be present in `base.html`.

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
- Prefer OpenGraph → Twitter Cards → standard HTML metadata. Resolve relative image URLs to absolute.

### Rule 14 — Project Uploads
- Validate against an allowlist of image + 3D printing file extensions.
- Stored filenames must include a unique identifier (no overwrites).
- Image previews use inline-serving route; downloads use `as_attachment=True`.

### Rule 15 — Backup Schema (Export / Import)

The `/export` and `/import` functions in `routes/settings.py` must cover the **entire persistent application state**:

| Category             | Tables / Data                                                          |
|----------------------|------------------------------------------------------------------------|
| Enumerations         | `Brand` (+ `shop_url`), `Color` (+ `hex_value`), `Material`           |
| Inventory            | `Filament` (all columns, resolved by name)                             |
| Movement history     | `MovementHistory`                                                      |
| App settings         | `AppSetting` (language, currency, theme, energy, sync config, etc.)    |
| Calculator records   | `PrintHistory`                                                         |
| Projects             | `Project`, `ProjectFile` (with file content), `ProjectLink`, `ProjectFilament`, `ProjectQuote`, `ProjectComment` |
| Bambu integration    | `BambuPrinter`, `BambuPrintJob`, `BambuJobMaterial`                    |
| Prusa integration    | `PrusaPrinter` (API keys excluded), `PrusaPrintJob`                    |
| Storage              | `StorageShelf`, `StoragePlacement`                                     |
| Users & auth         | `User`, `UserInvite`, `Notification`                                   |

- **Referential integrity**: resolve FKs by name/serial before inserting dependent rows. Commit in order: enumerations → filaments → history → projects → integrations → users.
- **Idempotency**: "skip if already exists" by natural key.
- **Any new model or column must be reflected in both export and import in the same commit.**

### Rule 16 — Stats Page Draggable Layout
- The Statistics page has **6 named sections**, each a `<div class="stats-section" data-section-id="...">`:
  `section_overview`, `section_charts_primary`, `section_charts_secondary`, `section_tables`, `section_detail`, `section_colors`.
- Layout is persisted in `localStorage` key `stats_layout_v2` as `{order:[...], hidden:[...], limits:{cardId: number|'all'}}`.
- **Edit mode**: toggled by `toggleEditMode()`, adds `edit-mode` class to `#stats-page`.
- **Row limit display**: use `row.style.display = 'none'` / `''` — **never `row.hidden`** — because Tailwind's `display:flex` overrides the `[hidden]` attribute.
- Color palette sorted by HSL hue via `_hex_to_hsl_sort_key()`. Do **not** revert to alphabetical.
- Chart.js instances are created in `stats.html` `<script>` block with embedded `chart_data` JSON. No AJAX re-fetch.

### Rule 17 — Docker & Deployment
- After modifying backend logic, templates, or translations: `docker compose up -d --build`.
- Code is NOT mounted via volumes — a rebuild is required for changes to take effect.
- Application accessible at `http://localhost:5050` (container port `5000`).

### Rule 18 — Versioning & Documentation
- Bump `APP_VERSION` in `app.py` when introducing feature additions or structural fixes.
- Record changes in `CHANGELOG.md` under the new version (Keep a Changelog format).
- Update the version tag at the top of `README.md`.

### Rule 19 — Testing
- Security-sensitive helpers require automated regression tests under `tests/`.
- Use `unittest` with `unittest.mock` for HTTP mocking.
- Run: `python -m pytest tests/ -v`

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
- Shared dashboard logic lives exclusively in **`static/js/dashboard.js`** (loaded by `base.html`). Never duplicate this code across templates.
  - `createWidgetLayoutManager(config)` — used by Overview and Projects pages (flat widget grids).
  - `createCardResizeManager(config)` — used by the Statistics page (card-level resize + row limits).
- When adding or changing dashboard behaviour, update `dashboard.js` once. The change automatically applies to all three pages.
- `createWidgetLayoutManager` config **must** always include `hideBtnTitle` and `limitAllText` (translated via `t()` in the template).
- The inline hide button (`.widget-hide-btn`) is injected dynamically by `applyLayout()` into each widget's `.dashboard-edit-bar`. Use the visibility panel (`visibilityPanelId`) to allow the user to restore hidden widgets.
- localStorage keys: `overview_layout_v1`, `projects_layout_v1`, `stats_layout_v2`.

### Rule 23 — Dashboard Mobile Layout (Widget col-span and localStorage)

**Critical gotcha:** `createWidgetLayoutManager` saves widget sizes as CSS class strings (e.g. `col-span-1 md:col-span-2 xl:col-span-3`) in localStorage. When the user resizes a widget on desktop, these classes are persisted and re-applied on every page load. If the grid container does **not** have `md:grid-cols-N` defined, applying `md:col-span-*` creates **implicit grid columns** — widgets end up side-by-side on tablet/mobile even though the grid appears to be single-column.

**`mdGridCols` config parameter** controls this behaviour in `dashboard.js`:
- `mdGridCols: 1` (default) — `spanClass()` emits only `xl:col-span-N`. When restoring from localStorage, `col-span-*` and `md:col-span-*` are stripped. Grid stays 1-column below xl.
- `mdGridCols: 2` — `spanClass()` emits `col-span-1 md:col-span-N xl:col-span-N`. Use this when the grid container has `md:grid-cols-2`.

**Current configuration:**
| Page | Grid container class | `mdGridCols` |
|---|---|---|
| Overview (`overview.html`) | `grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4` | `2` |
| Projects (`projects_index.html` / `_projects_layout.html`) | `grid grid-cols-1 xl:grid-cols-4` | `1` (default) |

**CSS override as safety net:** For grids that must be single-column on mobile regardless of JS/localStorage, add a scoped `!important` rule in the page template:
```html
<style>
@media (max-width: 1279px) {
    #projects-layout > .dashboard-widget {
        grid-column: 1 / -1 !important;
    }
}
</style>
```
This is already applied to `projects_index.html` and overrides any stale localStorage col-span classes.

**When adding a new dashboard page:**
1. Decide if the grid uses `md:grid-cols-N` — if yes, set `mdGridCols: N` in the `createWidgetLayoutManager` config.
2. If the grid is `grid-cols-1 xl:grid-cols-4` (single column until xl), omit `mdGridCols` (defaults to 1) **and** add the CSS `!important` override above as a belt-and-suspenders safeguard.
3. Full-width widgets (spanning all columns) need the matching `xl:col-span-4` and, if using a 2-col md grid, `md:col-span-2` class in the `<section>` element.

### Rule 24 — Time Handling (utc_now)
- Never use `datetime.utcnow()` directly, as it is deprecated and will be removed in Python 3.14.
- Always use the `utc_now()` helper from `utils.py`.
- For model definitions, `models.py` uses its own internal `_utc_now()` helper to avoid circular imports.
- Any time math or defaulting must rely on timezone-aware UTC representations when possible or naive UTC from `utc_now()` if legacy compatibility requires it.

### Rule 25 — Backend Translation (translate)
- Jinja2 templates use the `t("key")` context processor.
- Python code (e.g. background tasks, route handlers) must use `translate("key")` from `utils.py`.
- Do not hardcode localized strings in Python code (e.g. notifications, flash messages where feasible) if it should adapt to the user's selected language.

---

## 7. Post-Implementation Checklist

After every set of feature additions or structural fixes:

1. ✅ Verify Docker builds successfully
2. ✅ Bump `APP_VERSION` in `app.py` (SemVer: major.minor.patch)
3. ✅ Update `CHANGELOG.md` under the new version section
4. ✅ Update `README.md` version tag
5. ✅ `docker compose up -d --build` → verify HTTP 200
6. ✅ If DB schema changed → verify `/export` and `/import` updated (rule 15)
7. ✅ If user-facing text added → verify `messages.py` updated in both languages (rule 1)
8. ✅ If routes added/modified → verify `SECTION_BY_ENDPOINT` in `auth.py` (rule 4)
9. ✅ If inventory rendering changed → verify low-stock indicators (rule 12) and `<div>` closings (rule 9)
10. ✅ If external URL fetching added → verify SSRF protection (rule 13)
11. ✅ If file upload added → verify validation and unique naming (rule 14)
12. ✅ If security-sensitive code added → verify tests exist (rule 19)
13. ✅ If Stats page modified → verify compliance with rule 16
14. ✅ If any dashboard page (Overview, Projects, Stats) modified → verify compliance with rule 22
15. ✅ Keep this instruction file up to date with any new rules or patterns
