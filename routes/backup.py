"""Full database export and import endpoints for backups."""
import base64
import gzip
import io
import json
import os
import tarfile
import uuid
from flask import current_app as app, request, redirect, url_for, Response, Blueprint

from database import db
from models import (
    Brand, Color, Material, AppSetting, Filament, MovementHistory,
    PrintHistory, Project, ProjectFile, ProjectLink, ProjectFilament, ProjectQuote,
    BambuPrinter, BambuPrintJob, BambuJobMaterial, StoragePlacement, StorageShelf,
    PrusaPrinter, PrusaPrintJob, ProjectComment, ProjectTodo, ProjectPrintItem, User, UserInvite, Notification, AuditLog,
    PrinterMaintenance, WasteRecord, WasteFile, FilamentUndoLog,
)
from utils import encrypt_token, format_tags, utc_now


def _filament_ref(filament):
    if not filament:
        return None
    return {
        'name': filament.name,
        'brand': filament.brand.name if filament.brand else None,
        'material': filament.material.name if filament.material else None,
        'color': filament.color.name if filament.color else None,
    }


def _resolve_filament_ref(ref, fallback_name=None):
    if isinstance(ref, str):
        fallback_name = ref
        ref = None

    if isinstance(ref, dict):
        name = (ref.get('name') or '').strip()
        brand_name = (ref.get('brand') or '').strip()
        material_name = (ref.get('material') or '').strip()
        color_name = (ref.get('color') or '').strip()
        if name and brand_name and material_name and color_name:
            brand = Brand.query.filter_by(name=brand_name).first()
            material = Material.query.filter_by(name=material_name).first()
            color = Color.query.filter_by(name=color_name).first()
            if brand and material and color:
                filament = Filament.query.filter_by(
                    name=name,
                    brand_id=brand.id,
                    material_id=material.id,
                    color_id=color.id,
                ).first()
                if filament:
                    return filament
        if name:
            fallback_name = name

    fallback_name = (fallback_name or '').split(' | ')[0].strip()
    if fallback_name:
        return Filament.query.filter_by(name=fallback_name).order_by(Filament.id.asc()).first()
    return None


def _project_file_payload(project_file):
    from werkzeug.utils import secure_filename
    payload = {
        'filename': project_file.filename,
        'filepath': project_file.filepath,
        'uploaded_at': project_file.uploaded_at.isoformat() if project_file.uploaded_at else None,
        'archive_path': None,
        'content_b64': None,
    }
    if project_file.filepath and os.path.isfile(project_file.filepath):
        safe_name = secure_filename(project_file.filename or '') or f'project_file_{uuid.uuid4().hex[:8]}'
        stamp = ''.join(ch for ch in (payload['uploaded_at'] or '') if ch.isdigit())[:14] or uuid.uuid4().hex[:12]
        payload['archive_path'] = f'uploads/{project_file.project_id}/{stamp}_{safe_name}'
    return payload


def _build_import_file_path(upload_folder, project_id, filename, uploaded_at_text):
    from werkzeug.utils import secure_filename
    safe_name = secure_filename(filename or '') or f'project_file_{uuid.uuid4().hex[:8]}'
    stamp = ''.join(ch for ch in (uploaded_at_text or '') if ch.isdigit())[:14] or uuid.uuid4().hex[:12]
    return os.path.join(upload_folder, f'{project_id}_{stamp}_{safe_name}')


def _load_backup_package(uploaded_file):
    raw_bytes = uploaded_file.read()
    if not raw_bytes:
        return {}, {}

    try:
        with tarfile.open(fileobj=io.BytesIO(raw_bytes), mode='r:*') as archive:
            manifest_member = archive.extractfile('manifest.json')
            if manifest_member is None:
                raise ValueError('Backup archive is missing manifest.json')
            data = json.loads(manifest_member.read().decode('utf-8'))
            attachments = {}
            for member in archive.getmembers():
                if not member.isfile() or member.name == 'manifest.json':
                    continue
                extracted = archive.extractfile(member)
                if extracted is not None:
                    attachments[member.name] = extracted.read()
            return data, attachments
    except (tarfile.TarError, ValueError):
        pass

    filename = (uploaded_file.filename or '').lower()
    if filename.endswith('.gz') or raw_bytes[:2] == b'\x1f\x8b':
        raw_bytes = gzip.decompress(raw_bytes)
    return json.loads(raw_bytes.decode('utf-8')), {}


def _user_ref(user):
    if not user:
        return None
    return {'email': user.email, 'name': user.name}


def _resolve_user_ref(ref):
    if not ref:
        return None
    email = (ref.get('email') or '').strip().lower()
    name = (ref.get('name') or '').strip()
    if email:
        user = User.query.filter_by(email=email).first()
        if user:
            return user
    if name:
        return User.query.filter_by(name=name).first()
    return None


