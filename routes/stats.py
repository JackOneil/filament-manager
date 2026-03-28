"""Statistics dashboard: usage charts, project summaries, and stock forecast."""
from collections import defaultdict
from datetime import datetime, timedelta
import json

from flask import render_template, request
from sqlalchemy.orm import joinedload

from database import db
from models import AppSetting, BambuPrintJob, Filament, MovementHistory, Project, ProjectFilament, ProjectQuote
from utils import collect_usage_windows, compute_stock_status


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
        for project in Project.query.all():
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
                actual_cost += ((job.cost_time or 0) / 3600.0) * (printer_power / 1000.0) * kwh_price
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

        return render_template(
            'stats.html',
            days=days,
            summary=summary,
            chart_data=json.dumps(chart_data),
            top_materials=top_materials,
            project_rows=project_rows,
            purchase_rows=purchase_filament_rows[:10],
            forecast_rows=forecast_rows[:12],
            purchase_recommendations=purchase_recommendations,
            top_turnover=top_turnover,
            profitable_projects=profitable_projects,
        )
