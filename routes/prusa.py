"""
PrusaLink local API integration — poll-based print job recording,
printer management, filament mapping, and stock deduction.

PrusaLink is the official, locally-hosted REST API that runs directly on
the printer (or on a Raspberry Pi). It is authenticated via an X-Api-Key
header. Only the current job state is available (no cloud history), so
this integration polls each printer periodically and records completed
or in-progress print jobs.

No Flask Blueprints — all routes are registered directly on the app object.
"""
import json
import logging
import re
from datetime import datetime, timezone

import requests
from flask import render_template, request, redirect, url_for, jsonify

from database import db
from models import (
    AppSetting, PrusaPrinter, PrusaPrintJob,
    Filament, Project, PrintHistory, ProjectFilament,
)
from utils import deduct_filament_stock, encrypt_token, decrypt_token, log_movement

_LOG = logging.getLogger(__name__)

_PRUSA_TIMEOUT = 10  # seconds per HTTP request to printer


# ─── Helpers ────────────────────────────────────────────────────────────────

def _prusa_headers(api_key: str) -> dict:
    return {'X-Api-Key': api_key}


def _clean_filename(raw: str) -> str:
    """Strip extension and underscores from a g-code filename for display."""
    if not raw:
        return raw
    name = re.sub(r'\.(gcode|bgcode|gco|gc|sl1|3mf)$', '', raw, flags=re.IGNORECASE).strip()
    name = name.replace('_', ' ').replace('-', ' ')
    # Collapse multiple spaces
    name = re.sub(r'\s+', ' ', name).strip()
    return name or raw


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


def _validate_host(host: str) -> str | None:
    """Normalise and validate a printer host URL.

    Returns the cleaned URL or None if the value is clearly invalid.
    Only http:// and https:// are allowed. Empty string is treated as invalid.
    """
    host = (host or '').strip().rstrip('/')
    if not host:
        return None
    if not re.match(r'^https?://', host, re.IGNORECASE):
        host = 'http://' + host
    # Basic sanity check — must contain at least one dot or be a valid IP-like
    parsed = re.sub(r'^https?://', '', host, flags=re.IGNORECASE)
    if not parsed:
        return None
    return host


def _prusa_request(printer: PrusaPrinter, path: str) -> dict | None:
    """GET request to a PrusaLink endpoint.  Returns parsed JSON or None on error."""
    api_key = decrypt_token(printer.api_key)
    url = f'{printer.host.rstrip("/")}/{path.lstrip("/")}'
    try:
        resp = requests.get(
            url,
            headers=_prusa_headers(api_key),
            timeout=_PRUSA_TIMEOUT,
        )
        if resp.status_code == 204:
            return {}  # No content — no current job
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.Timeout:
        _LOG.warning('PrusaLink timeout for printer %s (%s)', printer.name, url)
    except requests.exceptions.ConnectionError:
        _LOG.warning('PrusaLink connection error for printer %s (%s)', printer.name, url)
    except Exception as exc:
        _LOG.warning('PrusaLink request error for printer %s: %s', printer.name, exc)
    return None


