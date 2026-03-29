# GitHub Copilot Custom Instructions for the Filament Manager Project

This file contains permanent instructions and prompts for future interactions. Always keep this context in mind to provide the correct code outputs!

## Main Project Context (Tech Stack)
- **Application:** Web-based 3D filament management and slicer-based print cost calculator.
- **Backend:** Python 3.11, Flask, SQLAlchemy (without complex DB migrations like Alembic), SQLite (persisted in the `./data/` directory).
- **Frontend:** Jinja2 templates, TailwindCSS via CDN (responsive UI using flex/grid), FontAwesome icons, **Alpine.js 3.x via CDN** (reactive state for inventory filters, sort, and view toggle).
- **Infrastructure:** Docker & Docker Compose (`filament_app`, port `5050:5000`).

## Project File Structure (Modular Architecture)
The project uses a modular Flask app factory pattern — **no Flask Blueprints**. Routes are registered directly on the `app` object via `register(app)` functions, so `url_for("index")` etc. work in templates without any prefix.

```
app.py               # Thin orchestrator: create_app(), _setup_database(), _safe_alter()
database.py          # Shared db = SQLAlchemy() instance
models.py            # All ORM models: Brand, Color, Material, Filament, MovementHistory,
                     #   AppSetting, PrintHistory, Project, ProjectFile, ProjectLink,
                     #   ProjectFilament, BambuPrinter, BambuPrintJob, BambuJobMaterial
messages.py          # i18n translations (cs + en dictionaries)
utils.py             # Shared helpers: get_settings(), get_current_lang(), get_current_currency(), get_current_theme(), log_movement()
routes/
  __init__.py        # register_all(app) - calls all register() functions
  inventory.py       # index, add, edit, delete, use_filament, add_spool, remove_spool
  api.py             # /api/filaments-list (AJAX endpoint for filtering/sorting)
  calculator.py      # /calculator, /calculator/history/<id>/delete
  history.py         # /history
  projects.py        # /projects, /projects/create, /projects/<id>, /projects/<id>/edit,
                     #   /projects/<id>/delete, /projects/<id>/add_filament,
                     #   /projects/<id>/update_filament/<pf_id>, /projects/<id>/remove_filament/<pf_id>,
                     #   /projects/<id>/upload, /projects/<id>/delete_file/<fid>,
                     #   /projects/<id>/add_link, /projects/<id>/delete_link/<lid>,
                     #   /projects/<id>/serve_file/<fid>, /projects/<id>/link_preview
  bambu.py           # /bambu, /bambu/sync, /bambu/job/<id>/assign, /bambu/job/<id>/deduct,
                     #   Bambu Cloud API integration (BambuPrinter, BambuPrintJob, BambuJobMaterial)
  settings.py        # /settings, /export, /import, /toggle-theme, /edit_bambu_printer
  stats.py           # /stats — Statistics dashboard (usage charts, forecast, stock health,
                     #   top-turnover, profitable projects, color palette). Sorted with HSL hue helper.
  storage.py         # /storage, /storage/shelf (POST), /storage/shelf/<id>/update,
                     #   /storage/shelf/<id>/delete, /storage/slot/assign,
                     #   /storage/placement/<id>/move, /storage/placement/<id>/orientation,
                     #   /storage/placement/<id>/delete — physical shelf/slot management
templates/
  base.html          # Layout with Alpine.js + TailwindCSS CDN
  index.html         # Inventory page (Alpine.js x-data="inventoryApp()")
  stats.html         # Statistics dashboard — Chart.js charts, 7 draggable sections (see rule 18)
  storage.html       # Visual storage shelf map
  ...
```

## Development and Conversation Rules (Core Prompts)
When a user asks for modifications to the project, you must follow and automatically apply these specifications:

1. **Translation Rule (i18n Prompt)**
   - Never use hardcoded text inside HTML (Jinja2) templates.
   - Always map strings using the `{{ t("new_key") }}` standard.
   - You must immediately expand the `messages.py` file by adding your new key/value pairs to both the `cs` (Czech) and `en` (English) dictionary objects.

