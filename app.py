"""
Filament Manager — application entry point.

Structure:
  database.py          — shared SQLAlchemy instance (db)
  models.py            — ORM models
  utils.py             — helpers (get_settings, log_movement, …)
  routes/
    __init__.py        — register_all(app) aggregator
    inventory.py       — index, add, edit, delete, spool management
    api.py             — /api/filaments-list  (AJAX)
    calculator.py      — /calculator + print history
    history.py         — /history  (movement log)
    settings.py        — /settings, /export, /import, /toggle-theme
  messages.py          — i18n translation dictionaries
"""
import os
import json
import logging
import threading
import time
from datetime import datetime, timedelta
from flask import Flask
from flask_wtf.csrf import CSRFProtect
from sqlalchemy import text
from werkzeug.middleware.proxy_fix import ProxyFix

from database import db
from models import (
    Brand, Color, Material, AppSetting, Filament, 
    MovementHistory, PrintHistory, Project, ProjectFile, 
    ProjectLink, ProjectFilament, ProjectQuote, StorageShelf, StoragePlacement, BambuPrinter, BambuPrintJob, BambuJobMaterial
)  # noqa: F401
from utils import get_settings
from routes import register_all
from messages import TRANSLATIONS

APP_VERSION = '1.38.0'

csrf = CSRFProtect()


def create_app(test_config=None) -> Flask:
    app = Flask(__name__)
    # Secret key: must be set via SECRET_KEY env var in production.
    # Defaults to a random value (sessions lost on restart) if not configured.
    app.secret_key = os.environ.get('SECRET_KEY', os.urandom(24).hex())
    if not os.environ.get('SECRET_KEY'):
        app.logger.warning('SECRET_KEY env var not set — sessions will not persist across restarts.')
    # Only trust X-Forwarded-* headers when explicitly running behind a reverse proxy.
    if os.environ.get('BEHIND_PROXY'):
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

    db_dir = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'data')
    os.makedirs(db_dir, exist_ok=True)
    app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{os.path.join(db_dir, "filament.db")}'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['MAX_CONTENT_LENGTH'] = 64 * 1024 * 1024
    app.config['PROJECT_UPLOAD_FOLDER'] = os.path.join(db_dir, 'uploads')
    # Increase SQLite busy-timeout to reduce 'database is locked' errors under load.
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
        'connect_args': {'timeout': 30},
    }

    if test_config:
        app.config.update(test_config)

    db.init_app(app)
    csrf.init_app(app)
    register_all(app)

    @app.context_processor
    def inject_globals():
        setting = get_settings()
        lang = setting.lang if setting else 'cs'
        currency = setting.currency if setting and setting.currency else 'CZK'
        theme = setting.theme if setting and setting.theme else 'light'

        def t(key):
            return TRANSLATIONS.get(lang, TRANSLATIONS['cs']).get(key, key)

        return dict(t=t, current_lang=lang, current_currency=currency, theme=theme, app_version=APP_VERSION)

    _setup_database(app)
    _start_bambu_sync_worker(app)
    return app


