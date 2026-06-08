"""Calculator routes: print cost estimation and history."""
from flask import render_template, request, redirect, url_for, abort, Blueprint
from database import db
from models import Filament, AppSetting, PrintHistory, Project, ProjectQuote
from utils import get_current_currency, translate, utc_now, safe_commit


def _build_filament_label(filament):
    return f"{filament.name} | {filament.brand.name} {filament.material.name}"


def _calculate_quote(filament, weight, print_time, margin_percent, setting):
    kwh_price = setting.kwh_price if setting else 5.0
    printer_power = setting.printer_power if setting else 150
    cost_per_gram = filament.price / filament.weight_total if filament.weight_total > 0 else 0.0
    material_cost = cost_per_gram * weight
    electricity_cost = print_time * (printer_power / 1000.0) * kwh_price
    base_cost = material_cost + electricity_cost
    margin_amount = base_cost * (margin_percent / 100.0)
    total_cost = base_cost + margin_amount

    return {
        'filament': filament,
        'filament_name': _build_filament_label(filament),
        'weight': weight,
        'print_time': print_time,
        'material_cost': material_cost,
        'electricity_cost': electricity_cost,
        'base_cost': base_cost,
        'margin_percent': margin_percent,
        'margin_amount': margin_amount,
        'total_cost': total_cost,
        'cost_per_gram': cost_per_gram,
        'currency': get_current_currency(),
    }


def _calculate_project_quote(project, margin_percent, setting):
    """
    Calculate a multi-material quote for a project.

    Data source priority:
      1. Actual Bambu print jobs (per-AMS-slot BambuJobMaterial with weight_grams & mapped filament)
      2. Actual Prusa print jobs (PrusaPrintJob with weight_grams & mapped filament)
      3. Planned ProjectFilament entries (fallback when no real jobs exist)

    Returns a dict with per-material lines, aggregate totals, source metadata.
    """
    kwh_price = setting.kwh_price if setting else 5.0
    printer_power = setting.printer_power if setting else 150
    currency = get_current_currency()

    # ── Collect real job data ────────────────────────────────────────────────
    # Aggregate per filament_id: {filament_id: {'filament': obj, 'weight': float, 'color_hex': str|None}}
    real_by_filament = {}  # filament_id → aggregated slot
    total_cost_time_seconds = 0

    bambu_jobs = list(getattr(project, 'bambu_jobs', []) or [])
    prusa_jobs = list(getattr(project, 'prusa_jobs', []) or [])

    for job in bambu_jobs:
        total_cost_time_seconds += job.cost_time or 0
        slots = list(getattr(job, 'materials', []) or [])
        if slots:
            for slot in slots:
                if not slot.weight_grams or slot.weight_grams <= 0:
                    continue
                if slot.filament_id and slot.filament:
                    key = slot.filament_id
                    if key not in real_by_filament:
                        real_by_filament[key] = {
                            'filament': slot.filament,
                            'weight': 0.0,
                            'color_hex': slot.color_hex or (slot.filament.color.hex_value if slot.filament.color else None),
                        }
                    real_by_filament[key]['weight'] += slot.weight_grams
                else:
                    # Slot not mapped to a filament — aggregate under a "unknown" key using job filament
                    if slot.weight_grams and slot.weight_grams > 0:
                        key = f'bambu_unmapped_{slot.color_hex or slot.material_name or "?"}'
                        if key not in real_by_filament:
                            real_by_filament[key] = {
                                'filament': job.filament,  # may be None
                                'weight': 0.0,
                                'color_hex': slot.color_hex,
                                'label': slot.material_name or slot.color_hex or 'Unknown',
                                'unmapped': True,
                            }
                        real_by_filament[key]['weight'] += slot.weight_grams
        else:
            # No per-slot breakdown — use job-level filament + weight
            if job.filament_id and job.filament and job.weight_grams and job.weight_grams > 0:
                key = job.filament_id
                if key not in real_by_filament:
                    real_by_filament[key] = {
                        'filament': job.filament,
                        'weight': 0.0,
                        'color_hex': job.filament.color.hex_value if job.filament.color else None,
                    }
                real_by_filament[key]['weight'] += job.weight_grams

    for job in prusa_jobs:
        total_cost_time_seconds += job.cost_time or 0
        if job.filament_id and job.filament and job.weight_grams and job.weight_grams > 0:
            key = job.filament_id
            if key not in real_by_filament:
                real_by_filament[key] = {
                    'filament': job.filament,
                    'weight': 0.0,
                    'color_hex': job.filament.color.hex_value if job.filament.color else None,
                }
            real_by_filament[key]['weight'] += job.weight_grams

    # ── Choose data source ───────────────────────────────────────────────────
    use_jobs = bool(real_by_filament)
    data_source = 'jobs' if use_jobs else 'planned'

    if use_jobs:
        print_time_hours = total_cost_time_seconds / 3600.0
        raw_lines = list(real_by_filament.values())
    else:
        # Fallback: planned filaments
        print_time_hours = (project.estimated_print_time or 0) / 60.0
        raw_lines = []
        for pf in project.filaments:
            f = pf.filament
            if not f or pf.estimated_weight <= 0:
                continue
            raw_lines.append({
                'filament': f,
                'weight': pf.estimated_weight,
                'color_hex': f.color.hex_value if f.color else None,
            })

    # ── Build breakdown lines ────────────────────────────────────────────────
    lines = []
    total_material_cost = 0.0
    total_weight = 0.0

    for entry in raw_lines:
        weight = entry['weight']
        f = entry.get('filament')
        unmapped = entry.get('unmapped', False)

        if weight <= 0:
            continue

        if f and f.weight_total > 0:
            cost_per_gram = f.price / f.weight_total
            material_cost = cost_per_gram * weight
            name = f.name
            brand_material = f'{f.brand.name} · {f.material.name}' if f.brand and f.material else ''
        else:
            cost_per_gram = 0.0
            material_cost = 0.0
            name = entry.get('label', translate('calc_unknown_filament'))
            brand_material = '—'

        total_material_cost += material_cost
        total_weight += weight
        lines.append({
            'filament': f,
            'name': name,
            'brand_material': brand_material,
            'weight': weight,
            'cost_per_gram': cost_per_gram,
            'material_cost': material_cost,
            'color_hex': entry.get('color_hex'),
            'unmapped': unmapped,
        })

    # ── Totals ───────────────────────────────────────────────────────────────
    electricity_cost = print_time_hours * (printer_power / 1000.0) * kwh_price
    base_cost = total_material_cost + electricity_cost
    margin_amount = base_cost * (margin_percent / 100.0)
    total_cost = base_cost + margin_amount

    return {
        'project': project,
        'lines': lines,
        'data_source': data_source,           # 'jobs' | 'planned'
        'print_time_hours': print_time_hours,
        'total_weight': total_weight,
        'total_material_cost': total_material_cost,
        'electricity_cost': electricity_cost,
        'base_cost': base_cost,
        'margin_percent': margin_percent,
        'margin_amount': margin_amount,
        'total_cost': total_cost,
        'currency': currency,
    }