2. **Database Rule (Schema Prompt)**
   - Models live in `models.py`. If you add a new column to a SQLAlchemy model, automatically add a safe SQL fallback inside `_safe_alter()` in `app.py` using the existing pattern:
     ```python
     _safe_alter("ALTER TABLE tablename ADD COLUMN column_name type")
     ```
     This prevents crashes on existing databases without needing Alembic.
   - **Whenever a feature adds, removes, or restructures any table or column, also update the backup schema** (see rule 17). The export and import functions in `routes/settings.py` must reflect the new or changed data so that backups remain complete.

3. **Route / Modularization Rule**
   - **Never use Flask Blueprints.** Blueprints require `url_for("blueprint.route_name")` prefixes in all templates and have caused breakage in this project.
   - When adding a new route, add it inside the appropriate `routes/*.py` file inside its `register(app)` function, or create a new `routes/feature.py` with a `register(app)` function and call it from `routes/__init__.py`.
   - `url_for("index")`, `url_for("add")`, etc. work as-is in templates — no prefix needed.

4. **Frontend State Rule (Alpine.js)**
   - Inventory page state (filters, sort, view mode) is managed by the Alpine.js component `inventoryApp()` defined in the `<script>` block of `templates/index.html`.
   - Use `x-data`, `x-model`, `x-on:click`, `x-show`, and `:class` Alpine directives instead of imperative vanilla JS for reactive UI.
   - The Alpine instance is exposed globally via `window.__inv = $data` so that AJAX-reloaded list header buttons can call `window.__inv.toggleSort("field")`.
   - Modal helpers (`openUseFilamentModal`, `closeUseFilamentModal`) remain as plain global JS functions since they are invoked from AJAX-loaded partial HTML.

5. **Docker and Deployment Rule**
   - After modifying core backend logic, templates, or translations, remind the user and ALWAYS automatically execute: `docker compose -f /opt/git/filament/docker-compose.yml up -d --build`.
   - A standard restart is not enough because local application code is not mounted via volumes and needs to be rebuilt into the image.
   - Application is accessible at `http://localhost:5050` (maps to container port `5000`).

6. **Versioning and Documentation Rule (Versioning Prompt)**
   - When introducing feature additions or structural UI fixes, bump the `APP_VERSION` variable in `app.py`.
   - Record and describe your changes properly inside `CHANGELOG.md` under the newly bumped version.
   - Immediately overwrite the version tag located at the top of the `README.md` file.

7. **CSS/Design Rule**
   - Do not alter existing CSS classes (especially spacing and baseline colors) unless specifically asked. Prioritize modern flexbox and grid behaviors for alignment. Button interfaces must retain their established spacing and animation classes like `hover:bg-... transition-all`.

8. **Jinja2 Template Variable Scoping Rule**
   - Variables defined with `{% set var = ... %}` inside a `{% for %}` loop are **scoped to that loop iteration**. They are NOT accessible in a different `{% for %}` loop even in the same template, nor in `{% else %}`/`{% elif %}` blocks of a different outer conditional.
   - When both card view and list view loops need the same per-item computed variable (e.g., `capacity_all`, `pct`), define it at the **start of each loop** independently:
     ```jinja2
     {% for fil in filaments.items %}
         {% set capacity_all = fil.quantity * fil.weight_total %}
         ...
     {% endfor %}
     ```
   - Partial templates (`_filament_cards.html`, `_filament_list_rows.html`) used by the AJAX API already handle their own variable definitions correctly.

9. **HTML Div Closing Rule Inside Jinja2 Loops**
   - Every `<div>` opened inside a `{% for %}` loop body **must be explicitly closed** within the same iteration. Missing a closing `</div>` (e.g., for the row wrapper) causes all subsequent iterations to be DOM-nested inside the first, producing a catastrophic layout collapse where items visually overlap.
   - This is especially deceptive because AJAX partials (`_filament_list_rows.html`) may have correct structure, so the page works fine after a card→list AJAX switch but breaks on the initial server-rendered page load.
   - Unclosed row divs in the loop also prevent the content wrapper div from being properly closed in the browser's DOM. This causes the modal (which follows after `{% endif %}`) to become a child of the content wrapper. Subsequent `fetchContent()` AJAX calls replace `wrapper.innerHTML`, removing the modal from the DOM and causing `document.getElementById('modalTitle')` to return `null`.
   - **Always count opening and closing `<div>` tags** in a loop body: for each `<div>` opened, there must be a corresponding `</div>` in the same template block.

