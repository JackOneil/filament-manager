import math
import os
import uuid
from datetime import date, datetime
from types import SimpleNamespace

from flask import abort, current_app, flash, jsonify, redirect, render_template, request, send_from_directory, url_for, Blueprint
from markupsafe import Markup
from sqlalchemy.orm import joinedload, selectinload
from werkzeug.utils import secure_filename

from auth import create_notification, get_current_user, is_admin
from database import db
from models import (
    AppSetting,
    BambuJobMaterial,
    BambuPrintJob,
    BambuPrinter,
    Filament,
    Project,
    ProjectComment,
    ProjectCommentReaction,
    ProjectFile,
    ProjectFilament,
    ProjectLink,
    ProjectPrintItem,
    ProjectQuote,
    ProjectTemplate,
    ProjectTodo,
    PrusaPrintJob,
    PrusaPrinter,
    User,
)
from utils import build_project_metrics, clean_bambu_title, escape_like, format_tags, parse_tags, render_markdown, safe_commit, translate, utc_now, _toggle_markdown_checkbox


from routes.projects_helpers import (
    ALLOWED_PROJECT_FILE_EXTENSIONS,
    IMAGE_EXTENSIONS,
    ALLOWED_PROJECT_STATUSES,
    KANBAN_STATUSES,
    _get_extension,
    _is_allowed_project_file,
    _build_storage_name,
    _project_detail_redirect,
    _job_timestamp,
    _job_cost_parts,
    _job_slots,
    _job_colors,
    _build_project_job_feed,
    _project_scope,
    _project_or_404,
    _project_write_allowed,
    _comment_edit_allowed,
    _comment_delete_allowed,
    _require_project_admin,
    _project_owner_choices,
    _resolve_project_owner_from_form,
    _notify_project_created,
    _notify_project_status,
    _notify_project_comment,
    _get_project_files_by_category,
    _build_project_next_actions,
    _build_project_activity_events,
    _build_project_comments,
    _paginate_jobs,
    _schedule_link_preview_refresh,
)

