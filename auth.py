import json
import secrets
from datetime import datetime, timedelta
from utils import utc_now
from functools import wraps
from urllib.parse import urljoin, urlsplit

from flask import abort, current_app, flash, g, redirect, request, session, url_for
from sqlalchemy import inspect as sa_inspect
from werkzeug.security import check_password_hash, generate_password_hash

from database import db
from models import AuditLog, Notification, User, UserInvite

SECTION_OVERVIEW = 'overview'
SECTION_FILAMENTS = 'filaments'
SECTION_PROJECTS = 'projects'
SECTION_HISTORY = 'history'
SECTION_STORAGE = 'storage'
SECTION_CALCULATOR = 'calculator'
SECTION_PRINTERS = 'printers'
SECTION_STATS = 'stats'
SECTION_SETTINGS = 'settings'
SECTION_USERS = 'users'
SECTION_NOTIFICATIONS = 'notifications'

ALL_SECTIONS = [
    SECTION_OVERVIEW,
    SECTION_FILAMENTS,
    SECTION_PROJECTS,
    SECTION_HISTORY,
    SECTION_STORAGE,
    SECTION_CALCULATOR,
    SECTION_PRINTERS,
    SECTION_STATS,
    SECTION_SETTINGS,
    SECTION_USERS,
]

PUBLIC_ENDPOINTS = {
    'login',
    'logout',
    'register_account',
    'activate_invite',
    'manifest',
    'service_worker',
    'static',
    'project_share',
}