10. **Alpine.js `x-cloak` Rule**
    - Any element that uses `x-show` and should be hidden before Alpine initializes must also have the `x-cloak` attribute.
    - The CSS rule `[x-cloak] { display: none !important; }` **must be present** in `base.html`'s `<style>` block (before the Alpine CDN `<script>` tag). Without it, `x-cloak` has no effect and the element flashes visible during page load.
    - This applies particularly to sort-by sections and other view-mode-dependent UI that is conditionally shown by Alpine.

11. **Alpine Reactive Flush vs. AJAX innerHTML Timing Rule**
    - Alpine 3 schedules its reactive DOM updates (`:class`, `x-show`, etc.) as a `queueMicrotask(flush)`. When `fetchContent()` is an `async` function that immediately calls `await fetch(...)`, the microtask ordering is not guaranteed to place Alpine's flush BEFORE the AJAX response resolves and `wrapper.innerHTML` is set — especially when the server responds near-instantly (localhost).
    - **Symptom**: after a card→list view switch via AJAX, list rows appear 3-per-row (the static SSR card grid classes `grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6` are still on the wrapper when list rows are injected).
    - **Fix**: inside `fetchContent()`, explicitly update `wrapper.classList` SYNCHRONOUSLY before setting `wrapper.innerHTML`. This is safe alongside Alpine's `:class` binding because `classList.add/remove` is idempotent:
      ```js
      if (this.viewMode === 'list') {
          wrapper.classList.remove('grid', 'grid-cols-1', 'md:grid-cols-2', 'lg:grid-cols-3', 'gap-6');
          wrapper.classList.add('space-y-0');
      } else {
          wrapper.classList.remove('space-y-0');
          wrapper.classList.add('grid', 'grid-cols-1', 'md:grid-cols-2', 'lg:grid-cols-3', 'gap-6');
      }
      wrapper.innerHTML = ...;
      ```
    - Never rely solely on Alpine `:class` reactive binding to set layout classes on an AJAX content wrapper. Always mirror the class update imperatively in the function that changes `innerHTML`.

12. **Fulltext Filter Dropdown Pattern**
    - Inventory page filters (brand, material, color) are implemented as custom Alpine.js fulltext search dropdowns, NOT native `<select>` elements.
    - Option data is embedded as JS arrays in the `inventoryApp()` component via Jinja2 at render time: `brandOptions: [{% for b in brands %}{"id":{{ b.id }},"name":{{ b.name|tojson }}}...{% endfor %}]`. Use `|tojson` for string values to handle quotes/special chars automatically.
    - Each filter has: `<field>Q` (search text input), `<field>Open` (dropdown open state), `filtered<Field>s` (computed getter that filters by `Q`), `select<Field>(id, name)` method.
    - Pre-population when page loads with active filters (e.g., `?brand=2`) is handled by the Alpine `init()` method, which looks up the name from the options array using loose equality (`==`) since IDs from `this.brand` are strings (from URL params) while option IDs are numbers.
    - The actual filter IDs (`this.brand`, `this.material`, `this.color`) fed to `fetchContent()` remain unchanged — only the display text (`brandQ` etc.) is a separate state variable.
    - Color filter options include `"hex"` field for rendering colored swatches (`:style="'background-color:' + opt.hex"`).
    - `resetFilters()` must clear **both** the ID (`this.brand = ''`) and the text (`this.brandQ = ''`) for all three filters.
    - Use `@click.outside="brandOpen = false"` (Alpine magic) on the wrapper `<div>` to close the dropdown when clicking elsewhere. Dropdowns use `x-show` + `x-cloak`.

