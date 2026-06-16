import ipaddress
import json
import math
import os
import re
import socket
import threading
import time
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from urllib.parse import urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup
from sqlalchemy.orm import joinedload

from database import db
from models import (
    AppSetting, BambuJobMaterial, BambuPrintJob, BambuPrinter, MovementHistory,
    Project, ProjectTodo, PrusaPrintJob, PrusaPrinter, FilamentUndoLog, ProjectFilament,
    Filament, Material, Color,
)


def _json_default(obj):
    """JSON encoder default for Decimal objects (convert to float)."""
    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError(f'Object of type {obj.__class__.__name__} is not JSON serializable')


# ---------------------------------------------------------------------------
# Short-lived in-process KPI cache (single-worker; invalidated on writes)
# ---------------------------------------------------------------------------
_KPI_CACHE_TTL = 30  # seconds

class _KpiCache:
    """Thread-safe TTL cache for one computed value."""
    def __init__(self, ttl: int = _KPI_CACHE_TTL):
        self._lock = threading.Lock()
        self._data = None
        self._ts: float = 0.0
        self._ttl = ttl

    def get(self):
        with self._lock:
            if self._data is not None and (time.monotonic() - self._ts) < self._ttl:
                return self._data
        return None

    def set(self, data):
        with self._lock:
            self._data = data
            self._ts = time.monotonic()

    def invalidate(self):
        with self._lock:
            self._data = None
            self._ts = 0.0

_action_center_cache: _KpiCache = _KpiCache(ttl=30)

def invalidate_kpi_cache():
    """Call after any inventory mutation to flush cached KPIs."""
    _action_center_cache.invalidate()


from flask import g, has_app_context

def get_settings():
    if has_app_context():
        if 'app_setting' not in g:
            g.app_setting = AppSetting.query.first()
        return g.app_setting
    return AppSetting.query.first()


def get_current_lang():
    setting = get_settings()
    lang = setting.lang if setting else 'cs'
    # Per-user language override — lazy import to avoid circular dependency
    # (auth.py imports utc_now from utils).
    try:
        from auth import get_current_user as _gcu
        user = _gcu()
        if user and user.preferred_language:
            lang = user.preferred_language
    except (ImportError, RuntimeError):
        pass
    return lang


def translate(key):
    """Translate a message key using the current app language.

    This is the Python-side equivalent of the Jinja2 ``t()`` context processor.
    Use it in route handlers, notification builders, and other non-template code.
    """
    from messages import TRANSLATIONS
    lang = get_current_lang()
    return TRANSLATIONS.get(lang, TRANSLATIONS['cs']).get(key, key)


def safe_commit(error_key='error_general', flash_msg=None):
    """Commit the current DB transaction, rolling back and flashing on error.

    Returns True on success, False on failure (caller should redirect/return).
    If flash_msg is given it is flashed as 'error'; otherwise error_key is
    translated and flashed.

    Usage::

        if not safe_commit('project_save_failed'):
            return redirect(...)
    """
    from database import db
    try:
        db.session.commit()
        return True
    except Exception:
        db.session.rollback()
        try:
            from flask import flash, current_app
            msg = flash_msg or translate(error_key)
            flash(msg, 'error')
        except Exception:
            # If flash itself fails (no request context), silently pass
            pass
        import logging
        logging.getLogger('filament').exception('DB commit failed, rolled back')
        return False


from time_utils import utc_now, utc_now_aware, utc_now_naive  # noqa: F811 — re-exported from leaf module to avoid circular imports; utc_now() is now aware (BUG-514)

# ── Markdown renderer (Refactor B: extracted to utils/markdown.py) ──────
# Re-exported for backward compatibility — new code should import directly
# from ``utils.markdown``.
from utils.markdown import (  # noqa: E402,F401  (re-exports)
    _render_markdown_inline,
    _toggle_markdown_checkbox,
    render_markdown,
)

# ── Sort-key sentinel for mixed tz-aware/naive datetimes ───────────────
# Sentinel used for sorting list of objects that share a datetime field that
# may be ``None``.  With the UtcDateTime type decorator (BUG-514), all values
# read from the database are now timezone-aware, so the sentinel must match.
_SORT_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def get_current_currency():
    setting = get_settings()
    return setting.currency if setting and setting.currency else 'CZK'


def get_current_theme():
    setting = get_settings()
    return setting.theme if setting and setting.theme else 'light'


def build_filament_history_name(filament):
    brand_name = filament.brand.name if filament.brand else ""
    mat_name = filament.material.name if filament.material else ""
    return f"{filament.name} | {brand_name} {mat_name}".strip(" | ")


def parse_tags(raw_value):
    if not raw_value:
        return []
    if isinstance(raw_value, list):
        values = raw_value
    else:
        values = re.split(r'[,;\n]+', str(raw_value))
    tags = []
    seen = set()
    for value in values:
        tag = ' '.join(str(value).strip().split())
        if not tag:
            continue
        lowered = tag.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        tags.append(tag)
    return tags


def format_tags(raw_value):
    return ', '.join(parse_tags(raw_value))


def escape_like(value):
    """Escape special LIKE wildcard characters in user input.

    Prevents wildcard injection where ``%`` matches any sequence
    and ``_`` matches any single character.
    """
    return value.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')


def _is_safe_markdown_href(href):
    """Deprecated re-export. Prefer ``utils.markdown._is_safe_markdown_href``."""
    from utils.markdown import _is_safe_markdown_href as _impl
    return _impl(href)


def remove_tag(raw_value, tag_to_remove):
    tag_to_remove = ' '.join(str(tag_to_remove or '').strip().split()).lower()
    if not tag_to_remove:
        return format_tags(raw_value)
    return ', '.join(
        tag for tag in parse_tags(raw_value)
        if tag.lower() != tag_to_remove
    )


def get_filament_tags(filament):
    return parse_tags(getattr(filament, 'tag_text', ''))


def movement_action_label(action_type):
    """Return a human-readable label for a movement-history action type.

    Lookup goes through the i18n dictionary first (rule 25) so labels
    follow the active language.  Falls back to a title-cased version of
    the raw action_type when no translation is registered — the fallback
    is intentionally language-neutral (ASCII-only title-case).
    """
    key = f'movement_action_{action_type}' if action_type else ''
    if key:
        from utils import translate
        label = translate(key)
        if label != key:
            return label
    return (action_type or '').replace('_', ' ').title()


def compute_stock_status(filament, usage_30=0.0, usage_90=0.0):
    min_stock = max(float(getattr(filament, 'min_stock_grams', 0.0) or 0.0), 0.0)
    max_stock = max(float(getattr(filament, 'max_stock_grams', 0.0) or 0.0), 0.0)
    remaining = max(float(getattr(filament, 'weight_remaining', 0.0) or 0.0), 0.0)
    usage_30 = max(float(usage_30 or 0.0), 0.0)
    usage_90 = max(float(usage_90 or 0.0), 0.0)

    target_stock = max(min_stock, usage_30 * 1.15, (usage_90 / 3.0) * 1.10 if usage_90 > 0 else 0.0)
    if max_stock > 0:
        target_stock = min(target_stock, max_stock)
    recommended_grams = max(0.0, target_stock - remaining)
    spool_weight = float(getattr(filament, 'weight_total', 0.0) or 0.0)
    recommended_spools = math.ceil(recommended_grams / spool_weight) if spool_weight > 0 and recommended_grams > 0 else 0
    recommended_order_grams = recommended_spools * spool_weight if recommended_spools > 0 and spool_weight > 0 else 0.0
    spool_price = float(getattr(filament, 'price', 0.0) or 0.0)
    recommended_order_price = recommended_spools * spool_price if recommended_spools > 0 and spool_price > 0 else 0.0

    critical_usage_threshold = usage_30 / 4.0 if usage_30 > 0 else 0.0

    if remaining <= 0 or (min_stock > 0 and remaining < min_stock * 0.5) or (critical_usage_threshold > 0 and remaining <= critical_usage_threshold):
        status = 'critical'
    elif min_stock > 0 and remaining < min_stock:
        status = 'warning'
    elif usage_30 > 0 and remaining < usage_30:
        status = 'warning'
    else:
        status = 'stable'

    return {
        'remaining': round(remaining, 1),
        'min_stock': round(min_stock, 1),
        'max_stock': round(max_stock, 1),
        'usage_30': round(usage_30, 1),
        'usage_90': round(usage_90, 1),
        'target_stock': round(target_stock, 1),
        'recommended_grams': round(recommended_grams, 1),
        'recommended_spools': recommended_spools,
        'recommended_order_grams': round(recommended_order_grams, 1),
        'recommended_order_price': round(recommended_order_price, 2),
        'spool_price': round(spool_price, 2),
        'status': status,
    }


