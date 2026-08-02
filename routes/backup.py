"""Full database export and import endpoints for backups."""
import base64
import gzip
import io
import json
import os
import tarfile
import uuid
from datetime import datetime, date
from flask import abort, current_app as app, request, redirect, url_for, Response, Blueprint, flash
from werkzeug.utils import secure_filename

from database import db
from models import (
    Brand, Color, Material, AppSetting, Filament, MovementHistory,
    PrintHistory, Project, ProjectFile, ProjectLink, ProjectFilament, ProjectQuote,
    BambuPrinter, BambuPrintJob, BambuJobMaterial, StoragePlacement, StorageShelf,
    PrusaPrinter, PrusaPrintJob, ProjectComment, ProjectCommentReaction,
    ProjectTodo, ProjectPrintItem, User, UserInvite, UserSession,
    Notification, AuditLog, ModelComment, ModelCategory,
    PrinterMaintenance, WasteRecord, WasteFile, FilamentUndoLog, ProjectTemplate,
)
from utils import encrypt_token, format_tags, safe_commit, utc_now, translate, validate_printer_host


from routes.backup_helpers import (
    _filament_ref,
    _resolve_filament_ref,
    _project_file_payload,
    _build_import_file_path,
    _load_backup_package,
    _user_ref,
    _resolve_user_ref,
    _build_export_data,
    _build_backup_archive_bytes,
    _build_backup_archive_from_data,
    _cleanup_old_backups,
)


# ── Module-level path helpers (3.7 — backup path safety) ────────────────
# ``os.path.abspath`` only resolves ``..`` syntactically — symlinks inside
# the data directory could still allow escape.  We therefore canonicalise
# both the target and the storage directory with ``realpath`` and verify
# containment.  The check is cheap (two stat calls) and only runs on the
# small number of operations that touch the on-disk archive.

_BACKUP_STORAGE_DIRNAME = 'backup'


def _backup_storage_dir() -> str:
    """Return the absolute, realpath of the on-disk backup directory.

    The directory is created on demand so the very first backup works
    without manual ``mkdir``.  The returned path contains no symlinks.
    Tests can redirect the location via ``app.config['BACKUP_DIR']`` so
    the suite never touches the production ``data/backup`` directory.
    """
    try:
        from flask import current_app
        configured = current_app.config.get('BACKUP_DIR')
    except Exception:
        configured = None
    if configured:
        base = str(configured)
    else:
        base = os.path.abspath(os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'data',
            _BACKUP_STORAGE_DIRNAME,
        ))
    os.makedirs(base, exist_ok=True)
    return os.path.realpath(base)


def _is_path_inside(path: str, directory: str) -> bool:
    """Return True iff *path* (after symlink resolution) lies inside *directory*."""
    try:
        path_real = os.path.realpath(path)
        dir_real = os.path.realpath(directory)
    except (OSError, ValueError):
        return False
    # Use os.sep to avoid the ``/backup-evil`` prefix-matching pitfall.
    return path_real == dir_real or path_real.startswith(dir_real + os.sep)