SECTION_BY_ENDPOINT = {
    'index': SECTION_OVERVIEW,
    'filaments_index': SECTION_FILAMENTS,
    'filament_detail': SECTION_FILAMENTS,
    'api_filaments_list': SECTION_FILAMENTS,
    'api_live_printers_partial': SECTION_OVERVIEW,
    'add': SECTION_FILAMENTS,
    'edit': SECTION_FILAMENTS,
    'use_filament': SECTION_FILAMENTS,
    'add_spool': SECTION_FILAMENTS,
    'remove_spool': SECTION_FILAMENTS,
    'delete': SECTION_FILAMENTS,
    'inventory_bulk': SECTION_FILAMENTS,
    'inventory_undo': SECTION_FILAMENTS,
    'filament_update_meta': SECTION_FILAMENTS,
    'filament_toggle_reorder_snooze': SECTION_FILAMENTS,
    'api_search': SECTION_OVERVIEW,
    'calculator': SECTION_CALCULATOR,
    'calculator_project': SECTION_CALCULATOR,
    'delete_history': SECTION_CALCULATOR,
    'delete_quote': SECTION_PROJECTS,
    'export_quote': SECTION_PROJECTS,
    'history': SECTION_HISTORY,
    'clear_history': SECTION_HISTORY,
    'projects_index': SECTION_PROJECTS,
    'project_create': SECTION_PROJECTS,
    'project_detail': SECTION_PROJECTS,
    'project_edit': SECTION_PROJECTS,
    'project_delete': SECTION_PROJECTS,
    'project_upload_file': SECTION_PROJECTS,
    'project_download_file': SECTION_PROJECTS,
    'project_view_file': SECTION_PROJECTS,
    'project_image_file': SECTION_PROJECTS,
    'project_delete_file': SECTION_PROJECTS,
    'project_add_link': SECTION_PROJECTS,
    'project_delete_link': SECTION_PROJECTS,
    'project_refresh_link': SECTION_PROJECTS,
    'project_add_filament': SECTION_PROJECTS,
    'project_remove_filament': SECTION_PROJECTS,
    'project_update_filament': SECTION_PROJECTS,
    'project_status': SECTION_PROJECTS,
    'project_advance_status': SECTION_PROJECTS,
    'project_clone': SECTION_PROJECTS,
    'project_generate_share_token': SECTION_PROJECTS,
    'project_revoke_share_token': SECTION_PROJECTS,
    'project_templates_index': SECTION_PROJECTS,
    'project_template_save': SECTION_PROJECTS,
    'project_template_delete': SECTION_PROJECTS,
    'project_create_from_template': SECTION_PROJECTS,
    'project_comment_react': SECTION_PROJECTS,
    'project_consume_filament': SECTION_PROJECTS,
    'project_add_comment': SECTION_PROJECTS,
    'project_update_comment': SECTION_PROJECTS,
    'project_delete_comment': SECTION_PROJECTS,
    'project_toggle_comment_checkbox': SECTION_PROJECTS,
    'project_toggle_description_checkbox': SECTION_PROJECTS,
    'project_add_todo': SECTION_PROJECTS,
    'project_toggle_todo': SECTION_PROJECTS,
    'project_delete_todo': SECTION_PROJECTS,
    'project_edit_todo': SECTION_PROJECTS,
    'project_add_print_item': SECTION_PROJECTS,
    'project_edit_print_item': SECTION_PROJECTS,
    'project_delete_print_item': SECTION_PROJECTS,
    'project_increment_print_item': SECTION_PROJECTS,
    'project_decrement_print_item': SECTION_PROJECTS,
    'bambu_jobs': SECTION_PRINTERS,
    'bambu_jobs_partial': SECTION_PRINTERS,
    'bambu_sync': SECTION_PRINTERS,
    'bambu_refetch_thumbnails': SECTION_PRINTERS,
    'bambu_job_map': SECTION_PRINTERS,
    'bambu_job_deduct_slot': SECTION_PRINTERS,
    'bambu_job_remap_slot': SECTION_PRINTERS,
    'bambu_job_delete': SECTION_PRINTERS,
    'bambu_create_project': SECTION_PRINTERS,
    'prusa_jobs': SECTION_PRINTERS,
    'prusa_printer_sync': SECTION_PRINTERS,
    'prusa_printer_test': SECTION_PRINTERS,
    'prusa_job_map': SECTION_PRINTERS,
    'prusa_job_delete': SECTION_PRINTERS,
    'stats': SECTION_STATS,
    'storage': SECTION_STORAGE,
    'storage_add_shelf': SECTION_STORAGE,
    'storage_update_shelf': SECTION_STORAGE,
    'storage_delete_shelf': SECTION_STORAGE,
    'storage_assign_slot': SECTION_STORAGE,
    'storage_move_placement': SECTION_STORAGE,
    'storage_reorder_shelves': SECTION_STORAGE,
    'storage_update_orientation': SECTION_STORAGE,
    'storage_delete_placement': SECTION_STORAGE,
    'settings': SECTION_SETTINGS,
    'settings_bambu_test': SECTION_SETTINGS,
    'export_data': SECTION_SETTINGS,
    'import_data': SECTION_SETTINGS,
    'toggle_theme': SECTION_NOTIFICATIONS,
    'toggle_ui_mode': SECTION_OVERVIEW,
    'onboarding_dismiss': SECTION_SETTINGS,
    'filament_import_csv': SECTION_FILAMENTS,
    'filament_community_db': SECTION_FILAMENTS,
    'filament_community_db_import': SECTION_FILAMENTS,
    'filament_export_csv': SECTION_FILAMENTS,
    'maintenance_index': SECTION_PRINTERS,
    'maintenance_add': SECTION_PRINTERS,
    'maintenance_edit': SECTION_PRINTERS,
    'maintenance_delete': SECTION_PRINTERS,
    'maintenance_ics': SECTION_PRINTERS,
    'waste_index': SECTION_FILAMENTS,
    'waste_add': SECTION_FILAMENTS,
    'waste_edit': SECTION_FILAMENTS,
    'waste_delete': SECTION_FILAMENTS,
    'waste_upload_file': SECTION_FILAMENTS,
    'waste_serve_file': SECTION_FILAMENTS,
    'waste_download_file': SECTION_FILAMENTS,
    'waste_delete_file': SECTION_FILAMENTS,
    'users_index': SECTION_USERS,
    'user_detail': SECTION_USERS,
    'account_settings': SECTION_NOTIFICATIONS,
    'notifications_index': SECTION_NOTIFICATIONS,
    'notification_mark_read': SECTION_NOTIFICATIONS,
    'notification_mark_all_read': SECTION_NOTIFICATIONS,
    'notification_delete': SECTION_NOTIFICATIONS,
    'notification_delete_read': SECTION_NOTIFICATIONS,
    'audit_logs': SECTION_USERS,
}


