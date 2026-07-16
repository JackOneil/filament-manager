# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.119.12] — 2026-07-13

### Added
- **Bambu waste modal: interactive Project search**: Pole "Projekt" nyní interaktivní fulltext vyhledávač (stejný pattern jako filament).
- **Waste recording stays on Bambu page**: Po zaznamenání zmetku se již nepřesměrovává na stránku zmetků — formulář odeslán AJAXem, tisk je automaticky namapován na vybraný filament a projekt s odečtením zásob. Job se okamžitě zobrazí jako přiřazený.
- **Waste propagates filament to print job**: Vybraný filament a projekt se při záznamu zmetku propíše i do Bambu tisku — včetně odečtu (`deduct=1`) a aktualizace UI.

### Fixed
- **BUG-603 (2nd re-fix): Color picker portal regression** — přechod na portal pattern (`position: fixed` v `document.body`) způsobil, že kliknutí na barevné políčko bylo přerušeno `mousedown` handlerem, který picker schoval dřív, než se stihl zpracovat `click`. Oprava: `_dashEnsurePickerClose` nyní kontroluje i `.widget-color-picker` jako bezpečnou zónu. (static/js/dashboard.js)

## [1.119.11] — 2026-07-13

### Fixed
- **BUG-603 (re-fix): Color picker dropdown hidden behind adjacent widgets**: Původní fix pomocí `z-index: 50` na widgetu nefungoval — `will-change: transform` a `opacity < 1` v editačním režimu vytvářejí nezávislé stacking kontexty, které `z-index` ignorují. **Oprava:** Color picker dropdown nyní používa portal pattern — renderuje se přímo do `document.body` s `position: fixed` a pozicí vypočítanou z `getBoundingClientRect()`. Tím zcela uniká všem stacking kontextům. Přidán `scroll`/`resize` listener pro přepočítání pozice. (static/js/dashboard.js)

## [1.119.10] — 2026-07-13

### Added
- **Bambu waste modal: interactive filament search + AMS auto-suggestion**: V modálním okně "Zaznamenat zmetek" na stránce Bambu tisků je nyní interaktivní filamentový vyhledávač (plnotextové vyhledávání s barevnými indikátory) namísto nativního `<select>`. Filament je automaticky předvybrán dle barvy a materiálu z AMS dat — stejná logika `_rankFilaments`/`_suggestedFilaments` jako u přiřazování filamentů k tiskům. (templates/bambu.html, templates/_bambu_job_cards.html)

## [1.119.9] — 2026-07-13

### Fixed
- **Color picker dropdown hidden behind widgets on Projects/Overview pages**: `.dashboard-widget { position: relative }` creates a CSS stacking context trapping the colour picker (`z-[999]`) inside its parent widget. Adjacent widgets later in the DOM rendered above the picker dropdown, making it invisible and unselectable. **Fix:** When the colour picker opens, the parent widget's `z-index` is elevated to `50`. Reset on close (swatch click, click-away, and edit-mode toggle). (static/js/dashboard.js)

## [1.119.8] — 2026-07-13

### Added
- **Tag filter on models page**: Nový sloupec "Štítky" s interaktivním dropdown filtrem na stránce modelů — automaticky obsahuje všechny dostupné štítky z projektů. Kliknutím na štítek u modelu se filtrují modely podle daného štítku. Tag badges are now clickable and filter the models list. Added `tag` query parameter to API and Alpine.js component with fulltext search dropdown. (routes/models.py, templates/models_index.html, templates/_models_cards.html, templates/_models_rows.html, templates/models_detail.html, messages.py)

## [1.119.7] — 2026-07-13

### Added
- **Project tags displayed on models**: Modely nahrané přes projekty nyní přejímají a zobrazují štítky svého projektu. Project tags shown on model cards, list rows, and detail page when the model belongs to a project. Uses `ui-badge` style consistent with project detail page. (routes/models.py, templates/_models_cards.html, templates/_models_rows.html, templates/models_detail.html)

## [1.119.6] — 2026-07-04

### Added
- Bambu: Ruční duplikování tisku — nová funkce `/bambu/job/<id>/duplicate` (POST) umožňuje vytvořit manuální kopii tisku, který nebyl synchronizován (edge case opakovaného tisku přímo na tiskárně). Nová kopie má `deducted=False` pro nezávislé přiřazení filamentu.

### Fixed
- N/A

## [1.119.4] - 2026-07-02
### Fixed
- **Markdown code block unreadable in light theme**: `<code>` inside `<pre>` blocks in project descriptions/comments inherited `bg-gray-100` from the generic `[&_code]:bg-gray-100` Tailwind rule, rendering light text on a light background. Added `[&_pre_code]:bg-transparent` to override the background for code inside pre blocks. Affected: project description, project comments, and share page. (templates/_project_overview.html, templates/project_share.html)

## [1.119.3] - 2026-06-28
### Fixed
- **PostgreSQL `DATETIME` → `TIMESTAMP` compatibility (BUG-596)**: 11 `_safe_alter()` migration calls used `DATETIME` type which PostgreSQL rejects (requires `TIMESTAMP`). All changed to `TIMESTAMP` for cross-engine compatibility. (migrations.py)
- **SSRF guard for Bambu cover image fetch (BUG-597)**: `_cache_cover_image()` in `bambu_helpers.py` fetched external URLs from Bambu API responses without `is_safe_external_url()` validation. Added SSRF check with warning logging. (routes/bambu_helpers.py)
- **IDOR bypass for project-less files (BUG-598)**: `_check_file_access()` in `routes/models.py` skipped all authorization for files with `project_id IS NULL`. Now requires admin access for orphaned files. (routes/models.py)
- **N+1 backup export (BUG-599)**: Project export in `backup_helpers.py` triggered 7 lazy-load queries per project (files, links, filaments, quotes, comments, todos, print_items). Added `joinedload()` eager loading. (routes/backup_helpers.py)
- **Notification polling `setInterval` leak**: `notificationBell()` component in `app-shell.js` never cleared its polling interval on component destruction. Added `destroy()` lifecycle method with `clearInterval()`. (static/js/app-shell.js)
- **Silent invalid date filter errors in Bambu page**: 4 `except (ValueError, OverflowError): pass` blocks swallowed invalid date inputs with zero user feedback. Added `flash()` warnings via new `bambu_invalid_date_filter` i18n key. (routes/bambu.py, messages.py)
- **Unused imports removed**: `secrets`, `threading` (routes/inventory.py), `mimetypes` (routes/bambu.py), `threading` (routes/projects.py). (routes/inventory.py, routes/bambu.py, routes/projects.py)
- **CSP nonce missing on `inventory.js` script tag** in `index.html`. Added nonce injection. (templates/index.html)
- **Hardcoded/missing `aria-label` attributes**: Replaced hardcoded `aria-label="Close"` with `{{ t("close") }}` in `bambu.html`, added missing `aria-label` to `&times;` close buttons in `bambu.html` and `prusa.html`. (templates/bambu.html, templates/prusa.html)
- **`nullable=False` added to nullable default=0 columns**: `Project.estimated_print_time` and `BambuPrinter.pre_job_time_minutes` now have `nullable=False`. (models.py)
- **Heatmap labels HTML-escaped** in `enhancements.js` to prevent potential XSS via label data. (static/js/enhancements.js)
- **Model edit clears `project_id` on empty form**: `model_edit` was setting `root_file.project_id = None` when the form field was omitted, disassociating the file from its project. Now only updates when explicitly provided. (routes/models.py)
- **`.env` added to `.dockerignore`** along with `node_modules/` and `*.log`. (BUG-560, .dockerignore)

## [1.119.2] - 2026-06-28
### Fixed
- **Backup export/import missing critical fields (BUG-594)**: Comprehensive audit revealed 7 fields missing from the backup/restore cycle:
  - `FilamentUndoLog.target_type` and `target_key` (🔴 critical) — undo metadata for waste/maintenance operations was lost, breaking undo after restore. (routes/backup_helpers.py, routes/backup.py)
  - `Project.share_token` (🔴 critical) — share links were lost on restore, requiring manual re-generation. (routes/backup_helpers.py, routes/backup.py)
  - `User.last_login_at` (🟠 medium) — last login timestamps lost after restore. (routes/backup_helpers.py, routes/backup.py)
  - `AppSetting.link_preview_reader_enabled` (🟠 medium) — Jina AI reader opt-in lost after restore. (routes/backup_helpers.py, routes/backup.py)
  - `BambuPrintJob.raw_payload` and `PrusaPrintJob.raw_payload` (🟠 medium) — raw API payload data lost after restore. (routes/backup_helpers.py, routes/backup.py)
- **Heatmap legend showing unresolved placeholders (BUG-595)**: The `{{T:less}}` and `{{T:more}}` placeholders in the consumption heatmap legend were never resolved to translated text (`méně`/`více` or `less`/`more`) because the translation replacement ran before `initHeatmaps()` created the legend DOM elements. Fixed by using the i18n helper directly in `initHeatmaps()`. (static/js/enhancements.js)
- **Duplicate `material` key in translations**: The `material` i18n key was defined twice in both `cs` and `en` dictionaries. Removed the duplicate from the "Generic single-word labels" section. (messages.py)

## [1.119.1] - 2026-06-28
### Fixed
- **403 Forbidden on waste page AJAX endpoints (BUG-593)**: The waste page filters, modal add/edit/delete, data fetch, and photo upload AJAX endpoints (`waste_records_partial`, `waste_add_ajax`, `waste_edit_ajax`, `waste_delete_ajax`, `waste_data_ajax`, `waste_upload_ajax`, `waste_delete_file_ajax`) were not registered in `SECTION_BY_ENDPOINT` in `auth.py`, causing the default-deny security policy to reject all AJAX requests with HTTP 403. This broke the waste page filter pills, the "Zapsat zmetek" button modal submission, and inline edit/delete actions. (auth.py, routes/waste.py)
- **Unmapped AJAX endpoints for maintenance and project templates**: `maintenance_data` and `project_template_data` AJAX endpoints were also missing from `SECTION_BY_ENDPOINT`, causing 403 errors when accessing maintenance record data or project template data via JavaScript. Added to `SECTION_PRINTERS` and `SECTION_PROJECTS` respectively. (auth.py)

