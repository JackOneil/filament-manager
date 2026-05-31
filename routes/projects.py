import math
import os
import threading
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
from utils import build_project_metrics, escape_like, format_tags, parse_tags, render_markdown, translate, utc_now, _toggle_markdown_checkbox


ALLOWED_PROJECT_FILE_EXTENSIONS = {
    '3mf', 'stl', 'obj', 'amf', 'step', 'stp', 'gcode', 'gc', 'bgcode',
    'jpg', 'jpeg', 'png', 'gif', 'webp',
}
IMAGE_EXTENSIONS = {'jpg', 'jpeg', 'png', 'gif', 'webp'}
ALLOWED_PROJECT_STATUSES = {'NEW', 'PENDING_APPROVAL', 'APPROVED', 'REJECTED', 'PRINTING', 'DONE'}
KANBAN_STATUSES = ('PENDING_APPROVAL', 'APPROVED', 'PRINTING', 'DONE')


def _get_extension(filename):
    return filename.rsplit('.', 1)[1].lower() if '.' in filename else ''


def _is_allowed_project_file(filename):
    return _get_extension(filename) in ALLOWED_PROJECT_FILE_EXTENSIONS


def _build_storage_name(project_id, filename):
    safe_name = secure_filename(filename)
    unique_id = uuid.uuid4().hex[:12]
    return f'{project_id}_{unique_id}_{safe_name}'


def _project_detail_redirect(project_id, tab='overview', **extra_params):
    params = {'id': project_id, 'tab': tab}
    params.update(extra_params)
    return redirect(url_for('project_detail', **params))


def _job_timestamp(job):
    return job.started_at or job.finished_at or getattr(job, 'synced_at', None) or datetime.min


def _job_cost_parts(job, setting, bambu_powers=None, prusa_powers=None):
    kwh_price = setting.kwh_price if setting else 5.0
    printer_power = setting.printer_power if setting else 150

    job_power = printer_power
    if isinstance(job, BambuPrintJob):
        if bambu_powers and job.device_id and job.device_id in bambu_powers and bambu_powers[job.device_id] is not None:
            job_power = bambu_powers[job.device_id]
    else:
        # PrusaPrintJob uses printer_id
        if prusa_powers and job.printer_id and job.printer_id in prusa_powers and prusa_powers[job.printer_id] is not None:
            job_power = prusa_powers[job.printer_id]

    energy_cost = ((job.cost_time or 0) / 3600.0) * (job_power / 1000.0) * kwh_price
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


def _job_slots(job, source, weight_grams_total):
    """Return per-slot detail list for expanded view."""
    slots = []
    if source == 'bambu':
        for slot in getattr(job, 'materials', []) or []:
            fil = slot.filament
            color = slot.color_hex or (fil.color.hex_value if fil and fil.color else None)
            slots.append({
                'color_hex': color,
                'material_name': slot.material_name or (fil.material.name if fil and fil.material else None),
                'weight_grams': slot.weight_grams,
                'filament_id': slot.filament_id,
                'filament_name': fil.name if fil else None,
                'filament_url': url_for('filament_detail', id=slot.filament_id) if slot.filament_id else None,
            })
    else:
        fil = job.filament
        if fil:
            slots.append({
                'color_hex': fil.color.hex_value if fil.color else None,
                'material_name': fil.material.name if fil.material else None,
                'weight_grams': weight_grams_total,
                'filament_id': fil.id,
                'filament_name': fil.name,
                'filament_url': url_for('filament_detail', id=fil.id),
            })
    return slots


def _job_colors(job, source):
    """Return a deduplicated list of color hex strings for a job.
    For Bambu: prefer per-slot color_hex (available even without filament mapping).
    For Prusa: use the mapped filament's color.
    Falls back to the mapped filament color on the job itself."""
    colors = []
    seen = set()
    if source == 'bambu':
        for slot in getattr(job, 'materials', []) or []:
            c = slot.color_hex
            if not c:
                # fallback: mapped filament color for this slot
                c = slot.filament.color.hex_value if slot.filament and slot.filament.color else None
            if c and c not in seen:
                seen.add(c)
                colors.append(c)
    if not colors and job.filament and job.filament.color:
        c = job.filament.color.hex_value
        if c:
            colors.append(c)
    return colors


