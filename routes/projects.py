import os
import uuid
import math
from types import SimpleNamespace
from datetime import datetime
from flask import render_template, request, redirect, url_for, send_from_directory, flash
from werkzeug.utils import secure_filename
from sqlalchemy.orm import joinedload
from database import db
from models import AppSetting, BambuJobMaterial, BambuPrintJob, MovementHistory, Project, ProjectFile, ProjectLink, ProjectFilament, ProjectQuote, PrusaPrintJob, PrusaPrinter, Filament
from utils import build_project_metrics, format_tags


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


def _project_detail_redirect(project_id, tab='overview', **extra_params):
    params = {'id': project_id, 'tab': tab}
    params.update(extra_params)
    return redirect(url_for('project_detail', **params))


def _job_timestamp(job):
    return job.started_at or job.finished_at or getattr(job, 'synced_at', None) or datetime.min


def _job_cost_parts(job, setting):
    kwh_price = setting.kwh_price if setting else 5.0
    printer_power = setting.printer_power if setting else 150
    energy_cost = ((job.cost_time or 0) / 3600.0) * (printer_power / 1000.0) * kwh_price
    material_cost = 0.0
    weight_grams = float(job.weight_grams or 0.0)

    if isinstance(job, BambuPrintJob) and getattr(job, 'materials', None):
        slot_weight = 0.0
        slot_cost = 0.0
        for slot in job.materials:
            slot_weight += float(slot.weight_grams or 0.0)
            if slot.filament and slot.filament.weight_total > 0 and slot.weight_grams:
                slot_cost += (slot.filament.price / slot.filament.weight_total) * slot.weight_grams
        if slot_weight > 0:
            weight_grams = slot_weight
        if slot_cost > 0:
            material_cost = slot_cost

    if material_cost == 0.0 and job.filament and job.filament.weight_total > 0 and weight_grams > 0:
        material_cost = (job.filament.price / job.filament.weight_total) * weight_grams

    return round(weight_grams, 1), round(material_cost, 2), round(energy_cost, 2)


def _build_project_job_feed(project, setting, show_bambu_jobs, show_prusa_jobs):
    items = []

    if show_bambu_jobs:
        for job in getattr(project, 'bambu_jobs', []) or []:
            weight_grams, material_cost, energy_cost = _job_cost_parts(job, setting)
            items.append({
                'source': 'bambu',
                'title': job.model_name or job.external_id or f'Job #{job.id}',
                'printer_name': job.printer_name,
                'status': job.status,
                'timestamp': _job_timestamp(job),
                'weight_grams': weight_grams or None,
                'cost_time': job.cost_time or 0,
                'material_cost': material_cost,
                'energy_cost': energy_cost,
                'total_cost': round(material_cost + energy_cost, 2),
                'filament_name': job.filament.name if job.filament else None,
                'material_slots': len([slot for slot in getattr(job, 'materials', []) or [] if slot.weight_grams]),
                'deducted': bool(job.deducted),
                'detail_url': url_for('bambu_jobs'),
                'unmapped': (
                    job.project_id is None
                    or job.filament_id is None
                    or any(slot.filament_id is None for slot in getattr(job, 'materials', []) or [])
                ),
            })

    if show_prusa_jobs:
        for job in getattr(project, 'prusa_jobs', []) or []:
            weight_grams, material_cost, energy_cost = _job_cost_parts(job, setting)
            items.append({
                'source': 'prusa',
                'title': job.display_name or job.file_name or f'Job #{job.id}',
                'printer_name': job.printer.name if job.printer else job.printer_name,
                'status': job.status,
                'timestamp': _job_timestamp(job),
                'weight_grams': weight_grams or None,
                'cost_time': job.cost_time or 0,
                'material_cost': material_cost,
                'energy_cost': energy_cost,
                'total_cost': round(material_cost + energy_cost, 2),
                'filament_name': job.filament.name if job.filament else None,
                'material_slots': 0,
                'deducted': bool(job.deducted),
                'detail_url': url_for('prusa_jobs'),
                'unmapped': (job.project_id is None or job.filament_id is None),
            })

    items.sort(key=lambda item: item['timestamp'] or datetime.min, reverse=True)
    return items


