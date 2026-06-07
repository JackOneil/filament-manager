"""Waste/scrap tracking — record failed prints with reason, weight, filament and project."""
import os
import uuid
from datetime import datetime

from flask import abort, redirect, render_template, request, send_from_directory, url_for, Blueprint
from werkzeug.utils import secure_filename

from auth import require_admin
from sqlalchemy.orm import joinedload
from database import db
from models import Filament, Project, WasteFile, WasteRecord, AppSetting
from utils import utc_now


_DEFAULT_WASTE_REASONS = ['stringing', 'warping', 'bed_adhesion', 'clogging', 'layer_shift', 'spaghetti', 'broken_support', 'other']
WASTE_IMAGE_EXTENSIONS = {'jpg', 'jpeg', 'png', 'gif', 'webp'}


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

        query = WasteRecord.query.order_by(WasteRecord.created_at.desc())
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
        db.session.commit()
        return redirect(url_for('waste_index'))

    @bp.route('/waste/<int:rec_id>/edit', methods=['POST'])
    def waste_edit(rec_id):
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

        db.session.commit()
        return redirect(url_for('waste_index'))

    @bp.route('/waste/<int:rec_id>/delete', methods=['POST'])
    def waste_delete(rec_id):
        from auth import get_current_user, is_admin
        user = get_current_user()
        if not is_admin(user):
            abort(403)
        rec = db.get_or_404(WasteRecord, rec_id)
        # Delete associated files from disk
        for f in list(rec.files):
            try:
                os.remove(f.filepath)
            except OSError:
                pass
        db.session.delete(rec)
        db.session.commit()
        return redirect(url_for('waste_index'))

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
        db.session.commit()
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
        db.session.commit()
        page = request.args.get('page', 1)
        reason = request.args.get('reason', '')
        filament = request.args.get('filament', '')
        project = request.args.get('project', '')
        rec_id = wf.waste_record_id
        return redirect(url_for('waste_index', page=page, reason=reason, filament=filament, project=project, _anchor=f'rec-{rec_id}'))
    app.register_blueprint(bp)
