import os
import math
import hashlib
import mimetypes
import logging
import secrets
from datetime import datetime
from types import SimpleNamespace

from flask import (
    Blueprint, render_template, request, redirect, url_for,
    jsonify, send_from_directory, abort, flash, current_app
)
from werkzeug.utils import secure_filename

from database import db
from auth import get_current_user, is_admin
from models import Project, ProjectFile, AppSetting, User, ModelComment
from utils import escape_like, utc_now, translate

logger = logging.getLogger(__name__)

bp = Blueprint('models', __name__)

MODEL_EXTENSIONS = {'3mf', 'stl', 'obj', 'amf', 'step', 'stp', 'gcode', 'gc', 'bgcode'}
STL_EXTENSIONS = {'stl'}

def _get_projects():
    user = get_current_user()
    if is_admin(user):
        return Project.query.order_by(Project.name.asc()).all()
    if not user:
        return []
    return Project.query.filter_by(owner_user_id=user.id).order_by(Project.name.asc()).all()

def _get_latest_version(root_file):
    if not root_file.versions:
        return root_file
    all_versions = [root_file] + root_file.versions
    all_versions.sort(key=lambda f: f.version, reverse=True)
    return all_versions[0]

def _check_project_access(project_id):
    project = Project.query.get_or_404(project_id)
    user = get_current_user()
    if is_admin(user):
        return project
    if user and project.owner_user_id == user.id:
        return project
    abort(404)

def _check_file_access(file_id):
    f = ProjectFile.query.get_or_404(file_id)
    if f.project_id is not None:
        _check_project_access(f.project_id)
    return f

def _is_allowed_model_file(filename):
    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
    return ext in MODEL_EXTENSIONS

def _get_stl_thumbnail_paths():
    """Return (upload_folder, thumb_dir) for STL thumbnail storage."""
    upload_folder = current_app.config.get(
        'PROJECT_UPLOAD_FOLDER',
        os.path.join(os.path.abspath(os.path.dirname(__file__)), '..', 'data', 'uploads')
    )
    thumb_dir = os.path.join(upload_folder, 'thumbnails')
    os.makedirs(thumb_dir, exist_ok=True)
    return upload_folder, thumb_dir


def _extract_3mf_thumbnail(project_file):
    """Extract an embedded thumbnail from a 3MF file (ZIP archive).

    Many slicers (Bambu Studio, PrusaSlicer, Cura) embed a preview image
    at Metadata/thumbnail.png inside the 3MF archive.
    Returns True on success, False otherwise.
    """
    if not project_file or not project_file.filename:
        return False
    ext = project_file.filename.rsplit('.', 1)[-1].lower() if '.' in project_file.filename else ''
    if ext != '3mf':
        return False
    if project_file.thumbnail_path:
        return True
    if not project_file.filepath or not os.path.isfile(project_file.filepath):
        return False
    try:
        import zipfile
        with zipfile.ZipFile(project_file.filepath, 'r') as zf:
            candidates = [n for n in zf.namelist() if n.lower().endswith(('thumbnail.png', 'thumbnail.jpg', 'thumbnail.jpeg'))]
            if not candidates:
                # Try Metadata/thumbnail.png specifically
                if 'Metadata/thumbnail.png' in zf.namelist():
                    candidates = ['Metadata/thumbnail.png']
            if not candidates:
                return False
            upload_folder, thumb_dir = _get_stl_thumbnail_paths()
            # Use same naming convention as STL thumbnails
            thumb_name = f'thumb_{project_file.id}.png'
            thumb_path = os.path.join(thumb_dir, thumb_name)
            with zf.open(candidates[0]) as src, open(thumb_path, 'wb') as dst:
                dst.write(src.read())
            project_file.thumbnail_path = f'thumbnails/{thumb_name}'
            return True
    except Exception as exc:
        logger.warning('3MF thumbnail extraction failed for ProjectFile id=%s: %s', project_file.id, exc)
    return False


