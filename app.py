"""
Filament Manager — application entry point.

Structure:
  database.py          — shared SQLAlchemy instance (db)
  models.py            — ORM models
  auth.py              — multi-user auth, RBAC, session management, invite system
  utils.py             — helpers (get_settings, log_movement, stock logic, …)
  messages.py          — i18n translation dictionaries (cs + en)
  routes/
    __init__.py        — register_all(app) aggregator
    inventory.py       — /, /filaments, /filament/<id>, /add, /edit, /use, /delete, bulk ops
    api.py             — /api/filaments-list, /api/search  (AJAX)
    calculator.py      — /calculator + print history
    history.py         — /history  (movement log)
    settings.py        — /settings, /export, /import
    projects.py        — /projects, /projects/<id>/*, comments, files, todos, quotes
    bambu.py           — /bambu, Bambu Cloud sync + job mapping
    prusa.py           — /prusa, PrusaLink polling + job mapping
    stats.py           — /stats  (dashboard statistics)
    storage.py         — /storage  (shelf/slot management)
    auth.py            — /login, /register, /users, /notifications
    pwa.py             — /manifest.json, /sw.js  (PWA support)
"""
import os
import json
import logging
import threading
import time
from datetime import datetime, timedelta
from flask import Flask, render_template
from flask_wtf.csrf import CSRFProtect
from sqlalchemy import text
from werkzeug.middleware.proxy_fix import ProxyFix

from database import db
from auth import init_app as init_auth, get_current_user, has_section_access, is_admin
from models import (
    Brand, Color, Material, AppSetting, Filament, 
    MovementHistory, PrintHistory, Project, ProjectFile, 
    ProjectLink, ProjectFilament, ProjectQuote, StorageShelf, StoragePlacement,
    BambuPrinter, BambuPrintJob, BambuJobMaterial,
    PrusaPrinter, PrusaPrintJob,
    User, UserInvite, Notification, AuditLog, ProjectComment,
    PrinterMaintenance, FilamentUndoLog,
)  # noqa: F401
from utils import get_settings, utc_now
from routes import register_all
from messages import TRANSLATIONS
from migrations import run_migrations