def default_section_permissions():
    return {
        SECTION_OVERVIEW: True,
        SECTION_FILAMENTS: True,
        SECTION_PROJECTS: True,
        SECTION_HISTORY: False,
        SECTION_STORAGE: False,
        SECTION_CALCULATOR: False,
        SECTION_PRINTERS: False,
        SECTION_STATS: False,
        SECTION_SETTINGS: False,
        SECTION_USERS: False,
    }


def admin_section_permissions():
    return {section: True for section in ALL_SECTIONS}


def _normalize_permissions(raw_value, role='user'):
    if role == 'admin':
        return admin_section_permissions()
    permissions = default_section_permissions()
    if not raw_value:
        return permissions
    try:
        payload = json.loads(raw_value) if isinstance(raw_value, str) else dict(raw_value)
    except (TypeError, ValueError, json.JSONDecodeError):
        return permissions
    for section in ALL_SECTIONS:
        if section in payload:
            permissions[section] = bool(payload[section])
    return permissions


def serialize_permissions(mapping, role='user'):
    return json.dumps(_normalize_permissions(mapping, role=role), ensure_ascii=True, sort_keys=True)


def user_permissions(user):
    if not user:
        return {}
    return _normalize_permissions(user.section_permissions, role=user.role)


def get_current_user():
    if hasattr(g, '_current_user'):
        return g._current_user
    user_id = session.get('user_id')
    g._current_user = db.session.get(User, user_id) if user_id else None
    return g._current_user


def is_admin(user=None):
    user = user or get_current_user()
    return bool(user and user.role == 'admin' and user.is_active)


def has_section_access(section, write=False, user=None):
    user = user or get_current_user()
    if not user or not user.is_active:
        return False
    if is_admin(user):
        return True
    if write:
        return False
    return bool(user_permissions(user).get(section, False))


def hash_password(password):
    return generate_password_hash(password, method='scrypt')


def password_needs_rehash(password_hash):
    if not password_hash:
        return True
    return not str(password_hash).startswith('scrypt:')


def verify_password(user, password):
    if not user or not user.password_hash:
        return False
    return check_password_hash(user.password_hash, password)


def is_safe_redirect_target(target):
    if not target:
        return False
    ref_url = urlsplit(request.host_url)
    test_url = urlsplit(urljoin(request.host_url, target))
    return (
        test_url.scheme in {'http', 'https'}
        and ref_url.netloc == test_url.netloc
    )


def safe_redirect_target(target, fallback_endpoint='index'):
    if is_safe_redirect_target(target):
        return target
    return url_for(fallback_endpoint)


def login_user(user, plain_password=None):
    session.clear()
    user.last_login_at = utc_now()
    if plain_password and password_needs_rehash(user.password_hash):
        user.password_hash = hash_password(plain_password)
    db.session.commit()
    session['user_id'] = user.id
    session.permanent = True


def logout_user():
    session.clear()