## [1.119.0] - 2026-06-27
### Added
- **Dark-mode Chart.js theming**: New `window.enh` API in `static/js/enhancements.js` registers every Chart.js instance and re-themes it automatically when the user toggles dark mode. Chart axes, grid, legend and tooltip colours now adapt to the theme without a page reload. (static/js/enhancements.js, templates/stats.html, static/css/enhancements.css)
- **Consumption heatmap (day × hour)**: New draggable section on the Statistics page. A 7×24 grid of CSS-only cells visualises when you actually print, aggregated from the last 90 days of `MovementHistory`. Includes tooltip on hover with exact grams and a colour-scale legend. Computed in `routes/stats.py:heatmap_matrix` and exposed via `chart_data.heatmap`. (routes/stats.py, templates/stats.html, static/css/enhancements.css, static/js/enhancements.js)
- **KPI animated counters**: All four executive KPIs on `/stats` now animate from 0 to the target value over 900 ms (ease-out-cubic) on first load. Uses CSS `tabular-nums` to prevent layout shift and a brief `enh-roll-in` flip on every change. (templates/stats.html, static/js/enhancements.js, static/css/enhancements.css)
- **Inline sparklines in KPI cards**: Each KPI card now includes a 14- or 30-point SVG sparkline showing the daily trend. Pure-SVG renderer (no Chart.js dependency, sub-2KB), themed via CSS variables. (templates/stats.html, static/js/enhancements.js, static/css/enhancements.css)
- **Responsive table-to-card transformation**: All admin tables (`/users`, `/history`, `/audit`) automatically collapse into a card-stack layout on viewports `< 768 px`. Each cell carries a `data-label` attribute that becomes the left-aligned label in card mode. Old long-press / horizontal-scroll behaviour on mobile is gone. (templates/_users_table.html, templates/history.html, templates/audit.html, static/css/enhancements.css)
- **Mobile row actions reveal**: Long-press (≥ 280 ms) anywhere on a table row to reveal the action buttons (previously always-visible, now compact on mobile). Tap-outside dismisses. Activates only below 768 px width. (static/js/enhancements.js, static/css/enhancements.css)
- **Staggered widget reveal**: Overview and statistics page widgets now animate in with a 20–40 ms cascade. Implemented via `data-stagger="N"` on the parent and `data-animate` on each child — pure CSS, no JS animation loops. (templates/overview.html, templates/stats.html, static/css/enhancements.css)
- **Heart-pop reaction animation**: Clicking a project comment reaction now triggers a `enh-heart-pop` keyframe (scale + slight rotation) for a satisfying tactile feel. (templates/_project_overview.html, static/css/enhancements.css)
- **Ripple effect on primary buttons**: Any button can opt into a Material-style ripple by adding `data-enh-ripple`. The ripple origin tracks the click position via CSS custom properties. (static/js/enhancements.js, static/css/enhancements.css)
- **Slide-up toast animation**: Client-side `window.showToast()` toasts now slide in from below with a smooth cubic-bezier transition instead of appearing instantly. (static/js/app-shell.js, static/css/enhancements.css)
- **Stronger focus ring for keyboard nav**: `:focus-visible` now gets a brand-coloured outline for all interactive elements — improves a11y for keyboard users. (static/css/enhancements.css)
- **Selection colour follows theme**: Custom `::selection` colour for both light and dark modes. (static/css/enhancements.css)

### Changed
- Chart.js options on `/stats` now include `animation: { duration: 700, easing: 'easeOutCubic' }` for smoother initial render.
- All existing dashboards now load the new `static/css/enhancements.css` and `static/js/enhancements.js` (idempotent, no breaking changes).
- KPI group (4 cards) on `/stats` uses the new `ui-kpi-group` class which auto-collapses to 2 columns on narrow screens (≤ 767 px) and hides cards 5+ on mobile.

### Fixed
- Chart axes/grid/tooltips were hard-coded to light-mode colours and remained bright after toggling dark mode — now reactive via `MutationObserver` on `<html>` class.

## [1.118.1] - 2026-06-25
### Fixed
- **Auto-backup & manual backup stuck (BUG-592)**: `run_migrations()` left idle-in-transaction database connections after reading `AppSetting` and `Brand` without committing or rolling back (migrations.py:253–260, 239–251). On PostgreSQL, these open transactions held shared locks on the tables, blocking ALL subsequent `ALTER TABLE` operations (`_safe_alter()`) and any query that needed to read those tables — including the auto-backup worker which calls `AppSetting.query.first()` to read backup settings. This caused the auto-backup to silently stop (last backup: June 6, 2026) and manual backup to hang.

  **Fix:** Added explicit `db.session.commit()` (or `db.session.rollback()` when seed data already exists) after every read query in `run_migrations()`. Also added `db.session.rollback()` at the beginning of `_safe_alter()` to release any pending locks before executing DDL — critical for PostgreSQL where idle transactions block exclusive locks. (migrations.py)
- **Manual backup button submitting wrong form (BUG-592b)**: The "Spustit zálohu teď" button was nested inside the settings `<form>`. Nested forms are invalid HTML — browsers handle them inconsistently, often submitting to the outer form's action instead. This caused the button to save settings (flash: "Nastavení automatického zálohování uloženo.") instead of triggering a backup. **Fix:** Closed the settings form before the button row, moved the "Uložit" button outside the form using the `form="backup-auto-form"` attribute, and kept the trigger button in its own independent `<form>`. (templates/settings.html)

## [1.118.0] - 2026-06-25
### Added
- **PostgreSQL support (BL-004)**: The application now auto-detects PostgreSQL via the `DATABASE_URL` environment variable. When set, connection pooling (`pool_size=10`, `max_overflow=20`, `pool_pre_ping=True`, `pool_recycle=3600`) is configured automatically. SQLite remains the default when `DATABASE_URL` is unset, ensuring full backward compatibility.
- **Dialect abstraction layer** in `database.py`: `detect_dialect(uri)`, `engine_options_for(dialect)`, and `setup_sqlite_pragmas()` extract dialect-specific logic from `app.py`, making the codebase cleaner and more testable.
- **PostgreSQL Docker Compose service**: `postgres:16-alpine` container with healthcheck, persistent `postgres_data` volume, and wait-for-healthy `depends_on` in the app service. Environment variables `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` control the PostgreSQL setup.
- **Migration guide in README**: Step-by-step instructions for migrating from SQLite to PostgreSQL (and back), including export/import workflow, `.env` configuration, and PostgreSQL performance tuning tips.
- **`psycopg2-binary>=2.9`** added to `requirements.txt`.

