# GitHub Copilot Custom Instructions for the Filament Manager Project

This file contains permanent instructions and prompts for future interactions. Always keep this context in mind to provide the correct code outputs!

## Main Project Context (Tech Stack)
- **Application:** Web-based 3D filament management and slicer-based print cost calculator.
- **Backend:** Python 3.11, Flask, SQLAlchemy (without complex DB migrations like Alembic), SQLite (persisted in the `./data/` directory).
- **Frontend:** Jinja2 templates, TailwindCSS via CDN (responsive UI using flex/grid), FontAwesome icons.
- **Infrastructure:** Docker & Docker Compose (`filament_app`, port `5050:5000`).

## Development and Conversation Rules (Core Prompts)
When a user asks for modifications to the project, you must follow and automatically apply these specifications:

1. **Translation Rule (i18n Prompt)**
   - Never use hardcoded text inside HTML (Jinja2) templates.
   - Always map strings using the `{{ t('new_key') }}` standard.
   - You must immediately expand the `messages.py` file by adding your new key/value pairs to both the `cs` (Czech) and `en` (English) dictionary objects.

2. **Database Rule (Schema Prompt)**
   - If you modify models in `app.py` (e.g., adding a new column to a SQLAlchemy class), automatically create a safe SQL fallback inside the `setup_database()` function using `try: db.session.execute(text('ALTER TABLE ... ADD COLUMN ...')) except: db.session.rollback()`. This prevents crashes for existing relational collections without needing a complete DB migration utility.

3. **Docker and Deployment Rule**
   - After modifying core backend logic (`app.py`), templates, or translations, remind the user and ALWAYS automatically execute the following command in the terminal: `docker compose -f /opt/git/filament/docker-compose.yml up -d --build`. 
   - A standard restart isn't enough because local application code is not mounted via volumes and needs to be rebuilt into the image.

4. **Versioning and Documentation Rule (Versioning Prompt)**
   - When introducing feature additions or structural UI fixes, bump the `APP_VERSION` variable in `app.py`.
   - Record and describe your changes properly inside `CHANGELOG.md` under the newly bumped version.
   - Immediately overwrite the version tag located at the top of the `README.md` file.

5. **CSS/Design Rule**
   - Do not alter existing CSS classes (especially spacing and baseline colors) unless specifically asked. Prioritize modern flexbox and grid behaviors for alignment (e.g., `<div class="grid grid-cols-1 md:grid-cols-3 gap-5">`). Button interfaces must retain their established spacing and animation classes like `hover:bg-... transition-all`.
