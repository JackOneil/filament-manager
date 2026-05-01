# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.72.1] - 2026-05-02

### Changed
- **Print pieces AJAX** — The +/- increment/decrement buttons in the print items panel no longer trigger a full page reload. Counts and progress bars update instantly via AJAX.
- **Collapsible print items panel** — The "Pieces to print" panel can now be collapsed to show only the aggregate progress bar. The collapsed/expanded state is persisted per-project in `localStorage`.

## [1.72.0] - 2026-05-01

### Added
- **Print pieces tracking** — Projects now support a list of print items (models), each with a target quantity and a printed count. Items can be added, edited, incremented/decremented, and deleted from the project detail overview tab.
- **Pieces progress bar** — Each print item shows a progress bar and percentage. An aggregate bar at the top of the section shows overall pieces completion for the project.
- **Kanban pieces stats** — The projects kanban board now shows a mini progress bar and `N/M pieces printed` indicator on each card when print items exist.
- **Overview pieces stats** — The active projects panel on the main overview page shows a mini pieces progress bar and printed count for each project that has print items defined.
- **Backup support** — `ProjectPrintItem` records are fully covered by the export and import in `routes/backup.py`.
- **i18n** — All new labels added to both `cs` and `en` in `messages.py`.

## [1.71.0] - 2026-04-29

### Added
- **Inventory quick add quantity** — The filament list quick-add action now opens a quantity modal so multiple spools can be added at once.
- **No-refresh quick add** — Adding spools from the inventory list now uses AJAX and refreshes only the filament list content, preserving the current scroll position.

## [1.70.0] - 2026-04-28

### Added
- **Mini consumption chart** — Filament detail page now shows a 6-month bar chart of filament consumption driven by movement history.
- **Operator / Admin UI mode toggle** — Admins can switch to an "Operator" view (read-only, simplified layout) without logging out. An amber indicator badge is shown in the top bar while in operator mode.
- **Onboarding checklist** — A guided setup checklist appears after first installation until dismissed. Checks currency, energy cost, printer connection, and first filament.
- **Settings page tabs** — Settings are now organised into six tabs: General, Printers, Integrations, Company, Data, and Dictionaries.
- **CSV / Excel filament import** — New two-step import wizard at `/filaments/import-csv`. Parses CSV/TSV, shows a preview table, and creates missing brands/materials/colors automatically on confirm.
- **Printer maintenance module** — New `/maintenance` page for logging nozzle changes, calibrations, services, faults, and other events per printer. Supports overdue and due-soon badge indicators.
- **Project file versioning** — Re-uploading a file with the same name to a project automatically creates a new version. The files tab groups all versions under the root file with an expandable history panel.

## [1.69.2] - 2026-04-26

### Fixed
- **Czech glyph rendering** — Added the Plus Jakarta Sans Latin Extended font subset to the self-hosted font bundle. Czech characters such as `ř`, `ě`, `ů`, and `č` now render in the same font family instead of falling back to a visually different system font.

## [1.69.1] - 2026-04-26

### Changed
- **Overview active print timestamps** — Improved readability of the active print start/ETA timestamps by visually separating the date and time (`26.04 · 17:18`) instead of rendering them as one dense string.

## [1.69.0] - 2026-04-26

### Added
- **Admin audit log** — Added persistent `AuditLog` records for successful administrator mutations. Each entry stores user, email/name snapshot, action, endpoint/path, object type/id, IP address, session identifier, user agent, and before/after JSON snapshots with sensitive form fields redacted.
- **Audit log UI** — New `/audit` admin-only page lists audit records with filters for action and object type, full-text search, pagination, and expandable before/after snapshots.

### Changed
- **Modern SQLAlchemy pagination** — All `db.paginate()` calls now receive `Select` statements (`query.statement`) instead of legacy `Query` objects, removing the Flask-SQLAlchemy deprecation warnings during tests.
- **Backup schema** — Full export/import now includes `AuditLog` records and preserves their user references, request metadata, and before/after snapshots.

### Fixed
- **Endpoint authorization map** — Added missing `api_search`, `calculator_project`, and `audit_logs` entries to `SECTION_BY_ENDPOINT` so access control remains explicit for every route.

## [1.68.2] - 2026-04-26

### Changed
- **Inventory page — removed KPI cards** — The four summary cards (*Celkem civek*, *Celkem zbyva*, *Celkova hodnota*, *Nizky stav skladu*) above the filament list have been removed to reduce clutter.
- **Inventory page — collapsible Smart Highlights** — The Smart Highlights and Color Mix panels are now wrapped in a collapsible accordion. The section is collapsed by default; a compact summary bar shows critical/warning/stable badge counts and five colour swatches at a glance. State is persisted in `localStorage['filament.highlightsOpen']`.
- **Inventory page — removed Low Stock section** — The full low-stock filament grid below the main inventory list has been removed.

### Fixed
- **Compact view persistence bug** — When compact view was saved as the active mode in the database, refreshing the page showed list rows with the compact button highlighted instead of actual compact cards. `inventoryApp.init()` now always triggers `fetchContent()` when `viewMode === 'compact'` because the server-side template only renders compact HTML via the AJAX partial, never in the initial full-page render.

## [1.68.1] - 2026-04-26

### Added
- **Bambu per-printer pre-job time** — Each Bambu printer in Settings now has an editable *Pre-job preparation* field (minutes). This value represents the calibration/warmup phase before the print actually starts. The time is stored on the `BambuPrinter` record and is added to the estimated finish time (ETA) shown on the Overview dashboard for running Bambu jobs.

## [1.68.0] - 2026-04-26

### Added
- **Configurable display timezone** — A new *Timezone* selector has been added to the General Settings page. All timestamp displays throughout the app (history, projects, print jobs, notifications, users, calculator) are now converted from UTC to the configured local timezone before rendering. The default is `Europe/Prague`. Data continues to be stored as UTC.
- **Docker timezone** — `TZ: Europe/Prague` added to `docker-compose.yml` so the container OS clock matches Prague local time.
- **`fmt_dt` Jinja2 filter** — A `fmt_dt(fmt)` template filter is registered in `app.py`. It converts a naive-UTC `datetime` to the app timezone and formats it; pure `date` objects are formatted without conversion; `None` returns an empty string.

## [1.67.1] - 2026-04-26

### Fixed
- **Duplicate project status notifications** — `_notify_project_status()` now uses a `seen` set (same pattern as `_notify_project_comment`) so admin users who are also a project owner receive only one notification when the project status changes, not two.
- **Live Printers widget — filament grams & progress bar** — The standalone "Aktuálně tisknoucí zařízení" card on the Overview dashboard now shows:
  - Bambu: per-material gram weights next to each colour swatch; a time-based estimated progress bar and percentage badge computed from `started_at + cost_time`; estimated finish time (ETA).
  - Prusa: filament weight in grams; corrected progress percentage (was rendering 0 % because the stored `0.0–1.0` value was not multiplied by 100).

## [1.67.0] - 2026-04-25

### Added
- **DB indexes** — Added missing indexes on frequently-queried columns: `bambu_print_job.status`, `bambu_print_job.project_id`, `project_filament.project_id`, `project_filament.filament_id`, `prusa_print_job.status`, `prusa_print_job.printer_id`, `movement_history.project_id`. Created via `_safe_alter` so existing databases are migrated automatically on startup.
- **KPI cache** — Added a thread-safe 30-second in-process TTL cache (`_KpiCache`) for `build_action_center()` results (utils.py). The cache is invalidated automatically after every successful POST/PUT/PATCH/DELETE request via a new `after_request` hook in app.py, keeping the overview dashboard responsive without redundant heavy queries on every page load.
- **AbortController + debounce for AJAX inventory filters** — `fetchContent()` now accepts an `AbortController` and cancels any in-flight request before issuing a new one. A new `fetchContentDebounced()` method (300 ms delay) is used by text-input driven filters (tag field) to prevent unnecessary parallel requests during fast typing. Direct interactions (sort toggles, dropdown selections, pagination, quick views) remain immediate.
- **Background worker duplicate guard** — `_start_bambu_sync_worker()` and `_start_prusa_sync_worker()` now call `_acquire_worker_lock()` before starting a thread. The lock uses a PID file in `./data/` to detect and skip duplicate workers when Gunicorn is launched with multiple worker processes. Stale PID files (from crashed processes) are automatically reclaimed.
- **Compact table view** — New third inventory view mode `compact` shows ultra-dense rows (colour swatch, name, stock badge, remaining/capacity, %, inline mini-bar, quick-use and edit icons) for power users managing large inventories. Rendered via new `_filament_compact.html` partial. The view toggle button in the page header gains a third "Compact" option.
- **Sticky filter bar** — The inventory filter panel is now `position: sticky; top: 8px` so filters stay visible while scrolling through a long filament list. Background uses `bg-white/95 backdrop-blur-sm` for a glass-card effect.
- **Quick-view filter buttons** — Three one-click filter pills appear inside the filter panel: *All* (reset), *Low stock* (quantity = 0 or remaining < 20 % of capacity — computed server-side), *Reorder needed* (has `min_stock_grams` set and current remaining is below threshold). Active pill is highlighted; clicking the active button resets to *All*.

### Changed
- **`_safe_alter` index migrations** — Added seven new `CREATE INDEX IF NOT EXISTS` calls in `_setup_database()`. Safe to re-run on existing databases.

## [1.66.0] - 2026-04-25

### Added
- **Activity timeline tab** — Project detail workspace now has a dedicated *Activity* tab showing a chronological timeline of all project events (quotes saved, files uploaded, comments, tasks) with colour-coded icons and timestamps.
- **Sequential invoice numbering** — Quote export auto-assigns a sequential invoice number (`{prefix}-{year}{counter}`) on first access. Invoice prefix and counter are configurable in App Settings and persisted in `app_setting` DB table.
- **Quote export overhaul** — `quote_export.html` rebuilt as fully self-hosted (no CDN), i18n-aware template with company/client data fields, document type selector (invoice, pro forma, detailed, simple) and a footer note field.

### Fixed
- **PWA routes Blueprint violation** — `routes/pwa.py` was incorrectly using a Flask Blueprint. Converted to direct `@app.route` inside `register(app)` per project Rule 3.
- **Deprecated `datetime.utcnow()` in utils.py** — `collect_usage_windows()` was using `_dt.utcnow()`; replaced with `utc_now()` per Rule 24.
- **Deprecated `Query.paginate()` in Bambu / Prusa routes** — Replaced legacy `query.paginate()` calls with `db.paginate(query, ...)` to silence SQLAlchemy 2.x deprecation warnings.

### Changed
- **Backup schema updated** — `routes/backup.py` export and import now include `invoice_prefix`, `invoice_counter` (AppSetting) and `invoice_number` (ProjectQuote) per Rule 15.
- **Activity tab route** — `routes/projects.py` validates `'activity'` as a valid project tab and passes all activity events (previously capped at 15).

## [1.65.0] - 2026-04-25

### Added
- **Notification refactor** — Complete overhaul of the notifications system:
  - **Specific notification kinds** — Changed from generic `kind='project'` to granular `project_new`, `project_status`, `project_comment` kinds for better differentiation.
  - **Kind filter pills** — New filter pills on the notifications page allow filtering by notification type (All / New projects / Status changes / Comments / Info) with per-kind counts.
  - **Delete actions** — Added delete button per notification and a "Delete read" bulk action to clean up the inbox.
  - **Visual redesign** — Each notification kind now has a distinct icon and color scheme (blue for new projects, violet for status changes, amber for comments).
  - **Persistent kind filter** — Pagination, mark-as-read, and delete actions all preserve the active kind filter.
  - **Account page** — Notification preferences now show kind-specific icons and a clear section header.
  - **New i18n keys** — Added 15 new message keys in both `cs` and `en` for kind labels, delete actions, and preferences.

## [1.64.0] - 2026-04-24

