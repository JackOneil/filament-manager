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
    min_stock_grams = db.Column(db.Float, nullable=False, default=0.0)
    max_stock_grams = db.Column(db.Float, nullable=False, default=0.0)
    tag_text = db.Column(db.Text, nullable=True)
    quality_stringing = db.Column(db.Text, nullable=True)
    quality_adhesion = db.Column(db.Text, nullable=True)
    quality_drying = db.Column(db.Text, nullable=True)
    quality_profile = db.Column(db.Text, nullable=True)
    quality_notes = db.Column(db.Text, nullable=True)
    recommended_nozzle_temp = db.Column(db.Integer, nullable=True)
    recommended_bed_temp = db.Column(db.Integer, nullable=True)
    reorder_alert_snoozed = db.Column(db.Boolean, nullable=False, default=False)

    brand = db.relationship('Brand', backref=db.backref('filaments', lazy=True))
    color = db.relationship('Color', backref=db.backref('filaments', lazy=True))
    material = db.relationship('Material', backref=db.backref('filaments', lazy=True))


class MovementHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    filament_id = db.Column(db.Integer, db.ForeignKey('filament.id'), nullable=True)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=True)
    bambu_job_id = db.Column(db.Integer, db.ForeignKey('bambu_print_job.id'), nullable=True)
    filament_name = db.Column(db.String(255), nullable=False)
    action_type = db.Column(db.String(50), nullable=False)
    weight = db.Column(db.Float, nullable=False)
    cost = db.Column(db.Float, nullable=False)
    currency = db.Column(db.String(10), nullable=False)
    note = db.Column(db.Text, nullable=True)

    filament = db.relationship('Filament', backref=db.backref('movements', lazy=True))
    project = db.relationship('Project', backref=db.backref('movements', lazy=True))
    bambu_job = db.relationship('BambuPrintJob', backref=db.backref('movements', lazy=True))