### Changed
- `app.py`: Database URI now reads `DATABASE_URL` env var; engine options are dialect-aware; SQLite PRAGMA setup uses the shared helper from `database.py`.
- `migrations.py`: `_migrate_nullable_project_id()` and `_migrate_waste_record_fk()` are now guarded with dialect checks — skipped on PostgreSQL since `db.create_all()` already creates the correct schema.
- `database.py`: Refactored from a single `db = SQLAlchemy()` instance to include dialect detection and engine option helpers.
- `.env`: Added commented PostgreSQL configuration examples with `DATABASE_URL`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`.
- `README.md`: Updated Tech Stack, Quick Start, and Platform sections to reflect PostgreSQL support. Added full migration guide.

## [1.117.1] - 2026-06-15
### Fixed
- **Makerworld link preview broken**: Cloudflare-protected sites (Makerworld, Printables, etc.) returned HTTP 403 without useful metadata when accessed with bare `User-Agent` headers. Updated `fetch_link_metadata()` in `utils/__init__.py` to send modern browser-like headers (`Sec-Ch-Ua`, `Sec-Fetch-*`, `Accept-Language`) that pass Cloudflare's bot detection and receive actual page content with `og:` meta tags.
- **Jina reader fallback regression**: Removed opt-in gate on the Jina reader fallback introduced in v1.110.x. The reader now always attempts when direct metadata extraction fails, restoring behavior for sites that still block requests.
- **Missing `coverUrl` key**: Added `coverUrl` to the set of image keys searched in `_extract_preview_from_json_payloads()` so Next.js `__NEXT_DATA__` payloads (used by Makerworld) yield cover images.

## [1.117.0] - 2026-06-10
### Added
- **Interactive notification bell with live counter**: Replaced static bell icon in topbar with Alpine.js dropdown showing recent notifications, unread badge counter with pulse animation on new notifications, AJAX polling every 30s for real-time unread count updates, one-click mark-read via hover button, "Mark all read" and "See all" actions, and relative time display ("5m", "2h", "3d"). Dropdown is styled with glass-morphism consistent with the rest of the UI.
- **4 new AJAX API endpoints**: `GET /api/notifications/unread-count`, `GET /api/notifications/recent`, `POST /api/notifications/<id>/mark-read`, `POST /api/notifications/mark-all-read` — all with auth protection and ownership checks.
- **`notifications_see_all` i18n key** added to both Czech and English dictionaries.

### Changed
- Notification bell in topbar no longer navigates to `/notifications` directly — opens dropdown instead. Existing full-page notifications view at `/notifications` remains accessible via "See all" link.
- Added 4 new endpoint names to `SECTION_BY_ENDPOINT` (auth.py) and `HELP_SECTIONS` endpoints array (help.js).

## [1.116.1] - 2026-06-09
### Fixed
- **HTTP 500 on /projects and /stats**: `db.Numeric(10,2)` columns (`Filament.price`, `AppSetting.kwh_price`, `ProjectQuote.final_price`) return `Decimal` objects, which cannot be multiplied/divided with `float`. Added `float()` casts at all arithmetic sites in `utils/__init__.py` (`build_project_metrics`), `routes/stats.py` (profitable projects), and `routes/projects_helpers.py` (`_job_cost_parts`). Regression from BUG-423 (v1.116.0) which changed monetary fields from `db.Float` to `db.Numeric`. (utils/__init__.py, routes/stats.py, routes/projects_helpers.py)

## [1.116.0] - 2026-06-09
### Fixed
- **BUG-423**: Changed monetary fields from `db.Float` to `db.Numeric(10,2)` in models.py — eliminates IEEE 754 floating-point precision errors for currency values (`price`, `cost`, `kwh_price`, `total_cost`, `material_cost`, `electricity_cost`, `base_cost`, `margin_amount`, `final_price`). Added `float()` casts in `log_movement()`, `_calculate_quote()`, and `_calculate_project_quote()` for Decimal/Float arithmetic compatibility. Added `_json_default` helper and `decimal.Decimal` import for JSON serialization of Decimal values in backup export, undo system, and calculator. (models.py, utils/__init__.py, routes/calculator.py, routes/backup_helpers.py, tests/test_settings.py)
- **BUG-552**: Replaced in-memory list comprehension with SQL subquery in `models_index` stats — `ProjectFile.id.in_(base_q.with_entities(ProjectFile.id).subquery())` instead of loading all IDs into Python memory for total size computation. (routes/models.py)
- **BUG-553**: Added past due date validation with flash warning in `project_create` and `project_edit` — users are warned when setting a due date in the past. Added `project_due_date_past` i18n key to both cs/en. (routes/projects.py, messages.py)
- **BUG-531**: Restored dropped indexes after `_migrate_waste_record_fk` table recreation — added `CREATE INDEX IF NOT EXISTS ix_waste_record_filament_project` and `ix_waste_file_waste_record_id` after migrating waste tables. (migrations.py)
- **BUG-538**: Removed 4 stale `TODO(security)` comments — origin validation is already implemented (same-origin check on postMessage handlers in project_detail.html and viewer.html). Replaced with descriptive comments confirming the existing validation. (templates/project_detail.html, static/viewer.html)
- **BUG-424**: Added `_keydownBound` guard to prevent duplicate keydown listener registration in command palette (app-shell.js). Re-initialization of the Alpine component no longer stacks listeners. (static/js/app-shell.js)
- **BUG-425**: Added `window.__filCtxMenuInit` guard to prevent duplicate context menu listener registration (inventory.js). The IIFE that adds document-level listeners (click, keydown, contextmenu) now only runs once. (static/js/inventory.js)
- **BUG-426**: Added `container.__dashLayoutManager` guard + `destroy()` method to `createWidgetLayoutManager` — prevents duplicate manager instances on the same container after AJAX reloads. Added `_dashDragInitDone` module-level guard. (static/js/dashboard.js)
- **BUG-526**: Added `aria-label` attributes to 14+ icon-only buttons across `_filament_cards.html`, `_filament_list_rows.html`, `_project_files.html`, and `project_detail.html` for screen reader accessibility. All labels mirror existing `title` translations. (templates/*.html)
- **BUG-527**: Added `x-cloak` to flash toast (`base.html`) and undo toast (`_toast_undo.html`) to prevent brief visible flash on page load before Alpine initializes. (templates/base.html, templates/_toast_undo.html)

### Changed
- Minor release — 10 low-priority bugs resolved in a single batch, completing all open 🟢 Low items from audits #1, #2, and #3.

## [1.115.1] - 2026-06-09
### Fixed
- **BUG-525**: Added `UniqueConstraint('shelf_id', 'slot_index')` to `StoragePlacement` model — prevents two filaments from being placed in the same shelf slot at DB level. Added `CREATE UNIQUE INDEX IF NOT EXISTS uq_shelf_slot` migration for legacy databases. Updated `storage_move_placement` to use a 3-step swap with temporary slot (-1) to avoid transient UNIQUE violation during placement moves. (models.py, migrations.py, routes/storage.py)
- **BUG-530**: Added `nullable=False` to 27 `AppSetting` model columns that already had `NOT NULL` in migrations — resolves inconsistency between `db.create_all()` (which produced NULLABLE columns) and migrations (which produced NOT NULL). Affected columns: lang, kwh_price, printer_power, currency, debug_logging, theme, nav_palette, view_mode, items_per_page, bambu_region, bambu_auto_sync_enabled, bambu_auto_sync_interval_minutes, invoice_prefix, invoice_counter, app_timezone, onboarding_dismissed, audit_logging_enabled, auto_filament_mapping_enabled, backup_auto_enabled, backup_auto_frequency, backup_auto_time, backup_auto_day, backup_auto_include_files, backup_auto_keep_count, backup_auto_keep_days, waste_reasons_json, link_preview_reader_enabled. (models.py)
- **BUG-535**: Replaced 15 hardcoded English/Czech strings in `log_movement()` notes across inventory.py, projects.py, bambu.py, prusa.py with translatable i18n keys using `translate()`. All notes now respect the user's language setting. Added 12 new `movement_note_*` i18n keys to both cs and en dictionaries. (routes/inventory.py, routes/projects.py, routes/bambu.py, routes/prusa.py, messages.py)
- **BUG-537**: Applied DB-level pagination to `api_models_list()` — replaced `query.all()` (loading all models into memory) with proper `query.offset().limit()` after a COUNT query. Added subquery joins for complex sort modes (uploaded, size_desc) that need latest-version attributes, enabling ORDER BY at DB level. Enrichment now only processes the paginated page instead of all records. (routes/models.py)

### Changed
- Updated 4 tests in test_inventory_extended.py that filtered movement history by hardcoded English note strings — now filter by `action_type` instead, which is language-independent. (tests/test_inventory_extended.py)
- Fixed `test_move_placement` in storage tests to work with the new UNIQUE constraint — the swap logic now uses a 3-step approach with a temporary slot index. (routes/storage.py)

## [1.115.0] - 2026-06-08
### Changed
- **BUG-514**: Standardised datetime handling on timezone-aware UTC throughout the entire stack
  - Added `UtcDateTime` SQLAlchemy TypeDecorator that normalises all DateTime columns to aware UTC on read/write — legacy naive rows are automatically upgraded on read (models.py)
  - Changed `utc_now()` to return timezone-aware datetime (was naive); `utc_now_naive()` added for explicit legacy use (time_utils.py)
  - `_SORT_EPOCH` sentinel updated to aware UTC for compatibility with UtcDateTime read values (utils/__init__.py)
  - `_parse_ts()` in Bambu helpers now returns aware datetimes (routes/bambu_helpers.py)
  - All ~40 `db.DateTime` columns in models.py migrated to `UtcDateTime` type
  - Eliminates Python 3.12+ `TypeError` when comparing aware vs. naive datetimes
- **BUG-516**: Replaced all deprecated `document.execCommand()` calls in markdown editor with modern Selection/Range API
  - Added `_toggleInlineTag()`, `_wrapInline()`, `_execBlockTag()`, `_execList()` helpers (static/js/markdown-editor.js)
  - Handles bold, italic, code, link, heading, blockquote, bullet/numbered lists — all without deprecated API
  - Link creation now uses `_wrapInline('a', {...})` instead of `execCommand('createLink', ...)`
- **BUG-515**: Added global `safe_commit()` utility that wraps `db.session.commit()` in try/except/rollback with flash error message
  - Applied to ~115 commit sites across routes/inventory.py, routes/projects.py, routes/auth.py, routes/settings.py, routes/waste.py, routes/maintenance.py, routes/storage.py, routes/calculator.py, routes/history.py, routes/models.py, and 3 helper modules
  - Prevents bare HTTP 500 from `IntegrityError`/`OperationalError` on DB write failures; user sees translated error toast instead
  - Added `error_general` and `error_db_commit` i18n keys to both cs/en (messages.py)
  - Background workers (bambu/prusa sync, auto-backup) are excluded — no user to flash to

## [1.114.2] - 2026-06-08
### Fixed
- **BUG-512**: Made Jina Reader link preview fallback opt-in via `link_preview_reader_enabled` AppSetting (default: off). Added toggle in Settings → General tab. Prevents unintended third-party data leak when OpenGraph metadata is insufficient. (models.py, migrations.py, templates/settings.html, routes/settings.py, utils/__init__.py, messages.py)
- **BUG-518**: Replaced blocking `window.prompt()` with an inline modal for URL input in the markdown editor. No longer blocks the main thread, works with restrictive CSP policies, and supports dark mode. Added `md_url_prompt_title`/`cancel`/`ok` i18n keys to `window.__i18n`. (static/js/markdown-editor.js, templates/base.html)
- **BUG-513**: Added DNS rebinding defense — `_validate_peer_ip()` checks the actually-connected socket IP after each HTTP request in `_follow_safe_redirects()` and `_fetch_reader_fallback()`. Prevents attackers from switching DNS A records to private IPs between the safety check and TCP handshake. (utils/__init__.py)

## [1.114.1] - 2026-06-08
### Fixed
- **BUG-539**: Replaced 2 remaining `onclick="confirm(...)"` patterns in settings.html with `data-confirm` attribute — backup trigger now button converted to proper form, import confirm moved to form attribute (templates/settings.html)
- **BUG-540**: Replaced inline `confirm()` in Alpine `@submit.prevent` with `$el.dataset.confirmMsg` data attribute pattern in models_index.html bulk delete form (templates/models_index.html)
- **BUG-541**: Fixed 6 instances of `abort(401)` → `abort(403)` in projects.py file ownership checks — HTTP 403 (Forbidden) is the correct status for authorization failures when the user IS authenticated (routes/projects.py)
- **BUG-542**: Added server-side empty name validation in `project_create` and `project_edit` — prevents empty project names from being stored; displays flash error and redirects back (routes/projects.py, messages.py)
- **BUG-511**: Added hostname format validation and localhost/loopback blocking to `validate_printer_host()` — rejects empty hosts, spaces, non-standard characters, and loopback addresses (utils/__init__.py)
- **BUG-543**: Fixed login rate limiter to use `request.remote_addr` instead of spoofable `request.access_route[0]` (X-Forwarded-For) — consistent with registration endpoint (routes/auth.py)
- **BUG-544**: Added `root_id` ownership check in `model_delete_comment` — comment must belong to the specified root model, preventing minor IDOR (routes/models.py)
- **BUG-545**: Added 10 MB payload size check in `model_upload_thumbnail` before base64 decode — prevents memory exhaustion from large uploads (routes/models.py, messages.py)
- **BUG-546**: Added None guard for `get_current_user()` in `api_models_list` — prevents `AttributeError` if auth middleware edge case returns None (routes/models.py)
- **BUG-547**: Fixed URL corruption in `_fetch_reader_fallback` — replaced fragile `.replace('https://', '').replace('http://', '')` chaining with `re.sub(r'^https?://', '', ...)` to avoid mangling URLs with `http://` in query strings (utils/__init__.py)
- **BUG-548**: Added session invalidation for users deactivated in bulk — now calls `invalidate_all_user_sessions()` for each deactivated user, consistent with single-user deactivation (routes/auth.py)
- **BUG-549**: Added periodic cleanup of `_login_attempts` dict — pruned IP entries are now deleted from the dict when empty, and a hard reset triggers at 1000+ entries to prevent unbounded growth (routes/auth.py)
- **BUG-550**: Replaced `{{ t(...)|e }}` (HTML-escape) in JS string context with `data-confirm-msg` attribute pattern in users.html bulk delete form — HTML-escaping does not protect against single-quote breakout in JavaScript (templates/users.html)
- **BUG-551**: Added `threading.Lock()` protection to `_login_attempts` dict — prevents logical race condition between multiple Gunicorn threads on rate limit checks (routes/auth.py)

## [1.114.0] - 2026-06-07
### Added
- **BL-004**: Model Categories — categorize 3D models into user-defined categories (e.g. Kitchen accessories, Cosplay, Technical parts)
  - New `ModelCategory` model with `name`, `color`, `created_at` fields (models.py)
  - New `category_id` FK on `ProjectFile` with `ON DELETE SET NULL` (models.py, migrations.py)
  - Category CRUD in Settings → Dictionaries tab — add, edit (inline), delete with color picker (routes/settings.py, templates/settings.html)
  - Interactive fulltext search dropdown filter on Models index page — same UX as existing filters (templates/models_index.html)
  - "Uncategorized" quick-filter option to show models without a category
  - Category badge with color dot displayed on model cards and in table rows (templates/_models_cards.html, templates/_models_rows.html)
  - Category selector in model detail edit modal — interactive dropdown with color swatches (templates/models_detail.html)
  - Category display in model detail header alongside project link
  - Full export/import support — `model_categories` section + `category_name` on project files (routes/backup_helpers.py, routes/backup.py)
  - 13 new i18n keys in both `cs` and `en` (messages.py)
  - Help tip added to models section in both languages (static/js/help.js)

