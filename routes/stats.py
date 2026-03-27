"""Statistics dashboard: usage charts, project summaries, and stock forecast."""
from collections import defaultdict
from datetime import datetime, timedelta
import json

from flask import render_template, request
from sqlalchemy.orm import joinedload

from database import db
from models import BambuPrintJob, Filament, MovementHistory, Project, ProjectFilament


CHART_PALETTE = [
    '#2563eb', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6',
    '#06b6d4', '#84cc16', '#f97316', '#ec4899', '#14b8a6',
]


def _display_filament_name(filament):
    brand_name = filament.brand.name if filament.brand else ''
    mat_name = filament.material.name if filament.material else ''
    return f"{filament.name} | {brand_name} {mat_name}".strip(" | ")


def _date_labels(days):
    today = datetime.utcnow().date()
    return [today - timedelta(days=offset) for offset in range(days - 1, -1, -1)]


def _empty_series(days):
    return {day.isoformat(): 0.0 for day in _date_labels(days)}


def _safe_divide(numerator, denominator):
    if not denominator:
        return 0.0
    return numerator / denominator


def _project_usage_rows():
    rows = defaultdict(lambda: {'grams': 0.0, 'jobs': 0, 'source': set()})

    bambu_jobs = BambuPrintJob.query.options(
        joinedload(BambuPrintJob.project),
        joinedload(BambuPrintJob.materials),
    ).filter(BambuPrintJob.project_id.is_not(None)).all()

    for job in bambu_jobs:
        if not job.project:
            continue
        grams = 0.0
        if len(job.materials) > 1:
            grams = sum((mat.weight_grams or 0.0) for mat in job.materials if mat.deducted)
        elif job.deducted:
            grams = job.weight_grams or 0.0
        elif job.materials:
            grams = sum((mat.weight_grams or 0.0) for mat in job.materials if mat.deducted)

        if grams <= 0:
            continue

        row = rows[job.project.name]
        row['grams'] += grams
        row['jobs'] += 1
        row['source'].add('bambu')

    manual_links = ProjectFilament.query.options(
        joinedload(ProjectFilament.project)
    ).filter(ProjectFilament.is_used.is_(True)).all()

    for link in manual_links:
        if not link.project or link.estimated_weight <= 0:
            continue
        row = rows[link.project.name]
        row['grams'] += link.estimated_weight
        row['source'].add('manual')

    result = []
    for project_name, data in rows.items():
        result.append({
            'project_name': project_name,
            'grams': round(data['grams'], 1),
            'jobs': data['jobs'],
            'source': ', '.join(sorted(data['source'])),
        })
    return sorted(result, key=lambda item: item['grams'], reverse=True)


def register(app):

    @app.route('/stats')
    def stats():
        days = request.args.get('days', 30, type=int)
        if days not in (7, 30, 90, 180):
            days = 30

        labels = _date_labels(days)
        label_keys = [day.isoformat() for day in labels]
        since_dt = datetime.combine(labels[0], datetime.min.time())
        last_30_dt = datetime.utcnow() - timedelta(days=30)

        filaments = Filament.query.options(
            joinedload(Filament.brand),
            joinedload(Filament.material),
            joinedload(Filament.color),
        ).order_by(Filament.name.asc()).all()
        filament_name_map = {_display_filament_name(f): f for f in filaments}

        movement_rows = MovementHistory.query.filter(
            MovementHistory.created_at >= since_dt
        ).order_by(MovementHistory.created_at.asc()).all()

        usage_daily = _empty_series(days)
        purchase_daily = _empty_series(days)
        material_daily = defaultdict(lambda: _empty_series(days))
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
                purchase_filament_rows.append({
                    'date': row.created_at.strftime('%d.%m.%Y'),
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

        forecast_rows = []
        for filament in filaments:
            display_name = _display_filament_name(filament)
            last_30_usage = MovementHistory.query.with_entities(
                db.func.coalesce(db.func.sum(MovementHistory.weight), 0.0)
            ).filter(
                MovementHistory.filament_name == display_name,
                MovementHistory.action_type.in_(('remove', 'bambu_print')),
                MovementHistory.created_at >= last_30_dt,
            ).scalar() or 0.0

            avg_daily = _safe_divide(last_30_usage, 30)
            days_left = _safe_divide(filament.weight_remaining, avg_daily) if avg_daily > 0 else None

            if days_left is None:
                reorder_status = 'stable'
            elif days_left <= 7:
                reorder_status = 'critical'
            elif days_left <= 21:
                reorder_status = 'warning'
            else:
                reorder_status = 'stable'

            forecast_rows.append({
                'filament_name': filament.name,
                'material_name': filament.material.name if filament.material else '',
                'color_name': filament.color.name if filament.color else '',
                'remaining': round(filament.weight_remaining, 1),
                'avg_daily_usage': round(avg_daily, 2),
                'days_left': round(days_left, 1) if days_left is not None else None,
                'reorder_status': reorder_status,
            })

        forecast_rows.sort(
            key=lambda item: item['days_left'] if item['days_left'] is not None else float('inf')
        )

        critical_count = sum(1 for row in forecast_rows if row['reorder_status'] == 'critical')
        warning_count = sum(1 for row in forecast_rows if row['reorder_status'] == 'warning')

        project_rows = _project_usage_rows()[:8]
        top_materials = [
            {'name': name, 'grams': round(total, 1)}
            for name, total, _series in material_totals
        ]

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
        }

        return render_template(
            'stats.html',
            days=days,
            summary=summary,
            chart_data=json.dumps(chart_data),
            top_materials=top_materials,
            project_rows=project_rows,
            purchase_rows=purchase_filament_rows[:10],
            forecast_rows=forecast_rows[:12],
        )
