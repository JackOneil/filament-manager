from datetime import datetime
from database import db


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