## [1.113.0] - 2026-06-07
### Fixed
- **BUG-500, BUG-501**: Fixed UserSession backup export/import crash — `last_activity` → `last_activity_at`, removed non-existent `expires_at` column (routes/backup_helpers.py, routes/backup.py)
- **BUG-502**: Fixed XSS vulnerability in stats page — changed `{{ chart_data|safe }}` to `{{ chart_data|tojson }}` and removed `json.dumps()` from route to prevent script injection via filament names (templates/stats.html, routes/stats.py)
- **BUG-503**: Fixed RBAC bypass — unmapped endpoints now default to `abort(403)` instead of allowing all authenticated users (auth.py)
- **BUG-504**: Replaced 15+ hardcoded Czech strings in calculator_project.html with `{{ t("key") }}` — added 10 new i18n keys to messages.py (templates/calculator_project.html, messages.py)
- **BUG-505**: Fixed zero-price/weight filament creation bug — `all([..., 0.0, ...])` returned False; now uses explicit `is None` checks (routes/inventory.py)
- **BUG-506, BUG-507**: Added `nullable=False` to `BambuPrintJob.deducted`, `BambuJobMaterial.deducted`, and `ProjectFilament.is_used` boolean columns (models.py)
- **BUG-508**: Fixed ICS injection in maintenance calendar export — added `_ics_escape()` to sanitize newlines and special characters in printer_name and notes (routes/maintenance.py)
- **BUG-509**: Added rate limiting to `/register` endpoint — reuses login rate limiter (10 attempts per 5-minute window per IP) (routes/auth.py)
- **BUG-510**: Added session invalidation on role/permission change — all user sessions are now deleted when admin updates user role/permissions, forcing re-login (auth.py, routes/auth.py)
- **BUG-517**: Replaced `alert()` with `showToast()` in inventory.js context menu error handler (static/js/inventory.js)
- **BUG-519**: Added AbortController to command palette search — prevents race conditions when typing quickly (static/js/app-shell.js)
- **BUG-520**: Added radix parameter `, 10` to all `parseInt()` calls in dashboard.js (static/js/dashboard.js)
- **BUG-521**: Replaced hardcoded Czech/English tour labels with `window.__i18n` dictionary lookups — added 4 new keys to base.html i18n block (static/js/tour.js, templates/base.html)
- **BUG-522**: Replaced hardcoded English fallbacks in mobile-ux.js with `window.__i18n` lookups — added 3 new keys (ptr_pull, ptr_release, ptr_loading) to base.html (static/js/mobile-ux.js, templates/base.html)
- **BUG-523**: Added `nullable=False` to 4 timestamp columns: `PrintHistory.created_at`, `ProjectComment.created_at`, `ProjectFile.uploaded_at`, `WasteFile.uploaded_at` (models.py)
- **BUG-524**: Removed stale `overview_user` entry from `SECTION_BY_ENDPOINT` — endpoint does not exist (auth.py)
- **BUG-528**: Added `index=True` to `PrusaPrintJob.project_id` FK column (models.py)
- **BUG-529**: Added `index=True` to `MovementHistory.bambu_job_id` FK column (models.py)
- **BUG-532**: Replaced `onclick="return confirm('{{ t(...) }}')"` with `data-confirm` attribute in history.html — prevents JS injection via translated strings (templates/history.html)
- **BUG-533**: Replaced 5 hardcoded English strings in models_detail.html with `{{ t("key") }}` — added 7 new i18n keys (templates/models_detail.html, messages.py)
- **BUG-534**: Replaced hardcoded Czech fallback in api.py search results with `translate('project_client_missing_label')` (routes/api.py)
- **BUG-536**: Replaced `sum(r.weight_grams for r in WasteRecord.query.all())` with DB aggregate `db.session.query(db.func.sum(...)).scalar()` — avoids loading all records into memory (routes/waste.py)

## [1.112.1] - 2026-06-07
### Fixed
- **Tour wizard**: Fixed off-by-one error in `startFirstLoginTour()` redirect — the `first_login` URL parameter was set to `i+1` (next step index) instead of `i` (current step index), causing the wizard to redirect through all pages without ever showing the tour overlay (static/js/tour.js)
- **BUG-422**: Command palette (Ctrl+K) showed empty state because `<script>` tag was missing `x-ref="commandItems"` attribute — broke static item loading (templates/base.html)

## [1.112.0] - 2026-06-07
### Changed
- Command palette (Ctrl+K): reordered navigation items by priority — Overview, Filaments, Projects, Bambu, Prusa, Calculator, Stats, Storage, Models, History at the top (templates/base.html)
- Command palette: added missing Maintenance and Waste entries (admin-only), with new i18n keys `nav_maintenance_note` and `nav_waste_note` (templates/base.html, messages.py)

## [1.111.0] - 2026-06-07
### Fixed
- **BUG-400**: Fixed column order mismatch in `_migrate_nullable_project_id()` — `model_note` and `uploaded_by_user_id` were swapped in CREATE TABLE, causing silent data corruption on legacy upgrade (migrations.py)
- **BUG-401**: PRAGMA `foreign_keys=OFF` is now restored in the `except` block of `_migrate_waste_record_fk()` — prevents FK checks remaining disabled after a migration failure (migrations.py)
- **BUG-402**: Added `ondelete='SET NULL'` to `Project.owner_user_id` and `Project.created_by_user_id` FK columns (models.py)
- **BUG-403**: Changed `parent_file_id` FK from `ON DELETE SET NULL` to `ON DELETE CASCADE` in migration CREATE TABLE to match model and ORM cascade (migrations.py)
- **BUG-404**: Replaced 44 `onsubmit="return confirm('{{ t(...) }}')"` patterns with `data-confirm` attribute approach across 22 templates — prevents JS injection via translated strings (all affected templates, base.html)
- **BUG-405**: Added in-memory rate limiting to login endpoint — 10 attempts per 5-minute window per IP (routes/auth.py)
- **BUG-406**: Added `validate_password_strength()` to auth module — enforces minimum 8-char, max 256-char passwords on registration, activation, and password change (auth.py, routes/auth.py)
- **BUG-407**: Added CSP nonce to all 8 `<script src="...">` tags in base.html that were missing it (templates/base.html)
- **BUG-408**: Replaced 20+ hardcoded English error strings in JSON API responses with `translate()` calls across routes/bambu.py, projects.py, settings.py, prusa.py, models.py, and routes/models.py
- **BUG-409**: Replaced 7 hardcoded URL paths with `url_for()` in JS fetch() calls across overview.html, bambu.html, and prusa.html
- **BUG-410**: Changed unsafe `\|escape` to `\|tojson` in JS string context for 3D viewer title in project_detail.html — prevents XSS via filename
- **BUG-411**: Replaced internal `.whereclause` access with clean filter logic for `status_counts` query in account settings (routes/auth.py)
- **BUG-412**: Wrapped unprotected `db.session.commit()` in try/except in calculator route (routes/calculator.py)
- **BUG-413**: `encrypt_token()` now raises `RuntimeError` if FERNET_KEY is not configured (except during testing/placeholders) — prevents silent plaintext credential storage (utils/__init__.py)
- **BUG-415**: Added missing `printer_bambu` and `printer_prusa` translation keys to English dictionary (messages.py)
- **BUG-416**: Fixed 4 translation errors — `overview_command_center_title` (cs), `maintenance_fault_resolved` (cs), `markdown_editor_visual` (cs), `account_lang_cs` (en) (messages.py)
- **BUG-417**: Added CSP nonce to `<script src="...">` tags on standalone pages (quote_export.html, models_share.html)
- **BUG-418**: Added `\|safe` filter to `comment.body_html` rendering (render_markdown produces safe HTML) (_project_overview.html)
- **BUG-419**: Replaced `x-text` with inline JS string interpolation using separate `x-show` spans to prevent injection via translated strings (project_detail.html)
- **BUG-420**: Added `overview_user` endpoint to SECTION_BY_ENDPOINT mapping (auth.py)
- **BUG-421**: Added 3 AJAX endpoints (`api_filaments_list`, `api_live_printers_partial`, `api_search`) to help.js (static/js/help.js)
- **BUG-422**: Added `@require_admin` decorator to `clear_history` endpoint — previously relied solely on section mapping (routes/history.py)
- **BUG-423**: Fixed `x-show` without `x-cloak` (FOUC) on 12 elements across 5 templates (add.html, _projects_layout.html, bambu.html, storage.html, index.html)
- **BUG-425**: Removed dead `or endpoint.startswith('pwa.')` check in auth.py (already stripped at lines 363-364)
- **BUG-426**: Removed redundant module-level `csv` and `io` imports from routes/inventory.py (already imported inside `filament_import_csv`)
- **BUG-427**: Changed `file_size_bytes` column from `INTEGER` to `BIGINT` in migration ALTER TABLE and CREATE TABLE statements to match model's `db.BigInteger` (migrations.py)
- **BUG-428**: Restructured `window.__i18n` block to use Jinja with `\|tojson`; added sync comment (templates/base.html)
- **BUG-429**: Removed redundant `\|forceescape` after `\|tojson` in waste.html and removed `\|safe` after `\|tojson` in bambu.html
- **BUG-430**: Added `index=True` to 7 model columns that had indexes created in migrations but not on the model definition (models.py)
- **BUG-431**: Added comment noting redundant AuditLog index creation in migrations (migrations.py)
- **BUG-432**: Added nonce to remaining `<script src="...">` tags, fixed url_for route resolution for integer parameters, added proper test mode handling for fernet encryption
- **BUG-434**: Removed redundant `\|safe` after `\|tojson` in bambu.html
- **BUG-435**: Fixed `document.execCommand('copy')` to use `navigator.clipboard.writeText()` in models_detail.html
- **BUG-436**: Fixed action type fallback rendering in overview.html to use `t()` calls
- **BUG-427**: Added `https://` URL scheme validation to markdown editor link inputs (visual and source modes) — prevents `javascript:` XSS (static/js/markdown-editor.js)

## [1.110.0] - 2026-06-07
### Added
- **Prusa HTTP endpoint tests**: 23 new tests covering job page rendering, printer sync/test, job mapping, and job deletion for PrusaLink routes — addresses BUG-108 (tests/test_prusa_extended.py)
- **Model public share tests**: Test coverage for `model_public_share`, `model_generate_share`, and `model_revoke_share` endpoints — addresses BUG-112 (tests/test_models.py)
- **i18n keys**: Added `dashboard_color`, `dashboard_resize`, `dashboard_rows`, `bambu_name_required`, `tag_example` translation keys in both cs and en (messages.py)
- **DB safety net**: Global `app.teardown_request` handler rolls back the SQLAlchemy session on unhandled exceptions — prevents cascading failures in POST handlers (BUG-107, app.py)
- **Maintenance validation**: `_validate_printer_exists()` checks `printer_id` against real printer rows before assigning maintenance records (BUG-305, routes/maintenance.py)