def _check_fernet_configured() -> bool:
    """Check if FERNET_KEY is configured. Returns True if configured."""
    raw_key = os.environ.get('FERNET_KEY', '').strip()
    if not raw_key:
        return False
    try:
        from cryptography.fernet import Fernet
        Fernet(raw_key.encode())
        return True
    except Exception:
        return False


def _is_testing():
    """Check if running in Flask test mode."""
    try:
        from flask import current_app
        return current_app.config.get('TESTING', False)
    except (RuntimeError, ImportError):
        return False


def encrypt_token(plaintext: str) -> str:
    """Encrypt a sensitive token using FERNET_KEY env var.

    Raises RuntimeError if FERNET_KEY is not configured (except for
    empty/placeholder values like 'NEEDS_CONFIGURATION' and during
    testing where plaintext is accepted for backward compatibility).

    Use _check_fernet_configured() to test at startup.
    """
    if not plaintext:
        return plaintext
    # Allow known placeholders through without encryption
    if plaintext in ('NEEDS_CONFIGURATION',):
        return plaintext
    raw_key = os.environ.get('FERNET_KEY', '').strip().encode()
    if not raw_key:
        if _is_testing():
            return plaintext  # accept plaintext during testing
        raise RuntimeError(
            'FERNET_KEY environment variable is not set — cannot encrypt '
            'sensitive tokens. Set FERNET_KEY to a valid Fernet key to '
            'enable encryption at rest.'
        )
    try:
        from cryptography.fernet import Fernet
        return Fernet(raw_key).encrypt(plaintext.encode()).decode()
    except Exception as exc:
        raise RuntimeError(
            f'Fernet encryption failed (invalid FERNET_KEY?): {exc}'
        ) from exc


def decrypt_token(ciphertext: str) -> str:
    """Decrypt a token encrypted with encrypt_token().

    When FERNET_KEY is not set, or when decryption fails (e.g. legacy
    plaintext token), the value is returned as-is so existing deployments
    are not broken.
    """
    if not ciphertext:
        return ciphertext
    # Allow known placeholders through without decryption
    if ciphertext in ('NEEDS_CONFIGURATION',):
        return ciphertext
    raw_key = os.environ.get('FERNET_KEY', '').strip().encode()
    if not raw_key:
        return ciphertext  # no key configured — return as-is (legacy plaintext)
    try:
        from cryptography.fernet import Fernet
        return Fernet(raw_key).decrypt(ciphertext.encode()).decode()
    except Exception:
        return ciphertext  # legacy plaintext or wrong key — return as-is


def collect_usage_windows(filaments, now=None):
    if now is None:
        now = utc_now()
    by_id = {fil.id: {'usage_30': 0.0, 'usage_90': 0.0} for fil in filaments}
    by_name = {build_filament_history_name(fil): fil.id for fil in filaments}
    since_90 = now - timedelta(days=90)
    since_30 = now - timedelta(days=30)

    # 1. Aggregate by filament_id directly
    results_id = db.session.query(
        MovementHistory.filament_id,
        db.func.sum(db.case((MovementHistory.created_at >= since_30, MovementHistory.weight), else_=0.0)),
        db.func.sum(MovementHistory.weight)
    ).filter(
        MovementHistory.created_at >= since_90,
        MovementHistory.action_type.in_(('remove', 'bambu_print')),
        MovementHistory.filament_id.is_not(None)
    ).group_by(MovementHistory.filament_id).all()

    for fid, u30, u90 in results_id:
        if fid in by_id:
            by_id[fid]['usage_30'] += u30 or 0.0
            by_id[fid]['usage_90'] += u90 or 0.0

    # 2. Aggregate by filament_name for historical/unlinked entries
    results_name = db.session.query(
        MovementHistory.filament_name,
        db.func.sum(db.case((MovementHistory.created_at >= since_30, MovementHistory.weight), else_=0.0)),
        db.func.sum(MovementHistory.weight)
    ).filter(
        MovementHistory.created_at >= since_90,
        MovementHistory.action_type.in_(('remove', 'bambu_print')),
        MovementHistory.filament_id.is_(None)
    ).group_by(MovementHistory.filament_name).all()

    for name, u30, u90 in results_name:
        fid = by_name.get(name)
        if fid in by_id:
            by_id[fid]['usage_30'] += u30 or 0.0
            by_id[fid]['usage_90'] += u90 or 0.0

    return by_id


def collect_activity_heatmap(now=None):
    """Return a list of 364 day-buckets (52 weeks × 7) for the activity heatmap.

    Each entry is a dict with keys ``date`` (ISO string) and ``count``
    (number of movement events that day).  The list is ordered from the oldest
    day (index 0 = 364 days ago) to today (index 363).
    """
    if now is None:
        now = utc_now()
    today = datetime(now.year, now.month, now.day)
    since = today - timedelta(days=363)

    results = db.session.query(
        db.func.date(MovementHistory.created_at),
        db.func.count(MovementHistory.id)
    ).filter(
        MovementHistory.created_at >= since
    ).group_by(
        db.func.date(MovementHistory.created_at)
    ).all()

    by_date = {date_str: count for date_str, count in results if date_str}

    result = []
    for i in range(364):
        d = today - timedelta(days=363 - i)
        iso = d.strftime('%Y-%m-%d')
        result.append({'date': iso, 'count': by_date.get(iso, 0)})
    return result


def collect_sparkline_data(filaments, now=None):
    """Return a dict mapping filament_id → list[float] of daily consumption
    for the last 7 days (index 0 = 7 days ago, index 6 = yesterday/today).
    Only removal-type movements are counted.
    """
    if now is None:
        now = utc_now()
    today = datetime(now.year, now.month, now.day)
    since = today - timedelta(days=6)
    since_date = since.date()
    by_id = {fil.id: [0.0] * 7 for fil in filaments}
    by_name = {build_filament_history_name(fil): fil.id for fil in filaments}

    # Aggregate by ID and Date
    results_id = db.session.query(
        MovementHistory.filament_id,
        db.func.date(MovementHistory.created_at),
        db.func.sum(MovementHistory.weight)
    ).filter(
        MovementHistory.created_at >= since,
        MovementHistory.action_type.in_(('remove', 'bambu_print')),
        MovementHistory.filament_id.is_not(None)
    ).group_by(
        MovementHistory.filament_id,
        db.func.date(MovementHistory.created_at)
    ).all()

    for fid, date_str, weight in results_id:
        if fid in by_id and date_str:
            try:
                dt = datetime.strptime(date_str, '%Y-%m-%d').date()
                day_index = (dt - since_date).days
                if 0 <= day_index <= 6:
                    by_id[fid][day_index] += weight or 0.0
            except ValueError:
                pass

    # Aggregate by Name and Date
    results_name = db.session.query(
        MovementHistory.filament_name,
        db.func.date(MovementHistory.created_at),
        db.func.sum(MovementHistory.weight)
    ).filter(
        MovementHistory.created_at >= since,
        MovementHistory.action_type.in_(('remove', 'bambu_print')),
        MovementHistory.filament_id.is_(None)
    ).group_by(
        MovementHistory.filament_name,
        db.func.date(MovementHistory.created_at)
    ).all()

    for name, date_str, weight in results_name:
        fid = by_name.get(name)
        if fid in by_id and date_str:
            try:
                dt = datetime.strptime(date_str, '%Y-%m-%d').date()
                day_index = (dt - since_date).days
                if 0 <= day_index <= 6:
                    by_id[fid][day_index] += weight or 0.0
            except ValueError:
                pass

    return by_id