### Changed (Performance)
- **Self-hosted frontend assets** — All external CDN dependencies are now bundled locally during the Docker build, eliminating 5–6 external network requests per page load (previously adding ~300–500 ms on first visit even on LAN):
  - **Tailwind CSS** — Replaced Tailwind Play CDN (~400 KB JS runtime that builds CSS in the browser on every load) with a pre-built, minified `tailwind.css` generated by Tailwind CLI v3 during `docker build`. Tailwind scans all templates and JS at build time and emits only the used utility classes (~50–100 KB static CSS).
  - **Alpine.js** — Downloaded from npm (`alpinejs@3.14.x`) and served from `static/js/alpine.min.js`.
  - **FontAwesome 6.4** — Downloaded from npm (`@fortawesome/fontawesome-free@6.4.x`) and served from `static/css/fontawesome.min.css` + `static/webfonts/`. CSS uses relative paths so no URL patching required.
  - **Chart.js** — Downloaded from npm (`chart.js@4.4.x`) and served from `static/js/chart.min.js` (stats page only).
  - **Online3DViewer** — Downloaded from npm (`online-3d-viewer@0.18.0`) and served from `static/js/o3dv.min.js` (project detail page only).
  - **Plus Jakarta Sans font** — Replaced Google Fonts request with a self-hosted variable font (`@fontsource-variable/plus-jakarta-sans`) downloaded during build. Single `.woff2` covers all weights 200–800.
- **Multi-stage Dockerfile** — Added a Node 20 build stage that runs `npm install` + Tailwind CLI. The final Python image stays slim (no Node.js or `node_modules` in the production layer). First `docker build` takes ~60 s longer; subsequent builds are cached.

## [1.63.0] - 2026-04-24

### Added
- **HTML Test Reports** — Configured `pytest` to automatically generate a human-readable HTML summary report (`test_report.html`) when tests are run. This report includes test results, expected vs actual outputs, and detailed traceback information for easier debugging.
- **`utc_now()` centralized helper** — New `utc_now()` function in `utils.py` replaces all deprecated `datetime.utcnow()` calls project-wide (Python 3.14+ compatibility). All 14 model column defaults and 30+ runtime calls across 10 files have been migrated.
- **`translate()` helper** — New Python-side translation helper in `utils.py` for use in route handlers and notification builders where the Jinja2 `t()` context processor is unavailable.
- **Notification i18n keys** — Added 6 new message keys (`notify_project_created_title/body`, `notify_project_status_title/body`, `notify_comment_title/body`) in both `cs` and `en` locales.
- **Model `__repr__()` methods** — Added debugging-friendly `__repr__()` to 11 models: `User`, `UserInvite`, `Notification`, `Brand`, `Color`, `Material`, `Filament`, `MovementHistory`, `Project`, `BambuPrintJob`, `PrusaPrintJob`.

### Changed (Performance)
- **SQLAlchemy Cartesian Product fix** — Replaced `joinedload` with `selectinload` for 1:N relations in `projects_index` to prevent exponential dataset growth during project and kanban list rendering. This reduces the number of hydrated rows per project from hundreds/thousands to just the exact number of related items, solving a 500-700ms loading bottleneck.
- **Request-Level Caching** — The global setting lookup `get_settings()` and the `PrusaPrinter` enablement check now utilize `flask.g` to cache their results per-request. This eliminates dozens of duplicate SQLite queries fired by the Jinja context processor during template rendering.
- **Database Indices** — Added `CREATE INDEX` for `Project.status`, `Project.due_date`, and `Project.created_at`. Sorting and Kanban filtering via `db.paginate()` no longer triggers full table scans, massively improving performance for workspaces with large project histories.

### Changed
- **Backup module extraction** — Extracted `export_data` and `import_data` logic and associated helpers from `routes/settings.py` into a new `routes/backup.py` file, reducing the monolith settings file by over 750 lines and improving maintainability.
- **Project detail refactoring** — Modularized the massive 500+ line `project_detail()` view in `routes/projects.py` by extracting sub-logic into dedicated helpers (`_get_project_files_by_category`, `_build_project_next_actions`, `_build_project_activity_events`, `_build_project_comments`, `_paginate_jobs`), vastly improving readability.
- **Settings form safety** — Replaced 18 instances of unsafe `request.form['key']` with defensive `request.form.get()` across all settings actions (brand, color, material, language, currency, items_per_page, edit/delete entities). Missing form fields now raise `ValueError` with descriptive messages instead of causing HTTP 400/500. (Rule 20 compliance)
- **Stock deduction consolidation** — `use_filament()` and `remove_spool()` now use the centralized `deduct_filament_stock()` helper from `utils.py` instead of duplicating weight-clamping and quantity-adjustment logic.
- **LIKE wildcard escaping** — All `ilike()` filters across inventory, projects, API search, and user search now escape `%` and `_` characters in user input via a new `escape_like()` helper, preventing wildcard injection.
- **Performance: overview page** — Eliminated 3 redundant `Filament.query.all()` calls on the overview dashboard. `build_action_center()` and `_overview_focus()` now load filaments once and reuse the list.
- **Performance: tag options** — Tag option lists for inventory and project filters now use lightweight column-only SQL queries (`with_entities(tag_text)`) instead of loading full ORM objects.
- **Notification localization** — Project notification functions (`_notify_project_created`, `_notify_project_status`, `_notify_project_comment`) now use `translate()` with i18n keys instead of hardcoded Czech strings.
- **Bambu timestamp parsing** — Replaced deprecated `datetime.utcfromtimestamp()` in Bambu Cloud API timestamp parser with `datetime.fromtimestamp(tz=UTC)`.

### Fixed
- **README version sync** — Updated README.md from `v1.61.0` to `v1.62.6` to match `APP_VERSION`. (Rule 18 compliance)
- **Dead code in comment permissions** — Removed identical TESTING/non-TESTING branches in `_comment_edit_allowed()` and `_comment_delete_allowed()`.
- **Deprecated `version` key** — Removed `version: '3.8'` from `docker-compose.yml` (deprecated in Docker Compose v2+).
- **Documentation: app.py docstring** — Updated module docstring to list all 12 route modules (was listing only 5).
- **Documentation: instruction file** — Added `ProjectTodo` to the model list in `copilot-instructions.md` and updated model count from ~20 to ~23.

## [1.62.6] - 2026-04-16
### Fixed
- **Visual editor — cursor oscillation after exiting task list** — After typing text in a checkbox row and pressing Enter twice to exit the list, subsequent Enter presses no longer make the cursor jump back and forth between the paragraph and the task list item. Root cause: the exit `<p>` was created with a bare empty text node which browsers (Chrome especially) do not accept as a stable cursor anchor, causing the cursor to silently drift back into the task list. Fixed by creating `<p><br></p>` and placing the cursor with `range.setStart(p, 0)`, matching native browser expectations.
- **Visual editor — `<ul>` nesting inside `<p>`** — Clicking the checkbox toolbar button while the cursor was inside a paragraph could cause the new `<ul>` to be inserted inside the `<p>` (invalid HTML), leading to unpredictable DOM repairs by the browser. A new `_blockAncestor()` helper now finds the surrounding block element and inserts the list cleanly after it.
- **Removed `placeCaretAtElementStart`** — The helper incorrectly tried to append a text node inside `<br>` elements; it has been removed and replaced by the inline `range.setStart(element, 0)` approach used in the exit-paragraph logic above.

## [1.62.5] - 2026-04-16
### Added
- **Project comment delete action** — Added a delete button for comments in project detail, including confirmation prompt before deletion.

### Fixed
- **Visual editor checkbox reinsertion after list exit** — After leaving a checkbox list with double Enter, the toolbar checkbox button works immediately on the current line (no need to type/delete a character first).
- **Visual caret persistence** — Added selection save/restore in the visual markdown editor so toolbar actions apply reliably at the current caret position.

## [1.62.4] - 2026-04-16
### Fixed
- **Visual checkbox Enter regression** — Pressing Enter after typing text in a checkbox row no longer deletes the existing row. Empty-row detection now evaluates all non-checkbox content in the row (including browser-generated text nodes outside helper spans), so only truly empty rows trigger list-exit behavior.

## [1.62.3] - 2026-04-16
### Fixed
- **Visual checkbox list parity with bullet lists** — Pressing Enter on an empty checkbox row now exits checkbox list editing and continues in normal text mode, instead of endlessly creating/keeping empty checkbox rows.

## [1.62.2] - 2026-04-16
### Fixed
- **Visual task-list editing** — Enter inside a checkbox item now creates a clean sibling checkbox row (no progressive indentation drift).
- **Caret placement after checkbox insertion** is now anchored into the task text area directly to the right of the checkbox.
- **Visual paste behavior restored** to native rich-text paste (formatting preserved), while still keeping deterministic task-list insertion behavior.
- **Checkbox click handling in visual mode** now places the caret into editable task text instead of stealing focus unpredictably.

## [1.62.1] - 2026-04-16
### Fixed
- **Markdown editor UX for checkboxes** — The checkbox action now inserts an empty task marker in Markdown mode (`- [ ] `) without forcing placeholder text.
- **Visual editor checkbox insertion** no longer injects default filler text when no selection exists.
- **Visual editor paste behavior** is now normalized to plain text in the rich-text area, preventing unpredictable pasted structures (unexpected lists/HTML blocks) after inserting task checkboxes.

## [1.62.0] - 2026-04-16
### Added
- **Interactive markdown checkboxes** — Task-list syntax (`- [ ] item`, `- [x] item`) is now supported in both project descriptions and comments. Checkboxes render as interactive elements and can be checked/unchecked directly in the view without entering edit mode. Clicking a checkbox sends an AJAX request that persists the updated state immediately.
- **Checkbox toolbar button** added to all markdown editors (project create, edit, comment add and comment edit forms) for quick task-list insertion.
- New AJAX endpoints `POST /projects/<id>/toggle-description-checkbox` and `POST /projects/<id>/comments/<id>/toggle-checkbox` handle server-side state persistence. Both require project write access (admin or project owner).

## [1.61.0] - 2026-04-12
### Fixed
- **Security: client filter dropdown scoped to current user** — The list of client names shown in the project search dropdown was previously built from a global query across all projects, leaking other users' client names. The query is now scoped through `_project_scope()` so regular users only see client names from their own projects.
- **Smart highlights — "Co dochází" widget** now shows the recommended order in pieces (`N ks`) instead of the raw gram deficit (`285 g`), consistent with all other low-stock displays in the app.
- **Card view weight-bar tooltip** under the progress bar also updated from `recommended_grams` to `recommended_spools` count for consistency.
- **Command center KPI mini-card** for "Hoří teď" replaced with a **Stock value card** showing total filament inventory value (with currency), spool count, and remaining weight in kg — the duplicate urgent-items list was already displayed in the large panel below.
- **Command center large panel** — "Hoří teď" heading and `overview_burning_now_title` i18n key added (CS + EN) to complete the command center redesign.

### Tests
- Updated `test_projects_list_is_paginated_using_app_setting` and `test_project_client_is_rendered_as_filter_link` to match the current Alpine.js AJAX pagination and filter-click behavior (tests previously checked for URL-based `?page=2` links that no longer exist).
- Added `test_user_client_dropdown_only_shows_own_clients` — regression test verifying that a user's client name dropdown does not expose client names from other users' projects.

## [1.60.0] - 2026-04-11
### Added
- **Toggle-hide on widgets**: Clicking the hide button on an already-hidden widget (shown as faded in edit mode) now shows it again. The hide button switches to an amber eye icon when the widget is hidden, making the toggle state obvious.
- **Widget colour picker**: Every widget on Overview, Projects, and Statistics pages now has a colour-palette button in the edit bar. Choose from 9 subtle accent tints (blue, green, amber, red, purple, rose, cyan, slate + default). The tint is applied as a translucent background, keeping text fully legible in both light and dark mode. Selections persist in `localStorage`.
- **Redesigned widget overview panel**: The widget list at the top of all three dashboard pages (shown in edit mode) is now a grid of cards — one per widget — each displaying a colour dot, widget name, and a visibility toggle eye button. Hidden cards are indicated with a dashed border and reduced opacity.
- **Projects visibility panel**: The Projects page now has a `#projectsVisibilityPanel` (matching Overview), populated by `createWidgetLayoutManager`. Previously it had no panel at all.
- **Stats hidden-card panel upgraded**: The `#restorePanel` on Statistics now shows ALL cards (not just hidden ones), matching the design of Overview and Projects.

### Changed
- `createWidgetLayoutManager` extended: `showBtnTitle` config param, `colors` in layout storage, `syncVisibility()` rebuild to grid-card layout.
- `createCardResizeManager` extended: `initHandles()` injects colour-picker buttons into `.card-edit-bar`; new `applyColors()` export.
- `dashboard_show_widget` i18n key added (CS + EN).

## [1.59.0] - 2026-04-13
### Added
- **Inline Widget Hide Button**: All widgets on the Overview and Projects dashboard pages now have an inline hide button (eye-slash icon) directly on the widget's edit bar — identical to the hide button already present on Statistics cards. Click the button in edit mode to immediately hide a widget; restore it via the visibility panel.
- **Shared Dashboard Module** (`static/js/dashboard.js`): Extracted all dashboard management logic into a single shared JS file. `createWidgetLayoutManager` (Overview/Projects) and `createCardResizeManager` (Statistics) are now defined once and sourced by all three dashboard pages, eliminating code duplication.

