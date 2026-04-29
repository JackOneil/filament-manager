"""Inventory routes: listing, CRUD, spool management, and filament detail."""
import csv
import io
import math
from collections import Counter
from datetime import datetime, timedelta
from types import SimpleNamespace

from flask import abort, jsonify, render_template, request, redirect, url_for
from sqlalchemy import func
from sqlalchemy.orm import joinedload

from database import db
from auth import get_current_user, is_admin
from models import AppSetting, PrusaPrinter, BambuJobMaterial, BambuPrintJob, BambuPrinter, PrusaPrintJob, Brand, Color, Filament, Material, MovementHistory, Notification, Project, ProjectComment, ProjectFilament, ProjectQuote
from utils import (
    build_action_center,
    build_filament_history_name as _display_filament_name,
    compute_stock_status,
    deduct_filament_stock,
    escape_like,
    format_tags,
    get_filament_tags,
    log_movement,
    movement_action_label,
    parse_tags,
    translate,
    utc_now,
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
        filaments_query = filaments_query.filter(Filament.tag_text.ilike(f'%{escape_like(f_tag)}%'))

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


def _inventory_stats(f_brand='', f_material='', f_color='', f_tag=''):
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
        agg_query = agg_query.filter(Filament.tag_text.ilike(f'%{escape_like(f_tag)}%'))

    agg_result = agg_query.first()
    return {
        'spools': agg_result.spools or 0,
        'remaining': agg_result.remaining or 0,
        'value': agg_result.value or 0,
    }


def _live_printers():
    live = []
    now_dt = utc_now()
    freshness_cutoff = now_dt - timedelta(minutes=15)

    # Prusa — real-time local-network printers with progress
    for printer in PrusaPrinter.query.filter_by(enabled=True).all():
        job = PrusaPrintJob.query.filter_by(printer_id=printer.id).order_by(PrusaPrintJob.started_at.desc().nullslast()).first()
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

    # Bambu Cloud — jobs with RUNNING or PAUSED status fetched from Cloud API.
    # NOTE: Bambu Cloud API sometimes reports actively printing jobs as PAUSED
    # (raw status=4) instead of RUNNING (raw status=1). This is a known firmware
    # quirk — PAUSED from the task API does NOT mean the print is actually paused
    # by the user; it means the job is in an intermediate active-printing state.
    # Both statuses are therefore treated as "currently printing" for the overview.
    running_bambu = (
        BambuPrintJob.query
        .filter(BambuPrintJob.status.in_(['RUNNING', 'PAUSED']))
        .order_by(BambuPrintJob.synced_at.desc())
        .all()
    )
    for job in running_bambu:
        fake_printer = SimpleNamespace(
            name=job.printer_name or 'Bambu Lab',
            host=job.printer_name or 'Bambu Lab',
            printer_model=job.printer_model or None,
        )
        # Collect material swatches from BambuJobMaterial rows
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
            cost_time=job.cost_time,        # seconds
            started_at=job.started_at,
            material_swatches=material_swatches,
        )
        # Compute time-based progress estimate for Bambu (no real-time progress from Cloud API)
        bambu_progress_pct = None
        bambu_eta_at = None
        if job.started_at and job.cost_time and job.cost_time > 0:
            # Look up per-printer pre-job calibration offset
            bambu_printer = BambuPrinter.query.filter_by(device_id=job.device_id).first() if job.device_id else None
            pre_job_secs = (bambu_printer.pre_job_time_minutes or 0) * 60 if bambu_printer else 0
            total_secs = job.cost_time + pre_job_secs
            elapsed = (now_dt - job.started_at).total_seconds()
            bambu_progress_pct = min(99, int(elapsed / total_secs * 100))
            bambu_eta_at = job.started_at + timedelta(seconds=total_secs)
        live.append({'printer': fake_printer, 'job': fake_job, 'type': 'bambu',
                     'progress_pct': bambu_progress_pct, 'eta_at': bambu_eta_at})

    return live