def generate_sparkline_svg_path(sparkline_data_for_filament):
    """Generate SVG polyline points string for sparkline from 7 data points.
    
    This moves SVG path construction from Jinja2 templates to Python (Rule 3.5).
    Input: list of 7 floats [day0, day1, ..., day6]
    Output: tuple of (polyline_points, fill_points) for SVG
    """
    if not sparkline_data_for_filament or len(sparkline_data_for_filament) != 7:
        return '', ''
    
    sl_max = max(sparkline_data_for_filament) if sparkline_data_for_filament else 0
    sl_max_safe = sl_max if sl_max > 0 else 1
    
    points = []
    for i in range(7):
        x = round(i * 70 / 6, 2)
        y = round(20 - sparkline_data_for_filament[i] / sl_max_safe * 18, 2)
        points.append(f'{x},{y}')
    
    polyline_points = ' '.join(points)
    fill_points = f'0,20 {polyline_points} 70,20'
    
    return polyline_points, fill_points


def parse_sync_status(raw_value):
    if not raw_value:
        return {
            'ok': None,
            'error': None,
            'added': 0,
            'updated': 0,
            'skipped': 0,
            'label': None,
        }

    raw_text = str(raw_value).strip()
    if raw_text.lower().startswith('error:'):
        return {
            'ok': False,
            'error': raw_text[6:].strip(),
            'added': 0,
            'updated': 0,
            'skipped': 0,
            'label': raw_text,
        }

    try:
        payload = json.loads(raw_text)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {
            'ok': None,
            'error': None,
            'added': 0,
            'updated': 0,
            'skipped': 0,
            'label': raw_text,
        }

    return {
        'ok': True,
        'error': None,
        'added': int(payload.get('added', 0) or 0),
        'updated': int(payload.get('updated', 0) or 0),
        'skipped': int(payload.get('skipped', 0) or 0),
        'label': raw_text,
    }


def build_project_metrics(project, setting=None, bambu_powers=None, prusa_powers=None):
    setting = setting or get_settings()
    kwh_price = float(setting.kwh_price) if setting else 5.0
    printer_power = setting.printer_power if setting else 150

    if bambu_powers is None:
        bambu_powers = {p.device_id: p.power_draw_watts for p in BambuPrinter.query.all() if p.device_id}
    if prusa_powers is None:
        prusa_powers = {p.id: p.power_draw_watts for p in PrusaPrinter.query.all()}

    estimated_material_cost = 0.0
    estimated_weight = 0.0
    planned_items = 0
    completed_plans = 0
    for item in getattr(project, 'filaments', []) or []:
        planned_items += 1
        estimated_weight += float(item.estimated_weight or 0.0)
        if item.is_used:
            completed_plans += 1
        if item.filament and item.filament.weight_total > 0:
            estimated_material_cost += (float(item.filament.price) / item.filament.weight_total) * (item.estimated_weight or 0.0)

    actual_material_cost = 0.0
    actual_weight = 0.0
    actual_seconds = 0
    energy_cost = 0.0

    for job in getattr(project, 'bambu_jobs', []) or []:
        job_seconds = int(job.cost_time or 0)
        actual_seconds += job_seconds

        job_power = printer_power
        if job.device_id and job.device_id in bambu_powers and bambu_powers[job.device_id] is not None:
            job_power = bambu_powers[job.device_id]
        energy_cost += (job_seconds / 3600.0) * (job_power / 1000.0) * kwh_price

        if job.materials:
            slot_total = 0.0
            for slot in job.materials:
                if slot.weight_grams:
                    actual_weight += float(slot.weight_grams or 0.0)
                if slot.filament and slot.filament.weight_total > 0 and slot.weight_grams:
                    slot_total += (float(slot.filament.price) / slot.filament.weight_total) * slot.weight_grams
            if slot_total > 0:
                actual_material_cost += slot_total
            elif job.filament and job.filament.weight_total > 0 and job.weight_grams:
                actual_material_cost += (float(job.filament.price) / job.filament.weight_total) * job.weight_grams
        elif job.filament and job.filament.weight_total > 0 and job.weight_grams:
            actual_weight += float(job.weight_grams or 0.0)
            actual_material_cost += (float(job.filament.price) / job.filament.weight_total) * job.weight_grams
        elif job.weight_grams:
            actual_weight += float(job.weight_grams or 0.0)

    for job in getattr(project, 'prusa_jobs', []) or []:
        job_seconds = int(job.cost_time or 0)
        actual_seconds += job_seconds

        job_power = printer_power
        if job.printer_id and job.printer_id in prusa_powers and prusa_powers[job.printer_id] is not None:
            job_power = prusa_powers[job.printer_id]
        energy_cost += (job_seconds / 3600.0) * (job_power / 1000.0) * kwh_price

        if job.weight_grams:
            actual_weight += float(job.weight_grams or 0.0)
        if job.filament and job.filament.weight_total > 0 and job.weight_grams:
            actual_material_cost += (float(job.filament.price) / job.filament.weight_total) * job.weight_grams

    actual_total_cost = actual_material_cost + energy_cost
    latest_quote = None
    if getattr(project, 'quotes', None):
        latest_quote = max(project.quotes, key=lambda item: item.created_at or _SORT_EPOCH)

    quote_price = float(latest_quote.final_price or 0.0) if latest_quote else 0.0
    profit = quote_price - actual_total_cost if latest_quote else None
    estimated_seconds = int((project.estimated_print_time or 0) * 60)

    return {
        'estimated_material_cost': round(estimated_material_cost, 2),
        'estimated_weight': round(estimated_weight, 1),
        'estimated_seconds': estimated_seconds,
        'actual_material_cost': round(actual_material_cost, 2),
        'actual_weight': round(actual_weight, 1),
        'actual_seconds': actual_seconds,
        'energy_cost': round(energy_cost, 2),
        'actual_total_cost': round(actual_total_cost, 2),
        'quote_price': round(quote_price, 2) if latest_quote else None,
        'profit': round(profit, 2) if profit is not None else None,
        'planned_items': planned_items,
        'completed_plans': completed_plans,
        'completion_ratio': round((completed_plans / planned_items) * 100) if planned_items else 0,
        'has_quote': latest_quote is not None,
    }