def register(app):
    bp = Blueprint('backup', __name__)

    @bp.route('/export')
    def export_data():
        include_files = request.args.get('include_files', '1') != '0'
        data, setting = _build_export_data(app, include_files=include_files)

        if setting:
            setting.backup_last_export_at = utc_now()
            setting.backup_last_export_meta = json.dumps(data['backup_meta'], ensure_ascii=False)
            safe_commit()

        # Build the archive from the data we already walked — a second
        # _build_export_data() pass would double every DB query on export.
        archive_bytes = _build_backup_archive_from_data(data, include_files=include_files)
        response = Response(archive_bytes, mimetype='application/gzip')
        suffix = 'filament_backup.tar.gz' if include_files else 'filament_backup_db_only.tar.gz'
        response.headers['Content-Disposition'] = f'attachment; filename={suffix}'
        return response

    @bp.route('/backup/trigger-now', methods=['POST'])
    def backup_trigger_now():
        """Manually trigger an automatic-style backup to disk."""
        setting = AppSetting.query.first()
        if not setting:
            flash(translate('backup_auto_no_settings'), 'error')
            return redirect(url_for('settings') + '?tab=data')

        try:
            include_files = bool(setting.backup_auto_include_files)
            # Build export data and archive in a single pass (refactor 5.5:
            # avoid the previous pattern of calling _build_export_data twice).
            data, _ = _build_export_data(app, include_files=include_files)
            archive_bytes = _build_backup_archive_from_data(data, include_files=include_files)
            backup_dir = _backup_storage_dir()
            os.makedirs(backup_dir, exist_ok=True)

            now = utc_now()
            ts = now.strftime('%Y%m%d_%H%M%S')
            suffix = 'full' if include_files else 'db'
            filename = f'auto_backup_{suffix}_{ts}.tar.gz'
            filepath = os.path.join(backup_dir, filename)
            if not _is_path_inside(filepath, backup_dir):
                # Belt-and-suspenders: should never trigger for hard-coded names.
                app.logger.error('Computed backup path escaped storage dir: %r', filepath)
                flash(translate('backup_auto_failed'), 'error')
                return redirect(url_for('settings') + '?tab=data')
            with open(filepath, 'wb') as fh:
                fh.write(archive_bytes)

            setting.backup_auto_last_run_at = now
            setting.backup_last_export_at = now
            setting.backup_last_export_meta = json.dumps(data['backup_meta'], ensure_ascii=False)
            safe_commit()

            # Clean up old backups according to retention settings
            keep_count = getattr(setting, 'backup_auto_keep_count', None)
            keep_count = 10 if keep_count is None else keep_count
            keep_days = getattr(setting, 'backup_auto_keep_days', None)
            keep_days = 0 if keep_days is None else keep_days
            removed = _cleanup_old_backups(backup_dir, keep_count=keep_count, keep_days=keep_days)
            if removed:
                app.logger.info(f"Cleaned up {removed} old backup(s) (keep_count={keep_count}, keep_days={keep_days})")

            app.logger.info(f"Manual auto-backup triggered: {filename} ({len(archive_bytes)} bytes)")
            flash(translate('backup_auto_triggered').format(filename=filename), 'success')
        except Exception:
            db.session.rollback()
            app.logger.exception("Manual auto-backup failed")
            flash(translate('backup_auto_failed'), 'error')
        return redirect(url_for('settings') + '?tab=data')

    @bp.route('/backup/list-files')
    def backup_list_files():
        """Return JSON list of existing auto-backup files."""
        backup_dir = _backup_storage_dir()
        files = []
        if os.path.isdir(backup_dir):
            for name in sorted(os.listdir(backup_dir), reverse=True):
                fpath = os.path.join(backup_dir, name)
                if os.path.isfile(fpath) and name.endswith('.tar.gz'):
                    stat = os.stat(fpath)
                    # Defensive realpath check — should always be inside backup_dir,
                    # but we re-verify to be safe against any future symlink additions.
                    if not _is_path_inside(fpath, backup_dir):
                        continue
                    files.append({
                        'filename': name,
                        'size_bytes': stat.st_size,
                        'modified_at_ts': int(stat.st_mtime),
                    })
        from flask import jsonify
        return jsonify({'files': files})

    @bp.route('/backup/download/<filename>')
    def backup_download_file(filename):
        """Download a specific auto-backup file."""
        from werkzeug.utils import secure_filename
        safe_name = secure_filename(filename)
        if not safe_name or not safe_name.endswith('.tar.gz'):
            abort(400)
        backup_dir = _backup_storage_dir()
        filepath = os.path.join(backup_dir, safe_name)
        # Defence-in-depth: realpath must remain inside the backup directory.
        if not _is_path_inside(filepath, backup_dir):
            app.logger.warning('Backup download path traversal attempt: %r', filename)
            abort(400)
        if not os.path.isfile(filepath):
            abort(404)
        from flask import send_file
        return send_file(filepath, mimetype='application/gzip', as_attachment=True,
                         download_name=safe_name)

    @bp.route('/backup/delete/<filename>', methods=['POST'])
    def backup_delete_file(filename):
        """Delete a specific auto-backup file."""
        from werkzeug.utils import secure_filename
        safe_name = secure_filename(filename)
        if not safe_name or not safe_name.endswith('.tar.gz'):
            abort(400)
        backup_dir = _backup_storage_dir()
        filepath = os.path.join(backup_dir, safe_name)
        if not _is_path_inside(filepath, backup_dir):
            app.logger.warning('Backup delete path traversal attempt: %r', filename)
            flash(translate('backup_auto_file_invalid'), 'error')
            return redirect(url_for('settings') + '?tab=data')
        if os.path.isfile(filepath):
            os.remove(filepath)
            app.logger.info(f"Deleted backup file: {safe_name}")
            flash(translate('backup_auto_file_deleted').format(filename=safe_name), 'success')
        return redirect(url_for('settings') + '?tab=data')

    @bp.route('/import', methods=['POST'])
    def import_data():
        from datetime import datetime, date
        file = request.files.get('file')
        if not file or file.filename == '':
            return redirect(url_for('settings'))

        dry_run = request.form.get('dry_run') == 'on'
        conflict_mode = (request.form.get('conflict_mode') or 'merge').strip().lower()
        if conflict_mode not in {'skip', 'overwrite', 'merge'}:
            conflict_mode = 'merge'
        overwrite_mode = conflict_mode == 'overwrite'
        skip_mode = conflict_mode == 'skip'

        imported_filaments = 0
        upload_folder = app.config.get('PROJECT_UPLOAD_FOLDER')
        os.makedirs(upload_folder, exist_ok=True)
        try:
            data, backup_files = _load_backup_package(file)
            if not isinstance(data, dict):
                flash(translate('backup_import_incompatible'), 'error')
                return redirect(url_for('settings') + '?tab=data')

            meta = data.get('backup_meta', {}) or {}
            format_version = meta.get('format_version', 1)
            if isinstance(format_version, int) and format_version > 2:
                flash(translate('backup_import_incompatible'), 'error')
                return redirect(url_for('settings') + '?tab=data')

            if dry_run:
                total = len(data.get('filaments', [])) + len(data.get('projects', [])) + len(data.get('users', []))
                # Structural validation — dry-run must actually detect
                # incomplete/incompatible backups, not just count rows.
                problems = []
                for section in ('filaments', 'projects', 'users', 'brands', 'colors', 'materials'):
                    value = data.get(section, [])
                    if not isinstance(value, list):
                        problems.append(section)
                for filament in data.get('filaments', []):
                    if not isinstance(filament, dict) or not filament.get('name'):
                        problems.append('filament-row')
                        break
                for project in data.get('projects', []):
                    if not isinstance(project, dict) or not project.get('name'):
                        problems.append('project-row')
                        break
                if problems:
                    flash(translate('backup_dry_run_invalid').format(detail=', '.join(sorted(set(problems)))), 'error')
                    return redirect(url_for('settings') + '?tab=data')
                flash(translate('backup_dry_run_ok').format(total=total), 'success')
                return redirect(url_for('settings') + '?tab=data')

            # `db.session.begin()` requires a fresh transaction. Requests that
            # only read (typical GETs) leave an open read transaction on the
            # thread's session — end it first so the import never fails with
            # "A transaction is already begun on this Session".
            db.session.rollback()

            with db.session.begin():
                # ── 1. Enumerations ────────────────────────────────────
                for b_data in data.get('brands', []):
                    b_name = b_data if isinstance(b_data, str) else b_data.get('name', '')
                    if not b_name:
                        continue
                    existing = Brand.query.filter_by(name=b_name).first()
                    if not existing:
                        db.session.add(Brand(name=b_name, shop_url=b_data.get('shop_url') if isinstance(b_data, dict) else None))
                    elif overwrite_mode and isinstance(b_data, dict):
                        existing.shop_url = b_data['shop_url']
                    elif conflict_mode == 'merge' and isinstance(b_data, dict) and b_data.get('shop_url') and not existing.shop_url:
                        existing.shop_url = b_data['shop_url']

                for m_name in data.get('materials', []):
                    if not Material.query.filter_by(name=m_name).first():
                        db.session.add(Material(name=m_name))

                for c in data.get('colors', []):
                    existing_color = Color.query.filter_by(name=c.get('name')).first()
                    if not existing_color:
                        db.session.add(Color(name=c.get('name'), hex_value=c.get('hex_value', '')))
                    elif overwrite_mode:
                        existing_color.hex_value = c.get('hex_value', existing_color.hex_value)
                    elif conflict_mode == 'merge' and not existing_color.hex_value:
                        existing_color.hex_value = c.get('hex_value', existing_color.hex_value)

                db.session.flush()

                # ── 2. App settings ────────────────────────────────────
                s = data.get('app_settings', {})
                if s and not skip_mode:
                    setting = AppSetting.query.first()
                    if not setting:
                        # A fresh database has no settings row — create one so
                        # a restore actually restores the configuration instead
                        # of silently dropping it.
                        setting = AppSetting()
                        db.session.add(setting)
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
                        setting.bambu_last_test_at = datetime.fromisoformat(s['bambu_last_test_at']) if s.get('bambu_last_test_at') else setting.bambu_last_test_at
                        setting.bambu_last_test_status = s.get('bambu_last_test_status', setting.bambu_last_test_status)
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
                        setting.backup_last_export_at = datetime.fromisoformat(s['backup_last_export_at']) if s.get('backup_last_export_at') else setting.backup_last_export_at
                        setting.backup_last_export_meta = s.get('backup_last_export_meta', setting.backup_last_export_meta)
                        if 'audit_logging_enabled' in s:
                            setting.audit_logging_enabled = s['audit_logging_enabled']
                        if 'auto_filament_mapping_enabled' in s:
                            setting.auto_filament_mapping_enabled = s['auto_filament_mapping_enabled']
                        if 'backup_auto_enabled' in s:
                            setting.backup_auto_enabled = s['backup_auto_enabled']
                        if 'backup_auto_frequency' in s:
                            setting.backup_auto_frequency = s.get('backup_auto_frequency', 'weekly')
                        if 'backup_auto_time' in s:
                            setting.backup_auto_time = s.get('backup_auto_time', '03:00')
                        if 'backup_auto_day' in s:
                            setting.backup_auto_day = s.get('backup_auto_day', 1)
                        if 'backup_auto_include_files' in s:
                            setting.backup_auto_include_files = s['backup_auto_include_files']
                        if 'backup_auto_last_run_at' in s:
                            setting.backup_auto_last_run_at = datetime.fromisoformat(s['backup_auto_last_run_at']) if s.get('backup_auto_last_run_at') else setting.backup_auto_last_run_at
                        if 'backup_auto_keep_count' in s:
                            setting.backup_auto_keep_count = s.get('backup_auto_keep_count', 10)
                        if 'backup_auto_keep_days' in s:
                            setting.backup_auto_keep_days = s.get('backup_auto_keep_days', 0)
                        if 'waste_reasons_json' in s:
                            setting.waste_reasons_json = s.get('waste_reasons_json', '')
                        if 'link_preview_reader_enabled' in s:
                            setting.link_preview_reader_enabled = s['link_preview_reader_enabled']

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
                            preferred_language=user_data.get('preferred_language'),
                            preferred_theme=user_data.get('preferred_theme'),
                            last_login_at=datetime.fromisoformat(user_data['last_login_at']) if user_data.get('last_login_at') else None,
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
                        elif overwrite_mode:
                            exists.weight_total = f.get('weight_total', exists.weight_total)
                            exists.weight_remaining = f.get('weight_remaining', exists.weight_remaining)
                            exists.price = f.get('price', exists.price)
                            exists.quantity = f.get('quantity', exists.quantity)
                            exists.min_stock_grams = f.get('min_stock_grams', exists.min_stock_grams)
                            exists.max_stock_grams = f.get('max_stock_grams', exists.max_stock_grams)
                            exists.tag_text = format_tags(f.get('tag_text', exists.tag_text or ''))
                            exists.quality_stringing = f.get('quality_stringing', exists.quality_stringing)
                            exists.quality_adhesion = f.get('quality_adhesion', exists.quality_adhesion)
                            exists.quality_drying = f.get('quality_drying', exists.quality_drying)
                            exists.quality_profile = f.get('quality_profile', exists.quality_profile)
                            exists.quality_notes = f.get('quality_notes', exists.quality_notes)
                            exists.recommended_nozzle_temp = f.get('recommended_nozzle_temp', exists.recommended_nozzle_temp)
                            exists.recommended_bed_temp = f.get('recommended_bed_temp', exists.recommended_bed_temp)
                            exists.reorder_alert_snoozed = f.get('reorder_alert_snoozed', exists.reorder_alert_snoozed)
                            exists.shop_url = f.get('shop_url', exists.shop_url)

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
                            client_email=proj_data.get('client_email'),
                            client_phone=proj_data.get('client_phone'),
                            priority=proj_data.get('priority', 'medium'),
                            share_token=proj_data.get('share_token'),
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
                        if proj_data.get('client_email'):
                            proj.client_email = proj_data.get('client_email')
                        if proj_data.get('client_phone'):
                            proj.client_phone = proj_data.get('client_phone')
                        if proj_data.get('priority'):
                            proj.priority = proj_data.get('priority', 'medium')
                        if 'owner_name' in proj_data:
                            proj.owner_name = (proj_data.get('owner_name') or '').strip() or None

                    imported_files_map = {}
                    files_to_resolve = []

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
                            
                            uploaded_by_id = None
                            user_ref = file_data.get('uploaded_by')
                            if user_ref:
                                resolved_user = _resolve_user_ref(user_ref)
                                if resolved_user:
                                    uploaded_by_id = resolved_user.id

                            # Resolve category by name
                            resolved_category_id = None
                            cat_name = file_data.get('category_name')
                            if cat_name:
                                cat = ModelCategory.query.filter_by(name=cat_name).first()
                                if cat:
                                    resolved_category_id = cat.id

                            new_file = ProjectFile(
                                project_id=proj.id,
                                filename=file_data.get('filename', ''),
                                filepath=filepath,
                                uploaded_at=uploaded_at,
                                version=file_data.get('version', 1),
                                display_name=file_data.get('display_name'),
                                file_size_bytes=file_data.get('file_size_bytes'),
                                mime_type=file_data.get('mime_type'),
                                checksum_sha256=file_data.get('checksum_sha256'),
                                thumbnail_path=file_data.get('thumbnail_path'),
                                version_note=file_data.get('version_note'),
                                model_note=file_data.get('model_note'),
                                uploaded_by_user_id=uploaded_by_id,
                                share_token=file_data.get('share_token'),
                                category_id=resolved_category_id,
                            )
                            db.session.add(new_file)
                            imported_files_map[(proj.id, file_data.get('filename', ''), file_data.get('version', 1))] = new_file
                            if file_data.get('parent_file_id') is not None or file_data.get('version', 1) > 1:
                                files_to_resolve.append((new_file, file_data.get('filename', ''), file_data.get('version', 1)))

                    db.session.flush()

                    for new_file, filename, version in files_to_resolve:
                        root_file = imported_files_map.get((proj.id, filename, 1))
                        if root_file:
                            new_file.parent_file_id = root_file.id
                        else:
                            db_root = ProjectFile.query.filter_by(project_id=proj.id, filename=filename, version=1).first()
                            if db_root:
                                new_file.parent_file_id = db_root.id


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
                                due_date=date.fromisoformat(todo_data['due_date']) if todo_data.get('due_date') else None,
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

                # ── 5b. Project templates ──────────────────────────────
                for tpl_data in data.get('project_templates', []):
                    if not ProjectTemplate.query.filter_by(name=tpl_data.get('name')).first():
                        db.session.add(ProjectTemplate(
                            name=tpl_data.get('name', ''),
                            description=tpl_data.get('description'),
                            estimated_print_time=tpl_data.get('estimated_print_time', 0),
                            tag_text=tpl_data.get('tag_text'),
                            created_by_user_id=_resolve_user_ref(tpl_data.get('created_by')).id if _resolve_user_ref(tpl_data.get('created_by')) else None,
                            created_at=datetime.fromisoformat(tpl_data['created_at']) if tpl_data.get('created_at') else utc_now(),
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
                        raw_payload=j.get('raw_payload'),
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
                        # Re-validate the host (SSRF hardening): a crafted
                        # backup must not be able to point the 60s poller at
                        # internal addresses.
                        valid_host = validate_printer_host(pp.get('host', ''))
                        if not valid_host:
                            app.logger.warning(
                                "Skipping Prusa printer import: host failed SSRF validation (%s)",
                                pp.get('host'),
                            )
                            continue
                        restored_printer = PrusaPrinter(
                            name=pp.get('name', ''),
                            host=valid_host,
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
                        raw_payload=j.get('raw_payload'),
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
                    # Resolve printer_id by (type, name) — printer IDs are
                    # re-assigned on restore, so the raw ID would silently
                    # point at an unrelated printer.
                    printer_id = m_data.get('printer_id')
                    printer_type = m_data.get('printer_type', 'bambu')
                    printer_name = m_data.get('printer_name', '')
                    if printer_id:
                        if printer_type == 'bambu':
                            resolved = BambuPrinter.query.filter_by(name=printer_name).first()
                        else:
                            resolved = PrusaPrinter.query.filter_by(name=printer_name).first()
                        printer_id = resolved.id if resolved else None
                    db.session.add(PrinterMaintenance(
                        printer_type=printer_type,
                        printer_id=printer_id,
                        printer_name=printer_name,
                        maintenance_type=m_data.get('maintenance_type', 'other'),
                        notes=m_data.get('notes'),
                        notes_is_markdown=bool(m_data.get('notes_is_markdown', False)),
                        performed_at=performed_at,
                        next_service_at=datetime.fromisoformat(m_data['next_service_at']) if m_data.get('next_service_at') else None,
                        recurrence_type=m_data.get('recurrence_type', 'none'),
                        recurrence_value=m_data.get('recurrence_value', 0),
                        recurrence_enabled=m_data.get('recurrence_enabled', False),
                        fault_resolved=bool(m_data.get('fault_resolved', False)),
                        fault_resolved_at=datetime.fromisoformat(m_data['fault_resolved_at']) if m_data.get('fault_resolved_at') else None,
                        predictive_enabled=bool(m_data.get('predictive_enabled', False)),
                        predictive_runtime_hours=m_data.get('predictive_runtime_hours', 0.0) or 0.0,
                        predictive_jobs_count=m_data.get('predictive_jobs_count', 0) or 0,
                        predictive_filament_grams=m_data.get('predictive_filament_grams', 0.0) or 0.0,
                        predictive_window_days=m_data.get('predictive_window_days', 30) or 30,
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
                        original_name = secure_filename(wf_data.get('filename', 'attachment.jpg')) or 'attachment.jpg'
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
                        target_type=ul_data.get('target_type', 'filament'),
                        target_key=ul_data.get('target_key'),
                        expires_at=datetime.fromisoformat(ul_data['expires_at']) if ul_data.get('expires_at') else utc_now(),
                        is_consumed=ul_data.get('is_consumed', False),
                        consumed_at=datetime.fromisoformat(ul_data['consumed_at']) if ul_data.get('consumed_at') else None,
                    ))

                # ── 14. User sessions ─────────────────────────────────
                for us_data in data.get('user_sessions', []):
                    us_user = _resolve_user_ref(us_data.get('user'))
                    if not us_user:
                        continue
                    exists_us = UserSession.query.filter_by(
                        user_id=us_user.id,
                        session_key=us_data.get('session_key', ''),
                    ).first()
                    if exists_us:
                        continue
                    db.session.add(UserSession(
                        user_id=us_user.id,
                        session_key=us_data.get('session_key', ''),
                        ip_address=us_data.get('ip_address'),
                        user_agent=us_data.get('user_agent'),
                        created_at=datetime.fromisoformat(us_data['created_at']) if us_data.get('created_at') else utc_now(),
                        last_activity_at=datetime.fromisoformat(us_data['last_activity_at']) if us_data.get('last_activity_at') else None,
                    ))

                # ── 14b. Model categories ─────────────────────────────
                for cat_data in data.get('model_categories', []):
                    cat_name = cat_data.get('name', '').strip()
                    if not cat_name:
                        continue
                    exists_cat = ModelCategory.query.filter_by(name=cat_name).first()
                    if exists_cat:
                        continue
                    db.session.add(ModelCategory(
                        name=cat_name,
                        color=cat_data.get('color'),
                        created_at=datetime.fromisoformat(cat_data['created_at']) if cat_data.get('created_at') else utc_now(),
                    ))
                db.session.flush()  # Ensure categories are available for FK resolution

                # ── 15. Model comments ────────────────────────────────
                for mc_data in data.get('model_comments', []):
                    project_name = mc_data.get('project_name')
                    filename = mc_data.get('filename')
                    root_file = None
                    if project_name and filename:
                        proj = Project.query.filter_by(name=project_name).first()
                        if proj:
                            root_file = ProjectFile.query.filter_by(
                                project_id=proj.id, filename=filename
                            ).first()
                    mc_user = _resolve_user_ref(mc_data.get('user'))
                    if not root_file:
                        continue
                    exists_mc = ModelComment.query.filter_by(
                        root_file_id=root_file.id,
                        body=mc_data.get('body', ''),
                        created_at=datetime.fromisoformat(mc_data['created_at']) if mc_data.get('created_at') else utc_now(),
                    ).first()
                    if exists_mc:
                        continue
                    db.session.add(ModelComment(
                        root_file_id=root_file.id,
                        user_id=mc_user.id if mc_user else None,
                        body=mc_data.get('body', ''),
                        created_at=datetime.fromisoformat(mc_data['created_at']) if mc_data.get('created_at') else utc_now(),
                    ))

                # ── 16. Comment reactions ─────────────────────────────
                for cr_data in data.get('comment_reactions', []):
                    project_name = cr_data.get('project_name')
                    comment_body = cr_data.get('comment_body')
                    if not project_name or not comment_body:
                        continue
                    proj = Project.query.filter_by(name=project_name).first()
                    if not proj:
                        continue
                    comment = ProjectComment.query.filter_by(
                        project_id=proj.id,
                        body=comment_body,
                    ).order_by(ProjectComment.created_at.desc()).first()
                    if not comment:
                        continue
                    cr_user = _resolve_user_ref(cr_data.get('user'))
                    if not cr_user:
                        continue
                    exists_cr = ProjectCommentReaction.query.filter_by(
                        comment_id=comment.id,
                        user_id=cr_user.id,
                        emoji=cr_data.get('emoji', ''),
                    ).first()
                    if exists_cr:
                        continue
                    db.session.add(ProjectCommentReaction(
                        comment_id=comment.id,
                        user_id=cr_user.id,
                        emoji=cr_data.get('emoji', ''),
                        created_at=datetime.fromisoformat(cr_data['created_at']) if cr_data.get('created_at') else utc_now(),
                    ))

            app.logger.debug(f"Import finished: {imported_filaments} filaments, projects and Bambu jobs processed.")
            flash(translate('backup_import_success'), 'success')
        except Exception:
            db.session.rollback()
            app.logger.exception("Import failed")
            flash(translate('backup_import_failed'), 'error')

        return redirect(url_for('settings') + '?tab=data')
    app.register_blueprint(bp)
