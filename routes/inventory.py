"""Inventory routes: listing, CRUD, spool management."""
import math
from flask import render_template, request, redirect, url_for
from database import db
from models import Filament, Brand, Color, Material, AppSetting
from utils import log_movement


def register(app):

    @app.route('/')
    def index():
        filaments_query = Filament.query

        f_brand = request.args.get('brand', '')
        f_material = request.args.get('material', '')
        f_color = request.args.get('color', '')
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
        if view_mode_param and view_mode_param in ['card', 'list']:
            setting.view_mode = view_mode_param
            db.session.commit()
            app.logger.debug(f"View mode changed to: {view_mode_param}")

        view_mode = setting.view_mode

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

        all_filtered = filaments_query.all()
        total_spools = sum(f.quantity for f in all_filtered)
        total_remaining_g = sum(f.weight_remaining for f in all_filtered)
        total_value = sum(
            (f.price / f.weight_total * f.weight_remaining) if f.weight_total > 0 else 0
            for f in all_filtered
        )

        filaments_paginated = db.paginate(filaments_query, page=page, per_page=per_page, error_out=False)

        if sort_by == 'percent':
            filaments_paginated.items.sort(
                key=lambda f: f.weight_remaining / (f.quantity * f.weight_total)
                if (f.quantity * f.weight_total) > 0 else 0,
                reverse=(sort_direction == 'desc')
            )

        brands = Brand.query.order_by(Brand.name).all()
        materials = Material.query.order_by(Material.name).all()
        colors = Color.query.order_by(Color.name).all()

        app.logger.debug(
            f"Index viewed: view_mode={view_mode}, page={page}, per_page={per_page}, "
            f"sort_by={sort_by}, sort_direction={sort_direction}, "
            f"filters: brand={f_brand}, material={f_material}, color={f_color}"
        )

        return render_template(
            'index.html',
            filaments=filaments_paginated,
            stats={"spools": total_spools, "remaining": total_remaining_g, "value": total_value},
            brands=brands, materials=materials, colors=colors,
            f_brand=f_brand, f_material=f_material, f_color=f_color,
            view_mode=view_mode, per_page=per_page,
            sort_by=sort_by, sort_direction=sort_direction,
        )

    @app.route('/add', methods=['GET', 'POST'])
    def add():
        if request.method == 'POST':
            name = request.form.get('name', '').strip()
            brand_id = request.form['brand_id']
            color_id = request.form['color_id']
            material_id = request.form['material_id']
            weight_total = float(request.form['weight_total'])
            quantity = int(request.form['quantity'])
            weight_remaining = float(request.form.get('weight_remaining', weight_total * quantity))
            price = float(request.form['price'])

            if not name:
                brand = db.session.get(Brand, brand_id)
                material = db.session.get(Material, material_id)
                color = db.session.get(Color, color_id)
                name = f"{brand.name} {material.name} {color.name}"

            new_fil = Filament(
                name=name, brand_id=brand_id, color_id=color_id, material_id=material_id,
                weight_total=weight_total, weight_remaining=weight_remaining,
                price=price, quantity=quantity,
            )
            db.session.add(new_fil)
            db.session.flush()
            log_movement(new_fil, 'add', weight_remaining)
            db.session.commit()
            app.logger.debug(f"Added new filament: {name}")
            return redirect(url_for('index'))

        brands = Brand.query.order_by(Brand.name).all()
        colors = Color.query.order_by(Color.name).all()
        materials = Material.query.order_by(Material.name).all()
        return render_template('add.html', brands=brands, colors=colors, materials=materials)

    @app.route('/edit/<int:id>', methods=['GET', 'POST'])
    def edit(id):
        filament = db.get_or_404(Filament, id)
        if request.method == 'POST':
            old_weight = filament.weight_remaining
            old_name = filament.name

            filament.name = request.form['name']
            filament.weight_remaining = float(request.form['weight_remaining'])
            filament.price = float(request.form['price'])
            filament.quantity = int(request.form['quantity'])

            weight_diff = filament.weight_remaining - old_weight
            if weight_diff > 0:
                log_movement(filament, 'add', weight_diff)
            elif weight_diff < 0:
                log_movement(filament, 'remove', abs(weight_diff))

            app.logger.debug(
                f"Edited filament: {old_name} -> {filament.name} "
                f"(weight: {old_weight}g -> {filament.weight_remaining}g)"
            )
            db.session.commit()
            return redirect(url_for('index'))

        return render_template('edit.html', filament=filament)

    @app.route('/use/<int:id>', methods=['POST'])
    def use_filament(id):
        amount = float(request.form['amount'])
        filament = db.get_or_404(Filament, id)
        old_weight = filament.weight_remaining
        filament.weight_remaining -= amount
        if filament.weight_remaining < 0:
            filament.weight_remaining = 0
        actual_amount = old_weight - filament.weight_remaining

        if filament.weight_total > 0:
            expected_quantity = math.ceil(filament.weight_remaining / filament.weight_total)
            if expected_quantity < filament.quantity:
                filament.quantity = expected_quantity

        app.logger.debug(f"Used {actual_amount}g of {filament.name} (remaining: {filament.weight_remaining}g)")
        log_movement(filament, 'remove', actual_amount)
        db.session.commit()
        return redirect(url_for('index'))

    @app.route('/add_spool/<int:id>', methods=['POST'])
    def add_spool(id):
        filament = db.get_or_404(Filament, id)
        filament.quantity += 1
        filament.weight_remaining += filament.weight_total
        app.logger.debug(f"Added spool to {filament.name} (qty: {filament.quantity})")
        log_movement(filament, 'add', filament.weight_total)
        db.session.commit()
        return redirect(url_for('index'))

    @app.route('/remove_spool/<int:id>', methods=['POST'])
    def remove_spool(id):
        filament = db.get_or_404(Filament, id)
        if filament.quantity > 0:
            filament.quantity -= 1
            old_weight = filament.weight_remaining
            filament.weight_remaining -= filament.weight_total
            if filament.weight_remaining < 0:
                filament.weight_remaining = 0
            actual_amount = old_weight - filament.weight_remaining
            app.logger.debug(f"Removed spool from {filament.name} (weight removed: {actual_amount}g)")
            log_movement(filament, 'remove', actual_amount)
        db.session.commit()
        return redirect(url_for('index'))

    @app.route('/delete/<int:id>', methods=['POST'])
    def delete(id):
        filament = db.get_or_404(Filament, id)
        app.logger.debug(f"Deleted filament: {filament.name}")
        log_movement(filament, 'remove', filament.weight_remaining)
        db.session.delete(filament)
        db.session.commit()
        return redirect(url_for('index'))