def build_action_center(now=None):
    # Use cached result when called without explicit `now` (i.e. from normal HTTP requests).
    # The cache has a 30-second TTL to keep KPIs fresh without hammering SQLite.
    _use_cache = now is None
    if _use_cache:
        cached = _action_center_cache.get()
        if cached is not None:
            return cached

    now = now or utc_now()
    setting = get_settings()

    low_stock_rows = []

    all_filaments = Filament.query.all()
    usage_windows = collect_usage_windows(all_filaments, now=now)
    for filament in all_filaments:
        stock = compute_stock_status(
            filament,
            usage_windows.get(filament.id, {}).get('usage_30', 0.0),
            usage_windows.get(filament.id, {}).get('usage_90', 0.0),
        )
        if stock['status'] in ('critical', 'warning') and not filament.reorder_alert_snoozed:
            low_stock_rows.append({
                'filament': filament,
                'status': stock['status'],
                'recommended_spools': stock['recommended_spools'],
                'recommended_grams': stock['recommended_grams'],
                'recommended_order_grams': stock['recommended_order_grams'],
            })
    low_stock_rows.sort(key=lambda item: (0 if item['status'] == 'critical' else 1, -item['recommended_grams']))

    overdue_projects = (
        Project.query
        .filter(Project.status != 'DONE', Project.due_date.is_not(None), Project.due_date < now)
        .order_by(Project.due_date.asc())
        .limit(6)
        .all()
    )

    today = now.date()
    overdue_todos = (
        ProjectTodo.query
        .join(Project)
        .filter(
            ProjectTodo.is_done == False,
            ProjectTodo.due_date.is_not(None),
            ProjectTodo.due_date < today,
            Project.status != 'DONE',
        )
        .order_by(ProjectTodo.due_date.asc())
        .limit(6)
        .all()
    )
    upcoming_limit = today + timedelta(days=3)
    upcoming_todos = (
        ProjectTodo.query
        .join(Project)
        .filter(
            ProjectTodo.is_done == False,
            ProjectTodo.due_date.is_not(None),
            ProjectTodo.due_date >= today,
            ProjectTodo.due_date <= upcoming_limit,
            Project.status != 'DONE',
        )
        .order_by(ProjectTodo.due_date.asc())
        .limit(6)
        .all()
    )

    unmapped_bambu = (
        BambuPrintJob.query
        .filter(
            db.or_(
                BambuPrintJob.filament_id.is_(None),
                BambuPrintJob.materials.any(BambuJobMaterial.filament_id.is_(None)),
            )
        )
        .order_by(BambuPrintJob.started_at.desc().nullslast(), BambuPrintJob.synced_at.desc())
        .limit(6)
        .all()
    )
    unmapped_prusa = (
        PrusaPrintJob.query
        .filter(
            db.or_(PrusaPrintJob.project_id.is_(None), PrusaPrintJob.filament_id.is_(None)),
            PrusaPrintJob.status.in_(('PRINTING', 'FINISHED')),
        )
        .order_by(PrusaPrintJob.synced_at.desc())
        .limit(6)
        .all()
    )

    printer_issues = []
    bambu_status = parse_sync_status(setting.bambu_last_sync_status if setting else None)
    if setting and setting.bambu_token:
        stale_minutes = max(int(setting.bambu_auto_sync_interval_minutes or 60) * 2, 15)
        is_stale = not setting.bambu_last_sync_at or setting.bambu_last_sync_at < now - timedelta(minutes=stale_minutes)
        if bambu_status['ok'] is False or is_stale:
            printer_issues.append({
                'type': 'bambu',
                'name': 'Bambu Cloud',
                'last_sync_at': setting.bambu_last_sync_at,
                'last_success_at': setting.bambu_last_sync_at if bambu_status['ok'] else None,
                'status': bambu_status,
                'is_stale': is_stale,
            })

    for printer in PrusaPrinter.query.filter_by(enabled=True).order_by(PrusaPrinter.name.asc()).all():
        status = parse_sync_status(printer.last_sync_status)
        is_stale = not printer.last_sync_at or printer.last_sync_at < now - timedelta(minutes=15)
        if status['ok'] is False or is_stale:
            printer_issues.append({
                'type': 'prusa',
                'name': printer.name,
                'printer': printer,
                'last_sync_at': printer.last_sync_at,
                'last_success_at': printer.last_success_at,
                'status': status,
                'is_stale': is_stale,
            })

    # Recent completed print jobs (Bambu + Prusa) for the overview activity feed
    recent_bambu = (
        BambuPrintJob.query
        .filter(BambuPrintJob.status == 'FINISH')
        .order_by(BambuPrintJob.finished_at.desc().nullslast(), BambuPrintJob.synced_at.desc())
        .limit(8)
        .all()
    )
    recent_prusa = (
        PrusaPrintJob.query
        .filter(PrusaPrintJob.status == 'FINISHED')
        .order_by(PrusaPrintJob.finished_at.desc().nullslast(), PrusaPrintJob.synced_at.desc())
        .limit(8)
        .all()
    )
    # Merge and sort by timestamp, keep latest 6
    recent_prints = []
    for job in recent_bambu:
        recent_prints.append({
            'source': 'bambu',
            'title': job.model_name or job.external_id or f'Job #{job.id}',
            'printer_name': job.printer_name,
            'timestamp': job.finished_at or job.started_at or job.synced_at,
            'weight_grams': job.weight_grams,
            'detail_url': '/bambu',
        })
    for job in recent_prusa:
        recent_prints.append({
            'source': 'prusa',
            'title': job.display_name or job.file_name or f'Job #{job.id}',
            'printer_name': job.printer.name if getattr(job, 'printer', None) else job.printer_name,
            'timestamp': job.finished_at or job.started_at or job.synced_at,
            'weight_grams': job.weight_grams,
            'detail_url': '/prusa',
        })
    # Use a tz-aware epoch sentinel (UtcDateTime normalises all DB reads to aware).
    # Python 3.12+ "can't compare aware and naive" TypeError.  Job timestamps
    # may be aware (newer records) or naive (legacy rows).
    recent_prints.sort(key=lambda x: x['timestamp'] or _SORT_EPOCH, reverse=True)
    recent_prints = recent_prints[:6]

    result = {
        'low_stock': low_stock_rows[:6],
        'overdue_projects': overdue_projects,
        'overdue_todos': overdue_todos,
        'upcoming_todos': upcoming_todos,
        'unmapped_bambu': unmapped_bambu,
        'unmapped_prusa': unmapped_prusa,
        'printer_issues': printer_issues[:6],
        'recent_prints': recent_prints,
        'counts': {
            'low_stock': len(low_stock_rows),
            'overdue_projects': len(overdue_projects),
            'overdue_todos': len(overdue_todos),
            'upcoming_todos': len(upcoming_todos),
            'unmapped_jobs': len(unmapped_bambu) + len(unmapped_prusa),
            'printer_issues': len(printer_issues),
        },
        # Per-job auto-mapping suggestions (populated when settings allow)
        'bambu_suggestions': {},
    }

    # Compute mapping suggestions for unmapped Bambu jobs (shown in Action Center)
    setting_for_suggestions = setting or AppSetting.query.first()
    for job in unmapped_bambu:
        suggestions = compute_bambu_job_suggestions(job)
        if any(s['candidates'] for s in suggestions):
            result['bambu_suggestions'][job.id] = suggestions

    if _use_cache:
        _action_center_cache.set(result)
    return result


def normalize_hex(value: str | None) -> str | None:
    """Normalize a color hex value to uppercase #RRGGBB, or None if invalid."""
    if not value:
        return None
    s = str(value).strip().lstrip('#')
    # Strip alpha channel (RRGGBBAA → RRGGBB)
    if len(s) == 8:
        s = s[:6]
    if len(s) != 6:
        return None
    if not re.fullmatch(r'[0-9a-fA-F]{6}', s):
        return None
    return f'#{s.upper()}'


def format_duration(seconds) -> str:
    """Format seconds as 'Xh Ym' or 'Ym' string."""
    if not seconds:
        return ''
    total = int(seconds)
    h, m = divmod(total, 3600)
    m = m // 60
    if h:
        return f'{h}h {m}min'
    return f'{m}min'


def try_auto_map_filament(material_name: str | None, color_hex: str | None):
    """Try to find a filament match for the given material type and color.

    Returns a tuple ``(best_match, candidates)`` where:
    - ``best_match`` is a single :class:`Filament` when there is exactly one
      candidate matching both material **and** color, or the single result of a
      material-only search.  ``None`` when there are zero or multiple matches.
    - ``candidates`` is the full list of :class:`Filament` objects that matched
      (may be empty, one, or many).

    Only in-stock filaments (quantity > 0 or weight_remaining > 0) are
    considered so depleted reels don't pollute the results.
    """
    if not material_name and not color_hex:
        return None, []

    norm_hex = normalize_hex(color_hex)

    base_q = (
        Filament.query
        .join(Filament.material)
        .join(Filament.color)
        .filter(db.or_(Filament.quantity > 0, Filament.weight_remaining > 0))
    )

    if material_name:
        norm_mat = material_name.strip().upper()
        base_q = base_q.filter(db.func.upper(Material.name) == norm_mat)

    # ── Strict match: material + color ───────────────────────────────────────
    if norm_hex:
        strict_results = base_q.filter(
            db.func.upper(Color.hex_value) == norm_hex
        ).all()
        if len(strict_results) == 1:
            return strict_results[0], strict_results
        if len(strict_results) > 1:
            return None, strict_results

    # ── Fallback: material-only match ─────────────────────────────────────────
    if material_name:
        fallback_results = base_q.all()
        if len(fallback_results) == 1:
            return fallback_results[0], fallback_results
        if len(fallback_results) > 1:
            return None, fallback_results

    return None, []