def _overview_focus(action_center, live_printers, now=None):
    now = now or utc_now()
    today_start = datetime(now.year, now.month, now.day)
    tomorrow_start = today_start + timedelta(days=1)
    active_statuses = ('NEW', 'PENDING_APPROVAL', 'APPROVED', 'PRINTING')

    due_today = (
        Project.query
        .filter(
            Project.status != 'DONE',
            Project.due_date.is_not(None),
            Project.due_date >= today_start,
            Project.due_date < tomorrow_start,
        )
        .order_by(Project.due_date.asc(), Project.created_at.desc())
        .limit(4)
        .all()
    )
    active_projects = (
        Project.query
        .filter(Project.status.in_(active_statuses))
        .order_by(
            db.case((Project.status == 'PRINTING', 0), (Project.status == 'APPROVED', 1), else_=2),
            db.case((Project.due_date.is_(None), 1), else_=0),
            Project.due_date.asc(),
            Project.created_at.desc(),
        )
        .limit(20)
        .all()
    )

    upcoming_deadlines = (
        Project.query
        .filter(
            Project.status.in_(active_statuses),
            Project.due_date.is_not(None),
            Project.due_date >= today_start,
        )
        .order_by(Project.due_date.asc(), Project.created_at.desc())
        .limit(15)
        .all()
    )

    from utils import collect_usage_windows

    seven_days_ago = datetime.combine(now.date() - timedelta(days=6), datetime.min.time())
    recent_movements = MovementHistory.query.filter(
        MovementHistory.action_type.in_(('remove', 'bambu_print')),
        MovementHistory.created_at >= seven_days_ago
    ).all()
    
    usage_7d = [0.0] * 7
    for row in recent_movements:
        if row.weight:
            row_date = (row.created_at or now).date()
            days_ago = (now.date() - row_date).days
            if 0 <= days_ago < 7:
                 usage_7d[6 - days_ago] += row.weight
                 
    all_filaments = Filament.query.all()
    usage_windows = collect_usage_windows(all_filaments, now=now)
    top_turnover_month = []
    for f in all_filaments:
         usage = usage_windows.get(f.id, {}).get('usage_30', 0.0)
         if usage > 0:
             top_turnover_month.append({'filament': f, 'usage': usage})
    top_turnover_month.sort(key=lambda x: x['usage'], reverse=True)
    top_turnover_month = top_turnover_month[:10]

    urgent_items = []
    for item in action_center['low_stock'][:2]:
        urgent_items.append({
            'title': item['filament'].name,
            'meta': f"{int(item['filament'].weight_remaining or 0)} g",
            'url': url_for('filament_detail', id=item['filament'].id),
            'tone': 'critical' if item['status'] == 'critical' else 'warning',
        })
    for project in action_center['overdue_projects'][:2]:
        urgent_items.append({
            'title': project.name,
            'meta': project.due_date.strftime('%d.%m.%Y') if project.due_date else '-',
            'url': url_for('project_detail', id=project.id),
            'tone': 'critical',
        })
    for issue in action_center['printer_issues'][:1]:
        urgent_items.append({
            'title': issue['name'],
            'meta': 'sync',
            'url': url_for('settings') + '#printer-diagnostics',
            'tone': 'warning',
        })

    recent_activity = (
        MovementHistory.query
        .order_by(MovementHistory.created_at.desc())
        .limit(20)
        .all()
    )

    return {
        'urgent_total': (
            int(action_center['counts']['low_stock'] or 0)
            + int(action_center['counts']['overdue_projects'] or 0)
            + int(action_center['counts']['unmapped_jobs'] or 0)
            + len(action_center['printer_issues'])
        ),
        'urgent_items': urgent_items[:4],
        'due_today_total': len(due_today),
        'active_total': Project.query.filter(Project.status.in_(active_statuses)).count(),
        'printing_total': sum(1 for project in active_projects if project.status == 'PRINTING'),
        'live_total': len(live_printers),
        'due_today': due_today,
        'upcoming_deadlines': upcoming_deadlines,
        'active_projects': active_projects,
        'usage_7d': usage_7d,
        'top_turnover_month': top_turnover_month,
        'recent_activity': recent_activity,
    }