def render_stl_thumbnail_for_file(project_file, commit=True):
    """Auto-render an STL thumbnail for a ProjectFile.

    Skips silently if:
    - the file extension is not STL
    - the file is missing on disk
    - the file already has a thumbnail_path set
    - the on-disk file does not exist
    Returns True on success, False otherwise.
    """
    if not project_file or not project_file.filename:
        return False
    ext = project_file.filename.rsplit('.', 1)[-1].lower() if '.' in project_file.filename else ''
    if ext not in STL_EXTENSIONS:
        return False
    if project_file.thumbnail_path:
        return True  # already rendered
    if not project_file.filepath or not os.path.isfile(project_file.filepath):
        return False

    try:
        from routes.model_renderer import render_stl_thumbnail
        upload_folder, thumb_dir = _get_stl_thumbnail_paths()
        thumb_name = f'thumb_{project_file.id}.png'
        thumb_path = os.path.join(thumb_dir, thumb_name)
        ok = render_stl_thumbnail(project_file.filepath, thumb_path)
        if ok:
            project_file.thumbnail_path = f'thumbnails/{thumb_name}'
            if commit:
                db.session.commit()
            logger.info('Auto-rendered STL thumbnail for ProjectFile id=%s', project_file.id)
            return True
    except Exception as exc:
        logger.warning('STL thumbnail render failed for ProjectFile id=%s: %s', project_file.id, exc)
    return False

def _get_file_size_and_checksum(filepath):
    try:
        size = os.path.getsize(filepath)
        sha = hashlib.sha256()
        with open(filepath, 'rb') as fh:
            while chunk := fh.read(8192):
                sha.update(chunk)
        return size, sha.hexdigest()
    except OSError:
        return 0, None

@bp.route('/models')
def models_index():
    projects = _get_projects()
    setting = AppSetting.query.first()

    # Stats bar
    user = get_current_user()
    base_q = ProjectFile.query.filter(ProjectFile.parent_file_id.is_(None))
    if not is_admin(user):
        base_q = base_q.outerjoin(Project).filter(Project.owner_user_id == user.id if user else False)
    ext_conditions = [ProjectFile.filename.like(f'%.{ext}') for ext in MODEL_EXTENSIONS]
    base_q = base_q.filter(db.or_(*ext_conditions))

    total_count = base_q.count()
    total_size = db.session.query(
        db.func.sum(ProjectFile.file_size_bytes)
    ).filter(
        ProjectFile.id.in_([f.id for f in base_q.with_entities(ProjectFile.id).all()])
    ).scalar() or 0
    no_thumb = base_q.filter(ProjectFile.thumbnail_path.is_(None)).count()

    models_stats = {
        'total': total_count,
        'total_size': total_size,
        'no_thumb': no_thumb,
    }

    return render_template(
        'models_index.html',
        projects=projects,
        setting=setting,
        model_extensions=sorted(list(MODEL_EXTENSIONS)),
        models_stats=models_stats,
    )

