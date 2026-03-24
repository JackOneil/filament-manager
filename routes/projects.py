import os
from datetime import datetime
from flask import render_template, request, redirect, url_for, send_from_directory, flash
from werkzeug.utils import secure_filename
from sqlalchemy.orm import joinedload
from database import db
from models import Project, ProjectFile, ProjectLink, ProjectFilament, Filament

def register(app):
    UPLOAD_FOLDER = os.path.join(os.path.abspath(os.path.dirname(__file__)), '..', 'data', 'uploads')
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
        project = db.get_or_404(Project, id)
        filaments = Filament.query.all()
        
        return render_template('project_detail.html', project=project, all_filaments=filaments)

    @app.route('/projects/<int:id>/edit', methods=['GET', 'POST'])
    def project_edit(id):
        project = db.get_or_404(Project, id)
        if request.method == 'POST':
            project.name = request.form.get('name', '').strip()
            project.description = request.form.get('description', '').strip()
            project.client_name = request.form.get('client_name', '').strip()
            due_date_str = request.form.get('due_date', '').strip()
            project.estimated_print_time = request.form.get('estimated_print_time', 0, type=int)

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
        for file in files:
            if file.filename == '':
                continue

            filename = secure_filename(file.filename)
            filepath = os.path.join(UPLOAD_FOLDER, f"{project.id}_{filename}")
            file.save(filepath)

            pf = ProjectFile(project_id=project.id, filename=filename, filepath=filepath)
            db.session.add(pf)
        
        db.session.commit()
        return redirect(url_for('project_detail', id=id))

    @app.route('/projects/<int:id>/download/<int:file_id>')
    def project_download_file(id, file_id):
        pf = db.get_or_404(ProjectFile, file_id)
        if pf.project_id != id:
            return "Unauthorized", 401
        directory = os.path.dirname(pf.filepath)
        filename = os.path.basename(pf.filepath)
        return send_from_directory(directory, filename, as_attachment=True, download_name=pf.filename)

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
        from utils import fetch_link_metadata
        project = db.get_or_404(Project, id)
        url = request.form.get('url', '').strip()
        name = request.form.get('name', '').strip()
        if url:
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
            if pf.is_used:
                # We optionally could refund the filament, but for simplicity we just restrict deleting used filaments 
                # or we just allow it. Let's just allow it without refunding automatically for safety, or actually we shouldn't allow deleting used.
                if pf.is_used:
                    return redirect(url_for('project_detail', id=id))
            db.session.delete(pf)
            db.session.commit()
        return redirect(url_for('project_detail', id=id))

    @app.route('/projects/<int:id>/status', methods=['POST'])
    def project_status(id):
        project = db.get_or_404(Project, id)
        new_status = request.form.get('status', project.status)
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