### Changed
- `createWidgetLayoutManager` now accepts `hideBtnTitle` and `limitAllText` config params (translated strings), and injects the hide button and row-limit selector dynamically.
- `stats.html` refactored to use `createCardResizeManager` from `dashboard.js` instead of inline duplicated functions. Card resize, size apply, and limit apply are now delegated to the shared manager.
- `copilot-instructions.md` updated with Rule 22 (Dashboard Consistency) requiring identical capabilities on Overview, Projects, and Statistics pages via `dashboard.js`.

## [1.58.0] - 2026-04-12
### Added
- **Live Printers Widget**: Restored the standalone "Currently Printing" widget on the Overview dashboard, now alongside the Recent Activity widget. Shows real-time Prusa progress bars and Bambu stripe animations with material swatches.
- **Row Limit Controls**: All list widgets on the Overview page (Recent Activity, Upcoming Deadlines, Top Turnover) now have a row-count selector (5 / 10 / 20 / All) in their edit bar. The selection persists in `localStorage`. Changing the limit instantly shows or hides rows.
- **Projects Grid Expanded to 4 Columns**: Projects layout changed from 3 to 4 columns on XL screens, allowing widgets (e.g. Due Calendar) to be resized up to 4 columns.

### Changed
- Removed the numeric 1/2/4 size buttons from all widget edit bars on Overview, Projects and Statistics pages — horizontal resizing is now done exclusively via the drag-to-resize corner handle.
- Increased backend data limits for Recent Activity (20), Upcoming Deadlines (15), and Top Turnover (10) to better support the row-limit selector.

## [1.57.0] - 2026-04-11
### Added
- **Interactive Card Resize**: Dashboard widgets on the Overview, Projects, and Statistics pages can now be resized interactively by dragging the bottom-right corner handle. Resizing snaps horizontally by one grid column and vertically in 80 px increments. Sizes persist in `localStorage`. The drag-to-move functionality is preserved.
- **Recent Activity Widget**: Replaced the duplicate "Currently Printing" widget on the Overview command-center layout with a **Recent Activity** feed showing the last 10 filament movement log entries (type, grams, project, timestamp). The live-printer status is still shown in the Command Center header stats.
- Resize hint added to edit-mode banners on Overview, Projects, and Statistics pages.

### Changed
- `createWidgetLayoutManager` in `base.html` now stores widget heights in `localStorage` and adds a resize handle to every managed widget.
- Statistics page card resize now uses drag-handle in addition to the existing numeric size buttons; heights are persisted.

## [1.56.9] - 2026-04-10
### Added
- **Global Billing Settings**: Added a new configuration panel in Settings for setting up default company billing details (Supplier info), ensuring invoice documents are prepopulated and synced with database backups.
- **Interactive Invoice & Quote Generator**: Completely reimagined the quote export flow using Alpine.js and Tailwind. Users can seamlessly switch between three layout modes: `Simple Quote`, `Detailed Quote`, and `Invoice` (Faktura), and adjust data dynamically before generating print-perfect cross-browser PDFs.

### Changed
- Standardized display precision of numeric values related to Print Quotes in the project detail interface. Material volumes and print times are now nicely rounded to nearest decimals for cleaner UI.

### Fixed
- **Detailed Quote Print Scaling**: Adjusted the padding values of the detailed quote layout during print mode. The document now natively fits onto a standard A4 page without requiring the user to manually scale down to 72% in the print dialog.

## [1.56.8] - 2026-04-10
### Fixed
- **Project calculator saving:** Instead of saving an individual row (`ProjectQuote`) for every single mapped filament slot, the calculator now saves **one unified calculate quote** for the entire project.
  - Generates a composite name (e.g. `PLA Black (200g) + PETG White (50g)`).
  - Contains the aggregated payload of total material cost, base cost, margin, and electricity.
  - Fixes timeline and Materials tab cluttering from dozens of single quotes.

## [1.56.7] - 2026-04-10
### Changed
- **Project calculator — real job data as primary source:** The project-mode calculator (`/calculator/project/<id>`) now prefers actual print data from Bambu and Prusa jobs over planned filament estimates:
  - **Bambu jobs:** Reads per-AMS-slot `BambuJobMaterial` records (weight per slot, mapped filament, color). Multiple jobs are aggregated per filament.
  - **Prusa jobs:** Reads `PrusaPrintJob` weight and mapped filament.
  - **Print time:** Calculated from the sum of actual `cost_time` (seconds) across all jobs, not the project estimate.
  - **Fallback:** If no jobs with usable data exist, falls back to planned `ProjectFilament` entries and estimated print time.
  - **Source badge:** Header shows a teal badge ("Realálná data z tiskových jobů") or amber badge ("Plánovaná data") so the user knows which source is used.
  - **Unmapped slots:** Bambu slots not yet assigned to a filament are shown with a warning badge instead of being silently dropped — their cost is 0 but weight is still visible.
  - **Empty state:** Improved with links to both the Materials tab and Jobs tab when neither source provides data.

## [1.56.6] - 2026-04-10
### Added
- **Project-mode print calculator (`/calculator/project/<id>`):** Clicking the Calculator button from any project detail page now opens a dedicated project-mode calculator that automatically pre-fills all inputs from the project — filaments, estimated weights, and print time. Only the margin (%) can be adjusted by the user.
  - Per-material cost breakdown table with material name, weight, unit price, and material cost.
  - Shared electricity cost row split proportionally by weight across materials.
  - Live-updating sidebar: changing the margin instantly recalculates the final price without a page reload.
  - Saving stores one `ProjectQuote` row per material line and redirects back to the project Materials tab.
  - Empty-state shown when the project has no filaments assigned yet.
### Changed
- **Project detail — Calculator links:** All three calculator buttons in project detail (hero badge, materials tab badge) now link directly to the new project-mode calculator instead of the generic manual calculator.

## [1.56.5] - 2026-04-10
### Changed
- **Command Center redesign:** Replaced the 2-panel layout (large description block + 4 stat cards + 2 wide project panels) with a compact 3-column hub that acts as a true crossroads of what's happening now:
  - **Needs Attention** — each urgent item (low stock, overdue projects, unmapped Bambu jobs, printer issues) is its own clickable row with a coloured dot and chevron; a green "all clear" state when nothing is pending.
  - **Active Print** — compact live printer cards with progress bar, model name, start time and BAMBU/% badge; scales to show all active printers.
  - **Active Projects** — concise list with a status-coloured dot, project name, status label and due date; projects due today are highlighted in amber.
  - KPI totals (urgent, active projects, live printers, due today) moved to a compact pill row in the header instead of 4 large stat cards.

## [1.56.4] - 2026-04-10
### Fixed
- **Movement History — per_page preference not remembered:** Replaced the previous `localStorage` + redirect approach (which caused a double page load) with a server-side cookie (`history_per_page`, 1 year). The server reads the cookie as a fallback when `per_page` is absent from the URL, so the preference is applied immediately on every visit without any redirect or flicker.

## [1.56.3] - 2026-04-10
### Changed
- **Movement History — unified design:** Rewritten `history.html` to use the same `page-shell` / `page-hero` / `app-surface` layout pattern as other pages (Bambu, Prusa, Stats). The page header now uses the shared `page-title` / `page-title-icon` component. Table uses design-system CSS variables for colors, borders, and dark-mode support.
- **Movement History — clickable filament rows:** Each movement that has a linked filament record (`filament_id` is set) now renders the filament name as a clickable link leading to the filament detail page. A spool icon and an "external-link" indicator appear on hover.

## [1.56.2] - 2026-04-10
### Fixed
- **Missing Movement History link in main navigation:** The movement history page (`/history`) was accessible via the command palette (Ctrl+K) but had no entry in the sidebar or mobile menu. Added a dedicated nav link with the `fa-clock-rotate-left` icon, correct active-state highlight, permission guard (`auth_has_section_access('history')`), and breadcrumb label in the topbar.

### Fixed
- **Bambu — active print not shown on overview:** For some printer/firmware versions, the Bambu Cloud API reports ongoing prints with status `PAUSED` (raw=4) instead of `RUNNING` (raw=1). The "Live Printers" widget on the main page now includes both values in the filter, so ongoing prints are correctly displayed as active even in this state.

## [1.56.0] - 2026-04-08
### Changed
- **Dark mode – Stats page:** All stats cards (`low_stock`, `top_turnover`, `profitable_projects`, charts, tables, color palette) now correctly adapt to dark mode using CSS custom-property surfaces, borders, and text colors. Day-filter pills, edit-mode button, navigator links, and color-palette tooltips also switch to dark-aware styles.
- **Dark mode – Project detail:** Status-flow step cards, progress-bar track, TODO item cards, description text, and comment bodies now all render correctly in dark mode.
- **Project client simplified:** Removed the separate "Vlastník (uživatel)" user-selector and "Vlastník (externí jméno)" manual-input fields from project create, edit, and the projects list/kanban view. Only the "Klient" field is now shown and editable. The owner relationship is retained internally for access-control (non-admin users still see only their own projects) but is no longer surfaced in the UI.

## [1.55.0] - 2026-04-08
### Added
- **Project owner assignment flexibility:** Administrators can now assign a project owner either to an existing system user or to an external person name (without creating a user account).

### Changed
- **Project create/edit forms:** Admin project forms now include dedicated owner assignment fields (`owner user` and `external owner name`), with external name taking precedence when filled.
- **Owner display fallback:** Project owner labels across project list/detail and overview now correctly show external owner names when no user account is assigned.
- **Backup compatibility:** Project export/import now preserves the new external owner name field so owner assignments remain intact after restore.

## [1.54.0] - 2026-04-08
### Added
- **Project collaboration UX upgrades:** Project detail now supports TODO checklists, Markdown-rendered descriptions and comments, inline comment editing for the comment owner, deletion of uploaded project files across file types, and a richer Markdown/WYSIWYG editor with preview for project descriptions and project comments.
- **3D preview color control:** The project 3D model viewer now includes a simple model color picker to improve visibility for hard-to-see meshes in the preview.

### Changed
- **Project detail workspace refinement:** The low-value "Next steps" card was replaced by a TODO-focused card and summary, the TODO input layout was hardened for narrow sidebars, and the filament picker in project materials now stays above neighboring cards instead of rendering underneath the quote section.
- **Navigation permissions tightened:** Bambu and Prusa printer entries in the navigation are now hidden unless the user actually has access to the printers section, not only when the integration is configured.

## [1.53.0] - 2026-04-07
### Added
- **Global Command Palette:** Added a global search layer (Ctrl+K) accessible from anywhere to instantly navigate through filaments, projects, and printers.
- **Configurable Dashboard Widgets:** The overview page now supports resizable widgets (1 to 4 columns wide) to let users build a custom dashboard grid.
- **Dashboard Widget Visibility:** Introduced a widget picker panel in the layout edit mode, allowing users to show or hide individual widget blocks based on their preference.
- **Statistics card sizing:** The statistics dashboard edit mode now also supports per-card width selection, so individual cards can be expanded to better fit the chosen layout.
- **New Dashboard Widgets:** Added widgets for "Spotřeba za posledních 7 dní" (7-day activity sparkline), "Nadcházející termíny" (upcoming project deadlines), and "Nejpoužívanější filamenty" (top turnover filaments).
- **Configurable navigation palette:** Settings now include a new interface palette selector for the main menu and top app shell, with multiple color moods for the navigation area.

### Changed
- **Navigation Redesign:** The entire application layout has been modernized to use a collapsed left sidebar that expands on hover (saving horizontal space) and a bottom tab bar for mobile screens, replacing the traditional top navigation.
- **Main navigation compacted:** The top app bar now uses a denser layout with smaller vertical padding, tighter menu pills, and a more compact brand block so it takes less space on the screen.
- **Main navigation motion reduced:** Removed the dropdown/menu animation from the main navigation to keep the header calmer and visually cleaner.
- **Page header consistency:** Main application pages now use a unified content shell and a consistent title header with icons, so sections like Projects, Storage, Statistics, Bambu, and Prusa align visually.
- **Header branding simplified:** Removed the extra descriptive subtitle text from the main menu brand block.
- **Overview upgraded into a command center:** The admin homepage now surfaces urgent items, projects due today, and the active project queue in a stronger operations-first layout above the existing widgets.
- **Project detail turned into a richer workspace:** Project pages now open with a progress-first workspace header, visible status timeline, clearer delivery signals, and a sticky right-side next-action panel.
- **Inventory visuals strengthened:** The filament inventory now highlights stock risks, turnover, and color mix before the filter area, and the card view uses stronger color swatches, compact stock metrics, and clearer quick actions.
- **Command center urgency card clarified:** The `Hoří teď` block now shows a concrete shortlist of urgent stock, project, or printer issues instead of only a summary number.