def compute_bambu_job_suggestions(job) -> list:
    """Return auto-mapping suggestions for an unmapped BambuPrintJob.

    Each entry in the returned list describes one material slot::

        {
            'slot_id': int | None,   # BambuJobMaterial.id (None for single-slot jobs)
            'material_name': str | None,
            'color_hex': str | None,
            'best': Filament | None,  # only set when 1 candidate
            'candidates': [Filament, ...],
        }
    """
    suggestions = []
    materials = list(job.materials)
    is_mm = len(materials) > 1

    if is_mm:
        for mat in materials:
            if mat.filament_id is not None:
                continue  # already mapped
            best, candidates = try_auto_map_filament(mat.material_name, mat.color_hex)
            suggestions.append({
                'slot_id': mat.id,
                'material_name': mat.material_name,
                'color_hex': normalize_hex(mat.color_hex),
                'best': best,
                'candidates': candidates,
            })
    else:
        if job.filament_id is not None:
            return []
        color_hex = None
        material_name = None
        if materials:
            color_hex = materials[0].color_hex
            material_name = materials[0].material_name
        best, candidates = try_auto_map_filament(material_name, color_hex)
        suggestions.append({
            'slot_id': materials[0].id if materials else None,
            'material_name': material_name,
            'color_hex': normalize_hex(color_hex),
            'best': best,
            'candidates': candidates,
        })
    return suggestions


def top_tags(items, attr_name='tag_text', limit=10):
    counter = Counter()
    for item in items:
        counter.update(parse_tags(getattr(item, attr_name, '')))
    return counter.most_common(limit)


def log_movement(filament, action_type, weight, project_id=None, bambu_job_id=None, note=None):
    """Record a filament weight movement with cost calculation.

    .. warning::

        This function **only** adds a ``MovementHistory`` row to the
        current SQLAlchemy session.  It does **not** call
        ``safe_commit()``.  The **caller is responsible** for
        committing the transaction; otherwise the movement record is
        silently lost when the session closes without a commit.

        Example::

            log_movement(filament, 'use', 12.5, note='Benchy')
            safe_commit()
    """
    if weight <= 0:
        return
    cost_per_gram = float(filament.price) / filament.weight_total if filament.weight_total > 0 else 0
    total_cost = cost_per_gram * weight
    currency = get_current_currency()

    filament_name = build_filament_history_name(filament)

    movement = MovementHistory(
        filament_id=filament.id if getattr(filament, 'id', None) else None,
        project_id=project_id,
        bambu_job_id=bambu_job_id,
        filament_name=filament_name,
        action_type=action_type,
        weight=weight,
        cost=total_cost,
        currency=currency,
        note=note,
    )
    db.session.add(movement)


def deduct_filament_stock(filament, requested_weight):
    """Deduct stock safely and keep weight/quantity consistent.

    Returns the actually deducted weight after clamping to zero.
    """
    if not filament or requested_weight <= 0:
        return 0.0

    old_weight = filament.weight_remaining
    filament.weight_remaining = max(0.0, filament.weight_remaining - requested_weight)
    actual_amount = old_weight - filament.weight_remaining

    if filament.weight_total > 0:
        expected_quantity = math.ceil(filament.weight_remaining / filament.weight_total)
        if expected_quantity < filament.quantity:
            filament.quantity = expected_quantity

    return actual_amount


# ---------------------------------------------------------------------------
# Database-backed Undo System
# ---------------------------------------------------------------------------
_UNDO_TTL_MINUTES = 15  # Undo tokens expire after 15 minutes


def create_undo_snapshot(user_id, action_type, filament, project_filaments=None, project_quote_ids=None, restore_quantity=None, restore_weight=None):
    """Create a database-backed undo snapshot for a filament operation.

    Args:
        user_id: ID of the user performing the action
        action_type: One of 'delete_filament', 'bulk_delete', 'remove_spool'
        filament: Filament object to snapshot
        project_filaments: List of ProjectFilament objects for relation restoration
        project_quote_ids: List of ProjectQuote IDs for relation restoration
        restore_quantity: For remove_spool, quantity to restore (default: 1)
        restore_weight: For remove_spool, weight to restore

    Returns:
        FilamentUndoLog object
    """

    snapshot_data = {
        'filament': {
            'id': filament.id,
            'name': filament.name,
            'brand_id': filament.brand_id,
            'color_id': filament.color_id,
            'material_id': filament.material_id,
            'weight_total': filament.weight_total,
            'weight_remaining': filament.weight_remaining,
            'price': filament.price,
            'quantity': filament.quantity,
            'min_stock_grams': filament.min_stock_grams,
            'max_stock_grams': filament.max_stock_grams,
            'tag_text': filament.tag_text,
            'quality_stringing': filament.quality_stringing,
            'quality_adhesion': filament.quality_adhesion,
            'quality_drying': filament.quality_drying,
            'quality_profile': filament.quality_profile,
            'quality_notes': filament.quality_notes,
            'recommended_nozzle_temp': filament.recommended_nozzle_temp,
            'recommended_bed_temp': filament.recommended_bed_temp,
            'reorder_alert_snoozed': filament.reorder_alert_snoozed,
            'shop_url': filament.shop_url,
        },
        'project_filaments': [
            {
                'project_id': pf.project_id,
                'estimated_weight': pf.estimated_weight,
                'is_used': pf.is_used,
            }
            for pf in (project_filaments or [])
        ],
        'project_quote_ids': list(project_quote_ids or []),
        'restore_quantity': restore_quantity,
        'restore_weight': restore_weight,
    }

    undo_log = FilamentUndoLog(
        user_id=user_id,
        action_type=action_type,
        filament_id=filament.id,
        snapshot_data=json.dumps(snapshot_data, default=_json_default),
        expires_at=utc_now() + timedelta(minutes=_UNDO_TTL_MINUTES),
        is_consumed=False,
    )
    db.session.add(undo_log)
    safe_commit()
    return undo_log


def create_bulk_undo_snapshot(user_id, entries):
    """Create a database-backed undo snapshot for bulk delete operation.

    Args:
        user_id: ID of the user performing the action
        entries: List of dicts with 'filament', 'project_filaments', 'project_quote_ids'

    Returns:
        FilamentUndoLog object
    """

    snapshot_data = {
        'type': 'bulk_delete',
        'entries': []
    }

    for entry in entries:
        filament = entry['filament']
        snapshot_data['entries'].append({
            'filament': {
                'id': filament.id,
                'name': filament.name,
                'brand_id': filament.brand_id,
                'color_id': filament.color_id,
                'material_id': filament.material_id,
                'weight_total': filament.weight_total,
                'weight_remaining': filament.weight_remaining,
                'price': filament.price,
                'quantity': filament.quantity,
                'min_stock_grams': filament.min_stock_grams,
                'max_stock_grams': filament.max_stock_grams,
                'tag_text': filament.tag_text,
                'quality_stringing': filament.quality_stringing,
                'quality_adhesion': filament.quality_adhesion,
                'quality_drying': filament.quality_drying,
                'quality_profile': filament.quality_profile,
                'quality_notes': filament.quality_notes,
                'recommended_nozzle_temp': filament.recommended_nozzle_temp,
                'recommended_bed_temp': filament.recommended_bed_temp,
                'reorder_alert_snoozed': filament.reorder_alert_snoozed,
                'shop_url': filament.shop_url,
            },
            'project_filaments': [
                {
                    'project_id': pf.project_id,
                    'estimated_weight': pf.estimated_weight,
                    'is_used': pf.is_used,
                }
                for pf in entry.get('project_filaments', [])
            ],
            'project_quote_ids': list(entry.get('project_quote_ids', [])),
        })

    undo_log = FilamentUndoLog(
        user_id=user_id,
        action_type='bulk_delete',
        filament_id=None,  # Multiple filaments
        snapshot_data=json.dumps(snapshot_data, default=_json_default),
        expires_at=utc_now() + timedelta(minutes=_UNDO_TTL_MINUTES),
        is_consumed=False,
    )
    db.session.add(undo_log)
    safe_commit()
    return undo_log


def get_pending_undo(user_id):
    """Get pending undo log for a user (not expired, not consumed).

    Args:
        user_id: ID of the user

    Returns:
        FilamentUndoLog object or None
    """

    undo_log = FilamentUndoLog.query.filter(
        FilamentUndoLog.user_id == user_id,
        FilamentUndoLog.is_consumed == False,
        FilamentUndoLog.expires_at > utc_now(),
    ).order_by(FilamentUndoLog.created_at.desc()).first()

    return undo_log


