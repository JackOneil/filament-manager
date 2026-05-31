"""Inventory routes: listing, CRUD, spool management, and filament detail."""
import csv
import io
import math
import os
import secrets
import threading
from collections import Counter
from datetime import datetime, timedelta
from types import SimpleNamespace

from flask import abort, flash, jsonify, render_template, request, redirect, session, url_for, Blueprint
from sqlalchemy import func, select
from sqlalchemy.orm import joinedload

from database import db
from auth import get_current_user, is_admin
from models import AppSetting, PrusaPrinter, BambuJobMaterial, BambuPrintJob, BambuPrinter, PrusaPrintJob, Brand, Color, Filament, Material, MovementHistory, Notification, Project, ProjectComment, ProjectFilament, ProjectQuote, FilamentUndoLog
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
    movement_action_label,
    parse_tags,
    restore_filament_from_snapshot,
    restore_bulk_from_snapshot,
    translate,
    utc_now,
)



def _build_filament_query():
    return select(Filament).options(
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
        filaments_query = filaments_query.where(Filament.brand_id == f_brand)
    if f_material:
        filaments_query = filaments_query.where(Filament.material_id == f_material)
    if f_color:
        filaments_query = filaments_query.where(Filament.color_id == f_color)
    if f_tag:
        filaments_query = filaments_query.where(Filament.tag_text.ilike(f'%{escape_like(f_tag)}%'))

    return filaments_query, f_brand, f_material, f_color, f_tag


def _decorate_filament(filament, usage_map, sparkline_data=None):
    metrics = compute_stock_status(
        filament,
        usage_map.get(filament.id, {}).get('usage_30', 0.0),
        usage_map.get(filament.id, {}).get('usage_90', 0.0),
    )
    filament.stock_metrics = metrics
    filament.tag_list = get_filament_tags(filament)
    
    # Pre-compute capacity and percentage to avoid Jinja2 arithmetic (Rule 3.4)
    capacity_all = filament.quantity * filament.weight_total
    filament._capacity_all = capacity_all
    if capacity_all > 0:
        filament._pct = round(filament.weight_remaining / capacity_all * 100)
    else:
        filament._pct = 0
    
    # Pre-compute SVG sparkline path to avoid Jinja2 loops (Rule 3.5)
    if sparkline_data and filament.id in sparkline_data:
        polyline_pts, fill_pts = generate_sparkline_svg_path(sparkline_data[filament.id])
        filament._sparkline_polyline = polyline_pts
        filament._sparkline_fill = fill_pts
    else:
        filament._sparkline_polyline = ''
        filament._sparkline_fill = ''
    
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


def _low_stock_filaments(app_settings, limit=20):
    """Return filaments sorted by remaining percentage (lowest first), with shop URLs resolved."""
    from utils import collect_usage_windows

    filaments = (
        Filament.query
        .options(joinedload(Filament.brand), joinedload(Filament.material), joinedload(Filament.color))
        .filter(Filament.quantity > 0)
        .all()
    )

    usage_windows = collect_usage_windows(filaments)

    results = []
    for fil in filaments:
        capacity_all = fil.quantity * fil.weight_total
        pct = round(fil.weight_remaining / capacity_all * 100) if capacity_all > 0 else 0
        usage = usage_windows.get(fil.id, {})
        status_info = compute_stock_status(fil, usage.get('usage_30', 0.0), usage.get('usage_90', 0.0))

        results.append({
            'filament': fil,
            'pct': pct,
            'remaining': float(fil.weight_remaining or 0),
            'status': status_info['status'],
            'recommended_spools': status_info.get('recommended_spools', 0),
            'recommended_grams': status_info.get('recommended_grams', 0),
            'recommended_order_grams': status_info.get('recommended_order_grams', 0),
        })

    results.sort(key=lambda x: x['pct'])
    return results[:limit]


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
        .limit(30)
        .all()
    )

    from utils import collect_usage_windows, translate

    seven_days_ago = datetime.combine(now.date() - timedelta(days=6), datetime.min.time())
    kpi_trend_cutoff = datetime.combine(now.date() - timedelta(days=7), datetime.min.time())

    # All movements in the last 7 days (for usage_7d bars + kpi trends)
    all_movements_7d = MovementHistory.query.filter(
        MovementHistory.created_at >= seven_days_ago
    ).all()

    usage_7d = [0.0] * 7
    net_grams_7d = 0.0
    net_spools_7d = 0
    for row in all_movements_7d:
        w = float(row.weight or 0)
        row_date = (row.created_at or now).date()
        days_ago = (now.date() - row_date).days
        if row.action_type in ('remove', 'bambu_print'):
            if 0 <= days_ago < 7:
                usage_7d[6 - days_ago] += w
            net_grams_7d -= w
        elif row.action_type in ('add', 'bulk_add_weight', 'bulk_add_spool'):
            net_grams_7d += w
            if row.action_type == 'bulk_add_spool':
                net_spools_7d += 1
        elif row.action_type == 'bulk_remove_spool':
            net_grams_7d -= w
            net_spools_7d -= 1

    new_projects_7d = Project.query.filter(
        Project.created_at >= kpi_trend_cutoff
    ).count()

    # Prints this week vs last week (calendar weeks, Mon–Sun)
    days_since_monday = now.weekday()
    this_week_start = datetime.combine(now.date() - timedelta(days=days_since_monday), datetime.min.time())
    last_week_start = this_week_start - timedelta(days=7)

    prints_this_week = (
        BambuPrintJob.query.filter(BambuPrintJob.started_at >= this_week_start).count()
        + PrusaPrintJob.query.filter(PrusaPrintJob.started_at >= this_week_start).count()
    )
    prints_last_week = (
        BambuPrintJob.query.filter(
            BambuPrintJob.started_at >= last_week_start,
            BambuPrintJob.started_at < this_week_start,
        ).count()
        + PrusaPrintJob.query.filter(
            PrusaPrintJob.started_at >= last_week_start,
            PrusaPrintJob.started_at < this_week_start,
        ).count()
    )
    prints_delta = prints_this_week - prints_last_week

    def _trend(delta, unit=''):
        sign = '+' if delta >= 0 else ''
        return {
            'delta': delta,
            'delta_str': f'{sign}{delta:,}{unit}',
            'dir': 'up' if delta > 0 else ('down' if delta < 0 else 'flat'),
        }

    kpi_trends = {
        'total_remaining': _trend(int(round(net_grams_7d)), ' g'),
        'total_spools': _trend(net_spools_7d),
        'active_projects': {'delta': new_projects_7d, 'delta_str': f'+{new_projects_7d}', 'dir': 'up' if new_projects_7d > 0 else 'flat'},
        'live_printers': {
            'delta': prints_delta,
            'delta_str': ('+' if prints_delta >= 0 else '') + str(prints_delta),
            'dir': 'up' if prints_delta > 0 else ('down' if prints_delta < 0 else 'flat'),
            'period': 'last_week',
        },
    }

    # Day labels for usage_7d chart (translation keys)
    usage_7d_labels = []
    for i in range(7):
        day_date = now.date() - timedelta(days=6 - i)
        usage_7d_labels.append('today' if i == 6 else f'weekday_{day_date.weekday()}')

    # Mini-calendar days (next 7 days from today)
    mini_cal_days = []
    for i in range(7):
        cal_date = today_start.date() + timedelta(days=i)
        mini_cal_days.append({
            'date': cal_date,
            'day_key': f'weekday_{cal_date.weekday()}',
            'is_today': i == 0,
        })
                 
    all_filaments = Filament.query.options(joinedload(Filament.brand), joinedload(Filament.material), joinedload(Filament.color)).all()
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
        'usage_7d_labels': usage_7d_labels,
        'top_turnover_month': top_turnover_month,
        'recent_activity': recent_activity,
        'kpi_trends': kpi_trends,
        'mini_cal_days': mini_cal_days,
        'prints_this_week': prints_this_week,
        'prints_last_week': prints_last_week,
    }


