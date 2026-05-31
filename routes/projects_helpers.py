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
from utils import build_project_metrics, clean_bambu_title, escape_like, format_tags, parse_tags, render_markdown, translate, utc_now, _toggle_markdown_checkbox


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

