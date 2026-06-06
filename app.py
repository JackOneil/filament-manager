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
    settings.py        — /settings, dictionary management, integrations
    backup.py          — /export, /import
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
from flask_compress import Compress
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
    PrinterMaintenance, FilamentUndoLog, ProjectTemplate, ProjectCommentReaction,
)  # noqa: F401
from utils import get_settings, utc_now
from routes import register_all
from messages import TRANSLATIONS
from migrations import run_migrations

APP_VERSION = '1.107.3'

csrf = CSRFProtect()


def create_app(test_config=None) -> Flask:
    app = Flask(__name__)
    app.config['APP_VERSION'] = APP_VERSION
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
    # SESSION_COOKIE_SECURE: only send cookies over HTTPS.
    # Set BEHIND_PROXY=1 when running behind a TLS-terminating reverse proxy
    # (e.g. nginx, Traefik) that handles HTTPS and forwards plain HTTP to the app.
    # Without this flag, session cookies may be exposed over unencrypted connections.
    _behind_proxy = bool(os.environ.get('BEHIND_PROXY'))
    app.config['SESSION_COOKIE_SECURE'] = _behind_proxy
    if not _behind_proxy:
        app.logger.warning(
            'SESSION_COOKIE_SECURE is disabled (BEHIND_PROXY not set). '
            'Session cookies will be transmitted over HTTP — enable BEHIND_PROXY '
            'when running behind a TLS-terminating reverse proxy in production.'
        )
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
    Compress(app)
    init_auth(app)
    register_all(app)

    # ── CSP nonce generation (per request) ───────────────────────────────────
    import secrets as _secrets

    @app.before_request
    def _set_csp_nonce():
        from flask import g as _g_csp
        _g_csp.csp_nonce = _secrets.token_hex(32)

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
        """Format a UTC datetime into the configured app timezone.

        Returns an empty string for None/falsy values.
        Pure ``date`` objects (no time component) are formatted without
        timezone conversion since they carry no time-of-day information.

        Handles both timezone-aware and naive datetimes:
          - Aware datetimes are converted directly to the target timezone.
          - Naive datetimes are assumed to be UTC and converted accordingly
            (backward compatibility with old database records).
        """
        if not value:
            return ''
        if type(value) is _date:
            return value.strftime(fmt)
        try:
            from utils import get_settings as _get_settings
            setting = _get_settings()
            tz_name = (setting.app_timezone if setting and setting.app_timezone else 'Europe/Prague')
            target_tz = ZoneInfo(tz_name)
            if value.tzinfo is not None:
                # Timezone-aware — convert directly.
                local = value.astimezone(target_tz)
            else:
                # Legacy naive UTC — assume UTC, then convert.
                local = value.replace(tzinfo=ZoneInfo('UTC')).astimezone(target_tz)
            return local.strftime(fmt)
        except (ZoneInfoNotFoundError, Exception):
            return value.strftime(fmt)

    @app.template_filter('hue_from')
    def _filter_hue_from(value):
        """Derive a deterministic HSL hue (0-360) from a string."""
        if not value:
            return 'hsl(200, 60%, 50%)'
        h = hash(str(value)) % 360
        return f'hsl({h}, 60%, 50%)'

    @app.context_processor
    def inject_globals():
        setting = get_settings()
        current_user = get_current_user()
        lang = setting.lang if setting else 'cs'
        # Per-user language override
        if current_user and current_user.preferred_language:
            lang = current_user.preferred_language
        currency = setting.currency if setting and setting.currency else 'CZK'
        theme = setting.theme if setting and setting.theme else 'light'
        # Per-user theme override
        if current_user and current_user.preferred_theme:
            theme = current_user.preferred_theme
        nav_palette = setting.nav_palette if setting and setting.nav_palette else 'teal'

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

        # Generic project-undo slot (project + project file deletion).
        pending_project_undo = None
        raw_proj_undo = _session.get('project_pending_undo')
        if isinstance(raw_proj_undo, dict):
            expires_raw = raw_proj_undo.get('expires_at')
            try:
                expires_at = datetime.fromisoformat(expires_raw) if expires_raw else None
            except (TypeError, ValueError):
                expires_at = None

            if expires_at and expires_at > utc_now():
                pending_project_undo = raw_proj_undo
            else:
                _session.pop('project_pending_undo', None)

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
            pending_project_undo=pending_project_undo,
            csp_nonce=getattr(g, 'csp_nonce', ''),
        )

    @app.errorhandler(403)
    def forbidden(_error):
        return render_template('error_403.html'), 403

    @app.after_request
    def add_security_headers(response):
        from flask import g as _g_sec
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        response.headers['Permissions-Policy'] = 'geolocation=(), microphone=(), camera=()'
        response.headers['Content-Security-Policy'] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-eval' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com; "
            "img-src 'self' data: https:; "
            "font-src 'self' https://fonts.gstatic.com; "
            "connect-src 'self' ws: wss: blob: https://cdn.jsdelivr.net; "
            "worker-src 'self' blob: https://cdn.jsdelivr.net; "
            "child-src 'self' blob: https://cdn.jsdelivr.net; "
            "frame-src 'self';"
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
    _start_auto_backup_worker(app)
    _start_model_thumbnail_worker(app)
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