APP_VERSION = '1.85.13'

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
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
    app.config['SESSION_COOKIE_SECURE'] = bool(os.environ.get('BEHIND_PROXY'))
    app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=14)
    # Increase SQLite busy-timeout to reduce 'database is locked' errors under load.
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
        'connect_args': {'timeout': 30},
    }

    if test_config:
        app.config.update(test_config)

    db.init_app(app)

    # Enable WAL mode and synchronous=NORMAL for SQLite connections to improve concurrency
    with app.app_context():
        if db.engine.url.drivername == 'sqlite':
            from sqlalchemy import event
            @event.listens_for(db.engine, "connect")
            def set_sqlite_pragma(dbapi_connection, connection_record):
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute("PRAGMA synchronous=NORMAL")
                cursor.execute("PRAGMA cache_size=-16000")
                cursor.execute("PRAGMA mmap_size=268435456")
                cursor.execute("PRAGMA temp_store=MEMORY")
                cursor.close()

    csrf.init_app(app)
    init_auth(app)
    register_all(app)

    # ── url_for fallback for decomposed Blueprints ─────────────────────────────
    from flask import url_for
    from werkzeug.routing import BuildError

    def url_for_fallback(error, endpoint, values):
        if "." in endpoint:
            raise error
        for bp_name in app.blueprints:
            prefixed = f"{bp_name}.{endpoint}"
            if prefixed in app.view_functions:
                try:
                    return url_for(prefixed, **values)
                except BuildError:
                    pass
        raise error

    app.url_build_error_handlers.append(url_for_fallback)


    # ── Pretty-print JSON filter ───────────────────────────────────────────────
    import json as _json

    @app.template_filter('pretty_json')
    def _pretty_json_filter(value):
        """Try to parse value as JSON and return an indented string.
        Falls back to the original value if parsing fails."""
        if not value:
            return value
        try:
            parsed = _json.loads(value)
            return _json.dumps(parsed, indent=2, ensure_ascii=False)
        except (ValueError, TypeError):
            return value

    # ── Timezone-aware datetime formatting filter ─────────────────────────────
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
    from datetime import date as _date

    @app.template_filter('fmt_dt')
    def _fmt_dt_filter(value, fmt='%d.%m.%Y %H:%M'):
        """Format a naive-UTC datetime into the configured app timezone.

        Returns an empty string for None/falsy values.
        Pure ``date`` objects (no time component) are formatted without
        timezone conversion since they carry no time-of-day information.
        """
        if not value:
            return ''
        if type(value) is _date:
            # Pure date — no conversion, just format.
            return value.strftime(fmt)
        try:
            from utils import get_settings as _get_settings
            setting = _get_settings()
            tz_name = (setting.app_timezone if setting and setting.app_timezone else 'Europe/Prague')
            local = value.replace(tzinfo=ZoneInfo('UTC')).astimezone(ZoneInfo(tz_name))
            return local.strftime(fmt)
        except (ZoneInfoNotFoundError, Exception):
            return value.strftime(fmt)

    @app.context_processor
    def inject_globals():
        setting = get_settings()
        lang = setting.lang if setting else 'cs'
        currency = setting.currency if setting and setting.currency else 'CZK'
        theme = setting.theme if setting and setting.theme else 'light'
        nav_palette = setting.nav_palette if setting and setting.nav_palette else 'teal'
        current_user = get_current_user()

        def t(key):
            return TRANSLATIONS.get(lang, TRANSLATIONS['cs']).get(key, key)

        # Navigation visibility flags ─────────────────────────────────────────
        printer_access = has_section_access('printers', user=current_user) or is_admin(current_user)
        nav_bambu_enabled = bool(setting and setting.bambu_token and printer_access)
        nav_audit_enabled = bool(setting and getattr(setting, 'audit_logging_enabled', True) and is_admin(current_user))
        try:
            from flask import g
            if 'nav_prusa_enabled' not in g:
                from models import PrusaPrinter
                g.nav_prusa_enabled = bool(printer_access and PrusaPrinter.query.filter_by(enabled=True).first() is not None)
            nav_prusa_enabled = g.nav_prusa_enabled
        except Exception:
            nav_prusa_enabled = False

        from flask import session as _session
        ui_mode = _session.get('ui_mode', 'admin')  # 'admin' or 'operator'
        pending_inventory_undo = None
        raw_undo = _session.get('inventory_pending_undo')
        if isinstance(raw_undo, dict):
            expires_raw = raw_undo.get('expires_at')
            try:
                expires_at = datetime.fromisoformat(expires_raw) if expires_raw else None
            except (TypeError, ValueError):
                expires_at = None

            if expires_at and expires_at > utc_now():
                pending_inventory_undo = raw_undo
            else:
                _session.pop('inventory_pending_undo', None)

        return dict(
            t=t,
            current_lang=lang,
            current_currency=currency,
            theme=theme,
            nav_palette=nav_palette,
            app_version=APP_VERSION,
            nav_bambu_enabled=nav_bambu_enabled,
            nav_prusa_enabled=nav_prusa_enabled,
            nav_audit_enabled=nav_audit_enabled,
            current_user=current_user,
            auth_has_section_access=has_section_access,
            auth_is_admin=is_admin,
            ui_mode=ui_mode,
            pending_inventory_undo=pending_inventory_undo,
        )

    @app.errorhandler(403)
    def forbidden(_error):
        return render_template('error_403.html'), 403

    @app.after_request
    def add_security_headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        response.headers['Permissions-Policy'] = 'geolocation=(), microphone=(), camera=()'
        response.headers['Content-Security-Policy'] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com; "
            "img-src 'self' data: https:; "
            "font-src 'self' https://fonts.gstatic.com; "
            "connect-src 'self' ws: wss:;"
        )
        if request_is_secure(response):
            response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
        return response

    @app.after_request
    def _invalidate_kpi_on_write(response):
        """Flush the KPI cache after any successful mutation so the overview stays fresh."""
        from flask import request as _req
        if _req.method in ('POST', 'PUT', 'PATCH', 'DELETE') and response.status_code < 400:
            from utils import invalidate_kpi_cache
            invalidate_kpi_cache()
        return response

    run_migrations(app)
    _start_bambu_sync_worker(app)
    _start_prusa_sync_worker(app)
    return app