13. **Low-Stock Indicators Rule**
    - When a filament has **0 quantity** (out of stock) or **< 20% remaining weight**, display a visual warning indicator in both card and list views.
    - **Card view** (`_filament_cards.html` and server card in `index.html`): absolute-positioned badge in top-right corner with:
      - Red background (`bg-red-600`) for out of stock (`fil.quantity == 0`)
      - Orange background (`bg-orange-500`) for low stock (`pct < 20`)
      - Text: `{{ t('out_of_stock') }}` or `{{ t('low_stock') }}`
    - **List view** (`_filament_list_rows.html` and server list in `index.html`): small icon badge next to the filament name with:
      - Red circle badge with `fa-exclamation-circle` icon for out of stock
      - Orange badge with `fa-triangle-exclamation` icon for low stock
    - **Important**: Define `pct` variable **before** the low-stock check. In server-rendered views, calculate `capacity_all` and `pct` before the outer card/row div. In partials, set them at the top of the loop.
    - I18n keys required: `'out_of_stock'` and `'low_stock'` (both in Czech and English).

14. **External Link Preview Security Rule**
    - Any server-side URL fetch used for link previews must allow only `http`/`https` URLs and must reject `localhost`, loopback addresses (`127.0.0.0/8`, `::1`), and non-public/private address ranges before making the request.
    - Redirect targets must be validated with the same rules before they are followed.
    - Preview extraction should prefer OpenGraph metadata, then Twitter cards, then standard HTML metadata (`<title>`, `<meta name="description">`) and resolve relative image URLs to absolute URLs.

15. **Project Upload Rule**
    - Project file uploads must be validated against an allowlist of supported image and 3D printing file extensions.
    - Stored filenames must always include a generated unique identifier so uploading the same filename twice never overwrites an existing file.
    - Image previews/lightboxes must use an inline-serving route; generic downloads may still use `as_attachment=True`.

16. **Testing Rule**
    - Security-sensitive helpers (URL validation, metadata fetching, upload validation) require automated regression tests under `tests/`.
    - Prefer `unittest` with `unittest.mock` for HTTP mocking unless the repository already standardizes on another framework.

17. **Backup Schema Rule (Full-Application Export/Import)**
    - The export (`/export`) and import (`/import`) functions in `routes/settings.py` must always cover the **entire persistent application state**. The canonical list of what must be included:

      | Category | Tables / data |
      |---|---|
      | Enumerations | `Brand`, `Color` (with `hex_value`), `Material` |
      | Inventory | `Filament` (all columns, resolved brand/color/material by name) |
      | Movement history | `MovementHistory` (filament ref, change, reason, timestamp) |
      | App settings | `AppSetting` (language, currency, theme, printer settings, energy cost, etc.) |
      | Calculator records | `PrintHistory` (all columns) |
      | Projects | `Project`, `ProjectFile` (filename + original name), `ProjectLink`, `ProjectFilament` |
      | Bambu integration | `BambuPrinter` (serial, access code, alias), `BambuPrintJob`, `BambuJobMaterial` |

    - **Referential integrity on import**: resolve foreign keys by name/serial (e.g. brand name → brand id) before inserting dependent rows. Commit enumerations before filaments; commit filaments before movement history etc.
    - **Idempotency**: use a "skip if already exists" strategy (check by natural key) so that importing the same backup twice does not create duplicates.
    - **Whenever a new model or column is added to the project, update both the export dict and the import handler in `routes/settings.py` in the same pull/commit.**

