from datetime import datetime, timezone
from database import db


def _utc_now():
    """Return current UTC time as a naive datetime (no tzinfo).

    Local helper to avoid circular import with utils.utc_now.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='user')  # admin, user
    section_permissions = db.Column(db.Text, nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    notify_project_created = db.Column(db.Boolean, nullable=False, default=True)
    notify_project_status_changed = db.Column(db.Boolean, nullable=False, default=True)
    notify_project_comment = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, default=_utc_now)
    last_login_at = db.Column(db.DateTime, nullable=True, index=True)

    def __repr__(self):
        return f'<User {self.id} {self.email!r} role={self.role}>'


class UserInvite(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), nullable=True, index=True)
    code = db.Column(db.String(64), unique=True, nullable=False, index=True)
    role = db.Column(db.String(20), nullable=False, default='user')
    section_permissions = db.Column(db.Text, nullable=True)
    is_used = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, default=_utc_now)
    expires_at = db.Column(db.DateTime, nullable=True)

    def __repr__(self):
        return f'<UserInvite {self.id} code={self.code!r}>'


class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False, index=True)
    kind = db.Column(db.String(50), nullable=False, default='info')
    title = db.Column(db.String(255), nullable=False)
    body = db.Column(db.Text, nullable=True)
    link = db.Column(db.String(500), nullable=True)
    is_read = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, default=_utc_now, index=True)

    user = db.relationship('User', backref=db.backref('notifications', lazy=True, cascade='all, delete-orphan'))

    def __repr__(self):
        return f'<Notification {self.id} user={self.user_id} {self.kind!r}>'


class AuditLog(db.Model):
    """Admin action audit trail with request and before/after snapshots."""
    id = db.Column(db.Integer, primary_key=True)
    created_at = db.Column(db.DateTime, default=_utc_now, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='SET NULL'), nullable=True, index=True)
    user_email = db.Column(db.String(255), nullable=True)
    user_name = db.Column(db.String(120), nullable=True)
    session_id = db.Column(db.String(64), nullable=True, index=True)
    ip_address = db.Column(db.String(64), nullable=True)
    user_agent = db.Column(db.String(255), nullable=True)
    method = db.Column(db.String(12), nullable=False)
    endpoint = db.Column(db.String(120), nullable=True, index=True)
    path = db.Column(db.String(500), nullable=False)
    action = db.Column(db.String(120), nullable=False, index=True)
    object_type = db.Column(db.String(120), nullable=True, index=True)
    object_id = db.Column(db.String(120), nullable=True, index=True)
    before_data = db.Column(db.Text, nullable=True)
    after_data = db.Column(db.Text, nullable=True)

    user = db.relationship('User', backref=db.backref('audit_logs', lazy=True))

    def __repr__(self):
        return f'<AuditLog {self.id} {self.action!r} user={self.user_id}>'


class Brand(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    shop_url = db.Column(db.Text, nullable=True)

    def __repr__(self):
        return f'<Brand {self.id} {self.name!r}>'


class Color(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    hex_value = db.Column(db.String(20), nullable=True)

    def __repr__(self):
        return f'<Color {self.id} {self.name!r}>'


class Material(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)

    def __repr__(self):
        return f'<Material {self.id} {self.name!r}>'


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
    shop_url = db.Column(db.Text, nullable=True)

    brand = db.relationship('Brand', backref=db.backref('filaments', lazy=True))
    color = db.relationship('Color', backref=db.backref('filaments', lazy=True))
    material = db.relationship('Material', backref=db.backref('filaments', lazy=True))

    def __repr__(self):
        return f'<Filament {self.id} {self.name!r}>'


class MovementHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    created_at = db.Column(db.DateTime, default=_utc_now, index=True)
    filament_id = db.Column(db.Integer, db.ForeignKey('filament.id'), nullable=True, index=True)
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

    def __repr__(self):
        return f'<MovementHistory {self.id} {self.action_type!r} {self.weight}g>'


class AppSetting(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    lang = db.Column(db.String(10), default='cs')
    kwh_price = db.Column(db.Float, default=5.0)
    printer_power = db.Column(db.Integer, default=150)
    currency = db.Column(db.String(10), default='CZK')
    debug_logging = db.Column(db.Boolean, default=False)
    theme = db.Column(db.String(10), default='light')
    nav_palette = db.Column(db.String(20), default='teal')
    view_mode = db.Column(db.String(10), default='card')
    items_per_page = db.Column(db.Integer, default=12)
    # Bambu Lab Cloud integration
    bambu_token = db.Column(db.Text, nullable=True)
    bambu_region = db.Column(db.String(10), default='global')
    bambu_auto_sync_enabled = db.Column(db.Boolean, default=False)
    bambu_auto_sync_interval_minutes = db.Column(db.Integer, default=60)
    bambu_last_sync_at = db.Column(db.DateTime, nullable=True)
    bambu_last_sync_status = db.Column(db.String(255), nullable=True)
    reorder_shop_url = db.Column(db.Text, nullable=True)
    
    # Billing / Invoice Details
    company_name = db.Column(db.String(200), nullable=True)
    company_street = db.Column(db.String(200), nullable=True)
    company_city = db.Column(db.String(200), nullable=True)
    company_zip = db.Column(db.String(20), nullable=True)
    company_id = db.Column(db.String(50), nullable=True)  # IČO
    company_vat_id = db.Column(db.String(50), nullable=True)  # DIČ
    company_bank_account = db.Column(db.String(100), nullable=True)

    # Invoice / document number sequence
    invoice_prefix = db.Column(db.String(20), default='FV')
    invoice_counter = db.Column(db.Integer, default=0)

    # Display timezone
    app_timezone = db.Column(db.String(50), default='Europe/Prague')

    # Onboarding
    onboarding_dismissed = db.Column(db.Boolean, default=False)

    # Audit logging toggle
    audit_logging_enabled = db.Column(db.Boolean, default=True)


class PrintHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filament_name = db.Column(db.String(200), nullable=False)
    weight = db.Column(db.Float, nullable=False)
    total_cost = db.Column(db.Float, nullable=False)
    created_at = db.Column(db.DateTime, default=_utc_now)


class ProjectQuote(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id', ondelete='CASCADE'), nullable=False)
    filament_id = db.Column(db.Integer, db.ForeignKey('filament.id', ondelete='SET NULL'), nullable=True)
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
    invoice_number = db.Column(db.String(50), nullable=True)
    created_at = db.Column(db.DateTime, default=_utc_now)

    project = db.relationship('Project', backref=db.backref('quotes', lazy=True, cascade='all, delete-orphan'))
    filament = db.relationship('Filament')


class Project(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=_utc_now, index=True)
    due_date = db.Column(db.DateTime, nullable=True, index=True)
    client_name = db.Column(db.String(100), nullable=True)
    estimated_print_time = db.Column(db.Integer, default=0) # in minutes
    status = db.Column(db.String(20), default='NEW', index=True) # PENDING_APPROVAL, APPROVED, REJECTED, PRINTING, DONE
    tag_text = db.Column(db.Text, nullable=True)
    owner_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True, index=True)
    owner_name = db.Column(db.String(120), nullable=True)
    created_by_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True, index=True)

    owner = db.relationship('User', foreign_keys=[owner_user_id], backref=db.backref('owned_projects', lazy=True))
    created_by = db.relationship('User', foreign_keys=[created_by_user_id], backref=db.backref('created_projects', lazy=True))

    @property
    def owner_display_name(self):
        if self.owner:
            return self.owner.name
        return (self.owner_name or '').strip()

    def __repr__(self):
        return f'<Project {self.id} {self.name!r} status={self.status}>'


class ProjectComment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id', ondelete='CASCADE'), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='SET NULL'), nullable=True, index=True)
    body = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=_utc_now, index=True)
    updated_at = db.Column(db.DateTime, nullable=True)

    project = db.relationship('Project', backref=db.backref('comments', lazy=True, cascade='all, delete-orphan'))
    user = db.relationship('User', backref=db.backref('project_comments', lazy=True))


class ProjectTodo(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id', ondelete='CASCADE'), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='SET NULL'), nullable=True, index=True)
    body = db.Column(db.String(255), nullable=False)
    is_done = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, default=_utc_now, index=True)
    completed_at = db.Column(db.DateTime, nullable=True)

    project = db.relationship('Project', backref=db.backref('todos', lazy=True, cascade='all, delete-orphan'))
    user = db.relationship('User', backref=db.backref('project_todos', lazy=True))


class ProjectFile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id', ondelete='CASCADE'), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    filepath = db.Column(db.String(255), nullable=False)
    uploaded_at = db.Column(db.DateTime, default=_utc_now)
    version = db.Column(db.Integer, nullable=False, default=1)
    parent_file_id = db.Column(db.Integer, db.ForeignKey('project_file.id', ondelete='SET NULL'), nullable=True)
    project = db.relationship('Project', backref=db.backref('files', lazy=True, cascade="all, delete-orphan"))
    versions = db.relationship('ProjectFile', backref=db.backref('parent', remote_side='ProjectFile.id'), lazy=True, cascade='all, delete-orphan')


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
    project_id = db.Column(db.Integer, db.ForeignKey('project.id', ondelete='CASCADE'), nullable=False, index=True)
    filament_id = db.Column(db.Integer, db.ForeignKey('filament.id', ondelete='CASCADE'), nullable=False, index=True)
    estimated_weight = db.Column(db.Float, nullable=False, default=0.0)
    is_used = db.Column(db.Boolean, default=False)
    project = db.relationship('Project', backref=db.backref('filaments', lazy=True, cascade="all, delete-orphan"))
    filament = db.relationship('Filament')


class ProjectPrintItem(db.Model):
    """Tracks individual print models and their completion counts within a project."""
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id', ondelete='CASCADE'), nullable=False, index=True)
    name = db.Column(db.String(200), nullable=False)
    quantity_total = db.Column(db.Integer, nullable=False, default=1)
    quantity_done = db.Column(db.Integer, nullable=False, default=0)
    notes = db.Column(db.Text, nullable=True)
    sort_order = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime, default=_utc_now)

    project = db.relationship('Project', backref=db.backref('print_items', lazy=True, cascade='all, delete-orphan'))

    def __repr__(self):
        return f'<ProjectPrintItem {self.id} {self.name!r} {self.quantity_done}/{self.quantity_total}>'


class StorageShelf(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False, unique=True)
    columns = db.Column(db.Integer, nullable=False, default=4)
    slots_count = db.Column(db.Integer, nullable=False, default=12)
    sort_order = db.Column(db.Integer, nullable=False, default=0)


class StoragePlacement(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    shelf_id = db.Column(db.Integer, db.ForeignKey('storage_shelf.id', ondelete='CASCADE'), nullable=False)
    filament_id = db.Column(db.Integer, db.ForeignKey('filament.id', ondelete='CASCADE'), nullable=False)
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
    pre_job_time_minutes = db.Column(db.Integer, default=0)  # calibration/warmup time before print
    power_draw_watts = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime, default=_utc_now)



class BambuPrintJob(db.Model):
    """Real print job fetched from Bambu Lab Cloud."""
    id = db.Column(db.Integer, primary_key=True)
    external_id = db.Column(db.String(100), unique=True, nullable=False)
    printer_name = db.Column(db.String(200), nullable=True)
    printer_model = db.Column(db.String(100), nullable=True)
    device_id = db.Column(db.String(100), nullable=True)
    model_name = db.Column(db.String(300), nullable=True)
    status = db.Column(db.String(50), nullable=True, index=True)
    started_at = db.Column(db.DateTime, nullable=True)
    finished_at = db.Column(db.DateTime, nullable=True)
    weight_grams = db.Column(db.Float, nullable=True)
    cost_time = db.Column(db.Integer, nullable=True)   # print duration in seconds
    raw_payload = db.Column(db.Text, nullable=True)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id', ondelete='SET NULL'), nullable=True, index=True)
    filament_id = db.Column(db.Integer, db.ForeignKey('filament.id', ondelete='SET NULL'), nullable=True)
    deducted = db.Column(db.Boolean, default=False)
    synced_at = db.Column(db.DateTime, default=_utc_now)

    project = db.relationship('Project', backref=db.backref('bambu_jobs', lazy=True))
    filament = db.relationship('Filament', backref=db.backref('bambu_jobs', lazy=True))

    def __repr__(self):
        return f'<BambuPrintJob {self.id} {self.model_name!r} status={self.status}>'


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


class PrusaPrinter(db.Model):
    """Manually configured PrusaLink printer (local network API)."""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    host = db.Column(db.String(255), nullable=False)          # e.g. http://192.168.1.50
    api_key = db.Column(db.Text, nullable=False)              # encrypted via encrypt_token
    printer_model = db.Column(db.String(100), nullable=True)  # filled from /api/v1/info
    notes = db.Column(db.Text, nullable=True)
    enabled = db.Column(db.Boolean, nullable=False, default=True)
    last_sync_at = db.Column(db.DateTime, nullable=True)
    last_success_at = db.Column(db.DateTime, nullable=True)
    last_sync_status = db.Column(db.String(255), nullable=True)
    power_draw_watts = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime, default=_utc_now)



class PrusaPrintJob(db.Model):
    """Print job recorded by polling a PrusaLink printer."""
    id = db.Column(db.Integer, primary_key=True)
    printer_id = db.Column(db.Integer, db.ForeignKey('prusa_printer.id', ondelete='SET NULL'), nullable=True, index=True)
    printer_name = db.Column(db.String(200), nullable=True)   # snapshot at time of record
    file_name = db.Column(db.String(300), nullable=True)      # raw filename from printer
    display_name = db.Column(db.String(300), nullable=True)   # human-readable name
    status = db.Column(db.String(50), nullable=True, index=True)          # PRINTING, FINISHED, STOPPED, IDLE
    started_at = db.Column(db.DateTime, nullable=True)
    finished_at = db.Column(db.DateTime, nullable=True)
    weight_grams = db.Column(db.Float, nullable=True)         # from g-code metadata
    cost_time = db.Column(db.Integer, nullable=True)          # print duration in seconds
    progress = db.Column(db.Float, nullable=True)             # 0.0–1.0
    filament_id = db.Column(db.Integer, db.ForeignKey('filament.id', ondelete='SET NULL'), nullable=True)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id', ondelete='SET NULL'), nullable=True)
    deducted = db.Column(db.Boolean, nullable=False, default=False)
    raw_payload = db.Column(db.Text, nullable=True)
    synced_at = db.Column(db.DateTime, default=_utc_now)

    printer = db.relationship('PrusaPrinter', backref=db.backref('jobs', lazy=True))
    filament = db.relationship('Filament', backref=db.backref('prusa_jobs', lazy=True))
    project = db.relationship('Project', backref=db.backref('prusa_jobs', lazy=True))

    def __repr__(self):
        return f'<PrusaPrintJob {self.id} {self.display_name!r} status={self.status}>'


class PrinterMaintenance(db.Model):
    """Service record for Bambu or Prusa printers (nozzle changes, calibration, faults, etc.)."""
    id = db.Column(db.Integer, primary_key=True)
    printer_type = db.Column(db.String(20), nullable=False)   # 'bambu' or 'prusa'
    printer_id = db.Column(db.Integer, nullable=True)          # FK to BambuPrinter or PrusaPrinter
    printer_name = db.Column(db.String(200), nullable=False)   # denormalized snapshot
    maintenance_type = db.Column(db.String(50), nullable=False, default='other')
    # nozzle_change, calibration, service, fault, other
    notes = db.Column(db.Text, nullable=True)
    performed_at = db.Column(db.DateTime, nullable=False, default=_utc_now)
    next_service_at = db.Column(db.DateTime, nullable=True)
    recurrence_type = db.Column(db.String(20), nullable=False, default='none')
    # none, hours, days, months
    recurrence_value = db.Column(db.Integer, nullable=False, default=0)
    recurrence_enabled = db.Column(db.Boolean, nullable=False, default=False)
    last_renewed_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=_utc_now)

    def __repr__(self):
        return f'<PrinterMaintenance {self.id} {self.printer_name!r} {self.maintenance_type!r}>'


class WasteRecord(db.Model):
    """Record of failed/scrapped prints with reason, weight, and filament reference."""
    id = db.Column(db.Integer, primary_key=True)
    filament_id = db.Column(db.Integer, db.ForeignKey('filament.id'), nullable=False)
    filament = db.relationship('Filament', backref=db.backref('waste_records', lazy=True))
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=True)
    project = db.relationship('Project', backref=db.backref('waste_records', lazy=True))
    reason = db.Column(db.String(50), nullable=False, default='other')
    # stringing, warping, bed_adhesion, clogging, layer_shift, spaghetti, broken_support, other
    weight_grams = db.Column(db.Float, nullable=False, default=0.0)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=_utc_now)
    recorded_by_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    recorded_by = db.relationship('User', backref=db.backref('waste_records', lazy=True))

    def __repr__(self):
        return f'<WasteRecord {self.id} {self.filament.name if self.filament else "?"} {self.weight_grams}g {self.reason}>'


class WasteFile(db.Model):
    """Photo/image attachments for a WasteRecord (documenting failed prints)."""
    id = db.Column(db.Integer, primary_key=True)
    waste_record_id = db.Column(db.Integer, db.ForeignKey('waste_record.id', ondelete='CASCADE'), nullable=False, index=True)
    filename = db.Column(db.String(255), nullable=False)
    filepath = db.Column(db.String(255), nullable=False)
    uploaded_at = db.Column(db.DateTime, default=_utc_now)
    record = db.relationship('WasteRecord', backref=db.backref('files', lazy=True, cascade='all, delete-orphan'))


class FilamentUndoLog(db.Model):
    """Database-backed undo log for filament operations.

    Persists undo snapshots in the database instead of in-memory cache,
    providing durability across restarts and better audit trail.
    """
    id = db.Column(db.Integer, primary_key=True)
    created_at = db.Column(db.DateTime, default=_utc_now, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False, index=True)
    action_type = db.Column(db.String(50), nullable=False)  # delete_filament, bulk_delete, remove_spool
    filament_id = db.Column(db.Integer, db.ForeignKey('filament.id', ondelete='CASCADE'), nullable=True, index=True)
    snapshot_data = db.Column(db.Text, nullable=False)  # JSON of filament state and relations
    expires_at = db.Column(db.DateTime, nullable=False, index=True)
    is_consumed = db.Column(db.Boolean, nullable=False, default=False)
    consumed_at = db.Column(db.DateTime, nullable=True)

    user = db.relationship('User', backref=db.backref('filament_undo_logs', lazy=True))
    filament = db.relationship('Filament', backref=db.backref('undo_logs', lazy=True))

    def __repr__(self):
        return f'<FilamentUndoLog {self.id} action={self.action_type!r} user={self.user_id} consumed={self.is_consumed}>'
