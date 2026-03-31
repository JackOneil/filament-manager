"""
Bambu Lab Cloud integration — idempotent print-job sync, job list, manual
filament mapping, and stock deduction.

No Flask Blueprints — all routes are registered directly on the app object.
"""
import json
import re
import logging
from datetime import datetime

import requests
from flask import render_template, request, redirect, url_for, jsonify

from database import db
from models import (
    AppSetting, BambuPrinter, BambuPrintJob, BambuJobMaterial,
    Filament, PrintHistory, Project, ProjectFilament,
)
from sqlalchemy import and_, func, or_, select
from utils import deduct_filament_stock, decrypt_token, log_movement

_LOG = logging.getLogger(__name__)

# ─── Bambu Cloud status mapping ─────────────────────────────────────────────
# Verified against actual Bambu Cloud /v1/user-service/my/tasks responses.
# status=2 is FINISH (completed) in the Cloud task API.
_STATUS_MAP = {
    0: 'INIT',
    1: 'RUNNING',
    2: 'FINISH',      # Bambu Cloud: 2 = successfully finished (start→end delta ≈ costTime)
    3: 'FAILED',
    4: 'RUNNING',     # Bambu Cloud: 4 = currently printing (API sets endTime placeholder ~6s after start)
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
            return datetime.utcfromtimestamp(ts)
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

    for task in hits:
        ext_id = str(task.get('id', '')).strip()
        if not ext_id:
            skipped += 1
            continue

        status = _resolve_status(task.get('status', 0))

        existing = BambuPrintJob.query.filter_by(external_id=ext_id).first()
        if existing:
            changed = False
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
            raw_payload=json.dumps(task, ensure_ascii=False),
        )
        db.session.add(job)
        db.session.flush()  # populate job.id

        for m in ams_list:
            slot_w = float(m.get('weight') or 0)
            db.session.add(BambuJobMaterial(
                job_id=job.id,
                ams_id=m.get('amsId'),
                tray_id=m.get('trayId'),
                color_hex=m.get('color') or m.get('colorHex'),
                material_name=m.get('materialName') or m.get('material'),
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


# ─── Route registration ──────────────────────────────────────────────────────

def register(app):

    # Make _format_duration available in all templates from this route module
    app.jinja_env.globals['format_duration'] = _format_duration

    @app.route('/bambu')
    def bambu_jobs():
        setting = AppSetting.query.first()
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

        jobs = (
            base_q
            .order_by(BambuPrintJob.started_at.desc().nullslast(), BambuPrintJob.synced_at.desc())
            .paginate(page=page, per_page=per_page, error_out=False)
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

        filaments_orm = Filament.query.order_by(Filament.name).all()
        projects_orm = Project.query.order_by(Project.name).all()
        printers = BambuPrinter.query.order_by(BambuPrinter.name).all()
        has_token = bool(setting and setting.bambu_token)
        # Serialise to simple dicts for Alpine.js fulltext dropdowns
        filaments_json = [
            {
                'id': f.id,
                'label': f.name,
                'mat': f"{f.brand.name} {f.material.name}" if f.brand and f.material else '',
            }
            for f in filaments_orm
        ]
        projects_json = [
            {'id': p.id, 'name': p.name}
            for p in projects_orm
        ]
        return render_template(
            'bambu.html',
            jobs=jobs,
            filaments=filaments_json,
            projects=projects_json,
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
        )

    @app.route('/bambu/sync', methods=['POST'])
    def bambu_sync():
        setting = AppSetting.query.first()
        if not setting or not setting.bambu_token:
            return jsonify({'ok': False, 'error': 'No Bambu token configured'}), 400
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
        return jsonify({'ok': result['error'] is None, **result})

    @app.route('/bambu/job/<int:job_id>/map', methods=['POST'])
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

    @app.route('/bambu/job/<int:job_id>/deduct-slot', methods=['POST'])
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

    @app.route('/bambu/job/<int:job_id>/delete', methods=['POST'])
    def bambu_job_delete(job_id):
        job = db.session.get(BambuPrintJob, job_id)
        if job:
            db.session.delete(job)
            db.session.commit()
        return redirect(url_for('bambu_jobs'))