def register(app):
    UPLOAD_FOLDER = app.config.get(
        'PROJECT_UPLOAD_FOLDER',
        os.path.join(os.path.abspath(os.path.dirname(__file__)), '..', 'data', 'uploads')
    )
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)

    @app.route('/projects')
    def projects_index():
        from models import AppSetting

        sort_by = request.args.get('sort_by', 'due_date')
        page = request.args.get('page', 1, type=int)
        setting = AppSetting.query.first()
        per_page = setting.items_per_page if setting and setting.items_per_page in [12, 24, 48, 96] else 12
        if sort_by == 'name':
            order_expr = [Project.name.asc()]
        elif sort_by == 'due_date':
            order_expr = [db.case((Project.due_date == None, 1), else_=0), Project.due_date.asc()]
        elif sort_by == 'client':
            order_expr = [Project.client_name.asc()]
        elif sort_by == 'status':
            order_expr = [Project.status.asc()]
        elif sort_by == 'created':
            order_expr = [Project.created_at.desc()]
        else:
            order_expr = [Project.created_at.desc()]

        projects = db.paginate(
            Project.query.order_by(*order_expr),
            page=page,
            per_page=per_page,
            error_out=False,
        )
        all_projects = Project.query.options(
            joinedload(Project.filaments).joinedload(ProjectFilament.filament),
            joinedload(Project.quotes),
            joinedload(Project.bambu_jobs).joinedload(BambuPrintJob.filament),
            joinedload(Project.bambu_jobs).joinedload(BambuPrintJob.materials),
            joinedload(Project.prusa_jobs).joinedload(PrusaPrintJob.filament),
        ).order_by(
            db.case((Project.due_date == None, 1), else_=0),
            Project.due_date.asc(),
            Project.created_at.desc(),
        ).all()
        project_metrics = {project.id: build_project_metrics(project, setting) for project in all_projects}
        projects_by_status = {
            'NEW': [project for project in all_projects if project.status == 'NEW'],
            'PRINTING': [project for project in all_projects if project.status == 'PRINTING'],
            'DONE': [project for project in all_projects if project.status == 'DONE'],
        }
        upcoming_due = [project for project in all_projects if project.due_date][:8]
        return render_template(
            'projects_index.html',
            projects=projects,
            sort_by=sort_by,
            per_page=per_page,
            project_metrics=project_metrics,
            projects_by_status=projects_by_status,
            upcoming_due=upcoming_due,
            now=datetime.utcnow(),
        )

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
                estimated_print_time=estimated_print_time,
                tag_text=format_tags(request.form.get('tag_text', '')),
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
            joinedload(Project.quotes),
            joinedload(Project.movements),
            joinedload(Project.filaments)
            .joinedload(ProjectFilament.filament)
            .joinedload(Filament.color),
            joinedload(Project.filaments)
            .joinedload(ProjectFilament.filament)
            .joinedload(Filament.brand),
            joinedload(Project.filaments)
            .joinedload(ProjectFilament.filament)
            .joinedload(Filament.material),
            joinedload(Project.bambu_jobs)
            .joinedload(BambuPrintJob.filament)
            .joinedload(Filament.color),
            joinedload(Project.bambu_jobs)
            .joinedload(BambuPrintJob.filament)
            .joinedload(Filament.brand),
            joinedload(Project.bambu_jobs)
            .joinedload(BambuPrintJob.filament)
            .joinedload(Filament.material),
            joinedload(Project.bambu_jobs)
            .joinedload(BambuPrintJob.materials)
            .joinedload(BambuJobMaterial.filament)
            .joinedload(Filament.color),
            joinedload(Project.bambu_jobs)
            .joinedload(BambuPrintJob.materials)
            .joinedload(BambuJobMaterial.filament)
            .joinedload(Filament.brand),
            joinedload(Project.bambu_jobs)
            .joinedload(BambuPrintJob.materials),
            joinedload(Project.prusa_jobs)
            .joinedload(PrusaPrintJob.printer),
            joinedload(Project.prusa_jobs)
            .joinedload(PrusaPrintJob.filament)
            .joinedload(Filament.color),
            joinedload(Project.prusa_jobs)
            .joinedload(PrusaPrintJob.filament)
            .joinedload(Filament.brand),
            joinedload(Project.prusa_jobs)
            .joinedload(PrusaPrintJob.filament)
            .joinedload(Filament.material),
        ).filter(Project.id == id).first_or_404()
        filaments = Filament.query.order_by(Filament.name.asc()).all()
        setting = AppSetting.query.first()
        show_bambu_jobs = bool(setting and setting.bambu_token)
        show_prusa_jobs = PrusaPrinter.query.filter_by(enabled=True).first() is not None
        active_tab = request.args.get('tab', 'overview')
        if active_tab not in {'overview', 'materials', 'files', 'jobs'}:
            active_tab = 'overview'
        project_metrics = build_project_metrics(project, setting)
        images = []
        model_files = []
        other_files = []
        for project_file in project.files:
            ext = _get_extension(project_file.filename)
            if ext in IMAGE_EXTENSIONS:
                images.append(project_file)
            elif ext in {'3mf', 'stl', 'obj', 'amf', 'step', 'stp', 'gcode', 'gc', 'bgcode'}:
                model_files.append(project_file)
            else:
                other_files.append(project_file)

        next_actions = []
        if project.due_date and project.due_date < datetime.utcnow() and project.status != 'DONE':
            next_actions.append('overdue')
        if not project.filaments:
            next_actions.append('plan_filaments')
        if project_metrics['has_quote'] is False:
            next_actions.append('create_quote')
        if any(not row.is_used for row in project.filaments):
            next_actions.append('consume_planned')
        if show_prusa_jobs and any(job.project_id is None or job.filament_id is None for job in getattr(project, 'prusa_jobs', [])):
            next_actions.append('map_prusa_jobs')
        if show_bambu_jobs and any(
            job.project_id is None or job.filament_id is None or any(slot.filament_id is None for slot in job.materials)
            for job in getattr(project, 'bambu_jobs', [])
        ):
            next_actions.append('map_bambu_jobs')
        activity_events = []
        for movement in sorted(project.movements, key=lambda item: item.created_at or datetime.min, reverse=True):
            activity_events.append({
                'created_at': movement.created_at,
                'label': movement.note or movement.action_type.replace('_', ' ').title(),
                'meta': f"{movement.weight:.1f} g · {movement.currency}",
                'kind': 'movement',
            })
        for quote in sorted(project.quotes, key=lambda item: item.created_at or datetime.min, reverse=True):
            activity_events.append({
                'created_at': quote.created_at,
                'label': f'Quote saved: {quote.final_price:.2f} {quote.currency}',
                'meta': f'{quote.filament_name} · {quote.weight} g',
                'kind': 'quote',
            })
        for project_file in sorted(project.files, key=lambda item: item.uploaded_at or datetime.min, reverse=True):
            activity_events.append({
                'created_at': project_file.uploaded_at,
                'label': f'File uploaded: {project_file.filename}',
                'meta': _get_extension(project_file.filename).upper() or 'FILE',
                'kind': 'file',
            })
        activity_events.sort(key=lambda item: item['created_at'] or datetime.min, reverse=True)

        job_feed = _build_project_job_feed(project, setting, show_bambu_jobs, show_prusa_jobs)
        jobs_page = request.args.get('jobs_page', 1, type=int)
        jobs_per_page = 8
        jobs_total = len(job_feed)
        jobs_pages = max(1, math.ceil(jobs_total / jobs_per_page)) if jobs_total else 1
        jobs_page = min(max(jobs_page, 1), jobs_pages)
        start = (jobs_page - 1) * jobs_per_page
        job_feed_page = job_feed[start:start + jobs_per_page]
        jobs_pagination = SimpleNamespace(
            page=jobs_page,
            pages=jobs_pages,
            total=jobs_total,
            has_prev=jobs_page > 1,
            has_next=jobs_page < jobs_pages,
            prev_num=jobs_page - 1 if jobs_page > 1 else 1,
            next_num=jobs_page + 1 if jobs_page < jobs_pages else jobs_pages,
        )
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
        return render_template(
            'project_detail.html',
            project=project,
            all_filaments=filaments,
            filaments_json=filaments_json,
            setting=setting,
            project_tags=format_tags(project.tag_text),
            project_metrics=project_metrics,
            images=images,
            model_files=model_files,
            other_files=other_files,
            next_actions=next_actions,
            activity_events=activity_events[:15],
            active_tab=active_tab,
            show_bambu_jobs=show_bambu_jobs,
            show_prusa_jobs=show_prusa_jobs,
            job_feed=job_feed_page,
            jobs_pagination=jobs_pagination,
        )

    @app.route('/projects/<int:id>/edit', methods=['GET', 'POST'])
    def project_edit(id):
        project = db.get_or_404(Project, id)
        if request.method == 'POST':
            project.name = request.form.get('name', '').strip()
            project.description = request.form.get('description', '').strip()
            project.client_name = request.form.get('client_name', '').strip()
            project.tag_text = format_tags(request.form.get('tag_text', ''))
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

        return render_template('project_edit.html', project=project, project_tags=format_tags(project.tag_text))

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
            return _project_detail_redirect(id, 'files')
        
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
        return _project_detail_redirect(id, 'files')

    @app.route('/projects/<int:id>/download/<int:file_id>')
    def project_download_file(id, file_id):
        pf = db.get_or_404(ProjectFile, file_id)
        if pf.project_id != id:
            return "Unauthorized", 401
        # Guard against path traversal: ensure the stored path is inside UPLOAD_FOLDER
        real_path = os.path.realpath(pf.filepath)
        real_folder = os.path.realpath(UPLOAD_FOLDER)
        if not real_path.startswith(real_folder + os.sep):
            return "Forbidden", 403
        directory = os.path.dirname(pf.filepath)
        filename = os.path.basename(pf.filepath)
        return send_from_directory(directory, filename, as_attachment=True, download_name=pf.filename)

    @app.route('/projects/<int:id>/view_file/<int:file_id>/<filename>')
    def project_view_file(id, file_id, filename):
        pf = db.get_or_404(ProjectFile, file_id)
        if pf.project_id != id:
            return "Unauthorized", 401
        real_path = os.path.realpath(pf.filepath)
        real_folder = os.path.realpath(UPLOAD_FOLDER)
        if not real_path.startswith(real_folder + os.sep):
            return "Forbidden", 403
        directory = os.path.dirname(pf.filepath)
        filename = os.path.basename(pf.filepath)
        return send_from_directory(directory, filename, as_attachment=False)

    @app.route('/projects/<int:id>/image/<int:file_id>')
    def project_image_file(id, file_id):
        pf = db.get_or_404(ProjectFile, file_id)
        if pf.project_id != id or _get_extension(pf.filename) not in IMAGE_EXTENSIONS:
            return "Unauthorized", 401
        # Guard against path traversal
        real_path = os.path.realpath(pf.filepath)
        real_folder = os.path.realpath(UPLOAD_FOLDER)
        if not real_path.startswith(real_folder + os.sep):
            return "Forbidden", 403
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
        return _project_detail_redirect(id, 'files')

    @app.route('/projects/<int:id>/add_link', methods=['POST'])
    def project_add_link(id):
        from utils import fetch_link_metadata, is_safe_external_url
        project = db.get_or_404(Project, id)
        url = request.form.get('url', '').strip()
        name = request.form.get('name', '').strip()
        if url:
            if not is_safe_external_url(url):
                flash('project_link_invalid', 'error')
                return _project_detail_redirect(id, 'files')
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
        return _project_detail_redirect(id, 'files')

    @app.route('/projects/<int:id>/delete_link/<int:link_id>', methods=['POST'])
    def project_delete_link(id, link_id):
        link = db.get_or_404(ProjectLink, link_id)
        if link.project_id == id:
            db.session.delete(link)
            db.session.commit()
        return _project_detail_redirect(id, 'files')

    @app.route('/projects/<int:id>/refresh_link/<int:link_id>', methods=['POST'])
    def project_refresh_link(id, link_id):
        from utils import fetch_link_metadata, is_safe_external_url
        link = db.get_or_404(ProjectLink, link_id)
        if link.project_id == id and is_safe_external_url(link.url):
            meta = fetch_link_metadata(link.url)
            link.og_title = meta['og_title']
            link.og_image = meta['og_image']
            link.og_description = meta['og_description']
            link.domain = meta['domain']
            db.session.commit()
        return _project_detail_redirect(id, 'files')

    @app.route('/projects/<int:id>/add_filament', methods=['POST'])
    def project_add_filament(id):
        project = db.get_or_404(Project, id)
        filament_id = request.form.get('filament_id', type=int)
        estimated_weight = request.form.get('estimated_weight', 0.0, type=float)
        if filament_id and estimated_weight > 0:
            pf = ProjectFilament(project_id=project.id, filament_id=filament_id, estimated_weight=estimated_weight)
            db.session.add(pf)
            db.session.commit()
        return _project_detail_redirect(id, 'materials')

    @app.route('/projects/<int:id>/remove_filament/<int:pf_id>', methods=['POST'])
    def project_remove_filament(id, pf_id):
        pf = db.get_or_404(ProjectFilament, pf_id)
        if pf.project_id == id:
            db.session.delete(pf)
            db.session.commit()
        return _project_detail_redirect(id, 'materials')

    @app.route('/projects/<int:id>/update_filament/<int:pf_id>', methods=['POST'])
    def project_update_filament(id, pf_id):
        pf = db.get_or_404(ProjectFilament, pf_id)
        if pf.project_id == id:
            new_weight = request.form.get('estimated_weight', 0.0, type=float)
            if new_weight > 0:
                pf.estimated_weight = new_weight
                db.session.commit()
        return _project_detail_redirect(id, 'materials')

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
            log_movement(
                filament,
                'remove',
                actual_amount,
                project_id=pf.project_id,
                note=f'Project consume: {pf.project.name if pf.project else ""}'.strip(),
            )
            db.session.commit()
            
        return _project_detail_redirect(id, 'materials')