def _compute_next_auto_backup_run(
    now_local,
    freq: str,
    time_str: str,
    day_val: int,
):
    """Return the next local-time datetime the backup should run.

    Refactor 4.4: previously the worker relied on a 5-minute polling
    window and string-typed freq/day.  We now compute the next run
    explicitly so:

    * a sleep gap longer than 5 minutes (GC pause, IO stall, restart)
      no longer causes the worker to silently skip a cycle;
    * "weekly" / "monthly" decisions are made against a *target* day
      rather than the polling tick;
    * the worker can sleep for the full interval (≈24 h for daily)
      and only spin every 60 s for cheap reconfiguration detection.

    Returns ``None`` when the configuration is invalid.
    """
    from datetime import datetime as _datetime, timedelta as _timedelta

    try:
        hour, minute = (int(p) for p in time_str.split(':', 1))
    except (ValueError, AttributeError):
        return None
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None

    freq = (freq or 'weekly').lower()
    if freq not in {'daily', 'weekly', 'monthly'}:
        return None

    # Anchor at today's target time in the local timezone.
    target_today = now_local.replace(hour=hour, minute=minute, second=0, microsecond=0)

    if freq == 'daily':
        next_run = target_today if now_local < target_today else target_today + _timedelta(days=1)

    elif freq == 'weekly':
        # 0 = Monday, 6 = Sunday (Python's ``weekday()`` convention).
        day_val = max(0, min(int(day_val or 0), 6))
        days_ahead = (day_val - now_local.weekday()) % 7
        candidate = target_today + _timedelta(days=days_ahead)
        if candidate <= now_local:
            candidate += _timedelta(days=7)
        next_run = candidate

    else:  # monthly
        day_val = max(1, min(int(day_val or 1), 31))
        year, month = now_local.year, now_local.month

        def _clamped(year_, month_):
            """Return the day-of-month for the requested schedule in the
            given calendar month, clamping to the month's last day so
            e.g. Feb 31 → Feb 28/29.  All datetimes are offset-aware so
            they can be compared with ``now_local`` (Python 3.12+
            requires consistent tz-awareness)."""
            if month_ == 12:
                first_next = _datetime(year_ + 1, 1, 1, tzinfo=now_local.tzinfo)
            else:
                first_next = _datetime(year_, month_ + 1, 1, tzinfo=now_local.tzinfo)
            last_day = (first_next - _timedelta(days=1)).day
            clamped = min(day_val, last_day)
            return _datetime(year_, month_, clamped, hour, minute, tzinfo=now_local.tzinfo)

        # Try the current month first (with day-of-month clamping).
        current_month_candidate = _clamped(year, month)
        if current_month_candidate > now_local:
            next_run = current_month_candidate
        else:
            # Otherwise walk forward to the next month(s).
            while True:
                if month == 12:
                    year += 1
                    month = 1
                else:
                    month += 1
                candidate = _clamped(year, month)
                if candidate > now_local:
                    next_run = candidate
                    break

    return next_run