def consume_undo_log(undo_log_id, user_id):
    """Consume an undo log entry (mark as consumed and return snapshot data).

    Args:
        undo_log_id: ID of the undo log entry
        user_id: ID of the user (for ownership validation)

    Returns:
        dict snapshot_data or None if invalid/expired
    """

    undo_log = FilamentUndoLog.query.filter_by(id=undo_log_id, user_id=user_id).first()
    if not undo_log:
        return None

    if undo_log.is_consumed:
        return None

    if undo_log.expires_at < utc_now():
        return None

    undo_log.is_consumed = True
    undo_log.consumed_at = utc_now()
    safe_commit()

    return json.loads(undo_log.snapshot_data)


def purge_expired_undo_logs():
    """Delete expired undo log entries (cleanup)."""

    expired = FilamentUndoLog.query.filter(
        FilamentUndoLog.expires_at < utc_now()
    ).delete()
    safe_commit()
    return expired


def restore_filament_from_snapshot(snapshot_data):
    """Restore a filament from snapshot data.

    Args:
        snapshot_data: dict with 'filament', 'project_filaments', 'project_quote_ids'

    Returns:
        Restored Filament object
    """
    filament_data = snapshot_data['filament']

    # Check if filament still exists (might have been recreated)
    filament = db.session.get(Filament, filament_data['id'])

    if filament:
        # Update existing filament
        filament.name = filament_data['name']
        filament.brand_id = filament_data['brand_id']
        filament.color_id = filament_data['color_id']
        filament.material_id = filament_data['material_id']
        filament.weight_total = filament_data['weight_total']
        filament.weight_remaining = filament_data['weight_remaining']
        filament.price = filament_data['price']
        filament.quantity = filament_data['quantity']
        filament.min_stock_grams = filament_data['min_stock_grams']
        filament.max_stock_grams = filament_data['max_stock_grams']
        filament.tag_text = filament_data['tag_text']
        filament.quality_stringing = filament_data['quality_stringing']
        filament.quality_adhesion = filament_data['quality_adhesion']
        filament.quality_drying = filament_data['quality_drying']
        filament.quality_profile = filament_data['quality_profile']
        filament.quality_notes = filament_data['quality_notes']
        filament.recommended_nozzle_temp = filament_data['recommended_nozzle_temp']
        filament.recommended_bed_temp = filament_data['recommended_bed_temp']
        filament.reorder_alert_snoozed = filament_data['reorder_alert_snoozed']
        filament.shop_url = filament_data['shop_url']
    else:
        # Recreate deleted filament
        filament = Filament(**filament_data)
        db.session.add(filament)
        db.session.flush()  # Get the new ID

    # Restore project filament relations
    for pf_data in snapshot_data.get('project_filaments', []):
        existing = ProjectFilament.query.filter_by(
            project_id=pf_data['project_id'],
            filament_id=filament.id
        ).first()
        if not existing:
            project_filament = ProjectFilament(
                project_id=pf_data['project_id'],
                filament_id=filament.id,
                estimated_weight=pf_data['estimated_weight'],
                is_used=pf_data['is_used'],
            )
            db.session.add(project_filament)

    # Restore ProjectQuote relations
    for qid in snapshot_data.get('project_quote_ids', []):
        ProjectQuote.query.filter_by(id=qid).update({'filament_id': filament.id}, synchronize_session=False)

    return filament


def restore_bulk_from_snapshot(snapshot_data):
    """Restore multiple filaments from bulk delete snapshot.

    Args:
        snapshot_data: dict with 'entries' list

    Returns:
        List of restored Filament objects
    """
    restored = []
    for entry in snapshot_data.get('entries', []):
        filament = restore_filament_from_snapshot(entry)
        restored.append(filament)
    return restored


def _is_public_ip(address):
    ip_obj = ipaddress.ip_address(address)
    return not (
        ip_obj.is_private
        or ip_obj.is_loopback
        or ip_obj.is_link_local
        or ip_obj.is_multicast
        or ip_obj.is_reserved
        or ip_obj.is_unspecified
    )


def is_safe_external_url(url):
    parsed = urlparse(url)
    if parsed.scheme not in {'http', 'https'}:
        return False

    hostname = parsed.hostname
    if not hostname:
        return False

    lowered = hostname.lower()
    if lowered in {'localhost', 'localhost.localdomain'} or lowered.endswith('.localhost'):
        return False

    try:
        ip_obj = ipaddress.ip_address(hostname)
        return _is_public_ip(ip_obj)
    except ValueError:
        pass

    try:
        addrinfos = socket.getaddrinfo(hostname, parsed.port or None, type=socket.SOCK_STREAM)
    except socket.gaierror:
        return False

    resolved = {item[4][0] for item in addrinfos}
    if not resolved:
        return False

    try:
        return all(_is_public_ip(address) for address in resolved)
    except ValueError:
        return False


def _strip_fragment(url):
    parsed = urlparse(url)
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, parsed.query, ''))


def _validate_peer_ip(response):
    """Validate that the actually-connected peer IP is public.

    Guards against DNS rebinding attacks where the DNS A record changes
    between the pre-connect safety check and the actual TCP handshake.
    """
    try:
        # Access the underlying urllib3 socket to get the real peer address
        sock = response.raw._connection.sock
        peer_ip = sock.getpeername()[0]
        if not _is_public_ip(peer_ip):
            raise ValueError('Peer IP {} is not public — possible DNS rebinding'.format(peer_ip))
    except (AttributeError, TypeError, IndexError):
        pass  # Cannot access socket — skip validation


def _follow_safe_redirects(url, headers, timeout, max_redirects=5):
    current_url = url

    for _ in range(max_redirects + 1):
        if not is_safe_external_url(current_url):
            raise ValueError('Unsafe redirect target')

        response = requests.get(
            current_url,
            headers=headers,
            timeout=timeout,
            allow_redirects=False,
            stream=False,
        )

        # Defend against DNS rebinding: validate the actual peer IP
        _validate_peer_ip(response)

        if 300 <= response.status_code < 400:
            location = response.headers.get('Location')
            if not location:
                return response, current_url
            current_url = urljoin(current_url, location)
            continue

        return response, current_url

    raise ValueError('Too many redirects')


def _extract_meta_content(soup, key, attr='property'):
    tag = soup.find('meta', attrs={attr: key})
    if tag:
        return tag.get('content')
    return None


def _pick_preview_image(soup, base_url):
    candidates = [
        _extract_meta_content(soup, 'og:image'),
        _extract_meta_content(soup, 'og:image', attr='name'),   # Printables & sites using name= instead of property=
        _extract_meta_content(soup, 'og:image:url'),
        _extract_meta_content(soup, 'og:image:url', attr='name'),
        _extract_meta_content(soup, 'twitter:image', attr='name'),
        _extract_meta_content(soup, 'twitter:image:src', attr='name'),
    ]

    link_tag = soup.find('link', rel=lambda value: value and 'image_src' in value)
    if link_tag:
        candidates.append(link_tag.get('href'))

    itemprop_image = soup.find(attrs={'itemprop': 'image'})
    if itemprop_image:
        candidates.append(itemprop_image.get('content') or itemprop_image.get('src'))

    for image in soup.find_all('img'):
        src = image.get('src')
        if not src:
            continue
        width = image.get('width')
        height = image.get('height')
        if width and height:
            try:
                if int(width) < 120 or int(height) < 120:
                    continue
            except ValueError:
                pass
        candidates.append(src)

    for candidate in candidates:
        if not candidate:
            continue
        absolute = urljoin(base_url, candidate.strip())
        if is_safe_external_url(absolute):
            return absolute
    return None


def _iter_nested_values(payload, keys):
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key in keys:
                yield value
            yield from _iter_nested_values(value, keys)
    elif isinstance(payload, list):
        for item in payload:
            yield from _iter_nested_values(item, keys)


def _normalize_image_candidate(candidate, base_url):
    if isinstance(candidate, str) and candidate.strip():
        absolute = urljoin(base_url, candidate.strip())
        if is_safe_external_url(absolute):
            return absolute
        return None

    if isinstance(candidate, list):
        for item in candidate:
            normalized = _normalize_image_candidate(item, base_url)
            if normalized:
                return normalized
        return None

    if isinstance(candidate, dict):
        for key in ('url', 'contentUrl', 'thumbnailUrl', 'src'):
            if key in candidate:
                normalized = _normalize_image_candidate(candidate[key], base_url)
                if normalized:
                    return normalized
    return None