18. **Stats Page Draggable Layout Rule**
    - The Statistics page (`/stats`, `templates/stats.html`) has **7 named sections**, each a `<div class="stats-section" data-section-id="...">`:
      `section_kpi`, `section_overview`, `section_charts_primary`, `section_charts_secondary`, `section_tables`, `section_detail`, `section_colors`.
    - Section order, hidden card IDs, and per-card row limits are persisted in `localStorage` under the key **`stats_layout_v2`** as `{order:[...sectionIds], hidden:[...cardIds], limits:{cardId: number|'all'}}`.
    - **Edit mode** is toggled by `toggleEditMode()`. In edit mode the `<div id="stats-page">` gets the class `edit-mode`, which makes `.section-edit-bar` and `.card-edit-bar` elements visible via CSS.
    - Each section-edit-bar contains: a drag grip, a label, ▲/▼ reorder buttons (`moveSectionUp/Down(sectionId)`), and optionally a hide button.
    - Each card-edit-bar (inside `.stats-card`) contains: a label, a `<select class="widget-limit-select">`, and a hide button.
    - **Row limit display fix**: Always use `row.style.display = 'none'` / `row.style.display = ''` to show/hide `[data-row-index]` rows — **never `row.hidden = bool`** — because Tailwind's `display:flex` class on `<a>` elements overrides the UA `[hidden]` rule.
    - Color palette in `routes/stats.py` is sorted by HSL hue via `_hex_to_hsl_sort_key()` (chromatic colors in rainbow order, neutrals at end). Do **not** revert to alphabetical sort.
    - Chart.js is loaded via CDN; chart instances are created in a `<script>` block at the bottom of `stats.html`. Avoid re-fetching chart data via AJAX — it is embedded as `chart_data` JSON in the template.

---

## Post-Implementation Versioning Checklist

**After every set of feature additions or structural UI fixes:**

1. ✅ Verify that all changes are complete and Docker builds successfully
2. ✅ Check `app.py` – is `APP_VERSION = 'X.Y.Z'` set correctly?
3. ✅ **Bump version** in `app.py` (semantic versioning: major.minor.patch)
4. ✅ **Update changelog** in `CHANGELOG.md` under the new version section
5. ✅ **Update README.md** – change the version tag in the first line
6. ✅ `docker compose up -d --build` → verify HTTP 200
7. ✅ If the feature touched any DB table or column — verify that `/export` and `/import` in `routes/settings.py` are updated to match (rule 17).
8. ✅ If the feature added any user-facing text — verify that `messages.py` is updated with the new keys/values in both languages (rule 1).
9. ✅ If the feature added or modified any route — verify that it is registered correctly in the appropriate `routes/*.py` file and that `url_for()` works without prefixes (rule 3).
10. ✅ If the feature modified inventory filters or view modes — verify that Alpine.js state and `fetchContent()` class updates are correct (rules 4 and 11).
11. ✅ If the feature modified inventory item rendering — verify that low-stock indicators are implemented correctly (rule 13) and that all `<div>` tags are properly closed (rule 9). 
12. ✅ If the feature added any external URL fetching — verify that security rules are followed (rule 14).
13. ✅ If the feature added any file upload — verify that validation and naming rules are followed (rule 15).
14. ✅ If the feature added any security-sensitive helper — verify that automated tests are added (rule 16).
15. ✅ If the feature modified the frontend design — verify that Tailwind classes are used correctly and that spacing/colors are consistent (rule 7).
16. ✅ If the feature modified the Stats page sections, cards, row-limit logic, or color palette sort — verify compliance with rule 18.
17. ✅ Keep the readme and documentation up to date with any new features or changes.
18. ✅ Keep the instruction file up to date with any new rules or patterns that should be followed in future interactions.
19. ✅ Always maintain a clean commit history with descriptive messages for each change.
20. ✅ Regularly review and refactor code to maintain readability and performance as the project evolves.
21. ✅ Engage with users and gather feedback to continuously improve the application and address any issues that arise.
22. ✅ Stay informed about updates to the technologies used in the project (Flask, SQLAlchemy, TailwindCSS, Alpine.js) and apply necessary updates or optimizations when appropriate.
23. ✅ Ensure that the application remains secure by regularly reviewing code for potential vulnerabilities and applying best practices for web security.
24. ✅ Foster a collaborative development environment by encouraging contributions, providing clear documentation, and maintaining open communication channels for feedback and support.
25. ✅ Continuously monitor the application's performance and scalability, making necessary adjustments to ensure it can handle increased usage and data as the user base grows.