### Fixed
- **Filaments page runtime error:** Restored the missing `Counter` import used by the new inventory highlight aggregation so `/filaments` no longer fails with HTTP 500.
- **Missing navigation entries:** Restored `Calculator` and `Users` in the main sidebar and mobile menu, where they had remained available in the command palette but disappeared from the visible navigation.

## [1.52.3] - 2026-04-07
### Changed
- **User table headers are now clickable for sorting:** All columns in the user overview table (Name, Email, Role, Created, Last login, Status) are now clickable links that toggle ascending/descending sort. Active sort direction is indicated with up/down arrow icons. The Status column is now also a sortable field.

### Fixed
- **Status column sorting:** The user list now supports sorting by account active/inactive status, with null values handled consistently.

## [1.52.2] - 2026-04-05
### Added
- **Initial remaining weight field on Add Filament form:** Users can now set a custom starting weight when adding a partially used spool (e.g. spool capacity 1000 g but only 500 g remaining). This avoids polluting usage statistics with a phantom subtract operation. The field is optional — when left empty, remaining weight defaults to full capacity × quantity.

### Fixed
- **Brand shop URL placeholder not substituted:** The `{query}` placeholder in Brand shop URLs (e.g. `https://allegro.cz/search?q={query}`) was only matched literally — typos like `{querry}` or `{search}` were passed through unchanged. Now any `{…}` placeholder is replaced with the filament name. Also added a visible hint text under the Brand shop URL input and changed input type from `url` to `text` to prevent HTML5 validation errors on template URLs.

### Changed
- **`README.md` rewritten:** Professional structure with feature overview, tech stack table, project tree, quick-start guide, upgrade/backup instructions, test commands, and roadmap status.
- **`.github/copilot-instructions.md` consolidated:** Merged architecture overview, data flow diagrams, dependency tables, and security layer from a separate `INSTRUCTIONS.md` into the existing copilot instructions. Removed `INSTRUCTIONS.md` from root. Fixed outdated stats section count (6, not 7). Updated backup schema table to cover all current models. Unified language to English.

### Security
- **Password storage hardened:** Password hashing is now explicitly generated with the modern `scrypt` scheme instead of relying on framework defaults.
- **Login redirect hardening:** The `next` parameter after login is now restricted to same-origin targets only, blocking open-redirect style abuse.
- **Session and cookie hardening:** Login/logout now rotate the session state, session cookies are explicitly marked `HttpOnly` and `SameSite=Lax`, and the secure flag is enabled automatically behind a reverse proxy.
- **Response security headers:** Added safe default headers including `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy`, and conditional HSTS on secure requests.

## [1.52.1] - 2026-04-05
### Changed
- **User filament pagination upgraded:** The regular-user filament list now has a dedicated records-per-page selector, numbered pagination links, and a remembered per-page preference so larger catalogs stay usable over time.
- **Project create dark-mode cleanup:** The read-only `Klient` block on the new-project form now uses neutral shared surface colors, keeping the text readable in dark mode.

### Fixed
- **Bambu page refresh loop:** The `hide failed` preference no longer triggers unnecessary URL rewrites on page load, which stopped the repeated self-refreshing behavior on the Bambu print history page.

## [1.51.0] - 2026-04-04
### Added
- **Multi-user authentication:** Added login, logout, self-registration, invite activation codes, account settings, notification inbox, and administrator user management.
- **Project ownership and collaboration:** Projects now support owners, creator tracking, approval statuses (`PENDING_APPROVAL`, `APPROVED`, `REJECTED`), per-project comments, and in-app notifications for new requests, status changes, and discussion updates.
- **Backup coverage for user workspace:** Export/import now includes users, invites, notifications, project ownership, and project comments so the new collaboration layer is part of full backups.

### Changed
- **Role-based access control:** Administrators keep full read/write access, while regular users are limited to permitted sections and only their own projects.
- **Projects UX:** The project list now supports owner filtering for administrators, and project detail screens adapt actions based on whether the viewer is an administrator or the project owner.

## [1.50.0] - 2026-04-03
### Added
- **Tag shortcuts from Settings:** Filament tags in Settings now open the dedicated `/filaments` page with the selected tag already applied as a filter, so the tag cloud doubles as a fast inventory entry point.

### Changed
- **Tag cleanup directly in Settings:** Both filament and project tags can now be removed directly from the Settings tag cloud. Removal updates every matching record case-insensitively while preserving the remaining tags.

## [1.49.0] - 2026-04-03
### Added
- **Per-brand shop URL:** Each brand in Settings can now have an optional search URL template (e.g. `https://www.alzament.cz/search?q={query}`). This is used as a fallback buy button on filament cards when no direct per-filament shop link is set.
- **Shop cart icon on inventory cards/list:** Every filament card and list row now shows a green shopping-cart icon in the quick-actions area. Priority: 1) direct filament `shop_url`, 2) brand search template, 3) global search template in Settings. If none is configured, the button is hidden.

### Fixed
- **Alza.cz search URL format:** Corrected Alza preset button to use `https://www.alza.cz/search.htm?exps={query}` (was `/hledani/{query}` which returned no results).
- **Allegro preset changed to .cz:** Changed the preset shop button from `allegro.pl` to `allegro.cz` with the correct Czech domain URL.

## [1.48.0] - 2026-04-05
### Added
- **Richer Bambu Cloud print info on overview:** Active printer cards now show material color swatches, material names, estimated weight usage, print duration (cost time), printer model, and job start time sourced from Bambu Cloud job data.
- **Per-filament shop URL:** Each filament can now have an optional direct shop product link (`Shop URL`) set in its edit form. This link overrides the global search template when shown as a buy button on the Statistics low-stock widget.
- **Global reorder shop URL template:** A new section in Settings lets you configure a default search URL template (e.g. `https://www.alza.cz/hledani/{query}`) with preset quick-set buttons for Alza.cz, Allegro.pl, Mironet.cz, and Amazon.de. Used as a fallback on the low-stock widget when no direct link is set.
- **Buy/search button on low-stock widget:** Each reorder row on the Statistics page now shows a shopping-cart icon (direct link) or magnifying-glass icon (search template) for quick shop navigation.

### Fixed
- **Clipboard copy not working on HTTP:** The "copy reorder" button on the Statistics low-stock widget failed silently on non-HTTPS connections (clipboard API requires a secure context). Added a textarea+execCommand fallback that works regardless of protocol.

## [1.47.0] - 2026-04-04
### Added
- **Color swatch in card view:** Inventory card view now shows a small colored circle swatch inline next to the color name for quick at-a-glance identification.
- **Printer brand icons on overview:** Live printer cards on the overview page now show brand badges — teal "BAMBU" for Bambu Cloud jobs (with a teal icon), orange "PRUSA" for Prusa Network printers (with an orange icon). Progress bar for Prusa is now orange to match the brand.
- **Calculator pre-fill from project:** The "Calculator" button in a project detail header now deep-links to the calculator with the first assigned filament pre-selected (via `?filament_id=X` query param). The calculator page reads this param and auto-fills the filament dropdown.
- **Reorder copy-to-clipboard:** Each row in the low-stock / reorder recommendations widget on the Statistics page now has a copy button that writes `Filament Name × N spools` to the clipboard.
- **Dark mode completion:** Fixed several components missing proper dark mode styling — body gradient (removed white top-fade), section/card edit bars in stats, all status chip colors (green/red/yellow/emerald/orange/teal), info banners, flash toast messages, and modal backgrounds.

### Changed
- **Stats – KPI section removed:** The entire draggable `section_kpi` (KPI summary) block has been removed from the Statistics page. The same data is already visible in the non-draggable Executive panel at the top of the page, making the section redundant.
- **Overview – live printers idle state:** The "Active Printers" widget is now always rendered in the DOM (removes outer `{% if live_printers %}` guard), preserving its drag-drop position in localStorage even when no printers are printing. An idle empty state is shown when there are no active jobs.

## [1.46.1] - 2026-04-03
### Fixed
- **Stats – duplicitní KPI odstranněno:** 4. karta v sekci `section_kpi` zobrazovala stejné „Upozornění na doobjednání“ jako fixní Denní řídcí přehled v horní části stránky. Karta je nyní nahrazena metrikou **Sledované filamenty** (celkový počet sledovaných filamentů + počet aktivních projektů), která nebyla nikde jinde zobrazena.

## [1.46.0] - 2026-04-03
### Fixed
- **Bambu live print card on overview:** Bambu Cloud jobs with `RUNNING` status are now included in the live printers widget on the overview page. Bambu cards display an animated indeterminate progress bar (since Cloud API doesn’t provide real-time progress) with a teal accent to distinguish them from local Prusa printers.

### Changed
- **Overview action center \u2013 sync section replaced:** The “Synchronizace” quadrant, which showed printer connectivity issues, has been replaced by a **Recent Prints** widget showing the last 6 completed print jobs across Bambu and Prusa printers. Printer issue count is also removed from the KPI total to keep the number actionable.
- **Projects page \u2013 scalable Kanban pagination:** The `projects_index` route previously loaded every project (with all relationships) into memory and sliced in Python. Each Kanban status column now runs a dedicated DB-level `db.paginate()` query. Metrics are computed only for the visible items on the current page, making the page fast even with hundreds of projects.
- **Projects Kanban \u2013 compact page links:** Kanban column pagination now uses `iter_pages()` with ellipsis truncation instead of rendering every page number, keeping the column footer clean with many pages.

## [1.45.4] - 2026-04-02
### Fixed
- **Statistics color palette link:** Clicking a color in the statistics palette now opens the dedicated filament list with the matching color filter instead of the overview page.
- **Outdated inventory link audit:** Reviewed post-refactor navigation targets after splitting `/` and `/filaments`; no other stale filtered links remained outside the statistics palette.

## [1.45.3] - 2026-04-02
### Changed
- **Projects board compacted:** Status columns on `/projects` now use denser cards, show 5 items per column, and paginate independently so the Kanban area stays readable.
- **Project detail cleanup:** The duplicate activity block was removed from the overview tab, leaving activity history only in the dedicated `Activity & jobs` workspace tab.
- **Dashboard edit button fix:** The active `Done editing` button now keeps readable light-theme hover styling on overview, projects, and statistics pages.
- **Statistics navigation simplified:** The confusing `Sections` tab switcher was replaced with a stable quick-jump navigator, and all deeper statistics sections remain visible on the same page instead of hiding surrounding content.
- **Projects due strip refined:** The `Termíny` widget now stays in a single compact row and shows only the nearest unfinished deadlines.
- **Live printer reliability tightened:** The overview now shows only printers with fresh sync data and real progress information, so stale `Heating / preparing` states no longer linger there.

## [1.45.2] - 2026-04-02
### Changed
- **Remembered filament view mode:** The `/filaments` page now keeps the selected card/list mode even after leaving the page and coming back later.
- **Interactive overview layout:** The overview page now supports the same edit-mode drag/reorder pattern as the statistics dashboard, with live printers promoted to the top in a more compact, immediately visible block.
- **Interactive projects board:** The projects page now uses the same draggable widget editing model as statistics, and Kanban columns are labeled only by their actual status names.
- **Action Center mapping cleanup:** Bambu jobs without a linked project are no longer treated as deficiencies on the overview dashboard; only missing filament/material mapping is surfaced there.

## [1.45.1] - 2026-04-02
### Changed
- **Overview split from filament list:** `/` is now a clean operations overview, while the full filterable inventory list moved to `/filaments` so dashboard work and stock browsing no longer compete on one page.
- **Navigation grouped for day-to-day use:** Top navigation now follows the intended structure `Inventory / Projects / Printers / Analytics / Settings` and includes a dedicated entry for the new filament list page.
- **Project detail tab persistence:** Uploading files, adding links, refreshing previews, and materials actions now redirect back to the relevant project tab instead of dropping the user onto the default view.
- **Project job history refined:** The project detail page now uses a compact combined Bambu/Prusa job feed with pagination, and printer history is shown only when the related integration is actually configured.
- **Link previews restored:** Rich project link cards with image/title/description previews were brought back so saved references are easier to scan again.

