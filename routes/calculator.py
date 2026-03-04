"""Calculator routes: print cost estimation and history."""
from flask import render_template, request, redirect, url_for
from database import db
from models import Filament, AppSetting, PrintHistory
from utils import get_current_currency


def register(app):

    @app.route('/calculator', methods=['GET', 'POST'])
    def calculator():
        filaments = Filament.query.all()
        setting = AppSetting.query.first()
        result = None

        if request.method == 'POST':
            filament_id = request.form.get('filament_id')
            weight = float(request.form.get('weight', 0))
            print_time = float(request.form.get('print_time', 0))
            kwh_price = float(request.form.get('kwh_price', 0))
            printer_power = int(request.form.get('printer_power', 0))

            if setting:
                setting.kwh_price = kwh_price
                setting.printer_power = printer_power
                db.session.commit()

            if filament_id and weight > 0:
                filament = db.session.get(Filament, filament_id)
                if filament and filament.weight_total > 0:
                    cost_per_gram = filament.price / filament.weight_total
                    material_cost = cost_per_gram * weight
                    electricity_cost = print_time * (printer_power / 1000.0) * kwh_price
                    total_cost = material_cost + electricity_cost
                    currency = get_current_currency()

                    result = {
                        'filament': filament,
                        'weight': weight,
                        'print_time': print_time,
                        'material_cost': material_cost,
                        'electricity_cost': electricity_cost,
                        'total_cost': total_cost,
                        'cost_per_gram': cost_per_gram,
                        'currency': currency,
                    }

                    db.session.add(PrintHistory(
                        filament_name=f"{filament.name} | {filament.brand.name} {filament.material.name}",
                        weight=weight,
                        total_cost=total_cost,
                    ))
                    app.logger.debug(
                        f"Print calculated: {filament.name}, weight={weight}g, "
                        f"material={material_cost:.2f}, elec={electricity_cost:.2f}, total={total_cost:.2f}"
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
            filaments=filaments, result=result, setting=setting,
            histories=histories_paginated, per_page=per_page,
        )

    @app.route('/calculator/history/<int:id>/delete', methods=['POST'])
    def delete_history(id):
        record = db.get_or_404(PrintHistory, id)
        app.logger.debug(f"Deleted print history: {record.filament_name}, cost: {record.total_cost}")
        db.session.delete(record)
        db.session.commit()
        return redirect(url_for('calculator'))