def do_poll(printer: PrusaPrinter) -> dict:
    """Poll a single PrusaLink printer and store any new/updated print jobs.

    Returns::
        {'added': int, 'updated': int, 'error': str|None}
    """
    added = updated = 0

    # ── 1. Fetch current status ───────────────────────────────────────────
    status_data = _prusa_request(printer, '/api/v1/status')
    if status_data is None:
        return {'added': 0, 'updated': 0, 'error': f'Cannot reach {printer.host}'}

    job_status = status_data.get('job') or {}
    printer_status = status_data.get('printer') or {}

    # ── 2. Fetch detailed job info ────────────────────────────────────────
    job_data = _prusa_request(printer, '/api/v1/job')
    if job_data is None:
        job_data = {}

    # Determine state
    state = (job_status.get('state') or printer_status.get('state') or '').upper()
    if not state or state in ('IDLE', 'READY', 'OPERATIONAL', ''):
        # No active job — nothing to record
        return {'added': 0, 'updated': 0, 'error': None}

    # ── 3. Extract job fields ─────────────────────────────────────────────
    raw_file: str = (
        (job_data.get('file') or {}).get('name')
        or job_status.get('file')
        or ''
    )
    display_name = (
        (job_data.get('file') or {}).get('display_name')
        or _clean_filename(raw_file)
        or raw_file
        or None
    )

    # Weight from g-code metadata (grams)
    meta = (job_data.get('file') or {}).get('metadata') or {}
    weight_raw = meta.get('filament used [g]')
    weight_grams = float(weight_raw) if weight_raw else None

    # Estimated duration (seconds)
    time_estimated = job_data.get('time_remaining') or job_data.get('time_estimated') or None
    if time_estimated:
        time_estimated = int(time_estimated)

    # Progress (0.0–1.0)
    progress_raw = job_status.get('progress') or job_data.get('progress') or None
    progress = float(progress_raw) / 100.0 if progress_raw is not None else None

    # Normalise state string
    if state in ('PRINTING', 'BUSY', 'ATTENTION'):
        norm_state = 'PRINTING'
    elif state in ('FINISHED', 'DONE'):
        norm_state = 'FINISHED'
    elif state in ('STOPPED', 'CANCELED', 'CANCELLED', 'ERROR'):
        norm_state = 'STOPPED'
    else:
        norm_state = state

    raw_payload = json.dumps({
        'status': status_data,
        'job': job_data,
    }, ensure_ascii=False)

    # ── 4. Find or create job record ─────────────────────────────────────
    # We use a combination of (printer_id + file_name + started_at_date) as a
    # natural key. Because PrusaLink doesn't provide a persistent job ID we
    # check for an in-progress record for this printer+file and upsert it.
    existing = (
        PrusaPrintJob.query
        .filter_by(printer_id=printer.id, file_name=raw_file or None, status='PRINTING')
        .order_by(PrusaPrintJob.synced_at.desc())
        .first()
    )

    if existing:
        changed = False
        if existing.status != norm_state:
            existing.status = norm_state
            if norm_state in ('FINISHED', 'STOPPED') and not existing.finished_at:
                existing.finished_at = datetime.utcnow()
            changed = True
        if progress is not None and existing.progress != progress:
            existing.progress = progress
            changed = True
        existing.synced_at = datetime.utcnow()
        existing.raw_payload = raw_payload
        if changed:
            updated += 1
    else:
        # Only create a new record if there is an active job
        if norm_state == 'PRINTING' or norm_state == 'FINISHED':
            job = PrusaPrintJob(
                printer_id=printer.id,
                printer_name=printer.name,
                file_name=raw_file or None,
                display_name=display_name,
                status=norm_state,
                started_at=datetime.utcnow() if norm_state == 'PRINTING' else None,
                finished_at=datetime.utcnow() if norm_state == 'FINISHED' else None,
                weight_grams=weight_grams,
                cost_time=time_estimated,
                progress=progress,
                raw_payload=raw_payload,
            )
            db.session.add(job)
            added += 1

    try:
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        _LOG.error('PrusaLink commit error: %s', exc)
        return {'added': 0, 'updated': 0, 'error': str(exc)}

    return {'added': added, 'updated': updated, 'error': None}


def do_test_connection(printer: PrusaPrinter) -> dict:
    """Test connectivity to a PrusaLink printer.

    Returns dict with 'ok', 'model', 'firmware', 'error'.
    """
    data = _prusa_request(printer, '/api/version')
    if data is None:
        return {'ok': False, 'model': None, 'firmware': None, 'error': f'Cannot reach {printer.host}'}
    version_text = data.get('text') or data.get('version', '')
    firmware = data.get('firmware') or data.get('printer') or ''

    # Try to get model from /api/v1/info
    info = _prusa_request(printer, '/api/v1/info') or {}
    model = info.get('type') or info.get('name') or None

    return {
        'ok': True,
        'model': model,
        'firmware': firmware,
        'version_text': version_text,
        'error': None,
    }


# ─── Route registration ──────────────────────────────────────────────────────