## [1.45.0] - 2026-04-01
### Added
- **Action Center on inventory dashboard:** New top-level operational panel on the main inventory page that groups low-stock alerts, overdue projects, unmapped print jobs, and printer sync issues into one place.
- **Saved views for inventory, storage, and stats:** Added browser-persisted presets for the most filter-heavy pages so users can jump back to common views in one click.
- **Prusa sync diagnostics persistence:** `PrusaPrinter` now stores `last_sync_at`, `last_success_at`, and `last_sync_status`, and those fields are included in export/import backups.

### Changed
- **Shared design system:** Introduced reusable UI surface, badge, filter, and table styles via CSS variables in `base.html`, with cleaner light/dark consistency across the updated pages.
- **Grouped navigation:** Top navigation is now organized into logical areas for inventory, projects, printers, analytics, and settings.
- **Statistics dashboard executive mode:** `/stats` now opens with a concise executive overview (primary KPI set + dominant chart) while deeper widgets are split into switchable sections for planning, projects, and detail work.
- **Projects workspace redesign:** Project detail now behaves more like a workspace with a left-side status/finance rail, next-action guidance, estimate-vs-actual summary, tabbed content areas, and a lightweight project activity feed.
- **Projects overview upgraded:** `/projects` now includes a kanban-style status board, due-date calendar strip, and estimate-vs-actual summary columns in the main table.
- **Filament knowledge layer emphasized:** Filament detail now highlights profile, drying, adhesion, and print-note data more clearly so filament-specific know-how is easier to reuse.
- **Settings printer diagnostics:** Settings now surfaces manual sync actions and last sync state summaries for both Bambu Cloud and PrusaLink integrations.

## [1.44.0] - 2026-04-01
### Added
- **Live printers on dashboard:** Displays current running print jobs (for both Bambu and Prusa printers) directly at the top of the main dashboard in a compact grid. Includes a progress bar thermometer, estimated time of arrival, and a pulsing status indicator.
- **Project 3D Viewer:** Integrated `Online3DViewer` CDN. Allows interactive 3D rendering of `.stl` and `.3mf` files attached to projects directly in the browser via an Alpine-powered modal dialog, with full CORS compatibility.
- **Full PWA Support (Progressive Web App):** Introduced auto-generated `/manifest.json` and a basic Service Worker (`/sw.js`). The application can now be installed on mobile devices or as a standalone desktop app.

### Changed
- **Toast notifications (UX Improvement):** Flash messages no longer push page content down. They have been replaced with elegant pop-up "toast" notifications in the top right corner that automatically dismiss after 5 seconds, driven by Alpine.js with smooth CSS transitions.

## [1.43.1] - 2026-04-01
### Changed
- **Conditional navigation links**: The "Bambu Lab" menu item is now visible only when a Bambu Cloud token is configured in Settings. The "Prusa Printers" menu item is visible only when at least one enabled PrusaLink printer exists. Both integrations must be set up in Settings before their respective pages appear in the navigation bar.

## [1.43.0] - 2026-04-01
### Added
- **PrusaLink Integration**: New printer integration via local PrusaLink REST API (no cloud required). Add any Prusa printer by its local IP address and API key; the background worker polls each enabled printer every 60 s and records active/completed print jobs automatically.
- **PrusaPrinter model**: Stores printer alias, host URL (encrypted), API key (encrypted), auto-detected model, notes, and enabled flag.
- **PrusaPrintJob model**: Stores captured print jobs including filename, display name, status, started/finished timestamps, weight from g-code metadata, estimated duration, progress (0–100 %), filament and project assignment, deduction flag, and raw API payload.
- **`/prusa` page**: Paginated print job history with filter pills (All / Without filament / Not deducted), hide-stopped toggle, per-printer manual sync buttons with AJAX feedback, expandable mapping panel (assign filament + project, deduct from stock), and animated progress badge for jobs in progress.
- **Settings — PrusaLink section** (`/settings#prusa-printers`): Add/edit/delete configured printers, test connection (returns firmware version and model), enable/disable individual printers.
- **Navigation**: "Prusa tiskárny / Prusa Printers" link added to the top navigation menu.
- **Background poll worker** (`_start_prusa_sync_worker`): Daemon thread polls all enabled printers every 60 s; exponential backoff on repeated errors (max 15 min gap).
- **Filament + stock deduction**: Clicking "Deduct from stock" on a finished job reduces `weight_remaining`, creates a `MovementHistory` entry (`prusa_print`), and records a `PrintHistory` row.
- **Test connection endpoint** (`POST /prusa/printer/<id>/test`): Validates connectivity against `/api/version` and back-fills detected printer model from `/api/v1/info`.
- **ALTER TABLE migrations**: `_safe_alter` guards for `prusa_printer.notes`, `prusa_printer.enabled`, `prusa_print_job.progress`, `prusa_print_job.raw_payload`.
- **Export/Import coverage**: `prusa_printers` and `prusa_jobs` are now included in full-application backup/restore (API keys excluded for security with a note on import).
- **i18n**: All UI strings translated in Czech (`cs`) and English (`en`).

## [1.42.0] - 2026-03-31
### Added
- **Bambu: Hide failed prints filter**: New persistent toggle on the Bambu print jobs page that hides failed and cancelled jobs. The preference is stored in `localStorage` and automatically restored on subsequent visits. Works independently alongside the existing filter pills (All / Unassigned / Not deducted) and the filament filter.

## [1.41.2] - 2026-03-31
### Fixed
- **Orphaned ProjectFilament rows on filament delete**: Deleting a filament (single or bulk) now explicitly removes associated `ProjectFilament` rows and nullifies `ProjectQuote.filament_id` references *before* the filament is deleted, preventing integrity errors and template crashes.
- **Model FK `ondelete` clauses**: Added `ondelete='CASCADE'` to `ProjectFilament.filament_id` and `ondelete='SET NULL'` to `ProjectQuote.filament_id` for correct behavior when FK enforcement is enabled.

### Removed
- **Dead code `get_project_tags()`**: Removed unused helper function from `utils.py` (never called anywhere).
- **Unused i18n keys**: Removed `project_files` and `bambu_project_link` from both `cs` and `en` translation dictionaries (defined but never referenced in any template or route).

### Changed
- **Updated `copilot-instructions.md`**: Replaced phantom route references (`serve_file`, `link_preview`) with the actual current project routes (`download`, `image`, `status`, `consume`, `refresh_link`).

## [1.41.1] - 2026-03-31
### Fixed
- **Bambu status string aliases**: Extended `_STATUS_STR_ALIASES` in `routes/bambu.py` to handle additional string status values from Bambu Lab Cloud API (`in_progress`, `printing`, `running`, `paused`, `canceled`, `init`, `prepare`, `slicing`, `failed`). Previously, these string statuses would fall through to the unknown status case and display incorrectly.

## [1.41.0] - 2026-03-29
### Changed
- **Color palette sort**: The color palette widget on the Statistics page now sorts colors by HSL hue (rainbow order) instead of alphabetically by name. Neutral/gray tones are grouped at the end. Implemented via `_hex_to_hsl_sort_key()` in `routes/stats.py` using Python's `colorsys` module.
- **README**: Updated feature list to reflect all current pages (Statistics, Storage, Bambu, Movement History, full backup/restore) and added Alpine.js + Chart.js to the technologies section.
- **Copilot instructions**: Added `stats.py` and `storage.py` to the file structure; added Rule 18 (Stats Page Draggable Layout) covering section IDs, localStorage key, edit mode, row-limit fix, and color sort.

## [1.40.0] - 2026-03-29
### Fixed
- **Stats record-limit bug**: The row-limit selector had no effect on the *Co dochází*, *Co se nejvíc točí*, and *Nejziskovější projekty* cards because `element.hidden` was overridden by Tailwind's `display: flex` class. Fixed by using `element.style.display` (inline style) instead.

### Added
- **Up/Down buttons in edit mode**: Each section-edit-bar now shows ▲ / ▼ arrow buttons alongside the drag handle so sections can be reordered by clicking without drag-and-drop.

## [1.39.0] - 2026-03-29
### Added
- **Draggable stats layout**: All 7 sections on the Statistics page can be freely reordered by drag-and-drop in edit mode. Order is persisted in `localStorage` per browser.
- **Hide/show individual cards**: Every card on the Statistics page has an eye-slash button (visible in edit mode) to hide it from view. Hidden cards can be restored from a restore panel that appears at the bottom of the page in edit mode.
- **Per-card record count**: Cards with tabular/list data (low stock, top turnover, profitable projects, forecast, purchase recommendations, project usage, purchase log) have a configurable row limit (e.g. 3/5/10/all) shown in edit mode. Limits are saved to `localStorage`.
- **Edit mode toggle**: A "Edit layout" button in the page header activates edit mode showing all section drag handles and card controls. "Done editing" returns to read-only view.
- **Reset layout**: A "Reset to default layout" link inside the edit mode hint bar reloads the page with the default section order and clears saved layout state.
- Backend now passes increased data sets to the stats page: up to 50 forecast rows, 30 purchase log entries, 20 project rows, 20 top-turnover rows, 15 profitable projects, all purchase recommendations.

## [1.38.0] - 2026-03-29
### Added
- **Color palette on Stats page**: New full-width card at the bottom of the Statistics page displays all filament colors as colored circles. Hovering over a circle reveals a popup card listing all filaments of that color with their name, brand, material, remaining weight and fill percentage bar. Clicking the circle navigates to the filtered inventory view for that color.
- **Persistent per-page setting in Movement History**: The "Records per page" selector in `/history` now saves its value to `localStorage`. When a user navigates away and returns, the previous selection is automatically restored (without adding an extra entry to the browser history).

## [1.37.0] - 2026-03-28
### Security
- **CSRF protection**: Added Flask-WTF `CSRFProtect`. Every POST form now receives an auto-injected `csrf_token` hidden field via a global JavaScript snippet in `base.html`. AJAX `fetch()` calls automatically receive the `X-CSRFToken` header.
- **Secret key from environment**: `app.secret_key` is now read from the `SECRET_KEY` environment variable instead of being hardcoded. Falls back to a random value per process (sessions not persisted across restarts) when the variable is not set.
- **Conditional ProxyFix**: `ProxyFix` middleware is only activated when `BEHIND_PROXY` env var is set, preventing IP header spoofing on direct deployments.
- **Bambu token encryption**: Bambu Lab Cloud token is now encrypted at rest using Fernet symmetric encryption when `FERNET_KEY` env var is configured. Fully backward-compatible — unset `FERNET_KEY` preserves existing plaintext behaviour.
- **Path traversal protection**: `project_download_file` and `project_image_file` now verify that the stored file path resolves inside `UPLOAD_FOLDER` before serving, blocking crafted import backups that could reference arbitrary filesystem paths.
- **Bulk-delete action validation**: `inventory_bulk` now requires `action=bulk_delete_selected` in the POST body. Unknown actions are silently ignored, preventing accidental data loss if the form is extended in future.

### Fixed
- **Input validation in inventory routes**: `add()`, `edit()`, and `use_filament()` now use `request.form.get()` with type coercion and proper error handling instead of raw `request.form['key']` which caused HTTP 500 on bad input.
- **Nested app context in `_safe_alter`**: Removed redundant inner `app.app_context()` wrap — `_safe_alter` is always called from within an existing context.
- **Gunicorn worker count**: Reduced from 2 to 1 worker to avoid SQLite `database is locked` errors under concurrent load.
- **Background Bambu worker exponential backoff**: Worker now backs off exponentially from 60 s up to 3600 s on consecutive errors instead of hammering the API every 60 s regardless.
- **Duplicate `_display_filament_name`**: Removed two local redefinitions in `routes/stats.py` and `routes/inventory.py`; both now use `build_filament_history_name` from `utils.py`.

### Changed
- **Dependencies pinned**: `requests` and `beautifulsoup4` now have version ranges (`>=2.31,<3` and `>=4.12,<5`). Added `Flask-WTF==1.2.1` and `cryptography>=42,<43`.
- **DB indexes**: Added `index=True` on `MovementHistory.created_at` and `MovementHistory.filament_id` to speed up the 90-day usage window query.
- **FK cascade on `StoragePlacement.filament_id`**: Changed to `ondelete='CASCADE'` so shelf placements are automatically removed when a filament is deleted.
- **FK cascade on `BambuPrintJob.project_id` / `filament_id`**: Changed to `ondelete='SET NULL'` so Bambu jobs are not orphaned silently when their parent project or filament is deleted.
- **SQLite connection timeout**: Added `connect_args={'timeout': 30}` to the SQLAlchemy engine options.

