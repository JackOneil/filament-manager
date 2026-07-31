"""
Bambu Lab Cloud integration — idempotent print-job sync, job list, manual
filament mapping, and stock deduction.

Routes are registered via a Flask Blueprint (bambu). A url_for fallback
handler in app.py maps unprefixed endpoint names to blueprint-prefixed ones.
"""
import json
import math
import re
import logging
import os
import mimetypes
from datetime import datetime, timedelta, timezone

import requests
from urllib.parse import urljoin
from flask import current_app, render_template, request, redirect, url_for, jsonify, Blueprint, send_file, abort

from database import db
from models import (
    BambuPrinter, BambuPrintJob, BambuJobMaterial,
    Filament, PrintHistory, Project, ProjectFilament,
)
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import joinedload
from utils import bambu_api_base, clean_bambu_title, deduct_filament_stock, decrypt_token, get_settings, log_movement, safe_commit, utc_now, try_auto_map_filament, invalidate_kpi_cache, format_duration, normalize_hex, is_safe_external_url


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

def _parse_ts(value):
    """Parse Bambu Cloud timestamp (epoch ms/s int or ISO-8601 string) →
    timezone-aware UTC datetime, or None if unparseable."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        ts = float(value) / 1000 if value > 1_000_000_000_000 else float(value)
        try:
            return datetime.fromtimestamp(ts, tz=timezone.utc)
        except (OSError, OverflowError, ValueError):
            return None
    s = re.sub(r'Z$|[+-]\d{2}:?\d{2}$', '', str(value).strip())
    for fmt in ('%Y-%m-%dT%H:%M:%S.%f', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%dT%H:%M'):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
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

    if not is_safe_external_url(cover_url):
        _LOG.warning('Bambu cover image URL rejected (SSRF guard): %s', cover_url)
        # Do NOT fetch — cover URLs can be attacker-influenced via crafted
        # backup imports (raw_payload) and could point at internal services.
        return None

    try:
        resp = requests.get(cover_url, timeout=15, allow_redirects=False)
        # Follow redirects manually, re-validating every hop (S3 signed URLs
        # redirect to the bucket — the target must pass the same SSRF checks).
        for _ in range(3):
            if resp.status_code not in (301, 302, 303, 307, 308):
                break
            location = resp.headers.get('Location')
            if not location:
                return None
            if location.startswith('/'):
                location = urljoin(cover_url, location)
            if not is_safe_external_url(location):
                _LOG.warning('Bambu cover redirect rejected (SSRF guard): %s', location)
                return None
            resp = requests.get(location, timeout=15, allow_redirects=False)
        resp.raise_for_status()
    except Exception:
        _LOG.warning('Bambu cover image download failed: %s', cover_url)
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
    base = bambu_api_base(region)
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
        _LOG.warning('Bambu single-task cover fetch failed for ext_id=%s', external_id)

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
        _LOG.warning('Bambu fallback cover scan failed for ext_id=%s', external_id)

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
        color_hex = normalize_hex(mat.color_hex) or normalize_hex(raw_color)
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

    Fetches the latest 100 tasks from the Bambu Cloud API, then reconciles
    any job still marked RUNNING that was NOT returned by the API (i.e. has
    been evicted from the API response) to FINISH.

    Additionally, an ``endTime``-based override handles the case where Bambu
    Cloud's status field lags behind reality: if the API provides ``endTime``
    but the resolved status is still ``RUNNING``, the job is promoted to
    ``FINISH`` immediately.

    Returns a dict::

        {'added': int, 'updated': int, 'skipped': int, 'orphans_reconciled': int, 'error': str|None}

    Only the official *.bambulab.com / *.bambulab.cn domain is ever called.
    """
    added = updated = skipped = 0
    orphans_reconciled = 0
    new_job_ids: list = []  # IDs of newly inserted jobs (for auto-mapping)
    all_ext_ids: set = set()

    base = bambu_api_base(region)
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
        _LOG.exception('Bambu sync API fetch error: %s', exc)
        return {'added': 0, 'updated': 0, 'skipped': 0, 'orphans_reconciled': 0, 'error': str(exc)}

    hits = data.get('hits') or data.get('tasks') or []
    hits_count = len(hits)
    if not hits:
        _LOG.error('Bambu sync: API returned 0 tasks (response keys: %s)', list(data.keys()))
    else:
        _LOG.info('Bambu sync: API returned %d tasks, first status=%s, keys=%s',
                   hits_count, hits[0].get('status', 'N/A'), list(hits[0].keys())[:15])

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
        all_ext_ids.add(ext_id)

        cover_url = _cover_url_from_payload(task)
        if cover_url and not _find_cached_thumb_path(ext_id):
            _cache_cover_image(ext_id, cover_url)

        task_payload = json.dumps(task, ensure_ascii=False)
        status = _resolve_status(task.get('status', 0))

        # ── endTime override ─────────────────────────────────────
        # Bambu Cloud sometimes lags in updating the status field:
        # a completed job may still report status=1 (RUNNING) even
        # though endTime is already set.  If endTime exists and the
        # resolved status is still RUNNING, promote to FINISH so the
        # UI shows the correct state.
        end_time_ts = task.get('endTime')
        if end_time_ts and status == 'RUNNING':
            status = 'FINISH'
            _LOG.debug('Bambu sync: override RUNNING→FINISH for task %s (endTime=%s)', ext_id, end_time_ts)

        # ── costTime heuristic ────────────────────────────────────
        # If the API doesn't provide endTime yet but the print
        # duration (costTime) + startTime is in the past, the print
        # must have completed.  Apply a 1-hour safety margin.
        # Covers both RUNNING and PAUSED — Bambu Cloud sometimes
        # reports status=4 (PAUSED) during active printing and only
        # updates to FINISH (2) after the job fully completes.
        if status in ('RUNNING', 'PAUSED'):
            ct = task.get('costTime')
            st = task.get('startTime') or task.get('createTime')
            if ct and st:
                started = _parse_ts(st)
                if started and utc_now() > started + timedelta(seconds=int(ct) + 3600):
                    status = 'FINISH'
                    _LOG.debug('Bambu sync: costTime heuristic %s→FINISH for task %s', status, ext_id)

        existing = existing_by_ext_id.get(ext_id)
        if existing:
            changed = False
            # Always sync raw_payload (Bambu may add metadata timestamps).
            if existing.raw_payload != task_payload:
                existing.raw_payload = task_payload
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
                # raw_payload-only changes are counted as "skipped" — the
                # job was processed but no status or meaningful field changed.
                skipped += 1
            continue

        # ── Correct field names from actual Bambu Cloud API ─────────────────
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
        raw_design = (task.get('designTitle') or '').strip()
        raw_title = (task.get('title') or '').strip()
        model_name = raw_design or clean_bambu_title(raw_title) or None
        cost_time = task.get('costTime')

        # ── Gather material slots
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
        new_job_ids.append(job.id)

        for m in ams_list:
            slot_w = float(m.get('weight') or 0)
            db.session.add(BambuJobMaterial(
                job_id=job.id,
                ams_id=m.get('amsId') if m.get('amsId') is not None else m.get('ams'),
                tray_id=m.get('trayId') if m.get('trayId') is not None else m.get('slotId'),
                color_hex=(
                    m.get('color') or m.get('colorHex')
                    or m.get('targetColor') or m.get('sourceColor')
                ),
                material_name=(
                    m.get('materialName') or m.get('material')
                    or m.get('filamentType') or m.get('targetFilamentType')
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
        safe_commit()
    except Exception as exc:
        db.session.rollback()
        _LOG.exception('Bambu sync commit error: %s', exc)
        return {'added': 0, 'updated': 0, 'skipped': skipped, 'orphans_reconciled': 0, 'error': str(exc)}

    # ── Orphan reconciliation ──────────────────────────────────────────────
    # Any job still marked RUNNING whose external_id was NOT seen in the API
    # response is reconciled to FINISH.  This only runs when the API actually
    # returned tasks — an empty response usually means a transient outage,
    # and treating it as authoritative would force-finish every RUNNING job.
    if all_ext_ids:
        try:
            orphans = BambuPrintJob.query.filter(
                BambuPrintJob.status == 'RUNNING',
                ~BambuPrintJob.external_id.in_(all_ext_ids),
            ).all()
            for orphan in orphans:
                orphan.status = 'FINISH'
                if not orphan.finished_at:
                    orphan.finished_at = utc_now()
            if orphans:
                safe_commit()
                orphans_reconciled = len(orphans)
                _LOG.info('Bambu sync: auto-reconciled %d orphan RUNNING job(s) to FINISH', orphans_reconciled)
        except Exception as exc:
            db.session.rollback()
            _LOG.warning('Bambu sync orphan reconciliation failed: %s', exc)

    # ── Auto-mapping (runs after commit so job IDs are stable) ───────────────
    setting = get_settings()
    if setting and getattr(setting, 'auto_filament_mapping_enabled', True) and new_job_ids:
        auto_mapped = _auto_map_new_jobs(new_job_ids)
        if auto_mapped:
            _LOG.info('Auto-mapped %d filament slot(s) across %d new Bambu job(s)', auto_mapped, len(new_job_ids))

    return {'added': added, 'updated': updated, 'skipped': skipped, 'hits': hits_count, 'orphans_reconciled': orphans_reconciled, 'error': None}


def _auto_map_from_history(job) -> int:
    """Try to assign filaments from a previously-mapped job with the same model_name.

    When a Bambu job shares the same ``model_name`` as an earlier job that was
    already manually mapped, copy the filament assignments slot-by-slot using
    colour hex + material name as the matching key.

    Returns the number of slots mapped from history (0 when no historic match
    exists or the job has no ``model_name``).
    """
    if not job.model_name:
        return 0

    materials = list(job.materials)
    unmapped = [m for m in materials if m.filament_id is None]
    if not unmapped:
        return 0

    # Find the most recently-synced job with the same model_name that has AT
    # LEAST one mapped slot.
    historic_job = (
        BambuPrintJob.query
        .filter(
            BambuPrintJob.model_name == job.model_name,
            BambuPrintJob.id != job.id,
            BambuPrintJob.materials.any(BambuJobMaterial.filament_id.is_not(None)),
        )
        .order_by(BambuPrintJob.synced_at.desc())
        .first()
    )
    if not historic_job:
        return 0

    # Build a lookup: (norm_color_hex, norm_material) → filament_id
    historic_slots = {}
    for hm in historic_job.materials:
        if hm.filament_id is None:
            continue
        key = (
            normalize_hex(hm.color_hex) or '',
            (hm.material_name or '').strip().upper(),
        )
        historic_slots[key] = hm.filament_id

    if not historic_slots:
        return 0

    mapped_count = 0
    for mat in unmapped:
        key = (
            normalize_hex(mat.color_hex) or '',
            (mat.material_name or '').strip().upper(),
        )
        if key in historic_slots and historic_slots[key] is not None:
            mat.filament_id = historic_slots[key]
            mapped_count += 1

    if mapped_count and len(materials) == 1:
        # Sync top-level filament_id for single-slot jobs
        if materials[0].filament_id is not None:
            job.filament_id = materials[0].filament_id

    return mapped_count


def _auto_map_new_jobs(job_ids: list) -> int:
    """Run auto-mapping on the given job IDs.

    Mapping strategy (ordered by priority):
    1. **History-based**: re-use assignments from a previously-mapped job with
       the same ``model_name`` (colour + material slot matching).
    2. **Material+colour matching**: calls ``try_auto_map_filament`` and
       assigns the filament when there is exactly one candidate.

    Returns the number of slots that were automatically mapped.
    """
    if not job_ids:
        return 0

    mapped_count = 0
    jobs = BambuPrintJob.query.filter(BambuPrintJob.id.in_(job_ids)).all()

    for job in jobs:
        # ── Step 1: History-based mapping ─────────────────────────────────
        history_mapped = _auto_map_from_history(job)
        if history_mapped:
            mapped_count += history_mapped

        # ── Step 2: Material + colour matching for remaining unmapped slots ─
        materials = list(job.materials)
        is_mm = len(materials) > 1

        if is_mm:
            for mat in materials:
                if mat.filament_id is not None:
                    continue
                best, _ = try_auto_map_filament(mat.material_name, mat.color_hex)
                if best:
                    mat.filament_id = best.id
                    mapped_count += 1
        else:
            if job.filament_id is not None:
                continue
            color_hex = materials[0].color_hex if materials else None
            material_name = materials[0].material_name if materials else None
            best, _ = try_auto_map_filament(material_name, color_hex)
            if best:
                job.filament_id = best.id
                if materials:
                    materials[0].filament_id = best.id
                mapped_count += 1

    if mapped_count:
        try:
            safe_commit()
            invalidate_kpi_cache()
        except Exception:
            db.session.rollback()
            _LOG.exception('Auto-mapping commit error')
            return 0

    return mapped_count


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

