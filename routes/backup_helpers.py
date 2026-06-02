"""Full database export and import endpoints for backups."""
import base64
import gzip
import io
import json
import os
import tarfile
import uuid
from flask import current_app as app, request, redirect, url_for, Response, Blueprint, flash

from database import db
from models import (
    Brand, Color, Material, AppSetting, Filament, MovementHistory,
    PrintHistory, Project, ProjectFile, ProjectLink, ProjectFilament, ProjectQuote,
    BambuPrinter, BambuPrintJob, BambuJobMaterial, StoragePlacement, StorageShelf,
    PrusaPrinter, PrusaPrintJob, ProjectComment, ProjectTodo, ProjectPrintItem, User, UserInvite, Notification, AuditLog,
    PrinterMaintenance, WasteRecord, WasteFile, FilamentUndoLog, ProjectTemplate,
)
from utils import encrypt_token, format_tags, utc_now, translate



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
        'version': project_file.version,
        'parent_file_id': project_file.parent_file_id,
        'display_name': project_file.display_name,
        'file_size_bytes': project_file.file_size_bytes,
        'mime_type': project_file.mime_type,
        'checksum_sha256': project_file.checksum_sha256,
        'thumbnail_path': project_file.thumbnail_path,
        'version_note': project_file.version_note,
        'uploaded_by': _user_ref(project_file.uploaded_by) if getattr(project_file, 'uploaded_by', None) else None,
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


