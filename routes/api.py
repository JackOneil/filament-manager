"""AJAX API routes for dynamic filtering/sorting without page reload."""
from flask import request, render_template, jsonify, Blueprint
from sqlalchemy import select
from sqlalchemy.orm import joinedload
from auth import get_current_user, is_admin
from database import db
from models import Filament, Brand, Project, PrusaPrinter, BambuPrinter
from utils import collect_usage_windows, collect_sparkline_data, compute_stock_status, escape_like, generate_sparkline_svg_path, get_filament_tags, get_live_printers, get_settings, translate


def register(app):
    bp = Blueprint('api', __name__)

    @bp.route('/api/filaments-list')
    def api_filaments_list():
        user = get_current_user()
        inventory_read_only = bool(user and not is_admin(user))
        filaments_query = select(Filament).options(
            joinedload(Filament.brand),
            joinedload(Filament.material),
            joinedload(Filament.color)
        )

        f_brand = request.args.get('brand', '')
        f_material = request.args.get('material', '')
        f_color = request.args.get('color', '')
        f_tag = request.args.get('tag', '').strip()
        sort_by = request.args.get('sort_by', 'name')
        sort_direction = request.args.get('sort_direction', 'asc')
        quick_filter = request.args.get('quick_filter', '').strip()
        view_mode = 'list' if inventory_read_only else request.args.get('view', 'card')

        if sort_direction not in ['asc', 'desc']:
            sort_direction = 'asc'

        if f_brand:
            filaments_query = filaments_query.where(Filament.brand_id == f_brand)
        if f_material:
            filaments_query = filaments_query.where(Filament.material_id == f_material)
        if f_color:
            filaments_query = filaments_query.where(Filament.color_id == f_color)
        if f_tag:
            filaments_query = filaments_query.where(Filament.tag_text.ilike(f'%{escape_like(f_tag)}%', escape='\\'))

        # Quick server-side filters (computed from DB columns, no post-load filtering needed)
        if quick_filter == 'low_stock':
            # quantity == 0 OR remaining/capacity < 20 %
            filaments_query = filaments_query.where(
                db.or_(
                    Filament.quantity == 0,
                    db.and_(
                        Filament.quantity * Filament.weight_total > 0,
                        Filament.weight_remaining / (Filament.quantity * Filament.weight_total) < 0.20,
                    ),
                )
            )
        elif quick_filter == 'reorder':
            # has a min_stock threshold AND remaining is below it
            filaments_query = filaments_query.where(
                Filament.min_stock_grams > 0,
                Filament.weight_remaining < Filament.min_stock_grams,
                Filament.reorder_alert_snoozed == False,  # noqa: E712
            )

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
                else_=0
            )
        else:
            order_expr = Filament.name

        if sort_direction == 'desc':
            filaments_query = filaments_query.order_by(order_expr.desc())
        else:
            filaments_query = filaments_query.order_by(order_expr.asc())

        page = request.args.get('page', 1, type=int)

        setting = get_settings()
        default_per_page = setting.items_per_page if setting else 12
        per_page = request.args.get('per_page', default_per_page, type=int)
        if per_page not in [12, 24, 48, 96]:
            per_page = default_per_page

        filaments_paginated = db.paginate(filaments_query, page=page, per_page=per_page, error_out=False)
        usage_map = collect_usage_windows(filaments_paginated.items)
        sparkline_data = collect_sparkline_data(filaments_paginated.items)
        
        # Decorate filaments with pre-computed values (Rule 3.4, 3.5)
        decorated_filaments = []
        for fil in filaments_paginated.items:
            metrics = compute_stock_status(
                fil,
                usage_map.get(fil.id, {}).get('usage_30', 0.0),
                usage_map.get(fil.id, {}).get('usage_90', 0.0),
            )
            fil.stock_metrics = metrics
            fil.tag_list = get_filament_tags(fil)
            
            # Pre-compute capacity and percentage
            capacity_all = fil.quantity * fil.weight_total
            fil._capacity_all = capacity_all
            fil._pct = round(fil.weight_remaining / capacity_all * 100) if capacity_all > 0 else 0
            
            # Pre-compute SVG sparkline path
            if fil.id in sparkline_data:
                polyline_pts, fill_pts = generate_sparkline_svg_path(sparkline_data[fil.id])
                fil._sparkline_polyline = polyline_pts
                fil._sparkline_fill = fill_pts
            else:
                fil._sparkline_polyline = ''
                fil._sparkline_fill = ''
            
            decorated_filaments.append(fil)

        if view_mode == 'card':
            html = render_template(
                '_filament_cards.html',
                filaments=decorated_filaments,
                app_settings=setting,
                inventory_read_only=inventory_read_only,
                sparkline_data=sparkline_data,
            )
        elif view_mode == 'compact':
            html = render_template(
                '_filament_compact.html',
                filaments=decorated_filaments,
                app_settings=setting,
                inventory_read_only=inventory_read_only,
                sparkline_data=sparkline_data,
            )
        else:
            html = render_template(
                '_filament_list_rows.html',
                filaments=decorated_filaments,
                app_settings=setting,
                inventory_read_only=inventory_read_only,
                sparkline_data=sparkline_data,
            )

        return jsonify({
            'html': html,
            'total_pages': filaments_paginated.pages,
            'current_page': page,
            'has_next': filaments_paginated.has_next,
            'has_prev': filaments_paginated.has_prev,
        })

    @bp.route('/api/search')
    def api_search():
        from flask import url_for
        q = request.args.get('q', '').strip()
        if not q:
            return jsonify({'results': []})
            
        results = []
        user = get_current_user()
        is_adm = is_admin(user) if user else False
        
        # 1. Filaments
        fil_query = Filament.query.options(
            joinedload(Filament.brand), joinedload(Filament.material), joinedload(Filament.color)
        ).filter(
            db.or_(
                Filament.name.ilike(f'%{escape_like(q)}%', escape='\\'),
                Filament.tag_text.ilike(f'%{escape_like(q)}%', escape='\\')
            )
        ).limit(10).all()
        
        for f in fil_query:
            results.append({
                'id': f'fil_{f.id}', 'type': 'filament', 'title': f.name,
                'subtitle': f"{f.brand.name if f.brand else ''} · {f.material.name if f.material else ''}",
                'url': url_for('filament_detail', id=f.id) if is_adm else url_for('filaments_index', tag=f.name),
                'icon': 'fa-solid fa-layer-group', 'color': f.color.hex_value if f.color else '#cbd5e1'
            })
            
        # 2. Projects
        proj_query = Project.query.filter(
            db.or_(
                Project.name.ilike(f'%{escape_like(q)}%', escape='\\'),
                Project.client_name.ilike(f'%{escape_like(q)}%', escape='\\'),
                Project.tag_text.ilike(f'%{escape_like(q)}%', escape='\\')
            )
        )
        if not is_adm and user:
            proj_query = proj_query.filter(Project.owner_user_id == user.id)
            
        for p in proj_query.limit(10).all():
            results.append({
                'id': f'proj_{p.id}', 'type': 'project', 'title': p.name,
                'subtitle': p.client_name or translate('project_client_missing_label'),
                'url': url_for('project_detail', id=p.id),
                'icon': 'fa-solid fa-diagram-project', 'color': '#3b82f6'
            })
            
        # 3. Printers
        if is_adm:
            prusa_query = PrusaPrinter.query.filter(
                db.or_(PrusaPrinter.name.ilike(f'%{escape_like(q)}%', escape='\\'), PrusaPrinter.printer_model.ilike(f'%{escape_like(q)}%', escape='\\'))
            ).limit(5).all()
            for p in prusa_query:
                results.append({
                    'id': f'prusa_{p.id}', 'type': 'printer', 'title': p.name,
                    'subtitle': f"Prusa {p.printer_model or ''}",
                    'url': url_for('prusa_jobs'),
                    'icon': 'fa-solid fa-network-wired', 'color': '#f97316'
                })
                
            bambu_query = BambuPrinter.query.filter(
                db.or_(BambuPrinter.name.ilike(f'%{escape_like(q)}%', escape='\\'), BambuPrinter.printer_model.ilike(f'%{escape_like(q)}%', escape='\\'))
            ).limit(5).all()
            for b in bambu_query:
                results.append({
                    'id': f'bambu_{b.id}', 'type': 'printer', 'title': b.name,
                    'subtitle': f"Bambu {b.printer_model or ''}",
                    'url': url_for('bambu_jobs'),
                    'icon': 'fa-solid fa-cloud', 'color': '#14b8a6'
                })
                
        return jsonify({'results': results})

    @bp.route('/api/overview/live-printers')
    def api_live_printers_partial():
        user = get_current_user()
        if not user or not is_admin(user):
            from flask import abort
            abort(403)
        live = get_live_printers()
        html = render_template('_live_printers_partial.html', live_printers=live)
        return jsonify({'html': html})

    app.register_blueprint(bp)
