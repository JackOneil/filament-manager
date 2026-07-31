"""Waste/scrap tracking — record failed prints with reason, weight, filament and project."""
import json
import math
import os
import uuid
from datetime import datetime, timedelta

from flask import abort, jsonify, redirect, render_template, request, send_from_directory, session, url_for, Blueprint
from werkzeug.utils import secure_filename

from auth import require_admin
from sqlalchemy.orm import joinedload
from database import db
from models import Filament, FilamentUndoLog, Project, WasteFile, WasteRecord, AppSetting
from routes.inventory_helpers import _UNDO_SESSION_KEY
from utils import deduct_filament_stock, log_movement, translate, utc_now, safe_commit


_DEFAULT_WASTE_REASONS = ['stringing', 'warping', 'bed_adhesion', 'clogging', 'layer_shift', 'spaghetti', 'broken_support', 'other']
WASTE_IMAGE_EXTENSIONS = {'jpg', 'jpeg', 'png', 'gif', 'webp'}

# Undo TTL for waste-record deletion — matches the filament undo window so
# the user has a realistic chance to click "Vrátit" before it expires.
_WASTE_UNDO_TTL_MINUTES = 15


def _restore_waste_stock(rec):
    """Return wasted grams back to the filament stock (delete path)."""
    if not rec or not rec.filament_id or not rec.weight_grams or rec.weight_grams <= 0:
        return
    filament = db.session.get(Filament, rec.filament_id)
    if not filament:
        return
    filament.weight_remaining = float(filament.weight_remaining or 0.0) + float(rec.weight_grams)
    if filament.weight_total > 0:
        expected_qty = math.ceil(filament.weight_remaining / filament.weight_total)
        if expected_qty > filament.quantity:
            filament.quantity = expected_qty
    log_movement(filament, 'add', float(rec.weight_grams), note=translate('movement_note_waste_restore'))


def _deduct_waste_stock(filament_id, weight_grams, project_id=None):
    """Deduct wasted grams from the filament stock (create/undo path)."""
    if not filament_id or not weight_grams or weight_grams <= 0:
        return
    filament = db.session.get(Filament, filament_id)
    if not filament:
        return
    actual = deduct_filament_stock(filament, weight_grams)
    if actual > 0:
        log_movement(
            filament,
            'waste',
            actual,
            project_id=project_id,
            note=translate('movement_note_waste'),
        )


def _get_waste_reasons():
    """Return the current list of waste reasons from AppSetting or default.

    Reasons are stored as a JSON array in AppSetting.waste_reasons_json.
    Falls back to the hardcoded default if unset or unparseable.
    """
    import json as _json
    setting = AppSetting.query.first()
    if setting and setting.waste_reasons_json:
        try:
            reasons = _json.loads(setting.waste_reasons_json)
            if isinstance(reasons, list) and all(isinstance(r, str) for r in reasons):
                return reasons
        except (TypeError, ValueError, _json.JSONDecodeError):
            pass
    return list(_DEFAULT_WASTE_REASONS)


def _get_extension(filename):
    return filename.rsplit('.', 1)[1].lower() if '.' in filename else ''


def _is_allowed_waste_image(filename):
    return _get_extension(filename) in WASTE_IMAGE_EXTENSIONS


def _build_waste_storage_name(rec_id, filename):
    safe_name = secure_filename(filename)
    unique_id = uuid.uuid4().hex[:12]
    return f'w{rec_id}_{unique_id}_{safe_name}'


