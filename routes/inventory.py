"""Inventory routes: listing, CRUD, spool management, and filament detail."""
import math

from flask import render_template, request, redirect, url_for
from sqlalchemy import func
from sqlalchemy.orm import joinedload

from database import db
from models import AppSetting, BambuJobMaterial, BambuPrintJob, Brand, Color, Filament, Material, MovementHistory, ProjectFilament
from utils import (
    build_filament_history_name as _display_filament_name,
    compute_stock_status,
    format_tags,
    get_filament_tags,
    log_movement,
    movement_action_label,
    parse_tags,
)


def _build_filament_query():
    return Filament.query.options(
        joinedload(Filament.brand),
        joinedload(Filament.material),
        joinedload(Filament.color),
    )


def _apply_inventory_filters(filaments_query):
    f_brand = request.args.get('brand', '')
    f_material = request.args.get('material', '')
    f_color = request.args.get('color', '')
    f_tag = request.args.get('tag', '').strip()

    if f_brand:
        filaments_query = filaments_query.filter(Filament.brand_id == f_brand)
    if f_material:
        filaments_query = filaments_query.filter(Filament.material_id == f_material)
    if f_color:
        filaments_query = filaments_query.filter(Filament.color_id == f_color)
    if f_tag:
        filaments_query = filaments_query.filter(Filament.tag_text.ilike(f'%{f_tag}%'))

    return filaments_query, f_brand, f_material, f_color, f_tag


def _decorate_filament(filament, usage_map):
    metrics = compute_stock_status(
        filament,
        usage_map.get(filament.id, {}).get('usage_30', 0.0),
        usage_map.get(filament.id, {}).get('usage_90', 0.0),
    )
    filament.stock_metrics = metrics
    filament.tag_list = get_filament_tags(filament)
    return filament


def _selected_filaments():
    selected_ids = request.form.getlist('selected_ids')
    ids = []
    for raw_id in selected_ids:
        try:
            ids.append(int(raw_id))
        except (TypeError, ValueError):
            continue
    if not ids:
        return []
    return Filament.query.filter(Filament.id.in_(ids)).all()