def _start_auto_backup_worker(app: Flask) -> None:
    """Background thread that runs automatic backups on a schedule.

    The worker is now driven by an explicit next-run computation
    (refactor 4.4): we look up the next scheduled time, sleep until
    60 s before it, then poll every 60 s to either run the backup or
    fall through to the next cycle if a restart / long pause caused us
    to miss the previous one.
    """
    if app.config.get('TESTING'):
        return
    if app.debug and os.environ.get('WERKZEUG_RUN_MAIN') != 'true':
        return
    if app.extensions.get('auto_backup_worker_started'):
        return
    if not _acquire_worker_lock(app, 'auto-backup'):
        return

    app.extensions['auto_backup_worker_started'] = True

    def worker():
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
        from datetime import datetime as _datetime, timedelta as _timedelta

        while True:
            try:
                time.sleep(60)
                with app.app_context():
                    from models import AppSetting
                    setting = AppSetting.query.first()
                    if not setting or not getattr(setting, 'backup_auto_enabled', False):
                        continue

                    freq = getattr(setting, 'backup_auto_frequency', 'weekly') or 'weekly'
                    time_str = getattr(setting, 'backup_auto_time', '03:00') or '03:00'
                    day_val = getattr(setting, 'backup_auto_day', 1) or 1
                    include_files = bool(getattr(setting, 'backup_auto_include_files', True))

                    tz_name = getattr(setting, 'app_timezone', 'Europe/Prague') or 'Europe/Prague'
                    try:
                        tz = ZoneInfo(tz_name)
                    except (ZoneInfoNotFoundError, KeyError):
                        tz = ZoneInfo('Europe/Prague')

                    now_utc = _datetime.now(ZoneInfo('UTC'))
                    now_local = now_utc.astimezone(tz)

                    next_run = _compute_next_auto_backup_run(now_local, freq, time_str, day_val)
                    if next_run is None:
                        app.logger.warning(
                            "Auto-backup: invalid configuration (freq=%r, time=%r, day=%r) — skipping this cycle",
                            freq, time_str, day_val,
                        )
                        continue

                    # Wait for the next scheduled slot, then run.
                    seconds_until = (next_run - now_local).total_seconds()
                    if seconds_until > 60:
                        # Long way off — sleep for the bulk of the gap and
                        # re-check next iteration.  We never sleep for more
                        # than ~15 min so a config change is picked up quickly.
                        time.sleep(min(seconds_until - 60, 900))
                        continue

                    # If we already ran in this exact slot, skip.  Compare
                    # against the local-time floor of the slot so a missed
                    # weekly run that wakes up 6 h late still re-runs.
                    last_run = getattr(setting, 'backup_auto_last_run_at', None)
                    last_run_local = None
                    if last_run is not None:
                        if last_run.tzinfo is None:
                            last_run_local = last_run.replace(tzinfo=ZoneInfo('UTC')).astimezone(tz)
                        else:
                            last_run_local = last_run.astimezone(tz)

                    if last_run_local and last_run_local >= next_run:
                        # Already executed this slot — sleep until the next one.
                        # Fall through to the top of the loop; we'll re-derive
                        # the future run from the new ``now_local``.
                        continue

                    app.logger.info(
                        f"Auto-backup triggered: freq={freq}, time={time_str}, "
                        f"day={day_val}, files={include_files}"
                    )

                    from routes.backup import _build_backup_archive_bytes, _backup_storage_dir
                    archive_bytes = _build_backup_archive_bytes(app, include_files=include_files)
                    backup_dir = _backup_storage_dir()

                    ts = now_utc.strftime('%Y%m%d_%H%M%S')
                    suffix = 'full' if include_files else 'db'
                    filename = f'auto_backup_{suffix}_{ts}.tar.gz'
                    filepath = os.path.join(backup_dir, filename)
                    with open(filepath, 'wb') as fh:
                        fh.write(archive_bytes)

                    setting.backup_auto_last_run_at = now_utc
                    db.session.commit()

                    # Clean up old backups according to retention settings
                    from routes.backup import _cleanup_old_backups
                    keep_count = getattr(setting, 'backup_auto_keep_count', 10) or 10
                    keep_days = getattr(setting, 'backup_auto_keep_days', 0) or 0
                    removed = _cleanup_old_backups(backup_dir, keep_count=keep_count, keep_days=keep_days)
                    if removed:
                        app.logger.info(
                            f"Auto-backup cleanup: removed {removed} old backup(s) "
                            f"(keep_count={keep_count}, keep_days={keep_days})"
                        )

                    app.logger.info(
                        f"Auto-backup completed: {filename} ({len(archive_bytes)} bytes)"
                    )
            except Exception as exc:
                app.logger.error("Background auto-backup failed: %s", exc)

    thread = threading.Thread(target=worker, name='auto-backup-worker', daemon=True)
    thread.start()


def _start_model_thumbnail_worker(app: Flask) -> None:
    """Background thread that auto-renders STL thumbnails for uploaded models.

    Scans for ProjectFile records that are STL files without a thumbnail_path
    set and renders a server-side preview.  Runs every 60 seconds; only
    processes a few records per tick to avoid CPU spikes.
    """
    if app.config.get('TESTING'):
        return
    if app.debug and os.environ.get('WERKZEUG_RUN_MAIN') != 'true':
        return
    if app.extensions.get('model_thumbnail_worker_started'):
        return
    if not _acquire_worker_lock(app, 'model_thumbnail'):
        return

    app.extensions['model_thumbnail_worker_started'] = True

    def worker():
        while True:
            try:
                time.sleep(60)
                with app.app_context():
                    from models import ProjectFile
                    from routes.models import render_stl_thumbnail_for_file
                    import os as _os

                    def _ext(name):
                        return name.rsplit('.', 1)[-1].lower() if '.' in name else ''

                    # Find STL files missing thumbnails.  Limit 3 per tick.
                    pending = (
                        ProjectFile.query
                        .filter(ProjectFile.filename.isnot(None))
                        .order_by(ProjectFile.id.asc())
                        .limit(40)
                        .all()
                    )
                    targets = []
                    for pf in pending:
                        if not (pf.filepath and _os.path.isfile(pf.filepath)):
                            continue
                        ext = _ext(pf.filename or '')
                        if ext != 'stl':
                            continue
                        if pf.thumbnail_path:
                            continue
                        targets.append(pf)
                    targets = targets[:3]
                    if not targets:
                        continue

                    rendered = 0
                    for pf in targets:
                        try:
                            if render_stl_thumbnail_for_file(pf, commit=True):
                                rendered += 1
                        except Exception as exc:
                            app.logger.warning(
                                'Background STL render failed for id=%s: %s',
                                pf.id, exc,
                            )
                    if rendered:
                        app.logger.info(
                            'Model-thumbnail worker: %d rendered', rendered,
                        )
            except Exception as exc:
                app.logger.error('Background model-thumbnail worker failed: %s', exc)

    thread = threading.Thread(target=worker, name='model-thumbnail-worker', daemon=True)
    thread.start()


# WSGI entry point (Gunicorn) and dev server
app = create_app()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