## [1.36.11] - 2026-03-28
### Fixed
- **Bambu mapping panel JavaScript repaired**: per-slot Alpine state now escapes filament names safely inside `x-data`, which fixes browser errors like `Unexpected token '}'` and missing `assignedLabel` / `slotQ` variables on the Bambu jobs page.

## [1.36.10] - 2026-03-28
### Changed
- **Project overview pagination**: `/projects` now uses the shared per-page app setting and renders navigation controls, so large project lists stay responsive and readable.
- **Compressed backup format**: Settings export now downloads a gzip-compressed `.json.gz` backup to reduce disk usage while keeping the same full-application payload.

### Fixed
- **Backup import compatibility**: `/import` now accepts both the new compressed backups and legacy plain `.json` exports, so older backup files remain restorable.

## [1.36.9] - 2026-03-28
### Fixed
- **Backup/import relationships hardened**: export/import now preserves filament references with full identity data instead of relying only on filament names, which prevents cross-linking the wrong spool when duplicate names exist.
- **Project file backups made portable**: exported project files now include restorable file content and import recreates real upload files instead of leaving dead filesystem paths in the database.
- **Statistics reorder labels restored**: purchase recommendations again show translated reorder states and the stock-status thresholds now mark very short remaining coverage as immediate reorder situations.
- **Projects name sorting repaired**: the projects overview now truly sorts by project name when that header is selected.
- **Storage redirects realigned**: shelf actions now redirect using the live shelf filter parameter instead of the stale `shelf_id` query argument.
- **Schema migration noise reduced**: expected duplicate-column `ALTER TABLE` cases no longer flood logs as application errors during startup and tests.

## [1.36.8] - 2026-03-28
### Changed
- **Shelf assignment modal decoupled from filters**: opening the slot-assignment dialog now always starts with an empty filament search, so it no longer inherits any active shelf-page filter context.

### Fixed
- **Shelf preview behavior kept universal**: hover previews remain available across both dense and smaller shelf layouts so reduced boards stay readable too.

## [1.36.7] - 2026-03-28
### Changed
- **Shelf hover previews expanded**: filament preview cards now appear on hover for all shelf layouts, not only dense boards.

### Fixed
- **No forced shelf filter after assignment**: assigning a filament into a shelf slot now returns to the unfiltered shelf view unless a filter was explicitly chosen by the user.

## [1.36.6] - 2026-03-28
### Changed
- **Reorder recommendations now respect spool capacity**: the statistics page now recommends only whole spools, shows the actual orderable gram total, and includes the resulting purchase price.

### Added
- **Per-filament alert snooze**: active reorder alerts can now be snoozed individually from the inventory/detail workflow while still remaining visible inside statistics.

## [1.36.5] - 2026-03-28
### Changed
- **Shelf assignment flow refined**: opening the slot-assignment modal now focuses the filament search input immediately so typing can start without an extra click.

### Fixed
- **No implicit filament filter after assignment**: assigning a filament into a shelf slot no longer activates the shelf-page filament filter afterward.
- **Shelf resize repacking**: when shrinking a shelf, out-of-range placements are now moved into any free slots that still exist before anything is removed from the layout.

## [1.36.4] - 2026-03-28
### Added
- **Shelf hover preview**: compact shelf slots now show a larger filament preview card on hover so dense layouts stay readable without sacrificing drag-and-drop between positions.

## [1.36.3] - 2026-03-28
### Changed
- **Shelf assignment modal aligned with overview filters**: filament assignment inside empty shelf slots now uses the same interactive searchable dropdown pattern as the main inventory overview.
- **Shelf page header simplified**: adding a shelf is now opened from a compact action button with a modal form, leaving more room for shelf filters at the top of the page.

## [1.36.2] - 2026-03-28
### Changed
- **Shelf inputs upgraded**: shelf filters and slot assignment now use searchable text inputs with narrowed suggestion lists instead of plain selects.
- **Shelf board densified**: large shelves now render as a compact square map that stays within the page width instead of forcing horizontal scrolling.
- **Orientation removed from shelf UI**: slot assignment and board cards no longer expose orientation controls, keeping the layout cleaner and faster to use.

### Added
- **Shelf deletion**: shelves can now be removed directly from their edit panel including all slot assignments in that shelf.

## [1.36.1] - 2026-03-28
### Changed
- **Shelf workflow reworked**: spool placement is now done directly from empty shelf slots, shelves can be edited in place, and large shelf grids use a more compact board layout with horizontal scrolling for better readability.
- **Shelf filtering improved**: filtering can now target a specific filament and matching slot positions are highlighted directly in the board instead of disappearing from view.

## [1.36.0] - 2026-03-28
### Added
- **Shelf layout prototype**: added a new visual `/storage` page with named shelves, configurable slot grids, spool placement cards, orientation controls, drag-and-drop moves, fill indicators, and filtering by shelf, brand, material, and tag.

### Changed
- **Filament detail pagination**: the spool-life timeline and related Bambu print list on the filament detail page are now paginated to keep long histories readable.
- **Backup schema expanded again**: `/export` and `/import` now include shelf layouts and spool placements so the new storage prototype remains fully portable in backups.

### Fixed
- **Project stats chart axis**: the project consumption chart now keeps project names on the categorical axis instead of formatting them as gram values.

## [1.35.0] - 2026-03-28
### Added
- **Automatic purchase recommendations**: the statistics dashboard now calculates what to order next from the last 30/90 days of real usage, including suggested grams and spool counts.
- **Min/max stock guardrails**: filaments now support minimum and maximum stock thresholds, visual low-stock warnings, and reorder recommendations across inventory and stats views.
- **Filament detail with spool timeline**: each filament now has its own detail page with a timeline of manual usage, project consumption, and Bambu deductions.
- **Quality log per filament**: operators can store notes for stringing, adhesion, drying, print profiles, nozzle/bed temperatures, and general material experience directly on the filament.
- **Tags for filaments and projects**: lightweight tags can now be stored on both inventory items and projects and are surfaced in overview screens and settings.
- **Bulk inventory operations**: the inventory overview now supports selecting multiple filaments and applying shared actions such as spool changes, weight additions, tags, minimum stock updates, or deletion.
- **Bambu background sync**: Bambu Cloud integration now supports automatic background synchronization with configurable interval and last-sync status tracking.

### Changed
- **Statistics dashboard widgets**: added quick widgets for low stock, fastest-turning filaments, and most profitable quoted projects.
- **Backup schema expanded**: `/export` and `/import` now include stock thresholds, quality-log fields, tags, richer movement metadata, and Bambu auto-sync settings.
- **Inventory cards and list rows**: overview items now expose tags, threshold hints, reorder context, selection checkboxes, and direct access to the filament timeline.

## [1.34.0] - 2026-03-28
### Added
- **Customer pricing calculator**: the Calculator now supports customer-facing pricing with explicit base cost, margin percentage, margin amount, and final selling price.
- **Project quote saving**: calculated offers can now be saved directly to a project as reusable quotes linked to the chosen filament and pricing snapshot.
- **Quote export**: saved project quotes can be opened as a simple printable/exportable offer page suitable for PDF export or sharing with a customer.
- **Backup support for quotes**: project quotes are now included in `/export` and restored by `/import`, keeping customer pricing data part of the full application backup.

## [1.33.2] - 2026-03-28
### Changed
- **Navigation cleanup**: unified top-menu iconography so all primary sections use matching Font Awesome icons.
- **Navigation simplification**: removed the duplicate *Add Filament* menu entry because the Overview page already provides a prominent *New* action for adding stock.

## [1.33.1] - 2026-03-28
### Fixed
- **Statistics chart sizing**: fixed the new statistics dashboard charts so they render inside stable-height containers instead of stretching vertically without limit on page load.

## [1.33.0] - 2026-03-27
### Added
- **Statistics dashboard**: Added a new `/stats` page with usage and stock-addition charts, top material and project summaries, a recent stock additions feed, and a stock depletion forecast to help time reorders before filament runs out.
- **Inventory forecasting**: The dashboard now estimates days remaining for each filament based on the last 30 days of recorded consumption and highlights critical or soon-to-reorder stock.
- **Project and material analytics**: Daily usage trends, top materials, and project consumption are now aggregated from movement history, Bambu print deductions, and project filament usage to give a clearer picture of what is being consumed and where.

## [1.32.4] - 2026-03-27
### Fixed
- **Bambu filtered workflow without page reset**: saving filament mapping from the *Without filament* or *Not deducted* filtered views now updates the page via AJAX instead of a full refresh, so the active filter stays preserved while processing multiple jobs.
- **Bambu filter badge refresh**: filter pill counters now update immediately after AJAX mapping changes, keeping the visible counts aligned with the remaining cards.
- **Bambu AJAX mapping endpoint**: the job mapping route can now return JSON state for in-place UI updates, including the updated assignment/deduction state and fresh filter counts.

## [1.32.3] - 2026-03-27
### Fixed
- **Single-color Bambu jobs**: jobs with only one material slot are no longer treated as multi-material. The “Material Slots” section stays hidden and the normal single-filament mapping flow is used instead.
- **Single-slot assignment state**: for jobs with exactly one material slot, assigning a filament at the job level now also satisfies the unassigned state even without linking a project, and the job disappears from the *Without filament* filter as expected.
- **Single-slot state sync**: for one-slot jobs, job-level assignment and deduction now synchronize the underlying slot record as well, keeping filters, badges, and stored data aligned.

## [1.32.2] - 2026-03-27
### Fixed
- **Bambu filter consistency**: multi-material jobs now disappear from *Without filament* as soon as all material slots have an assigned filament, even when `job.filament_id` stays empty.
- **Bambu deduction filter consistency**: multi-material jobs now disappear from *Not deducted* as soon as all material slots are deducted, based on per-slot deduction state instead of the unused job-level flag.
- **Bambu badges and filters aligned**: the Bambu page now uses the same slot-aware logic for filter counts, filtered results, and on-card badges, preventing mismatched status between the pill filters and the visible job card.

## [1.32.1] - 2026-03-27
### Fixed
- **Bambu stock consistency**: Bambu job deduction and per-slot AMS deduction now use the same stock-decrement rules as the core inventory workflow, so `weight_remaining` and `quantity` stay synchronized when a spool boundary is crossed.
- **Atomic backup restore**: `/import` now runs inside a single database transaction. If any later stage of the restore fails, the whole import is rolled back instead of leaving partially restored data behind.
- **Regression coverage**: Added automated tests for Bambu quantity recalculation and full rollback behavior during failed imports.

## [1.32.0] - 2026-03-27
### Changed
- **Bambu — multi-material workflow**: for jobs with more than one AMS slot, the global single-filament dropdown is hidden in the mapping panel. Only the project and job name can be set at the job level; filament assignment is done exclusively per-slot.
- **Bambu — per-slot AJAX assignment**: assigning a filament to an AMS slot no longer refreshes the entire page. The slot row updates reactively in-place (Alpine.js + JSON endpoint) — stock deduction and "Deducted" badge update immediately without losing panel state.
- **Bambu — smart "Unassigned" badge**: for multi-material jobs the orange left border and "Unassigned" badge now reflect whether *all* AMS slots have a filament assigned (instead of checking the unused `job.filament_id` column). The "Deducted" badge for multi-material jobs appears only when every slot has been deducted.

## [1.31.1] - 2026-03-26
### Changed
- **Full-application backup**: `/export` now includes the entire application state — enumerations (brands, materials, colors), app settings (language, currency, theme, printer/energy settings), filament inventory, movement history, calculator print records, projects (with links and filament estimates), and Bambu printers + print jobs with per-slot material data. Bambu token is intentionally excluded for security.
- **Full-application restore**: `/import` handles all the above categories with referential-integrity ordering (enumerations → filaments → history → projects → Bambu) and idempotent "skip if exists" logic.
- **Instructions update**: `copilot-instructions.md` updated with correct model list, full route list, new Backup Schema Rule (rule 17), a requirement to keep the backup schema in sync with any future DB changes, and a versioning checklist item for the backup schema check.

## [1.31.0] - 2026-03-27
### Added
- **Interactive filament picker in project detail**: The filament add form now uses a fulltext search dropdown with a colored swatch showing the selected filament's color, matching the inventory filter style.
- **Edit and delete for project filament estimates**: Each ProjectFilament row in project detail now has a pencil (edit weight) and trash (delete) button, available for all rows including already-used ones.
- **Hours + minutes print time input**: Project create and edit forms now split the estimated print time into separate hours and minutes inputs for easier entry.
- **Interactive dropdowns with color swatches on add filament page**: The brand, material, and color fields on the "Add filament" form are now fulltext Alpine.js dropdowns. Color options show a colored swatch dot next to the name; the selected color is also previewed in the input trigger.
- **i18n**: Added `no_results` key (CS: "Žádné výsledky", EN: "No results").