def _inventory_page_context():
    from utils import collect_usage_windows

    filaments_query, f_brand, f_material, f_color, f_tag = _apply_inventory_filters(_build_filament_query())
    # Capture filtered query before sorting — used for Smart Highlights across ALL pages
    highlights_query = filaments_query
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

    filaments_paginated = db.paginate(filaments_query, page=page, per_page=per_page, error_out=False)

    # Load ALL filaments matching the current filter (no pagination) so Smart Highlights
    # (top turnover, counts, alerts) reflect the entire inventory, not just the current page.
    all_highlights_filaments = db.session.execute(highlights_query).scalars().all()
    highlights_usage_map = collect_usage_windows(all_highlights_filaments)
    for fil in all_highlights_filaments:
        fil.stock_metrics = compute_stock_status(
            fil,
            highlights_usage_map.get(fil.id, {}).get('usage_30', 0.0),
            highlights_usage_map.get(fil.id, {}).get('usage_90', 0.0),
        )
        fil.tag_list = get_filament_tags(fil)
        capacity_all = fil.quantity * fil.weight_total
        fil._capacity_all = capacity_all
        fil._pct = round(fil.weight_remaining / capacity_all * 100) if capacity_all > 0 else 0

    usage_map = collect_usage_windows(filaments_paginated.items)
    sparkline_data = collect_sparkline_data(filaments_paginated.items)
    filaments_paginated.items[:] = [_decorate_filament(fil, usage_map, sparkline_data) for fil in filaments_paginated.items]

    brands = Brand.query.order_by(Brand.name).all()
    materials = Material.query.order_by(Material.name).all()
    colors = Color.query.order_by(Color.name).all()
    tag_options = sorted({
        tag
        for (tag_text,) in db.session.query(Filament.tag_text).filter(Filament.tag_text.isnot(None)).all()
        for tag in parse_tags(tag_text)
    }, key=str.lower)

    stock_alert_pool = [
        fil for fil in all_highlights_filaments
        if fil.stock_metrics['status'] in ('critical', 'warning') and not fil.reorder_alert_snoozed
    ]
    stock_alert_pool.sort(
        key=lambda item: (
            0 if item.stock_metrics['status'] == 'critical' else 1,
            item.stock_metrics['recommended_grams'] * -1,
            item.name.lower(),
        ),
    )

    critical_count = sum(1 for fil in all_highlights_filaments if fil.stock_metrics['status'] == 'critical')
    warning_count = sum(1 for fil in all_highlights_filaments if fil.stock_metrics['status'] == 'warning')
    stable_count = sum(1 for fil in all_highlights_filaments if fil.stock_metrics['status'] == 'stable')

    color_counts = Counter()
    for fil in all_highlights_filaments:
        color_name = fil.color.name if fil.color else '-'
        color_hex = fil.color.hex_value if fil.color and fil.color.hex_value else '#cbd5e1'
        color_counts[(color_name, color_hex)] += max(int(fil.quantity or 0), 1)
    color_mix = [
        {'name': name, 'hex': hex_value, 'count': count}
        for (name, hex_value), count in color_counts.most_common(6)
    ]
    top_turnover = sorted(
        [fil for fil in all_highlights_filaments if fil.stock_metrics['usage_30'] > 0],
        key=lambda fil: fil.stock_metrics['usage_30'],
        reverse=True,
    )[:3]
    healthy_pool = sorted(
        [fil for fil in all_highlights_filaments if fil.stock_metrics['status'] == 'stable'],
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
            'tagged_count': sum(1 for fil in all_highlights_filaments if fil.tag_list),
            'color_mix': color_mix,
            'top_turnover': top_turnover,
            'healthy_pool': healthy_pool,
        },
        'app_settings': setting,
        'sparkline_data': sparkline_data,
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


