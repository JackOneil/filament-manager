"""
Bambu Lab Cloud integration — idempotent print-job sync, job list, manual
filament mapping, and stock deduction.

No Flask Blueprints — all routes are registered directly on the app object.
"""
import json
import re
import logging
import os
import mimetypes
from datetime import datetime

import requests
from flask import current_app, render_template, request, redirect, url_for, jsonify, Blueprint, send_file, abort

from database import db
from models import (
    BambuPrinter, BambuPrintJob, BambuJobMaterial,
    Filament, PrintHistory, Project, ProjectFilament,
)
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import joinedload
from utils import deduct_filament_stock, decrypt_token, get_settings, log_movement, utc_now

_LOG = logging.getLogger(__name__)

# ─── Bambu Cloud status mapping ─────────────────────────────────────────────
# Verified against actual Bambu Cloud /v1/user-service/my/tasks responses.
# status=2 is FINISH (completed) in the Cloud task API.
_STATUS_MAP = {
    0: 'INIT',
    1: 'RUNNING',
    2: 'FINISH',      # Bambu Cloud: 2 = successfully finished (start→end delta ≈ costTime)
    3: 'FAILED',
    4: 'PAUSED',
    5: 'PREPARE',
    6: 'SLICING',
    7: 'CANCELLED',
    -7: 'CANCELLED',
}
# String aliases returned by some API versions / firmware variants
_STATUS_STR_ALIASES = {
    'success': 'FINISH',
    'finished': 'FINISH',
    'complete': 'FINISH',
    'completed': 'FINISH',
    'cancel': 'CANCELLED',
    'canceled': 'CANCELLED',
    'pause': 'PAUSED',
    'paused': 'PAUSED',
    'in_progress': 'RUNNING',
    'printing': 'RUNNING',
    'running': 'RUNNING',
    'init': 'INIT',
    'prepare': 'PREPARE',
    'slicing': 'SLICING',
    'failed': 'FAILED',
}
_FINISHED_STATUSES = {'FINISH'}


# ─── Helpers ────────────────────────────────────────────────────────────────

def _api_base(region: str) -> str:
    return 'https://api.bambulab.cn' if region == 'china' else 'https://api.bambulab.com'