def register(app):
    bp = Blueprint('calculator', __name__)

    @bp.route('/calculator', methods=['GET', 'POST'])
    def calculator():
        filaments = Filament.query.all()
        projects = Project.query.order_by(Project.name.asc()).all()
        setting = AppSetting.query.first()
        result = None
        saved_quote = None

        if request.method == 'POST':
            filament_id = request.form.get('filament_id', type=int)
            project_id = request.form.get('project_id', type=int)
            weight = float(request.form.get('weight', 0) or 0)
            print_time = float(request.form.get('print_time', 0) or 0)
            margin_percent = float(request.form.get('margin_percent', 0) or 0)
            action = request.form.get('action', 'calculate')

            if filament_id and weight > 0:
                filament = db.session.get(Filament, filament_id)
                if filament and filament.weight_total > 0:
                    result = _calculate_quote(filament, weight, print_time, margin_percent, setting)

                    db.session.add(PrintHistory(
                        filament_name=result['filament_name'],
                        weight=weight,
                        total_cost=result['total_cost'],
                    ))

                    if action == 'save_quote' and project_id:
                        project = db.session.get(Project, project_id)
                        if project:
                            saved_quote = ProjectQuote(
                                project_id=project.id,
                                filament_id=filament.id,
                                filament_name=result['filament_name'],
                                weight=weight,
                                print_time=print_time,
                                material_cost=result['material_cost'],
                                electricity_cost=result['electricity_cost'],
                                base_cost=result['base_cost'],
                                margin_percent=margin_percent,
                                margin_amount=result['margin_amount'],
                                final_price=result['total_cost'],
                                currency=result['currency'],
                            )
                            db.session.add(saved_quote)

                    try:
                        safe_commit()
                        app.logger.debug(
                            f"Print calculated: {filament.name}, weight={weight}g, "
                            f"material={result['material_cost']:.2f}, elec={result['electricity_cost']:.2f}, total={result['total_cost']:.2f}"
                        )
                    except Exception:
                        db.session.rollback()
                        app.logger.exception("Failed to save print calculation")

        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 10, type=int)
        if per_page not in [10, 20, 50, 100]:
            per_page = 10

        histories_paginated = db.paginate(
            PrintHistory.query.order_by(PrintHistory.created_at.desc()).statement,
            page=page, per_page=per_page, error_out=False,
        )

        return render_template(
            'calculator.html',
            filaments=filaments, projects=projects, result=result, saved_quote=saved_quote, setting=setting,
            histories=histories_paginated, per_page=per_page,
        )

    # ── Project-mode calculator ──────────────────────────────────────────────
    @bp.route('/calculator/project/<int:project_id>', methods=['GET', 'POST'])
    def calculator_project(project_id):
        """
        Project-mode calculator: all inputs (filaments, weights, print time)
        are pulled from the project. Only the margin can be adjusted.
        On POST the quote is saved and the user is redirected back to the project.
        """
        project = db.get_or_404(Project, project_id)
        setting = AppSetting.query.first()

        margin_percent = float(request.form.get('margin_percent', 20) or 20)
        if request.method == 'GET':
            margin_percent = float(request.args.get('margin', 20) or 20)

        project_result = _calculate_project_quote(project, margin_percent, setting)
        saved_quotes = []

        if request.method == 'POST' and project_result['lines']:
            # Aggregate into a single quote for the entire project
            labels = []
            for line in project_result['lines']:
                f_name = line.get('name') or (line.get('filament').name if line.get('filament') else translate('calc_unknown'))
                labels.append(f"{f_name} ({line['weight']:.0f}g)")
            
            combined_name = " + ".join(labels)
            if len(combined_name) > 255:
                combined_name = combined_name[:250] + "..."

            # If there's only one mapped material, link it; otherwise None
            fid = project_result['lines'][0]['filament'].id if len(project_result['lines']) == 1 and project_result['lines'][0].get('filament') else None

            q = ProjectQuote(
                project_id=project.id,
                filament_id=fid,
                filament_name=combined_name,
                weight=project_result['total_weight'],
                print_time=project_result['print_time_hours'],
                material_cost=round(project_result['total_material_cost'], 4),
                electricity_cost=round(project_result['electricity_cost'], 4),
                base_cost=round(project_result['base_cost'], 4),
                margin_percent=margin_percent,
                margin_amount=round(project_result['margin_amount'], 4),
                final_price=round(project_result['total_cost'], 4),
                currency=project_result['currency'],
            )
            db.session.add(q)
            saved_quotes = [q]

            safe_commit()
            app.logger.info(
                f"Project quote saved: project_id={project.id}, lines={len(saved_quotes)}, "
                f"total={project_result['total_cost']:.2f} {project_result['currency']}"
            )
            return redirect(url_for('project_detail', id=project.id, tab='materials'))

        return render_template(
            'calculator_project.html',
            project=project,
            project_result=project_result,
            setting=setting,
            margin_percent=margin_percent,
        )

    @bp.route('/calculator/history/<int:id>/delete', methods=['POST'])
    def delete_history(id):
        record = db.get_or_404(PrintHistory, id)
        app.logger.debug(f"Deleted print history: {record.filament_name}, cost: {record.total_cost}")
        db.session.delete(record)
        safe_commit()
        return redirect(url_for('calculator'))

    @bp.route('/calculator/quote/<int:id>/delete', methods=['POST'])
    def delete_quote(id):
        quote = db.get_or_404(ProjectQuote, id)
        project_id = quote.project_id
        db.session.delete(quote)
        safe_commit()
        return redirect(url_for('project_detail', id=project_id, tab='materials'))

    @bp.route('/calculator/quote/<int:id>/export')
    def export_quote(id):
        quote = db.get_or_404(ProjectQuote, id)
        settings = AppSetting.query.first()

        # Auto-assign a sequential invoice number on first view
        if not quote.invoice_number:
            prefix = (settings.invoice_prefix or 'FV') if settings else 'FV'
            counter = ((settings.invoice_counter or 0) + 1) if settings else 1
            quote.invoice_number = f'{prefix}-{utc_now().year}{counter:04d}'
            if settings:
                settings.invoice_counter = counter
            safe_commit()

        # Provide the next suggested number for display (not yet claimed)
        prefix = (settings.invoice_prefix or 'FV') if settings else 'FV'
        counter = (settings.invoice_counter or 0) if settings else 0
        suggested_invoice_number = f'{prefix}-{utc_now().year}{counter + 1:04d}'

        return render_template(
            'quote_export.html',
            quote=quote,
            settings=settings,
            suggested_invoice_number=suggested_invoice_number,
        )
    app.register_blueprint(bp)
