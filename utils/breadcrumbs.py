"""Build safe, translated breadcrumbs for the shared application shell."""

from flask import url_for

from database import db
from models import Filament, Project, ProjectFile, User


# Short endpoint names are used because Flask request.endpoint includes the
# blueprint prefix while legacy templates and auth mappings use the short name.
_BREADCRUMB_DEFS = {
    'index': [('overview', None)],
    'filaments_index': [('filaments_nav', 'inventory.filaments_index')],
    'filament_detail': [('filaments_nav', 'inventory.filaments_index'), ('__name__', None)],
    'add': [('filaments_nav', 'inventory.filaments_index'), ('add_new_title', None)],
    'edit': [('filaments_nav', 'inventory.filaments_index'), ('__name__', None)],
    'filament_import_csv': [('filaments_nav', 'inventory.filaments_index'), ('import_csv_title', None)],
    'filament_community_db': [('filaments_nav', 'inventory.filaments_index'), ('community_db_title', None)],
    'storage': [('storage_nav', 'storage.storage')],
    'models_index': [('models_nav', 'models.models_index')],
    'model_detail': [('models_nav', 'models.models_index'), ('__name__', None)],
    'model_edit': [('models_nav', 'models.models_index'), ('__name__', None)],
    'maintenance_index': [('maintenance_title', 'maintenance.maintenance_index')],
    'waste_index': [('waste_title', 'waste.waste_index')],
    'users_index': [('users_nav', 'auth.users_index')],
    'user_detail': [('users_nav', 'auth.users_index'), ('__name__', None)],
    'account_settings': [('auth_account', 'auth.account_settings')],
    'notifications_index': [('notifications_nav', 'auth.notifications_index')],
    'calculator': [('calculator', 'calculator.calculator')],
    'calculator_project': [('calculator', 'calculator.calculator'), ('__name__', None)],
    'bambu_jobs': [('bambu_jobs', 'bambu.bambu_jobs')],
    'prusa_jobs': [('prusa_jobs', 'prusa.prusa_jobs')],
    'projects_index': [('projects', 'projects.projects_index')],
    'project_create': [('projects', 'projects.projects_index'), ('project_create', None)],
    'project_edit': [('projects', 'projects.projects_index'), ('__name__', None)],
    'project_detail': [('projects', 'projects.projects_index'), ('__name__', None)],
    'project_templates_index': [('projects', 'projects.projects_index'), ('project_templates_title', None)],
    'history': [('movement_history', 'history.history')],
    'stats': [('stats_nav', 'stats.stats')],
    'settings': [('settings', 'settings.settings')],
    'audit_logs': [('audit_nav', 'auth.audit_logs')],
}

_NAME_RESOLVERS = {
    'filament_detail': (Filament, 'id', 'name'),
    'edit': (Filament, 'id', 'name'),
    'project_detail': (Project, 'id', 'name'),
    'project_edit': (Project, 'id', 'name'),
    'calculator_project': (Project, 'project_id', 'name'),
    'model_detail': (ProjectFile, 'root_id', 'display_name'),
    'model_edit': (ProjectFile, 'root_id', 'display_name'),
    'user_detail': (User, 'user_id', 'name'),
}

_PUBLIC_ENDPOINTS = {
    'login', 'register_account', 'activate_invite', 'logout',
    'project_share', 'project_share_download_file', 'project_share_view_file',
    'project_share_image_file', 'model_public_share', 'model_public_share_file',
    'model_public_share_download', 'manifest', 'service_worker',
}


def _safe_url(endpoint):
    if not endpoint:
        return None
    try:
        return url_for(endpoint)
    except Exception:
        return None


def build_breadcrumbs(t, endpoint, view_args=None):
    """Return translated breadcrumb dictionaries for the current page.

    Entity names are looked up only for an explicit allowlist of detail
    endpoints. Missing records and endpoints gracefully fall back to the old
    generic admin-tools label. Values remain plain strings so Jinja autoescape
    is the only output encoding layer.
    """
    endpoint = (endpoint or '').split('.')[-1]
    view_args = view_args or {}

    if endpoint in _PUBLIC_ENDPOINTS:
        return [{'label': t('title'), 'url': None}]

    definitions = _BREADCRUMB_DEFS.get(endpoint)
    if definitions is None:
        return [
            {'label': t('title'), 'url': _safe_url('inventory.index')},
            {'label': t('nav_admin_tools'), 'url': None},
        ]

    entity_name = None
    resolver = _NAME_RESOLVERS.get(endpoint)
    if resolver:
        model, arg_name, attr_name = resolver
        entity_id = view_args.get(arg_name)
        if entity_id is not None:
            try:
                entity = db.session.get(model, entity_id)
                if entity:
                    entity_name = getattr(entity, attr_name, None) or getattr(entity, 'filename', None)
            except Exception:
                entity_name = None

    breadcrumbs = [{'label': t('title'), 'url': _safe_url('inventory.index')}]
    for label_key, target_endpoint in definitions:
        if label_key == '__name__':
            label = entity_name or t('nav_admin_tools')
        else:
            label = t(label_key)
        breadcrumbs.append({'label': label, 'url': _safe_url(target_endpoint) if target_endpoint else None})
    return breadcrumbs