def _parse_ts(value):
    """Parse Bambu Cloud timestamp (epoch ms/s int or ISO-8601 string) →
    UTC-naive datetime, or None if unparseable."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        ts = float(value) / 1000 if value > 1_000_000_000_000 else float(value)
        try:
            from datetime import timezone as _tz
            return datetime.fromtimestamp(ts, tz=_tz.utc).replace(tzinfo=None)
        except (OSError, OverflowError, ValueError):
            return None
    s = re.sub(r'Z$|[+-]\d{2}:?\d{2}$', '', str(value).strip())
    for fmt in ('%Y-%m-%dT%H:%M:%S.%f', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%dT%H:%M'):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def _resolve_status(raw) -> str:
    """Normalise a Bambu status field (int or string) to a short label."""
    if isinstance(raw, int):
        return _STATUS_MAP.get(raw, f'STATUS_{raw}')
    if isinstance(raw, str) and raw.lstrip('-').isdigit():
        return _STATUS_MAP.get(int(raw), raw)
    if isinstance(raw, str):
        normalised = raw.strip().lower()
        if normalised in _STATUS_STR_ALIASES:
            return _STATUS_STR_ALIASES[normalised]
        return raw.strip().upper() if raw.strip() else 'UNKNOWN'
    return 'UNKNOWN'


def _format_duration(seconds) -> str:
    """Format seconds as 'Xh Ym' or 'Ym' string."""
    if not seconds:
        return ''
    total = int(seconds)
    h, m = divmod(total, 3600)
    m = m // 60
    if h:
        return f'{h}h {m}min'
    return f'{m}min'


def _thumb_dir() -> str:
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    return os.path.join(base_dir, 'data', 'bambu_thumbs')


def _safe_thumb_id(external_id: str) -> str:
    return re.sub(r'[^a-zA-Z0-9_-]', '_', str(external_id or '').strip())


def _cover_url_from_payload(payload: dict) -> str | None:
    if not isinstance(payload, dict):
        return None
    return payload.get('cover') or payload.get('snapShot') or None


def _find_cached_thumb_path(external_id: str) -> str | None:
    safe_id = _safe_thumb_id(external_id)
    if not safe_id:
        return None
    for ext in ('jpg', 'jpeg', 'png', 'webp', 'gif'):
        path = os.path.join(_thumb_dir(), f'{safe_id}.{ext}')
        if os.path.exists(path):
            return path
    return None


def _cache_cover_image(external_id: str, cover_url: str | None) -> str | None:
    if not external_id or not cover_url:
        return None

    try:
        resp = requests.get(cover_url, timeout=15)
        resp.raise_for_status()
    except Exception:
        return None

    ctype = (resp.headers.get('Content-Type') or '').split(';', 1)[0].strip().lower()
    ext_map = {
        'image/jpeg': 'jpg',
        'image/jpg': 'jpg',
        'image/png': 'png',
        'image/webp': 'webp',
        'image/gif': 'gif',
    }
    ext = ext_map.get(ctype)
    if not ext:
        # S3 and some CDNs serve images as binary/octet-stream — fall back to
        # the file extension in the URL path (strip query string first).
        url_path = cover_url.split('?', 1)[0].lower()
        url_ext = url_path.rsplit('.', 1)[-1] if '.' in url_path else ''
        ext = ext_map.get(f'image/{url_ext}') or (url_ext if url_ext in ('jpg', 'jpeg', 'png', 'webp', 'gif') else None)
    if not ext:
        return None
    if ext == 'jpeg':
        ext = 'jpg'

    content = resp.content or b''
    if not content or len(content) > 8 * 1024 * 1024:
        return None

    os.makedirs(_thumb_dir(), exist_ok=True)
    safe_id = _safe_thumb_id(external_id)
    if not safe_id:
        return None

    for old_ext in ('jpg', 'jpeg', 'png', 'webp', 'gif'):
        old_path = os.path.join(_thumb_dir(), f'{safe_id}.{old_ext}')
        if os.path.exists(old_path):
            try:
                os.remove(old_path)
            except OSError:
                pass

    target = os.path.join(_thumb_dir(), f'{safe_id}.{ext}')
    try:
        with open(target, 'wb') as fh:
            fh.write(content)
    except OSError:
        return None

    return target


def _fetch_fresh_cover_url_from_api(external_id: str, token: str, region: str) -> str | None:
    """Ask Bambu Cloud API for a fresh signed cover URL for a specific task.

    Tries the single-task endpoint first; falls back to scanning the list.
    Returns the cover URL string or None.
    """
    base = _api_base(region)
    # Single-task endpoint (may not exist on all regions — tolerate 404)
    try:
        resp = requests.get(
            f'{base}/v1/user-service/my/tasks/{external_id}',
            headers={'Authorization': f'Bearer {token}'},
            timeout=15,
        )
        if resp.ok:
            cover = _cover_url_from_payload(resp.json())
            if cover:
                return cover
    except Exception:
        pass

    # Fallback: scan the first page of tasks
    try:
        resp = requests.get(
            f'{base}/v1/user-service/my/tasks',
            params={'limit': 100, 'offset': 0},
            headers={'Authorization': f'Bearer {token}'},
            timeout=15,
        )
        if resp.ok:
            hits = resp.json().get('hits') or resp.json().get('tasks') or []
            for task in hits:
                if str(task.get('id', '')).strip() == str(external_id):
                    cover = _cover_url_from_payload(task)
                    if cover:
                        return cover
    except Exception:
        pass

    return None


def _send_inline_thumbnail(path: str):
    mimetype, _ = mimetypes.guess_type(path)
    response = send_file(path, mimetype=mimetype or 'image/jpeg', as_attachment=False)
    # Force browser inline rendering when opening the thumbnail endpoint.
    response.headers['Content-Disposition'] = 'inline'
    return response


def _thumbnail_placeholder_response():
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256" viewBox="0 0 256 256" role="img" aria-label="Thumbnail unavailable">'
        '<rect width="256" height="256" rx="20" fill="#F3F4F6"/>'
        '<rect x="44" y="44" width="168" height="168" rx="16" fill="#FFFFFF" stroke="#D1D5DB" stroke-width="8" stroke-dasharray="14 10"/>'
        '<circle cx="128" cy="112" r="26" fill="#E5E7EB"/>'
        '<path d="M82 176l30-34 24 22 18-18 20 30H82z" fill="#E5E7EB"/>'
        '<path d="M96 76h64" stroke="#D1D5DB" stroke-width="10" stroke-linecap="round"/>'
        '</svg>'
    )
    response = current_app.response_class(svg, mimetype='image/svg+xml')
    response.headers['Content-Disposition'] = 'inline'
    response.headers['Cache-Control'] = 'no-store'
    return response


def _normalize_color_hex(value):
    """Normalize color hex values from Cloud payloads to #RRGGBB when possible."""
    if not value:
        return None
    s = str(value).strip().lstrip('#')
    if len(s) == 8:
        s = s[:6]
    if len(s) != 6:
        return None
    if not re.fullmatch(r'[0-9a-fA-F]{6}', s):
        return None
    return f'#{s.upper()}'


