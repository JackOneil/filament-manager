"""Statistics dashboard: usage charts, project summaries, and stock forecast."""
from collections import defaultdict
from datetime import datetime, timedelta
import colorsys
import json

from flask import render_template, request, Blueprint
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from database import db
from models import (
    AppSetting, BambuJobMaterial, BambuPrintJob, Filament,
    MovementHistory, Project, ProjectFilament, ProjectQuote
)
from utils import build_filament_history_name as _display_filament_name, collect_usage_windows, compute_stock_status, utc_now


def _hex_to_hsl_sort_key(hex_value):
    """Return sort key (bucket, hue, -saturation) for rainbow-order color grouping.
    Neutrals (saturation < 10 %) are placed at the end, ordered light→dark."""
    hex_color = (hex_value or '').lstrip('#')
    if len(hex_color) != 6:
        return (2, 0, 0)
    try:
        r = int(hex_color[0:2], 16) / 255.0
        g = int(hex_color[2:4], 16) / 255.0
        b = int(hex_color[4:6], 16) / 255.0
    except ValueError:
        return (2, 0, 0)
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    if s < 0.10:          # neutral — group separately at end, ordered by lightness
        return (1, l, 0)
    return (0, h, -s)    # chromatic — rainbow order, vivid first within same hue


CHART_PALETTE = [
    '#2563eb', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6',
    '#06b6d4', '#84cc16', '#f97316', '#ec4899', '#14b8a6',
]


def _date_labels(days):
    today = utc_now().date()
    return [today - timedelta(days=offset) for offset in range(days - 1, -1, -1)]


def _empty_series(days):
    return {day.isoformat(): 0.0 for day in _date_labels(days)}


def _safe_divide(numerator, denominator):
    if not denominator:
        return 0.0
    return numerator / denominator


def _reorder_status_label_key(status):
    return {
        'critical': 'stats_reorder_now',
        'warning': 'stats_reorder_soon',
        'stable': 'stats_stock_ok',
    }.get(status, status)


def _project_usage_rows():
    rows = defaultdict(lambda: {'grams': 0.0, 'jobs': 0, 'source': set()})

    # Subquery: get all job IDs that have materials
    has_materials_sub = select(BambuJobMaterial.job_id).distinct()

    # Query 1: Bambu jobs with materials
    bambu_with_materials = db.session.query(
        Project.id.label('project_id'),
        Project.name.label('project_name'),
        db.func.count(db.func.distinct(BambuPrintJob.id)).label('job_count'),
        db.func.sum(BambuJobMaterial.weight_grams).label('total_weight')
    ).join(
        BambuPrintJob, Project.id == BambuPrintJob.project_id
    ).join(
        BambuJobMaterial, BambuPrintJob.id == BambuJobMaterial.job_id
    ).filter(
        BambuJobMaterial.deducted.is_(True),
        BambuJobMaterial.weight_grams > 0
    ).group_by(
        Project.id, Project.name
    ).all()

    # Query 2: Bambu jobs without materials
    bambu_no_materials = db.session.query(
        Project.id.label('project_id'),
        Project.name.label('project_name'),
        db.func.count(BambuPrintJob.id).label('job_count'),
        db.func.sum(BambuPrintJob.weight_grams).label('total_weight')
    ).join(
        Project, Project.id == BambuPrintJob.project_id
    ).filter(
        BambuPrintJob.deducted.is_(True),
        BambuPrintJob.weight_grams > 0,
        ~BambuPrintJob.id.in_(has_materials_sub)
    ).group_by(
        Project.id, Project.name
    ).all()

    # Query 3: Manual links
    manual_sums = db.session.query(
        Project.id.label('project_id'),
        Project.name.label('project_name'),
        db.func.sum(ProjectFilament.estimated_weight).label('total_weight')
    ).join(
        Project, Project.id == ProjectFilament.project_id
    ).filter(
        ProjectFilament.is_used.is_(True),
        ProjectFilament.estimated_weight > 0
    ).group_by(
        Project.id, Project.name
    ).all()

    for project_id, project_name, job_count, total_weight in bambu_with_materials:
        row = rows[project_id]
        row['project_name'] = project_name
        row['grams'] += total_weight
        row['jobs'] += job_count
        row['source'].add('bambu')

    for project_id, project_name, job_count, total_weight in bambu_no_materials:
        row = rows[project_id]
        row['project_name'] = project_name
        row['grams'] += total_weight
        row['jobs'] += job_count
        row['source'].add('bambu')

    for project_id, project_name, total_weight in manual_sums:
        row = rows[project_id]
        row['project_name'] = project_name
        row['grams'] += total_weight
        row['source'].add('manual')

    result = []
    for project_id, data in rows.items():
        result.append({
            'project_id': project_id,
            'project_name': data.get('project_name') or '',
            'grams': round(data['grams'], 1),
            'jobs': data['jobs'],
            'source': ', '.join(sorted(data['source'])),
        })
    return sorted(result, key=lambda item: item['grams'], reverse=True)