## [1.30.1] - 2026-03-26
### Added
- **Filter bar on Bambu jobs page**: Three filter pills — *All*, *Without filament* (unassigned), *Not deducted* — with live counts. The active filter is preserved across pagination.
- **Unassigned visual highlight**: Bambu job cards with no filament assigned get an orange left border and an "Unassigned" badge, making the backlog immediately visible.
- **Multi-material badge**: Jobs with more than one AMS slot automatically display a purple *Multi-material* badge. Per-slot deduction was already supported; the badge makes it obvious which jobs need per-slot assignment.
- **Printer rename in Settings**: Each detected Bambu printer now has a *Rename* button in the Bambu section of Settings, with an inline form saved via the new `edit_bambu_printer` action.
### Fixed
- **Duplicate filament in project detail**: Deducting a Bambu job via "Deduct from stock" no longer auto-creates a `ProjectFilament` row when the filament wasn\'t previously added as an estimate. The Bambu jobs list at the bottom of project detail already shows this info; creating a redundant estimate row caused visual duplication.

## [1.30.0] - 2026-03-27
### Added
- **Printer & Energy Settings section**: `kwh_price` (CZK/kWh) and `printer_power` (W) moved from the Calculator page to a dedicated *Printer & Energy Settings* section in `/settings#printer-energy`. Values are saved via new `printer_energy_settings` action and read by the Calculator automatically.
- **Calculator simplified**: Removed `kwh_price` and `printer_power` input fields from the Calculator form. An info bar now shows the current values with a direct link to Settings.
- **Actual print cost in project detail**: Project detail now shows an *Actual Cost* badge (blue) next to the Estimated Cost badge. The actual cost is computed from all deducted Bambu print jobs: `(filament_price / weight_total × weight_grams) + (printer_power_kW × duration_hours × kwh_price)`.
- **Filament + color in Bambu jobs list**: Each Bambu print job in the project detail now shows a colored swatch and filament name next to the model name, making it clear which filament was consumed.

## [1.29.1] - 2026-03-26
### Fixed
- **Bambu status mapping**: Corrected `_STATUS_MAP` — Bambu Cloud API uses `status=2` for successfully finished prints (not "Paused"). `4=PAUSED`, `6=SLICING` added. Existing stored jobs with incorrect `PAUSED` status (raw=2) auto-corrected in DB.
- **Printer name missing**: Sync now reads `deviceName`/`deviceModel` (real Bambu Cloud API field names) instead of the non-existent `printerName`/`printerModel`. Backfills missing names from `raw_payload` on re-sync.
- **Bogus printer entries**: Fixed deduplication — `instanceId` (often `0` or a small integer) is no longer used as a device identifier. `deviceId` (the real hardware serial) is the primary key. Database cleaned of 25 incorrect auto-registered "printers".
- **Print duration**: `costTime` (seconds) is now stored in a new `cost_time` column on `BambuPrintJob` and displayed in human-readable format (e.g. `45min`, `1h 23min`) in the job list.
- **Interactive filament/project search**: Replaced plain `<select>` dropdowns in the Bambu job mapping panel with Alpine.js fulltext-search dropdowns, consistent with the inventory page filter pattern.
- **Per-slot AMS search dropdown**: The per-AMS-slot deduction form also uses a live-search filament picker.
- **Status label for SLICING/PREPARE**: Added `bambu_status_slicing` i18n key (CS: "Zpracování", EN: "Slicing").
- **Re-sync backfill**: `do_sync()` now also updates `printer_name` and `cost_time` on already-existing jobs when those fields were missing.

## [1.29.0] - 2026-03-25
### Added
- **Bambu Lab Cloud Integration**: New integration layer for syncing real print jobs from Bambu Lab Cloud (global and China regions), completely separate from existing project and inventory routes.
- **BambuPrintJob model**: Stores external job ID, printer name/model, model name, status, start/finish timestamps, consumed grams, project link (nullable), filament mapping, deduction flag, and raw API payload.
- **BambuJobMaterial model**: Per-AMS-slot material consumption with AMS ID, tray ID, color hex, material name, weight, filament mapping, and deduction flag.
- **BambuPrinter model**: Auto-discovered printers from sync, with device ID, friendly name, model, and notes.
- **Idempotent sync**: `/bambu/sync` (POST, AJAX) checks `external_id` uniqueness before inserting — same job is never stored twice; changed status is updated instead.
- **Manual sync button** on `/bambu` page with live AJAX feedback (added / updated / skipped counts).
- **Bambu jobs page** (`/bambu`): Paginated list of print jobs with status badges, per-job filament/project mapping panel, per-AMS-slot deduction forms.
- **Bambu Cloud settings section** in `/settings#bambu-cloud`: Token input, region selector (Global/China), connection status badge, detected printers list, disconnect button.
- **Post-print deduction**: Mapping a filament and clicking "Deduct from stock" reduces `weight_remaining`, creates a `MovementHistory` entry (action `bambu_print`), and creates a `PrintHistory` record.
- **Per-slot deduction**: Individual AMS slots can be mapped to different inventory filaments and deducted independently.
- **Auto-deduplication**: `deducted` flag on both `BambuPrintJob` and `BambuJobMaterial` prevents double-deduction.
- **Auto-register printers**: Printers encountered during sync are automatically added to `BambuPrinter`.
- **Navigation link**: "Bambu Lab Jobs" added to the top navigation bar.
- **ALTER TABLE migrations**: Safe fallback `ALTER TABLE` statements for `app_setting.bambu_token` and `app_setting.bambu_region`.
- **i18n**: All Bambu UI strings translated in both Czech (`cs`) and English (`en`).
- **Tests**: `tests/test_bambu.py` covers `_parse_ts`, `_resolve_status`, `do_sync` idempotency, status updates, per-material slot storage, weight derivation from AMS, printer auto-registration, API error handling, filament deduction route, double-deduction prevention, `PrintHistory`/`MovementHistory` creation, and the sync HTTP endpoint.

## [1.28.2] - 2026-03-24
### Fixed
- **MakerWorld Link Previews**: Added a fragment-safe reader fallback for pages protected by Cloudflare so MakerWorld model links can still generate title, description, and image previews on the project detail page.

## [1.28.1] - 2026-03-24
### Fixed
- **Hydrated Link Previews**: Link preview extraction now falls back to JSON-LD and embedded JSON script payloads, improving support for SPA pages such as MakerWorld model detail links that do not expose complete OpenGraph metadata.

## [1.28.0] - 2026-03-24
### Added
- **Upload Validation & Collision Safety**: Project uploads now accept only supported image and common 3D printing file formats, and stored filenames include a generated identifier so same-named uploads never overwrite each other.
- **Automated Tests**: Added regression coverage for link preview security/metadata extraction and project upload validation.

### Changed
- **Version Consistency**: Synchronized the runtime app version and README with the changelog.

### Fixed
- **SSRF Protection for Link Previews**: Link preview fetching now rejects localhost, loopback, and non-public targets before any request is made, including redirect targets.
- **Richer Link Preview Metadata**: Preview generation now resolves redirected URLs, supports OpenGraph/Twitter/basic metadata fallbacks, and converts relative image URLs to absolute ones for card rendering.
- **Inline Project Images**: Project gallery images are now served inline instead of download-only so previews and the lightbox render correctly.

## [1.27.1] - 2026-03-24
### Added
- **Project Configuration**: Added a comprehensive `.gitignore` file to prevent tracking of temporary files, virtual environments, and local data.

## [1.27.0] - 2026-03-22
### Added
- **Image Lightbox**: Added a fullscreen Alpine.js powered lightbox to view project images intuitively without leaving the page.
- **Rich Link Previews**: Integrated OpenGraph metadata scraping so external project links automatically generate rich preview cards with thumbnails and descriptions.

## [1.26.0] - 2026-03-22
### Added
- **Print Projects Feature**: Added a comprehensive 3D printing job management system accessible via the main navigation menu. It allows tracking of client projects, due dates, descriptions, statuses (NEW, PRINTING, DONE), and estimated print times.
- **Image Gallery**: Interactive drag and drop area for multiple concurrent image uploads on the project detail, complete with an image gallery and preview thumbnails.
- **Print Cost Calculator**: Dynamic project cost calculation based on assigned filaments.
- **Project File Attachments**: Users can now securely upload model/slice files (e.g., `.3mf`) and embed dynamic external URLs.
- **Filament Planning Integration**: Projects seamlessly connect to the core inventory database. Users can pre-plan required filaments per project and deduct the planned amounts from stock smoothly with a single click.
### Fixed
- **I18n Language Bug**: Fixed a bug where several texts on project views remained hardcoded in Czech instead of fully switching to English.
- **Delete Confirmation Dialog**: Corrected the terminology used in the delete project confirmation modal from "filament" to "project".
- **Project inputs visibility**: Fixed an issue where input fields on the project creation and edit screens were incorrectly styled with a dark background even when the light theme was active.

## [1.25.2] - 2026-03-07
### Changed
- **Optimized Database Aggregations**: Replaced in-memory Python aggregations for total spools, remaining weight, and value calculations with optimized SQL aggregations, drastically reducing memory usage for large inventories.
- **Eager Loading for Filament Queries**: Implemented `joinedload` to eliminate the N+1 query problem when fetching filament lists, significantly improving dashboard load times.

### Fixed
- **Percent Sort Bug**: Fixed the sorting algorithm for the "Percent" metric. It now properly sorts across all dataset pages using a SQL-native formula (including division-by-zero protection) instead of sorting only the current active paginated chunk in Python.
- **Exception Logging**: Improved error visibility by securely adding `app.logger.error` traces in `_safe_alter` database migration loops and backup import routines.

## [1.25.1] - 2026-03-05
### Changed
- **Settings page UI/UX redesign**: Rearranged the global application settings (Currency, Language, Items per page, Debug Mode) into a dedicated vertical card ("General Settings") inline with the other sub-dictionaries to improve visual cleanliness and reduce header clutter.

### Fixed
- **API module missing dependency**: Fixed a 500 fatal backend error originating from missing `AppSetting` import inside the `api.py` router logic when applying the new items per page limitation. The AJAX endpoints are fully stable again.

## [1.25.0] - 2026-03-05
### Added
- **Pagination user settings**: The number of items displayed per page on the overview is now customizable from the settings page (choices: 12, 24, 48, 96).

### Fixed
- **Pagination display enhancement**: Corrected the visual structure of the pagination component so page numbers are actively displayed and highlighted. Users will now see direct page numbers (e.g., `< 1, 2, ... 4 >`) instead of just left and right navigational arrows. Database structure properly adapts with the updated schema upgrade loop logic.

## [1.24.0] - 2026-03-05
### Fixed
- **Dynamic Alpine.js Pagination**: The manual pagination block on the inventory overview page now accurately responds to fulltext search filtering without requiring a full page refresh. Users no longer get disconnected pagination controls when manipulating filters.
- Clarified expected pagination constraints on page loading thresholds (limit is set securely at 12 items).

## [1.23.0] - 2026-03-05
### Added
- **Clear all movement history button**: New red button on the Movement History page allows users to delete the entire movement history at once. Button requires confirmation dialog before proceeding ("Are you absolutely sure you want to delete the ENTIRE movement history? This action cannot be undone.") to prevent accidental data loss.
- Button is positioned next to the per-page selector with trash icon for visual consistency.

## [1.22.0] - 2026-03-05
### Added
- **Fulltext search filters on inventory page**: Brand, Material, and Color filters now support real-time text search (typing instantly narrows options), matching the behavior of the calculator's filament picker. Displays matching options in a dropdown with visual feedback and checkmarks for active selections.
- **Color filter visual enhancement**: Color filter dropdown now shows colored swatches next to each color name for quick visual identification.
- **Low-stock warning indicators**: New visual alerts for filaments:
  - Red "Out of Stock" badge (card view top-right; list view icon) when quantity reaches 0.
  - Orange "Low Stock" badge/icon when remaining weight drops below 20% of total capacity.
  - Applied consistently across both card and list view modes.