def _inventory_page_context():
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
    if view_mode_param and view_mode_param in ['card', 'list', 'compact']:
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
    allowed_per_page = [12, 24, 48, 96]
    default_per_page = setting.items_per_page if setting and setting.items_per_page in allowed_per_page else 12
    per_page = request.args.get('per_page', default_per_page, type=int)
    if per_page not in allowed_per_page:
        per_page = default_per_page

    stats = _inventory_stats(f_brand, f_material, f_color, f_tag)

    filaments_paginated = db.paginate(filaments_query.statement, page=page, per_page=per_page, error_out=False)
    usage_map = collect_usage_windows(filaments_paginated.items)
    filaments_paginated.items[:] = [_decorate_filament(fil, usage_map) for fil in filaments_paginated.items]

    brands = Brand.query.order_by(Brand.name).all()
    materials = Material.query.order_by(Material.name).all()
    colors = Color.query.order_by(Color.name).all()
    tag_options = sorted({
        tag
        for (tag_text,) in db.session.query(Filament.tag_text).filter(Filament.tag_text.isnot(None)).all()
        for tag in parse_tags(tag_text)
    }, key=str.lower)

    stock_alert_pool = [
        fil for fil in filaments_paginated.items
        if fil.stock_metrics['status'] in ('critical', 'warning') and not fil.reorder_alert_snoozed
    ]
    stock_alert_pool.sort(
        key=lambda item: (
            0 if item.stock_metrics['status'] == 'critical' else 1,
            item.stock_metrics['recommended_grams'] * -1,
            item.name.lower(),
        ),
    )

    visible_filaments = list(filaments_paginated.items)
    critical_count = sum(1 for fil in visible_filaments if fil.stock_metrics['status'] == 'critical')
    warning_count = sum(1 for fil in visible_filaments if fil.stock_metrics['status'] == 'warning')
    stable_count = sum(1 for fil in visible_filaments if fil.stock_metrics['status'] == 'stable')

    color_counts = Counter()
    for fil in visible_filaments:
        color_name = fil.color.name if fil.color else '-'
        color_hex = fil.color.hex_value if fil.color and fil.color.hex_value else '#cbd5e1'
        color_counts[(color_name, color_hex)] += max(int(fil.quantity or 0), 1)
    color_mix = [
        {'name': name, 'hex': hex_value, 'count': count}
        for (name, hex_value), count in color_counts.most_common(6)
    ]
    top_turnover = sorted(
        [fil for fil in visible_filaments if fil.stock_metrics['usage_30'] > 0],
        key=lambda fil: (fil.stock_metrics['usage_30'], fil.weight_remaining),
        reverse=True,
    )[:3]
    healthy_pool = sorted(
        [fil for fil in visible_filaments if fil.stock_metrics['status'] == 'stable'],
        key=lambda fil: ((fil.weight_remaining or 0), (fil.quantity or 0)),
        reverse=True,
    )[:3]

    return {
        'filaments': filaments_paginated,
        'stats': stats,
        'brands': brands,
        'materials': materials,
        'colors': colors,
        'f_brand': f_brand,
        'f_material': f_material,
        'f_color': f_color,
        'f_tag': f_tag,
        'quick_filter': '',
        'tag_options': tag_options,
        'view_mode': view_mode,
        'per_page': per_page,
        'per_page_options': allowed_per_page,
        'sort_by': sort_by,
        'sort_direction': sort_direction,
        'stock_alerts': stock_alert_pool[:6],
        'stock_alert_count': len(stock_alert_pool),
        'inventory_highlights': {
            'critical_count': critical_count,
            'warning_count': warning_count,
            'stable_count': stable_count,
            'tagged_count': sum(1 for fil in visible_filaments if fil.tag_list),
            'color_mix': color_mix,
            'top_turnover': top_turnover,
            'healthy_pool': healthy_pool,
        },
        'app_settings': setting,
    }


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


def _require_inventory_admin():
    user = get_current_user()
    if user and not is_admin(user):
        abort(403)