def _extract_job_meta(job: BambuPrintJob) -> tuple[dict, dict]:
    """Build UI-friendly metadata from raw_payload and per-slot fallbacks.

    Returns:
      (job_meta, slot_meta_by_material_id)
    """
    payload = {}
    if job.raw_payload:
        try:
            payload = json.loads(job.raw_payload)
        except (TypeError, ValueError, json.JSONDecodeError):
            payload = {}

    raw_slots = (
        payload.get('amsDetailMapping')
        or payload.get('amsDetailMappings')
        or payload.get('amsDetail')
        or []
    )
    if not isinstance(raw_slots, list):
        raw_slots = []

    nozzle_infos = payload.get('nozzleInfos') or []
    if not isinstance(nozzle_infos, list):
        nozzle_infos = []

    cover_url = _cover_url_from_payload(payload)
    cached_thumb = _find_cached_thumb_path(job.external_id)

    job_meta = {
        'cover_url': cover_url,
        'has_thumbnail': bool(cover_url or cached_thumb),
        'nozzle_infos': nozzle_infos,
        'ams_mapping': payload.get('amsMapping') if isinstance(payload.get('amsMapping'), list) else [],
        'ams_mapping2': payload.get('amsMapping2') if isinstance(payload.get('amsMapping2'), list) else [],
    }

    slot_meta = {}
    for idx, mat in enumerate(list(job.materials or [])):
        raw = raw_slots[idx] if idx < len(raw_slots) and isinstance(raw_slots[idx], dict) else {}
        raw_color = (
            raw.get('targetColor')
            or raw.get('sourceColor')
            or raw.get('colorHex')
            or raw.get('color')
        )
        color_hex = _normalize_color_hex(mat.color_hex) or _normalize_color_hex(raw_color)
        color_code = color_hex or (str(raw_color) if raw_color else None)
        material_type = (
            mat.material_name
            or raw.get('materialName')
            or raw.get('material')
            or raw.get('filamentType')
            or raw.get('targetFilamentType')
            or '?'
        )

        ams_val = mat.ams_id if mat.ams_id is not None else raw.get('amsId')
        if ams_val is None:
            ams_val = raw.get('ams')
        tray_val = mat.tray_id if mat.tray_id is not None else raw.get('trayId')
        if tray_val is None:
            tray_val = raw.get('slotId')

        slot_meta[mat.id] = {
            'material_type': material_type,
            'color_hex': color_hex,
            'color_code': color_code,
            'ams': ams_val,
            'tray': tray_val,
        }

    return job_meta, slot_meta


def _clean_title(title: str) -> str:
    """Clean up slicer-generated plate names into a readable model name.

    Bambu Studio creates titles like 'Model.stl_1 + Model.stl_2' (one entry
    per plate).  Strip the extension and trailing plate index, then deduplicate.
    Also strips bare slicer profile strings like '0.20mm Standard @BBL X1C'.
    """
    if not title:
        return title
    # Slicer profile strings start with a layer-height pattern — skip cleanup
    # for these; they are profile names, not model names (user must edit manually)
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