def register(app):
    bp = Blueprint('backup', __name__)

    @bp.route('/export')
    def export_data():
        setting = AppSetting.query.first()

        data = {
            'backup_meta': {
                'format_version': 2,
                'packaging': 'tar.gz',
            },
            # ── Enumerations ───────────────────────────────────────────
            'brands': [{'name': b.name, 'shop_url': b.shop_url} for b in Brand.query.all()],
            'materials': [m.name for m in Material.query.all()],
            'colors': [{'name': c.name, 'hex_value': c.hex_value} for c in Color.query.all()],

            # ── App settings ───────────────────────────────────────────
            'app_settings': {
                'lang': setting.lang if setting else 'cs',
                'currency': setting.currency if setting else 'CZK',
                'theme': setting.theme if setting else 'light',
                'nav_palette': setting.nav_palette if setting and setting.nav_palette else 'teal',
                'view_mode': setting.view_mode if setting else 'card',
                'items_per_page': setting.items_per_page if setting else 12,
                'kwh_price': setting.kwh_price if setting else 5.0,
                'printer_power': setting.printer_power if setting else 150,
                'debug_logging': setting.debug_logging if setting else False,
                'bambu_region': setting.bambu_region if setting else 'global',
                'bambu_auto_sync_enabled': setting.bambu_auto_sync_enabled if setting else False,
                'bambu_auto_sync_interval_minutes': setting.bambu_auto_sync_interval_minutes if setting else 60,
                'bambu_last_sync_at': setting.bambu_last_sync_at.isoformat() if setting and setting.bambu_last_sync_at else None,
                'bambu_last_sync_status': setting.bambu_last_sync_status if setting else None,
                'reorder_shop_url': setting.reorder_shop_url if setting else None,
                'company_name': setting.company_name if setting else None,
                'company_street': setting.company_street if setting else None,
                'company_city': setting.company_city if setting else None,
                'company_zip': setting.company_zip if setting else None,
                'company_id': setting.company_id if setting else None,
                'company_vat_id': setting.company_vat_id if setting else None,
                'company_bank_account': setting.company_bank_account if setting else None,
                'invoice_prefix': setting.invoice_prefix if setting else 'FV',
                'invoice_counter': setting.invoice_counter if setting else 0,
                'app_timezone': setting.app_timezone if setting and setting.app_timezone else 'Europe/Prague',
                'onboarding_dismissed': setting.onboarding_dismissed if setting else False,
                'audit_logging_enabled': getattr(setting, 'audit_logging_enabled', True) if setting else True,
                # bambu_token intentionally excluded for security
            } if setting else {},

            # ── Inventory ──────────────────────────────────────────────
            'filaments': [{
                'name': f.name,
                'brand': f.brand.name if f.brand else '',
                'material': f.material.name if f.material else '',
                'color': f.color.name if f.color else '',
                'weight_total': f.weight_total,
                'weight_remaining': f.weight_remaining,
                'price': f.price,
                'quantity': f.quantity,
                'min_stock_grams': f.min_stock_grams,
                'max_stock_grams': f.max_stock_grams,
                'tag_text': f.tag_text,
                'quality_stringing': f.quality_stringing,
                'quality_adhesion': f.quality_adhesion,
                'quality_drying': f.quality_drying,
                'quality_profile': f.quality_profile,
                'quality_notes': f.quality_notes,
                'recommended_nozzle_temp': f.recommended_nozzle_temp,
                'recommended_bed_temp': f.recommended_bed_temp,
                'reorder_alert_snoozed': f.reorder_alert_snoozed,
                'shop_url': f.shop_url,
            } for f in Filament.query.all()],

            # ── Movement history ───────────────────────────────────────
            'movement_history': [{
                'filament_name': m.filament_name,
                'filament_id': m.filament_id,
                'filament_ref': _filament_ref(m.filament),
                'project_name': m.project.name if m.project else None,
                'bambu_external_id': m.bambu_job.external_id if m.bambu_job else None,
                'action_type': m.action_type,
                'weight': m.weight,
                'cost': m.cost,
                'currency': m.currency,
                'note': m.note,
                'created_at': m.created_at.isoformat() if m.created_at else None,
            } for m in MovementHistory.query.order_by(MovementHistory.created_at).all()],

            # ── Calculator / print history ─────────────────────────────
            'print_history': [{
                'filament_name': p.filament_name,
                'weight': p.weight,
                'total_cost': p.total_cost,
                'created_at': p.created_at.isoformat() if p.created_at else None,
            } for p in PrintHistory.query.order_by(PrintHistory.created_at).all()],

            # ── Projects ───────────────────────────────────────────────
            'projects': [{
                'name': proj.name,
                'description': proj.description,
                'status': proj.status,
                'client_name': proj.client_name,
                'tag_text': proj.tag_text,
                'estimated_print_time': proj.estimated_print_time,
                'due_date': proj.due_date.isoformat() if proj.due_date else None,
                'created_at': proj.created_at.isoformat() if proj.created_at else None,
                'owner': _user_ref(proj.owner),
                'owner_name': proj.owner_name,
                'created_by': _user_ref(proj.created_by),
                'files': [_project_file_payload(pf) for pf in proj.files],
                'links': [{
                    'url': pl.url,
                    'name': pl.name,
                    'og_title': pl.og_title,
                    'og_image': pl.og_image,
                    'og_description': pl.og_description,
                    'domain': pl.domain,
                } for pl in proj.links],
                'filaments': [{
                    'filament_name': pf.filament.name if pf.filament else None,
                    'filament_ref': _filament_ref(pf.filament),
                    'estimated_weight': pf.estimated_weight,
                    'is_used': pf.is_used,
                } for pf in proj.filaments],
                'quotes': [{
                    'filament_name': quote.filament_name,
                    'filament_ref': _filament_ref(quote.filament),
                    'weight': quote.weight,
                    'print_time': quote.print_time,
                    'material_cost': quote.material_cost,
                    'electricity_cost': quote.electricity_cost,
                    'base_cost': quote.base_cost,
                    'margin_percent': quote.margin_percent,
                    'margin_amount': quote.margin_amount,
                    'final_price': quote.final_price,
                    'currency': quote.currency,
                    'invoice_number': quote.invoice_number,
                    'created_at': quote.created_at.isoformat() if quote.created_at else None,
                } for quote in proj.quotes],
                'comments': [{
                    'user': _user_ref(comment.user),
                    'body': comment.body,
                    'created_at': comment.created_at.isoformat() if comment.created_at else None,
                    'updated_at': comment.updated_at.isoformat() if comment.updated_at else None,
                } for comment in proj.comments],
                'todos': [{
                    'user': _user_ref(todo.user),
                    'body': todo.body,
                    'is_done': todo.is_done,
                    'created_at': todo.created_at.isoformat() if todo.created_at else None,
                    'completed_at': todo.completed_at.isoformat() if todo.completed_at else None,
                } for todo in proj.todos],
                'print_items': [{
                    'name': pi.name,
                    'quantity_total': pi.quantity_total,
                    'quantity_done': pi.quantity_done,
                    'notes': pi.notes,
                    'sort_order': pi.sort_order,
                    'created_at': pi.created_at.isoformat() if pi.created_at else None,
                } for pi in proj.print_items],
            } for proj in Project.query.order_by(Project.created_at).all()],

            'users': [{
                'email': user.email,
                'name': user.name,
                'password_hash': user.password_hash,
                'role': user.role,
                'section_permissions': user.section_permissions,
                'is_active': user.is_active,
                'notify_project_created': user.notify_project_created,
                'notify_project_status_changed': user.notify_project_status_changed,
                'notify_project_comment': user.notify_project_comment,
                'created_at': user.created_at.isoformat() if user.created_at else None,
            } for user in User.query.order_by(User.created_at).all()],

            'user_invites': [{
                'email': invite.email,
                'code': invite.code,
                'role': invite.role,
                'section_permissions': invite.section_permissions,
                'is_used': invite.is_used,
                'created_at': invite.created_at.isoformat() if invite.created_at else None,
                'expires_at': invite.expires_at.isoformat() if invite.expires_at else None,
            } for invite in UserInvite.query.order_by(UserInvite.created_at).all()],

            'notifications': [{
                'user': _user_ref(notification.user),
                'kind': notification.kind,
                'title': notification.title,
                'body': notification.body,
                'link': notification.link,
                'is_read': notification.is_read,
                'created_at': notification.created_at.isoformat() if notification.created_at else None,
            } for notification in Notification.query.order_by(Notification.created_at).all()],

            'audit_logs': [{
                'user': _user_ref(audit.user),
                'user_email': audit.user_email,
                'user_name': audit.user_name,
                'session_id': audit.session_id,
                'ip_address': audit.ip_address,
                'user_agent': audit.user_agent,
                'method': audit.method,
                'endpoint': audit.endpoint,
                'path': audit.path,
                'action': audit.action,
                'object_type': audit.object_type,
                'object_id': audit.object_id,
                'before_data': audit.before_data,
                'after_data': audit.after_data,
                'created_at': audit.created_at.isoformat() if audit.created_at else None,
            } for audit in AuditLog.query.order_by(AuditLog.created_at).all()],

            # ── Bambu integration ──────────────────────────────────────
            'bambu_printers': [{
                'device_id': bp.device_id,
                'name': bp.name,
                'printer_model': bp.printer_model,
                'notes': bp.notes,
                'pre_job_time_minutes': bp.pre_job_time_minutes or 0,
                'power_draw_watts': bp.power_draw_watts,
            } for bp in BambuPrinter.query.all()],

            'bambu_jobs': [{
                'external_id': j.external_id,
                'printer_name': j.printer_name,
                'printer_model': j.printer_model,
                'device_id': j.device_id,
                'model_name': j.model_name,
                'status': j.status,
                'weight_grams': j.weight_grams,
                'cost_time': j.cost_time,
                'started_at': j.started_at.isoformat() if j.started_at else None,
                'finished_at': j.finished_at.isoformat() if j.finished_at else None,
                'synced_at': j.synced_at.isoformat() if j.synced_at else None,
                'deducted': j.deducted,
                'filament_name': j.filament.name if j.filament else None,
                'filament_ref': _filament_ref(j.filament),
                'project_name': j.project.name if j.project else None,
                'materials': [{
                    'ams_id': m.ams_id,
                    'tray_id': m.tray_id,
                    'color_hex': m.color_hex,
                    'material_name': m.material_name,
                    'weight_grams': m.weight_grams,
                    'filament_name': m.filament.name if m.filament else None,
                    'filament_ref': _filament_ref(m.filament),
                    'deducted': m.deducted,
                } for m in j.materials],
            } for j in BambuPrintJob.query.order_by(BambuPrintJob.started_at).all()],

            # ── Storage visualization ────────────────────────────────
            'storage_shelves': [{
                'name': shelf.name,
                'columns': shelf.columns,
                'slots_count': shelf.slots_count,
                'sort_order': shelf.sort_order,
            } for shelf in StorageShelf.query.order_by(StorageShelf.sort_order, StorageShelf.name).all()],

            'storage_placements': [{
                'shelf_name': placement.shelf.name if placement.shelf else None,
                'filament_name': placement.filament.name if placement.filament else None,
                'filament_ref': _filament_ref(placement.filament),
                'slot_index': placement.slot_index,
                'orientation': placement.orientation,
            } for placement in StoragePlacement.query.order_by(StoragePlacement.shelf_id, StoragePlacement.slot_index).all()],

            # ── PrusaLink integration ────────────────────────────────
            'prusa_printers': [{
                'name': pp.name,
                'host': pp.host,
                # api_key intentionally excluded for security
                'printer_model': pp.printer_model,
                'notes': pp.notes,
                'enabled': pp.enabled,
                'last_sync_at': pp.last_sync_at.isoformat() if pp.last_sync_at else None,
                'last_success_at': pp.last_success_at.isoformat() if pp.last_success_at else None,
                'last_sync_status': pp.last_sync_status,
                'power_draw_watts': pp.power_draw_watts,
            } for pp in PrusaPrinter.query.all()],

            'prusa_jobs': [{
                'printer_name': j.printer_name,
                'file_name': j.file_name,
                'display_name': j.display_name,
                'status': j.status,
                'weight_grams': j.weight_grams,
                'cost_time': j.cost_time,
                'progress': j.progress,
                'started_at': j.started_at.isoformat() if j.started_at else None,
                'finished_at': j.finished_at.isoformat() if j.finished_at else None,
                'synced_at': j.synced_at.isoformat() if j.synced_at else None,
                'deducted': j.deducted,
                'filament_name': j.filament.name if j.filament else None,
                'filament_ref': _filament_ref(j.filament),
                'project_name': j.project.name if j.project else None,
            } for j in PrusaPrintJob.query.order_by(PrusaPrintJob.synced_at).all()],

            # ── Printer maintenance records ───────────────────────────
            'printer_maintenance': [{
                'printer_type': m.printer_type,
                'printer_id': m.printer_id,
                'printer_name': m.printer_name,
                'maintenance_type': m.maintenance_type,
                'notes': m.notes,
                'performed_at': m.performed_at.isoformat() if m.performed_at else None,
                'next_service_at': m.next_service_at.isoformat() if m.next_service_at else None,
                'recurrence_type': m.recurrence_type,
                'recurrence_value': m.recurrence_value,
                'recurrence_enabled': m.recurrence_enabled,
                'last_renewed_at': m.last_renewed_at.isoformat() if m.last_renewed_at else None,
                'created_at': m.created_at.isoformat() if m.created_at else None,
            } for m in PrinterMaintenance.query.order_by(PrinterMaintenance.performed_at).all()],

            # ── Waste records ────────────────────────────────────────────
            'waste_records': [{
                'filament_name': w.filament.name if w.filament else None,
                'filament_ref': _filament_ref(w.filament),
                'project_name': w.project.name if w.project else None,
                'reason': w.reason,
                'weight_grams': w.weight_grams,
                'notes': w.notes,
                'created_at': w.created_at.isoformat() if w.created_at else None,
                'recorded_by': _user_ref(w.recorded_by),
                'files': [{
                    'filename': wf.filename,
                    'archive_path': f'waste_files/w{w.id}_{wf.id}_{wf.filename}',
                    'filepath': wf.filepath,
                    'uploaded_at': wf.uploaded_at.isoformat() if wf.uploaded_at else None,
                } for wf in w.files],
            } for w in WasteRecord.query.order_by(WasteRecord.created_at).all()],

            # ── Undo log ─────────────────────────────────────────────
            'undo_logs': [{
                'created_at': ul.created_at.isoformat() if ul.created_at else None,
                'user_email': ul.user.email if ul.user else None,
                'action_type': ul.action_type,
                'filament_name': ul.filament.name if ul.filament else None,
                'filament_ref': _filament_ref(ul.filament),
                'snapshot_data': ul.snapshot_data,
                'expires_at': ul.expires_at.isoformat() if ul.expires_at else None,
                'is_consumed': ul.is_consumed,
                'consumed_at': ul.consumed_at.isoformat() if ul.consumed_at else None,
            } for ul in FilamentUndoLog.query.order_by(FilamentUndoLog.created_at).all()],
        }

        app.logger.debug(
            f"Export: {len(data['filaments'])} filaments, "
            f"{len(data['projects'])} projects, "
            f"{len(data['bambu_jobs'])} Bambu jobs"
        )
        archive_buffer = io.BytesIO()
        manifest_bytes = json.dumps(data, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
        with tarfile.open(fileobj=archive_buffer, mode='w:gz') as archive:
            manifest_info = tarfile.TarInfo('manifest.json')
            manifest_info.size = len(manifest_bytes)
            archive.addfile(manifest_info, io.BytesIO(manifest_bytes))
            for project in data.get('projects', []):
                for file_data in project.get('files', []):
                    archive_path = file_data.get('archive_path')
                    source_path = file_data.get('filepath')
                    if not archive_path or not source_path or not os.path.isfile(source_path):
                        continue
                    with open(source_path, 'rb') as handle:
                        content = handle.read()
                    file_info = tarfile.TarInfo(archive_path)
                    file_info.size = len(content)
                    archive.addfile(file_info, io.BytesIO(content))
            for w_rec in data.get('waste_records', []):
                for file_data in w_rec.get('files', []):
                    archive_path = file_data.get('archive_path')
                    source_path = file_data.get('filepath')
                    if not archive_path or not source_path or not os.path.isfile(source_path):
                        continue
                    with open(source_path, 'rb') as handle:
                        content = handle.read()
                    file_info = tarfile.TarInfo(archive_path)
                    file_info.size = len(content)
                    archive.addfile(file_info, io.BytesIO(content))
        response = Response(archive_buffer.getvalue(), mimetype='application/gzip')
        response.headers['Content-Disposition'] = 'attachment; filename=filament_backup.tar.gz'
        return response

    @bp.route('/import', methods=['POST'])
    def import_data():
        from datetime import datetime
        file = request.files.get('file')
        if not file or file.filename == '':
            return redirect(url_for('settings'))

        imported_filaments = 0
        upload_folder = app.config.get('PROJECT_UPLOAD_FOLDER')
        os.makedirs(upload_folder, exist_ok=True)
        try:
            data, backup_files = _load_backup_package(file)
            with db.session.begin():
                # ── 1. Enumerations ────────────────────────────────────
                for b_data in data.get('brands', []):
                    b_name = b_data if isinstance(b_data, str) else b_data.get('name', '')
                    if not b_name:
                        continue
                    existing = Brand.query.filter_by(name=b_name).first()
                    if not existing:
                        db.session.add(Brand(name=b_name, shop_url=b_data.get('shop_url') if isinstance(b_data, dict) else None))
                    elif isinstance(b_data, dict) and b_data.get('shop_url'):
                        existing.shop_url = b_data['shop_url']

                for m_name in data.get('materials', []):
                    if not Material.query.filter_by(name=m_name).first():
                        db.session.add(Material(name=m_name))

                for c in data.get('colors', []):
                    if not Color.query.filter_by(name=c.get('name')).first():
                        db.session.add(Color(name=c.get('name'), hex_value=c.get('hex_value', '')))

                db.session.flush()

                # ── 2. App settings ────────────────────────────────────
                s = data.get('app_settings', {})
                if s:
                    setting = AppSetting.query.first()
                    if setting:
                        setting.lang = s.get('lang', setting.lang)
                        setting.currency = s.get('currency', setting.currency)
                        setting.theme = s.get('theme', setting.theme)
                        setting.nav_palette = s.get('nav_palette', setting.nav_palette)
                        setting.view_mode = s.get('view_mode', setting.view_mode)
                        setting.items_per_page = s.get('items_per_page', setting.items_per_page)
                        setting.kwh_price = s.get('kwh_price', setting.kwh_price)
                        setting.printer_power = s.get('printer_power', setting.printer_power)
                        setting.debug_logging = s.get('debug_logging', setting.debug_logging)
                        setting.bambu_region = s.get('bambu_region', setting.bambu_region)
                        setting.bambu_auto_sync_enabled = s.get('bambu_auto_sync_enabled', setting.bambu_auto_sync_enabled)
                        setting.bambu_auto_sync_interval_minutes = s.get('bambu_auto_sync_interval_minutes', setting.bambu_auto_sync_interval_minutes)
                        setting.bambu_last_sync_at = datetime.fromisoformat(s['bambu_last_sync_at']) if s.get('bambu_last_sync_at') else setting.bambu_last_sync_at
                        setting.bambu_last_sync_status = s.get('bambu_last_sync_status', setting.bambu_last_sync_status)
                        setting.reorder_shop_url = s.get('reorder_shop_url', setting.reorder_shop_url)
                        setting.company_name = s.get('company_name', setting.company_name)
                        setting.company_street = s.get('company_street', setting.company_street)
                        setting.company_city = s.get('company_city', setting.company_city)
                        setting.company_zip = s.get('company_zip', setting.company_zip)
                        setting.company_id = s.get('company_id', setting.company_id)
                        setting.company_vat_id = s.get('company_vat_id', setting.company_vat_id)
                        setting.company_bank_account = s.get('company_bank_account', setting.company_bank_account)
                        setting.invoice_prefix = s.get('invoice_prefix', setting.invoice_prefix)
                        setting.invoice_counter = s.get('invoice_counter', setting.invoice_counter)
                        setting.app_timezone = s.get('app_timezone', setting.app_timezone)
                        setting.onboarding_dismissed = s.get('onboarding_dismissed', setting.onboarding_dismissed)
                        if 'audit_logging_enabled' in s:
                            setting.audit_logging_enabled = s['audit_logging_enabled']

                # ── 2b. Users, invites, notifications ────────────────
                for user_data in data.get('users', []):
                    email = (user_data.get('email') or '').strip().lower()
                    if not email:
                        continue
                    existing_user = User.query.filter_by(email=email).first()
                    if not existing_user:
                        existing_user = User(
                            email=email,
                            name=user_data.get('name', email),
                            password_hash=user_data.get('password_hash', ''),
                            role=user_data.get('role', 'user'),
                            section_permissions=user_data.get('section_permissions'),
                            is_active=user_data.get('is_active', True),
                            notify_project_created=user_data.get('notify_project_created', True),
                            notify_project_status_changed=user_data.get('notify_project_status_changed', True),
                            notify_project_comment=user_data.get('notify_project_comment', True),
                            created_at=datetime.fromisoformat(user_data['created_at']) if user_data.get('created_at') else utc_now(),
                        )
                        db.session.add(existing_user)

                db.session.flush()

                for invite_data in data.get('user_invites', []):
                    code = invite_data.get('code')
                    if not code or UserInvite.query.filter_by(code=code).first():
                        continue
                    db.session.add(UserInvite(
                        email=invite_data.get('email'),
                        code=code,
                        role=invite_data.get('role', 'user'),
                        section_permissions=invite_data.get('section_permissions'),
                        is_used=invite_data.get('is_used', False),
                        created_at=datetime.fromisoformat(invite_data['created_at']) if invite_data.get('created_at') else utc_now(),
                        expires_at=datetime.fromisoformat(invite_data['expires_at']) if invite_data.get('expires_at') else None,
                    ))

                # ── 3. Filaments ───────────────────────────────────────
                for f in data.get('filaments', []):
                    b = Brand.query.filter_by(name=f.get('brand')).first()
                    m = Material.query.filter_by(name=f.get('material')).first()
                    c = Color.query.filter_by(name=f.get('color')).first()
                    if b and m and c:
                        exists = Filament.query.filter_by(
                            name=f.get('name'), brand_id=b.id, material_id=m.id, color_id=c.id
                        ).first()
                        if not exists:
                            db.session.add(Filament(
                                name=f.get('name'),
                                brand_id=b.id, material_id=m.id, color_id=c.id,
                                weight_total=f.get('weight_total', 1000),
                                weight_remaining=f.get('weight_remaining', 1000),
                                price=f.get('price', 0),
                                quantity=f.get('quantity', 1),
                                min_stock_grams=f.get('min_stock_grams', 0),
                                max_stock_grams=f.get('max_stock_grams', 0),
                                tag_text=format_tags(f.get('tag_text', '')),
                                quality_stringing=f.get('quality_stringing'),
                                quality_adhesion=f.get('quality_adhesion'),
                                quality_drying=f.get('quality_drying'),
                                quality_profile=f.get('quality_profile'),
                                quality_notes=f.get('quality_notes'),
                                recommended_nozzle_temp=f.get('recommended_nozzle_temp'),
                                recommended_bed_temp=f.get('recommended_bed_temp'),
                                reorder_alert_snoozed=f.get('reorder_alert_snoozed', False),
                                shop_url=f.get('shop_url'),
                            ))
                            imported_filaments += 1

                db.session.flush()

                # ── 4. Print history (calculator) ─────────────────────
                for p in data.get('print_history', []):
                    ts = datetime.fromisoformat(p['created_at']) if p.get('created_at') else utc_now()
                    exists = PrintHistory.query.filter_by(
                        filament_name=p.get('filament_name'),
                        created_at=ts,
                    ).first()
                    if not exists:
                        db.session.add(PrintHistory(
                            filament_name=p.get('filament_name'),
                            weight=p.get('weight', 0),
                            total_cost=p.get('total_cost', 0),
                            created_at=ts,
                        ))

                # ── 5. Projects ───────────────────────────────────────
                for proj_data in data.get('projects', []):
                    proj = Project.query.filter_by(name=proj_data.get('name')).first()
                    if not proj:
                        proj = Project(
                            name=proj_data.get('name'),
                            description=proj_data.get('description'),
                            status=proj_data.get('status', 'NEW'),
                            client_name=proj_data.get('client_name'),
                            tag_text=format_tags(proj_data.get('tag_text', '')),
                            estimated_print_time=proj_data.get('estimated_print_time', 0),
                            due_date=datetime.fromisoformat(proj_data['due_date']) if proj_data.get('due_date') else None,
                            created_at=datetime.fromisoformat(proj_data['created_at']) if proj_data.get('created_at') else utc_now(),
                            owner_user_id=_resolve_user_ref(proj_data.get('owner')).id if _resolve_user_ref(proj_data.get('owner')) else None,
                            owner_name=(proj_data.get('owner_name') or '').strip() or None,
                            created_by_user_id=_resolve_user_ref(proj_data.get('created_by')).id if _resolve_user_ref(proj_data.get('created_by')) else None,
                        )
                        db.session.add(proj)
                        db.session.flush()
                    else:
                        proj.tag_text = format_tags(proj_data.get('tag_text', proj.tag_text or ''))
                        if 'owner_name' in proj_data:
                            proj.owner_name = (proj_data.get('owner_name') or '').strip() or None

                    for file_data in proj_data.get('files', []):
                        uploaded_at = datetime.fromisoformat(file_data['uploaded_at']) if file_data.get('uploaded_at') else utc_now()
                        exists_file = ProjectFile.query.filter_by(
                            project_id=proj.id,
                            filename=file_data.get('filename', ''),
                            uploaded_at=uploaded_at,
                        ).first()
                        if not exists_file:
                            filepath = file_data.get('filepath', '')
                            archive_path = file_data.get('archive_path')
                            content_b64 = file_data.get('content_b64')
                            if archive_path and archive_path in backup_files:
                                filepath = _build_import_file_path(upload_folder, proj.id, file_data.get('filename', ''), file_data.get('uploaded_at'))
                                with open(filepath, 'wb') as handle:
                                    handle.write(backup_files[archive_path])
                            elif content_b64:
                                filepath = _build_import_file_path(upload_folder, proj.id, file_data.get('filename', ''), file_data.get('uploaded_at'))
                                with open(filepath, 'wb') as handle:
                                    handle.write(base64.b64decode(content_b64))
                            db.session.add(ProjectFile(
                                project_id=proj.id,
                                filename=file_data.get('filename', ''),
                                filepath=filepath,
                                uploaded_at=uploaded_at,
                            ))

                    for link in proj_data.get('links', []):
                        exists_link = ProjectLink.query.filter_by(
                            project_id=proj.id,
                            url=link.get('url', ''),
                        ).first()
                        if not exists_link:
                            db.session.add(ProjectLink(
                                project_id=proj.id,
                                url=link.get('url', ''),
                                name=link.get('name'),
                                og_title=link.get('og_title'),
                                og_image=link.get('og_image'),
                                og_description=link.get('og_description'),
                                domain=link.get('domain'),
                            ))

                    for pf_data in proj_data.get('filaments', []):
                        fil = _resolve_filament_ref(pf_data.get('filament_ref'), pf_data.get('filament_name'))
                        exists_pf = None
                        if fil:
                            exists_pf = ProjectFilament.query.filter_by(
                                project_id=proj.id,
                                filament_id=fil.id,
                                estimated_weight=pf_data.get('estimated_weight', 0),
                            ).first()
                        if fil and not exists_pf:
                            db.session.add(ProjectFilament(
                                project_id=proj.id,
                                filament_id=fil.id,
                                estimated_weight=pf_data.get('estimated_weight', 0),
                                is_used=pf_data.get('is_used', False),
                            ))

                    for quote_data in proj_data.get('quotes', []):
                        quote_ts = datetime.fromisoformat(quote_data['created_at']) if quote_data.get('created_at') else utc_now()
                        exists_quote = ProjectQuote.query.filter_by(
                            project_id=proj.id,
                            filament_name=quote_data.get('filament_name'),
                            created_at=quote_ts,
                        ).first()
                        if not exists_quote:
                            quote_fil = _resolve_filament_ref(quote_data.get('filament_ref'), quote_data.get('filament_name'))
                            db.session.add(ProjectQuote(
                                project_id=proj.id,
                                filament_id=quote_fil.id if quote_fil else None,
                                filament_name=quote_data.get('filament_name', ''),
                                weight=quote_data.get('weight', 0),
                                print_time=quote_data.get('print_time', 0),
                                material_cost=quote_data.get('material_cost', 0),
                                electricity_cost=quote_data.get('electricity_cost', 0),
                                base_cost=quote_data.get('base_cost', 0),
                                margin_percent=quote_data.get('margin_percent', 0),
                                margin_amount=quote_data.get('margin_amount', 0),
                                final_price=quote_data.get('final_price', 0),
                                currency=quote_data.get('currency', 'CZK'),
                                invoice_number=quote_data.get('invoice_number'),
                                created_at=quote_ts,
                            ))

                    for comment_data in proj_data.get('comments', []):
                        comment_ts = datetime.fromisoformat(comment_data['created_at']) if comment_data.get('created_at') else utc_now()
                        existing_comment = ProjectComment.query.filter_by(
                            project_id=proj.id,
                            body=comment_data.get('body', ''),
                            created_at=comment_ts,
                        ).first()
                        comment_user = _resolve_user_ref(comment_data.get('user'))
                        if not existing_comment:
                            db.session.add(ProjectComment(
                                project_id=proj.id,
                                user_id=comment_user.id if comment_user else None,
                                body=comment_data.get('body', ''),
                                created_at=comment_ts,
                                updated_at=datetime.fromisoformat(comment_data['updated_at']) if comment_data.get('updated_at') else None,
                            ))

                    for todo_data in proj_data.get('todos', []):
                        todo_ts = datetime.fromisoformat(todo_data['created_at']) if todo_data.get('created_at') else utc_now()
                        existing_todo = ProjectTodo.query.filter_by(
                            project_id=proj.id,
                            body=todo_data.get('body', ''),
                            created_at=todo_ts,
                        ).first()
                        todo_user = _resolve_user_ref(todo_data.get('user'))
                        if not existing_todo:
                            db.session.add(ProjectTodo(
                                project_id=proj.id,
                                user_id=todo_user.id if todo_user else None,
                                body=(todo_data.get('body') or '')[:255],
                                is_done=todo_data.get('is_done', False),
                                created_at=todo_ts,
                                completed_at=datetime.fromisoformat(todo_data['completed_at']) if todo_data.get('completed_at') else None,
                            ))

                    for pi_data in proj_data.get('print_items', []):
                        pi_ts = datetime.fromisoformat(pi_data['created_at']) if pi_data.get('created_at') else utc_now()
                        existing_pi = ProjectPrintItem.query.filter_by(
                            project_id=proj.id,
                            name=pi_data.get('name', ''),
                            created_at=pi_ts,
                        ).first()
                        if not existing_pi:
                            db.session.add(ProjectPrintItem(
                                project_id=proj.id,
                                name=(pi_data.get('name') or '')[:200],
                                quantity_total=max(1, int(pi_data.get('quantity_total', 1) or 1)),
                                quantity_done=max(0, int(pi_data.get('quantity_done', 0) or 0)),
                                notes=pi_data.get('notes'),
                                sort_order=int(pi_data.get('sort_order', 0) or 0),
                                created_at=pi_ts,
                            ))

                # ── 6. Bambu printers ─────────────────────────────────
                for bp in data.get('bambu_printers', []):
                    if not BambuPrinter.query.filter_by(device_id=bp.get('device_id')).first():
                        db.session.add(BambuPrinter(
                            device_id=bp.get('device_id'),
                            name=bp.get('name', ''),
                            printer_model=bp.get('printer_model'),
                            notes=bp.get('notes'),
                            pre_job_time_minutes=bp.get('pre_job_time_minutes', 0),
                            power_draw_watts=bp.get('power_draw_watts'),
                        ))

                # ── 7. Bambu jobs ─────────────────────────────────────
                for j in data.get('bambu_jobs', []):
                    if BambuPrintJob.query.filter_by(external_id=j.get('external_id')).first():
                        continue
                    fil = _resolve_filament_ref(j.get('filament_ref'), j.get('filament_name'))
                    proj = Project.query.filter_by(name=j.get('project_name')).first() if j.get('project_name') else None
                    job = BambuPrintJob(
                        external_id=j.get('external_id'),
                        printer_name=j.get('printer_name'),
                        printer_model=j.get('printer_model'),
                        device_id=j.get('device_id'),
                        model_name=j.get('model_name'),
                        status=j.get('status'),
                        weight_grams=j.get('weight_grams'),
                        cost_time=j.get('cost_time'),
                        started_at=datetime.fromisoformat(j['started_at']) if j.get('started_at') else None,
                        finished_at=datetime.fromisoformat(j['finished_at']) if j.get('finished_at') else None,
                        synced_at=datetime.fromisoformat(j['synced_at']) if j.get('synced_at') else utc_now(),
                        deducted=j.get('deducted', False),
                        filament_id=fil.id if fil else None,
                        project_id=proj.id if proj else None,
                    )
                    db.session.add(job)
                    db.session.flush()

                    for mat in j.get('materials', []):
                        mat_fil = _resolve_filament_ref(mat.get('filament_ref'), mat.get('filament_name'))
                        db.session.add(BambuJobMaterial(
                            job_id=job.id,
                            ams_id=mat.get('ams_id'),
                            tray_id=mat.get('tray_id'),
                            color_hex=mat.get('color_hex'),
                            material_name=mat.get('material_name'),
                            weight_grams=mat.get('weight_grams'),
                            filament_id=mat_fil.id if mat_fil else None,
                            deducted=mat.get('deducted', False),
                        ))

                db.session.flush()

                # ── 8. Movement history ────────────────────────────────
                for m in data.get('movement_history', []):
                    ts = datetime.fromisoformat(m['created_at']) if m.get('created_at') else utc_now()
                    exists = MovementHistory.query.filter_by(
                        filament_name=m.get('filament_name'),
                        action_type=m.get('action_type'),
                        created_at=ts,
                    ).first()
                    if exists:
                        continue

                    filament = _resolve_filament_ref(m.get('filament_ref'), m.get('filament_name'))
                    project = Project.query.filter_by(name=m.get('project_name')).first() if m.get('project_name') else None
                    bambu_job = BambuPrintJob.query.filter_by(external_id=m.get('bambu_external_id')).first() if m.get('bambu_external_id') else None

                    db.session.add(MovementHistory(
                        filament_id=filament.id if filament else None,
                        project_id=project.id if project else None,
                        bambu_job_id=bambu_job.id if bambu_job else None,
                        filament_name=m.get('filament_name'),
                        action_type=m.get('action_type'),
                        weight=m.get('weight', 0),
                        cost=m.get('cost', 0),
                        currency=m.get('currency', 'CZK'),
                        created_at=ts,
                        note=m.get('note'),
                    ))

                # ── 9. Storage shelves and placements ─────────────────
                for shelf_data in data.get('storage_shelves', []):
                    shelf_name = shelf_data.get('name')
                    if not shelf_name or StorageShelf.query.filter_by(name=shelf_name).first():
                        continue
                    db.session.add(StorageShelf(
                        name=shelf_name,
                        columns=max(shelf_data.get('columns', 4) or 4, 1),
                        slots_count=max(shelf_data.get('slots_count', 12) or 12, 1),
                        sort_order=shelf_data.get('sort_order', 0) or 0,
                    ))

                db.session.flush()

                for placement_data in data.get('storage_placements', []):
                    shelf = StorageShelf.query.filter_by(name=placement_data.get('shelf_name')).first()
                    filament = _resolve_filament_ref(placement_data.get('filament_ref'), placement_data.get('filament_name'))
                    slot_index = placement_data.get('slot_index')
                    if not shelf or not filament or not slot_index:
                        continue
                    exists_placement = StoragePlacement.query.filter_by(
                        shelf_id=shelf.id,
                        slot_index=slot_index,
                    ).first()
                    if exists_placement:
                        continue
                    db.session.add(StoragePlacement(
                        shelf_id=shelf.id,
                        filament_id=filament.id,
                        slot_index=slot_index,
                        orientation=placement_data.get('orientation', 'standing') or 'standing',
                    ))

                # ── 10. PrusaLink printers (no api_key — user must re-enter it) ──
                for pp in data.get('prusa_printers', []):
                    if PrusaPrinter.query.filter_by(name=pp.get('name'), host=pp.get('host', '')).first():
                        continue
                    # Only restore if host present; api_key is not exported so skip
                    if pp.get('host'):
                        restored_printer = PrusaPrinter(
                            name=pp.get('name', ''),
                            host=pp.get('host', ''),
                            api_key=encrypt_token('NEEDS_CONFIGURATION'),
                            printer_model=pp.get('printer_model'),
                            notes=pp.get('notes'),
                            enabled=pp.get('enabled', True),
                            power_draw_watts=pp.get('power_draw_watts'),
                        )
                        if pp.get('last_sync_at'):
                            restored_printer.last_sync_at = datetime.fromisoformat(pp['last_sync_at'])
                        if pp.get('last_success_at'):
                            restored_printer.last_success_at = datetime.fromisoformat(pp['last_success_at'])
                        restored_printer.last_sync_status = pp.get('last_sync_status')
                        db.session.add(restored_printer)

                db.session.flush()

                # ── 11. PrusaLink jobs ────────────────────────────────
                for j in data.get('prusa_jobs', []):
                    pp_printer = PrusaPrinter.query.filter_by(name=j.get('printer_name')).first() if j.get('printer_name') else None
                    exists = PrusaPrintJob.query.filter_by(
                        printer_name=j.get('printer_name'),
                        file_name=j.get('file_name'),
                        synced_at=datetime.fromisoformat(j['synced_at']) if j.get('synced_at') else None,
                    ).first()
                    if exists:
                        continue
                    fil = _resolve_filament_ref(j.get('filament_ref'), j.get('filament_name'))
                    proj = Project.query.filter_by(name=j.get('project_name')).first() if j.get('project_name') else None
                    db.session.add(PrusaPrintJob(
                        printer_id=pp_printer.id if pp_printer else None,
                        printer_name=j.get('printer_name'),
                        file_name=j.get('file_name'),
                        display_name=j.get('display_name'),
                        status=j.get('status'),
                        weight_grams=j.get('weight_grams'),
                        cost_time=j.get('cost_time'),
                        progress=j.get('progress'),
                        started_at=datetime.fromisoformat(j['started_at']) if j.get('started_at') else None,
                        finished_at=datetime.fromisoformat(j['finished_at']) if j.get('finished_at') else None,
                        synced_at=datetime.fromisoformat(j['synced_at']) if j.get('synced_at') else utc_now(),
                        deducted=j.get('deducted', False),
                        filament_id=fil.id if fil else None,
                        project_id=proj.id if proj else None,
                    ))

                for notification_data in data.get('notifications', []):
                    notification_ts = datetime.fromisoformat(notification_data['created_at']) if notification_data.get('created_at') else utc_now()
                    notification_user = _resolve_user_ref(notification_data.get('user'))
                    if not notification_user:
                        continue
                    exists_notification = Notification.query.filter_by(
                        user_id=notification_user.id,
                        title=notification_data.get('title', ''),
                        created_at=notification_ts,
                    ).first()
                    if not exists_notification:
                        db.session.add(Notification(
                            user_id=notification_user.id,
                            kind=notification_data.get('kind', 'info'),
                            title=notification_data.get('title', ''),
                            body=notification_data.get('body'),
                            link=notification_data.get('link'),
                            is_read=notification_data.get('is_read', False),
                            created_at=notification_ts,
                        ))

                for audit_data in data.get('audit_logs', []):
                    audit_ts = datetime.fromisoformat(audit_data['created_at']) if audit_data.get('created_at') else utc_now()
                    audit_user = _resolve_user_ref(audit_data.get('user'))
                    exists_audit = AuditLog.query.filter_by(
                        user_id=audit_user.id if audit_user else None,
                        endpoint=audit_data.get('endpoint'),
                        path=audit_data.get('path', ''),
                        action=audit_data.get('action', ''),
                        created_at=audit_ts,
                    ).first()
                    if exists_audit:
                        continue
                    db.session.add(AuditLog(
                        user_id=audit_user.id if audit_user else None,
                        user_email=audit_data.get('user_email'),
                        user_name=audit_data.get('user_name'),
                        session_id=audit_data.get('session_id'),
                        ip_address=audit_data.get('ip_address'),
                        user_agent=audit_data.get('user_agent'),
                        method=audit_data.get('method', 'POST'),
                        endpoint=audit_data.get('endpoint'),
                        path=audit_data.get('path', ''),
                        action=audit_data.get('action', ''),
                        object_type=audit_data.get('object_type'),
                        object_id=audit_data.get('object_id'),
                        before_data=audit_data.get('before_data'),
                        after_data=audit_data.get('after_data'),
                        created_at=audit_ts,
                    ))

                # ── 12. Printer maintenance records ───────────────────
                for m_data in data.get('printer_maintenance', []):
                    performed_at = datetime.fromisoformat(m_data['performed_at']) if m_data.get('performed_at') else utc_now()
                    exists_m = PrinterMaintenance.query.filter_by(
                        printer_name=m_data.get('printer_name', ''),
                        maintenance_type=m_data.get('maintenance_type', 'other'),
                        performed_at=performed_at,
                    ).first()
                    if exists_m:
                        continue
                    db.session.add(PrinterMaintenance(
                        printer_type=m_data.get('printer_type', 'bambu'),
                        printer_id=m_data.get('printer_id'),
                        printer_name=m_data.get('printer_name', ''),
                        maintenance_type=m_data.get('maintenance_type', 'other'),
                        notes=m_data.get('notes'),
                        performed_at=performed_at,
                        next_service_at=datetime.fromisoformat(m_data['next_service_at']) if m_data.get('next_service_at') else None,
                        recurrence_type=m_data.get('recurrence_type', 'none'),
                        recurrence_value=m_data.get('recurrence_value', 0),
                        recurrence_enabled=m_data.get('recurrence_enabled', False),
                        last_renewed_at=datetime.fromisoformat(m_data['last_renewed_at']) if m_data.get('last_renewed_at') else None,
                        created_at=datetime.fromisoformat(m_data['created_at']) if m_data.get('created_at') else utc_now(),
                    ))

                # ── 12b. Waste records ─────────────────────────────────
                for w_data in data.get('waste_records', []):
                    filament = _resolve_filament_ref(w_data.get('filament_ref'), w_data.get('filament_name'))
                    if not filament:
                        app.logger.warning(
                            f"Skipping waste record import: referenced filament '{w_data.get('filament_name')}' "
                            f"could not be resolved."
                        )
                        continue
                    project_id = None
                    project_name = w_data.get('project_name', '').strip()
                    if project_name:
                        proj = Project.query.filter_by(name=project_name).first()
                        if proj:
                            project_id = proj.id
                    recorded_by = _resolve_user_ref(w_data.get('recorded_by'))
                    waste_record = WasteRecord(
                        filament_id=filament.id if filament else None,
                        project_id=project_id,
                        reason=w_data.get('reason', 'other'),
                        weight_grams=w_data.get('weight_grams', 0.0) or 0.0,
                        notes=w_data.get('notes'),
                        created_at=datetime.fromisoformat(w_data['created_at']) if w_data.get('created_at') else utc_now(),
                        recorded_by_user_id=recorded_by.id if recorded_by else None,
                    )
                    db.session.add(waste_record)
                    db.session.flush()
                    for wf_data in w_data.get('files', []):
                        archive_path = wf_data.get('archive_path', '')
                        wf_content = backup_files.get(archive_path)
                        if wf_content is None:
                            continue
                        original_name = wf_data.get('filename', 'attachment.jpg')
                        stored_name = f'w{waste_record.id}_{uuid.uuid4().hex[:12]}_{original_name}'
                        dest_path = os.path.join(upload_folder, stored_name)
                        with open(dest_path, 'wb') as fh:
                            fh.write(wf_content)
                        db.session.add(WasteFile(
                            waste_record_id=waste_record.id,
                            filename=original_name,
                            filepath=dest_path,
                            uploaded_at=datetime.fromisoformat(wf_data['uploaded_at']) if wf_data.get('uploaded_at') else utc_now(),
                        ))

                # ── 13. Undo log ──────────────────────────────────────
                for ul_data in data.get('undo_logs', []):
                    ul_user = _resolve_user_ref({'email': ul_data.get('user_email')}) if ul_data.get('user_email') else None
                    if not ul_user:
                        continue
                    filament = _resolve_filament_ref(ul_data.get('filament_ref'), ul_data.get('filament_name'))
                    db.session.add(FilamentUndoLog(
                        created_at=datetime.fromisoformat(ul_data['created_at']) if ul_data.get('created_at') else utc_now(),
                        user_id=ul_user.id,
                        action_type=ul_data.get('action_type', ''),
                        filament_id=filament.id if filament else None,
                        snapshot_data=ul_data.get('snapshot_data', ''),
                        expires_at=datetime.fromisoformat(ul_data['expires_at']) if ul_data.get('expires_at') else utc_now(),
                        is_consumed=ul_data.get('is_consumed', True),
                        consumed_at=datetime.fromisoformat(ul_data['consumed_at']) if ul_data.get('consumed_at') else None,
                    ))

            app.logger.debug(f"Import finished: {imported_filaments} filaments, projects and Bambu jobs processed.")
        except Exception as e:
            db.session.rollback()
            app.logger.error(f"Import failed: {str(e)}")

        return redirect(url_for('settings'))
    app.register_blueprint(bp)