@bp.route('/models/upload', methods=['POST'])
def model_upload():
    project_id = request.form.get('project_id', type=int) or None
    if project_id:
        project = _check_project_access(project_id)
    else:
        project = None
    if 'file' not in request.files:
        flash(translate('models_error_upload'), 'error')
        return redirect(url_for('models.models_index'))
    file = request.files['file']
    if file.filename == '':
        flash(translate('models_error_upload'), 'error')
        return redirect(url_for('models.models_index'))
    if not _is_allowed_model_file(file.filename):
        flash(translate('models_error_type'), 'error')
        return redirect(url_for('models.models_index'))
    original_filename = secure_filename(file.filename)
    if not original_filename:
        flash(translate('models_error_type'), 'error')
        return redirect(url_for('models.models_index'))
    upload_folder = current_app.config.get(
        'PROJECT_UPLOAD_FOLDER',
        os.path.join(os.path.abspath(os.path.dirname(__file__)), '..', 'data', 'uploads')
    )
    import uuid
    unique_id = uuid.uuid4().hex[:12]
    stored_filename = f'{project.id if project else 0}_{unique_id}_{original_filename}'
    filepath = os.path.join(upload_folder, stored_filename)
    file.save(filepath)
    size, checksum = _get_file_size_and_checksum(filepath)
    mime = mimetypes.guess_type(original_filename)[0] or 'application/octet-stream'
    display = original_filename.rsplit('.', 1)[0] if '.' in original_filename else original_filename
    user = get_current_user()
    version_note = request.form.get('version_note', '').strip() or None
    new_file = ProjectFile(
        project_id=project.id if project else None,
        filename=original_filename,
        filepath=filepath,
        version=1,
        parent_file_id=None,
        display_name=display,
        file_size_bytes=size,
        mime_type=mime,
        checksum_sha256=checksum,
        version_note=version_note,
        uploaded_by_user_id=user.id if user else None
    )
    db.session.add(new_file)
    db.session.commit()
    # Auto-render STL thumbnail or extract 3MF thumbnail
    try:
        if not render_stl_thumbnail_for_file(new_file, commit=True):
            _extract_3mf_thumbnail(new_file)
            db.session.commit()
    except Exception as exc:
        logger.warning('Auto-thumbnail trigger failed for new model id=%s: %s', new_file.id, exc)
    flash(translate('models_upload_success'), 'success')
    return redirect(url_for('models.model_detail', root_id=new_file.id))

@bp.route('/api/models-list')
def api_models_list():
    query = ProjectFile.query.outerjoin(Project).filter(ProjectFile.parent_file_id.is_(None))
    
    if not is_admin():
        query = query.filter(Project.owner_user_id == get_current_user().id)
        
    conditions = []
    for ext in MODEL_EXTENSIONS:
        conditions.append(ProjectFile.filename.like(f'%.{ext}'))
    query = query.filter(db.or_(*conditions))

    # Search & filters
    fulltext = request.args.get('fulltext', '').strip()
    if fulltext:
        ft = f"%{escape_like(fulltext)}%"
        query = query.filter(db.or_(
            ProjectFile.display_name.ilike(ft),
            ProjectFile.filename.ilike(ft),
            Project.name.ilike(ft)
        ))
        
    project_id = request.args.get('project_id', type=int)
    no_project = request.args.get('no_project') == '1'
    if no_project:
        query = query.filter(ProjectFile.project_id.is_(None))
    elif project_id:
        query = query.filter(ProjectFile.project_id == project_id)
        
    file_type = request.args.get('file_type', '').strip().lower()
    if file_type:
        query = query.filter(ProjectFile.filename.like(f'%.{file_type}'))

    models_list = query.all()

    # Enrich models for sorting
    enriched = []
    for root in models_list:
        latest = _get_latest_version(root)
        enriched.append({
            'root': root,
            'latest': latest,
            'display_name': root.display_name or root.filename.rsplit('.', 1)[0],
            'project_name': root.project.name if root.project else '',
            'size': latest.file_size_bytes or 0,
            'uploaded_at': latest.uploaded_at or datetime.min,
            'version_count': len([root] + root.versions),
            'model_note': root.model_note or '',
        })

    # Sort
    sort_by = request.args.get('sort_by', 'uploaded')
    if sort_by == 'name_asc':
        enriched.sort(key=lambda x: x['display_name'].lower())
    elif sort_by == 'name_desc':
        enriched.sort(key=lambda x: x['display_name'].lower(), reverse=True)
    elif sort_by == 'project':
        enriched.sort(key=lambda x: x['project_name'].lower())
    elif sort_by == 'size_desc':
        enriched.sort(key=lambda x: x['size'], reverse=True)
    elif sort_by == 'uploaded_asc':
        enriched.sort(key=lambda x: x['uploaded_at'])
    else:  # uploaded (newest first)
        enriched.sort(key=lambda x: x['uploaded_at'], reverse=True)

    # Paginate
    page = request.args.get('page', 1, type=int)
    setting = AppSetting.query.first()
    per_page = setting.items_per_page if setting and setting.items_per_page in [12, 24, 48, 96] else 12
    
    total = len(enriched)
    pages = max(1, math.ceil(total / per_page))
    page = min(max(page, 1), pages)
    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    
    paginated_items = enriched[start_idx:end_idx]
    
    # Custom pagination pages generator for safety
    page_list = list(range(1, pages + 1))
    
    pagination = SimpleNamespace(
        page=page,
        pages=pages,
        total=total,
        has_prev=page > 1,
        has_next=page < pages,
        prev_num=page - 1 if page > 1 else 1,
        next_num=page + 1 if page < pages else pages,
        page_list=page_list
    )

    view_mode = request.args.get('view', 'card')
    template_name = '_models_cards.html' if view_mode == 'card' else '_models_rows.html'
    
    html = render_template(
        template_name,
        models=paginated_items,
        pagination=pagination
    )
    return jsonify({'html': html})

