import os
import json
import math
import logging
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, jsonify
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text
from werkzeug.middleware.proxy_fix import ProxyFix
from messages import TRANSLATIONS

app = Flask(__name__)
# Nastaveni pro ziskani skutecne IP adresy pres reverse proxy (napr. z Traefiku)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)
app.secret_key = 'filament-manager-secret'
APP_VERSION = '1.20.1'

# Setup databaze
db_dir = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'data')
os.makedirs(db_dir, exist_ok=True)
db_path = os.path.join(db_dir, 'filament.db')

app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# --- Modely databaze ---
class Brand(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)

class Color(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    hex_value = db.Column(db.String(20), nullable=True)

class Material(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)

class Filament(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    brand_id = db.Column(db.Integer, db.ForeignKey('brand.id'), nullable=False)
    color_id = db.Column(db.Integer, db.ForeignKey('color.id'), nullable=False)
    material_id = db.Column(db.Integer, db.ForeignKey('material.id'), nullable=False)
    
    weight_total = db.Column(db.Float, nullable=False)
    weight_remaining = db.Column(db.Float, nullable=False)
    price = db.Column(db.Float, nullable=False)
    quantity = db.Column(db.Integer, nullable=False, default=1)

    brand = db.relationship('Brand', backref=db.backref('filaments', lazy=True))
    color = db.relationship('Color', backref=db.backref('filaments', lazy=True))
    material = db.relationship('Material', backref=db.backref('filaments', lazy=True))

class MovementHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    filament_name = db.Column(db.String(255), nullable=False)
    action_type = db.Column(db.String(50), nullable=False)
    weight = db.Column(db.Float, nullable=False)
    cost = db.Column(db.Float, nullable=False)
    currency = db.Column(db.String(10), nullable=False)

class AppSetting(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    lang = db.Column(db.String(10), default='cs')
    kwh_price = db.Column(db.Float, default=5.0)
    printer_power = db.Column(db.Integer, default=150)
    currency = db.Column(db.String(10), default='CZK')
    debug_logging = db.Column(db.Boolean, default=False)
    theme = db.Column(db.String(10), default='light')
    view_mode = db.Column(db.String(10), default='card')

class PrintHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filament_name = db.Column(db.String(200), nullable=False)
    weight = db.Column(db.Float, nullable=False)
    total_cost = db.Column(db.Float, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

def get_settings():
    return AppSetting.query.first()

def get_current_lang():
    setting = get_settings()
    return setting.lang if setting else 'cs'

def get_current_currency():
    setting = get_settings()
    return setting.currency if setting and setting.currency else 'CZK'

def get_current_theme():
    setting = get_settings()
    return setting.theme if setting and setting.theme else 'light'

@app.context_processor
def inject_translations():
    setting = get_settings()
    lang = setting.lang if setting else 'cs'
    currency = setting.currency if setting and setting.currency else 'CZK'
    theme = setting.theme if setting and setting.theme else 'light'
    def t(key):
        return TRANSLATIONS.get(lang, TRANSLATIONS['cs']).get(key, key)
    return dict(t=t, current_lang=lang, current_currency=currency, theme=theme, app_version=APP_VERSION)

def setup_database():
    with app.app_context():
        db.create_all()
        # Inicializace vychozich zaznamu, pokud je DB prazdna
        if not Brand.query.first():
            default_brands = ['Prusament', 'Hatchbox', 'eSUN', 'Sunlu', 'Polymaker', 'Overture', 'Spectrum', 'Fiberlogy']
            for b in default_brands:
                db.session.add(Brand(name=b))
            
            default_materials = ['PLA', 'PETG', 'ABS', 'ASA', 'TPU', 'PC', 'Nylon']
            for m in default_materials:
                db.session.add(Material(name=m))
            
            default_colors = [
                ('Černá', '#000000'), ('Bílá', '#FFFFFF'), ('Šedá', '#808080'),
                ('Červená', '#FF0000'), ('Modrá', '#0000FF'), ('Zelená', '#00FF00'),
                ('Žlutá', '#FFFF00'), ('Oranžová', '#FFA500'), ('Fialová', '#800080'),
                ('Průhledná', '#edf2f7'), ('Stříbrná', '#C0C0C0'), ('Zlatá', '#FFD700')
            ]
            for name, hx in default_colors:
                db.session.add(Color(name=name, hex_value=hx))
            
            db.session.commit()

        # Pridani sloupce quantity do stare DB
        try:
            db.session.execute(text('ALTER TABLE filament ADD COLUMN quantity INTEGER NOT NULL DEFAULT 1'))
            db.session.commit()
        except Exception:
            db.session.rollback()
            
        try:
            db.session.execute(text('ALTER TABLE app_setting ADD COLUMN kwh_price FLOAT NOT NULL DEFAULT 5.0'))
            db.session.execute(text('ALTER TABLE app_setting ADD COLUMN printer_power INTEGER NOT NULL DEFAULT 150'))
            db.session.commit()
        except Exception:
            db.session.rollback()
            
        try:
            db.session.execute(text("ALTER TABLE app_setting ADD COLUMN currency VARCHAR(10) NOT NULL DEFAULT 'CZK'"))
            db.session.commit()
        except Exception:
            db.session.rollback()

        try:
            db.session.execute(text("ALTER TABLE app_setting ADD COLUMN debug_logging BOOLEAN NOT NULL DEFAULT 0"))
            db.session.commit()
        except Exception:
            db.session.rollback()

        try:
            db.session.execute(text("ALTER TABLE app_setting ADD COLUMN theme VARCHAR(10) NOT NULL DEFAULT 'light'"))
            db.session.commit()
        except Exception:
            db.session.rollback()

        try:
            db.session.execute(text("ALTER TABLE app_setting ADD COLUMN view_mode VARCHAR(10) NOT NULL DEFAULT 'card'"))
            db.session.commit()
        except Exception:
            db.session.rollback()

        if not AppSetting.query.first():
            db.session.add(AppSetting(lang='cs', kwh_price=5.0, printer_power=150, currency='CZK', debug_logging=False, theme='light', view_mode='card'))
            db.session.commit()
            
        # Apply logging based on setting
        setting = AppSetting.query.first()
        if setting and setting.debug_logging:
            app.logger.setLevel(logging.DEBUG)
            app.logger.debug("Debug logging enabled via settings.")
        else:
            app.logger.setLevel(logging.INFO)

# --- Routy (Logika) ---

def log_movement(filament, action_type, weight):
    if weight <= 0: return
    cost_per_gram = filament.price / filament.weight_total if filament.weight_total > 0 else 0
    total_cost = cost_per_gram * weight
    currency = get_current_currency()
    
    brand_name = filament.brand.name if filament.brand else ""
    mat_name = filament.material.name if filament.material else ""
    filament_name = f"{filament.name} | {brand_name} {mat_name}".strip(" | ")
    
    movement = MovementHistory(
        filament_name=filament_name,
        action_type=action_type,
        weight=weight,
        cost=total_cost,
        currency=currency
    )
    db.session.add(movement)


@app.route('/')
def index():
    filaments_query = Filament.query
    
    # Filtr - Ziskavani argumentu
    f_brand = request.args.get('brand', '')
    f_material = request.args.get('material', '')
    f_color = request.args.get('color', '')
    sort_by = request.args.get('sort_by', 'name')
    sort_direction = request.args.get('sort_direction', 'asc')
    
    if sort_direction not in ['asc', 'desc']:
        sort_direction = 'asc'
    
    # View mode - load from DB if not in URL, otherwise save to DB
    setting = get_settings()
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

    # Razeni
    if sort_by == 'brand':
        order_expr = Brand.name
        filaments_query = filaments_query.join(Brand)
    elif sort_by == 'pieces':
        order_expr = Filament.quantity
    elif sort_by == 'remaining':
        order_expr = Filament.weight_remaining
    elif sort_by == 'capacity':
        order_expr = Filament.quantity * Filament.weight_total
    else:  # 'name' je default
        order_expr = Filament.name
    
    # Aplikuj sort direction
    if sort_direction == 'desc':
        filaments_query = filaments_query.order_by(order_expr.desc())
    else:
        filaments_query = filaments_query.order_by(order_expr.asc())

    # Strankovani
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 12, type=int)
    if per_page not in [12, 24, 48]:
        per_page = 12

    # Statistiky - vypocet ze vsech filtrovanych filamentu (ne jen aktualni stranky)
    all_filtered = filaments_query.all()
    total_spools = sum(f.quantity for f in all_filtered)
    total_remaining_g = sum(f.weight_remaining for f in all_filtered)
    total_value = sum((f.price / f.weight_total * f.weight_remaining) if f.weight_total > 0 else 0 for f in all_filtered)
    
    filaments_paginated = db.paginate(filaments_query, page=page, per_page=per_page, error_out=False)
    
    # Razeni podle procenta - na Python straně pro aktuální stránku
    if sort_by == 'percent':
        filaments_paginated.items.sort(
            key=lambda f: f.weight_remaining / (f.quantity * f.weight_total) if (f.quantity * f.weight_total) > 0 else 0,
            reverse=(sort_direction == 'desc')
        )
    
    # Pro vyber filtru
    brands = Brand.query.order_by(Brand.name).all()
    materials = Material.query.order_by(Material.name).all()
    colors = Color.query.order_by(Color.name).all()
    
    app.logger.debug(f"Index viewed: view_mode={view_mode}, page={page}, per_page={per_page}, sort_by={sort_by}, sort_direction={sort_direction}, filters: brand={f_brand}, material={f_material}, color={f_color}")
    
    return render_template('index.html', filaments=filaments_paginated, stats={"spools": total_spools, "remaining": total_remaining_g, "value": total_value},
                           brands=brands, materials=materials, colors=colors,
                           f_brand=f_brand, f_material=f_material, f_color=f_color, view_mode=view_mode, per_page=per_page, sort_by=sort_by, sort_direction=sort_direction)

@app.route('/api/filaments-list')
def api_filaments_list():
    """AJAX endpoint for interactive sorting/filtering without page reload"""
    filaments_query = Filament.query
    
    # Filtr - Ziskavani argumentu
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

    # Razeni
    if sort_by == 'brand':
        order_expr = Brand.name
        filaments_query = filaments_query.join(Brand)
    elif sort_by == 'pieces':
        order_expr = Filament.quantity
    elif sort_by == 'remaining':
        order_expr = Filament.weight_remaining
    elif sort_by == 'capacity':
        order_expr = Filament.quantity * Filament.weight_total
    else:  # 'name' je default
        order_expr = Filament.name
    
    # Aplikuj sort direction
    if sort_direction == 'desc':
        filaments_query = filaments_query.order_by(order_expr.desc())
    else:
        filaments_query = filaments_query.order_by(order_expr.asc())

    # Strankovani
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 12, type=int)
    if per_page not in [12, 24, 48]:
        per_page = 12

    filaments_paginated = db.paginate(filaments_query, page=page, per_page=per_page, error_out=False)
    
    # Razeni podle procenta
    if sort_by == 'percent':
        filaments_paginated.items.sort(
            key=lambda f: f.weight_remaining / (f.quantity * f.weight_total) if (f.quantity * f.weight_total) > 0 else 0,
            reverse=(sort_direction == 'desc')
        )
    
    # Render správný template Based on view mode
    if view_mode == 'card':
        html = render_template('_filament_cards.html', filaments=filaments_paginated.items)
    else:
        html = render_template('_filament_list_rows.html', filaments=filaments_paginated.items)
    
    return jsonify({
        'html': html,
        'total_pages': filaments_paginated.pages,
        'current_page': page,
        'has_next': filaments_paginated.has_next,
        'has_prev': filaments_paginated.has_prev
    })

@app.route('/add', methods=['GET', 'POST'])
def add():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        brand_id = request.form['brand_id']
        color_id = request.form['color_id']
        material_id = request.form['material_id']
        weight_total = float(request.form['weight_total'])
        quantity = int(request.form['quantity'])
        # Vaha zustatku je prumerne plna
        weight_remaining = float(request.form.get('weight_remaining', weight_total * quantity))
        price = float(request.form['price'])

        if not name:
            brand = db.session.get(Brand, brand_id)
            material = db.session.get(Material, material_id)
            color = db.session.get(Color, color_id)
            name = f"{brand.name} {material.name} {color.name}"
        
        new_fil = Filament(name=name, brand_id=brand_id, color_id=color_id, material_id=material_id,
                           weight_total=weight_total, weight_remaining=weight_remaining, price=price, quantity=quantity)
        db.session.add(new_fil)
        db.session.flush()  # aby new_fil mel spravne namapovane vztahy
        
        log_movement(new_fil, 'add', weight_remaining)
        db.session.commit()
        app.logger.debug(f"Added new filament: {name} (Brand ID: {brand_id}, Material ID: {material_id})")
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
        
        app.logger.debug(f"Edited filament: {old_name} -> {filament.name} (weight: {old_weight}g -> {filament.weight_remaining}g, price: {filament.price})")
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
    app.logger.debug(f"Added spool to {filament.name} (quantity: {filament.quantity}, total weight: {filament.weight_remaining}g)")
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
        app.logger.debug(f"Removed spool from {filament.name} (quantity: {filament.quantity}, weight removed: {actual_amount}g)")
        log_movement(filament, 'remove', actual_amount)
    db.session.commit()
    return redirect(url_for('index'))

@app.route('/delete/<int:id>', methods=['POST'])
def delete(id):
    filament = db.get_or_404(Filament, id)
    app.logger.debug(f"Deleted filament: {filament.name} ({filament.weight_remaining}g remaining)")
    log_movement(filament, 'remove', filament.weight_remaining)
    db.session.delete(filament)
    db.session.commit()
    return redirect(url_for('index'))

@app.route('/calculator', methods=['GET', 'POST'])
def calculator():
    filaments = Filament.query.all()
    setting = get_settings()
    result = None
    if request.method == 'POST':
        filament_id = request.form.get('filament_id')
        weight = float(request.form.get('weight', 0))
        print_time = float(request.form.get('print_time', 0))
        kwh_price = float(request.form.get('kwh_price', 0))
        printer_power = int(request.form.get('printer_power', 0))
        
        # Ulozeni nastaveni elektriny pro priste
        if setting:
            setting.kwh_price = kwh_price
            setting.printer_power = printer_power
            db.session.commit()
            
        if filament_id and weight > 0:
            filament = db.session.get(Filament, filament_id)
            if filament.weight_total > 0:
                cost_per_gram = filament.price / filament.weight_total
                material_cost = cost_per_gram * weight
                
                # Vypocet elektriny: cas_h * (W / 1000) * cena_kwh
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
                    'currency': currency
                }
                
                # Ulozeni do historie
                history_record = PrintHistory(
                    filament_name=f"{filament.name} | {filament.brand.name} {filament.material.name}",
                    weight=weight,
                    total_cost=total_cost
                )
                db.session.add(history_record)
                app.logger.debug(f"Print calculated: {filament.name}, weight: {weight}g, material cost: {material_cost}, electricity cost: {electricity_cost}, total: {total_cost}")
                db.session.commit()
                
    # Strankovani pro historii
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)
    if per_page not in [10, 20, 50, 100]:
        per_page = 10

    histories_paginated = db.paginate(PrintHistory.query.order_by(PrintHistory.created_at.desc()), page=page, per_page=per_page, error_out=False)

    return render_template('calculator.html', filaments=filaments, result=result, setting=setting, histories=histories_paginated, per_page=per_page)