def _setup_database(app: Flask) -> None:
    """Create tables and run safe ALTER TABLE migrations for existing databases."""
    with app.app_context():
        db.create_all()

        if not Brand.query.first():
            for name in ['Prusament', 'Hatchbox', 'eSUN', 'Sunlu', 'Polymaker', 'Overture', 'Spectrum', 'Fiberlogy']:
                db.session.add(Brand(name=name))
            for name in ['PLA', 'PETG', 'ABS', 'ASA', 'TPU', 'PC', 'Nylon']:
                db.session.add(Material(name=name))
            for name, hex_val in [
                ('Černá', '#000000'), ('Bílá', '#FFFFFF'), ('Šedá', '#808080'),
                ('Červená', '#FF0000'), ('Modrá', '#0000FF'), ('Zelená', '#00FF00'),
                ('Žlutá', '#FFFF00'), ('Oranžová', '#FFA500'), ('Fialová', '#800080'),
                ('Průhledná', '#edf2f7'), ('Stříbrná', '#C0C0C0'), ('Zlatá', '#FFD700'),
            ]:
                db.session.add(Color(name=name, hex_value=hex_val))
            db.session.commit()

        _safe_alter(app, 'ALTER TABLE filament ADD COLUMN quantity INTEGER NOT NULL DEFAULT 1')
        _safe_alter(app, 'ALTER TABLE filament ADD COLUMN min_stock_grams FLOAT NOT NULL DEFAULT 0')
        _safe_alter(app, 'ALTER TABLE filament ADD COLUMN max_stock_grams FLOAT NOT NULL DEFAULT 0')
        _safe_alter(app, 'ALTER TABLE filament ADD COLUMN tag_text TEXT DEFAULT NULL')
        _safe_alter(app, 'ALTER TABLE filament ADD COLUMN quality_stringing TEXT DEFAULT NULL')
        _safe_alter(app, 'ALTER TABLE filament ADD COLUMN quality_adhesion TEXT DEFAULT NULL')
        _safe_alter(app, 'ALTER TABLE filament ADD COLUMN quality_drying TEXT DEFAULT NULL')
        _safe_alter(app, 'ALTER TABLE filament ADD COLUMN quality_profile TEXT DEFAULT NULL')
        _safe_alter(app, 'ALTER TABLE filament ADD COLUMN quality_notes TEXT DEFAULT NULL')
        _safe_alter(app, 'ALTER TABLE filament ADD COLUMN recommended_nozzle_temp INTEGER DEFAULT NULL')
        _safe_alter(app, 'ALTER TABLE filament ADD COLUMN recommended_bed_temp INTEGER DEFAULT NULL')
        _safe_alter(app, 'ALTER TABLE filament ADD COLUMN reorder_alert_snoozed BOOLEAN NOT NULL DEFAULT 0')
        _safe_alter(app, 'ALTER TABLE app_setting ADD COLUMN kwh_price FLOAT NOT NULL DEFAULT 5.0')
        _safe_alter(app, 'ALTER TABLE app_setting ADD COLUMN printer_power INTEGER NOT NULL DEFAULT 150')
        _safe_alter(app, "ALTER TABLE app_setting ADD COLUMN currency VARCHAR(10) NOT NULL DEFAULT 'CZK'")
        _safe_alter(app, 'ALTER TABLE app_setting ADD COLUMN debug_logging BOOLEAN NOT NULL DEFAULT 0')
        _safe_alter(app, "ALTER TABLE app_setting ADD COLUMN theme VARCHAR(10) NOT NULL DEFAULT 'light'")
        _safe_alter(app, "ALTER TABLE app_setting ADD COLUMN view_mode VARCHAR(10) NOT NULL DEFAULT 'card'")
        _safe_alter(app, "ALTER TABLE app_setting ADD COLUMN items_per_page INTEGER NOT NULL DEFAULT 12")
        _safe_alter(app, 'ALTER TABLE app_setting ADD COLUMN bambu_auto_sync_enabled BOOLEAN NOT NULL DEFAULT 0')
        _safe_alter(app, 'ALTER TABLE app_setting ADD COLUMN bambu_auto_sync_interval_minutes INTEGER NOT NULL DEFAULT 60')
        _safe_alter(app, 'ALTER TABLE app_setting ADD COLUMN bambu_last_sync_at DATETIME DEFAULT NULL')
        _safe_alter(app, 'ALTER TABLE app_setting ADD COLUMN bambu_last_sync_status VARCHAR(255) DEFAULT NULL')

        _safe_alter(app, "ALTER TABLE project_link ADD COLUMN og_title VARCHAR(255) DEFAULT NULL")
        _safe_alter(app, "ALTER TABLE project_link ADD COLUMN og_image VARCHAR(500) DEFAULT NULL")
        _safe_alter(app, "ALTER TABLE project_link ADD COLUMN og_description TEXT DEFAULT NULL")
        _safe_alter(app, 'ALTER TABLE project ADD COLUMN tag_text TEXT DEFAULT NULL')
        _safe_alter(app, 'ALTER TABLE movement_history ADD COLUMN filament_id INTEGER DEFAULT NULL')
        _safe_alter(app, 'ALTER TABLE movement_history ADD COLUMN project_id INTEGER DEFAULT NULL')
        _safe_alter(app, 'ALTER TABLE movement_history ADD COLUMN bambu_job_id INTEGER DEFAULT NULL')
        _safe_alter(app, 'ALTER TABLE movement_history ADD COLUMN note TEXT DEFAULT NULL')

        # Bambu Lab Cloud integration
        _safe_alter(app, "ALTER TABLE app_setting ADD COLUMN bambu_token TEXT DEFAULT NULL")
        _safe_alter(app, "ALTER TABLE app_setting ADD COLUMN bambu_region VARCHAR(10) NOT NULL DEFAULT 'global'")
        _safe_alter(app, "ALTER TABLE bambu_print_job ADD COLUMN cost_time INTEGER DEFAULT NULL")
        _safe_alter(app, "ALTER TABLE project_link ADD COLUMN domain VARCHAR(100) DEFAULT NULL")

        if not AppSetting.query.first():
            db.session.add(AppSetting(lang='cs', kwh_price=5.0, printer_power=150,
                                      currency='CZK', debug_logging=False, theme='light', view_mode='card', items_per_page=12))
        setting = AppSetting.query.first()
        if setting and setting.debug_logging:
            app.logger.setLevel(logging.DEBUG)
        else:
            app.logger.setLevel(logging.INFO)