def _build_project_job_feed(project, setting, show_bambu_jobs, show_prusa_jobs, bambu_powers=None, prusa_powers=None):
    items = []

    if show_bambu_jobs:
        for job in getattr(project, 'bambu_jobs', []) or []:
            weight_grams, material_cost, energy_cost = _job_cost_parts(job, setting, bambu_powers, prusa_powers)
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
                'filament_colors': _job_colors(job, 'bambu'),
                'slots': _job_slots(job, 'bambu', weight_grams),
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
            weight_grams, material_cost, energy_cost = _job_cost_parts(job, setting, bambu_powers, prusa_powers)
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
                'filament_colors': _job_colors(job, 'prusa'),
                'slots': _job_slots(job, 'prusa', weight_grams),
                'material_slots': 0,
                'deducted': bool(job.deducted),
                'detail_url': url_for('prusa_jobs'),
                'unmapped': (job.project_id is None or job.filament_id is None),
            })

    items.sort(key=lambda item: item['timestamp'] or datetime.min, reverse=True)
    return items


def _project_scope():
    user = get_current_user()
    query = Project.query
    if current_app.config.get('TESTING') and not current_app.config.get('AUTH_REQUIRED_IN_TESTS'):
        return query
    if is_admin(user):
        owner_id = request.args.get('owner_id', type=int)
        if owner_id:
            query = query.filter(Project.owner_user_id == owner_id)
        return query
    if not user:
        return query.filter(db.literal(False))
    return query.filter(Project.owner_user_id == user.id)


def _project_or_404(project_id):
    project = (
        Project.query
        .options(joinedload(Project.owner), joinedload(Project.created_by))
        .filter(Project.id == project_id)
        .first_or_404()
    )
    if current_app.config.get('TESTING') and not current_app.config.get('AUTH_REQUIRED_IN_TESTS'):
        return project
    user = get_current_user()
    if is_admin(user):
        return project
    if not user or project.owner_user_id != user.id:
        abort(404)
    return project


def _project_write_allowed(project):
    user = get_current_user()
    if current_app.config.get('TESTING') and not current_app.config.get('AUTH_REQUIRED_IN_TESTS'):
        return True
    return bool(user and (is_admin(user) or project.owner_user_id == user.id))


def _comment_edit_allowed(comment):
    user = get_current_user()
    return bool(user and comment.user_id == user.id)


def _comment_delete_allowed(comment):
    user = get_current_user()
    return bool(user and (is_admin(user) or comment.user_id == user.id))


def _require_project_admin():
    if current_app.config.get('TESTING') and not current_app.config.get('AUTH_REQUIRED_IN_TESTS'):
        return
    if not is_admin():
        abort(403)


def _project_owner_choices():
    if not is_admin():
        return []
    return User.query.filter_by(is_active=True).order_by(User.name.asc()).all()


def _resolve_project_owner_from_form(user):
    owner_user_id = user.id if user else None
    owner_name = None
    if not is_admin(user):
        return owner_user_id, owner_name

    selected_owner_id = request.form.get('owner_user_id', type=int)
    manual_owner_name = (request.form.get('owner_name', '') or '').strip()

    if manual_owner_name:
        return None, manual_owner_name[:120]

    if selected_owner_id:
        selected_owner = db.session.get(User, selected_owner_id)
        if selected_owner and selected_owner.is_active:
            return selected_owner.id, None

    return owner_user_id, None


def _notify_project_created(project):
    for admin in User.query.filter_by(role='admin', is_active=True).all():
        if admin.notify_project_created:
            create_notification(
                admin,
                translate('notify_project_created_title').format(name=project.name),
                translate('notify_project_created_body'),
                url_for('project_detail', id=project.id),
                kind='project_new',
            )