@app.route('/calculator/history/<int:id>/delete', methods=['POST'])
def delete_history(id):
    record = db.get_or_404(PrintHistory, id)
    app.logger.debug(f"Deleted print history: {record.filament_name}, weight: {record.weight}g, cost: {record.total_cost}")
    db.session.delete(record)
    db.session.commit()
    return redirect(url_for('calculator'))

@app.route('/history')
def history():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)
    if per_page not in [10, 20, 50, 100]:
        per_page = 10

    movements_paginated = db.paginate(MovementHistory.query.order_by(MovementHistory.created_at.desc()), page=page, per_page=per_page, error_out=False)
    
    return render_template('history.html', movements=movements_paginated, per_page=per_page)

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
                color_name = request.form['name']
                color_hex = request.form['hex_value']
                db.session.add(Color(name=color_name, hex_value=color_hex))
                app.logger.debug(f"Added color: {color_name} ({color_hex})")
            elif action == 'material':
                material_name = request.form['name']
                db.session.add(Material(name=material_name))
                app.logger.debug(f"Added material: {material_name}")
            elif action == 'language':
                setting = AppSetting.query.first()
                old_lang = setting.lang
                setting.lang = request.form['lang']
                app.logger.debug(f"Language changed: {old_lang} -> {setting.lang}")
            elif action == 'currency':
                setting = AppSetting.query.first()
                old_currency = setting.currency
                setting.currency = request.form['currency']
                app.logger.debug(f"Currency changed: {old_currency} -> {setting.currency}")
            elif action == 'debug_logging':
                setting = AppSetting.query.first()
                old_debug = setting.debug_logging
                setting.debug_logging = request.form.get('debug_logging') == 'on'
                app.logger.debug(f"Debug logging toggled: {old_debug} -> {setting.debug_logging}")
                if setting.debug_logging:
                    app.logger.setLevel(logging.DEBUG)
                    app.logger.debug("Debug logging mode enabled by user.")
                else:
                    app.logger.setLevel(logging.INFO)
            # Edit actions
            elif action == 'edit_brand':
                brand = db.session.get(Brand, request.form['id'])
                if brand:
                    old_name = brand.name
                    brand.name = request.form['name']
                    app.logger.debug(f"Brand edited: {old_name} -> {brand.name}")
            elif action == 'edit_material':
                mat = db.session.get(Material, request.form['id'])
                if mat:
                    old_name = mat.name
                    mat.name = request.form['name']
                    app.logger.debug(f"Material edited: {old_name} -> {mat.name}")
            elif action == 'edit_color':
                col = db.session.get(Color, request.form['id'])
                if col:
                    old_name = col.name
                    old_hex = col.hex_value
                    col.name = request.form['name']
                    col.hex_value = request.form['hex_value']
                    app.logger.debug(f"Color edited: {old_name} #{old_hex} -> {col.name} #{col.hex_value}")
            
            # Delete actions
            elif action == 'delete_brand':
                brand = db.session.get(Brand, request.form['id'])
                if brand and len(brand.filaments) == 0:
                    app.logger.debug(f"Brand deleted: {brand.name}")
                    db.session.delete(brand)
            elif action == 'delete_material':
                mat = db.session.get(Material, request.form['id'])
                if mat and len(mat.filaments) == 0:
                    app.logger.debug(f"Material deleted: {mat.name}")
                    db.session.delete(mat)
            elif action == 'delete_color':
                col = db.session.get(Color, request.form['id'])
                if col and len(col.filaments) == 0:
                    app.logger.debug(f"Color deleted: {col.name} #{col.hex_value}")
                    db.session.delete(col)
                    
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            app.logger.debug(f"Settings action error: {str(e)}")
        return redirect(url_for('settings'))
    
    brands = Brand.query.order_by(Brand.name).all()
    colors = Color.query.order_by(Color.name).all()
    materials = Material.query.order_by(Material.name).all()
    app_settings = AppSetting.query.first()
    return render_template('settings.html', brands=brands, colors=colors, materials=materials, app_settings=app_settings)

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
            'quantity': f.quantity
        } for f in Filament.query.all()]
    }
    app.logger.debug(f"Export started: brands={len(data['brands'])}, materials={len(data['materials'])}, colors={len(data['colors'])}, filaments={len(data['filaments'])}")
    response = jsonify(data)
    response.headers['Content-Disposition'] = 'attachment; filename=filament_backup.json'
    app.logger.debug("Export finished successfully")
    return response