def require_login(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not get_current_user():
            return redirect(url_for('login', next=request.url))
        return view(*args, **kwargs)
    return wrapped


def require_admin(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not is_admin():
            abort(403)
        return view(*args, **kwargs)
    return wrapped


def ensure_endpoint_access():
    endpoint = request.endpoint or ''
    if '.' in endpoint:
        endpoint = endpoint.split('.')[-1]
    if endpoint in PUBLIC_ENDPOINTS or endpoint.startswith('pwa.'):
        return None
    if request.method == 'OPTIONS':
        return None
    if current_app.config.get('TESTING') and not current_app.config.get('AUTH_REQUIRED_IN_TESTS'):
        return None
    user = get_current_user()
    if not user:
        return redirect(url_for('login', next=request.url))
    if not user.is_active:
        logout_user()
        flash('auth_account_disabled', 'error')
        return redirect(url_for('login'))

    section = SECTION_BY_ENDPOINT.get(endpoint)
    if section == SECTION_NOTIFICATIONS:
        return None
    if not section:
        return None
    if request.method in ('GET', 'HEAD'):
        if not has_section_access(section, write=False, user=user):
            abort(403)
        return None
    if section == SECTION_PROJECTS:
        if not has_section_access(section, write=False, user=user):
            abort(403)
        return None
    if is_admin(user):
        return None
    abort(403)


_AUDIT_REDACT_KEYS = ('password', 'token', 'secret', 'api_key', 'csrf', 'fernet')


def _audit_should_capture(user):
    if not user or not is_admin(user):
        return False
    if request.method not in ('POST', 'PUT', 'PATCH', 'DELETE'):
        return False
    if current_app.config.get('TESTING') and not current_app.config.get('AUTH_REQUIRED_IN_TESTS'):
        return False
    endpoint = request.endpoint or ''
    if '.' in endpoint:
        endpoint = endpoint.split('.')[-1]
    if endpoint in PUBLIC_ENDPOINTS:
        return False
    if endpoint in {'audit_logs'}:
        return False
    # Respect the audit_logging_enabled app setting
    from utils import get_settings
    setting = get_settings()
    if setting and not getattr(setting, 'audit_logging_enabled', True):
        return False
    return True


def _audit_json_dumps(payload):
    if payload is None:
        return None
    return json.dumps(payload, ensure_ascii=True, sort_keys=True, default=str, separators=(',', ':'))


def _audit_safe_value(value):
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _audit_snapshot_model(obj):
    if obj is None:
        return None
    snapshot = {}
    mapper = sa_inspect(obj.__class__)
    for attr in mapper.column_attrs:
        key = attr.key
        value = getattr(obj, key)
        if any(marker in key.lower() for marker in _AUDIT_REDACT_KEYS):
            snapshot[key] = '[redacted]' if value else None
        else:
            snapshot[key] = _audit_safe_value(value)
    return snapshot


def _audit_sanitized_form():
    data = {}
    for key in request.form.keys():
        values = request.form.getlist(key)
        if any(marker in key.lower() for marker in _AUDIT_REDACT_KEYS):
            data[key] = '[redacted]' if len(values) <= 1 else ['[redacted]' for _ in values]
        else:
            data[key] = values[0] if len(values) == 1 else values
    if request.files:
        data['_files'] = sorted(request.files.keys())
    return data


def _audit_client_ip():
    if request.access_route:
        return request.access_route[0]
    return request.remote_addr


def _audit_target():
    endpoint = request.endpoint or ''
    if '.' in endpoint:
        endpoint = endpoint.split('.')[-1]
    view_args = dict(request.view_args or {})

    from models import (
        AppSetting, BambuPrintJob, Filament, MovementHistory, PrintHistory,
        Project, ProjectComment, ProjectFile, ProjectFilament, ProjectLink,
        ProjectQuote, PrusaPrinter, PrusaPrintJob, StoragePlacement,
        StorageShelf, PrinterMaintenance, WasteRecord, WasteFile,
    )

    explicit = {
        'user_detail': (User, 'user_id'),
        'filament_detail': (Filament, 'id'),
        'filament_update_meta': (Filament, 'id'),
        'filament_toggle_reorder_snooze': (Filament, 'id'),
        'edit': (Filament, 'id'),
        'use_filament': (Filament, 'id'),
        'add_spool': (Filament, 'id'),
        'remove_spool': (Filament, 'id'),
        'delete': (Filament, 'id'),
        'project_detail': (Project, 'id'),
        'project_edit': (Project, 'id'),
        'project_delete': (Project, 'id'),
        'project_upload_file': (Project, 'id'),
        'project_add_link': (Project, 'id'),
        'project_delete_link': (ProjectLink, 'link_id'),
        'project_refresh_link': (ProjectLink, 'link_id'),
        'project_add_filament': (Project, 'id'),
        'project_remove_filament': (ProjectFilament, 'pf_id'),
        'project_update_filament': (ProjectFilament, 'pf_id'),
        'project_status': (Project, 'id'),
        'project_consume_filament': (ProjectFilament, 'pf_id'),
        'project_delete_file': (ProjectFile, 'file_id'),
        'project_add_comment': (Project, 'id'),
        'project_update_comment': (ProjectComment, 'comment_id'),
        'project_delete_comment': (ProjectComment, 'comment_id'),
        'project_toggle_comment_checkbox': (ProjectComment, 'comment_id'),
        'project_toggle_description_checkbox': (Project, 'id'),
        'project_add_todo': (Project, 'id'),
        'project_toggle_todo': (Project, 'id'),
        'project_delete_todo': (Project, 'id'),
        'project_edit_todo': (Project, 'id'),
        'delete_quote': (ProjectQuote, 'id'),
        'export_quote': (ProjectQuote, 'id'),
        'bambu_job_map': (BambuPrintJob, 'job_id'),
        'bambu_job_deduct_slot': (BambuPrintJob, 'job_id'),
        'bambu_job_remap_slot': (BambuPrintJob, 'job_id'),
        'bambu_job_delete': (BambuPrintJob, 'job_id'),
        'prusa_printer_sync': (PrusaPrinter, 'printer_id'),
        'prusa_printer_test': (PrusaPrinter, 'printer_id'),
        'prusa_job_map': (PrusaPrintJob, 'job_id'),
        'prusa_job_delete': (PrusaPrintJob, 'job_id'),
        'storage_update_shelf': (StorageShelf, 'shelf_id'),
        'storage_delete_shelf': (StorageShelf, 'shelf_id'),
        'storage_move_placement': (StoragePlacement, 'placement_id'),
        'storage_update_orientation': (StoragePlacement, 'placement_id'),
        'storage_delete_placement': (StoragePlacement, 'placement_id'),
        'maintenance_edit': (PrinterMaintenance, 'rec_id'),
        'maintenance_delete': (PrinterMaintenance, 'rec_id'),
        'waste_edit': (WasteRecord, 'rec_id'),
        'waste_delete': (WasteRecord, 'rec_id'),
        'waste_upload_file': (WasteRecord, 'rec_id'),
        'waste_delete_file': (WasteFile, 'file_id'),
        'notification_mark_read': (Notification, 'id'),
        'notification_delete': (Notification, 'id'),
    }
    model_pair = explicit.get(endpoint)
    if model_pair:
        model, arg_name = model_pair
        object_id = view_args.get(arg_name)
        return {
            'object_type': model.__name__,
            'object_id': str(object_id) if object_id is not None else None,
            'object': db.session.get(model, object_id) if object_id is not None else None,
        }
    if endpoint in {'settings', 'toggle_theme', 'import_data', 'export_data'}:
        setting = AppSetting.query.first()
        return {'object_type': 'AppSetting', 'object_id': str(setting.id) if setting else None, 'object': setting}
    if endpoint == 'history' or endpoint == 'clear_history':
        return {'object_type': 'MovementHistory', 'object_id': None, 'object': None}
    if endpoint == 'inventory_bulk':
        selected_ids = request.form.getlist('selected_ids')
        return {'object_type': 'Filament', 'object_id': ','.join(selected_ids), 'object': None}
    if endpoint == 'users_index':
        return {'object_type': 'UserInvite', 'object_id': None, 'object': None}
    if endpoint == 'storage_add_shelf':
        return {'object_type': 'StorageShelf', 'object_id': None, 'object': None}
    if endpoint == 'storage_assign_slot':
        return {'object_type': 'StoragePlacement', 'object_id': None, 'object': None}
    if endpoint in {'bambu_sync', 'bambu_refetch_thumbnails', 'prusa_jobs'}:
        return {'object_type': endpoint, 'object_id': None, 'object': None}
    return {'object_type': endpoint or None, 'object_id': None, 'object': None}


def _audit_prepare_request():
    user = get_current_user()
    if not _audit_should_capture(user):
        return
    if '_audit_sid' not in session:
        session['_audit_sid'] = secrets.token_hex(12)
    target = _audit_target()
    endpoint = request.endpoint or ''
    if '.' in endpoint:
        endpoint = endpoint.split('.')[-1]
    g.audit_context = {
        'user_id': user.id,
        'user_email': user.email,
        'user_name': user.name,
        'session_id': session.get('_audit_sid'),
        'ip_address': _audit_client_ip(),
        'user_agent': (request.headers.get('User-Agent') or '')[:255] or None,
        'method': request.method,
        'endpoint': endpoint,
        'path': request.full_path.rstrip('?'),
        'action': request.form.get('action') or endpoint or request.method.lower(),
        'object_type': target.get('object_type'),
        'object_id': target.get('object_id'),
        'before': {
            'object': _audit_snapshot_model(target.get('object')),
            'route_args': {key: _audit_safe_value(value) for key, value in (request.view_args or {}).items()},
        },
        'form': _audit_sanitized_form(),
    }


def _audit_finish_request(response):
    ctx = getattr(g, 'audit_context', None)
    if not ctx or response.status_code >= 400:
        return response
    target = _audit_target()
    after_payload = {
        'object': _audit_snapshot_model(target.get('object')),
        'form': ctx.get('form') or {},
    }
    if target.get('object_id') and not ctx.get('object_id'):
        ctx['object_id'] = target.get('object_id')
    try:
        row = AuditLog(
            user_id=ctx.get('user_id'),
            user_email=ctx.get('user_email'),
            user_name=ctx.get('user_name'),
            session_id=ctx.get('session_id'),
            ip_address=ctx.get('ip_address'),
            user_agent=ctx.get('user_agent'),
            method=ctx.get('method') or request.method,
            endpoint=ctx.get('endpoint'),
            path=ctx.get('path') or request.path,
            action=ctx.get('action') or request.endpoint or request.method.lower(),
            object_type=ctx.get('object_type'),
            object_id=ctx.get('object_id'),
            before_data=_audit_json_dumps(ctx.get('before')),
            after_data=_audit_json_dumps(after_payload),
        )
        db.session.add(row)
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        current_app.logger.warning('Audit log write failed: %s', exc)
    return response


def init_app(app):
    @app.before_request
    def _load_auth():
        result = ensure_endpoint_access()
        if result is not None:
            return result
        _audit_prepare_request()
        return None

    @app.after_request
    def _write_audit(response):
        return _audit_finish_request(response)


def create_notification(user, title, body=None, link=None, kind='info'):
    if not user:
        return None
    row = Notification(user_id=user.id, title=title, body=body, link=link, kind=kind)
    db.session.add(row)
    return row


def unread_notifications_count(user=None):
    user = user or get_current_user()
    if not user:
        return 0
    return Notification.query.filter_by(user_id=user.id, is_read=False).count()


def recent_notifications(user=None, limit=8):
    user = user or get_current_user()
    if not user:
        return []
    return (
        Notification.query
        .filter_by(user_id=user.id)
        .order_by(Notification.created_at.desc())
        .limit(limit)
        .all()
    )


def create_invite(email=None, role='user', permissions=None, expires_days=14):
    code = secrets.token_urlsafe(12)
    invite = UserInvite(
        email=(email or '').strip().lower() or None,
        code=code,
        role='admin' if role == 'admin' else 'user',
        section_permissions=serialize_permissions(permissions or default_section_permissions(), role=role),
        expires_at=utc_now() + timedelta(days=expires_days),
    )
    db.session.add(invite)
    return invite


def invite_is_valid(invite):
    if not invite or invite.is_used:
        return False
    if invite.expires_at and invite.expires_at < utc_now():
        return False
    return True
