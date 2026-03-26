import os
import uuid
from datetime import datetime
from flask import render_template, request, redirect, url_for, send_from_directory, flash
from werkzeug.utils import secure_filename
from sqlalchemy.orm import joinedload
from database import db
from models import Project, ProjectFile, ProjectLink, ProjectFilament, Filament


ALLOWED_PROJECT_FILE_EXTENSIONS = {
    '3mf', 'stl', 'obj', 'amf', 'step', 'stp', 'gcode', 'gc', 'bgcode',
    'jpg', 'jpeg', 'png', 'gif', 'webp'
}
IMAGE_EXTENSIONS = {'jpg', 'jpeg', 'png', 'gif', 'webp'}
ALLOWED_PROJECT_STATUSES = {'NEW', 'PRINTING', 'DONE'}


def _get_extension(filename):
    return filename.rsplit('.', 1)[1].lower() if '.' in filename else ''


def _is_allowed_project_file(filename):
    return _get_extension(filename) in ALLOWED_PROJECT_FILE_EXTENSIONS


def _build_storage_name(project_id, filename):
    safe_name = secure_filename(filename)
    unique_id = uuid.uuid4().hex[:12]
    return f"{project_id}_{unique_id}_{safe_name}"


def register(app):
    UPLOAD_FOLDER = app.config.get(
        'PROJECT_UPLOAD_FOLDER',
        os.path.join(os.path.abspath(os.path.dirname(__file__)), '..', 'data', 'uploads')
    )
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)

    @app.route('/projects')
    def projects_index():
        sort_by = request.args.get('sort_by', 'due_date')
        if sort_by == 'due_date':
            order_expr = [db.case((Project.due_date == None, 1), else_=0), Project.due_date.asc()]
        elif sort_by == 'client':
            order_expr = [Project.client_name.asc()]
        elif sort_by == 'status':
            order_expr = [Project.status.asc()]
        elif sort_by == 'created':
            order_expr = [Project.created_at.desc()]
        else:
            order_expr = [Project.created_at.desc()]

        projects = Project.query.order_by(*order_expr).all()
        return render_template('projects_index.html', projects=projects, sort_by=sort_by)

    @app.route('/projects/create', methods=['GET', 'POST'])
    def project_create():
        if request.method == 'POST':
            name = request.form.get('name', '').strip()
            description = request.form.get('description', '').strip()
            client_name = request.form.get('client_name', '').strip()
            due_date_str = request.form.get('due_date', '').strip()
            estimated_print_time = request.form.get('estimated_print_time', 0, type=int)
            hours = request.form.get('print_hours', 0, type=int)
            minutes = request.form.get('print_minutes', 0, type=int)
            if hours > 0 or minutes > 0:
                estimated_print_time = hours * 60 + minutes

            due_date = None
            if due_date_str:
                due_date = datetime.strptime(due_date_str, '%Y-%m-%d')

            new_project = Project(
                name=name,
                description=description,
                client_name=client_name,
                due_date=due_date,
                estimated_print_time=estimated_print_time
            )
            db.session.add(new_project)
            db.session.commit()
            app.logger.debug(f"Created new project: {name}")
            return redirect(url_for('project_detail', id=new_project.id))

        return render_template('project_create.html')

    @app.route('/projects/<int:id>', methods=['GET'])
    def project_detail(id):
        project = Project.query.options(
            joinedload(Project.files),
            joinedload(Project.links),
            joinedload(Project.filaments)
            .joinedload(ProjectFilament.filament)
            .joinedload(Filament.color),
        ).filter(Project.id == id).first_or_404()
        filaments = Filament.query.order_by(Filament.name.asc()).all()
        from models import AppSetting
        setting = AppSetting.query.first()
        filaments_json = [
            {
                'id': f.id,
                'name': f.name,
                'brand': f.brand.name if f.brand else '',
                'material': f.material.name if f.material else '',
                'color_hex': f.color.hex_value if f.color else '#cccccc',
                'remaining': int(f.weight_remaining),
            }
            for f in filaments
        ]
        return render_template('project_detail.html', project=project, all_filaments=filaments, filaments_json=filaments_json, setting=setting)

    @app.route('/projects/<int:id>/edit', methods=['GET', 'POST'])
    def project_edit(id):
        project = db.get_or_404(Project, id)
        if request.method == 'POST':
            project.name = request.form.get('name', '').strip()
            project.description = request.form.get('description', '').strip()
            project.client_name = request.form.get('client_name', '').strip()
            due_date_str = request.form.get('due_date', '').strip()
            project.estimated_print_time = request.form.get('estimated_print_time', 0, type=int)
            hours = request.form.get('print_hours', 0, type=int)
            minutes = request.form.get('print_minutes', 0, type=int)
            if hours > 0 or minutes > 0:
                project.estimated_print_time = hours * 60 + minutes

            if due_date_str:
                project.due_date = datetime.strptime(due_date_str, '%Y-%m-%d')
            else:
                project.due_date = None

            db.session.commit()
            return redirect(url_for('project_detail', id=project.id))

        return render_template('project_edit.html', project=project)

    @app.route('/projects/<int:id>/delete', methods=['POST'])
    def project_delete(id):
        project = db.get_or_404(Project, id)
        for f in project.files:
            try:
                os.remove(f.filepath)
            except OSError:
                pass
        db.session.delete(project)
        db.session.commit()
        return redirect(url_for('projects_index'))

    @app.route('/projects/<int:id>/upload', methods=['POST'])
    def project_upload_file(id):
        project = db.get_or_404(Project, id)
        if 'file' not in request.files:
            return redirect(url_for('project_detail', id=id))
        
        files = request.files.getlist('file')
        uploaded_any = False
        for file in files:
            if file.filename == '':
                continue

            if not _is_allowed_project_file(file.filename):
                flash('project_file_type_not_allowed', 'error')
                continue

            original_filename = secure_filename(file.filename)
            if not original_filename:
                flash('project_file_type_not_allowed', 'error')
                continue

            stored_filename = _build_storage_name(project.id, original_filename)
            filepath = os.path.join(UPLOAD_FOLDER, stored_filename)
            file.save(filepath)

            pf = ProjectFile(project_id=project.id, filename=original_filename, filepath=filepath)
            db.session.add(pf)
            uploaded_any = True
        
        if uploaded_any:
            db.session.commit()
        else:
            db.session.rollback()
        return redirect(url_for('project_detail', id=id))

    @app.route('/projects/<int:id>/download/<int:file_id>')
    def project_download_file(id, file_id):
        pf = db.get_or_404(ProjectFile, file_id)
        if pf.project_id != id:
            return "Unauthorized", 401
        directory = os.path.dirname(pf.filepath)
        filename = os.path.basename(pf.filepath)
        return send_from_directory(directory, filename, as_attachment=True, download_name=pf.filename)

    @app.route('/projects/<int:id>/image/<int:file_id>')
    def project_image_file(id, file_id):
        pf = db.get_or_404(ProjectFile, file_id)
        if pf.project_id != id or _get_extension(pf.filename) not in IMAGE_EXTENSIONS:
            return "Unauthorized", 401
        directory = os.path.dirname(pf.filepath)
        filename = os.path.basename(pf.filepath)
        return send_from_directory(directory, filename, as_attachment=False)

    @app.route('/projects/<int:id>/delete_file/<int:file_id>', methods=['POST'])
    def project_delete_file(id, file_id):
        pf = db.get_or_404(ProjectFile, file_id)
        if pf.project_id == id:
            try:
                os.remove(pf.filepath)
            except OSError:
                pass
            db.session.delete(pf)
            db.session.commit()
        return redirect(url_for('project_detail', id=id))

    @app.route('/projects/<int:id>/add_link', methods=['POST'])
    def project_add_link(id):
        from utils import fetch_link_metadata, is_safe_external_url
        project = db.get_or_404(Project, id)
        url = request.form.get('url', '').strip()
        name = request.form.get('name', '').strip()
        if url:
            if not is_safe_external_url(url):
                flash('project_link_invalid', 'error')
                return redirect(url_for('project_detail', id=id))
            meta = fetch_link_metadata(url)
            link = ProjectLink(
                project_id=project.id, 
                url=url, 
                name=name,
                og_title=meta['og_title'],
                og_image=meta['og_image'],
                og_description=meta['og_description'],
                domain=meta['domain']
            )
            db.session.add(link)
            db.session.commit()
        return redirect(url_for('project_detail', id=id))

    @app.route('/projects/<int:id>/delete_link/<int:link_id>', methods=['POST'])
    def project_delete_link(id, link_id):
        link = db.get_or_404(ProjectLink, link_id)
        if link.project_id == id:
            db.session.delete(link)
            db.session.commit()
        return redirect(url_for('project_detail', id=id))

    @app.route('/projects/<int:id>/add_filament', methods=['POST'])
    def project_add_filament(id):
        project = db.get_or_404(Project, id)
        filament_id = request.form.get('filament_id', type=int)
        estimated_weight = request.form.get('estimated_weight', 0.0, type=float)
        if filament_id and estimated_weight > 0:
            pf = ProjectFilament(project_id=project.id, filament_id=filament_id, estimated_weight=estimated_weight)
            db.session.add(pf)
            db.session.commit()
        return redirect(url_for('project_detail', id=id))

    @app.route('/projects/<int:id>/remove_filament/<int:pf_id>', methods=['POST'])
    def project_remove_filament(id, pf_id):
        pf = db.get_or_404(ProjectFilament, pf_id)
        if pf.project_id == id:
            db.session.delete(pf)
            db.session.commit()
        return redirect(url_for('project_detail', id=id))

    @app.route('/projects/<int:id>/update_filament/<int:pf_id>', methods=['POST'])
    def project_update_filament(id, pf_id):
        pf = db.get_or_404(ProjectFilament, pf_id)
        if pf.project_id == id:
            new_weight = request.form.get('estimated_weight', 0.0, type=float)
            if new_weight > 0:
                pf.estimated_weight = new_weight
                db.session.commit()
        return redirect(url_for('project_detail', id=id))

    @app.route('/projects/<int:id>/status', methods=['POST'])
    def project_status(id):
        project = db.get_or_404(Project, id)
        new_status = request.form.get('status', project.status)
        if new_status not in ALLOWED_PROJECT_STATUSES:
            flash('project_status_invalid', 'error')
            return redirect(url_for('project_detail', id=id))
        project.status = new_status
        db.session.commit()
        return redirect(url_for('project_detail', id=id))

    @app.route('/projects/<int:id>/consume/<int:pf_id>', methods=['POST'])
    def project_consume_filament(id, pf_id):
        from utils import log_movement
        import math
        pf = db.get_or_404(ProjectFilament, pf_id)
        if pf.project_id == id and not pf.is_used:
            filament = pf.filament
            amount = pf.estimated_weight
            
            old_weight = filament.weight_remaining
            filament.weight_remaining -= amount
            if filament.weight_remaining < 0:
                filament.weight_remaining = 0
            actual_amount = old_weight - filament.weight_remaining

            if filament.weight_total > 0:
                expected_quantity = math.ceil(filament.weight_remaining / filament.weight_total)
                if expected_quantity < filament.quantity:
                    filament.quantity = expected_quantity
                    
            pf.is_used = True
            log_movement(filament, 'remove', actual_amount)
            db.session.commit()
            
        return redirect(url_for('project_detail', id=id))