def _sync_project_filament(project_id: int, filament_id: int, actual_weight: float) -> None:
    """Find or create a ProjectFilament record and mark it as actually used.

    If a matching estimate already exists for this project+filament, mark
    is_used=True and update estimated_weight to the actual consumed weight.
    If no record exists yet, create one with is_used=True so the project
    shows the real consumption without requiring a separate "consume" click.
    Does NOT deduct filament.weight_remaining — that is handled by the caller.
    """
    pf = ProjectFilament.query.filter_by(
        project_id=project_id,
        filament_id=filament_id,
        is_used=False,
    ).first()
    if pf:
        # Mark existing planned estimate as actually used — do NOT change estimated_weight
        pf.is_used = True
    # If there is no existing estimate we intentionally do NOT create one here.
    # The Bambu job itself already shows up in project_detail under "Bambu jobs",
    # so creating a ProjectFilament entry would be a duplicate.


def _job_unassigned_filter():
    material_count = (
        select(func.count(BambuJobMaterial.id))
        .where(BambuJobMaterial.job_id == BambuPrintJob.id)
        .scalar_subquery()
    )
    has_assigned_single_slot = BambuPrintJob.materials.any(BambuJobMaterial.filament_id.is_not(None))

    return or_(
        and_(
            material_count > 1,
            BambuPrintJob.materials.any(BambuJobMaterial.filament_id.is_(None)),
        ),
        and_(
            material_count <= 1,
            BambuPrintJob.filament_id.is_(None),
            ~has_assigned_single_slot,
        ),
    )


def _job_not_deducted_filter():
    material_count = (
        select(func.count(BambuJobMaterial.id))
        .where(BambuJobMaterial.job_id == BambuPrintJob.id)
        .scalar_subquery()
    )
    has_deducted_single_slot = BambuPrintJob.materials.any(BambuJobMaterial.deducted.is_(True))

    return or_(
        and_(
            material_count > 1,
            BambuPrintJob.materials.any(BambuJobMaterial.deducted.is_(False)),
        ),
        and_(
            material_count <= 1,
            BambuPrintJob.deducted.is_(False),
            ~has_deducted_single_slot,
        ),
    )


def _job_display_state(job: BambuPrintJob) -> dict:
    materials = list(job.materials)
    is_mm = len(materials) > 1
    single_slot = materials[0] if len(materials) == 1 else None
    display_filament = job.filament or (single_slot.filament if single_slot and single_slot.filament else None)

    if is_mm:
        show_unassigned = any(mat.filament_id is None for mat in materials)
        show_deducted = bool(materials) and all(mat.deducted for mat in materials)
    else:
        show_unassigned = display_filament is None
        show_deducted = bool(job.deducted or (single_slot and single_slot.deducted))

    return {
        'is_multimaterial': is_mm,
        'show_unassigned': show_unassigned,
        'show_deducted': show_deducted,
        'filament_name': display_filament.name if display_filament else None,
        'project_name': job.project.name if job.project else None,
    }