def register(app):

    app.jinja_env.globals['prusa_format_duration'] = _format_duration

    # ── Overview page ────────────────────────────────────────────────────

    @app.route('/prusa')
    def prusa_jobs():
        page = request.args.get('page', 1, type=int)
        job_filter = request.args.get('filter', '')
        filament_id = request.args.get('filament_id', type=int)
        per_page = 20

        hide_failed = request.args.get('hide_failed', '') == '1'
        base_q = PrusaPrintJob.query
        active_filament = db.session.get(Filament, filament_id) if filament_id else None

        if filament_id:
            base_q = base_q.filter(PrusaPrintJob.filament_id == filament_id)
        if hide_failed:
            base_q = base_q.filter(PrusaPrintJob.status.notin_(('STOPPED',)))
        if job_filter == 'unassigned':
            base_q = base_q.filter(PrusaPrintJob.filament_id.is_(None))
        elif job_filter == 'not_deducted':
            base_q = base_q.filter(
                PrusaPrintJob.deducted.is_(False),
                PrusaPrintJob.status == 'FINISHED',
            )

        jobs = (
            base_q
            .order_by(PrusaPrintJob.synced_at.desc())
            .paginate(page=page, per_page=per_page, error_out=False)
        )

        # Badge counts
        count_base = PrusaPrintJob.query
        if filament_id:
            count_base = count_base.filter(PrusaPrintJob.filament_id == filament_id)
        if hide_failed:
            count_base = count_base.filter(PrusaPrintJob.status.notin_(('STOPPED',)))
        count_all = count_base.count()
        count_unassigned = count_base.filter(PrusaPrintJob.filament_id.is_(None)).count()
        count_not_deducted = count_base.filter(
            PrusaPrintJob.deducted.is_(False),
            PrusaPrintJob.status == 'FINISHED',
        ).count()

        printers = PrusaPrinter.query.order_by(PrusaPrinter.name).all()
        filaments_orm = Filament.query.order_by(Filament.name).all()
        projects_orm = Project.query.order_by(Project.name).all()
        has_printers = bool(printers)
        filaments_json = [
            {
                'id': f.id,
                'label': f.name,
                'mat': f'{f.brand.name} {f.material.name}' if f.brand and f.material else '',
            }
            for f in filaments_orm
        ]
        projects_json = [{'id': p.id, 'name': p.name} for p in projects_orm]

        return render_template(
            'prusa.html',
            jobs=jobs,
            printers=printers,
            filaments=filaments_json,
            projects=projects_json,
            has_printers=has_printers,
            job_filter=job_filter,
            active_filament=active_filament,
            active_filament_id=filament_id,
            count_all=count_all,
            count_unassigned=count_unassigned,
            count_not_deducted=count_not_deducted,
            hide_failed=hide_failed,
        )

    # ── Per-printer manual sync ──────────────────────────────────────────

    @app.route('/prusa/printer/<int:printer_id>/sync', methods=['POST'])
    def prusa_printer_sync(printer_id):
        printer = db.session.get(PrusaPrinter, printer_id)
        if not printer:
            return jsonify({'ok': False, 'error': 'Printer not found'}), 404
        result = do_poll(printer)
        return jsonify({'ok': result['error'] is None, **result})

    # ── Connection test ──────────────────────────────────────────────────

    @app.route('/prusa/printer/<int:printer_id>/test', methods=['POST'])
    def prusa_printer_test(printer_id):
        printer = db.session.get(PrusaPrinter, printer_id)
        if not printer:
            return jsonify({'ok': False, 'error': 'Printer not found'}), 404
        result = do_test_connection(printer)
        # Backfill model if discovered
        if result.get('ok') and result.get('model') and not printer.printer_model:
            printer.printer_model = result['model']
            db.session.commit()
        return jsonify(result)

    # ── Job mapping (filament + project) ─────────────────────────────────

    @app.route('/prusa/job/<int:job_id>/map', methods=['POST'])
    def prusa_job_map(job_id):
        is_ajax = request.args.get('ajax') == '1'
        job = db.session.get(PrusaPrintJob, job_id)
        if not job:
            if is_ajax:
                return jsonify({'ok': False, 'error': 'not found'}), 404
            return redirect(url_for('prusa_jobs'))

        filament_id = request.form.get('filament_id', type=int)
        project_id = request.form.get('project_id', type=int)
        deduct_now = request.form.get('deduct') == '1'

        name_input = request.form.get('display_name', '').strip()
        if name_input:
            job.display_name = name_input

        if filament_id:
            job.filament_id = filament_id
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
                        'prusa_print',
                        actual_amount,
                        project_id=project_id or job.project_id,
                        note=f'PrusaLink: {job.display_name or job.file_name or job.id}',
                    )
                    db.session.add(PrintHistory(
                        filament_name=(
                            f'{filament.name} | {filament.brand.name} {filament.material.name}'
                            if filament.brand and filament.material
                            else filament.name
                        ),
                        weight=actual_amount,
                        total_cost=0.0,
                    ))
                    job.deducted = True
                    effective_pid = project_id or job.project_id
                    if effective_pid:
                        _sync_project_filament(effective_pid, filament_id, actual_amount)

        db.session.commit()

        if is_ajax:
            unassigned = PrusaPrintJob.query.filter(PrusaPrintJob.filament_id.is_(None)).count()
            not_deducted = PrusaPrintJob.query.filter(
                PrusaPrintJob.deducted.is_(False),
                PrusaPrintJob.status == 'FINISHED',
            ).count()
            return jsonify({
                'ok': True,
                'job_id': job.id,
                'show_unassigned': job.filament_id is None,
                'show_deducted': job.deducted,
                'filament_name': job.filament.name if job.filament else None,
                'project_name': job.project.name if job.project else None,
                'filter_counts': {
                    'all': PrusaPrintJob.query.count(),
                    'unassigned': unassigned,
                    'not_deducted': not_deducted,
                },
            })
        return redirect(url_for('prusa_jobs'))

    # ── Delete job record ────────────────────────────────────────────────

    @app.route('/prusa/job/<int:job_id>/delete', methods=['POST'])
    def prusa_job_delete(job_id):
        job = db.session.get(PrusaPrintJob, job_id)
        if job:
            db.session.delete(job)
            db.session.commit()
        return redirect(url_for('prusa_jobs'))


# ─── Project filament sync helper ────────────────────────────────────────────

def _sync_project_filament(project_id: int, filament_id: int, actual_weight: float) -> None:
    """Mark a planned ProjectFilament record as actually used (if it exists)."""
    pf = ProjectFilament.query.filter_by(
        project_id=project_id,
        filament_id=filament_id,
        is_used=False,
    ).first()
    if pf:
        pf.is_used = True