_UNDO_SESSION_KEY = 'inventory_pending_undo'


def _serialize_filament_snapshot(filament):
    return {
        'id': filament.id,
        'name': filament.name,
        'brand_id': filament.brand_id,
        'color_id': filament.color_id,
        'material_id': filament.material_id,
        'weight_total': float(filament.weight_total or 0.0),
        'weight_remaining': float(filament.weight_remaining or 0.0),
        'price': float(filament.price or 0.0),
        'quantity': int(filament.quantity or 0),
        'min_stock_grams': float(filament.min_stock_grams or 0.0),
        'max_stock_grams': float(filament.max_stock_grams or 0.0),
        'tag_text': filament.tag_text,
        'quality_stringing': filament.quality_stringing,
        'quality_adhesion': filament.quality_adhesion,
        'quality_drying': filament.quality_drying,
        'quality_profile': filament.quality_profile,
        'quality_notes': filament.quality_notes,
        'recommended_nozzle_temp': filament.recommended_nozzle_temp,
        'recommended_bed_temp': filament.recommended_bed_temp,
        'reorder_alert_snoozed': bool(filament.reorder_alert_snoozed),
        'shop_url': filament.shop_url,
    }


def _build_filament_restore_bundle(filament):
    project_filaments = []
    for row in ProjectFilament.query.filter_by(filament_id=filament.id).all():
        project_filaments.append({
            'project_id': row.project_id,
            'estimated_weight': float(row.estimated_weight or 0.0),
            'is_used': bool(row.is_used),
        })

    project_quote_ids = [
        row.id
        for row in ProjectQuote.query.filter_by(filament_id=filament.id).all()
    ]

    return {
        'filament': _serialize_filament_snapshot(filament),
        'project_filaments': project_filaments,
        'project_quote_ids': project_quote_ids,
    }