@bp.route('/models/<int:root_id>')
def model_detail(root_id):
    root_file = _check_file_access(root_id)
    if root_file.parent_file_id is not None:
        # Must always open details of the root file
        return redirect(url_for('models.model_detail', root_id=root_file.parent_file_id))

    latest = _get_latest_version(root_file)

    # Compile history: root file first, then subsequent versions sorted by version number
    history = [root_file] + root_file.versions
    history.sort(key=lambda f: f.version, reverse=True)

    # Check for same checksum warning flag in request
    same_checksum = request.args.get('same_checksum') == '1'

    comments = ModelComment.query.filter_by(root_file_id=root_id)\
                                 .order_by(ModelComment.created_at.asc()).all()

    return render_template(
        'models_detail.html',
        root=root_file,
        latest=latest,
        history=history,
        same_checksum=same_checksum,
        projects=_get_projects(),
        comments=comments,
    )

@bp.route('/models/<int:root_id>/edit', methods=['POST'])
def model_edit(root_id):
    root_file = _check_file_access(root_id)
    display_name = request.form.get('display_name', '').strip()
    version_note = request.form.get('version_note', '').strip()
    model_note   = request.form.get('model_note', '').strip() or None
    project_id   = request.form.get('project_id', type=int) or None

    if not display_name:
        flash(translate('models_error_edit_name_required'), 'error')
        return redirect(url_for('models.model_detail', root_id=root_file.id))

    if project_id:
        _check_project_access(project_id)

    latest = _get_latest_version(root_file)

    root_file.display_name = display_name
    root_file.model_note   = model_note
    root_file.project_id   = project_id
    # Update note specifically on the latest version
    latest.version_note = version_note

    db.session.commit()
    flash(translate('models_success_edit'), 'success')
    return redirect(url_for('models.model_detail', root_id=root_file.id))