def register(app):
    bp = Blueprint('projects', __name__)
    upload_folder = app.config.get(
        'PROJECT_UPLOAD_FOLDER',
        os.path.join(os.path.abspath(os.path.dirname(__file__)), '..', 'data', 'uploads'),
    )
    os.makedirs(upload_folder, exist_ok=True)

    @bp.route('/projects')
    def projects_index():
        sort_by = request.args.get('sort_by', 'due_date')
        page = request.args.get('page', 1, type=int)
        kanban_per_page = 5
        setting = AppSetting.query.first()
        per_page = setting.items_per_page if setting and setting.items_per_page in [12, 24, 48, 96] else 12
        base_query = _project_scope()
        client_filter = request.args.get('client', '').strip()
        name_filter = request.args.get('name', '').strip()
        tag_filter = request.args.get('tag', '').strip()
        fulltext_filter = request.args.get('fulltext', '').strip()
        ajax_mode = request.args.get('ajax') == '1'
        hide_done = request.args.get('hide_done') == '1'

        if fulltext_filter:
            ft = f'%{escape_like(fulltext_filter)}%'
            base_query = base_query.filter(
                db.or_(
                    Project.name.ilike(ft),
                    Project.client_name.ilike(ft),
                    Project.tag_text.ilike(ft),
                )
            )
        if client_filter:
            base_query = base_query.filter(Project.client_name.ilike(f'%{escape_like(client_filter)}%'))
        if name_filter:
            base_query = base_query.filter(Project.name.ilike(f'%{escape_like(name_filter)}%'))
        if tag_filter:
            base_query = base_query.filter(Project.tag_text.ilike(f'%{escape_like(tag_filter)}%'))
        if hide_done:
            base_query = base_query.filter(Project.status != 'DONE')

        if sort_by == 'name':
            order_expr = [Project.name.asc()]
        elif sort_by == 'due_date':
            order_expr = [db.case((Project.due_date == None, 1), else_=0), Project.due_date.asc()]
        elif sort_by == 'client':
            order_expr = [Project.client_name.asc()]
        elif sort_by == 'status':
            order_expr = [Project.status.asc(), Project.created_at.desc()]
        else:
            order_expr = [Project.created_at.desc()]

        kanban_order = [
            db.case((Project.due_date == None, 1), else_=0),
            Project.due_date.asc(),
            Project.created_at.desc(),
        ]

        projects = db.paginate(base_query.order_by(*order_expr).statement, page=page, per_page=per_page, error_out=False)

        status_page_fields = {
            'PENDING_APPROVAL': 'kanban_pending_page',
            'APPROVED': 'kanban_approved_page',
            'PRINTING': 'kanban_printing_page',
            'DONE': 'kanban_done_page',
            'REJECTED': 'kanban_rejected_page',
        }

        def _projects_index_url(**overrides):
            params = {
                'sort_by': sort_by,
                'page': page,
                'owner_id': request.args.get('owner_id', type=int),
                'fulltext': fulltext_filter or None,
                'client': client_filter or None,
                'name': name_filter or None,
                'tag': tag_filter or None,
                'hide_done': '1' if hide_done else None,
                **{field: request.args.get(field, 1, type=int) for field in status_page_fields.values()},
            }
            params.update(overrides)
            return url_for('projects_index', **{k: v for k, v in params.items() if v})

        projects_by_status = {}
        for status, field_name in status_page_fields.items():
            status_page = max(request.args.get(field_name, 1, type=int), 1)
            pag = db.paginate(
                base_query.filter(Project.status == status).order_by(*kanban_order).statement,
                page=status_page,
                per_page=kanban_per_page,
                error_out=False,
            )
            page_list = list(pag.iter_pages(left_edge=1, right_edge=1, left_current=2, right_current=2))
            page_urls = {value: _projects_index_url(**{field_name: value}) for value in page_list if value}
            projects_by_status[status] = {
                'items': pag.items,
                'total': pag.total,
                'pagination': SimpleNamespace(
                    page=pag.page,
                    pages=pag.pages,
                    total=pag.total,
                    has_prev=pag.has_prev,
                    has_next=pag.has_next,
                    prev_num=pag.prev_num,
                    next_num=pag.next_num,
                    prev_url=_projects_index_url(**{field_name: pag.prev_num}) if pag.has_prev else '#',
                    next_url=_projects_index_url(**{field_name: pag.next_num}) if pag.has_next else '#',
                    page_list=page_list,
                    page_urls=page_urls,
                ),
            }

        visible_ids = set(project.id for project in projects.items)
        for board in projects_by_status.values():
            visible_ids.update(project.id for project in board['items'])

        if visible_ids:
            visible_projects = (
                _project_scope()
                .options(
                    selectinload(Project.filaments).joinedload(ProjectFilament.filament),
                    selectinload(Project.quotes),
                    selectinload(Project.bambu_jobs).selectinload(BambuPrintJob.materials),
                    selectinload(Project.bambu_jobs).joinedload(BambuPrintJob.filament),
                    selectinload(Project.prusa_jobs).joinedload(PrusaPrintJob.filament),
                )
                .filter(Project.id.in_(visible_ids))
                .all()
            )
            bambu_powers = {p.device_id: p.power_draw_watts for p in BambuPrinter.query.all() if p.device_id}
            prusa_powers = {p.id: p.power_draw_watts for p in PrusaPrinter.query.all()}
            project_metrics = {project.id: build_project_metrics(project, setting, bambu_powers=bambu_powers, prusa_powers=prusa_powers) for project in visible_projects}
        else:
            project_metrics = {}

        upcoming_due = (
            base_query
            .filter(Project.due_date.is_not(None), Project.status != 'DONE')
            .order_by(Project.due_date.asc())
            .limit(4)
            .all()
        )

        project_page_urls = {
            value: _projects_index_url(page=value)
            for value in projects.iter_pages(left_edge=1, right_edge=1, left_current=2, right_current=2)
            if value
        }
        
        context = dict(
            projects=projects,
            sort_by=sort_by,
            client_filter=client_filter,
            name_filter=name_filter,
            tag_filter=tag_filter,
            fulltext_filter=fulltext_filter,
            hide_done=hide_done,
            per_page=per_page,
            project_metrics=project_metrics,
            projects_by_status=projects_by_status,
            upcoming_due=upcoming_due,
            project_page_urls=project_page_urls,
            projects_prev_url=_projects_index_url(page=projects.prev_num) if projects.has_prev else '#',
            projects_next_url=_projects_index_url(page=projects.next_num) if projects.has_next else '#',
            projects_sort_urls={
                'name': _projects_index_url(sort_by='name', page=1),
                'due_date': _projects_index_url(sort_by='due_date', page=1),
                'status': _projects_index_url(sort_by='status', page=1),
            },
            projects_index_url=_projects_index_url,
            owner_choices=_project_owner_choices(),
            selected_owner_id=request.args.get('owner_id', type=int),
            now=utc_now(),
        )

        if ajax_mode:
            from flask import jsonify
            html = render_template('_projects_layout.html', **context)
            return jsonify({'html': html})
            
        client_options = [c[0] for c in _project_scope().with_entities(Project.client_name).distinct().filter(Project.client_name != None, Project.client_name != '').all()]
        tag_options = sorted({tag for (tag_text,) in _project_scope().with_entities(Project.tag_text).filter(Project.tag_text.isnot(None)).all() for tag in parse_tags(tag_text)}, key=str.lower)
        context['client_options'] = client_options
        context['tag_options'] = tag_options

        return render_template('projects_index.html', **context)

    @bp.route('/projects/create', methods=['GET', 'POST'])
    def project_create():
        user = get_current_user()
        if request.method == 'POST':
            name = request.form.get('name', '').strip()
            if not name:
                flash('project_name_required', 'error')
                return redirect(url_for('projects_index'))
            description = request.form.get('description', '').strip()
            client_name = user.name if user and not is_admin(user) else request.form.get('client_name', '').strip()
            client_email = request.form.get('client_email', '').strip()
            client_phone = request.form.get('client_phone', '').strip()
            due_date_str = request.form.get('due_date', '').strip()
            hours = request.form.get('print_hours', 0, type=int)
            minutes = request.form.get('print_minutes', 0, type=int)
            estimated_print_time = hours * 60 + minutes if hours > 0 or minutes > 0 else 0
            due_date = datetime.strptime(due_date_str, '%Y-%m-%d') if due_date_str else None
            if due_date and due_date.date() < utc_now().date():
                flash('project_due_date_past', 'warning')
            priority = request.form.get('priority', 'medium')
            if priority not in ('low', 'medium', 'high', 'urgent'):
                priority = 'medium'

            owner_user_id, owner_name = _resolve_project_owner_from_form(user)

            project = Project(
                name=name,
                description=description,
                client_name=client_name,
                client_email=client_email or None,
                client_phone=client_phone or None,
                due_date=due_date,
                estimated_print_time=estimated_print_time,
                priority=priority,
                tag_text=format_tags(request.form.get('tag_text', '')),
                owner_user_id=owner_user_id,
                owner_name=owner_name,
                created_by_user_id=user.id if user else None,
                status='APPROVED' if is_admin(user) else 'PENDING_APPROVAL',
            )
            db.session.add(project)
            db.session.flush()
            if not is_admin(user):
                _notify_project_created(project)
            safe_commit()
            return redirect(url_for('project_detail', id=project.id))

        # Query unmapped Bambu print jobs for naming suggestion
        unmapped_jobs = BambuPrintJob.query.filter_by(project_id=None).order_by(BambuPrintJob.started_at.desc()).limit(15).all()
        suggestions = []
        seen_names = set()
        for job in unmapped_jobs:
            if job.model_name:
                cleaned = clean_bambu_title(job.model_name)
                if cleaned and cleaned not in seen_names:
                    seen_names.add(cleaned)
                    suggestions.append(cleaned)

        return render_template(
            'project_create.html',
            is_admin_user=is_admin(user),
            default_client_name=user.name if user and not is_admin(user) else '',
            suggestions=suggestions,
            project_templates=ProjectTemplate.query.order_by(ProjectTemplate.created_at.desc()).all(),
            prefill_template=None,
        )


    @bp.route('/projects/<int:id>', methods=['GET'])
    def project_detail(id):
        _project_or_404(id)
        project = (
            Project.query
            .options(
                joinedload(Project.owner),
                joinedload(Project.created_by),
                joinedload(Project.files),
                joinedload(Project.links),
                joinedload(Project.quotes),
                joinedload(Project.comments).joinedload(ProjectComment.user),
                joinedload(Project.todos).joinedload(ProjectTodo.user),
                joinedload(Project.filaments).joinedload(ProjectFilament.filament).joinedload(Filament.color),
                joinedload(Project.filaments).joinedload(ProjectFilament.filament).joinedload(Filament.brand),
                joinedload(Project.filaments).joinedload(ProjectFilament.filament).joinedload(Filament.material),
                joinedload(Project.bambu_jobs).joinedload(BambuPrintJob.filament).joinedload(Filament.color),
                joinedload(Project.bambu_jobs).joinedload(BambuPrintJob.filament).joinedload(Filament.brand),
                joinedload(Project.bambu_jobs).joinedload(BambuPrintJob.filament).joinedload(Filament.material),
                joinedload(Project.bambu_jobs).joinedload(BambuPrintJob.materials).joinedload(BambuJobMaterial.filament).joinedload(Filament.color),
                joinedload(Project.bambu_jobs).joinedload(BambuPrintJob.materials).joinedload(BambuJobMaterial.filament).joinedload(Filament.material),
                joinedload(Project.prusa_jobs).joinedload(PrusaPrintJob.printer),
                joinedload(Project.prusa_jobs).joinedload(PrusaPrintJob.filament).joinedload(Filament.color),
                joinedload(Project.prusa_jobs).joinedload(PrusaPrintJob.filament).joinedload(Filament.brand),
                joinedload(Project.prusa_jobs).joinedload(PrusaPrintJob.filament).joinedload(Filament.material),
            )
            .filter(Project.id == id)
            .first_or_404()
        )
        filaments = Filament.query.order_by(Filament.name.asc()).all()
        setting = AppSetting.query.first()
        show_bambu_jobs = bool(setting and setting.bambu_token)
        show_prusa_jobs = PrusaPrinter.query.filter_by(enabled=True).first() is not None
        active_tab = request.args.get('tab', 'overview')
        if active_tab not in {'overview', 'materials', 'files', 'jobs', 'activity', 'todos'}:
            active_tab = 'overview'

        bambu_powers = {p.device_id: p.power_draw_watts for p in BambuPrinter.query.all() if p.device_id}
        prusa_powers = {p.id: p.power_draw_watts for p in PrusaPrinter.query.all()}

        project_metrics = build_project_metrics(project, setting, bambu_powers=bambu_powers, prusa_powers=prusa_powers)
        images, model_files, other_files = _get_project_files_by_category(project)
        next_actions = _build_project_next_actions(project, project_metrics, show_bambu_jobs, show_prusa_jobs)
        activity_events = _build_project_activity_events(project)

        job_feed = _build_project_job_feed(project, setting, show_bambu_jobs, show_prusa_jobs, bambu_powers=bambu_powers, prusa_powers=prusa_powers)
        jobs_page = request.args.get('jobs_page', 1, type=int)
        job_feed_page, jobs_pagination = _paginate_jobs(job_feed, jobs_page)

        filaments_json = [
            {
                'id': filament.id,
                'name': filament.name,
                'brand': filament.brand.name if filament.brand else '',
                'material': filament.material.name if filament.material else '',
                'color_hex': filament.color.hex_value if filament.color else '#cccccc',
                'remaining': int(filament.weight_remaining),
            }
            for filament in filaments
        ]
        
        project_comments = _build_project_comments(project)
        project_todos = sorted(
            project.todos,
            key=lambda item: (item.is_done, item.completed_at or datetime.max, item.created_at or datetime.min),
        )
        todo_done_count = len([todo for todo in project_todos if todo.is_done])
        project_print_items = sorted(
            getattr(project, 'print_items', []) or [],
            key=lambda item: (item.sort_order, item.created_at or datetime.min),
        )
        print_items_total = sum(i.quantity_total for i in project_print_items)
        print_items_done = sum(i.quantity_done for i in project_print_items)
        return render_template(
            'project_detail.html',
            project=project,
            all_filaments=filaments,
            filaments_json=filaments_json,
            setting=setting,
            project_tags=format_tags(project.tag_text),
            project_metrics=project_metrics,
            project_description_html=Markup(render_markdown(project.description or '')),
            images=images,
            model_files=model_files,
            other_files=other_files,
            next_actions=next_actions,
            activity_events=activity_events,
            active_tab=active_tab,
            show_bambu_jobs=show_bambu_jobs,
            show_prusa_jobs=show_prusa_jobs,
            job_feed=job_feed_page,
            jobs_pagination=jobs_pagination,
            project_comments=project_comments,
            project_todos=project_todos,
            todo_done_count=todo_done_count,
            project_print_items=project_print_items,
            print_items_total=print_items_total,
            print_items_done=print_items_done,
            today_date=utc_now().date(),
            can_edit_project=_project_write_allowed(project),
            can_manage_project=is_admin(),
            users_for_mentions=[{'id': u.id, 'name': u.name} for u in User.query.filter_by(is_active=True).order_by(User.name).all()],
            status_flow=['NEW', 'PENDING_APPROVAL', 'APPROVED', 'PRINTING', 'DONE'],
        )

    @bp.route('/projects/<int:id>/edit', methods=['GET', 'POST'])
    def project_edit(id):
        user = get_current_user()
        project = _project_or_404(id)
        if not _project_write_allowed(project):
            abort(403)
        if request.method == 'POST':
            project.name = request.form.get('name', '').strip()
            if not project.name:
                flash('project_name_required', 'error')
                return redirect(url_for('project_edit', id=id))
            project.description = request.form.get('description', '').strip()
            project.client_name = request.form.get('client_name', '').strip()
            project.client_email = request.form.get('client_email', '').strip() or None
            project.client_phone = request.form.get('client_phone', '').strip() or None
            project.tag_text = format_tags(request.form.get('tag_text', ''))
            priority = request.form.get('priority', 'medium')
            if priority not in ('low', 'medium', 'high', 'urgent'):
                priority = 'medium'
            project.priority = priority
            due_date_str = request.form.get('due_date', '').strip()
            hours = request.form.get('print_hours', 0, type=int)
            minutes = request.form.get('print_minutes', 0, type=int)
            project.estimated_print_time = hours * 60 + minutes if hours > 0 or minutes > 0 else 0
            project.due_date = datetime.strptime(due_date_str, '%Y-%m-%d') if due_date_str else None
            if project.due_date and project.due_date.date() < utc_now().date():
                flash('project_due_date_past', 'warning')
            if is_admin(user):
                owner_user_id, owner_name = _resolve_project_owner_from_form(user)
                project.owner_user_id = owner_user_id
                project.owner_name = owner_name
            safe_commit()
            return redirect(url_for('project_detail', id=project.id))
        return render_template('project_edit.html', project=project, project_tags=format_tags(project.tag_text), can_manage_project=is_admin())

    @bp.route('/projects/<int:id>/delete', methods=['POST'])
    def project_delete(id):
        project = _project_or_404(id)
        _require_project_admin()
        from routes.projects_helpers import (
            snapshot_project_for_undo, _store_pending_undo,
        )
        # Snapshot the project BEFORE deleting, so the user can undo.
        project_name = project.name or '—'
        snapshot_id, expires_at = snapshot_project_for_undo(project)
        for item in project.files:
            try:
                os.remove(item.filepath)
            except OSError:
                pass
        db.session.delete(project)
        safe_commit()
        from flask import session
        _store_pending_undo(
            session,
            kind='project',
            undo_log_id=snapshot_id,
            title_key='project_undo_toast_title',
            detail=project_name,
            expires_at=expires_at,
        )
        return redirect(url_for('projects_index'))

    @bp.route('/projects/<int:id>/upload', methods=['POST'])
    def project_upload_file(id):
        project = _project_or_404(id)
        if not _project_write_allowed(project):
            abort(403)
        if 'file' not in request.files:
            return _project_detail_redirect(id, 'files')
        files = request.files.getlist('file')
        uploaded_any = False
        newly_added_files = []
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
            filepath = os.path.join(upload_folder, stored_filename)
            file.save(filepath)
            # ── Extract Metadata ──
            import mimetypes
            import hashlib
            try:
                size = os.path.getsize(filepath)
                sha = hashlib.sha256()
                with open(filepath, 'rb') as fh:
                    while chunk := fh.read(8192):
                        sha.update(chunk)
                checksum = sha.hexdigest()
            except Exception:
                size = 0
                checksum = None
            mime = mimetypes.guess_type(original_filename)[0] or 'application/octet-stream'
            display = original_filename.rsplit('.', 1)[0] if '.' in original_filename else original_filename
            user = get_current_user()

            # ── Versioning: check if a file with the same name already exists ──
            existing = ProjectFile.query.filter_by(
                project_id=project.id, filename=original_filename, parent_file_id=None
            ).order_by(ProjectFile.version.desc()).first()
            if existing:
                # Find latest version in the chain
                latest = ProjectFile.query.filter_by(
                    project_id=project.id, filename=original_filename
                ).order_by(ProjectFile.version.desc()).first()
                new_version = (latest.version or 1) + 1
                # Mark the old "current" file by linking it: set its parent to itself (self-link as root)
                new_pf = ProjectFile(
                    project_id=project.id,
                    filename=original_filename,
                    filepath=filepath,
                    version=new_version,
                    parent_file_id=existing.id,
                    display_name=display,
                    file_size_bytes=size,
                    mime_type=mime,
                    checksum_sha256=checksum,
                    uploaded_by_user_id=user.id if user else None
                )
                db.session.add(new_pf)
                newly_added_files.append(new_pf)
            else:
                new_pf = ProjectFile(
                    project_id=project.id,
                    filename=original_filename,
                    filepath=filepath,
                    version=1,
                    display_name=display,
                    file_size_bytes=size,
                    mime_type=mime,
                    checksum_sha256=checksum,
                    uploaded_by_user_id=user.id if user else None
                )
                db.session.add(new_pf)
                newly_added_files.append(new_pf)
            uploaded_any = True
        if uploaded_any:
            safe_commit()
            # Auto-render STL thumbnails for newly uploaded model files
            # (non-blocking).
            try:
                from routes.models import render_stl_thumbnail_for_file
                for pf in newly_added_files:
                    if pf.filename and pf.filename.rsplit('.', 1)[-1].lower() == 'stl':
                        render_stl_thumbnail_for_file(pf, commit=True)
            except Exception as exc:
                current_app.logger.warning('Auto STL processing failed: %s', exc)
        else:
            db.session.rollback()
        return _project_detail_redirect(id, 'files')

    @bp.route('/projects/<int:id>/download/<int:file_id>')
    def project_download_file(id, file_id):
        _project_or_404(id)
        project_file = db.get_or_404(ProjectFile, file_id)
        if project_file.project_id is None or project_file.project_id != id:
            abort(403)
        real_path = os.path.realpath(project_file.filepath)
        real_folder = os.path.realpath(upload_folder)
        if not real_path.startswith(real_folder + os.sep):
            abort(403)
        return send_from_directory(
            os.path.dirname(project_file.filepath),
            os.path.basename(project_file.filepath),
            as_attachment=True,
            download_name=project_file.filename,
        )

    @bp.route('/projects/<int:id>/view_file/<int:file_id>/<filename>')
    def project_view_file(id, file_id, filename):
        _project_or_404(id)
        project_file = db.get_or_404(ProjectFile, file_id)
        if project_file.project_id is None or project_file.project_id != id:
            abort(403)
        real_path = os.path.realpath(project_file.filepath)
        real_folder = os.path.realpath(upload_folder)
        if not real_path.startswith(real_folder + os.sep):
            abort(403)
        return send_from_directory(os.path.dirname(project_file.filepath), os.path.basename(project_file.filepath), as_attachment=False)

    @bp.route('/projects/<int:id>/image/<int:file_id>')
    def project_image_file(id, file_id):
        _project_or_404(id)
        project_file = db.get_or_404(ProjectFile, file_id)
        if project_file.project_id is None or project_file.project_id != id or _get_extension(project_file.filename) not in IMAGE_EXTENSIONS:
            abort(403)
        real_path = os.path.realpath(project_file.filepath)
        real_folder = os.path.realpath(upload_folder)
        if not real_path.startswith(real_folder + os.sep):
            abort(403)
        return send_from_directory(os.path.dirname(project_file.filepath), os.path.basename(project_file.filepath), as_attachment=False)

    # ── Public share endpoints for files ─────────────────────────────────────

    @bp.route('/projects/share/<token>/download/<int:file_id>')
    def project_share_download_file(token, file_id):
        project = Project.query.filter_by(share_token=token).first_or_404()
        project_file = db.get_or_404(ProjectFile, file_id)
        if project_file.project_id is None or project_file.project_id != project.id:
            abort(403)
        real_path = os.path.realpath(project_file.filepath)
        real_folder = os.path.realpath(upload_folder)
        if not real_path.startswith(real_folder + os.sep):
            abort(403)
        return send_from_directory(
            os.path.dirname(project_file.filepath),
            os.path.basename(project_file.filepath),
            as_attachment=True,
            download_name=project_file.filename,
        )

    @bp.route('/projects/share/<token>/view/<int:file_id>/<filename>')
    def project_share_view_file(token, file_id, filename):
        project = Project.query.filter_by(share_token=token).first_or_404()
        project_file = db.get_or_404(ProjectFile, file_id)
        if project_file.project_id is None or project_file.project_id != project.id:
            abort(403)
        real_path = os.path.realpath(project_file.filepath)
        real_folder = os.path.realpath(upload_folder)
        if not real_path.startswith(real_folder + os.sep):
            abort(403)
        return send_from_directory(os.path.dirname(project_file.filepath), os.path.basename(project_file.filepath), as_attachment=False)

    @bp.route('/projects/share/<token>/image/<int:file_id>')
    def project_share_image_file(token, file_id):
        project = Project.query.filter_by(share_token=token).first_or_404()
        project_file = db.get_or_404(ProjectFile, file_id)
        if project_file.project_id is None or project_file.project_id != project.id or _get_extension(project_file.filename) not in IMAGE_EXTENSIONS:
            abort(403)
        real_path = os.path.realpath(project_file.filepath)
        real_folder = os.path.realpath(upload_folder)
        if not real_path.startswith(real_folder + os.sep):
            abort(403)
        return send_from_directory(os.path.dirname(project_file.filepath), os.path.basename(project_file.filepath), as_attachment=False)

    # ── End of public share file endpoints ───────────────────────────────────

    @bp.route('/projects/<int:id>/delete_file/<int:file_id>', methods=['POST'])
    def project_delete_file(id, file_id):
        project = _project_or_404(id)
        if not _project_write_allowed(project):
            abort(403)
        project_file = db.get_or_404(ProjectFile, file_id)
        if project_file.project_id is not None and project_file.project_id == id:
            from routes.projects_helpers import (
                snapshot_file_for_undo, _store_pending_undo,
            )
            file_name = project_file.filename or '—'
            snapshot_id, expires_at, _sidecar, _content = snapshot_file_for_undo(project_file)
            try:
                os.remove(project_file.filepath)
            except OSError:
                pass
            db.session.delete(project_file)
            safe_commit()
            from flask import session
            _store_pending_undo(
                session,
                kind='file',
                undo_log_id=snapshot_id,
                title_key='project_file_undo_toast_title',
                detail=file_name,
                expires_at=expires_at,
                project_id=id,
            )
        return _project_detail_redirect(id, 'files')

    @bp.route('/projects/undo', methods=['POST'])
    def project_undo():
        """Restore the most recently deleted project or project file.

        Looks at the `project_pending_undo` session slot populated by
        `project_delete` or `project_delete_file`. The slot is consumed
        atomically — submitting it twice does not work.
        """
        from flask import session
        from routes.projects_helpers import (
            _consume_pending_undo, _cleanup_undo_artifacts,
            restore_project_from_undo, restore_file_from_undo,
        )
        slot = _consume_pending_undo(session)
        if not slot:
            flash('undo_toast_not_available', 'error')
            return redirect(request.referrer or url_for('projects_index'))
        kind = slot.get('kind')
        undo_id = slot.get('undo_log_id')
        project_id = slot.get('project_id')
        try:
            if kind == 'project':
                new_project = restore_project_from_undo(undo_id)
                safe_commit()
                flash('undo_toast_applied', 'success')
                _cleanup_undo_artifacts(slot)
                return redirect(url_for('project_detail', id=new_project.id))
            elif kind == 'file':
                new_file = restore_file_from_undo(undo_id)
                safe_commit()
                flash('undo_toast_applied', 'success')
                _cleanup_undo_artifacts(slot)
                return _project_detail_redirect(project_id, 'files') if project_id else redirect(url_for('projects_index'))
            else:
                flash('undo_toast_not_available', 'error')
                return redirect(request.referrer or url_for('projects_index'))
        except Exception:
            db.session.rollback()
            current_app.logger.exception("Project undo failed for slot=%s", slot)
            flash('undo_toast_failed', 'error')
            _cleanup_undo_artifacts(slot)
            return redirect(request.referrer or url_for('projects_index'))

    @bp.route('/projects/<int:id>/add_link', methods=['POST'])
    def project_add_link(id):
        from utils import is_safe_external_url
        from urllib.parse import urlparse as _urlparse

        project = _project_or_404(id)
        if not _project_write_allowed(project):
            abort(403)
        url = request.form.get('url', '').strip()
        name = request.form.get('name', '').strip()
        if url:
            if not is_safe_external_url(url):
                flash('project_link_invalid', 'error')
                return _project_detail_redirect(id, 'files')
            # Save the link immediately so the user isn't blocked waiting for
            # slow external fetches (e.g. Cloudflare-protected MakerWorld pages).
            # Preview metadata is fetched in a background thread with retries.
            domain = _urlparse(url).netloc
            new_link = ProjectLink(
                project_id=project.id,
                url=url,
                name=name,
                og_title=None,
                og_image=None,
                og_description=None,
                domain=domain,
            )
            db.session.add(new_link)
            safe_commit()
            _schedule_link_preview_refresh(current_app._get_current_object(), new_link.id, url)
        return _project_detail_redirect(id, 'files')

    @bp.route('/projects/<int:id>/delete_link/<int:link_id>', methods=['POST'])
    def project_delete_link(id, link_id):
        project = _project_or_404(id)
        if not _project_write_allowed(project):
            abort(403)
        link = db.get_or_404(ProjectLink, link_id)
        if link.project_id == id:
            db.session.delete(link)
            safe_commit()
        return _project_detail_redirect(id, 'files')

    @bp.route('/projects/<int:id>/refresh_link/<int:link_id>', methods=['POST'])
    def project_refresh_link(id, link_id):
        from utils import fetch_link_metadata, is_safe_external_url

        project = _project_or_404(id)
        if not _project_write_allowed(project):
            abort(403)
        link = db.get_or_404(ProjectLink, link_id)
        if link.project_id == id and is_safe_external_url(link.url):
            meta = fetch_link_metadata(link.url)
            link.og_title = meta['og_title']
            link.og_image = meta['og_image']
            link.og_description = meta['og_description']
            link.domain = meta['domain']
            safe_commit()
        return _project_detail_redirect(id, 'files')

    @bp.route('/projects/<int:id>/add_filament', methods=['POST'])
    def project_add_filament(id):
        project = _project_or_404(id)
        _require_project_admin()
        filament_id = request.form.get('filament_id', type=int)
        estimated_weight = request.form.get('estimated_weight', 0.0, type=float)
        if filament_id and estimated_weight > 0:
            db.session.add(ProjectFilament(project_id=project.id, filament_id=filament_id, estimated_weight=estimated_weight))
            safe_commit()
        return _project_detail_redirect(id, 'materials')

    @bp.route('/projects/<int:id>/remove_filament/<int:pf_id>', methods=['POST'])
    def project_remove_filament(id, pf_id):
        _project_or_404(id)
        _require_project_admin()
        project_filament = db.get_or_404(ProjectFilament, pf_id)
        if project_filament.project_id == id:
            db.session.delete(project_filament)
            safe_commit()
        return _project_detail_redirect(id, 'materials')

    @bp.route('/projects/<int:id>/update_filament/<int:pf_id>', methods=['POST'])
    def project_update_filament(id, pf_id):
        _project_or_404(id)
        _require_project_admin()
        project_filament = db.get_or_404(ProjectFilament, pf_id)
        if project_filament.project_id == id:
            new_weight = request.form.get('estimated_weight', 0.0, type=float)
            if new_weight > 0:
                project_filament.estimated_weight = new_weight
                safe_commit()
        return _project_detail_redirect(id, 'materials')

    @bp.route('/projects/<int:id>/status', methods=['POST'])
    def project_status(id):
        project = _project_or_404(id)
        _require_project_admin()
        new_status = request.form.get('status', project.status)
        if new_status not in ALLOWED_PROJECT_STATUSES:
            flash('project_status_invalid', 'error')
            return redirect(url_for('project_detail', id=id))
        project.status = new_status
        _notify_project_status(project)
        safe_commit()
        return redirect(url_for('project_detail', id=id))

    @bp.route('/projects/<int:id>/advance_status', methods=['POST'])
    def project_advance_status(id):
        project = _project_or_404(id)
        _require_project_admin()
        flow = ['NEW', 'PENDING_APPROVAL', 'APPROVED', 'PRINTING', 'DONE']
        current_idx = flow.index(project.status) if project.status in flow else -1
        if current_idx < len(flow) - 1:
            old_status = project.status
            project.status = flow[current_idx + 1]
            _notify_project_status(project)
            safe_commit()
        else:
            flash(translate('project_advance_status_no_next'), 'info')
        return redirect(url_for('project_detail', id=id))

    @bp.route('/projects/<int:id>/clone', methods=['POST'])
    def project_clone(id):
        user = get_current_user()
        project = _project_or_404(id)
        clone = Project(
            name=project.name + ' ' + translate('project_clone_suffix'),
            description=project.description,
            client_name=project.client_name,
            client_email=project.client_email,
            client_phone=project.client_phone,
            estimated_print_time=project.estimated_print_time,
            priority=project.priority,
            tag_text=project.tag_text,
            due_date=project.due_date,
            owner_user_id=project.owner_user_id,
            owner_name=project.owner_name,
            created_by_user_id=user.id if user else None,
            status='APPROVED' if is_admin(user) else 'PENDING_APPROVAL',
        )
        db.session.add(clone)
        db.session.flush()
        for pf in project.filaments:
            db.session.add(ProjectFilament(
                project_id=clone.id,
                filament_id=pf.filament_id,
                estimated_weight=pf.estimated_weight,
                is_used=False,
            ))
        for pi in project.print_items:
            db.session.add(ProjectPrintItem(
                project_id=clone.id,
                name=pi.name,
                quantity_total=pi.quantity_total,
                quantity_done=0,
                notes=pi.notes,
            ))
        safe_commit()
        flash(translate('project_clone_success'), 'success')
        return redirect(url_for('project_detail', id=clone.id))

    @bp.route('/projects/<int:id>/generate_share_token', methods=['POST'])
    def project_generate_share_token(id):
        _require_project_admin()
        project = _project_or_404(id)
        import secrets as _secrets
        project.share_token = _secrets.token_urlsafe(32)
        safe_commit()
        flash(translate('project_share_link_generated'), 'success')
        return redirect(url_for('project_detail', id=id))

    @bp.route('/projects/<int:id>/revoke_share_token', methods=['POST'])
    def project_revoke_share_token(id):
        _require_project_admin()
        project = _project_or_404(id)
        project.share_token = None
        safe_commit()
        flash(translate('project_share_link_revoked'), 'success')
        return redirect(url_for('project_detail', id=id))

    @bp.route('/projects/share/<token>')
    def project_share(token):
        project = Project.query.filter_by(share_token=token).first_or_404()
        description_html = Markup(render_markdown(project.description or ''))
        images, model_files, other_files = _get_project_files_by_category(project)
        return render_template(
            'project_share.html',
            project=project,
            description_html=description_html,
            images=images,
            model_files=model_files,
            other_files=other_files,
        )

    @bp.route('/projects/templates')
    def project_templates_index():
        user = get_current_user()
        if is_admin():
            templates = ProjectTemplate.query.order_by(ProjectTemplate.created_at.desc()).all()
        else:
            templates = ProjectTemplate.query.filter_by(created_by_user_id=user.id if user else -1).order_by(ProjectTemplate.created_at.desc()).all()
        return render_template('project_templates.html', templates=templates, can_manage_project=is_admin())

    @bp.route('/projects/<int:id>/save_as_template', methods=['POST'])
    def project_template_save(id):
        user = get_current_user()
        project = _project_or_404(id)
        tpl = ProjectTemplate(
            name=project.name,
            description=project.description,
            estimated_print_time=project.estimated_print_time,
            tag_text=project.tag_text,
            created_by_user_id=user.id if user else None,
        )
        db.session.add(tpl)
        safe_commit()
        flash(translate('project_template_saved'), 'success')
        return redirect(url_for('project_detail', id=id))

    @bp.route('/projects/templates/<int:tid>/delete', methods=['POST'])
    def project_template_delete(tid):
        _require_project_admin()
        tpl = ProjectTemplate.query.get_or_404(tid)
        db.session.delete(tpl)
        safe_commit()
        flash(translate('project_template_deleted'), 'success')
        return redirect(url_for('project_templates_index'))

    @bp.route('/project-templates/<int:tid>/data')
    def project_template_data(tid):
        tpl = ProjectTemplate.query.get_or_404(tid)
        return jsonify(
            name=tpl.name,
            client_name='',
            client_email='',
            client_phone='',
            priority='medium',
            tag_text=tpl.tag_text or '',
            description=tpl.description or '',
            estimated_print_time=tpl.estimated_print_time or 0,
        )

    @bp.route('/projects/create/from_template/<int:tid>')
    def project_create_from_template(tid):
        tpl = ProjectTemplate.query.get_or_404(tid)
        user = get_current_user()
        return render_template(
            'project_create.html',
            is_admin_user=is_admin(user),
            default_client_name=user.name if user and not is_admin(user) else '',
            suggestions=[],
            project_templates=ProjectTemplate.query.order_by(ProjectTemplate.created_at.desc()).all(),
            prefill_template=tpl,
        )

    @bp.route('/projects/<int:id>/comments/<int:cid>/react', methods=['POST'])
    def project_comment_react(id, cid):
        user = get_current_user()
        if not user:
            return jsonify({'error': translate('error_unauthorized')}), 401
        comment = ProjectComment.query.filter_by(id=cid, project_id=id).first_or_404()
        emoji = request.form.get('emoji', '').strip()
        ALLOWED_EMOJIS = {'👍', '✅', '🔄', '🎉', '❤️', '😮', '😂', '🚀', '👀', '💯', '🔥', '🙏'}
        if emoji not in ALLOWED_EMOJIS:
            return jsonify({'error': translate('error_invalid_emoji')}), 400
        existing = ProjectCommentReaction.query.filter_by(comment_id=cid, user_id=user.id, emoji=emoji).first()
        if existing:
            db.session.delete(existing)
            reacted = False
        else:
            db.session.add(ProjectCommentReaction(comment_id=cid, user_id=user.id, emoji=emoji))
            reacted = True
        safe_commit()
        count = ProjectCommentReaction.query.filter_by(comment_id=cid, emoji=emoji).count()
        return jsonify({'reacted': reacted, 'count': count, 'emoji': emoji})

    @bp.route('/projects/<int:id>/consume/<int:pf_id>', methods=['POST'])
    def project_consume_filament(id, pf_id):
        from utils import log_movement

        _project_or_404(id)
        _require_project_admin()
        project_filament = db.get_or_404(ProjectFilament, pf_id)
        if project_filament.project_id == id and not project_filament.is_used:
            filament = project_filament.filament
            old_weight = filament.weight_remaining
            filament.weight_remaining -= project_filament.estimated_weight
            if filament.weight_remaining < 0:
                filament.weight_remaining = 0
            actual_amount = old_weight - filament.weight_remaining
            if filament.weight_total > 0:
                expected_quantity = math.ceil(filament.weight_remaining / filament.weight_total)
                if expected_quantity < filament.quantity:
                    filament.quantity = expected_quantity
            project_filament.is_used = True
            log_movement(
                filament,
                'remove',
                actual_amount,
                project_id=project_filament.project_id,
                note=translate('movement_note_project_consume').format(project=project_filament.project.name if project_filament.project else ""),
            )
            safe_commit()
        return _project_detail_redirect(id, 'materials')

    @bp.route('/projects/<int:id>/comments', methods=['POST'])
    def project_add_comment(id):
        project = _project_or_404(id)
        if not _project_write_allowed(project):
            abort(403)
        user = get_current_user()
        body = request.form.get('body', '').strip()
        if user and body:
            db.session.add(ProjectComment(project_id=project.id, user_id=user.id, body=body))
            _notify_project_comment(project, user)
            safe_commit()
        return _project_detail_redirect(id, 'overview')

    @bp.route('/projects/<int:id>/comments/<int:comment_id>/edit', methods=['POST'])
    def project_update_comment(id, comment_id):
        _project_or_404(id)
        comment = db.get_or_404(ProjectComment, comment_id)
        if comment.project_id != id:
            abort(404)
        if not _comment_edit_allowed(comment):
            abort(403)
        body = request.form.get('body', '').strip()
        if not body:
            flash('project_comment_empty', 'error')
            return _project_detail_redirect(id, 'overview')
        comment.body = body
        comment.updated_at = utc_now()
        safe_commit()
        return _project_detail_redirect(id, 'overview')

    @bp.route('/projects/<int:id>/comments/<int:comment_id>/delete', methods=['POST'])
    def project_delete_comment(id, comment_id):
        project = _project_or_404(id)
        if not _project_write_allowed(project):
            abort(403)
        comment = db.get_or_404(ProjectComment, comment_id)
        if comment.project_id != id:
            abort(404)
        if not _comment_delete_allowed(comment):
            abort(403)
        db.session.delete(comment)
        safe_commit()
        return _project_detail_redirect(id, 'overview')

    @bp.route('/projects/<int:id>/comments/<int:comment_id>/toggle-checkbox', methods=['POST'])
    def project_toggle_comment_checkbox(id, comment_id):
        project = _project_or_404(id)
        if not _project_write_allowed(project):
            return jsonify({'error': translate('error_forbidden')}), 403
        comment = db.get_or_404(ProjectComment, comment_id)
        if comment.project_id != id:
            abort(404)
        try:
            checkbox_index = int(request.form.get('checkbox_index', -1))
        except (TypeError, ValueError):
            return jsonify({'error': translate('error_invalid_index')}), 400
        if checkbox_index < 0:
            return jsonify({'error': translate('error_invalid_index')}), 400
        comment.body = _toggle_markdown_checkbox(comment.body, checkbox_index)
        comment.updated_at = utc_now()
        safe_commit()
        return jsonify({'html': render_markdown(comment.body)})

    @bp.route('/projects/<int:id>/toggle-description-checkbox', methods=['POST'])
    def project_toggle_description_checkbox(id):
        project = _project_or_404(id)
        if not _project_write_allowed(project):
            return jsonify({'error': translate('error_forbidden')}), 403
        try:
            checkbox_index = int(request.form.get('checkbox_index', -1))
        except (TypeError, ValueError):
            return jsonify({'error': translate('error_invalid_index')}), 400
        if checkbox_index < 0:
            return jsonify({'error': translate('error_invalid_index')}), 400
        project.description = _toggle_markdown_checkbox(project.description or '', checkbox_index)
        safe_commit()
        return jsonify({'html': render_markdown(project.description)})

    @bp.route('/projects/<int:id>/todos', methods=['POST'])
    def project_add_todo(id):
        project = _project_or_404(id)
        if not _project_write_allowed(project):
            abort(403)
        body = request.form.get('body', '').strip()
        user = get_current_user()
        if body:
            due_date_str = request.form.get('due_date', '').strip()
            due_date = None
            if due_date_str:
                try:
                    due_date = date.fromisoformat(due_date_str)
                except ValueError:
                    pass
            db.session.add(ProjectTodo(
                project_id=project.id,
                user_id=user.id if user else None,
                body=body[:255],
                due_date=due_date,
            ))
            safe_commit()
        return _project_detail_redirect(id, 'todos')

    @bp.route('/projects/<int:id>/todos/<int:todo_id>/toggle', methods=['POST'])
    def project_toggle_todo(id, todo_id):
        project = _project_or_404(id)
        if not _project_write_allowed(project):
            abort(403)
        todo = db.get_or_404(ProjectTodo, todo_id)
        if todo.project_id != id:
            abort(404)
        todo.is_done = not todo.is_done
        todo.completed_at = utc_now() if todo.is_done else None
        safe_commit()
        return _project_detail_redirect(id, 'todos')

    @bp.route('/projects/<int:id>/todos/<int:todo_id>/delete', methods=['POST'])
    def project_delete_todo(id, todo_id):
        project = _project_or_404(id)
        if not _project_write_allowed(project):
            abort(403)
        todo = db.get_or_404(ProjectTodo, todo_id)
        if todo.project_id != id:
            abort(404)
        db.session.delete(todo)
        safe_commit()
        return _project_detail_redirect(id, 'todos')

    @bp.route('/projects/<int:id>/todos/<int:todo_id>/edit', methods=['POST'])
    def project_edit_todo(id, todo_id):
        project = _project_or_404(id)
        if not _project_write_allowed(project):
            abort(403)
        todo = db.get_or_404(ProjectTodo, todo_id)
        if todo.project_id != id:
            abort(404)
        body = request.form.get('body', '').strip()
        if body:
            todo.body = body[:255]
        due_date_str = request.form.get('due_date', '').strip()
        if due_date_str:
            try:
                todo.due_date = date.fromisoformat(due_date_str)
            except ValueError:
                pass
        elif 'due_date' in request.form:
            todo.due_date = None
        safe_commit()
        return _project_detail_redirect(id, 'todos')

    # ── Print items (pieces tracking) ─────────────────────────────────────────

    @bp.route('/projects/<int:id>/printitems/add', methods=['POST'])
    def project_add_print_item(id):
        project = _project_or_404(id)
        if not _project_write_allowed(project):
            abort(403)
        name = (request.form.get('name', '') or '').strip()
        if not name:
            return _project_detail_redirect(id, 'overview')
        try:
            quantity_total = int(request.form.get('quantity_total', 1) or 1)
            quantity_total = max(1, quantity_total)
        except (TypeError, ValueError):
            quantity_total = 1
        notes = (request.form.get('notes', '') or '').strip() or None
        item = ProjectPrintItem(
            project_id=id,
            name=name[:200],
            quantity_total=quantity_total,
            quantity_done=0,
            notes=notes,
        )
        db.session.add(item)
        safe_commit()
        return _project_detail_redirect(id, 'overview')

    @bp.route('/projects/<int:id>/printitems/<int:item_id>/edit', methods=['POST'])
    def project_edit_print_item(id, item_id):
        project = _project_or_404(id)
        if not _project_write_allowed(project):
            abort(403)
        item = db.get_or_404(ProjectPrintItem, item_id)
        if item.project_id != id:
            abort(404)
        name = (request.form.get('name', '') or '').strip()
        if name:
            item.name = name[:200]
        try:
            quantity_total = int(request.form.get('quantity_total', item.quantity_total) or item.quantity_total)
            item.quantity_total = max(1, quantity_total)
        except (TypeError, ValueError):
            pass
        try:
            quantity_done = int(request.form.get('quantity_done', item.quantity_done) or 0)
            item.quantity_done = max(0, min(item.quantity_total, quantity_done))
        except (TypeError, ValueError):
            pass
        item.notes = (request.form.get('notes', '') or '').strip() or None
        safe_commit()
        return _project_detail_redirect(id, 'overview')

    @bp.route('/projects/<int:id>/printitems/<int:item_id>/delete', methods=['POST'])
    def project_delete_print_item(id, item_id):
        project = _project_or_404(id)
        if not _project_write_allowed(project):
            abort(403)
        item = db.get_or_404(ProjectPrintItem, item_id)
        if item.project_id != id:
            abort(404)
        db.session.delete(item)
        safe_commit()
        return _project_detail_redirect(id, 'overview')

    @bp.route('/projects/<int:id>/printitems/<int:item_id>/increment', methods=['POST'])
    def project_increment_print_item(id, item_id):
        project = _project_or_404(id)
        if not _project_write_allowed(project):
            abort(403)
        item = db.get_or_404(ProjectPrintItem, item_id)
        if item.project_id != id:
            abort(404)
        if item.quantity_done < item.quantity_total:
            item.quantity_done += 1
            safe_commit()
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            pct = int(item.quantity_done / item.quantity_total * 100) if item.quantity_total > 0 else 0
            return jsonify({'quantity_done': item.quantity_done, 'quantity_total': item.quantity_total, 'pct': pct})
        return _project_detail_redirect(id, 'overview')

    @bp.route('/projects/<int:id>/printitems/<int:item_id>/decrement', methods=['POST'])
    def project_decrement_print_item(id, item_id):
        project = _project_or_404(id)
        if not _project_write_allowed(project):
            abort(403)
        item = db.get_or_404(ProjectPrintItem, item_id)
        if item.project_id != id:
            abort(404)
        if item.quantity_done > 0:
            item.quantity_done -= 1
            safe_commit()
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            pct = int(item.quantity_done / item.quantity_total * 100) if item.quantity_total > 0 else 0
            return jsonify({'quantity_done': item.quantity_done, 'quantity_total': item.quantity_total, 'pct': pct})
        return _project_detail_redirect(id, 'overview')
    app.register_blueprint(bp)
