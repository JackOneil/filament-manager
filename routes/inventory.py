"""Inventory routes: listing, CRUD, spool management, and filament detail."""
import json
import math
import os
from collections import Counter
from datetime import datetime, timedelta
from types import SimpleNamespace

from flask import abort, flash, jsonify, render_template, request, redirect, session, url_for, Blueprint
from sqlalchemy import func, select, text
from sqlalchemy.orm import joinedload

from database import db
from auth import get_current_user, is_admin, safe_redirect_target
from models import AppSetting, PrusaPrinter, BambuJobMaterial, BambuPrintJob, BambuPrinter, PrusaPrintJob, Brand, Color, Filament, Material, MovementHistory, Notification, PrinterMaintenance, Project, ProjectComment, ProjectFilament, ProjectQuote, FilamentUndoLog, WasteRecord
from utils import (
    build_action_center,
    build_filament_history_name as _display_filament_name,
    collect_activity_heatmap,
    collect_sparkline_data,
    compute_stock_status,
    consume_undo_log,
    create_bulk_undo_snapshot,
    create_undo_snapshot,
    deduct_filament_stock,
    escape_like,
    format_tags,
    generate_sparkline_svg_path,
    get_filament_tags,
    get_live_printers,
    log_movement,
    mark_undo_consumed,
    movement_action_label,
    normalize_shop_url,
    parse_tags,
    restore_filament_from_snapshot,
    restore_bulk_from_snapshot,
    safe_commit,
    translate,
    utc_now,
)



from routes.inventory_helpers import (
    _build_filament_query,
    _apply_inventory_filters,
    _decorate_filament,
    _inventory_stats,
    _low_stock_filaments,
    _overview_focus,
    _inventory_page_context,
    _selected_filaments,
    _require_inventory_admin,
    _serialize_filament_snapshot,
    _build_filament_restore_bundle,
    _restore_filament_snapshot,
    _restore_project_relations,
    _user_dashboard_context,
    _UNDO_SESSION_KEY,
)

