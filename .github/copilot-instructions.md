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
models.py            # All 6 ORM models: Brand, Color, Material, Filament, MovementHistory, AppSetting, PrintHistory
messages.py          # i18n translations (cs + en dictionaries)
utils.py             # Shared helpers: get_settings(), get_current_lang(), get_current_currency(), get_current_theme(), log_movement()
routes/
  __init__.py        # register_all(app) - calls all register() functions
  inventory.py       # index, add, edit, delete, use_filament, add_spool, remove_spool
  api.py             # /api/filaments-list (AJAX endpoint for filtering/sorting)
  calculator.py      # /calculator, /calculator/history/<id>/delete
  history.py         # /history
  settings.py        # /settings, /export, /import, /toggle-theme
templates/
  base.html          # Layout with Alpine.js + TailwindCSS CDN
  index.html         # Inventory page (Alpine.js x-data="inventoryApp()")
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