def _normalize_text_candidate(candidate):
    if isinstance(candidate, str):
        cleaned = ' '.join(candidate.split())
        return cleaned or None
    if isinstance(candidate, list):
        for item in candidate:
            normalized = _normalize_text_candidate(item)
            if normalized:
                return normalized
    if isinstance(candidate, dict):
        for key in ('name', 'headline', 'title', 'description', 'text'):
            if key in candidate:
                normalized = _normalize_text_candidate(candidate[key])
                if normalized:
                    return normalized
    return None


def _extract_script_json_candidates(soup):
    json_payloads = []

    for script in soup.find_all('script', attrs={'type': 'application/ld+json'}):
        content = script.string or script.get_text(strip=True)
        if not content:
            continue
        try:
            json_payloads.append(json.loads(content))
        except json.JSONDecodeError:
            continue

    pattern = re.compile(r'({.*})', re.DOTALL)
    for script in soup.find_all('script'):
        content = script.string or script.get_text()
        if not content or ('image' not in content and 'title' not in content and 'description' not in content):
            continue
        if len(content) > 1_000_000:
            continue

        direct_candidate = content.strip()
        if direct_candidate.startswith('{') and direct_candidate.endswith('}'):
            candidates = [direct_candidate]
        else:
            candidates = [match.group(1) for match in pattern.finditer(content)]

        for candidate in candidates[:5]:
            try:
                json_payloads.append(json.loads(candidate))
            except json.JSONDecodeError:
                continue

    return json_payloads


def _extract_preview_from_json_payloads(payloads, base_url):
    preview = {
        'title': None,
        'description': None,
        'image': None,
    }

    title_keys = {'headline', 'name', 'title'}
    description_keys = {'description', 'summary', 'abstract', 'text'}
    image_keys = {'image', 'images', 'thumbnail', 'thumbnailUrl', 'cover', 'coverImage', 'coverUrl', 'banner'}

    for payload in payloads:
        if not preview['title']:
            preview['title'] = _normalize_text_candidate(next(_iter_nested_values(payload, title_keys), None))
        if not preview['description']:
            preview['description'] = _normalize_text_candidate(next(_iter_nested_values(payload, description_keys), None))
        if not preview['image']:
            preview['image'] = _normalize_image_candidate(next(_iter_nested_values(payload, image_keys), None), base_url)
        if all(preview.values()):
            break

    return preview


def _extract_markdown_preview(markdown, base_url):
    preview = {
        'title': None,
        'description': None,
        'image': None,
    }

    title_match = re.search(r'^Title:\s*(.+)$', markdown, flags=re.MULTILINE)
    if title_match:
        preview['title'] = _normalize_text_candidate(title_match.group(1))

    image_candidates = re.findall(r'!\[[^\]]*\]\((https?://[^)\s]+)\)', markdown)
    preferred_images = []
    fallback_images = []
    for candidate in image_candidates:
        normalized = _normalize_image_candidate(candidate, base_url)
        if not normalized:
            continue
        lowered = normalized.lower()
        if any(marker in lowered for marker in ('avatar/', 'favicon', 'icon for ')):
            continue
        if any(marker in lowered for marker in ('/design/', '/model/', 'makerworld.bblmw.com')):
            preferred_images.append(normalized)
        else:
            fallback_images.append(normalized)
    preview['image'] = (preferred_images or fallback_images or [None])[0]

    description_match = re.search(
        r'#+\s*Description\s*(.+?)(?:\n#+\s|\Z)',
        markdown,
        flags=re.DOTALL | re.IGNORECASE,
    )
    if description_match:
        description_lines = []
        for line in description_match.group(1).splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith('![') or stripped.startswith('['):
                continue
            description_lines.append(stripped)
        if description_lines:
            preview['description'] = _normalize_text_candidate(' '.join(description_lines))

    lines = []
    for line in markdown.splitlines():
        stripped = line.strip()
        if (
            not stripped
            or stripped.startswith('Title:')
            or stripped.startswith('URL Source:')
            or stripped.startswith('Markdown Content:')
            or stripped.startswith('#')
            or stripped.startswith('*')
            or stripped.startswith('![')
            or stripped.startswith('[')
        ):
            continue
        lines.append(stripped)

    if not preview['description'] and lines:
        preview['description'] = _normalize_text_candidate(lines[0])

    return preview


def _fetch_reader_fallback(url, headers, timeout):
    reader_url = f"https://r.jina.ai/http://{re.sub(r'^https?://', '', _strip_fragment(url))}"
    response = requests.get(reader_url, headers=headers, timeout=timeout)
    _validate_peer_ip(response)
    if response.status_code != 200 or 'text/plain' not in response.headers.get('Content-Type', ''):
        return None
    return _extract_markdown_preview(response.text, _strip_fragment(url))


def _is_weak_preview_value(value, kind):
    if not value:
        return True

    lowered = value.lower()
    if kind == 'title':
        return lowered in {'just a moment...', 'makerworld'}
    if kind == 'description':
        return lowered in {'explore', 'home', 'community'} or len(value.strip()) < 12
    if kind == 'image':
        return any(marker in lowered for marker in ('avatar/', 'favicon', '/user/'))
    return False


def fetch_link_metadata(url):
    meta = {
        'og_title': None,
        'og_image': None,
        'og_description': None,
        'domain': None,
    }

    clean_url = _strip_fragment(url)
    if not is_safe_external_url(clean_url):
        return meta

    try:
        parsed_uri = urlparse(clean_url)
        meta['domain'] = parsed_uri.netloc

        headers = {
            'User-Agent': (
                'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 '
                '(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
            ),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Sec-Ch-Ua': '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
            'Sec-Ch-Ua-Mobile': '?0',
            'Sec-Ch-Ua-Platform': '"Linux"',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Upgrade-Insecure-Requests': '1',
        }
        response, final_url = _follow_safe_redirects(clean_url, headers=headers, timeout=5)
        if response.status_code == 200 and 'text/html' in response.headers.get('Content-Type', ''):
            soup = BeautifulSoup(response.text, 'html.parser')

            meta['domain'] = urlparse(final_url).netloc
            meta['og_title'] = (
                _extract_meta_content(soup, 'og:title')
                or _extract_meta_content(soup, 'twitter:title', attr='name')
            )
            if not meta['og_title']:
                title_tag = soup.find('title')
                meta['og_title'] = title_tag.get_text(strip=True) if title_tag else None

            meta['og_description'] = (
                _extract_meta_content(soup, 'og:description')
                or _extract_meta_content(soup, 'twitter:description', attr='name')
                or _extract_meta_content(soup, 'description', attr='name')
            )
            meta['og_image'] = _pick_preview_image(soup, final_url)

            if not (meta['og_title'] and meta['og_description'] and meta['og_image']):
                json_preview = _extract_preview_from_json_payloads(
                    _extract_script_json_candidates(soup),
                    final_url,
                )
                meta['og_title'] = meta['og_title'] or json_preview['title']
                meta['og_description'] = meta['og_description'] or json_preview['description']
                meta['og_image'] = meta['og_image'] or json_preview['image']

        if not (meta['og_title'] and meta['og_image']):
            markdown_preview = _fetch_reader_fallback(clean_url, headers=headers, timeout=10)
            if markdown_preview:
                if markdown_preview['title'] and _is_weak_preview_value(meta['og_title'], 'title'):
                    meta['og_title'] = markdown_preview['title']
                if markdown_preview['description'] and _is_weak_preview_value(meta['og_description'], 'description'):
                    meta['og_description'] = markdown_preview['description']
                if markdown_preview['image'] and _is_weak_preview_value(meta['og_image'], 'image'):
                    meta['og_image'] = markdown_preview['image']

    except Exception:
        return meta

    if meta['og_title'] and len(meta['og_title']) > 250:
        meta['og_title'] = meta['og_title'][:250] + '...'
    if meta['og_description'] and len(meta['og_description']) > 400:
        meta['og_description'] = meta['og_description'][:400] + '...'
    if meta['og_image'] and len(meta['og_image']) > 490:
        meta['og_image'] = meta['og_image'][:490] + '...'

    return meta