def _build_export_data(app, include_files=True):
    """Build the full export data dict. Returns (data_dict, app_setting)."""
    setting = AppSetting.query.first()

    data = {
            'backup_meta': {
                'format_version': 2,
                'packaging': 'tar.gz',
                'include_files': include_files,
                'app_version': app.config.get('APP_VERSION', 'unknown'),
                'created_at': utc_now().isoformat(),
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
                'bambu_last_test_at': setting.bambu_last_test_at.isoformat() if setting and setting.bambu_last_test_at else None,
                'bambu_last_test_status': setting.bambu_last_test_status if setting else None,
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
                'auto_filament_mapping_enabled': getattr(setting, 'auto_filament_mapping_enabled', True) if setting else True,
                'backup_last_export_at': setting.backup_last_export_at.isoformat() if setting and setting.backup_last_export_at else None,
                'backup_last_export_meta': setting.backup_last_export_meta if setting else None,
                'backup_auto_enabled': getattr(setting, 'backup_auto_enabled', False) if setting else False,
                'backup_auto_frequency': getattr(setting, 'backup_auto_frequency', 'weekly') if setting else 'weekly',
                'backup_auto_time': getattr(setting, 'backup_auto_time', '03:00') if setting else '03:00',
                'backup_auto_day': getattr(setting, 'backup_auto_day', 1) if setting else 1,
                'backup_auto_include_files': getattr(setting, 'backup_auto_include_files', True) if setting else True,
                'backup_auto_last_run_at': setting.backup_auto_last_run_at.isoformat() if setting and setting.backup_auto_last_run_at else None,
                'backup_auto_keep_count': getattr(setting, 'backup_auto_keep_count', 10) if setting else 10,
                'backup_auto_keep_days': getattr(setting, 'backup_auto_keep_days', 0) if setting else 0,
                'waste_reasons_json': getattr(setting, 'waste_reasons_json', '') if setting else '',
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
                'client_email': proj.client_email,
                'client_phone': proj.client_phone,
                'priority': proj.priority,
                'tag_text': proj.tag_text,
                'estimated_print_time': proj.estimated_print_time,
                'due_date': proj.due_date.isoformat() if proj.due_date else None,
                'created_at': proj.created_at.isoformat() if proj.created_at else None,
                'owner': _user_ref(proj.owner),
                'owner_name': proj.owner_name,
                'created_by': _user_ref(proj.created_by),
                'files': ([_project_file_payload(pf) for pf in proj.files] if include_files else []),
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
                    'due_date': todo.due_date.isoformat() if todo.due_date else None,
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

            'project_templates': [{
                'name': tpl.name,
                'description': tpl.description,
                'estimated_print_time': tpl.estimated_print_time,
                'tag_text': tpl.tag_text,
                'created_by': _user_ref(tpl.created_by),
                'created_at': tpl.created_at.isoformat() if tpl.created_at else None,
            } for tpl in ProjectTemplate.query.order_by(ProjectTemplate.created_at).all()],

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
                'preferred_language': user.preferred_language,
                'preferred_theme': user.preferred_theme,
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
                'notes_is_markdown': m.notes_is_markdown,
                'performed_at': m.performed_at.isoformat() if m.performed_at else None,
                'next_service_at': m.next_service_at.isoformat() if m.next_service_at else None,
                'recurrence_type': m.recurrence_type,
                'recurrence_value': m.recurrence_value,
                'recurrence_enabled': m.recurrence_enabled,
                'fault_resolved': m.fault_resolved,
                'fault_resolved_at': m.fault_resolved_at.isoformat() if m.fault_resolved_at else None,
                'predictive_enabled': m.predictive_enabled,
                'predictive_runtime_hours': m.predictive_runtime_hours,
                'predictive_jobs_count': m.predictive_jobs_count,
                'predictive_filament_grams': m.predictive_filament_grams,
                'predictive_window_days': m.predictive_window_days,
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
                'files': ([{
                    'filename': wf.filename,
                    'archive_path': f'waste_files/w{w.id}_{wf.id}_{wf.filename}',
                    'filepath': wf.filepath,
                    'uploaded_at': wf.uploaded_at.isoformat() if wf.uploaded_at else None,
                } for wf in w.files] if include_files else []),
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

    counts = {
        'brands': len(data['brands']),
        'materials': len(data['materials']),
        'colors': len(data['colors']),
        'filaments': len(data['filaments']),
        'projects': len(data['projects']),
        'users': len(data['users']),
        'bambu_jobs': len(data['bambu_jobs']),
        'prusa_jobs': len(data['prusa_jobs']),
        'movement_history': len(data['movement_history']),
        'waste_records': len(data['waste_records']),
    }
    data['backup_meta']['record_counts'] = counts
    data['backup_meta']['total_records'] = sum(counts.values())

    app.logger.debug(
        f"Export: {len(data['filaments'])} filaments, "
        f"{len(data['projects'])} projects, "
        f"{len(data['bambu_jobs'])} Bambu jobs"
    )

    return data, setting


def _build_backup_archive_bytes(app, include_files=True):
    """Build backup tar.gz archive bytes from the full export data. Returns bytes."""
    data, _setting = _build_export_data(app, include_files=include_files)

    archive_buffer = io.BytesIO()
    manifest_bytes = json.dumps(data, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    with tarfile.open(fileobj=archive_buffer, mode='w:gz') as archive:
        manifest_info = tarfile.TarInfo('manifest.json')
        manifest_info.size = len(manifest_bytes)
        archive.addfile(manifest_info, io.BytesIO(manifest_bytes))
        if include_files:
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
    return archive_buffer.getvalue()


def _cleanup_old_backups(backup_dir, keep_count=10, keep_days=0):
    """Remove backup files exceeding retention limits.

    - *keep_count*: maximum number of newest files to keep (0 = unlimited)
    - *keep_days*: maximum age in days to keep (0 = unlimited)
    Both limits are applied independently — files older than *keep_days* are
    removed even if the count is under *keep_count*, and excess files beyond
    *keep_count* are removed even if they're recent.
    """
    if not os.path.isdir(backup_dir):
        return 0

    import time as _time

    files = []
    for name in os.listdir(backup_dir):
        fpath = os.path.join(backup_dir, name)
        if os.path.isfile(fpath) and name.startswith('auto_backup_') and name.endswith('.tar.gz'):
            files.append((fpath, os.path.getmtime(fpath)))
    if not files:
        return 0

    # Sort by mtime descending (newest first)
    files.sort(key=lambda x: x[1], reverse=True)

    now = _time.time()
    deleted = 0

    for idx, (fpath, mtime) in enumerate(files):
        remove = False
        # Count-based: remove if we have more than keep_count (0 = unlimited)
        if keep_count > 0 and idx >= keep_count:
            remove = True
        # Age-based: remove if older than keep_days (0 = unlimited)
        if keep_days > 0 and (now - mtime) > (keep_days * 86400):
            remove = True
        if remove:
            try:
                os.remove(fpath)
                deleted += 1
            except OSError:
                pass
    return deleted