def register(app):
    bp = Blueprint('inventory', __name__)

    @bp.route('/')
    def index():
        user = get_current_user()
        if user and not is_admin(user):
            return render_template(
                'overview_user.html',
                user_dashboard=_user_dashboard_context(user),
            )
        action_center = build_action_center()
        live_printers = get_live_printers()
        from models import AppSetting, PrusaPrinter, BambuPrinter
        app_settings = AppSetting.query.first()
        has_filament = Filament.query.first() is not None
        has_printer = (BambuPrinter.query.first() is not None or
                       PrusaPrinter.query.first() is not None)
        show_onboarding = (
            app_settings and not app_settings.onboarding_dismissed and
            not (has_filament and has_printer and
                 app_settings.currency and app_settings.kwh_price)
        )
        onboarding_steps = {
            'currency': bool(app_settings and app_settings.currency not in (None, 'CZK')),
            'energy': bool(app_settings and app_settings.kwh_price and app_settings.printer_power),
            'printer': has_printer,
            'filament': has_filament,
        }
        return render_template(
            'overview.html',
            stats=_inventory_stats(),
            action_center=action_center,
            live_printers=live_printers,
            overview_focus=_overview_focus(action_center, live_printers),
            low_stock_filaments=_low_stock_filaments(app_settings),
            app_settings=app_settings,
            today=utc_now().date(),
            show_onboarding=show_onboarding,
            onboarding_steps=onboarding_steps,
            activity_heatmap=collect_activity_heatmap(),
        )

    @bp.route('/filaments')
    def filaments_index():
        user = get_current_user()
        inventory_read_only = bool(user and not is_admin(user))
        context = _inventory_page_context()
        if inventory_read_only:
            return render_template('index_user.html', **context)
        return render_template('index.html', inventory_read_only=False, **context)

    @bp.route('/filament/<int:id>')
    def filament_detail(id):
        _require_inventory_admin()
        from utils import collect_usage_windows

        filament = db.first_or_404(_build_filament_query().where(Filament.id == id))
        usage_map = collect_usage_windows([filament])
        sparkline_data = collect_sparkline_data([filament])
        _decorate_filament(filament, usage_map, sparkline_data)

        timeline_page = request.args.get('timeline_page', 1, type=int)
        jobs_page = request.args.get('jobs_page', 1, type=int)
        detail_per_page = 10

        timeline_rows = select(MovementHistory).options(
            joinedload(MovementHistory.project),
            joinedload(MovementHistory.bambu_job),
        ).where(
            db.or_(MovementHistory.filament_id == filament.id, MovementHistory.filament_name == _display_filament_name(filament))
        ).order_by(MovementHistory.created_at.desc())
        timeline_paginated = db.paginate(timeline_rows, page=timeline_page, per_page=detail_per_page, error_out=False)

        timeline = [{
            'created_at': row.created_at,
            'action_type': row.action_type,
            'action_label': movement_action_label(row.action_type),
            'weight': row.weight,
            'note': row.note,
            'project': row.project,
            'bambu_job': row.bambu_job,
        } for row in timeline_paginated.items]

        related_project_rows = ProjectFilament.query.options(
            joinedload(ProjectFilament.project),
        ).filter(ProjectFilament.filament_id == filament.id).order_by(ProjectFilament.id.desc()).limit(20).all()
        related_jobs_query = select(BambuPrintJob).options(
            joinedload(BambuPrintJob.materials),
        ).where(
            db.or_(
                BambuPrintJob.filament_id == filament.id,
                BambuPrintJob.materials.any(BambuJobMaterial.filament_id == filament.id),
            )
        ).order_by(BambuPrintJob.started_at.desc().nullslast())
        related_jobs_paginated = db.paginate(related_jobs_query, page=jobs_page, per_page=detail_per_page, error_out=False)

        m = filament.stock_metrics
        daily_usage = m['usage_30'] / 30.0 if m['usage_30'] > 0 else 0.0
        detail_days_left = round(m['remaining'] / daily_usage) if daily_usage > 0 else None

        # ── Monthly consumption chart (last 6 months) ────────────────────────
        now = utc_now()
        chart_labels = []
        chart_data = []
        for i in range(5, -1, -1):
            month_start = (now.replace(day=1) - timedelta(days=i * 28)).replace(day=1)
            if i > 0:
                next_month_start = (month_start + timedelta(days=32)).replace(day=1)
            else:
                next_month_start = now + timedelta(days=1)
            consumed = db.session.query(func.sum(MovementHistory.weight)).filter(
                db.or_(
                    MovementHistory.filament_id == filament.id,
                    MovementHistory.filament_name == _display_filament_name(filament),
                ),
                MovementHistory.action_type.in_(['remove', 'bambu_print', 'prusa_print', 'bulk_delete']),
                MovementHistory.created_at >= month_start,
                MovementHistory.created_at < next_month_start,
            ).scalar() or 0.0
            chart_labels.append(month_start.strftime('%b %Y'))
            chart_data.append(round(consumed, 1))

        from utils import get_settings
        app_settings = get_settings()

        return render_template(
            'filament_detail.html',
            filament=filament,
            timeline=timeline,
            timeline_paginated=timeline_paginated,
            related_project_rows=related_project_rows,
            related_jobs=related_jobs_paginated.items,
            related_jobs_paginated=related_jobs_paginated,
            formatted_tags=format_tags(filament.tag_text),
            detail_days_left=detail_days_left,
            app_settings=app_settings,
            chart_labels=chart_labels,
            chart_data=chart_data,
        )

    @bp.route('/filament/<int:id>/meta', methods=['POST'])
    def filament_update_meta(id):
        _require_inventory_admin()
        filament = db.get_or_404(Filament, id)
        filament.tag_text = format_tags(request.form.get('tag_text', ''))
        filament.min_stock_grams = max(request.form.get('min_stock_grams', 0.0, type=float) or 0.0, 0.0)
        filament.max_stock_grams = max(request.form.get('max_stock_grams', 0.0, type=float) or 0.0, 0.0)
        filament.recommended_nozzle_temp = request.form.get('recommended_nozzle_temp', type=int)
        filament.recommended_bed_temp = request.form.get('recommended_bed_temp', type=int)
        filament.quality_stringing = request.form.get('quality_stringing', '').strip() or None
        filament.quality_adhesion = request.form.get('quality_adhesion', '').strip() or None
        filament.quality_drying = request.form.get('quality_drying', '').strip() or None
        filament.quality_profile = request.form.get('quality_profile', '').strip() or None
        filament.quality_notes = request.form.get('quality_notes', '').strip() or None
        safe_commit()
        return redirect(url_for('filament_detail', id=filament.id))

    @bp.route('/filament/<int:id>/toggle-reorder-snooze', methods=['POST'])
    def filament_toggle_reorder_snooze(id):
        _require_inventory_admin()
        filament = db.get_or_404(Filament, id)
        filament.reorder_alert_snoozed = not bool(filament.reorder_alert_snoozed)
        safe_commit()
        return redirect(safe_redirect_target(request.referrer, 'filament_detail', id=filament.id))

    @bp.route('/inventory/bulk', methods=['POST'])
    def inventory_bulk():
        _require_inventory_admin()
        # Only the delete action is supported from the UI; validate explicitly
        # so an unexpected action never silently deletes filaments.
        action = request.form.get('action', '')
        if action != 'bulk_delete_selected':
            return redirect(url_for('filaments_index'))

        selected = _selected_filaments()
        if not selected:
            return redirect(url_for('filaments_index'))

        undo_entries = [_build_filament_restore_bundle(filament) for filament in selected]

        # Create DB-backed undo snapshot BEFORE deleting filaments
        # so FK constraints on filament_undo_log.filament_id are satisfied.
        user = get_current_user()
        if user:
            undo_log = create_bulk_undo_snapshot(user.id, undo_entries)
            session[_UNDO_SESSION_KEY] = {
                'undo_log_id': undo_log.id,
                'title_key': 'undo_toast_bulk_delete_title',
                'detail': translate('undo_toast_bulk_delete_detail').format(count=len(undo_entries)),
                'expires_at': undo_log.expires_at.isoformat(timespec='seconds'),
            }

        selected_ids = [f.id for f in selected]
        ProjectFilament.query.filter(ProjectFilament.filament_id.in_(selected_ids)).delete(synchronize_session=False)
        ProjectQuote.query.filter(ProjectQuote.filament_id.in_(selected_ids)).update({'filament_id': None}, synchronize_session=False)
        for filament in selected:
            log_movement(filament, 'bulk_delete', filament.weight_remaining, note=translate('movement_note_bulk_delete'))
            db.session.delete(filament)

        safe_commit()
        return redirect(url_for('filaments_index'))

    @bp.route('/add', methods=['GET', 'POST'])
    def add():
        _require_inventory_admin()
        if request.method == 'POST':
            name = request.form.get('name', '').strip()
            try:
                brand_id = request.form.get('brand_id', type=int)
                color_id = request.form.get('color_id', type=int)
                material_id = request.form.get('material_id', type=int)
                weight_total = request.form.get('weight_total', type=float)
                quantity = request.form.get('quantity', 1, type=int) or 1
                price = request.form.get('price', type=float)
                if brand_id is None or color_id is None or material_id is None or weight_total is None or price is None:
                    return redirect(url_for('add'))
                if weight_total <= 0 or price < 0 or quantity < 1:
                    return redirect(url_for('add'))
                weight_remaining = float(
                    request.form.get('weight_remaining') or weight_total * quantity
                )
                weight_remaining = max(0.0, weight_remaining)
            except (TypeError, ValueError):
                return redirect(url_for('add'))
            min_stock_grams = max(request.form.get('min_stock_grams', 0.0, type=float) or 0.0, 0.0)
            max_stock_grams = max(request.form.get('max_stock_grams', 0.0, type=float) or 0.0, 0.0)
            tag_text = format_tags(request.form.get('tag_text', ''))

            if not name:
                brand = db.session.get(Brand, brand_id)
                material = db.session.get(Material, material_id)
                color = db.session.get(Color, color_id)
                if not (brand and material and color):
                    flash('inventory_invalid_reference', 'error')
                    return redirect(url_for('add'))
                name = f"{brand.name} {material.name} {color.name}"

            new_fil = Filament(
                name=name,
                brand_id=brand_id,
                color_id=color_id,
                material_id=material_id,
                weight_total=weight_total,
                weight_remaining=weight_remaining,
                price=price,
                quantity=quantity,
                min_stock_grams=min_stock_grams,
                max_stock_grams=max_stock_grams,
                tag_text=tag_text,
            )
            db.session.add(new_fil)
            db.session.flush()
            log_movement(new_fil, 'add', weight_remaining, note=translate('movement_note_initial_stock'))
            safe_commit()
            return redirect(url_for('filaments_index'))

        brands = Brand.query.order_by(Brand.name).all()
        colors = Color.query.order_by(Color.name).all()
        materials = Material.query.order_by(Material.name).all()
        return render_template('add.html', brands=brands, colors=colors, materials=materials)

    @bp.route('/edit/<int:id>', methods=['GET', 'POST'])
    def edit(id):
        _require_inventory_admin()
        filament = db.get_or_404(Filament, id)
        if request.method == 'POST':
            old_weight = filament.weight_remaining
            # Parse ALL form values first — never mutate the ORM object until
            # every conversion succeeded. Otherwise a failed parse leaves the
            # session dirty and the partial change gets committed by the next
            # request (dirty-session leak across requests).
            try:
                new_name = request.form.get('name', filament.name) or filament.name
                new_weight = float(request.form.get('weight_remaining', filament.weight_remaining))
                new_price = float(request.form.get('price', filament.price))
                new_quantity = int(request.form.get('quantity', filament.quantity))
            except (TypeError, ValueError):
                db.session.rollback()
                return redirect(url_for('edit', id=id))

            filament.name = new_name
            filament.weight_remaining = max(0.0, new_weight)
            filament.price = max(0.0, new_price)
            filament.quantity = max(0, int(new_quantity))
            filament.tag_text = format_tags(request.form.get('tag_text', filament.tag_text or ''))
            filament.min_stock_grams = max(request.form.get('min_stock_grams', filament.min_stock_grams, type=float) or 0.0, 0.0)
            filament.max_stock_grams = max(request.form.get('max_stock_grams', filament.max_stock_grams, type=float) or 0.0, 0.0)
            filament.shop_url = normalize_shop_url(request.form.get('shop_url'))

            weight_diff = filament.weight_remaining - old_weight
            if weight_diff > 0:
                log_movement(filament, 'add', weight_diff, note=translate('movement_note_manual_edit'))
            elif weight_diff < 0:
                log_movement(filament, 'remove', abs(weight_diff), note=translate('movement_note_manual_edit'))

            safe_commit()
            return redirect(url_for('filaments_index'))

        return render_template('edit.html', filament=filament, formatted_tags=format_tags(filament.tag_text))

    @bp.route('/use/<int:id>', methods=['POST'])
    def use_filament(id):
        _require_inventory_admin()
        try:
            amount = float(request.form.get('amount', 0) or 0)
        except (TypeError, ValueError):
            amount = 0.0
        if amount <= 0:
            return redirect(url_for('filaments_index'))
        filament = db.get_or_404(Filament, id)
        actual_amount = deduct_filament_stock(filament, amount)
        log_movement(filament, 'remove', actual_amount, note=translate('movement_note_manual_usage'))
        safe_commit()
        return redirect(url_for('filaments_index'))

    @bp.route('/add_spool/<int:id>', methods=['POST'])
    def add_spool(id):
        _require_inventory_admin()
        try:
            spool_count = request.form.get('quantity', 1, type=int) or 1
        except (TypeError, ValueError):
            spool_count = 1
        spool_count = max(spool_count, 1)

        filament = db.get_or_404(Filament, id)
        added_weight = filament.weight_total * spool_count
        filament.quantity += spool_count
        filament.weight_remaining += added_weight
        log_movement(
            filament,
            'add',
            added_weight,
            note=translate('movement_note_added_spools').format(count=spool_count),
        )
        safe_commit()
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.accept_mimetypes.best == 'application/json':
            return jsonify({
                'ok': True,
                'filament_id': filament.id,
                'quantity': filament.quantity,
                'weight_remaining': filament.weight_remaining,
                'added_spools': spool_count,
                'added_weight': added_weight,
            })
        return redirect(url_for('filaments_index'))

    @bp.route('/remove_spool/<int:id>', methods=['POST'])
    def remove_spool(id):
        _require_inventory_admin()
        filament = db.get_or_404(Filament, id)
        removed_weight = 0.0
        if filament.quantity > 0 and filament.weight_total > 0:
            # Atomically decrement quantity AND weight (compare-and-swap) so
            # concurrent requests cannot double-decrement or lose an update.
            for _attempt in range(5):
                old_qty = int(filament.quantity or 0)
                old_weight = float(filament.weight_remaining or 0.0)
                if old_qty <= 0:
                    break
                new_weight = max(0.0, old_weight - float(filament.weight_total))
                result = db.session.execute(
                    text(
                        "UPDATE filament SET quantity = quantity - 1, "
                        "weight_remaining = :new "
                        "WHERE id = :fid AND quantity > 0 AND weight_remaining = :old"
                    ),
                    {'new': new_weight, 'fid': filament.id, 'old': old_weight},
                )
                if result.rowcount == 1:
                    actual_amount = old_weight - new_weight
                    filament.quantity = old_qty - 1
                    filament.weight_remaining = new_weight
                    log_movement(filament, 'remove', actual_amount, note=translate('movement_note_removed_spool'))
                    removed_weight = actual_amount
                    break
                # Contention — re-read the committed row and retry.
                row = db.session.execute(
                    text("SELECT quantity, weight_remaining FROM filament WHERE id = :fid"),
                    {'fid': filament.id},
                ).fetchone()
                if row is None:
                    break
                filament.quantity = int(row[0])
                filament.weight_remaining = float(row[1])
        safe_commit()
        if removed_weight > 0:
            # Create DB-backed undo snapshot
            user = get_current_user()
            if user:
                undo_log = create_undo_snapshot(
                    user_id=user.id,
                    action_type='remove_spool',
                    filament=filament,
                    restore_quantity=1,
                    restore_weight=removed_weight,
                )
                session[_UNDO_SESSION_KEY] = {
                    'undo_log_id': undo_log.id,
                    'title_key': 'undo_toast_remove_spool_title',
                    'detail': filament.name,
                    'expires_at': undo_log.expires_at.isoformat(timespec='seconds'),
                }
        return redirect(url_for('filaments_index'))

    @bp.route('/delete/<int:id>', methods=['POST'])
    def delete(id):
        _require_inventory_admin()
        filament = db.get_or_404(Filament, id)
        undo_entry = _build_filament_restore_bundle(filament)
        log_movement(filament, 'remove', filament.weight_remaining, note=translate('movement_note_deleted_filament'))
        ProjectFilament.query.filter_by(filament_id=filament.id).delete()
        ProjectQuote.query.filter_by(filament_id=filament.id).update({'filament_id': None})

        # Create DB-backed undo snapshot BEFORE deleting the filament
        # so the FK constraint on filament_undo_log.filament_id is satisfied.
        user = get_current_user()
        if user:
            undo_log = create_undo_snapshot(
                user_id=user.id,
                action_type='delete_filament',
                filament=filament,
                project_filaments=[
                    type('obj', (object,), pf)() for pf in undo_entry.get('project_filaments', [])
                ] if undo_entry.get('project_filaments') else None,
                project_quote_ids=undo_entry.get('project_quote_ids', []),
            )
            session[_UNDO_SESSION_KEY] = {
                'undo_log_id': undo_log.id,
                'title_key': 'undo_toast_delete_title',
                'detail': undo_entry['filament']['name'],
                'expires_at': undo_log.expires_at.isoformat(timespec='seconds'),
            }

        db.session.delete(filament)
        safe_commit()
        return redirect(url_for('filaments_index'))

    @bp.route('/inventory/undo', methods=['POST'])
    def inventory_undo():
        _require_inventory_admin()
        pending = session.get(_UNDO_SESSION_KEY) or {}
        undo_log_id = request.form.get('undo_log_id', type=int)
        user = get_current_user()
        user_id = user.id if user else None

        if not undo_log_id or undo_log_id != pending.get('undo_log_id'):
            flash('undo_toast_not_available', 'error')
            session.pop(_UNDO_SESSION_KEY, None)
            return redirect(safe_redirect_target(request.referrer, 'filaments_index'))

        # Fetch snapshot data (the log row is only marked consumed AFTER the
        # restore succeeds, so a failed undo can be retried).
        snapshot_data = consume_undo_log(undo_log_id, user_id)
        session.pop(_UNDO_SESSION_KEY, None)
        
        if not snapshot_data:
            flash('undo_toast_not_available', 'error')
            return redirect(safe_redirect_target(request.referrer, 'filaments_index'))

        try:
            action_type = snapshot_data.get('action_type') or snapshot_data.get('type')
            
            if action_type == 'remove_spool':
                # The snapshot stores the filament under the 'filament' key
                # (with 'id' inside); fall back to a legacy top-level key.
                filament_id = (
                    (snapshot_data.get('filament') or {}).get('id')
                    or snapshot_data.get('filament_id')
                )
                filament = db.session.get(Filament, filament_id)
                if filament is None:
                    raise ValueError('filament_not_found')
                restore_quantity = int(snapshot_data.get('restore_quantity', 1) or 1)
                restore_weight = float(snapshot_data.get('restore_weight', 0.0) or 0.0)
                filament.quantity = int(filament.quantity or 0) + max(restore_quantity, 0)
                filament.weight_remaining = float(filament.weight_remaining or 0.0) + max(restore_weight, 0.0)
                log_movement(
                    filament,
                    'add',
                    max(restore_weight, 0.0),
                    note=translate('movement_note_undo_remove_spool'),
                )
                safe_commit()

            elif action_type == 'delete_filament':
                # Use the DB-backed restore function
                filament = restore_filament_from_snapshot(snapshot_data)
                log_movement(
                    filament,
                    'add',
                    float(filament.weight_remaining or 0.0),
                    note=translate('movement_note_undo_delete'),
                )

            elif action_type == 'bulk_delete':
                entries = snapshot_data.get('entries', [])
                for entry in entries:
                    filament = restore_filament_from_snapshot(entry)
                    log_movement(
                        filament,
                        'add',
                        float(filament.weight_remaining or 0.0),
                        note=translate('movement_note_undo_bulk_delete'),
                    )
            elif action_type in ('delete_waste', 'delete_maintenance'):
                target_key = snapshot_data.get('target_key')
                if not target_key:
                    raise ValueError('missing_target_key')
                if isinstance(target_key, str):
                    target_data = json.loads(target_key)
                else:
                    target_data = target_key

                if action_type == 'delete_waste':
                    # Recreate records will have new created_at; preserve original
                    rec = WasteRecord(
                        filament_id=target_data.get('filament_id'),
                        project_id=target_data.get('project_id'),
                        reason=target_data.get('reason', 'other'),
                        weight_grams=float(target_data.get('weight_grams', 0)),
                        notes=target_data.get('notes'),
                        recorded_by_user_id=target_data.get('recorded_by_user_id'),
                    )
                    if target_data.get('created_at'):
                        try:
                            rec.created_at = datetime.fromisoformat(target_data['created_at'])
                        except (ValueError, TypeError):
                            pass
                    db.session.add(rec)
                    # Re-deduct the wasted grams that waste_delete returned.
                    from routes.waste import _deduct_waste_stock
                    _deduct_waste_stock(
                        target_data.get('filament_id'),
                        float(target_data.get('weight_grams', 0)),
                        target_data.get('project_id'),
                    )
                elif action_type == 'delete_maintenance':
                    rec = PrinterMaintenance(
                        printer_type=target_data.get('printer_type', 'bambu'),
                        printer_id=target_data.get('printer_id'),
                        printer_name=target_data.get('printer_name', ''),
                        maintenance_type=target_data.get('maintenance_type', 'other'),
                        notes=target_data.get('notes'),
                        notes_is_markdown=target_data.get('notes_is_markdown', False),
                        recurrence_type=target_data.get('recurrence_type', 'none'),
                        recurrence_value=int(target_data.get('recurrence_value', 0)),
                        recurrence_enabled=target_data.get('recurrence_enabled', False),
                        predictive_enabled=target_data.get('predictive_enabled', False),
                        predictive_runtime_hours=float(target_data.get('predictive_runtime_hours', 0)),
                        predictive_jobs_count=int(target_data.get('predictive_jobs_count', 0)),
                        predictive_filament_grams=float(target_data.get('predictive_filament_grams', 0)),
                        predictive_window_days=int(target_data.get('predictive_window_days', 30)),
                    )
                    if target_data.get('performed_at'):
                        try:
                            rec.performed_at = datetime.fromisoformat(target_data['performed_at'])
                        except (ValueError, TypeError):
                            pass
                    if target_data.get('next_service_at'):
                        try:
                            rec.next_service_at = datetime.strptime(target_data['next_service_at'], '%Y-%m-%d')
                        except (ValueError, TypeError):
                            pass
                    db.session.add(rec)
            else:
                raise ValueError('unsupported_undo_type')

            safe_commit()
            mark_undo_consumed(undo_log_id, user_id)
            flash('undo_toast_applied', 'success')
        except Exception:
            try:
                db.session.rollback()
            except Exception:
                pass
            app.logger.exception("Undo action failed")
            flash('undo_toast_failed', 'error')

        return redirect(safe_redirect_target(request.referrer, 'filaments_index'))

    # ── Operator / Admin mode toggle ──────────────────────────────────────────

    @bp.route('/toggle-ui-mode', methods=['POST'])
    def toggle_ui_mode():
        from flask import session
        from auth import get_current_user, is_admin
        user = get_current_user()
        if not is_admin(user):
            return redirect(safe_redirect_target(request.referrer, 'index'))
        current = session.get('ui_mode', 'admin')
        session['ui_mode'] = 'operator' if current == 'admin' else 'admin'
        return redirect(safe_redirect_target(request.referrer, 'index'))

    # ── CSV filament import ───────────────────────────────────────────────────

    @bp.route('/filaments/import-csv', methods=['GET', 'POST'])
    def filament_import_csv():
        import csv
        import io
        _require_inventory_admin()
        from utils import translate

        REQUIRED_COLS = {'name', 'brand', 'material', 'color', 'weight_total', 'price'}
        COL_ALIASES = {
            'name': ['name', 'název', 'nazev'],
            'brand': ['brand', 'značka', 'znacka', 'výrobce', 'vyrobce'],
            'material': ['material', 'materiál'],
            'color': ['color', 'barva', 'colour'],
            'weight_total': ['weight_total', 'weight total', 'celková váha', 'celkova vaha', 'weight total (g)', 'celková váha (g)'],
            'weight_remaining': ['weight_remaining', 'weight remaining', 'zbývající váha', 'zbyvajici vaha', 'weight remaining (g)', 'zbývající váha (g)'],
            'price': ['price', 'cena'],
            'quantity': ['quantity', 'počet', 'pocet', 'qty'],
            'nozzle_temp': ['nozzle_temp', 'nozzle temp', 'teplota trysky'],
            'bed_temp': ['bed_temp', 'bed temp', 'teplota podložky', 'teplota podlozky'],
            'min_stock_grams': ['min_stock_grams', 'min stock', 'min stock (g)', 'minimum zásoby', 'minimum zasoby'],
            'max_stock_grams': ['max_stock_grams', 'max stock', 'max stock (g)', 'maximum zásoby', 'maximum zasoby'],
            'tags': ['tags', 'tagy', 'štítky', 'stitky'],
            'shop_url': ['shop_url', 'shop url', 'url eshopu', 'e-shop url', 'link'],
            'quality_drying': ['quality_drying', 'drying', 'sušení', 'suseni'],
            'quality_stringing': ['quality_stringing', 'stringing', 'stringing hodnocení'],
            'quality_adhesion': ['quality_adhesion', 'adhesion', 'přilnavost', 'prilnavost'],
            'quality_profile': ['quality_profile', 'profile', 'print profile', 'tiskový profil'],
            'quality_notes': ['quality_notes', 'notes', 'poznámky', 'poznamky'],
        }

        def _norm_header(h):
            return h.strip().lower()

        def _map_headers(headers):
            """Return dict {canonical_key: col_index} from raw headers."""
            norm = [_norm_header(h) for h in headers]
            mapping = {}
            for key, aliases in COL_ALIASES.items():
                for i, h in enumerate(norm):
                    if h in aliases:
                        mapping[key] = i
                        break
            return mapping

        if request.method == 'GET':
            if request.args.get('template') == '1':
                import flask
                CSV_TEMPLATE_HEADER = 'name,brand,material,color,weight_total,weight_remaining,price,quantity,nozzle_temp,bed_temp,min_stock_grams,max_stock_grams,tags,shop_url,quality_drying,quality_stringing,quality_adhesion,quality_profile,quality_notes\n'
                CSV_TEMPLATE_ROW = 'Example Filament,Bambu,PLA,Red,1000,1000,25.00,1,220,60,100,0,,,,,,\n'
                output = '\ufeff' + CSV_TEMPLATE_HEADER + CSV_TEMPLATE_ROW
                response = flask.make_response(output)
                response.headers['Content-Type'] = 'text/csv; charset=utf-8-sig'
                response.headers['Content-Disposition'] = 'attachment; filename="filament_import_template.csv"'
                return response
            return render_template('filament_import_csv.html', step='upload')

        # POST — could be 'upload' (parse preview) or 'confirm' (do import)
        step = request.form.get('step', 'upload')

        if step == 'upload':
            file = request.files.get('csv_file')
            if not file or file.filename == '':
                return render_template('filament_import_csv.html', step='upload',
                                       error=translate('import_csv_error_no_file'))
            separator = request.form.get('separator', ',')
            try:
                content = file.read().decode('utf-8-sig')
                reader = csv.reader(io.StringIO(content), delimiter=separator)
                rows = list(reader)
            except Exception:
                app.logger.exception("CSV import: failed to read uploaded file")
                return render_template('filament_import_csv.html', step='upload',
                                       error=translate('import_csv_error_bad_format'))
            if len(rows) < 2:
                return render_template('filament_import_csv.html', step='upload',
                                       error=translate('import_csv_error_bad_format'))
            col_map = _map_headers(rows[0])
            missing = REQUIRED_COLS - col_map.keys()
            if missing:
                return render_template('filament_import_csv.html', step='upload',
                                       error=translate('import_csv_error_missing_cols').replace(
                                           '{cols}', ', '.join(sorted(missing))))
            preview_rows = []
            for row in rows[1:]:
                if not any(c.strip() for c in row):
                    continue
                def _get(key, default=''):
                    idx = col_map.get(key)
                    if idx is None or idx >= len(row):
                        return default
                    return row[idx].strip()
                preview_rows.append({
                    'name': _get('name'),
                    'brand': _get('brand'),
                    'material': _get('material'),
                    'color': _get('color'),
                    'weight_total': _get('weight_total'),
                    'weight_remaining': _get('weight_remaining'),
                    'price': _get('price'),
                    'quantity': _get('quantity', '1'),
                    'nozzle_temp': _get('nozzle_temp'),
                    'bed_temp': _get('bed_temp'),
                    'min_stock_grams': _get('min_stock_grams'),
                    'max_stock_grams': _get('max_stock_grams'),
                    'tags': _get('tags'),
                    'shop_url': _get('shop_url'),
                    'quality_drying': _get('quality_drying'),
                    'quality_stringing': _get('quality_stringing'),
                    'quality_adhesion': _get('quality_adhesion'),
                    'quality_profile': _get('quality_profile'),
                    'quality_notes': _get('quality_notes'),
                })
            import json as _json
            csv_payload = _json.dumps({'separator': separator, 'col_map': {k: v for k, v in col_map.items()}, 'rows': preview_rows})
            return render_template('filament_import_csv.html', step='preview',
                                   preview_rows=preview_rows, csv_payload=csv_payload)

        if step == 'confirm':
            import json as _json
            try:
                payload = _json.loads(request.form.get('csv_payload', '{}'))
                rows = payload.get('rows', [])
            except Exception:
                app.logger.exception("CSV import: failed to parse payload JSON")
                return redirect(url_for('filament_import_csv'))
            # The payload is client-supplied — cap the row count so a crafted
            # request cannot bulk-insert an unbounded number of filaments.
            _MAX_CSV_IMPORT_ROWS = 5000
            if len(rows) > _MAX_CSV_IMPORT_ROWS:
                flash('inventory_csv_too_many_rows', 'error')
                return redirect(url_for('filament_import_csv'))
            imported = 0
            for row in rows:
                name = row.get('name', '').strip()
                if not name:
                    continue
                brand_name = row.get('brand', '').strip() or 'Unknown'
                material_name = row.get('material', '').strip() or 'PLA'
                color_name = row.get('color', '').strip() or 'Unknown'
                try:
                    weight_total = math.floor(float(row.get('weight_total') or 0) * 100) / 100
                    weight_remaining_raw = row.get('weight_remaining', '').strip()
                    weight_remaining = math.floor((float(weight_remaining_raw) if weight_remaining_raw else weight_total) * 100) / 100
                    price = math.floor(float(row.get('price') or 0) * 100) / 100
                    quantity = max(int(row.get('quantity') or 1), 1)
                except (TypeError, ValueError):
                    continue
                brand = Brand.query.filter_by(name=brand_name).first()
                if not brand:
                    brand = Brand(name=brand_name)
                    db.session.add(brand)
                    db.session.flush()
                material = Material.query.filter_by(name=material_name).first()
                if not material:
                    material = Material(name=material_name)
                    db.session.add(material)
                    db.session.flush()
                color = Color.query.filter_by(name=color_name).first()
                if not color:
                    color = Color(name=color_name)
                    db.session.add(color)
                    db.session.flush()
                try:
                    nozzle_temp = int(row.get('nozzle_temp') or 0) or None
                    bed_temp = int(row.get('bed_temp') or 0) or None
                except (TypeError, ValueError):
                    nozzle_temp = None
                    bed_temp = None
                try:
                    min_stock = math.floor(float(row.get('min_stock_grams') or 0) * 100) / 100
                    max_stock = math.floor(float(row.get('max_stock_grams') or 0) * 100) / 100
                except (TypeError, ValueError):
                    min_stock = 0.0
                    max_stock = 0.0
                from utils import format_tags
                db.session.add(Filament(
                    name=name,
                    brand_id=brand.id,
                    material_id=material.id,
                    color_id=color.id,
                    weight_total=weight_total,
                    weight_remaining=weight_remaining,
                    price=price,
                    quantity=quantity,
                    recommended_nozzle_temp=nozzle_temp,
                    recommended_bed_temp=bed_temp,
                    min_stock_grams=min_stock,
                    max_stock_grams=max_stock,
                    tag_text=format_tags(row.get('tags', '')) or None,
                    shop_url=normalize_shop_url(row.get('shop_url')),
                    quality_drying=row.get('quality_drying', '').strip() or None,
                    quality_stringing=row.get('quality_stringing', '').strip() or None,
                    quality_adhesion=row.get('quality_adhesion', '').strip() or None,
                    quality_profile=row.get('quality_profile', '').strip() or None,
                    quality_notes=row.get('quality_notes', '').strip() or None,
                ))
                imported += 1
            safe_commit()
            return redirect(url_for('filaments_index',
                                    _anchor='import_ok',
                                    imported=imported))

    # ── CSV filament export ───────────────────────────────────────────────────

    @bp.route('/filaments/export-csv', methods=['GET'])
    def filament_export_csv():
        import flask, io, csv
        _require_inventory_admin()
        filaments = Filament.query.options(joinedload(Filament.brand), joinedload(Filament.material), joinedload(Filament.color)).order_by(Filament.name).all()

        def _floor2(v):
            """Floor a float to 2 decimal places to avoid floating-point noise."""
            if v is None:
                return ''
            return math.floor(float(v) * 100) / 100

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            'name', 'brand', 'material', 'color',
            'weight_total', 'weight_remaining', 'price', 'quantity',
            'nozzle_temp', 'bed_temp',
            'min_stock_grams', 'max_stock_grams',
            'tags', 'shop_url',
            'quality_drying', 'quality_stringing', 'quality_adhesion',
            'quality_profile', 'quality_notes',
        ])
        for f in filaments:
            writer.writerow([
                f.name,
                f.brand.name if f.brand else '',
                f.material.name if f.material else '',
                f.color.name if f.color else '',
                _floor2(f.weight_total),
                _floor2(f.weight_remaining),
                _floor2(f.price),
                f.quantity,
                f.recommended_nozzle_temp or '',
                f.recommended_bed_temp or '',
                _floor2(f.min_stock_grams) if f.min_stock_grams else '',
                _floor2(f.max_stock_grams) if f.max_stock_grams else '',
                f.tag_text or '',
                f.shop_url or '',
                f.quality_drying or '',
                f.quality_stringing or '',
                f.quality_adhesion or '',
                f.quality_profile or '',
                f.quality_notes or '',
            ])
        csv_content = output.getvalue()
        # Prepend UTF-8 BOM so Excel and other tools correctly detect Czech characters
        response = flask.make_response('\ufeff' + csv_content)
        response.headers['Content-Type'] = 'text/csv; charset=utf-8-sig'
        response.headers['Content-Disposition'] = 'attachment; filename="filaments_export.csv"'
        return response

    # ── Community filament database ───────────────────────────────────────────

    @bp.route('/filaments/community-db')
    def filament_community_db():
        _require_inventory_admin()
        import json
        db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'static', 'data', 'filament_db.json')
        try:
            with open(db_path, encoding='utf-8') as f:
                community = json.load(f)
            profiles = community.get('profiles', [])
        except Exception:
            app.logger.exception("Failed to load community filament database")
            profiles = []

        brands = sorted({p['brand'] for p in profiles})
        materials = sorted({p['material'] for p in profiles})
        return render_template(
            'filament_db.html',
            profiles=profiles,
            brands=brands,
            materials=materials,
        )

    @bp.route('/filaments/community-db/import', methods=['POST'])
    def filament_community_db_import():
        _require_inventory_admin()
        import json
        db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'static', 'data', 'filament_db.json')
        try:
            with open(db_path, encoding='utf-8') as f:
                community = json.load(f)
            all_profiles = {
                f"{p['brand']}|{p['material']}|{p['color']}": p
                for p in community.get('profiles', [])
            }
        except Exception:
            app.logger.exception("Failed to load community filament database for import")
            all_profiles = {}

        selected_keys = request.form.getlist('profile_key')
        imported = 0
        for key in selected_keys:
            p = all_profiles.get(key)
            if not p:
                continue
            # Get or create Brand
            brand = Brand.query.filter_by(name=p['brand']).first()
            if not brand:
                brand = Brand(name=p['brand'])
                db.session.add(brand)
                db.session.flush()
            # Get or create Material
            material = Material.query.filter_by(name=p['material']).first()
            if not material:
                material = Material(name=p['material'])
                db.session.add(material)
                db.session.flush()
            # Get or create Color
            color = Color.query.filter_by(name=p['color']).first()
            if not color:
                color = Color(name=p['color'], hex_value=p.get('hex', '#888888'))
                db.session.add(color)
                db.session.flush()
            # Create Filament if not already present with same brand+material+color
            existing = Filament.query.filter_by(
                brand_id=brand.id,
                material_id=material.id,
                color_id=color.id,
            ).first()
            if existing:
                continue
            weight = p.get('weight_total', 1000)
            fil = Filament(
                name=f"{p['brand']} {p['material']} {p['color']}",
                brand_id=brand.id,
                material_id=material.id,
                color_id=color.id,
                weight_total=float(weight),
                weight_remaining=float(weight),
                price=0.0,
                quantity=0,
                recommended_nozzle_temp=p.get('nozzle_temp'),
                recommended_bed_temp=p.get('bed_temp'),
            )
            db.session.add(fil)
            imported += 1

        try:
            safe_commit()
        except Exception:
            try:
                db.session.rollback()
            except Exception:
                pass
            app.logger.exception("Community DB import commit failed")
            imported = 0
            flash(translate('community_db_import_failed'), 'error')
            return redirect(url_for('filament_community_db'))

        flash(translate('community_db_imported_n').format(count=imported), 'success')
        return redirect(url_for('filament_community_db'))
    app.register_blueprint(bp)