### Fixed
- **Critical HTML structure bug in list view**: Fixed missing closing `</div>` for the row wrapper in the list view loop, which caused DOM nesting and catastrophic layout collapse (items appearing on top of each other). This also resolved the modal null error (`Cannot set properties of null`) when interacting with list view items.
- **Alpine reactive flush timing race condition**: Added explicit `classList` synchronization in `fetchContent()` before `innerHTML` insertion, ensuring layout classes are correct immediately when switching between card and list views via AJAX (fixes 3-column grid appearing briefly in list mode after card view).
- **Alpine.js x-cloak visibility flash**: Added missing `[x-cloak] { display: none !important; }` CSS rule in base.html, preventing filter sections from briefly appearing before Alpine.js initializes.

## [1.20.1] - 2026-03-05
### Fixed
- **Reset/Clear filter button is now always visible**: Button no longer disappears when no filters are active. Instead, it displays with a disabled state (grayed out) when no filters are selected, and becomes enabled when filters are applied.
- Button properly toggles between enabled and disabled states via JavaScript when filters are applied or cleared without page reload.

## [1.20.0] - 2026-03-05
### Changed
- **Filtering is now fully interactive (AJAX-based) without page reload**: Brand, Material, and Color filters now update the inventory list instantly as you change selections.
- **Filter apply button is no longer needed** and has been removed. Filters are applied automatically on selection change.
- **Reset/Clear filter button now uses AJAX** instead of page navigation, preserving current sorting and view mode.
- **Filter state is maintained during view mode and sort changes** to provide seamless user experience.

## [1.19.2] - 2026-03-05
### Fixed
- **"Sort by" quick button section is now hidden in list view**: The "Sort by" quick action buttons no longer appear when switching to list view mode, as users can sort directly by clicking on column headers instead.
- Hide/show of sort-by-section is managed via JavaScript visibility toggle when view mode changes.

## [1.19.1] - 2026-03-02
### Fixed
- **List view header now displays translated column names**: Column headers in list view now properly show translated text (e.g., "Název", "Značka", "Kusy") instead of template tags.
- **Sort direction arrows now properly display in AJAX responses**: Arrow icons correctly update when switching views or sorting in list view.
- **Improved internationalization (i18n) for dynamic content**: Created global translation object (`listHeaderLabels`) to ensure proper translations in AJAX-generated content.

## [1.19.0] - 2026-03-04
### Changed
- **View mode toggle (card ↔ list) is now interactive (no page reload)**: Clicking the view toggle buttons now switches between card and list views dynamically via AJAX without reloading the page.
- Converted view toggle links from `<a>` tags to `<button>` elements with `onclick` handlers for AJAX triggering.
- View mode switches instantly while preserving current sort, filters, and page state.

## [1.18.0] - 2026-03-04
### Changed
- **Card view sorting is now interactive (no page reload)**: Clicking sort buttons now updates the card grid dynamically via AJAX without reloading the page.
- Added `/api/filaments-list` support for both card and list view modes — single endpoint handles both views.
- Converted sort button links from `<a>` tags to `<button>` elements with `onclick` handlers for AJAX triggering.
- Card view maintains same interactive experience as list view with smooth updates.

## [1.17.0] - 2026-03-04
### Changed
- **List view sorting is now interactive (no page reload)**: Clicking column headers or using sort buttons now updates the list dynamically via AJAX without reloading the page.
- Added `/api/filaments-list` endpoint for interactive sorting and filtering.
- Converted header links from `<a>` tags to `<button>` elements with `onclick` handlers for AJAX triggering.
### Fixed
- **Mobile list view now properly handles narrow screens**: Sort buttons remain functional on devices where column headers are hidden (`sm:hidden`).
- Improves UX on small screens by maintaining sorting functionality without page navigation.

## [1.16.0] - 2026-03-04
### Added
- Added "Subtract usage" action button to list view with modal dialog for weight input: users can now subtract filament in list view just like in card view.
- Modal dialog displays the selected filament name, accepts weight in grams with min/max constraints matching available weight, and has Cancel/Submit buttons.
- Dark mode styling applied to the modal dialog for consistent appearance.

## [1.15.1] - 2026-03-03
### Changed
- Removed duplicate sort buttons from list view: in list view, users now sort exclusively via clickable column headers (less visual clutter, prevents confusion).
- Sort buttons remain visible in card view where they provide the primary way to sort.

## [1.15.0] - 2026-03-03
### Changed
- Replaced sorting dropdown select with intuitive **quick sort buttons** — users now see all 6 sort options (Name, Brand, Pieces, Remaining, Capacity, Percent) as clickable chips.
- Sorting buttons display directional arrows: **↑** for ascending, **↓** for descending, **↕** for un-sorted options.
- Active sort button is highlighted in blue; inactive buttons are gray and hoverable.
- One-click sorting: no need to open a dropdown first — click the button to apply or toggle direction.
- Dramatically improved UX for both card and list views — sorting is now equally intuitive in both modes.

## [1.14.1] - 2026-03-03
### Changed
- Enhanced list view with clickable column headers: clicking a header toggles sorting direction (ascending ↔︎ descending).
- Column headers now display directional arrows (↑ / ↓) when that column is active.
- Sorting direction preference is fully preserved across pagination, filters, and view mode changes.

## [1.14.0] - 2026-03-03
### Added
- Added sorting feature on the overview page: users can now sort filaments by Name (A-Z), Brand (A-Z), Pieces (most), Remaining weight (most), Total capacity (most), and Percentage (most).
- Sort preference is preserved across pagination and filters.
### Fixed
- Fixed calculator result box visibility in dark theme: "Výsledek Vašeho Výpočtu" heading and result boxes now have appropriate dark mode background colors.

## [1.13.0] - 2026-03-03
### Fixed
- Fixed statistics on the overview page: total spools, remaining weight, and value are now calculated from **all filtered filaments**, not just the current page.
- Fixed missing translation key `'name'` (used in list view header) — added to both `cs` and `en` language dicts.
### Changed
- Replaced all deprecated `Model.query.get(id)` calls with `db.session.get(Model, id)` throughout the codebase.
- Replaced all deprecated `Model.query.get_or_404(id)` calls with `db.get_or_404(Model, id)`.
- Refactored `inject_translations()` context processor to call `get_settings()` once per request instead of issuing three separate DB queries.
- Moved `import math` from inside `use_filament()` function body to the top-level imports.
- Removed unused `session` import from Flask imports.
- Removed legacy `action == 'theme'` handler from the settings route (theme changes are handled exclusively by the `/toggle-theme` endpoint).
- Fixed indentation inconsistency on the `'title'` key in both language dicts in `messages.py`.
- Translated remaining English code comment in add route to Czech.

## [1.12.0] - 2026-03-02
### Added
- Added header row to list view in the overview page with column labels (Name, Brand, Quantity, Remaining, Capacity, Percentage, Actions).
- Added persistence for view mode preference (card/list): user's chosen view is now automatically saved and restored when returning to the overview page.
### Changed
- Improved list view layout with more compact grid system and reorganized columns for better readability.
- First column in list view (Name) now has expanded width to accommodate longer filament names without truncation.
- Action buttons are now positioned at the far right of each row for consistent and easy access.
- Header row is sticky on desktop views for easier navigation through large lists.

## [1.11.1] - 2026-03-01
### Changed
- Improved list view layout on the overview page: Information is now organized into distinct columns (Name, Material, Quantity, Remaining, Capacity, Percentage) instead of being grouped together, providing better readability and data organization.
- List view is now more compact and uses a responsive grid layout with hidden columns on mobile devices (Material and Capacity columns are hidden on small screens for better mobile experience).
- Action buttons remain fixed on the right side of each row for consistent access.

## [1.11.0] - 2026-03-01
### Added
- Added view toggle on the overview page to switch between card view (grid layout with detailed cards) and list view (minimalist row-based layout).
- Added pagination to the overview page, allowing users to browse large filament inventories in manageable chunks (default: 12 items per page).
- View toggle preference and pagination controls preserve applied filters when switching between views or pages.
- New card view displays filament details with progress bars, capacity information, and action buttons in a visual grid layout (3 columns on desktop).
- New list view displays each filament in a compact row format with the color indicator, name, material, quantity, remaining weight, capacity, and action buttons.

## [1.10.0] - 2026-03-01
### Added
- Added light/dark theme toggle available on all pages (in the navigation bar).
- Users can now switch between light mode and dark mode at any time while browsing the application.
- Theme preference is persisted in the database, automatically loading the user's chosen theme on every visit.
- Comprehensive dark mode styling with improved contrast and readability for reduced eye strain.
### Fixed
- Fixed theme toggle button behavior: users now remain on the same page after changing theme instead of being redirected to settings.
- Fixed dark mode input visibility: all input fields now have proper dark backgrounds and light text in dark mode for full readability.

## [1.9.0] - 2026-03-01
### Added
- Added comprehensive debug logging to all major application actions, including filament CRUD operations, settings modifications, calculator functions, and import/export operations.
- Debug messages are now displayed in the Docker container logs when DEBUG logging mode is enabled in Application Settings (Gunicorn output).
- Each loggable action now includes detailed context: operation type, entity names, before/after values, and operation results.

## [1.8.4] - 2026-03-01
### Changed
- Switched from Flask's built-in development server to Gunicorn (production WSGI server) in the Docker container to ensure true production readiness and fix security/performance warnings.

## [1.8.3] - 2026-03-01
### Fixed
- Fixed bug in filament addition where `db.session.commit()` and redirection were missing, causing the new filament not to appear in the overview.

### Added
- Added an option in Application Settings to toggle DEBUG logging mode dynamically.

## [1.8.2] - 2026-03-01
### Added
- Added total inventory monetary value calculation to the main dashboard overview, displaying active capital tied in filaments.

## [1.8.1] - 2026-03-01
### Fixed
- Fixed the visual sign logic representing the operational cost of filament movements in History (Added filament now renders as a visually positive value, deleted filament renders as negative value).

## [1.8.0] - 2026-03-01
### Added
- Created a new Filament Movement History page that tracks precisely when and how much material was added or removed.
- Implemented automatic logging for stock operations (e.g. subtracting material, adding spools, making adjustments).
- Fully paginated logging system using 10/20/50/100 records selection.

## [1.7.0] - 2026-03-01
### Added
- Added combinatorial filters to the main dashboard. Users can now filter their filament spools by Brand, Material, and Color simultaneously.

## [1.6.0] - 2026-03-01
### Added
- Upgraded the Print Calculator's simple filament dropdown into an interactive, live full-text search input component. Uses fast JS DOM manipulation to filter filaments by name, brand, or material instantly.

## [1.5.0] - 2026-03-01
### Added
- Added global Currency Selection setting (CZK, USD, EUR) to the Settings page. This directly modifies how strings and costs are displayed natively everywhere in the main index list and in the precise printing calculator view.
### Fixed
- Fixed currency formatting order on the dashboard index page (e.g., from `Cena 230.00 za 1000 g CZK` to `Cena 230.00 CZK za 1000 g`).

## [1.4.0] - 2026-03-01
### Added
- Added Database Import & Export functionalities (via JSON structure). Users can now natively download and upload back their complete settings/filaments/dictionaries list.

## [1.3.1] - 2026-03-01
### Added
- Added `.github/copilot-instructions.md` to persist project context, development rules, and standard prompts for GitHub Copilot.

## [1.3.0] - 2026-02-28
### Added
- Added calculation history feature to the Print Calculator (tracking past print jobs, used filament, weight, and total cost).
- Added an option to delete individual calculation history logs.

## [1.2.2] - 2026-02-28
### Fixed
- Reverted text shortenings for print weight and fixed layout using CSS grid `items-end` to perfectly align inputs on the Calculator page.

## [1.2.1] - 2026-02-28
### Fixed
- Fixed layout wrapping issue on the Calculator page in Czech language by shortening the text.

## [1.2.0] - 2026-02-28
### Added
- Possibility to delete individual dictionaries items (Brand, Material, Color) in Settings (only if they are not used).
- Display semantic App Version in the footer instead of the static text.

## [1.1.0] - 2026-02-28
### Added
- Electricity cost inclusion in the Print Calculator (Print time, kWh price, printer power).
- Added `-` (minus) button to easily decrease the spool quantity of a filament on the Overview page.
- Allowed editing existing records in Settings (Brands, Materials, Colors).
- Quantity of spools now decrements automatically when enough filament is used (e.g. crossing below previous spool capacity threshold).
- Basic semantic versioning and Changelog initialization.

## [1.0.1] - 2026-02-28
### Added
- Internationalization (i18n) for CZ/EN.
- Added spool quantity tracking.

## [1.0.0] - 2026-02-28
### Added
- Initial release of FilamentApp.
- Filament management, Print calculator, basic settings.
