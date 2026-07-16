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
from utils import bambu_api_base, clean_bambu_title, deduct_filament_stock, decrypt_token, get_settings, log_movement, safe_commit, utc_now, try_auto_map_filament, invalidate_kpi_cache, format_duration, normalize_hex, translate


from routes.bambu_helpers import (
    _LOG,
    _parse_ts,
    _resolve_status,
    _thumb_dir,
    _safe_thumb_id,
    _cover_url_from_payload,
    _find_cached_thumb_path,
    _cache_cover_image,
    _fetch_fresh_cover_url_from_api,
    _send_inline_thumbnail,
    _thumbnail_placeholder_response,
    _extract_job_meta,
    _job_unassigned_filter,
    _job_not_deducted_filter,
    _job_display_state,
    do_sync,
    _auto_map_new_jobs,
    _auto_map_from_history,
    _refetch_missing_thumbnails,
)

def register(app):
    bp = Blueprint('bambu', __name__)

    # Make format_duration available in all templates from this route module
    app.jinja_env.globals['format_duration'] = format_duration

    @bp.route('/bambu')
    def bambu_jobs():
        setting = get_settings()
        page = request.args.get('page', 1, type=int)
        job_filter = request.args.get('filter', '')
        filament_id = request.args.get('filament_id', type=int)
        project_id = request.args.get('project_id', type=int)
        search = request.args.get('search', '').strip()
        date_from = request.args.get('date_from', '').strip()
        date_to = request.args.get('date_to', '').strip()
        per_page = 20

        hide_failed = request.args.get('hide_failed', '') == '1'
        base_q = BambuPrintJob.query
        active_filament = db.session.get(Filament, filament_id) if filament_id else None
        if filament_id:
            base_q = base_q.filter(or_(
                BambuPrintJob.filament_id == filament_id,
                BambuPrintJob.materials.any(BambuJobMaterial.filament_id == filament_id),
            ))
        if project_id:
            base_q = base_q.filter(BambuPrintJob.project_id == project_id)
        if search:
            base_q = base_q.filter(BambuPrintJob.model_name.ilike(f'%{search}%'))
        if date_from:
            try:
                df = datetime.strptime(date_from, '%Y-%m-%d')
                base_q = base_q.filter(BambuPrintJob.started_at >= df)
            except (ValueError, OverflowError):
                flash(translate('bambu_invalid_date_filter'), 'warning')
        if date_to:
            try:
                dt = datetime.strptime(date_to, '%Y-%m-%d')
                # Include the entire end day
                dt_end = dt.replace(hour=23, minute=59, second=59)
                base_q = base_q.filter(BambuPrintJob.started_at <= dt_end)
            except (ValueError, OverflowError):
                flash(translate('bambu_invalid_date_filter'), 'warning')
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
        if project_id:
            count_base = count_base.filter(BambuPrintJob.project_id == project_id)
        if search:
            count_base = count_base.filter(BambuPrintJob.model_name.ilike(f'%{search}%'))
        if date_from:
            try:
                df = datetime.strptime(date_from, '%Y-%m-%d')
                count_base = count_base.filter(BambuPrintJob.started_at >= df)
            except (ValueError, OverflowError):
                flash(translate('bambu_invalid_date_filter'), 'warning')
        if date_to:
            try:
                dt = datetime.strptime(date_to, '%Y-%m-%d')
                dt_end = dt.replace(hour=23, minute=59, second=59)
                count_base = count_base.filter(BambuPrintJob.started_at <= dt_end)
            except (ValueError, OverflowError):
                flash(translate('bambu_invalid_date_filter'), 'warning')
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
            job_meta['cleaned_title'] = clean_bambu_title(job.model_name or '') if job.model_name else ''
            bambu_payload_meta[job.id] = job_meta
            slot_meta_by_material.update(slot_meta)

        # Resolve active project/filament names for search bar display
        active_project = db.session.get(Project, project_id) if project_id else None
        active_filament_obj = filament = active_filament
        return render_template(
            'bambu.html',
            jobs=jobs,
            per_page=per_page,
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
            active_project=active_project,
            active_project_id=project_id,
            active_search=search,
            active_date_from=date_from,
            active_date_to=date_to,
            count_all=count_all,
            count_unassigned=count_unassigned,
            count_not_deducted=count_not_deducted,
            hide_failed=hide_failed,
            bambu_payload_meta=bambu_payload_meta,
            slot_meta_by_material=slot_meta_by_material,
        )

    @bp.route('/bambu/jobs-partial')
    def bambu_jobs_partial():
        page = request.args.get('page', 1, type=int)
        job_filter = request.args.get('filter', '')
        filament_id = request.args.get('filament_id', type=int)
        project_id = request.args.get('project_id', type=int)
        search = request.args.get('search', '').strip()
        date_from = request.args.get('date_from', '').strip()
        date_to = request.args.get('date_to', '').strip()
        hide_failed = request.args.get('hide_failed', '') == '1'
        per_page = 20

        base_q = BambuPrintJob.query
        if filament_id:
            base_q = base_q.filter(or_(
                BambuPrintJob.filament_id == filament_id,
                BambuPrintJob.materials.any(BambuJobMaterial.filament_id == filament_id),
            ))
        if project_id:
            base_q = base_q.filter(BambuPrintJob.project_id == project_id)
        if search:
            base_q = base_q.filter(BambuPrintJob.model_name.ilike(f'%{search}%'))
        if date_from:
            try:
                df = datetime.strptime(date_from, '%Y-%m-%d')
                base_q = base_q.filter(BambuPrintJob.started_at >= df)
            except (ValueError, OverflowError):
                flash(translate('bambu_invalid_date_filter'), 'warning')
        if date_to:
            try:
                dt = datetime.strptime(date_to, '%Y-%m-%d')
                dt_end = dt.replace(hour=23, minute=59, second=59)
                base_q = base_q.filter(BambuPrintJob.started_at <= dt_end)
            except (ValueError, OverflowError):
                flash(translate('bambu_invalid_date_filter'), 'warning')
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

        bambu_payload_meta = {}
        slot_meta_by_material = {}
        bi_data = {}
        for job in jobs.items:
            job_meta, slot_meta = _extract_job_meta(job)
            job_meta['cleaned_title'] = clean_bambu_title(job.model_name or '') if job.model_name else ''
            bambu_payload_meta[job.id] = job_meta
            slot_meta_by_material.update(slot_meta)
            js_single_slot = job.materials[0] if len(job.materials) == 1 else None
            js_slot_meta = slot_meta_by_material.get(js_single_slot.id) if js_single_slot else None
            bi_data[str(job.id)] = {
                'fId': job.filament_id,
                'fLabel': job.filament.name if job.filament else None,
                'pId': job.project_id,
                'pLabel': job.project.name if job.project else None,
                'prefMaterial': (js_slot_meta.get('material_type', '') if js_slot_meta else '') or
                                (js_single_slot.material_name if js_single_slot else ''),
                'prefColor': (js_slot_meta.get('color_hex', '') if js_slot_meta else '') or
                             (js_single_slot.color_hex if js_single_slot else ''),
                'cleanedTitle': job_meta.get('cleaned_title', ''),
            }

        html = render_template(
            '_bambu_job_cards.html',
            jobs=jobs,
            bambu_payload_meta=bambu_payload_meta,
            slot_meta_by_material=slot_meta_by_material,
            job_filter=job_filter,
        )
        return jsonify({
            'html': html,
            'bi_data': bi_data,
            'has_next': jobs.has_next,
            'next_page': jobs.next_num,
            'count': len(jobs.items),
            'total': jobs.total,
            'page': jobs.page,
        })

    @bp.route('/bambu/sync', methods=['POST'])
    def bambu_sync():
        setting = get_settings()
        if not setting or not setting.bambu_token:
            return jsonify({'ok': False, 'error': translate('bambu_no_token')}), 400
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
        safe_commit()
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
                            safe_commit()
                        except Exception:
                            db.session.rollback()
                            _LOG.warning('Failed to persist fresh cover URL for job %d', job_id)
                        return _send_inline_thumbnail(recached)
            except Exception:
                _LOG.warning('Bambu thumbnail fresh-fetch failed for job %d', job_id)

        return _thumbnail_placeholder_response()

    @bp.route('/bambu/job/<int:job_id>/map', methods=['POST'])
    def bambu_job_map(job_id):
        """Manually map filament + project to a job; optionally deduct stock."""
        is_ajax = request.args.get('ajax') == '1'
        job = db.session.get(BambuPrintJob, job_id)
        if not job:
            if is_ajax:
                return jsonify({'ok': False, 'error': translate('error_job_not_found')}), 404
            return redirect(url_for('bambu_jobs'))

        filament_id = request.form.get('filament_id', type=int)
        project_id = request.form.get('project_id', type=int)
        deduct_now = request.form.get('deduct') == '1'

        model_name_input = request.form.get('model_name', '').strip()
        if model_name_input:
            job.model_name = model_name_input

        single_slot = job.materials[0] if len(job.materials) == 1 else None
        old_filament_id = job.filament_id
        if filament_id:
            job.filament_id = filament_id
            if single_slot:
                single_slot.filament_id = filament_id
        project_raw = request.form.get('project_id', '').strip()
        if project_raw == '':
            job.project_id = None
        elif project_id:
            job.project_id = project_id

        job_label = job.model_name or job.external_id or str(job.id)

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
                        note=translate('movement_note_bambu_job').format(label=job_label),
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
                        project_obj = db.session.get(Project, effective_project_id)
                        if project_obj:
                            project_obj.mark_planned_filament_used(filament_id)

        elif (
            job.deducted
            and filament_id
            and old_filament_id
            and filament_id != old_filament_id
            and job.weight_grams
            and job.weight_grams > 0
        ):
            # Job was already deducted but a different filament is being assigned
            # → restore stock to the old filament and deduct from the new one.
            old_filament = db.session.get(Filament, old_filament_id)
            new_filament = db.session.get(Filament, filament_id)
            if old_filament:
                old_filament.weight_remaining = old_filament.weight_remaining + job.weight_grams
                if old_filament.weight_total > 0:
                    expected_qty = math.ceil(old_filament.weight_remaining / old_filament.weight_total)
                    if expected_qty > old_filament.quantity:
                        old_filament.quantity = expected_qty
                log_movement(
                    old_filament,
                    'add',
                    job.weight_grams,
                    project_id=project_id or job.project_id,
                    bambu_job_id=job.id,
                    note=translate('movement_note_bambu_remap_return').format(label=job_label),
                )
            if new_filament:
                actual_amount = deduct_filament_stock(new_filament, job.weight_grams)
                if actual_amount > 0:
                    log_movement(
                        new_filament,
                        'bambu_print',
                        actual_amount,
                        project_id=project_id or job.project_id,
                        bambu_job_id=job.id,
                        note=translate('movement_note_bambu_remap').format(label=job_label),
                    )
            if single_slot:
                single_slot.deducted = True

        safe_commit()
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
                return jsonify({'ok': False, 'error': translate('error_job_not_found')}), 404
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
                        note=translate('movement_note_bambu_slot').format(label=job.model_name or job.external_id),
                    )
                    slot.deducted = True
                    actually_deducted = True
                    # Propagate to the linked project if any
                    if job.project:
                        job.project.mark_planned_filament_used(filament_id)

        safe_commit()

        if is_ajax:
            return jsonify({
                'ok': True,
                'filament_id': filament_id,
                'filament_name': filament_name,
                'deducted': actually_deducted,
            })
        return redirect(url_for('bambu_jobs'))

    @bp.route('/bambu/job/<int:job_id>/remap-slot', methods=['POST'])
    def bambu_job_remap_slot(job_id):
        """Reassign an AMS slot to a different filament with a full stock correction.

        When the slot was already deducted the old filament's stock is restored
        and the new filament is deducted by the same weight — keeping the
        inventory consistent.  No correction is made for slots that were never
        deducted (only the FK is updated).
        """
        is_ajax = request.args.get('ajax') == '1'
        job = db.session.get(BambuPrintJob, job_id)
        if not job:
            if is_ajax:
                return jsonify({'ok': False, 'error': translate('error_job_not_found')}), 404
            return redirect(url_for('bambu_jobs'))

        slot_id = request.form.get('slot_id', type=int)
        filament_id = request.form.get('filament_id', type=int)
        slot = db.session.get(BambuJobMaterial, slot_id) if slot_id else None

        filament_name = None
        if slot and slot.job_id == job_id and filament_id:
            old_filament_id = slot.filament_id
            weight = slot.weight_grams or 0.0
            job_label = job.model_name or job.external_id or str(job.id)

            # --- Stock correction when the slot was already deducted ---
            if slot.deducted and old_filament_id and old_filament_id != filament_id and weight > 0:
                old_filament = db.session.get(Filament, old_filament_id)
                new_filament = db.session.get(Filament, filament_id)
                if old_filament:
                    # Restore stock to old filament
                    old_filament.weight_remaining = old_filament.weight_remaining + weight
                    if old_filament.weight_total > 0:
                        expected_qty = math.ceil(old_filament.weight_remaining / old_filament.weight_total)
                        if expected_qty > old_filament.quantity:
                            old_filament.quantity = expected_qty
                    log_movement(
                        old_filament,
                        'add',
                        weight,
                        project_id=job.project_id,
                        bambu_job_id=job.id,
                        note=translate('movement_note_bambu_remap_return').format(label=job_label),
                    )
                if new_filament:
                    actual = deduct_filament_stock(new_filament, weight)
                    if actual > 0:
                        log_movement(
                            new_filament,
                            'bambu_print',
                            actual,
                            project_id=job.project_id,
                            bambu_job_id=job.id,
                            note=translate('movement_note_bambu_remap').format(label=job_label),
                        )

            # Update the FK on the slot
            slot.filament_id = filament_id
            new_filament_obj = db.session.get(Filament, filament_id)
            filament_name = new_filament_obj.name if new_filament_obj else None

            # For single-slot jobs also sync the top-level filament_id
            materials = list(job.materials)
            if len(materials) == 1:
                job.filament_id = filament_id

        safe_commit()

        if is_ajax:
            return jsonify({'ok': True, 'filament_id': filament_id, 'filament_name': filament_name})
        return redirect(url_for('bambu_jobs'))

    @bp.route('/bambu/job/<int:job_id>/duplicate', methods=['POST'])
    def bambu_job_duplicate(job_id):
        """Create a manual duplicate of an existing Bambu print job.

        Used when a print was repeated directly on the printer (not via the
        cloud queue) and therefore never appeared in the sync feed.  The new
        record is marked as not-deducted so the user can assign filament and
        deduct stock independently.
        """
        job = db.session.get(BambuPrintJob, job_id)
        if not job:
            return jsonify({'ok': False, 'error': translate('error_job_not_found')}), 404

        now = utc_now()
        import uuid
        new_external_id = f"manual-dup-{job.external_id}-{uuid.uuid4().hex[:8]}"

        new_job = BambuPrintJob(
            external_id=new_external_id,
            printer_name=job.printer_name,
            printer_model=job.printer_model,
            device_id=job.device_id,
            model_name=job.model_name,
            status='FINISH',
            started_at=now,
            finished_at=now,
            weight_grams=job.weight_grams,
            cost_time=job.cost_time,
            raw_payload=job.raw_payload,
            project_id=job.project_id,
            filament_id=job.filament_id,
            deducted=False,
            synced_at=now,
        )
        db.session.add(new_job)
        db.session.flush()

        # Copy material slots — reset deducted flag so user can deduct again
        for mat in job.materials:
            new_mat = BambuJobMaterial(
                job_id=new_job.id,
                ams_id=mat.ams_id,
                tray_id=mat.tray_id,
                color_hex=mat.color_hex,
                material_name=mat.material_name,
                weight_grams=mat.weight_grams,
                filament_id=mat.filament_id,
                deducted=False,
            )
            db.session.add(new_mat)

        safe_commit()
        return jsonify({'ok': True, 'new_job_id': new_job.id, 'message': translate('bambu_duplicate_success')})

    @bp.route('/bambu/job/<int:job_id>/delete', methods=['POST'])
    def bambu_job_delete(job_id):
        job = db.session.get(BambuPrintJob, job_id)
        if not job:
            return jsonify({'ok': False, 'error': translate('error_job_not_found')}), 404
        db.session.delete(job)
        safe_commit()
        return redirect(url_for('bambu_jobs'))

    @bp.route('/bambu/job/<int:job_id>/create_project', methods=['POST'])
    def bambu_create_project(job_id):
        """Create a new project from a Bambu job title and link it to the job."""
        from models import Project
        from auth import get_current_user
        user = get_current_user()
        job = db.session.get(BambuPrintJob, job_id)
        if not job:
            return jsonify({'ok': False, 'error': translate('error_job_not_found')}), 404
        project_name = request.form.get('project_name', '').strip()
        if not project_name:
            return jsonify({'ok': False, 'error': translate('bambu_name_required')}), 400
        project = Project(
            name=project_name,
            created_by_user_id=user.id if user else None,
            status='APPROVED',
        )
        db.session.add(project)
        db.session.flush()
        job.project_id = project.id
        safe_commit()
        return jsonify({'ok': True, 'project_id': project.id, 'project_name': project.name})

    @bp.route('/bambu/auto-map-history', methods=['POST'])
    def bambu_auto_map_history():
        """Trigger history-based auto-mapping on all unmapped Bambu jobs.

        Finds every BambuPrintJob that has unmapped material slots and a
        non-empty model_name, then attempts to copy filament assignments from
        the most recent previously-mapped job with the same model_name.
        """
        total_mapped = 0
        # Get all jobs that have at least one unmapped slot and have a model_name
        unmapped_jobs = (
            BambuPrintJob.query
            .filter(
                BambuPrintJob.model_name.is_not(None),
                BambuPrintJob.model_name != '',
                BambuPrintJob.materials.any(BambuJobMaterial.filament_id.is_(None)),
            )
            .all()
        )

        for job in unmapped_jobs:
            count = _auto_map_from_history(job)
            if count:
                total_mapped += count

        if total_mapped:
            try:
                safe_commit()
                invalidate_kpi_cache()
            except Exception:
                db.session.rollback()
                _LOG.warning('History auto-map commit error')
                return jsonify({'ok': False, 'error': translate('error_commit_failed')}), 500

        return jsonify({'ok': True, 'mapped': total_mapped, 'jobs_scanned': len(unmapped_jobs)})

    app.register_blueprint(bp)
