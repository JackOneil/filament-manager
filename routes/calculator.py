"""Calculator routes: print cost estimation and history."""
from flask import render_template, request, redirect, url_for
from database import db
from models import Filament, AppSetting, PrintHistory, Project, ProjectQuote
from utils import get_current_currency


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


def register(app):

    @app.route('/calculator', methods=['GET', 'POST'])
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

                    app.logger.debug(
                        f"Print calculated: {filament.name}, weight={weight}g, "
                        f"material={result['material_cost']:.2f}, elec={result['electricity_cost']:.2f}, total={result['total_cost']:.2f}"
                    )
                    db.session.commit()

        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 10, type=int)
        if per_page not in [10, 20, 50, 100]:
            per_page = 10

        histories_paginated = db.paginate(
            PrintHistory.query.order_by(PrintHistory.created_at.desc()),
            page=page, per_page=per_page, error_out=False,
        )

        return render_template(
            'calculator.html',
            filaments=filaments, projects=projects, result=result, saved_quote=saved_quote, setting=setting,
            histories=histories_paginated, per_page=per_page,
        )

    @app.route('/calculator/history/<int:id>/delete', methods=['POST'])
    def delete_history(id):
        record = db.get_or_404(PrintHistory, id)
        app.logger.debug(f"Deleted print history: {record.filament_name}, cost: {record.total_cost}")
        db.session.delete(record)
        db.session.commit()
        return redirect(url_for('calculator'))

    @app.route('/calculator/quote/<int:id>/delete', methods=['POST'])
    def delete_quote(id):
        quote = db.get_or_404(ProjectQuote, id)
        project_id = quote.project_id
        db.session.delete(quote)
        db.session.commit()
        return redirect(url_for('project_detail', id=project_id, tab='materials'))

    @app.route('/calculator/quote/<int:id>/export')
    def export_quote(id):
        quote = db.get_or_404(ProjectQuote, id)
        return render_template('quote_export.html', quote=quote)