def register(app):

    @app.route('/')
    def index():
        from utils import collect_usage_windows

        filaments_query, f_brand, f_material, f_color, f_tag = _apply_inventory_filters(_build_filament_query())
        sort_by = request.args.get('sort_by', 'name')
        sort_direction = request.args.get('sort_direction', 'asc')

        if sort_direction not in ['asc', 'desc']:
            sort_direction = 'asc'

        setting = AppSetting.query.first()
        if not setting:
            setting = AppSetting()
            db.session.add(setting)
            db.session.commit()

        view_mode_param = request.args.get('view', None)
        if view_mode_param and view_mode_param in ['card', 'list']:
            setting.view_mode = view_mode_param
            db.session.commit()

        view_mode = setting.view_mode

        if sort_by == 'brand':
            order_expr = Brand.name
            filaments_query = filaments_query.join(Brand)
        elif sort_by == 'pieces':
            order_expr = Filament.quantity
        elif sort_by == 'remaining':
            order_expr = Filament.weight_remaining
        elif sort_by == 'capacity':
            order_expr = Filament.quantity * Filament.weight_total
        elif sort_by == 'percent':
            order_expr = db.case(
                (Filament.quantity * Filament.weight_total > 0,
                 Filament.weight_remaining / (Filament.quantity * Filament.weight_total)),
                else_=0,
            )
        else:
            order_expr = Filament.name

        if sort_direction == 'desc':
            filaments_query = filaments_query.order_by(order_expr.desc())
        else:
            filaments_query = filaments_query.order_by(order_expr.asc())

        page = request.args.get('page', 1, type=int)
        default_per_page = setting.items_per_page if setting else 12
        per_page = request.args.get('per_page', default_per_page, type=int)
        if per_page not in [12, 24, 48, 96]:
            per_page = default_per_page

        agg_query = db.session.query(
            func.sum(Filament.quantity).label('spools'),
            func.sum(Filament.weight_remaining).label('remaining'),
            func.sum(
                db.case(
                    (Filament.weight_total > 0, (Filament.price / Filament.weight_total) * Filament.weight_remaining),
                    else_=0,
                )
            ).label('value'),
        )

        if f_brand:
            agg_query = agg_query.filter(Filament.brand_id == f_brand)
        if f_material:
            agg_query = agg_query.filter(Filament.material_id == f_material)
        if f_color:
            agg_query = agg_query.filter(Filament.color_id == f_color)
        if f_tag:
            agg_query = agg_query.filter(Filament.tag_text.ilike(f'%{f_tag}%'))

        agg_result = agg_query.first()
        total_spools = agg_result.spools or 0
        total_remaining_g = agg_result.remaining or 0
        total_value = agg_result.value or 0

        filaments_paginated = db.paginate(filaments_query, page=page, per_page=per_page, error_out=False)
        usage_map = collect_usage_windows(filaments_paginated.items)
        filaments_paginated.items[:] = [_decorate_filament(fil, usage_map) for fil in filaments_paginated.items]

        brands = Brand.query.order_by(Brand.name).all()
        materials = Material.query.order_by(Material.name).all()
        colors = Color.query.order_by(Color.name).all()
        tag_options = sorted({
            tag
            for filament in Filament.query.order_by(Filament.name).all()
            for tag in parse_tags(filament.tag_text)
        }, key=str.lower)

        stock_alerts = sorted(
            [fil for fil in filaments_paginated.items if fil.stock_metrics['status'] in ('critical', 'warning') and not fil.reorder_alert_snoozed],
            key=lambda item: (
                0 if item.stock_metrics['status'] == 'critical' else 1,
                item.stock_metrics['recommended_grams'] * -1,
                item.name.lower(),
            ),
        )[:6]

        return render_template(
            'index.html',
            filaments=filaments_paginated,
            stats={"spools": total_spools, "remaining": total_remaining_g, "value": total_value},
            brands=brands,
            materials=materials,
            colors=colors,
            f_brand=f_brand,
            f_material=f_material,
            f_color=f_color,
            f_tag=f_tag,
            tag_options=tag_options,
            view_mode=view_mode,
            per_page=per_page,
            sort_by=sort_by,
            sort_direction=sort_direction,
            stock_alerts=stock_alerts,
        )

    @app.route('/filament/<int:id>')
    def filament_detail(id):
        from utils import collect_usage_windows

        filament = _build_filament_query().filter(Filament.id == id).first_or_404()
        usage_map = collect_usage_windows([filament])
        _decorate_filament(filament, usage_map)

        timeline_page = request.args.get('timeline_page', 1, type=int)
        jobs_page = request.args.get('jobs_page', 1, type=int)
        detail_per_page = 10

        timeline_rows = MovementHistory.query.options(
            joinedload(MovementHistory.project),
            joinedload(MovementHistory.bambu_job),
        ).filter(
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
        related_jobs_query = BambuPrintJob.query.options(
            joinedload(BambuPrintJob.materials),
        ).filter(
            db.or_(
                BambuPrintJob.filament_id == filament.id,
                BambuPrintJob.materials.any(BambuJobMaterial.filament_id == filament.id),
            )
        ).order_by(BambuPrintJob.started_at.desc().nullslast())
        related_jobs_paginated = db.paginate(related_jobs_query, page=jobs_page, per_page=detail_per_page, error_out=False)

        return render_template(
            'filament_detail.html',
            filament=filament,
            timeline=timeline,
            timeline_paginated=timeline_paginated,
            related_project_rows=related_project_rows,
            related_jobs=related_jobs_paginated.items,
            related_jobs_paginated=related_jobs_paginated,
            formatted_tags=format_tags(filament.tag_text),
        )

    @app.route('/filament/<int:id>/meta', methods=['POST'])
    def filament_update_meta(id):
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
        db.session.commit()
        return redirect(url_for('filament_detail', id=filament.id))

    @app.route('/filament/<int:id>/toggle-reorder-snooze', methods=['POST'])
    def filament_toggle_reorder_snooze(id):
        filament = db.get_or_404(Filament, id)
        filament.reorder_alert_snoozed = not bool(filament.reorder_alert_snoozed)
        db.session.commit()
        return redirect(request.referrer or url_for('filament_detail', id=filament.id))

    @app.route('/inventory/bulk', methods=['POST'])
    def inventory_bulk():
        # Only the delete action is supported from the UI; validate explicitly
        # so an unexpected action never silently deletes filaments.
        action = request.form.get('action', '')
        if action != 'bulk_delete_selected':
            return redirect(url_for('index'))

        selected = _selected_filaments()
        if not selected:
            return redirect(url_for('index'))

        for filament in selected:
            log_movement(filament, 'bulk_delete', filament.weight_remaining, note='Bulk delete')
            db.session.delete(filament)

        db.session.commit()
        return redirect(url_for('index'))

    @app.route('/add', methods=['GET', 'POST'])
    def add():
        if request.method == 'POST':
            name = request.form.get('name', '').strip()
            try:
                brand_id = request.form.get('brand_id', type=int)
                color_id = request.form.get('color_id', type=int)
                material_id = request.form.get('material_id', type=int)
                weight_total = request.form.get('weight_total', type=float)
                quantity = request.form.get('quantity', 1, type=int) or 1
                price = request.form.get('price', type=float)
                if not all([brand_id, color_id, material_id, weight_total, price is not None]):
                    return redirect(url_for('add'))
                weight_remaining = float(
                    request.form.get('weight_remaining') or weight_total * quantity
                )
            except (TypeError, ValueError):
                return redirect(url_for('add'))
            min_stock_grams = max(request.form.get('min_stock_grams', 0.0, type=float) or 0.0, 0.0)
            max_stock_grams = max(request.form.get('max_stock_grams', 0.0, type=float) or 0.0, 0.0)
            tag_text = format_tags(request.form.get('tag_text', ''))

            if not name:
                brand = db.session.get(Brand, brand_id)
                material = db.session.get(Material, material_id)
                color = db.session.get(Color, color_id)
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
            log_movement(new_fil, 'add', weight_remaining, note='Initial stock')
            db.session.commit()
            return redirect(url_for('index'))

        brands = Brand.query.order_by(Brand.name).all()
        colors = Color.query.order_by(Color.name).all()
        materials = Material.query.order_by(Material.name).all()
        return render_template('add.html', brands=brands, colors=colors, materials=materials)

    @app.route('/edit/<int:id>', methods=['GET', 'POST'])
    def edit(id):
        filament = db.get_or_404(Filament, id)
        if request.method == 'POST':
            old_weight = filament.weight_remaining
            try:
                filament.name = request.form.get('name', filament.name) or filament.name
                filament.weight_remaining = float(request.form.get('weight_remaining', filament.weight_remaining))
                filament.price = float(request.form.get('price', filament.price))
                filament.quantity = int(request.form.get('quantity', filament.quantity))
            except (TypeError, ValueError):
                return redirect(url_for('edit', id=id))
            filament.tag_text = format_tags(request.form.get('tag_text', filament.tag_text or ''))
            filament.min_stock_grams = max(request.form.get('min_stock_grams', filament.min_stock_grams, type=float) or 0.0, 0.0)
            filament.max_stock_grams = max(request.form.get('max_stock_grams', filament.max_stock_grams, type=float) or 0.0, 0.0)

            weight_diff = filament.weight_remaining - old_weight
            if weight_diff > 0:
                log_movement(filament, 'add', weight_diff, note='Manual edit')
            elif weight_diff < 0:
                log_movement(filament, 'remove', abs(weight_diff), note='Manual edit')

            db.session.commit()
            return redirect(url_for('index'))

        return render_template('edit.html', filament=filament, formatted_tags=format_tags(filament.tag_text))

    @app.route('/use/<int:id>', methods=['POST'])
    def use_filament(id):
        try:
            amount = float(request.form.get('amount', 0) or 0)
        except (TypeError, ValueError):
            amount = 0.0
        if amount <= 0:
            return redirect(url_for('index'))
        filament = db.get_or_404(Filament, id)
        old_weight = filament.weight_remaining
        filament.weight_remaining -= amount
        if filament.weight_remaining < 0:
            filament.weight_remaining = 0
        actual_amount = old_weight - filament.weight_remaining

        if filament.weight_total > 0:
            expected_quantity = math.ceil(filament.weight_remaining / filament.weight_total)
            if expected_quantity < filament.quantity:
                filament.quantity = expected_quantity

        log_movement(filament, 'remove', actual_amount, note='Manual usage')
        db.session.commit()
        return redirect(url_for('index'))

    @app.route('/add_spool/<int:id>', methods=['POST'])
    def add_spool(id):
        filament = db.get_or_404(Filament, id)
        filament.quantity += 1
        filament.weight_remaining += filament.weight_total
        log_movement(filament, 'add', filament.weight_total, note='Added spool')
        db.session.commit()
        return redirect(url_for('index'))

    @app.route('/remove_spool/<int:id>', methods=['POST'])
    def remove_spool(id):
        filament = db.get_or_404(Filament, id)
        if filament.quantity > 0:
            filament.quantity -= 1
            old_weight = filament.weight_remaining
            filament.weight_remaining -= filament.weight_total
            if filament.weight_remaining < 0:
                filament.weight_remaining = 0
            actual_amount = old_weight - filament.weight_remaining
            log_movement(filament, 'remove', actual_amount, note='Removed spool')
        db.session.commit()
        return redirect(url_for('index'))

    @app.route('/delete/<int:id>', methods=['POST'])
    def delete(id):
        filament = db.get_or_404(Filament, id)
        log_movement(filament, 'remove', filament.weight_remaining, note='Deleted filament')
        db.session.delete(filament)
        db.session.commit()
        return redirect(url_for('index'))
