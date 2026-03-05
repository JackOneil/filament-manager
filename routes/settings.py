"""Settings, export/import, and theme routes."""
import json
import logging
from flask import render_template, request, redirect, url_for, jsonify
from database import db
from models import Brand, Color, Material, AppSetting, Filament


def register(app):

    @app.route('/settings', methods=['GET', 'POST'])
    def settings():
        if request.method == 'POST':
            action = request.form.get('action')
            try:
                if action == 'brand':
                    brand_name = request.form['name']
                    db.session.add(Brand(name=brand_name))
                    app.logger.debug(f"Added brand: {brand_name}")

                elif action == 'color':
                    db.session.add(Color(name=request.form['name'], hex_value=request.form['hex_value']))
                    app.logger.debug(f"Added color: {request.form['name']}")

                elif action == 'material':
                    db.session.add(Material(name=request.form['name']))
                    app.logger.debug(f"Added material: {request.form['name']}")

                elif action == 'language':
                    setting = AppSetting.query.first()
                    old = setting.lang
                    setting.lang = request.form['lang']
                    app.logger.debug(f"Language changed: {old} -> {setting.lang}")

                elif action == 'currency':
                    setting = AppSetting.query.first()
                    old = setting.currency
                    setting.currency = request.form['currency']
                    app.logger.debug(f"Currency changed: {old} -> {setting.currency}")

                elif action == 'items_per_page':
                    setting = AppSetting.query.first()
                    setting.items_per_page = int(request.form['items_per_page'])
                    app.logger.debug(f"Items per page changed to: {setting.items_per_page}")

                elif action == 'debug_logging':
                    setting = AppSetting.query.first()
                    setting.debug_logging = request.form.get('debug_logging') == 'on'
                    if setting.debug_logging:
                        app.logger.setLevel(logging.DEBUG)
                        app.logger.debug("Debug logging enabled.")
                    else:
                        app.logger.setLevel(logging.INFO)

                elif action == 'edit_brand':
                    brand = db.session.get(Brand, request.form['id'])
                    if brand:
                        old = brand.name
                        brand.name = request.form['name']
                        app.logger.debug(f"Brand edited: {old} -> {brand.name}")

                elif action == 'edit_material':
                    mat = db.session.get(Material, request.form['id'])
                    if mat:
                        old = mat.name
                        mat.name = request.form['name']
                        app.logger.debug(f"Material edited: {old} -> {mat.name}")

                elif action == 'edit_color':
                    col = db.session.get(Color, request.form['id'])
                    if col:
                        col.name = request.form['name']
                        col.hex_value = request.form['hex_value']
                        app.logger.debug(f"Color edited: {col.name}")

                elif action == 'delete_brand':
                    brand = db.session.get(Brand, request.form['id'])
                    if brand and len(brand.filaments) == 0:
                        db.session.delete(brand)
                        app.logger.debug(f"Brand deleted: {brand.name}")

                elif action == 'delete_material':
                    mat = db.session.get(Material, request.form['id'])
                    if mat and len(mat.filaments) == 0:
                        db.session.delete(mat)
                        app.logger.debug(f"Material deleted: {mat.name}")

                elif action == 'delete_color':
                    col = db.session.get(Color, request.form['id'])
                    if col and len(col.filaments) == 0:
                        db.session.delete(col)
                        app.logger.debug(f"Color deleted: {col.name}")

                db.session.commit()
            except Exception as e:
                db.session.rollback()
                app.logger.debug(f"Settings action error: {str(e)}")
            return redirect(url_for('settings'))

        brands = Brand.query.order_by(Brand.name).all()
        colors = Color.query.order_by(Color.name).all()
        materials = Material.query.order_by(Material.name).all()
        app_settings = AppSetting.query.first()
        return render_template(
            'settings.html',
            brands=brands, colors=colors, materials=materials, app_settings=app_settings,
        )

    @app.route('/export')
    def export_data():
        data = {
            'brands': [b.name for b in Brand.query.all()],
            'materials': [m.name for m in Material.query.all()],
            'colors': [{'name': c.name, 'hex_value': c.hex_value} for c in Color.query.all()],
            'filaments': [{
                'name': f.name,
                'brand': f.brand.name if f.brand else '',
                'material': f.material.name if f.material else '',
                'color': f.color.name if f.color else '',
                'weight_total': f.weight_total,
                'weight_remaining': f.weight_remaining,
                'price': f.price,
                'quantity': f.quantity,
            } for f in Filament.query.all()],
        }
        app.logger.debug(f"Export: {len(data['filaments'])} filaments")
        response = jsonify(data)
        response.headers['Content-Disposition'] = 'attachment; filename=filament_backup.json'
        return response

    @app.route('/import', methods=['POST'])
    def import_data():
        file = request.files.get('file')
        if not file or file.filename == '':
            return redirect(url_for('settings'))

        try:
            data = json.load(file)

            for b_name in data.get('brands', []):
                if not Brand.query.filter_by(name=b_name).first():
                    db.session.add(Brand(name=b_name))

            for m_name in data.get('materials', []):
                if not Material.query.filter_by(name=m_name).first():
                    db.session.add(Material(name=m_name))

            for c in data.get('colors', []):
                if not Color.query.filter_by(name=c.get('name')).first():
                    db.session.add(Color(name=c.get('name'), hex_value=c.get('hex_value', '')))

            db.session.commit()

            imported = 0
            for f in data.get('filaments', []):
                b = Brand.query.filter_by(name=f.get('brand')).first()
                m = Material.query.filter_by(name=f.get('material')).first()
                c = Color.query.filter_by(name=f.get('color')).first()
                if b and m and c:
                    db.session.add(Filament(
                        name=f.get('name'),
                        brand_id=b.id, material_id=m.id, color_id=c.id,
                        weight_total=f.get('weight_total', 1000),
                        weight_remaining=f.get('weight_remaining', 1000),
                        price=f.get('price', 0),
                        quantity=f.get('quantity', 1),
                    ))
                    imported += 1
            db.session.commit()
            app.logger.debug(f"Import finished: {imported} filaments")
        except Exception as e:
            db.session.rollback()
            app.logger.debug(f"Import failed: {str(e)}")

        return redirect(url_for('settings'))

    @app.route('/toggle-theme', methods=['POST'])
    def toggle_theme():
        setting = AppSetting.query.first()
        if setting:
            new_theme = 'light' if setting.theme == 'dark' else 'dark'
            setting.theme = new_theme
            db.session.commit()
            app.logger.debug(f"Theme changed to: {new_theme}")
        return redirect(request.referrer or url_for('index'))