def register(app):
    bp = Blueprint('waste', __name__)
    upload_folder = app.config.get(
        'PROJECT_UPLOAD_FOLDER',
        os.path.join(os.path.abspath(os.path.dirname(__file__)), '..', 'data', 'uploads'),
    )
    os.makedirs(upload_folder, exist_ok=True)

    @bp.route('/waste')
    def waste_index():
        from auth import get_current_user, is_admin
        user = get_current_user()
        if not is_admin(user):
            abort(403)

        filter_reason = request.args.get('reason', '')
        filter_filament = request.args.get('filament', '')
        filter_project = request.args.get('project', '')
        page = request.args.get('page', 1, type=int)

        query = WasteRecord.query.options(
            joinedload(WasteRecord.filament).joinedload(Filament.brand),
            joinedload(WasteRecord.filament).joinedload(Filament.material),
            joinedload(WasteRecord.filament).joinedload(Filament.color),
            joinedload(WasteRecord.project),
            joinedload(WasteRecord.files),
        ).order_by(WasteRecord.created_at.desc())
        if filter_reason and filter_reason in _get_waste_reasons():
            query = query.filter(WasteRecord.reason == filter_reason)
        if filter_filament:
            query = query.filter(WasteRecord.filament_id == filter_filament)
        if filter_project:
            query = query.filter(WasteRecord.project_id == filter_project)

        paginated = db.paginate(query.statement, page=page, per_page=20, error_out=False)

        filaments = Filament.query.options(joinedload(Filament.brand), joinedload(Filament.material), joinedload(Filament.color)).order_by(Filament.name).all()
        projects = Project.query.order_by(Project.name).all()

        filaments_json = [
            {
                'id': f.id,
                'label': f.name,
                'mat': f"{f.brand.name} {f.material.name}" if f.brand and f.material else '',
            }
            for f in filaments
        ]
        projects_json = [{'id': p.id, 'name': p.name} for p in projects]

        total_waste = db.session.query(db.func.sum(WasteRecord.weight_grams)).scalar() or 0

        return render_template(
            'waste.html',
            records=paginated.items,
            paginated=paginated,
            filaments=filaments,
            projects=projects,
            filaments_json=filaments_json,
            projects_json=projects_json,
            waste_reasons=_get_waste_reasons(),
            filter_reason=filter_reason,
            filter_filament=filter_filament,
            filter_project=filter_project,
            total_waste=total_waste,
        )

    @bp.route('/waste/add', methods=['POST'])
    def waste_add():
        from auth import get_current_user, is_admin
        user = get_current_user()
        if not is_admin(user):
            abort(403)

        filament_id = request.form.get('filament_id', type=int)
        project_id = request.form.get('project_id', type=int) or None
        reason = request.form.get('reason', 'other')
        if reason not in _get_waste_reasons():
            reason = 'other'
        notes = request.form.get('notes', '').strip() or None

        try:
            weight_grams = float(request.form.get('weight_grams', 0))
            if weight_grams <= 0:
                weight_grams = 0.0
        except (TypeError, ValueError):
            weight_grams = 0.0

        if not filament_id:
            return redirect(url_for('waste_index'))

        db.session.add(WasteRecord(
            filament_id=filament_id,
            project_id=project_id,
            reason=reason,
            weight_grams=weight_grams,
            notes=notes,
            recorded_by_user_id=user.id if user else None,
        ))
        # Wasted grams leave the inventory: deduct stock and log the movement.
        _deduct_waste_stock(filament_id, weight_grams, project_id)
        safe_commit()
        return redirect(url_for('waste_index'))

    @bp.route('/waste/<int:rec_id>/edit', methods=['POST'])
    def waste_edit(rec_id):
        from auth import get_current_user, is_admin
        user = get_current_user()
        if not is_admin(user):
            abort(403)
        rec = db.get_or_404(WasteRecord, rec_id)

        old_filament_id = rec.filament_id
        old_weight = float(rec.weight_grams or 0.0)

        filament_id = request.form.get('filament_id', type=int)
        if filament_id:
            rec.filament_id = filament_id

        project_id = request.form.get('project_id', type=int) or None
        rec.project_id = project_id

        reason = request.form.get('reason', 'other')
        if reason not in _get_waste_reasons():
            reason = 'other'
        rec.reason = reason

        try:
            weight_grams = float(request.form.get('weight_grams', 0))
            if weight_grams < 0:
                weight_grams = 0.0
        except (TypeError, ValueError):
            weight_grams = 0.0
        rec.weight_grams = weight_grams

        rec.notes = request.form.get('notes', '').strip() or None

        # Keep inventory consistent with the edit: restore the old amount to
        # the old filament, deduct the new amount from the new filament.
        if rec.filament_id == old_filament_id:
            delta = weight_grams - old_weight
            if delta > 0:
                _deduct_waste_stock(rec.filament_id, delta, rec.project_id)
            elif delta < 0:
                filament = db.session.get(Filament, rec.filament_id)
                if filament:
                    filament.weight_remaining = float(filament.weight_remaining or 0.0) + abs(delta)
                    log_movement(
                        filament,
                        'add',
                        abs(delta),
                        note=translate('movement_note_waste_restore'),
                    )
        else:
            if old_filament_id and old_weight > 0:
                old_fil = db.session.get(Filament, old_filament_id)
                if old_fil:
                    old_fil.weight_remaining = float(old_fil.weight_remaining or 0.0) + old_weight
                    log_movement(
                        old_fil,
                        'add',
                        old_weight,
                        note=translate('movement_note_waste_restore'),
                    )
            _deduct_waste_stock(rec.filament_id, weight_grams, rec.project_id)

        safe_commit()
        return redirect(url_for('waste_index'))

    @bp.route('/waste/<int:rec_id>/delete', methods=['POST'])
    def waste_delete(rec_id):
        from auth import get_current_user, is_admin
        user = get_current_user()
        if not is_admin(user):
            abort(403)
        rec = db.get_or_404(WasteRecord, rec_id)
        # Return the wasted grams back to the filament stock.
        _restore_waste_stock(rec)
        # Delete associated files from disk
        for f in list(rec.files):
            try:
                os.remove(f.filepath)
            except OSError:
                pass
        db.session.delete(rec)
        safe_commit()
        return redirect(url_for('waste_index'))

    @bp.route('/waste/_records')
    def waste_records_partial():
        """AJAX partial — returns only the records list + pagination."""
        from auth import get_current_user, is_admin
        user = get_current_user()
        if not is_admin(user):
            abort(403)

        filter_reason = request.args.get('reason', '')
        filter_filament = request.args.get('filament', '')
        filter_project = request.args.get('project', '')
        page = request.args.get('page', 1, type=int)

        query = WasteRecord.query.options(
            joinedload(WasteRecord.filament).joinedload(Filament.brand),
            joinedload(WasteRecord.filament).joinedload(Filament.material),
            joinedload(WasteRecord.filament).joinedload(Filament.color),
            joinedload(WasteRecord.project),
            joinedload(WasteRecord.files),
        ).order_by(WasteRecord.created_at.desc())
        if filter_reason and filter_reason in _get_waste_reasons():
            query = query.filter(WasteRecord.reason == filter_reason)
        if filter_filament:
            query = query.filter(WasteRecord.filament_id == filter_filament)
        if filter_project:
            query = query.filter(WasteRecord.project_id == filter_project)

        paginated = db.paginate(query.statement, page=page, per_page=20, error_out=False)
        total_waste = db.session.query(db.func.sum(WasteRecord.weight_grams)).scalar() or 0

        return render_template(
            '_waste_records.html',
            records=paginated.items,
            paginated=paginated,
            filter_reason=filter_reason,
            filter_filament=filter_filament,
            filter_project=filter_project,
            total_waste=total_waste,
        )

    @bp.route('/waste/_add', methods=['POST'])
    def waste_add_ajax():
        from auth import get_current_user, is_admin
        user = get_current_user()
        if not is_admin(user):
            abort(403)

        filament_id = request.form.get('filament_id', type=int)
        project_id = request.form.get('project_id', type=int) or None
        reason = request.form.get('reason', 'other')
        if reason not in _get_waste_reasons():
            reason = 'other'
        notes = request.form.get('notes', '').strip() or None

        try:
            weight_grams = float(request.form.get('weight_grams', 0))
            if weight_grams <= 0:
                weight_grams = 0.0
        except (TypeError, ValueError):
            weight_grams = 0.0

        if not filament_id:
            return jsonify(success=False, error='filament_required'), 400

        rec = WasteRecord(
            filament_id=filament_id,
            project_id=project_id,
            reason=reason,
            weight_grams=weight_grams,
            notes=notes,
            recorded_by_user_id=user.id if user else None,
        )
        db.session.add(rec)
        # Wasted grams leave the inventory: deduct stock and log the movement.
        _deduct_waste_stock(filament_id, weight_grams, project_id)
        safe_commit()
        return jsonify(success=True, id=rec.id)

    @bp.route('/waste/<int:rec_id>/_edit', methods=['POST'])
    def waste_edit_ajax(rec_id):
        from auth import get_current_user, is_admin
        user = get_current_user()
        if not is_admin(user):
            abort(403)
        rec = db.get_or_404(WasteRecord, rec_id)

        filament_id = request.form.get('filament_id', type=int)
        if filament_id:
            rec.filament_id = filament_id

        project_id = request.form.get('project_id', type=int) or None
        rec.project_id = project_id

        reason = request.form.get('reason', 'other')
        if reason not in _get_waste_reasons():
            reason = 'other'
        rec.reason = reason

        try:
            weight_grams = float(request.form.get('weight_grams', 0))
            if weight_grams < 0:
                weight_grams = 0.0
        except (TypeError, ValueError):
            weight_grams = 0.0
        rec.weight_grams = weight_grams

        rec.notes = request.form.get('notes', '').strip() or None
        safe_commit()
        return jsonify(success=True)

    @bp.route('/waste/<int:rec_id>/_delete', methods=['POST'])
    def waste_delete_ajax(rec_id):
        from auth import get_current_user, is_admin
        user = get_current_user()
        if not is_admin(user):
            abort(403)
        rec = db.get_or_404(WasteRecord, rec_id)

        # Return the wasted grams back to the filament stock.
        _restore_waste_stock(rec)

        # Create undo log before deleting
        undo_data = json.dumps({
            'filament_id': rec.filament_id,
            'project_id': rec.project_id,
            'reason': rec.reason,
            'weight_grams': rec.weight_grams,
            'notes': rec.notes,
            'created_at': rec.created_at.isoformat() if rec.created_at else None,
            'recorded_by_user_id': rec.recorded_by_user_id,
        })
        undo_log = FilamentUndoLog(
            user_id=user.id,
            action_type='delete_waste',
            target_type='waste',
            target_key=undo_data,
            snapshot_data=None,
            expires_at=utc_now() + timedelta(minutes=_WASTE_UNDO_TTL_MINUTES),
        )
        db.session.add(undo_log)
        safe_commit()
        # Populate the undo toast slot so the toast renders on the next page
        # load and the /inventory/undo endpoint can consume the snapshot.
        session[_UNDO_SESSION_KEY] = {
            'undo_log_id': undo_log.id,
            'title_key': 'undo_toast_waste_delete_title',
            'detail': (rec.filament.name if rec.filament else '') or '',
        }

        for f in list(rec.files):
            try:
                os.remove(f.filepath)
            except OSError:
                pass
        db.session.delete(rec)
        safe_commit()
        return jsonify(success=True)

    @bp.route('/waste/<int:rec_id>/_data')
    def waste_data_ajax(rec_id):
        from auth import get_current_user, is_admin
        user = get_current_user()
        if not is_admin(user):
            abort(403)
        rec = db.get_or_404(WasteRecord, rec_id)
        return jsonify(
            filament_id=rec.filament_id,
            filament_name=rec.filament.name if rec.filament else '',
            project_id=rec.project_id,
            project_name=rec.project.name if rec.project else '',
            reason=rec.reason,
            weight=rec.weight_grams,
            notes=rec.notes or '',
        )

    @bp.route('/waste/<int:rec_id>/_upload', methods=['POST'])
    def waste_upload_ajax(rec_id):
        from auth import get_current_user, is_admin
        user = get_current_user()
        if not is_admin(user):
            abort(403)
        rec = db.get_or_404(WasteRecord, rec_id)
        files = request.files.getlist('file')
        added = []
        for file in files:
            if not file or file.filename == '':
                continue
            if not _is_allowed_waste_image(file.filename):
                continue
            original_filename = secure_filename(file.filename)
            if not original_filename:
                continue
            stored_name = _build_waste_storage_name(rec.id, original_filename)
            filepath = os.path.join(upload_folder, stored_name)
            file.save(filepath)
            wf = WasteFile(
                waste_record_id=rec.id,
                filename=original_filename,
                filepath=filepath,
            )
            db.session.add(wf)
            added.append(wf)
        safe_commit()
        from flask import url_for as _url_for
        thumbnails = []
        for wf in added:
            thumbnails.append({
                'id': wf.id,
                'url': _url_for('waste_serve_file', file_id=wf.id),
                'filename': wf.filename,
            })
        return jsonify(success=True, thumbnails=thumbnails)

    @bp.route('/waste/file/<int:file_id>/_delete', methods=['POST'])
    def waste_delete_file_ajax(file_id):
        from auth import get_current_user, is_admin
        user = get_current_user()
        if not is_admin(user):
            abort(403)
        wf = db.get_or_404(WasteFile, file_id)
        try:
            os.remove(wf.filepath)
        except OSError:
            pass
        db.session.delete(wf)
        safe_commit()
        return jsonify(success=True)

    @bp.route('/waste/<int:rec_id>/upload', methods=['POST'])
    def waste_upload_file(rec_id):
        from auth import get_current_user, is_admin
        user = get_current_user()
        if not is_admin(user):
            abort(403)
        rec = db.get_or_404(WasteRecord, rec_id)
        files = request.files.getlist('file')
        for file in files:
            if not file or file.filename == '':
                continue
            if not _is_allowed_waste_image(file.filename):
                continue
            original_filename = secure_filename(file.filename)
            if not original_filename:
                continue
            stored_name = _build_waste_storage_name(rec.id, original_filename)
            filepath = os.path.join(upload_folder, stored_name)
            file.save(filepath)
            db.session.add(WasteFile(
                waste_record_id=rec.id,
                filename=original_filename,
                filepath=filepath,
            ))
        safe_commit()
        page = request.args.get('page', 1)
        reason = request.args.get('reason', '')
        filament = request.args.get('filament', '')
        project = request.args.get('project', '')
        return redirect(url_for('waste_index', page=page, reason=reason, filament=filament, project=project, _anchor=f'rec-{rec_id}'))

    @bp.route('/waste/file/<int:file_id>')
    def waste_serve_file(file_id):
        from auth import get_current_user, is_admin
        user = get_current_user()
        if not is_admin(user):
            abort(403)
        wf = db.get_or_404(WasteFile, file_id)
        real_path = os.path.realpath(wf.filepath)
        real_folder = os.path.realpath(upload_folder)
        if not real_path.startswith(real_folder + os.sep):
            abort(403)
        return send_from_directory(os.path.dirname(wf.filepath), os.path.basename(wf.filepath), as_attachment=False)

    @bp.route('/waste/file/<int:file_id>/download')
    def waste_download_file(file_id):
        from auth import get_current_user, is_admin
        user = get_current_user()
        if not is_admin(user):
            abort(403)
        wf = db.get_or_404(WasteFile, file_id)
        real_path = os.path.realpath(wf.filepath)
        real_folder = os.path.realpath(upload_folder)
        if not real_path.startswith(real_folder + os.sep):
            abort(403)
        return send_from_directory(os.path.dirname(wf.filepath), os.path.basename(wf.filepath), as_attachment=True, download_name=wf.filename)

    @bp.route('/waste/file/<int:file_id>/delete', methods=['POST'])
    def waste_delete_file(file_id):
        from auth import get_current_user, is_admin
        user = get_current_user()
        if not is_admin(user):
            abort(403)
        wf = db.get_or_404(WasteFile, file_id)
        try:
            os.remove(wf.filepath)
        except OSError:
            pass
        db.session.delete(wf)
        safe_commit()
        page = request.args.get('page', 1)
        reason = request.args.get('reason', '')
        filament = request.args.get('filament', '')
        project = request.args.get('project', '')
        rec_id = wf.waste_record_id
        return redirect(url_for('waste_index', page=page, reason=reason, filament=filament, project=project, _anchor=f'rec-{rec_id}'))
    app.register_blueprint(bp)