class AppSetting(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    lang = db.Column(db.String(10), default='cs')
    kwh_price = db.Column(db.Float, default=5.0)
    printer_power = db.Column(db.Integer, default=150)
    currency = db.Column(db.String(10), default='CZK')
    debug_logging = db.Column(db.Boolean, default=False)
    theme = db.Column(db.String(10), default='light')
    view_mode = db.Column(db.String(10), default='card')
    items_per_page = db.Column(db.Integer, default=12)
    # Bambu Lab Cloud integration
    bambu_token = db.Column(db.Text, nullable=True)
    bambu_region = db.Column(db.String(10), default='global')
    bambu_auto_sync_enabled = db.Column(db.Boolean, default=False)
    bambu_auto_sync_interval_minutes = db.Column(db.Integer, default=60)
    bambu_last_sync_at = db.Column(db.DateTime, nullable=True)
    bambu_last_sync_status = db.Column(db.String(255), nullable=True)


class PrintHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filament_name = db.Column(db.String(200), nullable=False)
    weight = db.Column(db.Float, nullable=False)
    total_cost = db.Column(db.Float, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class ProjectQuote(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id', ondelete='CASCADE'), nullable=False)
    filament_id = db.Column(db.Integer, db.ForeignKey('filament.id'), nullable=True)
    filament_name = db.Column(db.String(255), nullable=False)
    weight = db.Column(db.Float, nullable=False)
    print_time = db.Column(db.Float, nullable=False)
    material_cost = db.Column(db.Float, nullable=False, default=0.0)
    electricity_cost = db.Column(db.Float, nullable=False, default=0.0)
    base_cost = db.Column(db.Float, nullable=False, default=0.0)
    margin_percent = db.Column(db.Float, nullable=False, default=0.0)
    margin_amount = db.Column(db.Float, nullable=False, default=0.0)
    final_price = db.Column(db.Float, nullable=False, default=0.0)
    currency = db.Column(db.String(10), nullable=False, default='CZK')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    project = db.relationship('Project', backref=db.backref('quotes', lazy=True, cascade='all, delete-orphan'))
    filament = db.relationship('Filament')


class Project(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    due_date = db.Column(db.DateTime, nullable=True)
    client_name = db.Column(db.String(100), nullable=True)
    estimated_print_time = db.Column(db.Integer, default=0) # in minutes
    status = db.Column(db.String(20), default='NEW') # NEW, PRINTING, DONE
    tag_text = db.Column(db.Text, nullable=True)


class ProjectFile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id', ondelete='CASCADE'), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    filepath = db.Column(db.String(255), nullable=False)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)
    project = db.relationship('Project', backref=db.backref('files', lazy=True, cascade="all, delete-orphan"))


class ProjectLink(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id', ondelete='CASCADE'), nullable=False)
    url = db.Column(db.String(500), nullable=False)
    name = db.Column(db.String(100), nullable=True)
    og_title = db.Column(db.String(255), nullable=True)
    og_image = db.Column(db.String(500), nullable=True)
    og_description = db.Column(db.Text, nullable=True)
    domain = db.Column(db.String(100), nullable=True)
    project = db.relationship('Project', backref=db.backref('links', lazy=True, cascade="all, delete-orphan"))


class ProjectFilament(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id', ondelete='CASCADE'), nullable=False)
    filament_id = db.Column(db.Integer, db.ForeignKey('filament.id'), nullable=False)
    estimated_weight = db.Column(db.Float, nullable=False, default=0.0)
    is_used = db.Column(db.Boolean, default=False)
    project = db.relationship('Project', backref=db.backref('filaments', lazy=True, cascade="all, delete-orphan"))
    filament = db.relationship('Filament')


class StorageShelf(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False, unique=True)
    columns = db.Column(db.Integer, nullable=False, default=4)
    slots_count = db.Column(db.Integer, nullable=False, default=12)
    sort_order = db.Column(db.Integer, nullable=False, default=0)


class StoragePlacement(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    shelf_id = db.Column(db.Integer, db.ForeignKey('storage_shelf.id', ondelete='CASCADE'), nullable=False)
    filament_id = db.Column(db.Integer, db.ForeignKey('filament.id'), nullable=False)
    slot_index = db.Column(db.Integer, nullable=False)
    orientation = db.Column(db.String(20), nullable=False, default='standing')

    shelf = db.relationship('StorageShelf', backref=db.backref('placements', lazy=True, cascade='all, delete-orphan'))
    filament = db.relationship('Filament')


class BambuPrinter(db.Model):
    """Known Bambu Lab printers, auto-discovered from sync or manually added."""
    id = db.Column(db.Integer, primary_key=True)
    device_id = db.Column(db.String(100), nullable=True)
    name = db.Column(db.String(200), nullable=False)
    printer_model = db.Column(db.String(50), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class BambuPrintJob(db.Model):
    """Real print job fetched from Bambu Lab Cloud."""
    id = db.Column(db.Integer, primary_key=True)
    external_id = db.Column(db.String(100), unique=True, nullable=False)
    printer_name = db.Column(db.String(200), nullable=True)
    printer_model = db.Column(db.String(100), nullable=True)
    device_id = db.Column(db.String(100), nullable=True)
    model_name = db.Column(db.String(300), nullable=True)
    status = db.Column(db.String(50), nullable=True)
    started_at = db.Column(db.DateTime, nullable=True)
    finished_at = db.Column(db.DateTime, nullable=True)
    weight_grams = db.Column(db.Float, nullable=True)
    cost_time = db.Column(db.Integer, nullable=True)   # print duration in seconds
    raw_payload = db.Column(db.Text, nullable=True)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=True)
    filament_id = db.Column(db.Integer, db.ForeignKey('filament.id'), nullable=True)
    deducted = db.Column(db.Boolean, default=False)
    synced_at = db.Column(db.DateTime, default=datetime.utcnow)

    project = db.relationship('Project', backref=db.backref('bambu_jobs', lazy=True))
    filament = db.relationship('Filament', backref=db.backref('bambu_jobs', lazy=True))


class BambuJobMaterial(db.Model):
    """Per-AMS-slot material consumption for a Bambu print job."""
    id = db.Column(db.Integer, primary_key=True)
    job_id = db.Column(db.Integer, db.ForeignKey('bambu_print_job.id', ondelete='CASCADE'), nullable=False)
    ams_id = db.Column(db.Integer, nullable=True)
    tray_id = db.Column(db.Integer, nullable=True)
    color_hex = db.Column(db.String(10), nullable=True)
    material_name = db.Column(db.String(100), nullable=True)
    weight_grams = db.Column(db.Float, nullable=True)
    filament_id = db.Column(db.Integer, db.ForeignKey('filament.id'), nullable=True)
    deducted = db.Column(db.Boolean, default=False)

    job = db.relationship('BambuPrintJob', backref=db.backref('materials', lazy=True, cascade='all, delete-orphan'))
    filament = db.relationship('Filament')