def register(app):
    bp = Blueprint('stats', __name__)

    @bp.route('/stats')
    def stats():
        today = utc_now().date()
        date_from_str = request.args.get('date_from', '').strip()
        date_to_str   = request.args.get('date_to', '').strip()
        days_param    = request.args.get('days', 0, type=int)

        is_custom_range = False
        if date_from_str and date_to_str:
            try:
                df = datetime.strptime(date_from_str, '%Y-%m-%d').date()
                dt = datetime.strptime(date_to_str, '%Y-%m-%d').date()
                if df <= dt and dt <= today and (dt - df).days < 366:
                    labels = [df + timedelta(days=i) for i in range((dt - df).days + 1)]
                    days = len(labels)
                    is_custom_range = True
                else:
                    date_from_str = date_to_str = ''
            except ValueError:
                date_from_str = date_to_str = ''

        if not is_custom_range:
            days = days_param if days_param in (7, 30, 90, 180) else 30
            labels = _date_labels(days)
            date_from_str = labels[0].isoformat()
            date_to_str = today.isoformat()

        label_keys = [day.isoformat() for day in labels]
        since_dt = datetime.combine(labels[0], datetime.min.time())
        last_30_dt = utc_now() - timedelta(days=30)

        filaments = Filament.query.options(
            joinedload(Filament.brand),
            joinedload(Filament.material),
            joinedload(Filament.color),
        ).order_by(Filament.name.asc()).all()
        filament_name_map = {}
        for filament in filaments:
            filament_name_map[_display_filament_name(filament)] = filament
            filament_name_map[filament.name] = filament

        movement_rows = db.session.query(
            MovementHistory.created_at,
            MovementHistory.action_type,
            MovementHistory.weight,
            MovementHistory.cost,
            MovementHistory.currency,
            MovementHistory.filament_name
        ).filter(
            MovementHistory.created_at >= since_dt
        ).order_by(MovementHistory.created_at.asc()).all()

        usage_daily = {key: 0.0 for key in label_keys}
        purchase_daily = {key: 0.0 for key in label_keys}
        _label_keys_snapshot = list(label_keys)
        material_daily = defaultdict(lambda: {key: 0.0 for key in _label_keys_snapshot})
        purchase_filament_rows = []

        for row in movement_rows:
            if not row.created_at:
                continue
            day_key = row.created_at.date().isoformat()
            if day_key not in usage_daily:
                continue

            filament = filament_name_map.get(row.filament_name)
            material_name = filament.material.name if filament and filament.material else None

            if row.action_type in ('remove', 'bambu_print'):
                usage_daily[day_key] += row.weight
                if material_name:
                    material_daily[material_name][day_key] += row.weight
            elif row.action_type == 'add':
                purchase_daily[day_key] += row.weight
                linked_filament = filament_name_map.get(row.filament_name)
                purchase_filament_rows.append({
                    'date': row.created_at.strftime('%d.%m.%Y'),
                    'filament_id': linked_filament.id if linked_filament else None,
                    'filament_name': row.filament_name,
                    'weight': round(row.weight, 1),
                    'cost': round(row.cost, 2),
                    'currency': row.currency,
                })

        material_totals = []
        for material_name, series in material_daily.items():
            total = sum(series.values())
            if total > 0:
                material_totals.append((material_name, total, series))
        material_totals.sort(key=lambda item: item[1], reverse=True)
        material_totals = material_totals[:5]

        usage_total_period = round(sum(usage_daily.values()), 1)
        purchase_total_period = round(sum(purchase_daily.values()), 1)
        avg_daily_usage_period = round(_safe_divide(usage_total_period, days), 1)

        usage_windows = collect_usage_windows(filaments)
        forecast_rows = []
        for filament in filaments:
            usage_30 = usage_windows.get(filament.id, {}).get('usage_30', 0.0)
            usage_90 = usage_windows.get(filament.id, {}).get('usage_90', 0.0)
            avg_daily = _safe_divide(usage_30, 30)
            days_left = _safe_divide(filament.weight_remaining, avg_daily) if avg_daily > 0 else None
            stock = compute_stock_status(filament, usage_30, usage_90)
            reorder_status = stock['status']

            forecast_rows.append({
                'filament_id': filament.id,
                'filament_name': filament.name,
                'material_name': filament.material.name if filament.material else '',
                'color_name': filament.color.name if filament.color else '',
                'remaining': round(filament.weight_remaining, 1),
                'avg_daily_usage': round(avg_daily, 2),
                'days_left': round(days_left, 1) if days_left is not None else None,
                'reorder_status': reorder_status,
                'min_stock': stock['min_stock'],
                'max_stock': stock['max_stock'],
                'usage_30': stock['usage_30'],
                'usage_90': stock['usage_90'],
                'recommended_grams': stock['recommended_grams'],
                'recommended_spools': stock['recommended_spools'],
                'recommended_order_grams': stock['recommended_order_grams'],
                'recommended_order_price': stock['recommended_order_price'],
                'spool_price': stock['spool_price'],
                'spool_weight': filament.weight_total,
                'reorder_alert_snoozed': bool(filament.reorder_alert_snoozed),
                'shop_url': filament.shop_url or None,
            })

        forecast_rows.sort(
            key=lambda item: item['days_left'] if item['days_left'] is not None else float('inf')
        )

        critical_count = sum(1 for row in forecast_rows if row['reorder_status'] == 'critical')
        warning_count = sum(1 for row in forecast_rows if row['reorder_status'] == 'warning')

        project_rows = _project_usage_rows()[:20]
        top_materials = [
            {'name': name, 'grams': round(total, 1)}
            for name, total, _series in material_totals
        ]
        purchase_recommendations = [row for row in forecast_rows if row['recommended_grams'] > 0]
        purchase_recommendations.sort(
            key=lambda item: (
                0 if item['reorder_status'] == 'critical' else 1,
                -item['recommended_grams'],
                item['filament_name'].lower(),
            )
        )
        purchase_recommendations = purchase_recommendations[:10]

        top_turnover = sorted(
            [{
                'filament_id': filament.id,
                'filament_name': filament.name,
                'brand_name': filament.brand.name if filament.brand else '',
                'material_name': filament.material.name if filament.material else '',
                'usage_30': round(usage_windows.get(filament.id, {}).get('usage_30', 0.0), 1),
                'usage_90': round(usage_windows.get(filament.id, {}).get('usage_90', 0.0), 1),
            } for filament in filaments if usage_windows.get(filament.id, {}).get('usage_30', 0.0) > 0 or usage_windows.get(filament.id, {}).get('usage_90', 0.0) > 0],
            key=lambda item: (item['usage_30'], item['usage_90']),
            reverse=True,
        )[:5]

        quote_map = {}
        for quote in ProjectQuote.query.order_by(ProjectQuote.created_at.desc()).all():
            if quote.project_id not in quote_map:
                quote_map[quote.project_id] = quote

        profitable_projects = []
        setting = AppSetting.query.first()
        kwh_price = setting.kwh_price if setting else 5.0
        printer_power = setting.printer_power if setting else 150

        from models import BambuPrinter
        bambu_powers = {p.device_id: p.power_draw_watts for p in BambuPrinter.query.all() if p.device_id}

        project_ids_with_quotes = list(quote_map.keys())
        projects_to_calc = []
        if project_ids_with_quotes:
            projects_to_calc = (
                Project.query
                .options(
                    joinedload(Project.bambu_jobs).joinedload(BambuPrintJob.materials).joinedload(BambuJobMaterial.filament),
                    joinedload(Project.bambu_jobs).joinedload(BambuPrintJob.filament)
                )
                .filter(Project.id.in_(project_ids_with_quotes))
                .all()
            )

        for project in projects_to_calc:
            quote = quote_map.get(project.id)
            if not quote:
                continue
            actual_cost = 0.0
            for job in project.bambu_jobs:
                if job.materials:
                    for slot in job.materials:
                        if slot.filament and slot.weight_grams and slot.filament.weight_total > 0:
                            actual_cost += (slot.filament.price / slot.filament.weight_total) * slot.weight_grams
                elif job.filament and job.weight_grams and job.filament.weight_total > 0:
                    actual_cost += (job.filament.price / job.filament.weight_total) * job.weight_grams

                job_power = printer_power
                if job.device_id and job.device_id in bambu_powers and bambu_powers[job.device_id] is not None:
                    job_power = bambu_powers[job.device_id]
                actual_cost += ((job.cost_time or 0) / 3600.0) * (job_power / 1000.0) * kwh_price
            profit = round(quote.final_price - actual_cost, 2)
            profitable_projects.append({
                'project_id': project.id,
                'project_name': project.name,
                'quote_price': round(quote.final_price, 2),
                'actual_cost': round(actual_cost, 2),
                'profit': profit,
            })
        profitable_projects.sort(key=lambda item: item['profit'], reverse=True)
        profitable_projects = profitable_projects[:5]

        chart_data = {
            'labels': [day.strftime('%d.%m.') for day in labels],
            'usageDaily': [round(usage_daily[key], 1) for key in label_keys],
            'purchaseDaily': [round(purchase_daily[key], 1) for key in label_keys],
            'materialSeries': [
                {
                    'label': name,
                    'data': [round(series[key], 1) for key in label_keys],
                    'borderColor': CHART_PALETTE[idx % len(CHART_PALETTE)],
                    'backgroundColor': CHART_PALETTE[idx % len(CHART_PALETTE)],
                }
                for idx, (name, _total, series) in enumerate(material_totals)
            ],
            'projectLabels': [row['project_name'] for row in project_rows],
            'projectData': [row['grams'] for row in project_rows],
        }

        summary = {
            'usage_total_period': usage_total_period,
            'purchase_total_period': purchase_total_period,
            'avg_daily_usage_period': avg_daily_usage_period,
            'tracked_filaments': len(filaments),
            'active_projects': Project.query.filter(Project.status != 'DONE').count(),
            'critical_count': critical_count,
            'warning_count': warning_count,
            'reorder_recommendations': len(purchase_recommendations),
        }

        color_map = {}
        for fil in filaments:
            if not fil.color_id:
                continue
            if fil.color_id not in color_map:
                color_map[fil.color_id] = {
                    'color_id': fil.color_id,
                    'color_name': fil.color.name if fil.color else '',
                    'hex_value': (fil.color.hex_value or '#cccccc') if fil.color else '#cccccc',
                    'filaments': [],
                }
            fill_pct = round(fil.weight_remaining / fil.weight_total * 100) if fil.weight_total > 0 else 0
            color_map[fil.color_id]['filaments'].append({
                'id': fil.id,
                'name': fil.name,
                'brand': fil.brand.name if fil.brand else '',
                'material': fil.material.name if fil.material else '',
                'remaining': round(fil.weight_remaining, 1),
                'fill_pct': min(fill_pct, 100),
                'quantity': fil.quantity,
            })
        color_palette = sorted(color_map.values(), key=lambda c: _hex_to_hsl_sort_key(c['hex_value']))
        app_settings = AppSetting.query.first()

        return render_template(
            'stats.html',
            days=days,
            is_custom_range=is_custom_range,
            date_from_str=date_from_str,
            date_to_str=date_to_str,
            today_str=today.isoformat(),
            summary=summary,
            chart_data=json.dumps(chart_data),
            top_materials=top_materials,
            project_rows=project_rows[:20],
            purchase_rows=purchase_filament_rows[:30],
            forecast_rows=forecast_rows[:50],
            purchase_recommendations=purchase_recommendations,
            top_turnover=top_turnover[:20],
            profitable_projects=profitable_projects[:15],
            reorder_status_label_key=_reorder_status_label_key,
            color_palette=color_palette,
            app_settings=app_settings,
        )
    app.register_blueprint(bp)