def _safe_alter(app: Flask, sql: str) -> None:
    """Run a schema migration SQL inside the already-active app context."""
    try:
        db.session.execute(text(sql))
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        message = str(e).lower()
        if 'duplicate column name' in message or 'already exists' in message:
            app.logger.debug(f"Skipping existing schema change for '{sql}'")
        else:
            app.logger.error(f"Error in _safe_alter executing '{sql}': {e}")


def _start_bambu_sync_worker(app: Flask) -> None:
    if app.config.get('TESTING'):
        return
    if app.debug and os.environ.get('WERKZEUG_RUN_MAIN') != 'true':
        return
    if app.extensions.get('bambu_sync_worker_started'):
        return

    app.extensions['bambu_sync_worker_started'] = True

    def worker():
        from routes.bambu import do_sync
        from utils import decrypt_token

        _consecutive_errors = 0
        while True:
            try:
                with app.app_context():
                    setting = AppSetting.query.first()
                    if (
                        setting
                        and setting.bambu_token
                        and setting.bambu_auto_sync_enabled
                    ):
                        interval = max(int(setting.bambu_auto_sync_interval_minutes or 60), 5)
                        due = (
                            not setting.bambu_last_sync_at
                            or setting.bambu_last_sync_at <= datetime.utcnow() - timedelta(minutes=interval)
                        )
                        if due:
                            token = decrypt_token(setting.bambu_token)
                            result = do_sync(token, setting.bambu_region or 'global')
                            setting.bambu_last_sync_at = datetime.utcnow()
                            if result.get('error'):
                                setting.bambu_last_sync_status = f"error: {result['error'][:220]}"
                            else:
                                setting.bambu_last_sync_status = json.dumps({
                                    'added': result.get('added', 0),
                                    'updated': result.get('updated', 0),
                                    'skipped': result.get('skipped', 0),
                                })
                            db.session.commit()
                _consecutive_errors = 0
            except Exception as exc:
                app.logger.error("Background Bambu sync failed: %s", exc)
                _consecutive_errors += 1
            # Exponential backoff: 60s → 120s → 240s → … → 3600s max
            time.sleep(min(60 * (2 ** min(_consecutive_errors, 5)), 3600))

    thread = threading.Thread(target=worker, name='bambu-sync-worker', daemon=True)
    thread.start()


# WSGI entry point (Gunicorn) and dev server
app = create_app()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
