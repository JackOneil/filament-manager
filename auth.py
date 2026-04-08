import json
import secrets
from datetime import datetime, timedelta
from functools import wraps
from urllib.parse import urljoin, urlsplit

from flask import abort, current_app, flash, g, redirect, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from database import db
from models import Notification, User, UserInvite

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
    'sw',
    'static',
}

SECTION_BY_ENDPOINT = {
    'index': SECTION_OVERVIEW,
    'filaments_index': SECTION_FILAMENTS,
    'filament_detail': SECTION_FILAMENTS,
    'api_filaments_list': SECTION_FILAMENTS,
    'add': SECTION_FILAMENTS,
    'edit': SECTION_FILAMENTS,
    'use_filament': SECTION_FILAMENTS,
    'add_spool': SECTION_FILAMENTS,
    'remove_spool': SECTION_FILAMENTS,
    'delete': SECTION_FILAMENTS,
    'inventory_bulk': SECTION_FILAMENTS,
    'filament_update_meta': SECTION_FILAMENTS,
    'filament_toggle_reorder_snooze': SECTION_FILAMENTS,
    'calculator': SECTION_CALCULATOR,
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
    'project_consume_filament': SECTION_PROJECTS,
    'project_add_comment': SECTION_PROJECTS,
    'project_update_comment': SECTION_PROJECTS,
    'project_add_todo': SECTION_PROJECTS,
    'project_toggle_todo': SECTION_PROJECTS,
    'project_delete_todo': SECTION_PROJECTS,
    'bambu_jobs': SECTION_PRINTERS,
    'bambu_sync': SECTION_PRINTERS,
    'bambu_job_map': SECTION_PRINTERS,
    'bambu_job_deduct_slot': SECTION_PRINTERS,
    'bambu_job_delete': SECTION_PRINTERS,
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
    'storage_update_orientation': SECTION_STORAGE,
    'storage_delete_placement': SECTION_STORAGE,
    'settings': SECTION_SETTINGS,
    'export_data': SECTION_SETTINGS,
    'import_data': SECTION_SETTINGS,
    'toggle_theme': SECTION_NOTIFICATIONS,
    'users_index': SECTION_USERS,
    'user_detail': SECTION_USERS,
    'account_settings': SECTION_NOTIFICATIONS,
    'notifications_index': SECTION_NOTIFICATIONS,
    'notification_mark_read': SECTION_NOTIFICATIONS,
    'notification_mark_all_read': SECTION_NOTIFICATIONS,
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
    user.last_login_at = datetime.utcnow()
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


def init_app(app):
    @app.before_request
    def _load_auth():
        return ensure_endpoint_access()


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
        expires_at=datetime.utcnow() + timedelta(days=expires_days),
    )
    db.session.add(invite)
    return invite


def invite_is_valid(invite):
    if not invite or invite.is_used:
        return False
    if invite.expires_at and invite.expires_at < datetime.utcnow():
        return False
    return True
