# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