def _user_dashboard_context(user):
    owned_projects = (
        Project.query
        .filter(Project.owner_user_id == user.id)
        .order_by(Project.created_at.desc())
        .all()
    )
    open_projects = [project for project in owned_projects if project.status not in ('DONE', 'REJECTED')]
    pending_projects = [project for project in owned_projects if project.status == 'PENDING_APPROVAL']
    approved_projects = [project for project in owned_projects if project.status in ('APPROVED', 'PRINTING')]
    recent_comments = (
        ProjectComment.query
        .join(Project, Project.id == ProjectComment.project_id)
        .filter(Project.owner_user_id == user.id)
        .order_by(ProjectComment.created_at.desc())
        .limit(6)
        .all()
    )
    notifications = (
        Notification.query
        .filter_by(user_id=user.id)
        .order_by(Notification.created_at.desc())
        .limit(6)
        .all()
    )
    latest_projects = owned_projects[:5]
    return {
        'owned_projects': owned_projects,
        'open_projects_count': len(open_projects),
        'pending_projects_count': len(pending_projects),
        'approved_projects_count': len(approved_projects),
        'done_projects_count': len([project for project in owned_projects if project.status == 'DONE']),
        'recent_comments': recent_comments,
        'recent_notifications': notifications,
        'latest_projects': latest_projects,
    }