def _restore_filament_snapshot(snapshot):
    restored = db.session.get(Filament, snapshot['id'])
    if restored:
        return restored

    restored = Filament(
        id=snapshot['id'],
        name=snapshot['name'],
        brand_id=snapshot['brand_id'],
        color_id=snapshot['color_id'],
        material_id=snapshot['material_id'],
        weight_total=snapshot['weight_total'],
        weight_remaining=snapshot['weight_remaining'],
        price=snapshot['price'],
        quantity=snapshot['quantity'],
        min_stock_grams=snapshot['min_stock_grams'],
        max_stock_grams=snapshot['max_stock_grams'],
        tag_text=snapshot['tag_text'],
        quality_stringing=snapshot['quality_stringing'],
        quality_adhesion=snapshot['quality_adhesion'],
        quality_drying=snapshot['quality_drying'],
        quality_profile=snapshot['quality_profile'],
        quality_notes=snapshot['quality_notes'],
        recommended_nozzle_temp=snapshot['recommended_nozzle_temp'],
        recommended_bed_temp=snapshot['recommended_bed_temp'],
        reorder_alert_snoozed=snapshot['reorder_alert_snoozed'],
        shop_url=snapshot['shop_url'],
    )
    db.session.add(restored)
    db.session.flush()
    return restored


def _restore_project_relations(filament_id, project_filaments, project_quote_ids):
    for row in project_filaments:
        existing = ProjectFilament.query.filter_by(
            project_id=row['project_id'],
            filament_id=filament_id,
        ).first()
        if existing:
            existing.estimated_weight = row['estimated_weight']
            existing.is_used = row['is_used']
        else:
            db.session.add(ProjectFilament(
                project_id=row['project_id'],
                filament_id=filament_id,
                estimated_weight=row['estimated_weight'],
                is_used=row['is_used'],
            ))

    if project_quote_ids:
        ProjectQuote.query.filter(
            ProjectQuote.id.in_(project_quote_ids),
            ProjectQuote.filament_id.is_(None),
        ).update({'filament_id': filament_id}, synchronize_session=False)


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