def _notify_project_status(project):
    status_label = translate(f'project_status_{project.status.lower()}') if project.status else project.status
    title = translate('notify_project_status_title').format(name=project.name)
    body = translate('notify_project_status_body').format(status=status_label)
    link = url_for('project_detail', id=project.id)
    seen = set()
    if project.owner and project.owner.notify_project_status_changed:
        seen.add(project.owner.id)
        create_notification(project.owner, title, body, link, kind='project_status')
    for admin in User.query.filter_by(role='admin', is_active=True).all():
        if admin.notify_project_status_changed and admin.id not in seen:
            seen.add(admin.id)
            create_notification(admin, title, body, link, kind='project_status')


def _notify_project_comment(project, author):
    recipients = []
    if project.owner and project.owner.id != author.id and project.owner.notify_project_comment:
        recipients.append(project.owner)
    for admin in User.query.filter_by(role='admin', is_active=True).all():
        if admin.id != author.id and admin.notify_project_comment:
            recipients.append(admin)
    seen = set()
    title = translate('notify_comment_title').format(name=project.name)
    body = translate('notify_comment_body').format(author=author.name)
    for recipient in recipients:
        if recipient.id in seen:
            continue
        seen.add(recipient.id)
        create_notification(
            recipient,
            title,
            body,
            url_for('project_detail', id=project.id, tab='overview'),
            kind='project_comment',
        )


def _get_project_files_by_category(project):
    images, model_files, other_files = [], [], []
    # Collect all files per version chain (root = parent_file_id is None)
    roots = {}      # root_id -> root ProjectFile
    children = {}   # root_id -> [child ProjectFile, ...]
    for project_file in project.files:
        if project_file.parent_file_id is None:
            roots[project_file.id] = project_file
        else:
            children.setdefault(project_file.parent_file_id, []).append(project_file)

    for root_id, root_file in roots.items():
        chain = [root_file] + children.get(root_id, [])
        # The latest version (highest version number) is shown as the main file;
        # all older versions are shown in the collapsible history section.
        chain.sort(key=lambda f: f.version)
        latest = chain[-1]
        older = list(reversed(chain[:-1]))  # descending: newest-among-older first
        # Attach the older-versions list as a plain Python attribute so the template
        # can iterate it without mutating the SQLAlchemy relationship.
        latest._older_versions = older

        ext = _get_extension(latest.filename)
        if ext in IMAGE_EXTENSIONS:
            images.append(latest)
        elif ext in {'3mf', 'stl', 'obj', 'amf', 'step', 'stp', 'gcode', 'gc', 'bgcode'}:
            model_files.append(latest)
        else:
            other_files.append(latest)
    return images, model_files, other_files


def _build_project_next_actions(project, project_metrics, show_bambu_jobs, show_prusa_jobs):
    next_actions = []
    if project.due_date and project.due_date < utc_now() and project.status != 'DONE':
        next_actions.append('overdue')
    if is_admin() and not project.filaments:
        next_actions.append('plan_filaments')
    if is_admin() and project_metrics['has_quote'] is False:
        next_actions.append('create_quote')
    if is_admin() and any(not row.is_used for row in project.filaments):
        next_actions.append('consume_planned')
    if show_prusa_jobs and any(job.project_id is None or job.filament_id is None for job in getattr(project, 'prusa_jobs', [])):
        next_actions.append('map_prusa_jobs')
    if show_bambu_jobs and any(
        job.project_id is None or job.filament_id is None or any(slot.filament_id is None for slot in job.materials)
        for job in getattr(project, 'bambu_jobs', [])
    ):
        next_actions.append('map_bambu_jobs')
    return next_actions