# ─── Printer & Bambu shared helpers ──────────────────────────────────────────
# Functions shared across multiple route modules.  Moved here to eliminate
# deferred cross-route imports (CODE_IMPROVEMENTS.md #8).

_PRUSA_TIMEOUT = 10  # seconds per HTTP request to printer


def prusa_request_headers(api_key):
    """Build PrusaLink API request headers."""
    return {'X-Api-Key': api_key}


def validate_printer_host(host):
    """Normalise and validate a printer host URL.

    Returns the cleaned URL or None if the value is clearly invalid.
    Only http:// and https:// are allowed. Empty string is treated as invalid.
    Localhost/loopback addresses are rejected.
    """
    host = (host or '').strip().rstrip('/')
    if not host:
        return None
    if not re.match(r'^https?://', host, re.IGNORECASE):
        host = 'http://' + host
    parsed = re.sub(r'^https?://', '', host, flags=re.IGNORECASE)
    if not parsed:
        return None
    # Strip port and path for hostname validation
    hostname = parsed.split(':')[0].split('/')[0]
    if not hostname:
        return None
    # Reject localhost / loopback
    if hostname.lower() in ('localhost', '127.0.0.1', '::1', '0.0.0.0'):
        return None
    if hostname.lower().startswith('127.') or hostname == '[::1]':
        return None
    # Validate hostname format (basic: no spaces, at least one dot or is IP)
    if not re.match(r'^[a-zA-Z0-9]([a-zA-Z0-9\-\.]*[a-zA-Z0-9])?$', hostname):
        # Also allow IPv6 addresses in brackets
        if not re.match(r'^\[[0-9a-fA-F:]+\]$', hostname):
            return None
    return host


def prusa_request(printer, path):
    """GET request to a PrusaLink endpoint.  Returns parsed JSON or None on error."""
    api_key = decrypt_token(printer.api_key)
    url = f'{printer.host.rstrip("/")}/{path.lstrip("/")}'
    try:
        resp = requests.get(
            url,
            headers=prusa_request_headers(api_key),
            timeout=_PRUSA_TIMEOUT,
        )
        if resp.status_code == 204:
            return {}  # No content — no current job
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.Timeout:
        pass
    except requests.exceptions.ConnectionError:
        pass
    except Exception:
        pass
    return None


def prusa_test_connection(printer):
    """Test connectivity to a PrusaLink printer.

    Returns dict with 'ok', 'model', 'firmware', 'error'.
    """
    data = prusa_request(printer, '/api/version')
    if data is None:
        return {'ok': False, 'model': None, 'firmware': None, 'error': f'Cannot reach {printer.host}'}
    version_text = data.get('text') or data.get('version', '')
    firmware = data.get('firmware') or data.get('printer') or ''

    # Try to get model from /api/v1/info
    info = prusa_request(printer, '/api/v1/info') or {}
    model = info.get('type') or info.get('name') or None

    return {
        'ok': True,
        'model': model,
        'firmware': firmware,
        'version_text': version_text,
        'error': None,
    }


# ─── Bambu helpers ───────────────────────────────────────────────────────────


def bambu_api_base(region):
    """Return the Bambu Cloud API base URL for the given region."""
    return 'https://api.bambulab.cn' if region == 'china' else 'https://api.bambulab.com'


def clean_bambu_title(title):
    """Clean up slicer-generated plate names into a readable model name.

    Bambu Studio creates titles like 'Model.stl_1 + Model.stl_2' (one entry
    per plate).  Strip the extension and trailing plate index, then deduplicate.
    Also strips bare slicer profile strings like '0.20mm Standard @BBL X1C'.
    """
    if not title:
        return title
    # Slicer profile strings start with a layer-height pattern — skip cleanup
    if re.match(r'^\d+\.\d+\s*mm', title.strip()):
        return title
    parts = [p.strip() for p in title.split('+')]
    cleaned = []
    for part in parts:
        part = re.sub(r'\.(stl|3mf|obj|step|amf)$', '', part, flags=re.IGNORECASE).strip()
        part = re.sub(r'_\d+$', '', part).strip()
        if part and part not in cleaned:
            cleaned.append(part)
    return ' + '.join(cleaned) if cleaned else title


# ─── Dashboard helpers ───────────────────────────────────────────────────────


def get_live_printers():
    """Collect data about currently-active printers for the overview dashboard.

    Returns a list of dicts, each with keys: printer, job, type,
    progress_pct, eta_at.
    """
    live = []
    now_dt = utc_now()
    freshness_cutoff = now_dt - timedelta(minutes=15)

    # Prusa — real-time local-network printers with progress
    enabled_printers = PrusaPrinter.query.filter_by(enabled=True).all()
    printer_ids = [p.id for p in enabled_printers]
    printer_by_id = {p.id: p for p in enabled_printers}
    if printer_ids:
        latest_jobs = (
            PrusaPrintJob.query
            .filter(PrusaPrintJob.printer_id.in_(printer_ids))
            .order_by(PrusaPrintJob.started_at.desc().nullslast())
            .all()
        )
        latest_job_by_printer = {}
        for job in latest_jobs:
            if job.printer_id not in latest_job_by_printer:
                latest_job_by_printer[job.printer_id] = job
        for printer in enabled_printers:
            job = latest_job_by_printer.get(printer.id)
            if (
                job
                and job.status == 'PRINTING'
                and job.progress is not None
                and job.progress > 0
                and printer.last_success_at
                and printer.last_success_at >= freshness_cutoff
                and job.synced_at
                and job.synced_at >= freshness_cutoff
            ):
                prusa_progress_pct = int(job.progress * 100)
                prusa_eta_at = (job.started_at + timedelta(seconds=job.cost_time)) if (job.started_at and job.cost_time) else None
                live.append({'printer': printer, 'job': job, 'type': 'prusa',
                             'progress_pct': prusa_progress_pct, 'eta_at': prusa_eta_at})

    # Bambu Cloud — jobs with RUNNING or PAUSED status
    running_bambu = (
        BambuPrintJob.query
        .options(joinedload(BambuPrintJob.materials))
        .filter(BambuPrintJob.status.in_(['RUNNING', 'PAUSED']))
        .order_by(BambuPrintJob.synced_at.desc())
        .all()
    )
    bambu_printers_by_device = {p.device_id: p for p in BambuPrinter.query.all()} if running_bambu else {}
    for job in running_bambu:
        fake_printer = SimpleNamespace(
            name=job.printer_name or 'Bambu Lab',
            host=job.printer_name or 'Bambu Lab',
            printer_model=job.printer_model or None,
        )
        material_swatches = [
            SimpleNamespace(
                color_hex=m.color_hex or '#888888',
                material_name=m.material_name or '?',
                weight_grams=m.weight_grams,
            )
            for m in sorted((job.materials or []), key=lambda m: (m.ams_id or 0, m.tray_id or 0))
        ]
        fake_job = SimpleNamespace(
            display_name=job.model_name,
            file_name=None,
            id=job.id,
            finished_at=None,
            weight_grams=job.weight_grams,
            cost_time=job.cost_time,
            started_at=job.started_at,
            material_swatches=material_swatches,
        )
        bambu_progress_pct = None
        bambu_eta_at = None
        if job.started_at and job.cost_time and job.cost_time > 0:
            bambu_printer = bambu_printers_by_device.get(job.device_id) if job.device_id else None
            pre_job_secs = (bambu_printer.pre_job_time_minutes or 0) * 60 if bambu_printer else 0
            total_secs = job.cost_time + pre_job_secs
            elapsed = (now_dt - job.started_at).total_seconds()
            bambu_progress_pct = min(99, int(elapsed / total_secs * 100))
            bambu_eta_at = job.started_at + timedelta(seconds=total_secs)
        live.append({'printer': fake_printer, 'job': fake_job, 'type': 'bambu',
                     'progress_pct': bambu_progress_pct, 'eta_at': bambu_eta_at})

    return live
