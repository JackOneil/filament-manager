import math
import os
import shutil
import tempfile
import threading
import uuid
from datetime import date, datetime, timedelta
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
from utils import build_project_metrics, clean_bambu_title, escape_like, format_tags, normalize_hex, parse_tags, render_markdown, safe_commit, translate, utc_now, _toggle_markdown_checkbox


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
    kwh_price = float(setting.kwh_price) if setting else 5.0
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
                slot_cost += (float(slot.filament.price) / slot.filament.weight_total) * slot.weight_grams
        if slot_weight > 0:
            weight_grams = slot_weight
        if slot_cost > 0:
            material_cost = slot_cost

    if material_cost == 0.0 and job.filament and job.filament.weight_total > 0 and weight_grams > 0:
        material_cost = (float(job.filament.price) / job.filament.weight_total) * weight_grams

    return round(weight_grams, 1), round(material_cost, 2), round(energy_cost, 2)


def _job_slots(job, source, weight_grams_total):
    """Return per-slot detail list for expanded view."""
    slots = []
    if source == 'bambu':
        for slot in getattr(job, 'materials', []) or []:
            fil = slot.filament
            color = normalize_hex(slot.color_hex) or (fil.color.hex_value if fil and fil.color else None)
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
    For Bambu: prefer per-slot color_hex (available even without filament mapping),
    normalised to #RRGGBB for valid CSS rendering.
    For Prusa: use the mapped filament's color.
    Falls back to the mapped filament color on the job itself."""
    colors = []
    seen = set()
    if source == 'bambu':
        for slot in getattr(job, 'materials', []) or []:
            c = normalize_hex(slot.color_hex)
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
            filament_colors = _job_colors(job, 'bambu')
            # Derive the single primary colour hex for the compact row dot.
            # For single-slot jobs use the mapped filament colour; for
            # multi-material jobs use the first slot colour so the dot is at
            # least representative.
            if filament_colors:
                filament_color_hex = filament_colors[0]
            elif job.filament and job.filament.color:
                filament_color_hex = job.filament.color.hex_value
            else:
                filament_color_hex = None
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
                'filament_color_hex': filament_color_hex,
                'filament_colors': filament_colors,
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
                'filament_color_hex': job.filament.color.hex_value if job.filament and job.filament.color else None,
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
            'label': translate('activity_quote_saved').format(price=f'{quote.final_price:.2f}', currency=quote.currency),
            'detail': f'{quote.filament_name} · {quote.weight} g · {quote.final_price:.2f} {quote.currency}',
            'meta': f'{quote.filament_name} · {quote.weight} g',
            'kind': 'quote',
        })
    for project_file in sorted(project.files, key=lambda item: item.uploaded_at or datetime.min, reverse=True):
        activity_events.append({
            'created_at': project_file.uploaded_at,
            'label': translate('activity_file_uploaded').format(filename=project_file.filename),
            'detail': project_file.filename,
            'meta': _get_extension(project_file.filename).upper() or 'FILE',
            'kind': 'file',
        })
    for comment in sorted(project.comments, key=lambda item: item.created_at or datetime.min, reverse=True):
        activity_events.append({
            'created_at': comment.updated_at or comment.created_at,
            'label': translate('activity_comment').format(body=(comment.body or '')[:60]),
            'detail': (comment.body or '')[:200],
            'meta': comment.user.name if comment.user else '-',
            'kind': 'comment',
        })
    for todo in sorted(project.todos, key=lambda item: item.created_at or datetime.min, reverse=True):
        activity_events.append({
            'created_at': todo.completed_at or todo.created_at,
            'label': translate('activity_todo').format(body=todo.body),
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
                        safe_commit()
                    return  # success
            except Exception:
                flask_app.logger.exception(
                    "Link preview fetch attempt %d/%d failed for link_id=%d url=%s",
                    attempt + 1, max_attempts, link_id, url,
                )

    t = threading.Thread(target=_fetch, daemon=True)
    t.start()


# ── Undo system for project + project-file deletion ─────────────────────
# Uses a session-based snapshot (no new DB tables). On delete we dump the
# row(s) to a temp JSON file and store the path + kind in the session.
# On undo we restore from that file. The session-stored payload is small
# (a few fields); the heavy data lives on disk and is reaped automatically
# after _PROJECT_UNDO_TTL_MINUTES or by an opportunistic janitor pass.

_PROJECT_UNDO_TTL_MINUTES = 30
_PROJECT_UNDO_DIR = os.path.join(tempfile.gettempdir(), 'filament_undo')


def _ensure_undo_dir():
    os.makedirs(_PROJECT_UNDO_DIR, exist_ok=True)


def _project_undo_path(snapshot_id):
    return os.path.join(_PROJECT_UNDO_DIR, f'project_{snapshot_id}.json')


def _file_undo_path(snapshot_id, filename):
    return os.path.join(_PROJECT_UNDO_DIR, f'file_{snapshot_id}_{secure_filename(filename) or "blob"}')


def _store_pending_undo(session, *, kind, undo_log_id, title_key, detail, expires_at, project_id=None):
    """Generic session-based undo slot.

    `kind` is 'project' or 'file' (future-proof for 'comment', 'todo', etc.).
    `undo_log_id` is a short unique key matching the temp file/dir.
    `title_key` and `detail` are rendered into the toast by base.html.
    """
    session['project_pending_undo'] = {
        'kind': kind,
        'undo_log_id': undo_log_id,
        'title_key': title_key,
        'detail': detail,
        'expires_at': expires_at,
        'project_id': project_id,
    }


def _consume_pending_undo(session):
    slot = session.pop('project_pending_undo', None)
    if not slot:
        return None
    expires_raw = slot.get('expires_at')
    try:
        expires_at = datetime.fromisoformat(expires_raw) if expires_raw else None
    except (TypeError, ValueError):
        expires_at = None
    if expires_at and expires_at < utc_now():
        return None  # expired; caller will show "not available"
    return slot


def _cleanup_undo_artifacts(slot):
    """Best-effort delete of the on-disk snapshot files. Never raises."""
    if not slot:
        return
    undo_id = slot.get('undo_log_id')
    kind = slot.get('kind')
    if not undo_id:
        return
    try:
        if kind == 'project':
            p = _project_undo_path(undo_id)
            if os.path.isfile(p):
                os.remove(p)
        elif kind == 'file':
            # The undo_log_id encodes the file name; try a couple of patterns.
            d = os.path.join(_PROJECT_UNDO_DIR, f'file_{undo_id}_')
            if os.path.isdir(_PROJECT_UNDO_DIR):
                for fn in os.listdir(_PROJECT_UNDO_DIR):
                    if fn.startswith(f'file_{undo_id}_'):
                        try:
                            full = os.path.join(_PROJECT_UNDO_DIR, fn)
                            if os.path.isfile(full):
                                os.remove(full)
                        except OSError:
                            pass
    except OSError:
        current_app.logger.warning('Failed to clean up undo artifacts for %s', undo_id)


def snapshot_project_for_undo(project):
    """Dump the project (and its children) to a temp JSON file.

    Returns a (snapshot_id, expires_at_iso) tuple.
    """
    import json as _json
    _ensure_undo_dir()
    snapshot_id = uuid.uuid4().hex
    payload = {
        'project': {
            'name': project.name,
            'description': project.description,
            'client_name': project.client_name,
            'client_email': project.client_email,
            'client_phone': project.client_phone,
            'estimated_print_time': project.estimated_print_time,
            'status': project.status,
            'priority': project.priority,
            'tag_text': project.tag_text,
            'due_date': project.due_date.isoformat() if project.due_date else None,
            'share_token': project.share_token,
            'owner_user_id': project.owner_user_id,
            'owner_name': project.owner_name,
            'created_by_user_id': project.created_by_user_id,
        },
        'filaments': [
            {
                'filament_id': pf.filament_id,
                'estimated_weight': pf.estimated_weight,
                'is_used': pf.is_used,
            }
            for pf in project.filaments
        ],
        'todos': [
            {
                'body': t.body,
                'is_done': t.is_done,
                'position': t.position,
            }
            for t in sorted(project.todos, key=lambda x: (x.position or 0, x.id or 0))
        ],
        'links': [
            {
                'url': l.url,
                'name': l.name,
                'og_title': l.og_title,
                'og_image': l.og_image,
                'og_description': l.og_description,
                'domain': l.domain,
            }
            for l in project.links
        ],
    }
    path = _project_undo_path(snapshot_id)
    with open(path, 'w', encoding='utf-8') as f:
        _json.dump(payload, f, ensure_ascii=False, default=str)
    expires_at = utc_now() + timedelta(minutes=_PROJECT_UNDO_TTL_MINUTES)
    return snapshot_id, expires_at.isoformat(timespec='seconds')


def restore_project_from_undo(snapshot_id):
    """Re-create a project (and its children) from a previously stored snapshot.

    Returns the new Project object, or raises KeyError/ValueError on failure.
    """
    import json as _json
    path = _project_undo_path(snapshot_id)
    if not os.path.isfile(path):
        raise KeyError('snapshot_missing')
    with open(path, 'r', encoding='utf-8') as f:
        payload = _json.load(f)

    proj_data = payload.get('project') or {}
    new_project = Project(
        name=proj_data.get('name', 'Restored project'),
        description=proj_data.get('description'),
        client_name=proj_data.get('client_name'),
        client_email=proj_data.get('client_email'),
        client_phone=proj_data.get('client_phone'),
        estimated_print_time=proj_data.get('estimated_print_time') or 0,
        status=proj_data.get('status') or 'NEW',
        priority=proj_data.get('priority') or 'medium',
        tag_text=proj_data.get('tag_text'),
        owner_user_id=proj_data.get('owner_user_id'),
        owner_name=proj_data.get('owner_name'),
        created_by_user_id=proj_data.get('created_by_user_id'),
    )
    if proj_data.get('due_date'):
        try:
            new_project.due_date = date.fromisoformat(proj_data['due_date'])
        except (TypeError, ValueError):
            pass
    if proj_data.get('share_token'):
        new_project.share_token = proj_data['share_token']

    db.session.add(new_project)
    db.session.flush()  # get an id for children

    for fl in payload.get('filaments', []):
        if not fl.get('filament_id'):
            continue
        db.session.add(ProjectFilament(
            project_id=new_project.id,
            filament_id=fl['filament_id'],
            estimated_weight=fl.get('estimated_weight'),
            is_used=bool(fl.get('is_used')),
        ))

    for t in payload.get('todos', []):
        db.session.add(ProjectTodo(
            project_id=new_project.id,
            body=t.get('body', ''),
            is_done=bool(t.get('is_done')),
            position=t.get('position', 0),
        ))

    for l in payload.get('links', []):
        if not l.get('url'):
            continue
        db.session.add(ProjectLink(
            project_id=new_project.id,
            url=l['url'],
            name=l.get('name'),
            og_title=l.get('og_title'),
            og_image=l.get('og_image'),
            og_description=l.get('og_description'),
            domain=l.get('domain'),
        ))

    safe_commit()
    return new_project


def snapshot_file_for_undo(project_file):
    """Copy a project file to a temp location for potential restoration.

    Returns (snapshot_id, expires_at_iso). Also writes a small JSON sidecar
    with the file's DB row fields.
    """
    import json as _json
    _ensure_undo_dir()
    snapshot_id = uuid.uuid4().hex
    sidecar = {
        'project_id': project_file.project_id,
        'filename': project_file.filename,
        'filepath': project_file.filepath,
        'version': project_file.version,
        'parent_file_id': project_file.parent_file_id,
        'version_note': project_file.version_note,
        'model_note': project_file.model_note,
        'checksum_sha256': project_file.checksum_sha256,
        'file_size_bytes': project_file.file_size_bytes,
        'mime_type': project_file.mime_type,
        'uploaded_by_user_id': project_file.uploaded_by_user_id,
    }
    sidecar_path = _file_undo_path(snapshot_id, sidecar['filename'] or 'blob') + '.json'
    content_path = _file_undo_path(snapshot_id, sidecar['filename'] or 'blob')
    with open(sidecar_path, 'w', encoding='utf-8') as f:
        _json.dump(sidecar, f, ensure_ascii=False, default=str)
    # Best-effort copy of the file content. If the file is gone, the undo
    # will restore the row but the content will be missing (logged).
    try:
        if project_file.filepath and os.path.isfile(project_file.filepath):
            shutil.copy2(project_file.filepath, content_path)
        elif project_file.filepath:
            current_app.logger.warning('Undo snapshot: source file missing: %s', project_file.filepath)
    except OSError as exc:
        current_app.logger.warning('Undo snapshot: copy failed for %s: %s', project_file.filepath, exc)

    expires_at = utc_now() + timedelta(minutes=_PROJECT_UNDO_TTL_MINUTES)
    return snapshot_id, expires_at.isoformat(timespec='seconds'), sidecar_path, content_path


def restore_file_from_undo(snapshot_id):
    """Re-create a ProjectFile row (and its content) from a previous snapshot.

    Returns the new ProjectFile object, or raises KeyError/ValueError.
    """
    import json as _json
    _ensure_undo_dir()
    sidecars = [fn for fn in os.listdir(_PROJECT_UNDO_DIR) if fn.startswith(f'file_{snapshot_id}_') and fn.endswith('.json')]
    if not sidecars:
        raise KeyError('snapshot_missing')
    sidecar_path = os.path.join(_PROJECT_UNDO_DIR, sidecars[0])
    with open(sidecar_path, 'r', encoding='utf-8') as f:
        sidecar = _json.load(f)

    # Content path = sidecar path with .json stripped
    content_path = sidecar_path[:-5]
    project_file = ProjectFile(
        project_id=sidecar.get('project_id'),
        filename=sidecar.get('filename') or 'restored',
        filepath=sidecar.get('filepath') or '',
        version=sidecar.get('version') or 1,
        parent_file_id=sidecar.get('parent_file_id'),
        version_note=sidecar.get('version_note'),
        model_note=sidecar.get('model_note'),
        checksum_sha256=sidecar.get('checksum_sha256'),
        file_size_bytes=sidecar.get('file_size_bytes'),
        mime_type=sidecar.get('mime_type'),
        uploaded_by_user_id=sidecar.get('uploaded_by_user_id'),
    )
    # If the original on-disk file is still around, re-link it; otherwise
    # try to restore from the temp copy.
    if os.path.isfile(content_path) and project_file.filepath:
        try:
            os.makedirs(os.path.dirname(project_file.filepath) or '.', exist_ok=True)
            shutil.copy2(content_path, project_file.filepath)
        except OSError as exc:
            current_app.logger.warning('Undo restore: file copy failed: %s', exc)
    db.session.add(project_file)
    safe_commit()
    return project_file

