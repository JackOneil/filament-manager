"""AJAX API routes for dynamic filtering/sorting without page reload."""
from flask import request, render_template, jsonify
from database import db
from models import Filament, Brand, AppSetting


def register(app):

    @app.route('/api/filaments-list')
    def api_filaments_list():
        filaments_query = Filament.query

        f_brand = request.args.get('brand', '')
        f_material = request.args.get('material', '')
        f_color = request.args.get('color', '')
        sort_by = request.args.get('sort_by', 'name')
        sort_direction = request.args.get('sort_direction', 'asc')
        view_mode = request.args.get('view', 'card')

        if sort_direction not in ['asc', 'desc']:
            sort_direction = 'asc'

        if f_brand:
            filaments_query = filaments_query.filter(Filament.brand_id == f_brand)
        if f_material:
            filaments_query = filaments_query.filter(Filament.material_id == f_material)
        if f_color:
            filaments_query = filaments_query.filter(Filament.color_id == f_color)

        if sort_by == 'brand':
            order_expr = Brand.name
            filaments_query = filaments_query.join(Brand)
        elif sort_by == 'pieces':
            order_expr = Filament.quantity
        elif sort_by == 'remaining':
            order_expr = Filament.weight_remaining
        elif sort_by == 'capacity':
            order_expr = Filament.quantity * Filament.weight_total
        else:
            order_expr = Filament.name

        if sort_direction == 'desc':
            filaments_query = filaments_query.order_by(order_expr.desc())
        else:
            filaments_query = filaments_query.order_by(order_expr.asc())

        page = request.args.get('page', 1, type=int)

        setting = AppSetting.query.first()
        default_per_page = setting.items_per_page if setting else 12
        per_page = request.args.get('per_page', default_per_page, type=int)
        if per_page not in [12, 24, 48, 96]:
            per_page = default_per_page

        filaments_paginated = db.paginate(filaments_query, page=page, per_page=per_page, error_out=False)

        if sort_by == 'percent':
            filaments_paginated.items.sort(
                key=lambda f: f.weight_remaining / (f.quantity * f.weight_total)
                if (f.quantity * f.weight_total) > 0 else 0,
                reverse=(sort_direction == 'desc')
            )

        if view_mode == 'card':
            html = render_template('_filament_cards.html', filaments=filaments_paginated.items)
        else:
            html = render_template('_filament_list_rows.html', filaments=filaments_paginated.items)

        return jsonify({
            'html': html,
            'total_pages': filaments_paginated.pages,
            'current_page': page,
            'has_next': filaments_paginated.has_next,
            'has_prev': filaments_paginated.has_prev,
        })