def do_sync(token: str, region: str) -> dict:
    """Idempotent fetch-and-store of Bambu Cloud print tasks.

    Returns a dict::

        {'added': int, 'updated': int, 'skipped': int, 'error': str|None}

    Only the official *.bambulab.com / *.bambulab.cn domain is ever called.
    """
    added = updated = skipped = 0

    base = _api_base(region)
    url = f'{base}/v1/user-service/my/tasks'

    try:
        resp = requests.get(
            url,
            params={'limit': 100, 'offset': 0},
            headers={'Authorization': f'Bearer {token}'},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        _LOG.error('Bambu sync error: %s', exc)
        return {'added': 0, 'updated': 0, 'skipped': 0, 'error': str(exc)}

    hits = data.get('hits') or data.get('tasks') or []

    # Track device_ids registered in this batch to avoid duplicate INSERTs
    # before the session is committed (query won't see uncommitted rows).
    registered_device_ids: set = set(
        p.device_id for p in BambuPrinter.query.with_entities(BambuPrinter.device_id).all()
    )

    # Batch pre-load existing jobs to avoid N+1 per-task queries
    ext_ids = [str(task.get('id', '')).strip() for task in hits]
    ext_ids = [eid for eid in ext_ids if eid]
    existing_by_ext_id = {}
    if ext_ids:
        existing_by_ext_id = {
            job.external_id: job
            for job in BambuPrintJob.query.filter(BambuPrintJob.external_id.in_(ext_ids)).all()
        }

    for task in hits:
        ext_id = str(task.get('id', '')).strip()
        if not ext_id:
            skipped += 1
            continue

        cover_url = _cover_url_from_payload(task)
        if cover_url and not _find_cached_thumb_path(ext_id):
            _cache_cover_image(ext_id, cover_url)

        task_payload = json.dumps(task, ensure_ascii=False)
        status = _resolve_status(task.get('status', 0))

        existing = existing_by_ext_id.get(ext_id)
        if existing:
            changed = False
            if existing.raw_payload != task_payload:
                existing.raw_payload = task_payload
                changed = True
            if existing.status != status:
                existing.status = status
                changed = True
            # Backfill fields that may be missing from earlier syncs
            if not existing.printer_name:
                dn = (task.get('deviceName') or task.get('printerName')
                      or (task.get('printer') or {}).get('name'))
                if dn:
                    existing.printer_name = dn
                    changed = True
            if not existing.cost_time:
                ct = task.get('costTime')
                if ct:
                    existing.cost_time = int(ct)
                    changed = True
            if changed:
                updated += 1
            else:
                skipped += 1
            continue

        # ── Correct field names from actual Bambu Cloud API ─────────────────
        # Primary device identifier: deviceId is the real serial number.
        # instanceId is often 0 (falsy) or an unrelated numeric ID — ignore it.
        device_id = task.get('deviceId') or task.get('instanceId') or None
        if device_id == 0:
            device_id = None
        printer_name = (
            task.get('deviceName')
            or task.get('printerName')
            or (task.get('printer') or {}).get('name')
        )
        printer_model = (
            task.get('deviceModel')
            or task.get('printerModel')
            or (task.get('printer') or {}).get('model')
        )
        # Model name: prefer designTitle (human-readable design name), fall
        # back to title cleaned of STL plate indices.
        raw_design = (task.get('designTitle') or '').strip()
        raw_title = (task.get('title') or '').strip()
        model_name = raw_design or _clean_title(raw_title) or None
        cost_time = task.get('costTime')  # seconds

        # ── Gather material slots (Bambu uses amsDetailMappings or amsDetail)
        ams_list = (
            task.get('amsDetailMappings')
            or task.get('amsDetailMapping')
            or task.get('amsDetail')
            or []
        )
        total_weight = float(task.get('weight') or task.get('totalWeight') or 0.0)
        if not total_weight and ams_list:
            total_weight = sum(float(m.get('weight') or 0) for m in ams_list)

        job = BambuPrintJob(
            external_id=ext_id,
            printer_name=printer_name,
            printer_model=printer_model,
            device_id=device_id,
            model_name=model_name,
            status=status,
            started_at=_parse_ts(task.get('startTime') or task.get('createTime')),
            finished_at=_parse_ts(task.get('endTime')),
            weight_grams=total_weight if total_weight > 0 else None,
            cost_time=int(cost_time) if cost_time else None,
                raw_payload=task_payload,
        )
        db.session.add(job)
        db.session.flush()  # populate job.id

        for m in ams_list:
            slot_w = float(m.get('weight') or 0)
            db.session.add(BambuJobMaterial(
                job_id=job.id,
                ams_id=m.get('amsId') if m.get('amsId') is not None else m.get('ams'),
                tray_id=m.get('trayId') if m.get('trayId') is not None else m.get('slotId'),
                color_hex=(
                    m.get('color')
                    or m.get('colorHex')
                    or m.get('targetColor')
                    or m.get('sourceColor')
                ),
                material_name=(
                    m.get('materialName')
                    or m.get('material')
                    or m.get('filamentType')
                    or m.get('targetFilamentType')
                ),
                weight_grams=slot_w if slot_w > 0 else None,
            ))

        # Auto-register printer — deduplicate within this sync batch
        if device_id and device_id not in registered_device_ids:
            db.session.add(BambuPrinter(
                device_id=device_id,
                name=printer_name or str(device_id),
                printer_model=printer_model,
            ))
            registered_device_ids.add(device_id)

        added += 1

    try:
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        _LOG.error('Bambu sync commit error: %s', exc)
        return {'added': 0, 'updated': 0, 'skipped': skipped, 'error': str(exc)}

    return {'added': added, 'updated': updated, 'skipped': skipped, 'error': None}


def _refetch_missing_thumbnails() -> dict:
    """Try to cache thumbnails for jobs that do not have a local thumbnail yet."""
    stats = {
        'total_jobs': 0,
        'already_cached': 0,
        'missing_candidates': 0,
        'missing_cover': 0,
        'fetched': 0,
        'failed': 0,
    }

    jobs = BambuPrintJob.query.with_entities(BambuPrintJob.external_id, BambuPrintJob.raw_payload).all()
    for external_id, raw_payload in jobs:
        stats['total_jobs'] += 1

        if _find_cached_thumb_path(external_id):
            stats['already_cached'] += 1
            continue

        payload = {}
        if raw_payload:
            try:
                payload = json.loads(raw_payload)
            except (TypeError, ValueError, json.JSONDecodeError):
                payload = {}

        cover_url = _cover_url_from_payload(payload)
        if not cover_url:
            stats['missing_cover'] += 1
            continue

        stats['missing_candidates'] += 1
        if _cache_cover_image(external_id, cover_url):
            stats['fetched'] += 1
        else:
            stats['failed'] += 1

    return stats


# ─── Route registration ──────────────────────────────────────────────────────

def register(app):
    bp = Blueprint('bambu', __name__)

    # Make _format_duration available in all templates from this route module
    app.jinja_env.globals['format_duration'] = _format_duration

    @bp.route('/bambu')
    def bambu_jobs():
        setting = get_settings()
        page = request.args.get('page', 1, type=int)
        job_filter = request.args.get('filter', '')
        filament_id = request.args.get('filament_id', type=int)
        per_page = 20

        hide_failed = request.args.get('hide_failed', '') == '1'
        base_q = BambuPrintJob.query
        active_filament = db.session.get(Filament, filament_id) if filament_id else None
        if filament_id:
            base_q = base_q.filter(or_(
                BambuPrintJob.filament_id == filament_id,
                BambuPrintJob.materials.any(BambuJobMaterial.filament_id == filament_id),
            ))
        if hide_failed:
            base_q = base_q.filter(BambuPrintJob.status.notin_(('FAILED', 'CANCELLED')))
        if job_filter == 'unassigned':
            base_q = base_q.filter(_job_unassigned_filter())
        elif job_filter == 'not_deducted':
            base_q = base_q.filter(_job_not_deducted_filter())

        jobs = db.paginate(
            base_q.order_by(BambuPrintJob.started_at.desc().nullslast(), BambuPrintJob.synced_at.desc()).statement,
            page=page, per_page=per_page, error_out=False,
        )

        # Counts for filter bar badges
        count_base = BambuPrintJob.query
        if filament_id:
            count_base = count_base.filter(or_(
                BambuPrintJob.filament_id == filament_id,
                BambuPrintJob.materials.any(BambuJobMaterial.filament_id == filament_id),
            ))
        if hide_failed:
            count_base = count_base.filter(BambuPrintJob.status.notin_(('FAILED', 'CANCELLED')))
        count_all = count_base.count()
        count_unassigned = count_base.filter(_job_unassigned_filter()).count()
        count_not_deducted = count_base.filter(_job_not_deducted_filter()).count()

        filaments_orm = Filament.query.options(joinedload(Filament.brand), joinedload(Filament.material), joinedload(Filament.color)).order_by(Filament.name).all()
        projects_orm = Project.query.order_by(Project.name).all()
        printers = BambuPrinter.query.order_by(BambuPrinter.name).all()
        has_token = bool(setting and setting.bambu_token)
        # Serialise to simple dicts for Alpine.js fulltext dropdowns
        filaments_json = [
            {
                'id': f.id,
                'label': f.name,
                'mat': f"{f.brand.name} {f.material.name}" if f.brand and f.material else '',
                'material_name': f.material.name if f.material else '',
                'color_hex': f.color.hex_value if f.color else '',
            }
            for f in filaments_orm
        ]
        projects_json = [
            {'id': p.id, 'name': p.name}
            for p in projects_orm
        ]

        bambu_payload_meta = {}
        slot_meta_by_material = {}
        for job in jobs.items:
            job_meta, slot_meta = _extract_job_meta(job)
            bambu_payload_meta[job.id] = job_meta
            slot_meta_by_material.update(slot_meta)

        return render_template(
            'bambu.html',
            jobs=jobs,
            filaments=filaments_json,
            projects=projects_json,
            waste_filaments=filaments_orm,
            waste_projects=projects_orm,
            printers=printers,
            has_token=has_token,
            setting=setting,
            job_filter=job_filter,
            active_filament=active_filament,
            active_filament_id=filament_id,
            count_all=count_all,
            count_unassigned=count_unassigned,
            count_not_deducted=count_not_deducted,
            hide_failed=hide_failed,
            bambu_payload_meta=bambu_payload_meta,
            slot_meta_by_material=slot_meta_by_material,
        )

    @bp.route('/bambu/sync', methods=['POST'])
    def bambu_sync():
        setting = get_settings()
        if not setting or not setting.bambu_token:
            return jsonify({'ok': False, 'error': 'No Bambu token configured'}), 400
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
        return jsonify({'ok': result['error'] is None, **result})

    @bp.route('/bambu/refetch-thumbnails', methods=['POST'])
    def bambu_refetch_thumbnails():
        stats = _refetch_missing_thumbnails()
        return jsonify({'ok': True, **stats})

    @bp.route('/bambu/job/<int:job_id>/thumbnail')
    def bambu_job_thumbnail(job_id):
        job = db.session.get(BambuPrintJob, job_id)
        if not job:
            abort(404)

        cached = _find_cached_thumb_path(job.external_id)
        if cached:
            return _send_inline_thumbnail(cached)

        payload = {}
        if job.raw_payload:
            try:
                payload = json.loads(job.raw_payload)
            except (TypeError, ValueError, json.JSONDecodeError):
                payload = {}

        cover_url = _cover_url_from_payload(payload)
        if not cover_url:
            abort(404)

        recached = _cache_cover_image(job.external_id, cover_url)
        if recached:
            return _send_inline_thumbnail(recached)

        # Stored cover URL has expired — try to get a fresh one from Bambu API
        setting = get_settings()
        if setting and setting.bambu_token:
            try:
                api_token = decrypt_token(setting.bambu_token)
                region = setting.bambu_region or 'global'
                fresh_url = _fetch_fresh_cover_url_from_api(job.external_id, api_token, region)
                if fresh_url and fresh_url != cover_url:
                    recached = _cache_cover_image(job.external_id, fresh_url)
                    if recached:
                        # Persist the fresh URL back into the job payload so
                        # future loads skip the API roundtrip.
                        try:
                            payload['cover'] = fresh_url
                            job.raw_payload = json.dumps(payload, ensure_ascii=False)
                            db.session.commit()
                        except Exception:
                            db.session.rollback()
                        return _send_inline_thumbnail(recached)
            except Exception:
                pass

        return _thumbnail_placeholder_response()

    @bp.route('/bambu/job/<int:job_id>/map', methods=['POST'])
    def bambu_job_map(job_id):
        """Manually map filament + project to a job; optionally deduct stock."""
        is_ajax = request.args.get('ajax') == '1'
        job = db.session.get(BambuPrintJob, job_id)
        if not job:
            if is_ajax:
                return jsonify({'ok': False, 'error': 'not found'}), 404
            return redirect(url_for('bambu_jobs'))

        filament_id = request.form.get('filament_id', type=int)
        project_id = request.form.get('project_id', type=int)
        deduct_now = request.form.get('deduct') == '1'

        model_name_input = request.form.get('model_name', '').strip()
        if model_name_input:
            job.model_name = model_name_input

        single_slot = job.materials[0] if len(job.materials) == 1 else None
        if filament_id:
            job.filament_id = filament_id
            if single_slot:
                single_slot.filament_id = filament_id
        project_raw = request.form.get('project_id', '').strip()
        if project_raw == '':
            job.project_id = None
        elif project_id:
            job.project_id = project_id

        if (
            deduct_now
            and filament_id
            and not job.deducted
            and job.weight_grams
            and job.weight_grams > 0
        ):
            filament = db.session.get(Filament, filament_id)
            if filament:
                actual_amount = deduct_filament_stock(filament, job.weight_grams)
                if actual_amount > 0:
                    log_movement(
                        filament,
                        'bambu_print',
                        actual_amount,
                        project_id=project_id or job.project_id,
                        bambu_job_id=job.id,
                        note=f'Bambu job: {job.model_name or job.external_id}',
                    )
                    db.session.add(PrintHistory(
                        filament_name=(
                            f"{filament.name} | {filament.brand.name} {filament.material.name}"
                            if filament.brand and filament.material
                            else filament.name
                        ),
                        weight=actual_amount,
                        total_cost=0.0,
                    ))
                    job.deducted = True
                    if single_slot:
                        single_slot.deducted = True
                    # If the job is linked to a project, mark that filament as
                    # actually consumed in the project (find or create the link).
                    effective_project_id = project_id or job.project_id
                    if effective_project_id:
                        _sync_project_filament(effective_project_id, filament_id, actual_amount)

        db.session.commit()
        if is_ajax:
            state = _job_display_state(job)
            return jsonify({
                'ok': True,
                'job_id': job.id,
                **state,
                'filter_counts': {
                    'all': BambuPrintJob.query.count(),
                    'unassigned': BambuPrintJob.query.filter(_job_unassigned_filter()).count(),
                    'not_deducted': BambuPrintJob.query.filter(_job_not_deducted_filter()).count(),
                },
            })
        return redirect(url_for('bambu_jobs'))

    @bp.route('/bambu/job/<int:job_id>/deduct-slot', methods=['POST'])
    def bambu_job_deduct_slot(job_id):
        """Map a specific AMS slot to a filament and deduct from stock.

        Supports AJAX mode (returns JSON) when the query-string contains
        ``ajax=1``.  The redirect branch is kept for the (legacy) HTML-form
        fallback path.
        """
        is_ajax = request.args.get('ajax') == '1'
        job = db.session.get(BambuPrintJob, job_id)
        if not job:
            if is_ajax:
                return jsonify({'ok': False, 'error': 'not found'}), 404
            return redirect(url_for('bambu_jobs'))

        slot_id = request.form.get('slot_id', type=int)
        filament_id = request.form.get('filament_id', type=int)
        slot = db.session.get(BambuJobMaterial, slot_id) if slot_id else None

        filament_name = None
        actually_deducted = False

        if slot and slot.job_id == job_id and filament_id and not slot.deducted:
            slot.filament_id = filament_id
            filament = db.session.get(Filament, filament_id)
            filament_name = filament.name if filament else None
            weight = slot.weight_grams or 0.0
            if weight > 0 and filament:
                actual_amount = deduct_filament_stock(filament, weight)
                if actual_amount > 0:
                    log_movement(
                        filament,
                        'bambu_print',
                        actual_amount,
                        project_id=job.project_id,
                        bambu_job_id=job.id,
                        note=f'Bambu slot: {job.model_name or job.external_id}',
                    )
                    slot.deducted = True
                    actually_deducted = True
                    # Propagate to the linked project if any
                    if job.project_id:
                        _sync_project_filament(job.project_id, filament_id, actual_amount)

        db.session.commit()

        if is_ajax:
            return jsonify({
                'ok': True,
                'filament_id': filament_id,
                'filament_name': filament_name,
                'deducted': actually_deducted,
            })
        return redirect(url_for('bambu_jobs'))

    @bp.route('/bambu/job/<int:job_id>/delete', methods=['POST'])
    def bambu_job_delete(job_id):
        job = db.session.get(BambuPrintJob, job_id)
        if job:
            db.session.delete(job)
            db.session.commit()
        return redirect(url_for('bambu_jobs'))
    app.register_blueprint(bp)