def register(app):

    @app.route('/')
    def index():
        user = get_current_user()
        if user and not is_admin(user):
            return render_template(
                'overview_user.html',
                user_dashboard=_user_dashboard_context(user),
            )
        action_center = build_action_center()
        live_printers = _live_printers()
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
            today=utc_now().date(),
            show_onboarding=show_onboarding,
            onboarding_steps=onboarding_steps,
        )

    @app.route('/filaments')
    def filaments_index():
        user = get_current_user()
        inventory_read_only = bool(user and not is_admin(user))
        context = _inventory_page_context()
        if inventory_read_only:
            return render_template('index_user.html', **context)
        return render_template('index.html', inventory_read_only=False, **context)

    @app.route('/filament/<int:id>')
    def filament_detail(id):
        _require_inventory_admin()
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
        timeline_paginated = db.paginate(timeline_rows.statement, page=timeline_page, per_page=detail_per_page, error_out=False)

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
        related_jobs_paginated = db.paginate(related_jobs_query.statement, page=jobs_page, per_page=detail_per_page, error_out=False)

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

    @app.route('/filament/<int:id>/meta', methods=['POST'])
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
        db.session.commit()
        return redirect(url_for('filament_detail', id=filament.id))

    @app.route('/filament/<int:id>/toggle-reorder-snooze', methods=['POST'])
    def filament_toggle_reorder_snooze(id):
        _require_inventory_admin()
        filament = db.get_or_404(Filament, id)
        filament.reorder_alert_snoozed = not bool(filament.reorder_alert_snoozed)
        db.session.commit()
        return redirect(request.referrer or url_for('filament_detail', id=filament.id))

    @app.route('/inventory/bulk', methods=['POST'])
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

        selected_ids = [f.id for f in selected]
        ProjectFilament.query.filter(ProjectFilament.filament_id.in_(selected_ids)).delete(synchronize_session=False)
        ProjectQuote.query.filter(ProjectQuote.filament_id.in_(selected_ids)).update({'filament_id': None}, synchronize_session=False)
        for filament in selected:
            log_movement(filament, 'bulk_delete', filament.weight_remaining, note='Bulk delete')
            db.session.delete(filament)

        db.session.commit()
        return redirect(url_for('filaments_index'))

    @app.route('/add', methods=['GET', 'POST'])
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
            return redirect(url_for('filaments_index'))

        brands = Brand.query.order_by(Brand.name).all()
        colors = Color.query.order_by(Color.name).all()
        materials = Material.query.order_by(Material.name).all()
        return render_template('add.html', brands=brands, colors=colors, materials=materials)

    @app.route('/edit/<int:id>', methods=['GET', 'POST'])
    def edit(id):
        _require_inventory_admin()
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
            filament.shop_url = request.form.get('shop_url', '').strip() or None

            weight_diff = filament.weight_remaining - old_weight
            if weight_diff > 0:
                log_movement(filament, 'add', weight_diff, note='Manual edit')
            elif weight_diff < 0:
                log_movement(filament, 'remove', abs(weight_diff), note='Manual edit')

            db.session.commit()
            return redirect(url_for('filaments_index'))

        return render_template('edit.html', filament=filament, formatted_tags=format_tags(filament.tag_text))

    @app.route('/use/<int:id>', methods=['POST'])
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
        log_movement(filament, 'remove', actual_amount, note='Manual usage')
        db.session.commit()
        return redirect(url_for('filaments_index'))

    @app.route('/add_spool/<int:id>', methods=['POST'])
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
        db.session.commit()
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

    @app.route('/remove_spool/<int:id>', methods=['POST'])
    def remove_spool(id):
        _require_inventory_admin()
        filament = db.get_or_404(Filament, id)
        if filament.quantity > 0:
            filament.quantity -= 1
            actual_amount = deduct_filament_stock(filament, filament.weight_total)
            log_movement(filament, 'remove', actual_amount, note='Removed spool')
        db.session.commit()
        return redirect(url_for('filaments_index'))

    @app.route('/delete/<int:id>', methods=['POST'])
    def delete(id):
        _require_inventory_admin()
        filament = db.get_or_404(Filament, id)
        log_movement(filament, 'remove', filament.weight_remaining, note='Deleted filament')
        ProjectFilament.query.filter_by(filament_id=filament.id).delete()
        ProjectQuote.query.filter_by(filament_id=filament.id).update({'filament_id': None})
        db.session.delete(filament)
        db.session.commit()
        return redirect(url_for('filaments_index'))

    # ── Operator / Admin mode toggle ──────────────────────────────────────────

    @app.route('/toggle-ui-mode', methods=['POST'])
    def toggle_ui_mode():
        from flask import session
        from auth import get_current_user, is_admin
        user = get_current_user()
        if not is_admin(user):
            return redirect(request.referrer or url_for('index'))
        current = session.get('ui_mode', 'admin')
        session['ui_mode'] = 'operator' if current == 'admin' else 'admin'
        return redirect(request.referrer or url_for('index'))

    # ── CSV filament import ───────────────────────────────────────────────────

    @app.route('/filaments/import-csv', methods=['GET', 'POST'])
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
                CSV_TEMPLATE_HEADER = 'name,brand,material,color,weight_total,weight_remaining,price,quantity,nozzle_temp,bed_temp\n'
                CSV_TEMPLATE_ROW = 'Example Filament,Bambu,PLA,Red,1000,1000,25.00,1,220,60\n'
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
                    weight_total = float(row.get('weight_total') or 0)
                    weight_remaining_raw = row.get('weight_remaining', '').strip()
                    weight_remaining = float(weight_remaining_raw) if weight_remaining_raw else weight_total
                    price = float(row.get('price') or 0)
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
                ))
                imported += 1
            db.session.commit()
            return redirect(url_for('filaments_index',
                                    _anchor='import_ok',
                                    imported=imported))

    # ── CSV filament export ───────────────────────────────────────────────────

    @app.route('/filaments/export-csv', methods=['GET'])
    def filament_export_csv():
        import flask
        _require_inventory_admin()
        filaments = Filament.query.order_by(Filament.name).all()
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            'name', 'brand', 'material', 'color',
            'weight_total', 'weight_remaining', 'price', 'quantity',
            'nozzle_temp', 'bed_temp',
        ])
        for f in filaments:
            writer.writerow([
                f.name,
                f.brand.name if f.brand else '',
                f.material.name if f.material else '',
                f.color.name if f.color else '',
                f.weight_total,
                f.weight_remaining,
                f.price,
                f.quantity,
                f.recommended_nozzle_temp or '',
                f.recommended_bed_temp or '',
            ])
        csv_content = output.getvalue()
        # Prepend UTF-8 BOM so Excel and other tools correctly detect Czech characters
        response = flask.make_response('\ufeff' + csv_content)
        response.headers['Content-Type'] = 'text/csv; charset=utf-8-sig'
        response.headers['Content-Disposition'] = 'attachment; filename="filaments_export.csv"'
        return response