@bp.route('/models/<int:root_id>/upload-version', methods=['POST'])
def model_upload_version(root_id):
    root_file = _check_file_access(root_id)
    if 'file' not in request.files:
        flash(translate('models_error_upload'), 'error')
        return redirect(url_for('models.model_detail', root_id=root_file.id))
        
    file = request.files['file']
    if file.filename == '':
        flash(translate('models_error_upload'), 'error')
        return redirect(url_for('models.model_detail', root_id=root_file.id))
        
    if not _is_allowed_model_file(file.filename):
        flash(translate('models_error_type'), 'error')
        return redirect(url_for('models.model_detail', root_id=root_file.id))
        
    original_filename = secure_filename(file.filename)
    if not original_filename:
        flash(translate('models_error_type'), 'error')
        return redirect(url_for('models.model_detail', root_id=root_file.id))
        
    upload_folder = current_app.config.get(
        'PROJECT_UPLOAD_FOLDER',
        os.path.join(os.path.abspath(os.path.dirname(__file__)), '..', 'data', 'uploads')
    )
    
    # Stored with unique secure format: {project_id}_{uuid.uuid4().hex[:12]}_{filename}
    import uuid
    unique_id = uuid.uuid4().hex[:12]
    stored_filename = f'{root_file.project_id or 0}_{unique_id}_{original_filename}'
    filepath = os.path.join(upload_folder, stored_filename)
    file.save(filepath)
    
    # Get metadata
    size, checksum = _get_file_size_and_checksum(filepath)
    mime = mimetypes.guess_type(original_filename)[0] or 'application/octet-stream'
    
    latest = _get_latest_version(root_file)
    new_version = latest.version + 1
    
    # Check for same checksum warning
    same_checksum = (checksum is not None and latest.checksum_sha256 == checksum)
    
    user = get_current_user()
    
    new_file = ProjectFile(
        project_id=root_file.project_id,
        filename=original_filename,
        filepath=filepath,
        version=new_version,
        parent_file_id=root_file.id,
        display_name=root_file.display_name,
        file_size_bytes=size,
        mime_type=mime,
        checksum_sha256=checksum,
        version_note=request.form.get('version_note', '').strip() or None,
        uploaded_by_user_id=user.id if user else None
    )
    
    db.session.add(new_file)
    db.session.commit()

    # Auto-render STL thumbnail or extract 3MF thumbnail (non-blocking for the user)
    try:
        if not render_stl_thumbnail_for_file(new_file, commit=True):
            _extract_3mf_thumbnail(new_file)
            db.session.commit()
    except Exception as exc:
        logger.warning('Auto-thumbnail trigger failed for new version id=%s: %s', new_file.id, exc)

    flash(translate('models_success_upload'), 'success')
    return redirect(url_for('models.model_detail', root_id=root_file.id, same_checksum='1' if same_checksum else None))

def _delete_model_chain(root_file):
    """Delete root file and all its versions from DB and disk."""
    all_files = [root_file] + root_file.versions
    upload_folder, thumb_dir = _get_stl_thumbnail_paths()
    for f in all_files:
        _delete_file_on_disk(f)
        db.session.delete(f)


@bp.route('/models/<int:root_id>/delete', methods=['POST'])
def model_delete(root_id):
    root_file = _check_file_access(root_id)
    _delete_model_chain(root_file)
    db.session.commit()
    flash(translate('models_success_deleted'), 'success')
    return redirect(url_for('models.models_index'))

@bp.route('/models/version/<int:file_id>/delete', methods=['POST'])
def model_delete_version(file_id):
    pf = _check_file_access(file_id)
    is_root = (pf.parent_file_id is None)
    if is_root:
        # If deleting the root, handle re-parenting first
        children = ProjectFile.query.filter_by(parent_file_id=pf.id).order_by(ProjectFile.version.desc()).all()
        if children:
            # Promote the newest child as the new root
            new_root = children[0]
            new_root.parent_file_id = None
            # Re-parent remaining children to the new root
            for child in children[1:]:
                child.parent_file_id = new_root.id
            # Delete the old root from DB and disk
            _delete_file_on_disk(pf)
            db.session.delete(pf)
            db.session.commit()
            flash(translate('models_success_version_deleted'), 'success')
            return redirect(url_for('models.model_detail', root_id=new_root.id))
        # No children — delete the only version (entire model gone)
    # Non-root or lone root
    root_file = pf if is_root else ProjectFile.query.get(pf.parent_file_id)
    _delete_file_on_disk(pf)
    db.session.delete(pf)
    db.session.commit()
    if is_root:
        flash(translate('models_success_deleted'), 'success')
        return redirect(url_for('models.models_index'))
    else:
        flash(translate('models_success_version_deleted'), 'success')
        return redirect(url_for('models.model_detail', root_id=root_file.id))


def _delete_file_on_disk(pf):
    """Delete a ProjectFile from disk (file + thumbnail)."""
    try:
        if os.path.exists(pf.filepath):
            os.remove(pf.filepath)
    except OSError:
        pass
    if pf.thumbnail_path:
        upload_folder = current_app.config.get(
            'PROJECT_UPLOAD_FOLDER',
            os.path.join(os.path.abspath(os.path.dirname(__file__)), '..', 'data', 'uploads')
        )
        thumb_full = os.path.join(upload_folder, pf.thumbnail_path)
        try:
            if os.path.exists(thumb_full):
                os.remove(thumb_full)
        except OSError:
            pass