@app.route('/import', methods=['POST'])
def import_data():
    file = request.files.get('file')
    if not file or file.filename == '':
        app.logger.debug("Import failed: no file provided")
        return redirect(url_for('settings'))
        
    try:
        data = json.load(file)
        app.logger.debug(f"Import started: brands={len(data.get('brands', []))}, materials={len(data.get('materials', []))}, colors={len(data.get('colors', []))}, filaments={len(data.get('filaments', []))}")
        
        # Osetreni a import znacek
        for b_name in data.get('brands', []):
            if not Brand.query.filter_by(name=b_name).first():
                db.session.add(Brand(name=b_name))
                app.logger.debug(f"Brand imported: {b_name}")
        
        # Osetreni a import materialu
        for m_name in data.get('materials', []):
            if not Material.query.filter_by(name=m_name).first():
                db.session.add(Material(name=m_name))
                app.logger.debug(f"Material imported: {m_name}")
                
        # Osetreni a import barev
        for c in data.get('colors', []):
            if not Color.query.filter_by(name=c.get('name')).first():
                db.session.add(Color(name=c.get('name'), hex_value=c.get('hex_value', '')))
                app.logger.debug(f"Color imported: {c.get('name')} ({c.get('hex_value', '')})")
                
        db.session.commit()
        
        # Import filamentu (vzdy se pridaji jako nove)
        imported_count = 0
        for f in data.get('filaments', []):
            b = Brand.query.filter_by(name=f.get('brand')).first()
            m = Material.query.filter_by(name=f.get('material')).first()
            c = Color.query.filter_by(name=f.get('color')).first()
            
            if b and m and c:
                db.session.add(Filament(
                    name=f.get('name'),
                    brand_id=b.id,
                    material_id=m.id,
                    color_id=c.id,
                    weight_total=f.get('weight_total', 1000),
                    weight_remaining=f.get('weight_remaining', 1000),
                    price=f.get('price', 0),
                    quantity=f.get('quantity', 1)
                ))
                app.logger.debug(f"Filament imported: {f.get('name')}")
                imported_count += 1
        db.session.commit()
        app.logger.debug(f"Import finished: {imported_count} filaments imported")
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

# Initialize DB structures automatically for WSGI environments like Gunicorn
setup_database()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