def _build_project_activity_events(project):
    activity_events = []
    for quote in sorted(project.quotes, key=lambda item: item.created_at or datetime.min, reverse=True):
        activity_events.append({
            'created_at': quote.created_at,
            'label': f'Quote saved: {quote.final_price:.2f} {quote.currency}',
            'detail': f'{quote.filament_name} · {quote.weight} g · {quote.final_price:.2f} {quote.currency}',
            'meta': f'{quote.filament_name} · {quote.weight} g',
            'kind': 'quote',
        })
    for project_file in sorted(project.files, key=lambda item: item.uploaded_at or datetime.min, reverse=True):
        activity_events.append({
            'created_at': project_file.uploaded_at,
            'label': f'File uploaded: {project_file.filename}',
            'detail': project_file.filename,
            'meta': _get_extension(project_file.filename).upper() or 'FILE',
            'kind': 'file',
        })
    for comment in sorted(project.comments, key=lambda item: item.created_at or datetime.min, reverse=True):
        activity_events.append({
            'created_at': comment.updated_at or comment.created_at,
            'label': f'Comment: {(comment.body or "")[:60]}',
            'detail': (comment.body or '')[:200],
            'meta': comment.user.name if comment.user else '-',
            'kind': 'comment',
        })
    for todo in sorted(project.todos, key=lambda item: item.created_at or datetime.min, reverse=True):
        activity_events.append({
            'created_at': todo.completed_at or todo.created_at,
            'label': f'TODO: {todo.body}',
            'detail': todo.body or '',
            'meta': 'done' if todo.is_done else 'open',
            'kind': 'todo',
        })
    activity_events.sort(key=lambda item: item['created_at'] or datetime.min, reverse=True)
    return activity_events


def _build_project_comments(project):
    user = get_current_user()
    project_comments = []
    for comment in sorted(project.comments, key=lambda item: item.created_at or datetime.min, reverse=True):
        # Build reaction summary: {emoji: {count, user_reacted}}
        reaction_summary = {}
        for reaction in comment.reactions:
            if reaction.emoji not in reaction_summary:
                reaction_summary[reaction.emoji] = {'count': 0, 'user_reacted': False}
            reaction_summary[reaction.emoji]['count'] += 1
            if user and reaction.user_id == user.id:
                reaction_summary[reaction.emoji]['user_reacted'] = True
        project_comments.append({
            'id': comment.id,
            'user': comment.user,
            'body': comment.body,
            'body_html': Markup(render_markdown(comment.body)),
            'created_at': comment.created_at,
            'updated_at': comment.updated_at,
            'can_edit': _comment_edit_allowed(comment),
            'can_delete': _comment_delete_allowed(comment),
            'reactions': reaction_summary,
        })
    return project_comments


def _paginate_jobs(job_feed, page, per_page=8):
    jobs_total = len(job_feed)
    jobs_pages = max(1, math.ceil(jobs_total / per_page)) if jobs_total else 1
    page = min(max(page, 1), jobs_pages)
    start = (page - 1) * per_page
    return job_feed[start:start + per_page], SimpleNamespace(
        page=page,
        pages=jobs_pages,
        total=jobs_total,
        has_prev=page > 1,
        has_next=page < jobs_pages,
        prev_num=page - 1 if page > 1 else 1,
        next_num=page + 1 if page < jobs_pages else jobs_pages,
    )