@bp.route('/models/<int:root_id>/download')
def model_download_latest(root_id):
    root_file = _check_file_access(root_id)
    latest = _get_latest_version(root_file)
    return _send_file_safely(latest, as_attachment=True)

@bp.route('/models/version/<int:file_id>/download')
def model_download_version(file_id):
    f = _check_file_access(file_id)
    return _send_file_safely(f, as_attachment=True)

@bp.route('/models/version/<int:file_id>/view/<filename>')
def model_view_version(file_id, filename):
    f = _check_file_access(file_id)
    return _send_file_safely(f, as_attachment=False)

@bp.route('/models/version/<int:file_id>/thumbnail', methods=['POST'])
def model_upload_thumbnail(file_id):
    f = _check_file_access(file_id)
    
    img_data = request.form.get('image')
    if not img_data:
        return jsonify({'error': 'invalid data'}), 400
        
    is_jpeg = img_data.startswith('data:image/jpeg;base64,')
    is_png = img_data.startswith('data:image/png;base64,')
    
    if not (is_jpeg or is_png):
        return jsonify({'error': 'invalid data'}), 400
        
    import base64
    raw_data = base64.b64decode(img_data.split(',')[1])
    
    upload_folder = current_app.config.get(
        'PROJECT_UPLOAD_FOLDER',
        os.path.join(os.path.abspath(os.path.dirname(__file__)), '..', 'data', 'uploads')
    )
    thumb_dir = os.path.join(upload_folder, 'thumbnails')
    os.makedirs(thumb_dir, exist_ok=True)
    
    ext = 'png' if is_png else 'jpg'
    thumb_name = f'thumb_{f.id}.{ext}'
    thumb_path = os.path.join(thumb_dir, thumb_name)
    
    with open(thumb_path, 'wb') as handle:
        handle.write(raw_data)
        
    f.thumbnail_path = f'thumbnails/{thumb_name}'
    db.session.commit()
    
    return jsonify({'success': True, 'path': f.thumbnail_path})

@bp.route('/models/thumbnail/<int:file_id>')
def serve_thumbnail(file_id):
    f = _check_file_access(file_id)
    if not f.thumbnail_path:
        abort(404)
    upload_folder = current_app.config.get(
        'PROJECT_UPLOAD_FOLDER',
        os.path.join(os.path.abspath(os.path.dirname(__file__)), '..', 'data', 'uploads')
    )
    return send_from_directory(upload_folder, f.thumbnail_path, as_attachment=False)

def _send_file_safely(project_file, as_attachment=True):
    upload_folder = current_app.config.get(
        'PROJECT_UPLOAD_FOLDER',
        os.path.join(os.path.abspath(os.path.dirname(__file__)), '..', 'data', 'uploads')
    )
    real_path = os.path.realpath(project_file.filepath)
    real_folder = os.path.realpath(upload_folder)
    if not real_path.startswith(real_folder + os.sep):
        abort(403)
        
    return send_from_directory(
        os.path.dirname(project_file.filepath),
        os.path.basename(project_file.filepath),
        as_attachment=as_attachment,
        download_name=project_file.filename
    )


@bp.route('/models/<int:root_id>/comments', methods=['POST'])
def model_add_comment(root_id):
    root_file = _check_file_access(root_id)
    body = request.form.get('body', '').strip()
    if not body:
        flash(translate('models_comment_empty_error'), 'error')
        return redirect(url_for('models.model_detail', root_id=root_id))
    user = get_current_user()
    comment = ModelComment(root_file_id=root_id, user_id=user.id if user else None, body=body)
    db.session.add(comment)
    db.session.commit()
    return redirect(url_for('models.model_detail', root_id=root_id) + '#model-comments')