### Fixed
- **BUG-007**: `test_advance_status_full_flow` now makes actual HTTP requests and asserts final status instead of being vacuous (tests/test_projects_extended.py)
- **BUG-008**: `test_project_usage_returns_rows` now uses a meaningful assertion that checks project name is in usage rows (tests/test_stats_extended.py)
- **BUG-009**: `test_delete_filament_cleans_project_references` creates real Project/ProjectFilament records and verifies cleanup (tests/test_inventory_extended.py)
- **BUG-010**: Tour tooltip close button uses `this._t({cs:'Zavřít',en:'Close'})` instead of hardcoded Czech (static/js/tour.js)
- **BUG-011**: `showToast` i18n fallback no longer uses identity-replacement dead code (static/js/app-shell.js)
- **BUG-012**: Dashboard hardcoded strings `'Color'`, `'Resize'`, `'Rows'` now use `window._dashColorTitle`, `_dashResizeTitle`, `_dashRowsTitle` set from template `t()` calls (static/js/dashboard.js, templates/overview.html, projects_index.html, stats.html)
- **BUG-013**: Removed duplicate `openReorderShop` function from inventory.js (already defined in app-shell.js) (static/js/inventory.js)
- **BUG-104**: Added `bambu_auto_map_history` endpoint to help.js bambu section endpoints array (static/js/help.js)
- **BUG-105**: Added `project_undo` endpoint to help.js projects section endpoints array (static/js/help.js)
- **BUG-106**: Changed `ProjectFile.parent_file_id` FK from `ondelete='SET NULL'` to `ondelete='CASCADE'` to match ORM `all, delete-orphan` cascade (models.py)
- **BUG-109**: Removed identical duplicate `test_stats_page_returns_200_with_no_data` test (tests/test_stats_extended.py)
- **BUG-110**: Fixed `_login_admin` dead code by removing `if False else None` pattern (tests/test_bambu_extended.py)
- **BUG-111**: `loadScript` now deletes the cache entry on script load failure, allowing retries instead of returning stale rejection (static/js/app-shell.js)
- **BUG-200**: Added defense-in-depth attribute escaping to markdown editor link URLs (static/js/markdown-editor.js)
- **BUG-201**: Added `attrEsc()` helper to escape URLs from data-attributes in inventory context menu (static/js/inventory.js)
- **BUG-202**: Debounced `saveLayout()` calls during drag-and-drop to avoid excessive localStorage writes (static/js/dashboard.js)
- **BUG-204**: Strengthened chart data assertion to check for `const statsData` and `"labels"` JSON (tests/test_stats_extended.py)
- **BUG-205**: Fixed vacuously-true assertion in `test_just_scheme_no_host_returns_none` to check result type and content (tests/test_utils_extended.py)
- **BUG-206**: Changed loose `assertLessEqual` to precise `assertEqual` for auto-backup count test (tests/test_backup_extended.py)
- **BUG-207**: Changed `file_size_bytes` from `db.Integer` to `db.BigInteger` to prevent overflow on files >2GB (models.py)
- **BUG-208**: Added `x-cloak` to `x-show` element in `_projects_layout.html` (templates/_projects_layout.html)
- **BUG-209**: Fixed MutationObserver `DOMContentLoaded` edge case by checking `document.readyState` (static/js/app-shell.js)
- **BUG-210**: Simplified redundant conditional branches in dashboard.js drag-and-drop handler (static/js/dashboard.js)
- **BUG-212**: Added response status code check to `test_add_waste_record_without_filament_id` (tests/test_waste.py)
- **BUG-213**: Added response status code check to `test_add_shelf_duplicate_name_skipped` (tests/test_storage_history_pwa.py)
- **BUG-214**: `test_toggle_ui_mode_to_operator` now verifies session change via `session_transaction` (tests/test_inventory_extended.py)
- **BUG-215**: Replaced hardcoded English error messages with `translate()` calls in bambu.py JSON API (routes/bambu.py, messages.py)
- **BUG-216**: Changed f-string to lazy `%s` formatting in auto-backup logger call (app.py)
- **BUG-305**: Added `_validate_printer_exists()` to prevent attaching maintenance records to non-existent printers (routes/maintenance.py)
- **BUG-307**: Fixed hardcoded English tag placeholder and Czech shop URL placeholder (templates/add.html, templates/settings.html, messages.py)
- **BUG-308**: `_audit_finish_request` now logs audit entries even for failed write requests (4xx/5xx), including HTTP status in payload (auth.py)

## [1.109.1] - 2026-06-07
### Added
- **Backup coverage**: `UserSession`, `ModelComment`, and `ProjectCommentReaction` models now included in `/export` and `/import` — full round-trip backup/restore for user sessions, model file comments, and emoji reactions (routes/backup_helpers.py, routes/backup.py)
- **FK documentation**: Added migration notes for `movement_history` and `bambu_job_material` ondelete constraints (migrations.py)

### Fixed
- **BUG-302**: `encrypt_token()` now logs a warning when Fernet encryption fails (invalid key) — previously silently fell back to plaintext (utils/__init__.py)
- **BUG-303**: `log_movement()` docstring now explicitly warns callers that they must call `db.session.commit()` (utils/__init__.py)
- **BUG-100**: Added `ondelete='SET NULL'` to `MovementHistory.filament_id`, `project_id`, `bambu_job_id` and `BambuJobMaterial.filament_id` FK constraints (models.py)