def request_is_secure(response) -> bool:
    try:
        from flask import request
        forwarded_proto = request.headers.get('X-Forwarded-Proto', '')
        return bool(request.is_secure or forwarded_proto == 'https')
    except RuntimeError:
        return False





def _acquire_worker_lock(app: Flask, worker_name: str) -> bool:
    """Return True if this process should start the named background worker.

    Uses a PID-file in the data directory to prevent duplicate workers when
    Gunicorn is started with more than one worker process.  The lock is
    considered stale if the recorded PID no longer exists in the OS process
    table (e.g. after a crash or restart), at which point the current process
    takes over.
    """
    data_dir = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'data')
    lock_path = os.path.join(data_dir, f'.{worker_name}_worker.pid')
    my_pid = os.getpid()

    try:
        # Atomic check-and-write: try to exclusively create the lock file first.
        try:
            with open(lock_path, 'x') as fh:
                fh.write(str(my_pid))
            return True
        except FileExistsError:
            # Lock file already exists, read the owner pid.
            try:
                with open(lock_path, 'r') as fh:
                    existing_pid = int(fh.read().strip())
            except (ValueError, TypeError, IOError):
                # Corrupt lock file — take over.
                existing_pid = None

            if existing_pid is not None and existing_pid != my_pid:
                # Check whether the owning process is still alive.
                try:
                    os.kill(existing_pid, 0)  # signal 0 = existence check only
                    app.logger.info(
                        '%s-worker already owned by PID %d — skipping start in PID %d',
                        worker_name, existing_pid, my_pid,
                    )
                    return False
                except (ProcessLookupError, PermissionError):
                    # Stale lock — the previous owner is gone; take it over.
                    app.logger.info(
                        'Stale %s-worker lock (PID %d gone) — taking over in PID %d',
                        worker_name, existing_pid, my_pid,
                    )

            # Write our PID to assume ownership
            with open(lock_path, 'w') as fh:
                fh.write(str(my_pid))
            return True
    except Exception as exc:
        app.logger.warning('Could not acquire %s-worker lock: %s', worker_name, exc)
        # Fall back to always starting the worker (original behaviour) so a lock
        # file permission error doesn't silently break background sync.
        return True


def _start_bambu_sync_worker(app: Flask) -> None:
    if app.config.get('TESTING'):
        return
    if app.debug and os.environ.get('WERKZEUG_RUN_MAIN') != 'true':
        return
    if app.extensions.get('bambu_sync_worker_started'):
        return
    if not _acquire_worker_lock(app, 'bambu'):
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
                            or setting.bambu_last_sync_at <= utc_now() - timedelta(minutes=interval)
                        )
                        if due:
                            token = decrypt_token(setting.bambu_token)
                            result = do_sync(token, setting.bambu_region or 'global')
                            setting.bambu_last_sync_at = utc_now()
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


def _start_prusa_sync_worker(app: Flask) -> None:
    """Background thread that polls all enabled PrusaLink printers every 60 s."""
    if app.config.get('TESTING'):
        return
    if app.debug and os.environ.get('WERKZEUG_RUN_MAIN') != 'true':
        return
    if app.extensions.get('prusa_sync_worker_started'):
        return
    if not _acquire_worker_lock(app, 'prusa'):
        return

    app.extensions['prusa_sync_worker_started'] = True

    def worker():
        from routes.prusa import do_poll

        _consecutive_errors = 0
        while True:
            try:
                with app.app_context():
                    printers = PrusaPrinter.query.filter_by(enabled=True).all()
                    for printer in printers:
                        try:
                            do_poll(printer)
                        except Exception as exc:
                            app.logger.warning('Prusa poll error for %s: %s', printer.name, exc)
                _consecutive_errors = 0
            except Exception as exc:
                app.logger.error('Background Prusa sync failed: %s', exc)
                _consecutive_errors += 1
            # Poll interval: 60 s under normal conditions, exponential backoff on errors
            time.sleep(min(60 * (2 ** min(_consecutive_errors, 4)), 900))

    thread = threading.Thread(target=worker, name='prusa-sync-worker', daemon=True)
    thread.start()


# WSGI entry point (Gunicorn) and dev server
app = create_app()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