@bp.route('/models/<int:root_id>/comments/<int:comment_id>/delete', methods=['POST'])
def model_delete_comment(root_id, comment_id):
    comment = ModelComment.query.get_or_404(comment_id)
    user = get_current_user()
    if not is_admin(user) and (not user or comment.user_id != user.id):
        abort(403)
    db.session.delete(comment)
    db.session.commit()
    return redirect(url_for('models.model_detail', root_id=root_id) + '#model-comments')


@bp.route('/models/<int:root_id>/share/generate', methods=['POST'])
def model_generate_share(root_id):
    root_file = _check_file_access(root_id)
    if not root_file.share_token:
        root_file.share_token = secrets.token_urlsafe(32)
        db.session.commit()
    return redirect(url_for('models.model_detail', root_id=root_id))


@bp.route('/models/<int:root_id>/share/revoke', methods=['POST'])
def model_revoke_share(root_id):
    root_file = _check_file_access(root_id)
    root_file.share_token = None
    db.session.commit()
    return redirect(url_for('models.model_detail', root_id=root_id))


@bp.route('/models/share/<token>')
def model_public_share(token):
    """Public (no-auth) read-only model view."""
    root_file = ProjectFile.query.filter_by(share_token=token, parent_file_id=None).first_or_404()
    latest    = _get_latest_version(root_file)
    history   = sorted([root_file] + root_file.versions, key=lambda f: f.version, reverse=True)
    return render_template(
        'models_share.html',
        root=root_file,
        latest=latest,
        history=history,
    )


@bp.route('/models/share/<token>/file/<int:file_id>/<filename>')
def model_public_share_file(token, file_id, filename):
    """Serve a model file for public share (token-based auth, no login needed)."""
    from sqlalchemy import or_
    root_file = ProjectFile.query.filter_by(share_token=token, parent_file_id=None).first_or_404()
    # The requested file must be either the root or one of its versions
    version_file = ProjectFile.query.filter(
        ProjectFile.id == file_id,
        or_(
            ProjectFile.id == root_file.id,
            ProjectFile.parent_file_id == root_file.id
        )
    ).first_or_404()
    return _send_file_safely(version_file, as_attachment=False)


@bp.route('/models/share/<token>/file/<int:file_id>/<filename>/download')
def model_public_share_download(token, file_id, filename):
    """Download a model file from public share (token-based auth)."""
    from sqlalchemy import or_
    root_file = ProjectFile.query.filter_by(share_token=token, parent_file_id=None).first_or_404()
    version_file = ProjectFile.query.filter(
        ProjectFile.id == file_id,
        or_(
            ProjectFile.id == root_file.id,
            ProjectFile.parent_file_id == root_file.id
        )
    ).first_or_404()
    return _send_file_safely(version_file, as_attachment=True)


@bp.route('/models/bulk-delete', methods=['POST'])
def model_bulk_delete():
    if not is_admin():
        abort(403)
    raw = request.form.get('ids', '')
    ids = [int(x) for x in raw.split(',') if x.strip().isdigit()]
    deleted = 0
    for root_id in ids:
        root_file = ProjectFile.query.get(root_id)
        if root_file and root_file.parent_file_id is None:
            _delete_model_chain(root_file)
            deleted += 1
    db.session.commit()
    flash(translate('models_bulk_deleted').format(n=deleted), 'success')
    return redirect(url_for('models.models_index'))


@bp.route('/models/bulk-move', methods=['POST'])
def model_bulk_move():
    if not is_admin():
        abort(403)
    raw = request.form.get('ids', '')
    ids = [int(x) for x in raw.split(',') if x.strip().isdigit()]
    project_id = request.form.get('project_id', type=int) or None
    if project_id:
        _check_project_access(project_id)
    moved = 0
    for root_id in ids:
        root_file = ProjectFile.query.get(root_id)
        if root_file and root_file.parent_file_id is None:
            root_file.project_id = project_id
            moved += 1
    db.session.commit()
    flash(translate('models_bulk_moved').format(n=moved), 'success')
    return redirect(url_for('models.models_index'))


def register(app):
    app.register_blueprint(bp)