def _schedule_link_preview_refresh(flask_app, link_id, url, max_attempts=3, retry_delay=12):
    """Fetch and store link preview metadata in a background thread with retries.

    MakerWorld and similar JS-heavy sites (behind Cloudflare) often return a
    challenge page on the first request. The jina.ai reader fallback needs a
    short window to render and cache the page before it can return useful data.
    Retrying with delays handles this transparently without blocking the user.
    """
    def _fetch():
        from utils import fetch_link_metadata

        for attempt in range(max_attempts):
            if attempt > 0:
                threading.Event().wait(retry_delay)  # non-blocking sleep
            try:
                with flask_app.app_context():
                    meta = fetch_link_metadata(url)
                    if not any(v for v in (meta['og_title'], meta['og_image'], meta['og_description'])):
                        continue  # weak result – retry
                    link = db.session.get(ProjectLink, link_id)
                    if link:
                        link.og_title = meta['og_title']
                        link.og_image = meta['og_image']
                        link.og_description = meta['og_description']
                        link.domain = meta['domain'] or link.domain
                        db.session.commit()
                    return  # success
            except Exception:
                flask_app.logger.exception(
                    "Link preview fetch attempt %d/%d failed for link_id=%d url=%s",
                    attempt + 1, max_attempts, link_id, url,
                )

    t = threading.Thread(target=_fetch, daemon=True)
    t.start()


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
            description = request.form.get('description', '').strip()
            client_name = user.name if user and not is_admin(user) else request.form.get('client_name', '').strip()
            client_email = request.form.get('client_email', '').strip()
            client_phone = request.form.get('client_phone', '').strip()
            due_date_str = request.form.get('due_date', '').strip()
            hours = request.form.get('print_hours', 0, type=int)
            minutes = request.form.get('print_minutes', 0, type=int)
            estimated_print_time = hours * 60 + minutes if hours > 0 or minutes > 0 else 0
            due_date = datetime.strptime(due_date_str, '%Y-%m-%d') if due_date_str else None
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
            db.session.commit()
            return redirect(url_for('project_detail', id=project.id))

        # Query unmapped Bambu print jobs for naming suggestion
        unmapped_jobs = BambuPrintJob.query.filter_by(project_id=None).order_by(BambuPrintJob.started_at.desc()).limit(15).all()
        from routes.bambu import _clean_title
        suggestions = []
        seen_names = set()
        for job in unmapped_jobs:
            if job.model_name:
                cleaned = _clean_title(job.model_name)
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
            if is_admin(user):
                owner_user_id, owner_name = _resolve_project_owner_from_form(user)
                project.owner_user_id = owner_user_id
                project.owner_name = owner_name
            db.session.commit()
            return redirect(url_for('project_detail', id=project.id))
        return render_template('project_edit.html', project=project, project_tags=format_tags(project.tag_text), can_manage_project=is_admin())

    @bp.route('/projects/<int:id>/delete', methods=['POST'])
    def project_delete(id):
        project = _project_or_404(id)
        _require_project_admin()
        for item in project.files:
            try:
                os.remove(item.filepath)
            except OSError:
                pass
        db.session.delete(project)
        db.session.commit()
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
                db.session.add(ProjectFile(
                    project_id=project.id,
                    filename=original_filename,
                    filepath=filepath,
                    version=new_version,
                    parent_file_id=existing.id,
                ))
            else:
                db.session.add(ProjectFile(
                    project_id=project.id,
                    filename=original_filename,
                    filepath=filepath,
                    version=1,
                ))
            uploaded_any = True
        if uploaded_any:
            db.session.commit()
        else:
            db.session.rollback()
        return _project_detail_redirect(id, 'files')

    @bp.route('/projects/<int:id>/download/<int:file_id>')
    def project_download_file(id, file_id):
        _project_or_404(id)
        project_file = db.get_or_404(ProjectFile, file_id)
        if project_file.project_id != id:
            return 'Unauthorized', 401
        real_path = os.path.realpath(project_file.filepath)
        real_folder = os.path.realpath(upload_folder)
        if not real_path.startswith(real_folder + os.sep):
            return 'Forbidden', 403
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
        if project_file.project_id != id:
            return 'Unauthorized', 401
        real_path = os.path.realpath(project_file.filepath)
        real_folder = os.path.realpath(upload_folder)
        if not real_path.startswith(real_folder + os.sep):
            return 'Forbidden', 403
        return send_from_directory(os.path.dirname(project_file.filepath), os.path.basename(project_file.filepath), as_attachment=False)

    @bp.route('/projects/<int:id>/image/<int:file_id>')
    def project_image_file(id, file_id):
        _project_or_404(id)
        project_file = db.get_or_404(ProjectFile, file_id)
        if project_file.project_id != id or _get_extension(project_file.filename) not in IMAGE_EXTENSIONS:
            return 'Unauthorized', 401
        real_path = os.path.realpath(project_file.filepath)
        real_folder = os.path.realpath(upload_folder)
        if not real_path.startswith(real_folder + os.sep):
            return 'Forbidden', 403
        return send_from_directory(os.path.dirname(project_file.filepath), os.path.basename(project_file.filepath), as_attachment=False)

    # ── Public share endpoints for files ─────────────────────────────────────

    @bp.route('/projects/share/<token>/download/<int:file_id>')
    def project_share_download_file(token, file_id):
        project = Project.query.filter_by(share_token=token).first_or_404()
        project_file = db.get_or_404(ProjectFile, file_id)
        if project_file.project_id != project.id:
            return 'Unauthorized', 401
        real_path = os.path.realpath(project_file.filepath)
        real_folder = os.path.realpath(upload_folder)
        if not real_path.startswith(real_folder + os.sep):
            return 'Forbidden', 403
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
        if project_file.project_id != project.id:
            return 'Unauthorized', 401
        real_path = os.path.realpath(project_file.filepath)
        real_folder = os.path.realpath(upload_folder)
        if not real_path.startswith(real_folder + os.sep):
            return 'Forbidden', 403
        return send_from_directory(os.path.dirname(project_file.filepath), os.path.basename(project_file.filepath), as_attachment=False)

    @bp.route('/projects/share/<token>/image/<int:file_id>')
    def project_share_image_file(token, file_id):
        project = Project.query.filter_by(share_token=token).first_or_404()
        project_file = db.get_or_404(ProjectFile, file_id)
        if project_file.project_id != project.id or _get_extension(project_file.filename) not in IMAGE_EXTENSIONS:
            return 'Unauthorized', 401
        real_path = os.path.realpath(project_file.filepath)
        real_folder = os.path.realpath(upload_folder)
        if not real_path.startswith(real_folder + os.sep):
            return 'Forbidden', 403
        return send_from_directory(os.path.dirname(project_file.filepath), os.path.basename(project_file.filepath), as_attachment=False)

    # ── End of public share file endpoints ───────────────────────────────────

    @bp.route('/projects/<int:id>/delete_file/<int:file_id>', methods=['POST'])
    def project_delete_file(id, file_id):
        project = _project_or_404(id)
        if not _project_write_allowed(project):
            abort(403)
        project_file = db.get_or_404(ProjectFile, file_id)
        if project_file.project_id == id:
            try:
                os.remove(project_file.filepath)
            except OSError:
                pass
            db.session.delete(project_file)
            db.session.commit()
        return _project_detail_redirect(id, 'files')

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
            db.session.commit()
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
            db.session.commit()
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
            db.session.commit()
        return _project_detail_redirect(id, 'files')

    @bp.route('/projects/<int:id>/add_filament', methods=['POST'])
    def project_add_filament(id):
        project = _project_or_404(id)
        _require_project_admin()
        filament_id = request.form.get('filament_id', type=int)
        estimated_weight = request.form.get('estimated_weight', 0.0, type=float)
        if filament_id and estimated_weight > 0:
            db.session.add(ProjectFilament(project_id=project.id, filament_id=filament_id, estimated_weight=estimated_weight))
            db.session.commit()
        return _project_detail_redirect(id, 'materials')

    @bp.route('/projects/<int:id>/remove_filament/<int:pf_id>', methods=['POST'])
    def project_remove_filament(id, pf_id):
        _project_or_404(id)
        _require_project_admin()
        project_filament = db.get_or_404(ProjectFilament, pf_id)
        if project_filament.project_id == id:
            db.session.delete(project_filament)
            db.session.commit()
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
                db.session.commit()
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
        db.session.commit()
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
            db.session.commit()
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
                actual_weight=0,
                color_override=pf.color_override,
            ))
        for pi in project.print_items:
            db.session.add(ProjectPrintItem(
                project_id=clone.id,
                item_name=pi.item_name,
                quantity=pi.quantity,
                done=False,
                notes=pi.notes,
            ))
        db.session.commit()
        flash(translate('project_clone_success'), 'success')
        return redirect(url_for('project_detail', id=clone.id))

    @bp.route('/projects/<int:id>/generate_share_token', methods=['POST'])
    def project_generate_share_token(id):
        _require_project_admin()
        project = _project_or_404(id)
        import secrets as _secrets
        project.share_token = _secrets.token_urlsafe(32)
        db.session.commit()
        flash(translate('project_share_link_generated'), 'success')
        return redirect(url_for('project_detail', id=id))

    @bp.route('/projects/<int:id>/revoke_share_token', methods=['POST'])
    def project_revoke_share_token(id):
        _require_project_admin()
        project = _project_or_404(id)
        project.share_token = None
        db.session.commit()
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
        db.session.commit()
        flash(translate('project_template_saved'), 'success')
        return redirect(url_for('project_detail', id=id))

    @bp.route('/projects/templates/<int:tid>/delete', methods=['POST'])
    def project_template_delete(tid):
        _require_project_admin()
        tpl = ProjectTemplate.query.get_or_404(tid)
        db.session.delete(tpl)
        db.session.commit()
        flash(translate('project_template_deleted'), 'success')
        return redirect(url_for('project_templates_index'))

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
            return jsonify({'error': 'unauthorized'}), 401
        comment = ProjectComment.query.filter_by(id=cid, project_id=id).first_or_404()
        emoji = request.form.get('emoji', '').strip()
        ALLOWED_EMOJIS = {'👍', '✅', '🔄', '🎉', '❤️'}
        if emoji not in ALLOWED_EMOJIS:
            return jsonify({'error': 'invalid emoji'}), 400
        existing = ProjectCommentReaction.query.filter_by(comment_id=cid, user_id=user.id, emoji=emoji).first()
        if existing:
            db.session.delete(existing)
            reacted = False
        else:
            db.session.add(ProjectCommentReaction(comment_id=cid, user_id=user.id, emoji=emoji))
            reacted = True
        db.session.commit()
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
                note=f'Project consume: {project_filament.project.name if project_filament.project else ""}'.strip(),
            )
            db.session.commit()
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
            db.session.commit()
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
        db.session.commit()
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
        db.session.commit()
        return _project_detail_redirect(id, 'overview')

    @bp.route('/projects/<int:id>/comments/<int:comment_id>/toggle-checkbox', methods=['POST'])
    def project_toggle_comment_checkbox(id, comment_id):
        project = _project_or_404(id)
        if not _project_write_allowed(project):
            return jsonify({'error': 'Forbidden'}), 403
        comment = db.get_or_404(ProjectComment, comment_id)
        if comment.project_id != id:
            abort(404)
        try:
            checkbox_index = int(request.form.get('checkbox_index', -1))
        except (TypeError, ValueError):
            return jsonify({'error': 'Invalid index'}), 400
        if checkbox_index < 0:
            return jsonify({'error': 'Invalid index'}), 400
        comment.body = _toggle_markdown_checkbox(comment.body, checkbox_index)
        comment.updated_at = utc_now()
        db.session.commit()
        return jsonify({'html': render_markdown(comment.body)})

    @bp.route('/projects/<int:id>/toggle-description-checkbox', methods=['POST'])
    def project_toggle_description_checkbox(id):
        project = _project_or_404(id)
        if not _project_write_allowed(project):
            return jsonify({'error': 'Forbidden'}), 403
        try:
            checkbox_index = int(request.form.get('checkbox_index', -1))
        except (TypeError, ValueError):
            return jsonify({'error': 'Invalid index'}), 400
        if checkbox_index < 0:
            return jsonify({'error': 'Invalid index'}), 400
        project.description = _toggle_markdown_checkbox(project.description or '', checkbox_index)
        db.session.commit()
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
            db.session.commit()
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
        db.session.commit()
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
        db.session.commit()
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
        db.session.commit()
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
        db.session.commit()
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
        db.session.commit()
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
        db.session.commit()
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
            db.session.commit()
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
            db.session.commit()
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            pct = int(item.quantity_done / item.quantity_total * 100) if item.quantity_total > 0 else 0
            return jsonify({'quantity_done': item.quantity_done, 'quantity_total': item.quantity_total, 'pct': pct})
        return _project_detail_redirect(id, 'overview')
    app.register_blueprint(bp)