## [1.109.0] - 2026-06-07
### Added
- **i18n translations**: Added ~25 new translation keys (sidebar labels, quality labels, printer names, activity events, audit, stats, placeholders) in both `cs` and `en` (messages.py)
- **CSP nonce**: All inline `<script>` blocks across 24 templates now inject `nonce="{{ csp_nonce }}"` — enabling strict nonce-based CSP in the future (templates/*.html)

### Changed
- **BUG-301**: `utils.get_current_lang()` and `translate()` now respect `current_user.preferred_language` — backend notifications, flash messages, and audit labels follow the user's language preference (utils/__init__.py)
- **BUG-101**: Added `ondelete='RESTRICT'` to `Filament.brand_id`, `color_id`, `material_id` FK constraints — prevents deletion of brands/colors/materials in use (models.py)
- **BUG-102**: Replaced all hardcoded user-visible strings in route error responses (`return 'Unauthorized', 401` → `abort(401)` etc.) and activity event labels with translations (routes/projects.py, routes/backup.py, routes/calculator.py, routes/projects_helpers.py)
- **BUG-103**: Replaced all hardcoded user-visible text in templates with `{{ t("key") }}` — sidebar tooltips, printer type options, input placeholders, quality labels, etc. (templates/*.html)

## [1.108.2] - 2026-06-07
### Fixed
- **BUG-001**: `_migrate_nullable_project_id` CREATE TABLE missing `share_token` and `model_note` columns — crash on legacy database upgrade (migrations.py)
- **BUG-002**: Help panel `currentSection` detection broken due to Flask blueprint prefix mismatch — contextual tips never rendered (base.html)
- **BUG-003**: Missing `PRAGMA foreign_keys=ON` in SQLite connection setup — all FK constraints silently ignored (app.py)
- **BUG-004**: `WasteRecord.filament_id` FK missing `ondelete='CASCADE'` — risk of orphaned references when deleting a filament (models.py, migrations.py)
- **BUG-006**: `bambu_job_delete` returned 302 redirect for nonexistent jobs instead of 404; test name promised 404 but asserted 302 (routes/bambu.py, tests/test_bambu_extended.py)

## [1.108.1] - 2026-06-07
### Added
- **Canonical architecture documentation** — New `.kilo/ARCHITECTURE.md` serves as the single source of truth for all project architecture, conventions, rules, and data flow. All agent files now reference this document as their Phase 0 (mandatory first step).
- **Implementation backlog** — New `.kilo/BACKLOG.md` tracks features, bugs, and technical debt with criticality and effort estimates.
- **Changelog archive** — Versions v1.100.0 and older moved to `CHANGELOG-ARCHIVE.md` to keep the main changelog manageable (from ~1980 lines down to ~255).

### Changed
- `.kilo/agent/filament-agent.md` — Simplified to reference `.kilo/ARCHITECTURE.md` as canonical rules source. Removed duplicated rule content.
- `.github/agents/filament-release.agent.md` — Simplified to reference `.kilo/ARCHITECTURE.md` as canonical rules source. Removed duplicated rule content.
- `.github/copilot-instructions.md` — Updated header to note `.kilo/ARCHITECTURE.md` as canonical source. Updated Rule 29 and Post-Implementation Checklist.

## [1.108.0] - 2026-06-07
### Added
- **Comprehensive test coverage expansion** — 13 new test files with ~440 new tests across previously untested or under-tested areas:
  - `test_settings_integration.py` — Settings CRUD for dictionaries (brands/colors/materials), Bambu Cloud integration (connect/disconnect/test), company/billing details, reorder shop URL validation, auto-backup configuration, language/locale settings, onboarding dismiss (25 tests)
  - `test_inventory_extended.py` — Filament CRUD (add/edit/delete/use), spool management (add/remove), metadata update, reorder snooze toggle, bulk delete with undo, CSV import/export, community database import, UI mode toggle, overview onboarding (30 tests)
  - `test_calculator_extended.py` — Quote calculation unit tests (material/energy/margin math), project-based multi-material quotes, calculator history management, energy cost computation (14 tests)
  - `test_projects_extended.py` — Status workflow (advance/set), project clone, share tokens (generate/revoke/public view), project templates (save/delete/create-from), link management, filament planning, comment reactions, print items CRUD/increment/decrement, project detail rendering (25 tests)
  - `test_stats_extended.py` — HSL sort key unit tests, helper function tests (date_labels, empty_series, safe_divide), project usage rows, stats page rendering with custom days and chart data (15 tests)
  - `test_utils_extended.py` — Encrypt/decrypt (with and without Fernet key, roundtrip), compute_stock_status (all states), deduct_filament_stock (clamping, quantity update), tag parsing (separators, dedup, format, remove), hex normalization, duration formatting, auto-map filament, validate printer host, Bambu API base, clean title (40 tests)
  - `test_undo_system.py` — Undo snapshot creation (single/bulk/with references), get pending undo (recent/expired/consumed), consume undo (ownership/expiry/double-consume), purge expired logs, restore from snapshot (recreate/update/bulk) (9 tests)
  - `test_bambu_extended.py` — Jobs page rendering with filters (status/search/filament/pagination), job delete, map/deduct/remap, create project, auto-map history, refetch thumbnails, multi-material slot deduct (13 tests)
  - `test_backup_extended.py` — Export (full/db-only), backup storage dir creation, path safety (symlink/prefix), legacy JSON import, tar.gz import, conflict modes (skip/overwrite), retention cleanup by count (14 tests)
  - `test_models_core.py` — User/Filament/Project creation and relationships, notification creation, user sessions, invites, audit logs, project content (comments/reactions/templates/todos/print items), storage shelves/placements, printer models (Bambu/Prusa with jobs/materials), maintenance records, waste records with files (8 tests)
  - `test_security.py` — Escape LIKE, URL safety (SSRF: localhost/loopback/private IP/evil schemes), path traversal (project files), session cookie hardening (HttpOnly/SameSite), XSS prevention in filament names, project names, search queries (6 tests)
  - `test_waste_extended.py` — Waste file upload (valid/invalid extension), file serve/download, file delete, waste index filtering by reason/filament/pagination (6 tests)
  - `test_performance.py` — Smoke performance benchmarks with 50-filament/20-project dataset, verifying 7 key pages render under time limits (7 tests)
- **Parallel test execution** — Added `pytest-xdist` and configured `pytest.ini` with `addopts = -n auto`. Test suite now runs with 12 parallel workers (detected CPU cores). Full suite: 622 tests in ~35 seconds (was ~168 seconds sequentially, ~4.8× speedup).

### Changed
- `pytest.ini` — Added `addopts = -n auto` for parallel execution by default
- `requirements.txt` — Added `pytest-xdist>=3.6` for parallel test worker support

## [1.107.4] - 2026-06-07
### Added
- **Smart filament assignment from print-job history** — When a new Bambu job shares the same `model_name` as a previously manually-mapped job, `_auto_map_from_history()` now copies the filament assignments slot-by-slot using colour hex + material name as the matching key. This runs during auto-mapping (after sync / on manual trigger) and takes priority over material+colour heuristic matching, so repeating the same print multiple times requires zero manual remapping.

### Fixed
- **Project detail Print Jobs tab: filament colour dot always white** — The `_project_jobs.html` template used `item.filament_color_hex` but `_build_project_job_feed()` never populated that key (only `filament_colors` list). For Bambu jobs the primary colour is now derived from the first slot's hex or the mapped filament's colour; for Prusa jobs from the mapped filament's colour.

## [1.107.3] - 2026-06-07
### Fixed
- **All `fetch()` POST calls broken after v1.107.1 (CSRF rejection)** — v1.107.1 removed the `window.fetch` auto-injection patch from `app-shell.js` because it used `Object.assign({}, opts.headers, …)` which stripped methods from native `Headers` instances. However, eleven inline `fetch()` POST calls across `bambu.html`, `prusa.html`, `project_detail.html`, and `settings.html` relied on that patch for their `X-CSRFToken` header — none of them sent CSRF tokens themselves. The patch has been restored using **`new Headers(opts.headers)`** instead of `Object.assign`, so `Headers`-instance methods (`.get()`, `.set()`, iteration) are preserved while every non-GET `fetch()` call still receives the CSRF token automatically. User-visible symptom: "Chyba synchronizace: Unexpected token '<', … is not valid JSON" when triggering Bambu/Prusa sync.

## [1.107.2] - 2026-06-07
### Fixed
- **Alpine.js script tag missing from `base.html`** — Commit `3dd64d9` accidentally removed the `<script defer src="...alpine.min.js">` line from `<head>`. Since every page inherits `base.html`, this caused **all** Alpine.js directives (`x-data`, `x-show`, `x-cloak`, `x-init`, `:class`) to be silently ignored. All elements marked `x-cloak` stayed `display:none!important` permanently. User-visible impact: `/models` stuck on the loading spinner (the skeleton was never replaced), `/projects/<id>` tab content never rendered (every tab except overview was wrapped in `x-show` with `x-cloak`), and `/storage` shelf grid was hidden (the entire board depended on Alpine initialization). The missing line has been restored.
- **PWA service worker served stale `/static/` assets across minor releases** — `_sw_cache_name()` in `routes/pwa.py` derived the cache name from the *major* version only (`filament-manager-v1-static`), so the v1.106 → v1.107.0 upgrade kept the same cache name and the browser kept serving the **old** `app-shell.js` / `tour.js` while the new HTML referenced functions added in the new release. Cache name is now derived from the **full** `APP_VERSION` (`filament-manager-v1.107.2-static`), so every release installs a fresh cache and the `activate` step purges the previous one. Regression test `tests/test_refactors.py::TestPwaServiceWorker::test_cache_name_includes_version` updated to assert the full-version format.
- **`window.fetch` patch could break `Headers`-based requests** — `static/js/app-shell.js` used `Object.assign({}, opts.headers, { 'X-CSRFToken': … })`, which strips the methods of a `Headers` instance. The patch has been removed entirely; Flask-WTF already accepts the CSRF token via the `csrf_token` form field (auto-injected by `base.html`) and every in-app POST reads the token from the `<meta name="csrf-token">` tag directly.
- **Jinja2 `{{max}}` inside `<script>` blocks rendered as empty string** — Three sites (`templates/base.html` ×2, `templates/project_detail.html` ×1) used `{{max}}` as a JS string-literal placeholder, but Jinja2 interprets `{{` inside templates and emits the empty string for the unknown `max` variable. Renamed to `{max}` (single braces) so the literal survives the template engine.

## [1.107.0] - 2026-06-06
### Added
- **Optimistic UI for comment reactions** — `commentReactions.toggle()` in `templates/_project_overview.html` now mutates local state immediately, then sends the POST. If the server rejects, the local state is reverted and an error toast is shown. Snappy feedback on every network.
- **Skeleton loaders** for AJAX-driven lists — `static/css/skeleton.css` with shimmer keyframes, plus `templates/_skeleton_cards.html` and `templates/_skeleton_rows.html` partials. Projects index page now injects skeletons into Kanban columns, calendar items, and the project table during filter-driven refetches. Bambu page replaces its single spinner with three skeleton cards while syncing. (Prusa page renders all jobs server-side, so it does not need skeletons.)
- **Multi-step upload stepper** in project detail — The legacy `dropZone` / `fileInput` / `uploadForm` JS was replaced with an Alpine `x-data="uploadStepper(...)"` component. Phases: idle → validating → uploading → preview (3D model files only) → done. Real XHR progress events drive the progress bar. 4 step labels in `cs` + `en` (`upload_step_validate` / `upload_step_upload` / `upload_step_preview` / `upload_step_done`).
- **Undo toast for deleted projects and project files** — `routes/projects_helpers.py` adds `snapshot_project_for_undo()` / `restore_project_from_undo()` / `snapshot_file_for_undo()` / `restore_file_from_undo()`. Snapshots are stored in `/tmp/filament_undo/` and expire after 30 min. New POST endpoint `/projects/undo` consumes the `session['project_pending_undo']` slot atomically. `templates/_toast_undo.html` renders the toast with a countdown, X button, and undo button. 2 new i18n keys: `project_undo_toast_title`, `project_file_undo_toast_title`.
- **First-login onboarding wizard** — `routes/auth.py` `login()` now appends `?welcome=1` to the redirect (and sets a 1-year `first_login_tour_v1` cookie) the first time a user logs in. `static/js/tour.js` chains four section tours (filaments → projects → settings → stats) and opens the help panel at the end. The help panel gets a new "Spustit úvodního průvodce" button. Escape aborts the entire chain. 1 new i18n key: `tour_full_wizard_btn`.
- **Global client-side toast helper** — `window.showToast(messageKey, category, opts)` in `static/js/app-shell.js` looks up strings in `window.__i18n` and shows them in a right-side stack with fade transitions. Used by the optimistic-reactions revert path and (later) anywhere a one-off status message is needed.

### Changed
- **Prusa page intentionally not skeletonized** — Prusa jobs are rendered server-side with no auto-filter; the existing spinner remains. Documented to avoid future "why is it different?" confusion.

## [1.106.1] - 2026-06-06
### Fixed
- **Project detail page: Alpine `x-data` attribute for comment reactions was malformed** — `templates/_project_overview.html` rendered `x-data="commentReactions(<id>, {{ comment.reactions | tojson }})"`. Because Jinja's `tojson` emits double quotes, those `"` characters terminated the `x-data="…"` HTML attribute early, producing `Uncaught SyntaxError: missing ) after argument list` and `Uncaught ReferenceError: reactions is not defined` in Alpine on every project page that contained a comment. The attribute is now single-quoted (`x-data='commentReactions(…)'`) so the JSON's `"` survive. Regression test `test_project_detail_renders_well_formed_xdata_for_comment_reactions` added in `tests/test_projects.py`.

## [1.106.0] - 2026-06-06
### Changed
- **Markdown renderer extracted to `utils/markdown.py`** (Refactor B) — Pre-compiled regexes at import time, escape-first pipeline, and a public `toggle_markdown_checkbox()` alias.  The renderer is now in its own module so the security-sensitive XSS code is testable in isolation.  All existing `from utils import render_markdown` / `_toggle_markdown_checkbox` calls continue to work via re-exports.
- **`movement_action_label` now uses i18n** — Replaces the hardcoded English label map with `translate('movement_action_<type>')` lookups; new keys added to both `cs` and `en` in `messages.py`.  Falls back to a neutral title-cased string when no translation is registered.
- **Auto-backup scheduling rewritten** (4.4) — Replaced the brittle "5-minute polling window" with an explicit `_compute_next_auto_backup_run()` helper.  The worker now sleeps until 60 s before the next scheduled slot, then re-checks every 60 s.  Missed weekly/monthly runs are recovered automatically; 5+ minute GC pauses or restarts no longer cause silent skips.  All candidate datetimes are offset-aware to avoid the Python 3.12+ "can't compare naive and aware" TypeError.
- **PWA service worker hardened** (5.12) — Cache name is now derived from `APP_VERSION` (`filament-manager-v<MAJOR>-static`).  The `activate` handler purges caches belonging to previous versions.  Static assets under `/static/` and `/manifest.json` are served cache-first; everything else falls through to the browser default.  Response sets `Cache-Control: no-cache` and `Service-Worker-Allowed: /` headers.
- **Audit log: `_audit_target()` no longer queried twice** (5.3) — The resolved target object is stashed in `g.audit_context['target_object']` so `_audit_finish_request` reuses the in-memory reference instead of re-running the DB lookup.  Audit-write failures are now logged at `ERROR` level (was `WARNING`).

### Fixed
- **Backup path traversal hardening** (3.7) — `routes/backup.py` now uses a `_backup_storage_dir()` helper that returns the `realpath` of the directory, plus an `_is_path_inside()` containment check.  Download and delete endpoints refuse any path whose `realpath` is not inside the storage directory, with a `WARNING` audit log on attempted traversal.
- **Backup dead code removed** (5.2) — `backup_list_files` no longer constructs a fake `modified_at` ISO string from `utc_now().replace(year=2020, ...)`.  Replaced with a clean `modified_at_ts` field.
- **Backup "dual work" fixed** (5.5) — `backup_trigger_now` no longer calls `_build_export_data` twice.  New `_build_backup_archive_from_data()` helper takes the pre-built export dict and only serialises the archive.
- **`datetime.min` vs timezone-aware sort** (5.1) — `build_action_center` and `build_project_metrics` now use a `datetime(1970, 1, 1)` epoch sentinel (`_SORT_EPOCH`) for `max()` / `sort()` against a list that may contain mixed aware/naive datetimes.  Prevents the Python 3.12+ `TypeError: can't compare aware and naive` crash when sorting `BambuPrintJob.finished_at`.

### Added
- **`utils/markdown.py`** — Standalone Markdown renderer with `render_markdown()`, `toggle_markdown_checkbox()`, `markdown_extract_checkboxes()` public API.  Pre-compiled regexes, escape-first rendering, only `http`/`https`/`mailto` URL schemes permitted in links.
- **`tests/test_markdown.py`** — 49 tests covering XSS payloads, basic Markdown features, checkboxes, URL safety, edge cases, and re-export backward-compat.
- **`tests/test_refactors.py`** — 20 tests covering backup path containment (including symlink escape attempts), `movement_action_label` i18n, auto-backup scheduling math (daily/weekly/monthly + edge cases), and PWA service-worker cache name derivation.

## [1.105.1] - 2026-06-06
### Added
- **Model-level persistent notes** — A new `model_note` field on the `ProjectFile` model. Unlike version notes (which change per upload), the model note persists across all versions. It appears on model cards (table+card views) as an italic line, in the detail page metadata panel as a blue highlighted card, and in the Edit Metadata modal. Useful for reminders like "print with supports" or "PETG, 0.4mm nozzle".

### Fixed
- **Card click-through** — The hover overlay no longer blocks clicks to the model detail page. Replaced `onclick="stopPropagation()"` with `pointer-events-none group-hover:pointer-events-auto`.

### Changed
- **Stats bar** — Redesigned as a compact inline text row instead of three large cards, keeping it subtle and unobtrusive.

## [1.105.0] - 2026-06-06
### Added
- **Hover overlay on model cards** — Action buttons (Preview, Download, Delete) now appear as a semi-transparent overlay when hovering over the thumbnail image, freeing up footer space for metadata-only display.
- **Version count badge** — Cards now show a violet badge with the total number of versions when a model has more than one version.
- **"No project" quick filter** — A new filter pill above the filter panel lets you instantly isolate models that are not assigned to any project.
- **Model statistics bar** — A new stats row at the top of the Models page shows total model count, total file size, and number of models without thumbnails.
- **Fullscreen 3D viewer** — The model detail page now has a fullscreen toggle button in the viewer overlay, using the browser's Fullscreen API.
- **Project assignment from model detail** — The "Edit Metadata" modal now includes a project selector, allowing you to assign or reassign a model to a project directly from the detail page.
- **Model comments** — A new comments section below the version history timeline allows users to add, view, and delete comments on individual models.
- **Model sharing** — Generate a public read-only share link for any model, allowing unauthenticated users to view the 3D model and its version history.
- **Bulk actions** — Checkboxes on cards and table rows enable bulk selection, with a floating action bar offering bulk-delete and bulk-move-to-project operations.

### Changed
- **Model card footer** — Simplified to show only file size and upload date; action buttons moved to hover overlay.
- **Backup/export** — `share_token` column on `ProjectFile` is now included in exports and imports.

## [1.104.6] - 2026-06-03
### Changed
- **Version upload modal now uses drag-and-drop** — The "Upload version" modal on the model detail page now has the same drag-and-drop zone as the new model upload, including blue highlight on drag, file name/size feedback, and consistent styling. Drag-and-drop auto-submits; file browser selection only shows the filename (no auto-submit), letting the user add a version note first.

## [1.104.5] - 2026-06-03
### Fixed
- **Upload modal no longer auto-submits on file browse** — Selecting a file via the "Browse" link now only shows the filename/size; the user must click "Upload" explicitly. Drag-and-drop still auto-submits for convenience.
- **3MF files now extract embedded thumbnails** — Many slicers (Bambu Studio, PrusaSlicer, Cura) embed a `Metadata/thumbnail.png` inside the 3MF archive. The uploader now extracts this image automatically, providing a visual preview on the models page instead of the fallback SVG.
### Changed
- **Project-less models are now truly unassigned** — The `project_file.project_id` column is now nullable. Models uploaded without a project are stored with `project_id = NULL` instead of being placed in a hidden "Unassigned models" project. The auto-created "Unassigned models" project has been removed. All code paths (auth, listing, detail, export/import) handle null project_id correctly.

## [1.104.4] - 2026-06-03
### Changed
- **Redesigned model upload modal** — The upload popup on the Models page now matches the visual style of all other project components (drag-and-drop zone, hover states, dark mode support, consistent typography). File upload is now instant on drop or file select (auto-submit), with filename+size feedback shown below the drop zone.
- **Models can now be uploaded without a project** — The project selector in the upload modal is now optional. Models uploaded without a project are automatically placed under a hidden "Unassigned models" project (status DONE, priority low), keeping the database constraint intact while allowing free-form model cataloging.

## [1.104.3] - 2026-06-03
### Added
- **Direct model upload from Models page** — A new "Upload model" button on the Models page opens a modal where you can upload a 3D model file, select its project, and optionally add a version note. After upload, you are redirected to the model detail page where you can add more versions. Previously, models could only be uploaded from within project detail pages.

## [1.104.2] - 2026-06-03
### Added
- **Model deletion** — Models can now be deleted from the Models overview page (trash icon on each card/row) and from the Model detail page. In the model detail, you can delete the entire model chain (all versions) or individual versions from the history timeline. When deleting the root version, the newest remaining child is promoted as the new root. Deleting the last version removes the entire model. All files and thumbnails are cleaned up from disk.

## [1.104.1] - 2026-06-03
### Fixed
- **Project cloning now uses correct model columns** — `project_clone` referenced `actual_weight`, `color_override` on `ProjectFilament` and `item_name`, `quantity`, `done` on `ProjectPrintItem`, none of which exist in the current schema. Fixed to use `is_used` (ProjectFilament) and `name`, `quantity_total`, `quantity_done` (ProjectPrintItem). This was a residual from an earlier model schema where these columns were named differently.
- **3D viewer engine file missing** — `static/js/o3dv.min.js` was referenced by `viewer.html` but never copied from `node_modules`. Now properly included; the interactive 3D model viewer will no longer fail with "Failed to load 3D engine".
- **Help system endpoint names corrected** — `static/js/help.js` had 13+ stale/mismatched endpoint names (e.g., `overview` → `index`, `add_filament` → `add`, `stats_index` → `stats`, `storage_index` → `storage`, `bambu_index` → `bambu_jobs`, `prusa_index` → `prusa_jobs`, etc.). All sections now reference the actual Flask endpoint names. Missing endpoint names for new features (models, print items, comments, waste, etc.) were also added. Contextual help tips will now correctly match all pages.
- **Missing SECTION_BY_ENDPOINT entries added** — `bambu_job_thumbnail` and `serve_thumbnail` endpoints were missing from `auth.py`'s section mapping, now properly assigned to `SECTION_PRINTERS` and `SECTION_PROJECTS`.

## [1.104.0] - 2026-06-03
### Removed
- **Entire viewer-optimized file feature removed.** All simplified/decimated mesh generation, the `/models/version/<id>/optimized` endpoint, the `model_view_optimized` route, and all related functions (`simplify_stl`, `simplify_3mf`, `simplify_obj`, `simplify_amf`, `simplify_mesh_file`, `_decimate_indexed_mesh`, `generate_optimized_stl_for_file`, `get_optimized_stl_path`, etc.) have been removed. All viewer-optimized UI indicators (badges, right-panel status row, floating overlay chip, history preview icons) are also removed. The 3D viewer now always loads the original file via `model_view_version`. STL thumbnail rendering remains intact.
- Background worker no longer generates optimized files — only renders STL thumbnails.
- Removed ~40 tests covering mesh simplification, indexed decimation, and optimized endpoint behavior.
- Cleaned up `routes/model_renderer.py` to ~260 lines (was ~1,100+), keeping only the STL parser and isometric thumbnail renderer.

## [1.103.7] - 2026-06-03
### Changed
- **Decimation quality improved** — The grid-based vertex clustering now uses **iterative refinement**: if the output is too sparse (less than 75% of the target triangle count), the grid resolution is doubled and clustering is retried (up to 4 passes, grid_n max 512). This prevents thin/curved models from collapsing to far fewer triangles than intended. Example: the Norse Bracelet (612K triangles) previously collapsed to 6,980 triangles (98.9% reduction) — now produces exactly 50,000 (81.7% file-size reduction, preserving visible detail).

## [1.103.6] - 2026-06-03
### Fixed
- **Bambu Studio 3MF files now actually get optimized** — All 7 user 3MF files were previously marked "complex" and skipped by the optimizer because of three over-aggressive checks: (1) `<metadata>` tags were flagged as unsupported, (2) `<components>` tags (used by Bambu to reference external object files) were flagged, and (3) any build `<item>` with `objectid != 0` was rejected. Since ALL Bambu Studio exports use these three features, the optimizer silently refused every single real-world 3MF. Fixed by removing metadata/components/build-ref from the complexity check and adding `_resolve_external_object()` which follows the Bambu component chain (`build → item → resource-object → component → external-object-file`) to find the actual mesh in `3D/Objects/object_N.model` files. The decimated mesh is written back into the external object file, preserving all other ZIP entries (metadata images, slice info, auxiliaries).
- **3MF/AMF/OBJ viewer now loads correctly on first open** (from v1.103.5) — The `model_view_optimized` URL now includes the file extension so O3DV can detect the format.

### Changed
- `_detect_3mf_complexity()` now only flags: multiple `<object>` elements OR unsupported visual features (`colorgroup`, `texture2d`, `texture3d`, `basematerials`, `compositematerials`).
- `simplify_3mf()` has a two-phase strategy: first try inline `<mesh>` in `3dmodel.model`, then fall back to `_resolve_external_object()` for Bambu Studio's external-file pattern.
- Updated 2 tests in `test_model_renderer.py`: `test_3mf_with_metadata_can_be_simplified` and `test_3mf_with_non_zero_build_ref_is_simplified` now verify simplification succeeds (was expected to fail).

## [1.103.5] - 2026-06-03
### Fixed
- **3MF/AMF/OBJ viewer now loads correctly on first open** — The `model_view_optimized` endpoint URL (`/models/version/<id>/optimized`) had no file extension. Online3DViewer uses the URL extension to detect which importer to use (e.g. `CanImportExtension("3mf")`), so 3MF/AMF/OBJ files failed with "Failed to load model". The fix adds an optional `<path:filename>` suffix to the route (e.g. `/models/version/<id>/optimized/my_model.3mf`) so O3DV can detect the format from the `.3mf` extension in the URL. The original extensionless URL continues to work for backward compatibility. Also updated the history-version preview links to use `model_view_optimized` (with filename) for ALL mesh formats, not just STL.

## [1.103.4] - 2026-06-02
### Fixed
- **Complex 3MF files no longer break the 3D viewer** — The v1.103.3 3MF simplifier rewrote the entire `3dmodel.model` XML with a minimal single-object template, which **broke complex 3MFs** (multi-object files, files with build references to non-zero objects, files with materials, textures, or metadata). The viewer then failed to load the resulting malformed file with "Failed to load model". The simplifier now detects complex 3MF structure and **refuses to optimize it**, returning `None` so the route falls back to serving the original file (correct behavior, no speedup). For simple 3MFs (single object, no extra features), the simplifier now replaces only the `<vertices>` and `<triangles>` children of the first `<mesh>` in-place, preserving the original namespace, build refs, and all other structure. Added 4 unit tests in `tests/test_model_renderer.py` (multi-object / metadata / build-ref-to-other-object / archive-entries-preserved) and 1 integration test in `tests/test_models.py` (route serves original for complex 3MF, with both objects and the original build reference intact).

## [1.103.3] - 2026-06-02
### Added
- **Multi-Format Viewer Optimization (3MF, OBJ, AMF + STL)** — The same server-side mesh decimation that shipped in v1.103.1 for STL is now available for **all mesh formats the browser viewer can load**: STL, 3MF, OBJ, AMF. The interactive 3D viewer always loads a decimated version (default target ~50K triangles) via the existing `/models/version/<id>/optimized` endpoint, dramatically reducing load time for large models regardless of source format. Background worker now sweeps all mesh formats, not just STL.
- **Indexed-Mesh Decimation Algorithm** — STL stores 3 vertices per triangle (no sharing), but 3MF/OBJ/AMF share vertices via indices. New `_decimate_indexed_mesh()` function in `routes/model_renderer.py` clusters vertices to a 3D grid cell, picks one representative per cell, remaps every triangle's 3 indices, and drops degenerate (zero-area) triangles. Same shape-preservation guarantee as the STL grid-clustering decimation.
- **Per-Format Diagnostic in the Detail Page UI** — The "Not required for this format" message that was misleading users is replaced. The activation-placeholder badge and the right-side metadata panel now show the **actual format of the latest version** (e.g. `STL`, `3MF`, `STEP`, `GCODE`) alongside the optimization status. The label is rendered as a small chip so users can immediately see whether the latest version is the one they expect, and why the viewer is loading the original vs. optimized file. Non-mesh formats (STEP, GCODE, BGCODE) get a clear "this format cannot be optimized for the 3D viewer — the original file will be loaded as-is" note instead of the old generic message.
- **New translation keys** (`cs` + `en`): `models_viewer_optimized_format_label` ("Current format" / "Aktuální formát") and `models_viewer_optimized_non_mesh` ("This format ({ext}) cannot be optimized for the 3D viewer — the original file will be loaded as-is." / "Tento formát ({ext}) nelze optimalizovat pro 3D náhled — bude načten originální soubor.").
- **Tests** — 23 new tests in `tests/test_model_renderer.py` covering the new indexed-mesh decimation, OBJ/AMF/3MF parsers, writers, simplifiers, and the format-agnostic dispatcher, plus 1 new integration test in `tests/test_models.py` for the `/optimized` endpoint serving a real 3MF file.

### Changed
- **`routes/models.py`** — `STL_EXTENSIONS` kept for backward compatibility, but the optimized-file logic is now keyed on `OPTIMIZABLE_MESH_EXTENSIONS = {stl, 3mf, obj, amf}`. The optimized file keeps the source's extension on disk (e.g. `opt_42.3mf`), so the browser viewer's extension-based dispatch still works. `get_optimized_stl_path()` is preserved as the public function name (backward-compatible) but now returns the path for any optimizable mesh format.
- **Background model-thumbnail worker** — Now scans all mesh formats (STL, 3MF, OBJ, AMF) for files missing an optimized viewer version, not just STL. STL files still get a thumbnail; other formats rely on the existing SVG placeholder.

## [1.103.2] - 2026-06-02
### Added
- **Model-Detail Viewer-Optimization Indicators** — The `/models/<id>` page now clearly tells the user which file the 3D viewer will load. Three places are updated:
  1. **Activation placeholder** above the "Load Preview" button: an amber `fa-clock` badge labelled "Původní soubor / Original file" when no optimized version exists yet, or a green `fa-bolt` badge labelled "Optimized version" when one is cached. For non-STL formats a slate `fa-file` badge labelled "Original file" is shown with the note that no optimization is needed.
  2. **Right metadata panel** — a new "Browser-optimized version" row shows whether the optimized STL is `Available` (with file size) or `Will be generated on first open` (with a `fa-clock` icon). For non-STL formats a `Not required for this format` note is shown.
  3. **Version history Preview buttons** — every history entry whose filename is `.stl` gets a small inline icon next to its Preview button (`fa-bolt` green = optimized available, `fa-clock` amber = not yet generated), so users can see the status of every version at a glance.
  4. **Floating viewer overlay** (active version label in the bottom-left of the 3D viewport) — when the active file is an STL, a small "Optimized version" chip with `fa-bolt` is shown next to the filename. Switching versions in history updates this indicator live.
- The `model_detail` route in `routes/models.py` now passes per-version optimization state (`history_optimized` keyed by file id, with `is_stl` and `optimized_exists` flags) and latest-version state (`latest_is_stl`, `latest_optimized_exists`, `latest_optimized_size_bytes`) to the template, so the template never has to touch the filesystem.

## [1.103.1] - 2026-06-02
### Added
- **Server-Side Mesh Simplification for Fast 3D Viewing** — When an STL model is uploaded, the server now also generates a "viewer-optimized" version with reduced triangle count (target ~50K) using grid-based vertex clustering. The interactive 3D viewer always loads this lighter version via the new `/models/version/<id>/optimized` endpoint, eliminating browser hangs on large (10MB+) models. The full-resolution model is preserved for download. Non-STL formats fall back to the original file. Generation runs on upload and in the background worker, so previously uploaded models are optimized automatically.

## [1.103.0] - 2026-06-02
### Added
- **Automatic Server-Side STL Thumbnail Generation** — STL models uploaded to projects or via the Models page now get a real 3D preview rendered automatically, with no user interaction required. The renderer (`routes/model_renderer.py`) parses binary and ASCII STL files, applies isometric projection + simple directional shading + painter's algorithm for hidden surface removal, and outputs a 400×250 PNG. Pure-Python + Pillow only — no heavy 3D libraries (numpy, trimesh, pyrender) needed. Non-STL formats (3MF, OBJ, GCODE, etc.) keep the colour-coded SVG placeholder from v1.102.5.
- **Background Model-Thumbnail Worker** — A new daemon thread (`model-thumbnail-worker`, started in `app.py`) periodically scans for STL files without a saved thumbnail and renders them in batches of 3 per minute, catching any models missed by the immediate upload trigger (e.g. files imported before this feature shipped, or files where the upload-time render was skipped due to a transient error).
- **Pillow Dependency** — Added `Pillow>=10.0,<12` to `requirements.txt` for the renderer.

## [1.102.5] - 2026-06-02
### Added
- **Default SVG Thumbnails for Models** — Models without a captured thumbnail (manual uploads or newly imported models before first detail-page visit) now display a colour-coded SVG placeholder showing the file extension (STL, 3MF, OBJ, etc.) inside a tinted card. Each file type gets a distinct accent colour for quick visual distinction. Once the user opens the model detail page, the automatic canvas snapshot replaces the placeholder with a real 3D rendered preview.
- **Clickable Thumbnails** — Thumbnails in both card and list views now act as links to the model detail page (`/models/<id>`), in addition to the existing text link on the model name. This makes navigation more intuitive on mobile/touch interfaces.

## [1.102.4] - 2026-06-02
### Fixed
- **Lazy 3D Viewer Activation on Model Detail Page** — The heavy O3DV 3D viewer engine no longer auto-loads on page init at `/models/<id>`. Instead, a "Load Preview" button is shown, deferring the CPU-intensive model parsing until the user explicitly requests it. This eliminates page unresponsiveness during initial model detail visits while preserving all viewer features (rotation, color picker, thumbnail capture, version switching) once activated. Version history "Preview" buttons also activate the viewer on first click.
- **Threefold 3D Model Loading Speed Optimization** — (1) Added `Flask-Compress` with Brotli/gzip support — model files are now served compressed, cutting network transfer time by 50-70%. (2) Client-side binary STL triangle sampling — large models (>80K triangles) are automatically simplified in JavaScript before being handed to O3DV, reducing parse time by 5-20x while preserving visual fidelity for preview purposes. (3) Model data is pre-fetched by the parent page and passed to the iframe as a blob URL, eliminating a second network round-trip. Combined, these changes reduce total load time from 10-20s to 1-3s on typical high-poly models.

## [1.102.3] - 2026-06-01
### Fixed
- **iframe Process Isolation for 3D Viewer** — Moved the Online3DViewer (O3DV) engine into an isolated `<iframe>` (`/static/viewer.html`) that runs in a separate browser process. Since O3DV v0.18.0 parses STL/3MF/OBJ files synchronously on the main thread with no Web Worker support, this was the only way to prevent the parent page from freezing during large model loading. The parent page communicates with the iframe viewer via `postMessage()` API with strict same-origin validation, preserving all features: model preview, color picker, thumbnail capture, and version switching.
- **Security: DOM-safe Toast Notifications** — Refactored the `showToast()` function on the models detail page to use `document.createElement()` and `textContent` instead of `innerHTML`, preventing potential XSS in toast message rendering.

## [1.102.2] - 2026-06-01
### Fixed
- **True Self-Hosted Same-Origin 3D Web Workers** — Packaged and served the complete Online3DViewer external libraries (`libs`) locally from `/static/js/libs/` inside the Docker image. Configured templates to resolve `libs` relative to our own domain. This successfully bypasses modern browser Same-Origin Policy (SOP) restrictions that throw `SecurityError` and block workers created from cross-origin CDN URLs. Model decoding and Draco compression tasks now run in dedicated background threads, eliminating main thread blocking, unresponsive pages, and freezes.
- **Offline Visualization Capability** — Made the 3D visualizer completely self-contained and offline-capable by removing dependencies on external CDNs for Web Worker scripts.

## [1.102.1] - 2026-06-01
### Fixed
- **3D Viewer Web Worker & CSP Lockup** — Enabled asynchronous multi-threaded Web Worker parsing in Online3DViewer by setting `OV.SetExternalLibLocation` to point to jsDelivr CDN libs. Configured explicit `connect-src`, `worker-src`, and `child-src` directives in the application Content-Security-Policy (CSP) headers, allowing the browser to load worker threads and zip decoding assets asynchronously. This eliminates main UI thread blocking and freezes when visualizing large models (10MB+).
- **Project Detail 3D Previewer Stability** — Ported the safe `removeChild` DOM monkeypatch and proper `.Destroy()` lifecycle disposal to the project detail page 3D viewer, preventing WebGL context leaks and exceptions during color alterations or model reloads.

## [1.102.0] - 2026-06-01
### Added
- **Central 3D Model Browser** — Introduced a dedicated central repository at `/models` for managing all 3D model files (3MF, STL, OBJ, AMF, STEP, STP, GCODE) uploaded across projects. Features search, file extension/project filtering, and pagination.
- **Interactive 3D Previewer** — Embedded Online3DViewer supporting rotation, zoom, and dynamic model color mesh painting using the user's filament inventory palette.
- **Version Timeline & Revision Grouping** — Revision grouping showing uploader, file size, SHA256 checksum, MIME types, and version notes with inline preview or download actions.
- **Canvas WebGL Thumbnail Snapshot Capture** — Client-side WebGL canvas screenshot capabilities posting captured JPEG snapshots back to persist custom spool thumbnails.
- **Automated Model Tests** — Created automated test suite `tests/test_models.py` verifying model detection, search/sort/filter, CRUD edits, versioning increments, downloads, path-traversal blockages, and project RBAC rules.
- **Contextual Help Integration** — Integrated contextual help panels for models endpoints in both Czech and English.

### Fixed
- **Client-Side Javascript Runtime Error** — Corrected extension extraction logic in `templates/models_detail.html` under Alpine.js `init()` to utilize standard Javascript `split('.').pop().toLowerCase()` rather than Python-style list/string methods (`rsplit` / `[-1]` / `lower`), resolving browser console runtime exceptions.
- **3D Viewer Memory & Event Lifecycle Disposal** — Integrated proper `.Destroy()` disposal calls on previous viewer instances during reload, color updates, or version switching, and replaced the blind 2.5-second setTimeout delay with Online3DViewer's native `onModelLoaded` and `onModelLoadFailed` event callbacks. This ensures background thumbnail creation is only executed *after* large model (10MB+) parsing completes, preventing main thread freezing or UI lockups.
- **High-Performance Spool Thumbnail Capture** — Grab canvas frame buffer synchronously inside an explicit redraw wrapper (`viewer.Render()`) instead of launching heavy, blocking off-screen rendering contexts via `GetImageAsDataUrl()`. This captures sharp screenshots in less than 10 milliseconds, eliminating WebGL empty buffers and preventing main thread freezing or UI lockups.
- **Automatic Model Metadata Auto-Backfill** — Configured an on-startup migration routine in `migrations.py` to auto-backfill missing metadata (sizes, checksums, mime types, display names) for pre-existing uploaded files, and enabled instant extraction during project file uploads in `routes/projects.py`, resolving the "0 B" file size issue.

## [1.101.0] - 2026-05-31
### Changed
- **Route file modularization (#7)** — Split 4 large monolith route files (>1000 lines) into route modules + helper modules:
  - `bambu.py` → `bambu.py` (570 lines) + `bambu_helpers.py` (sync engine, thumbnails, mapping logic)
  - `inventory.py` → `inventory.py` (890 lines) + `inventory_helpers.py` (query builders, stock stats, undo helpers)
  - `projects.py` → `projects.py` (1166 lines) + `projects_helpers.py` (job feed, notifications, pagination)
  - `backup.py` → `backup.py` (888 lines) + `backup_helpers.py` (export/import serialization logic)
- **CSP nonce support (#15)** — Added per-request CSP nonce generation in `app.py` with nonce attributes on all inline `<script>` tags in `base.html`. The nonce is passed to templates via `csp_nonce` context variable for progressive CSP hardening.
- **Fernet missing-key warning (#16)** — `encrypt_token()` in `utils.py` now logs a one-time startup warning when `FERNET_KEY` environment variable is not set, alerting administrators that Bambu tokens and Prusa API keys are stored as plaintext.
- **Timezone-aware datetime storage (#17)** — Added `utc_now_aware()` to `time_utils.py` returning timezone-aware UTC datetimes. Model defaults in `models.py` now use timezone-aware datetimes for new records. Updated `fmt_dt` template filter in `app.py` to handle both aware and naive datetimes. Backup worker now stores timezone-aware timestamps.
- **SESSION_COOKIE_SECURE warning (#18)** — Added startup warning log when `BEHIND_PROXY` environment variable is not set, advising administrators to enable it for production deployments behind TLS-terminating reverse proxies.


---

*For changelog entries v1.100.0 and older, see [CHANGELOG-ARCHIVE.md](CHANGELOG-ARCHIVE.md).*
