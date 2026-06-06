from datetime import datetime
from utils import utc_now

from flask import abort, current_app, flash, jsonify, redirect, render_template, request, session, url_for, Blueprint
from sqlalchemy import or_

from auth import (
    create_invite,
    create_notification,
    default_section_permissions,
    get_current_user,
    get_user_sessions,
    hash_password,
    invalidate_all_other_sessions,
    invite_is_valid,
    is_admin,
    login_user,
    logout_user,
    recent_notifications,
    require_admin,
    require_login,
    safe_redirect_target,
    serialize_permissions,
    user_permissions,
    verify_password,
)
from database import db
from models import AuditLog, Notification, Project, User, UserInvite, UserSession
from sqlalchemy import func


def _bool_field(name):
    return request.form.get(name) == 'on'


def _permissions_from_form():
    return {
        'overview': _bool_field('perm_overview'),
        'filaments': _bool_field('perm_filaments'),
        'projects': _bool_field('perm_projects'),
        'history': _bool_field('perm_history'),
        'storage': _bool_field('perm_storage'),
        'calculator': _bool_field('perm_calculator'),
        'printers': _bool_field('perm_printers'),
        'stats': _bool_field('perm_stats'),
        'settings': _bool_field('perm_settings'),
        'users': _bool_field('perm_users'),
    }


def _build_users_query(q, role, status, sort_by, sort_direction):
    """Build and return a User query with filters and sorting."""
    users_query = User.query

    if q:
        from utils import escape_like
        pattern = f'%{escape_like(q)}%'
        users_query = users_query.filter(or_(User.name.ilike(pattern), User.email.ilike(pattern)))
    if role in {'admin', 'user'}:
        users_query = users_query.filter(User.role == role)
    if status == 'active':
        users_query = users_query.filter(User.is_active.is_(True))
    elif status == 'inactive':
        users_query = users_query.filter(User.is_active.is_(False))

    sort_map = {
        'name': User.name,
        'email': User.email,
        'created_at': User.created_at,
        'last_login_at': User.last_login_at,
        'role': User.role,
        'is_active': User.is_active,
    }
    order_expr = sort_map.get(sort_by, User.created_at)
    if sort_by in ('role', 'is_active'):
        users_query = users_query.order_by(
            order_expr.desc() if sort_direction == 'desc' else order_expr.asc(),
            User.name.asc()
        )
    else:
        null_rank = db.case((order_expr.is_(None), 1), else_=0)
        if sort_direction == 'asc':
            users_query = users_query.order_by(null_rank.asc(), order_expr.asc(), User.name.asc())
        else:
            users_query = users_query.order_by(null_rank.asc(), order_expr.desc(), User.name.asc())

    return users_query


def register(app):
    bp = Blueprint('auth', __name__)
    @bp.route('/login', methods=['GET', 'POST'])
    def login():
        if get_current_user():
            return redirect(url_for('index'))
        if request.method == 'POST':
            email = request.form.get('email', '').strip().lower()
            password = request.form.get('password', '')
            user = User.query.filter_by(email=email).first()
            if user and verify_password(user, password) and user.is_active:
                login_user(user, plain_password=password)
                flash('auth_login_success', 'success')
                # First-login onboarding tour: append ?welcome=1 if the user
                # has not yet completed the tour (tracked via a 1-year cookie).
                target = safe_redirect_target(request.args.get('next'), fallback_endpoint='index')
                if not request.cookies.get('first_login_tour_v1'):
                    from urllib.parse import urlparse, urlparse as _urlp, urlunparse, parse_qsl, urlencode
                    parts = _urlp(target)
                    qs = dict(parse_qsl(parts.query, keep_blank_values=True))
                    qs['welcome'] = '1'
                    target = urlunparse(parts._replace(query=urlencode(qs)))
                response = redirect(target)
                if not request.cookies.get('first_login_tour_v1'):
                    response.set_cookie(
                        'first_login_tour_v1', 'done',
                        max_age=365 * 24 * 60 * 60,
                        httponly=True,
                        samesite='Lax',
                    )
                return response
            flash('auth_login_failed', 'error')
        return render_template('auth_login.html', user_count=User.query.count())

    @bp.route('/logout', methods=['POST'])
    @require_login
    def logout():
        logout_user()
        flash('auth_logout_success', 'success')
        return redirect(url_for('login'))

    @bp.route('/register', methods=['GET', 'POST'])
    def register_account():
        current = get_current_user()
        if current:
            return redirect(url_for('index'))
        existing_users = User.query.count()
        if request.method == 'POST':
            name = request.form.get('name', '').strip()
            email = request.form.get('email', '').strip().lower()
            password = request.form.get('password', '')
            if not name or not email or len(password) < 8:
                flash('auth_register_invalid', 'error')
                return render_template('auth_register.html', bootstrap_admin=(existing_users == 0))
            if User.query.filter_by(email=email).first():
                flash('auth_email_exists', 'error')
                return render_template('auth_register.html', bootstrap_admin=(existing_users == 0))
            role = 'admin' if existing_users == 0 else 'user'
            permissions = default_section_permissions() if role == 'user' else None
            user = User(
                email=email,
                name=name,
                password_hash=hash_password(password),
                role=role,
                section_permissions=serialize_permissions(permissions, role=role),
            )
            db.session.add(user)
            db.session.commit()
            login_user(user, plain_password=password)
            flash('auth_register_success', 'success')
            return redirect(url_for('index'))
        return render_template('auth_register.html', bootstrap_admin=(existing_users == 0))

    @bp.route('/activate', methods=['GET', 'POST'])
    def activate_invite():
        code = request.values.get('code', '').strip()
        invite = UserInvite.query.filter_by(code=code).first() if code else None
        if request.method == 'POST':
            invite = UserInvite.query.filter_by(code=request.form.get('code', '').strip()).first()
            if not invite_is_valid(invite):
                flash('auth_invite_invalid', 'error')
                return redirect(url_for('activate_invite', code=code))
            name = request.form.get('name', '').strip()
            email = request.form.get('email', '').strip().lower() or (invite.email or '').strip().lower()
            password = request.form.get('password', '')
            if not name or not email or len(password) < 8:
                flash('auth_register_invalid', 'error')
                return render_template('auth_activate.html', invite=invite)
            if User.query.filter_by(email=email).first():
                flash('auth_email_exists', 'error')
                return render_template('auth_activate.html', invite=invite)
            user = User(
                email=email,
                name=name,
                password_hash=hash_password(password),
                role=invite.role,
                section_permissions=invite.section_permissions,
            )
            invite.is_used = True
            db.session.add(user)
            db.session.commit()
            login_user(user, plain_password=password)
            flash('auth_register_success', 'success')
            return redirect(url_for('index'))
        return render_template('auth_activate.html', invite=invite)

    @bp.route('/users', methods=['GET', 'POST'])
    @require_admin
    def users_index():
        if request.method == 'POST':
            action = request.form.get('action', '')
            if action == 'invite':
                role = 'admin' if request.form.get('role') == 'admin' else 'user'
                permissions = None if role == 'admin' else _permissions_from_form()
                invite = create_invite(
                    email=request.form.get('email', '').strip().lower(),
                    role=role,
                    permissions=permissions,
                )
                db.session.commit()
                flash('users_invite_created', 'success')
                return redirect(url_for('users_index', invite=invite.code))
            elif action == 'bulk':
                return _users_bulk_action()

        page = request.args.get('page', 1, type=int)
        q = request.args.get('q', '').strip()
        role = request.args.get('role', '').strip()
        status = request.args.get('status', '').strip()
        sort_by = request.args.get('sort_by', 'created_at')
        sort_direction = request.args.get('sort_direction', 'desc')
        ajax = request.args.get('ajax') == '1'

        users_query = _build_users_query(q, role, status, sort_by, sort_direction)
        users = db.paginate(users_query.statement, page=page, per_page=20, error_out=False)
        invites = UserInvite.query.order_by(UserInvite.created_at.desc()).limit(10).all()

        context = dict(
            users=users,
            invites=invites,
            generated_invite=request.args.get('invite', ''),
            filters={
                'q': q,
                'role': role,
                'status': status,
                'sort_by': sort_by,
                'sort_direction': sort_direction,
                'page': page,
            },
            default_permissions=default_section_permissions(),
            now=utc_now(),
        )

        if ajax:
            html = render_template('_users_table.html', **context)
            return jsonify({'html': html})

        return render_template('users.html', **context)

    def _check_delete_user_allowed(target_user, current_user):
        """Validate that a user can be deleted. Raises abort(400) if not."""
        if target_user.id == current_user.id:
            abort(400, translate('users_cannot_delete_self'))
        admin_count = User.query.filter_by(role='admin', is_active=True).count()
        if target_user.role == 'admin' and admin_count <= 1:
            abort(400, translate('users_cannot_delete_last_admin'))
        if not target_user.is_active:
            # Allow deleting inactive users
            pass

    @bp.route('/users/<int:user_id>', methods=['GET', 'POST'])
    @require_admin
    def user_detail(user_id):
        user = db.get_or_404(User, user_id)

        if request.method == 'POST':
            action = request.form.get('action', '')
            if action == 'delete':
                current = get_current_user()
                _check_delete_user_allowed(user, current)
                # Reassign owned projects to the deleting admin
                for project in user.owned_projects:
                    project.owner_user_id = current.id
                # Reassign projects created by this user
                for project in user.created_projects:
                    project.created_by_user_id = current.id
                db.session.delete(user)
                db.session.commit()
                flash('users_user_deleted', 'success')
                return redirect(url_for('users_index'))

            # Regular update
            role = 'admin' if request.form.get('role') == 'admin' else 'user'
            user.name = request.form.get('name', '').strip() or user.name
            user.email = request.form.get('email', '').strip().lower() or user.email
            user.role = role
            user.is_active = _bool_field('is_active')
            user.section_permissions = serialize_permissions(_permissions_from_form(), role=role)
            user.notify_project_created = _bool_field('notify_project_created')
            user.notify_project_status_changed = _bool_field('notify_project_status_changed')
            user.notify_project_comment = _bool_field('notify_project_comment')
            db.session.commit()
            flash('users_user_updated', 'success')
            return redirect(url_for('user_detail', user_id=user.id))

        user_projects = user.owned_projects
        user_projects_list = sorted(user_projects, key=lambda p: p.created_at or utc_now(), reverse=True)[:10]
        # Recent comments by this user
        user_comments = (
            user.project_comments
            if hasattr(user, 'project_comments')
            else []
        )
        user_comments_list = sorted(user_comments, key=lambda c: c.created_at or utc_now(), reverse=True)[:10]
        # Notification count
        notification_count = Notification.query.filter_by(user_id=user.id).count()
        # Recent audit log entries for this user
        from sqlalchemy import desc
        audit_entries = (
            AuditLog.query.filter_by(user_email=user.email)
            .order_by(desc(AuditLog.created_at))
            .limit(10)
            .all()
        )
        current_user = get_current_user()
        can_delete = user.id != current_user.id
        admin_count = User.query.filter_by(role='admin', is_active=True).count()
        is_last_admin = (user.role == 'admin' and admin_count <= 1)

        return render_template(
            'user_detail.html',
            managed_user=user,
            managed_user_permissions=user_permissions(user),
            default_permissions=default_section_permissions(),
            user_projects_count=len(user_projects),
            user_last_project_at=max((p.created_at for p in user_projects), default=None),
            user_recent_projects=user_projects_list,
            user_recent_comments=user_comments_list,
            user_notification_count=notification_count,
            user_audit_entries=audit_entries,
            can_delete=can_delete and not is_last_admin,
            now=utc_now(),
        )

    @bp.route('/invites/<int:invite_id>/delete', methods=['POST'])
    @require_admin
    def invite_delete(invite_id):
        invite = db.get_or_404(UserInvite, invite_id)
        if invite.is_used:
            flash('users_invite_already_used', 'error')
        else:
            db.session.delete(invite)
            db.session.commit()
            flash('users_invite_deleted', 'success')
        return redirect(url_for('users_index'))

    def _users_bulk_action():
        """Handle bulk actions on users (activate/deactivate/delete)."""
        action = request.form.get('bulk_action', '')
        selected = request.form.getlist('selected_users', type=int)
        if not selected or action not in ('activate', 'deactivate', 'delete'):
            flash('users_bulk_invalid', 'error')
            return redirect(url_for('users_index'))

        current_user = get_current_user()
        if action == 'delete':
            users_to_delete = User.query.filter(User.id.in_(selected)).all()
            admin_count = User.query.filter_by(role='admin', is_active=True).count()
            for target_user in users_to_delete:
                if target_user.id == current_user.id:
                    continue
                remaining_admins = admin_count - (1 if target_user.role == 'admin' else 0)
                if target_user.role == 'admin' and remaining_admins < 1:
                    continue
                # Reassign owned projects
                for project in target_user.owned_projects:
                    project.owner_user_id = current_user.id
                for project in target_user.created_projects:
                    project.created_by_user_id = current_user.id
                db.session.delete(target_user)
            db.session.commit()
            flash('users_bulk_deleted', 'success')
        elif action == 'activate':
            User.query.filter(User.id.in_(selected), User.is_active.is_(False)).update(
                {'is_active': True}, synchronize_session=False
            )
            db.session.commit()
            flash('users_bulk_activated', 'success')
        elif action == 'deactivate':
            # Prevent deactivating self
            safe_selected = [uid for uid in selected if uid != current_user.id]
            if safe_selected:
                User.query.filter(User.id.in_(safe_selected), User.is_active.is_(True)).update(
                    {'is_active': False}, synchronize_session=False
                )
                db.session.commit()
            flash('users_bulk_deactivated', 'success')
        return redirect(url_for('users_index'))

    @bp.route('/account', methods=['GET', 'POST'])
    @require_login
    def account_settings():
        user = get_current_user()
        if request.method == 'POST':
            action = request.form.get('action', '')
            try:
                if action == 'profile':
                    user.name = request.form.get('name', '').strip() or user.name
                    user.notify_project_created = _bool_field('notify_project_created')
                    user.notify_project_status_changed = _bool_field('notify_project_status_changed')
                    user.notify_project_comment = _bool_field('notify_project_comment')
                    db.session.commit()
                    flash('account_updated', 'success')
                elif action == 'preferences':
                    lang = request.form.get('preferred_language', '')
                    user.preferred_language = lang if lang in ('cs', 'en') else None
                    theme = request.form.get('preferred_theme', '')
                    user.preferred_theme = theme if theme in ('light', 'dark', 'auto') else None
                    db.session.commit()
                    flash('account_preferences_updated', 'success')
                elif action == 'password':
                    current_password = request.form.get('current_password', '')
                    new_password = request.form.get('new_password', '')
                    if not verify_password(user, current_password) or len(new_password) < 8:
                        flash('account_password_invalid', 'error')
                    else:
                        user.password_hash = hash_password(new_password)
                        db.session.commit()
                        # Invalidate all other sessions so old passwords are unusable
                        session_key = session.get('_session_key', '')
                        if session_key:
                            invalidate_all_other_sessions(user, session_key)
                        flash('account_password_updated', 'success')
                elif action == 'sign_out_everywhere':
                    session_key = session.get('_session_key', '')
                    if session_key:
                        invalidate_all_other_sessions(user, session_key)
                    flash('account_sessions_invalidated', 'success')
                else:
                    flash('account_unknown_action', 'error')
            except Exception as e:
                db.session.rollback()
                current_app.logger.exception('Account settings update failed')
                flash('account_update_failed', 'error')
            return redirect(url_for('account_settings'))

        # GET: compute stats and load sessions
        from flask import session as flask_session

        # Project stats for this user
        if is_admin(user):
            project_query = Project.query
        else:
            from sqlalchemy import or_
            project_query = Project.query.filter(
                or_(Project.owner_user_id == user.id, Project.created_by_user_id == user.id)
            )

        status_counts = dict(
            db.session.query(Project.status, func.count(Project.id))
            .filter(project_query.whereclause)
            .group_by(Project.status)
            .all()
        )
        total_projects = project_query.count()
        recent_projects = (
            project_query
            .order_by(Project.created_at.desc())
            .limit(5)
            .all()
        )

        # Active sessions
        sessions = get_user_sessions(user)
        current_session_key = flask_session.get('_session_key', '')

        return render_template(
            'account.html',
            user=user,
            permissions=user_permissions(user),
            sessions=sessions,
            current_session_key=current_session_key,
            status_counts=status_counts,
            total_projects=total_projects,
            recent_projects=recent_projects,
        )

    _VALID_NOTIFICATION_KINDS = {'project_new', 'project_status', 'project_comment', 'info', 'project'}

    @bp.route('/notifications')
    @require_login
    def notifications_index():
        user = get_current_user()
        page = request.args.get('page', 1, type=int)
        kind_filter = request.args.get('kind', '')
        if kind_filter not in _VALID_NOTIFICATION_KINDS:
            kind_filter = ''
        q = Notification.query.filter_by(user_id=user.id)
        if kind_filter:
            q = q.filter(Notification.kind == kind_filter)
        q = q.order_by(Notification.created_at.desc())
        notifications = db.paginate(q.statement, page=page, per_page=20, error_out=False)
        # counts per kind for filter pills
        from sqlalchemy import func
        kind_counts = {
            row.kind: row.cnt
            for row in db.session.query(Notification.kind, func.count(Notification.id).label('cnt'))
            .filter_by(user_id=user.id)
            .group_by(Notification.kind)
            .all()
        }
        total_count = sum(kind_counts.values())
        return render_template(
            'notifications.html',
            notifications=notifications,
            kind_filter=kind_filter,
            kind_counts=kind_counts,
            total_count=total_count,
        )

    @bp.route('/notifications/<int:id>/read', methods=['POST'])
    @require_login
    def notification_mark_read(id):
        user = get_current_user()
        notification = db.session.get(Notification, id)
        if not notification or notification.user_id != user.id:
            abort(404)
        notification.is_read = True
        db.session.commit()
        next_page = request.form.get('page', 1, type=int)
        kind_filter = request.form.get('kind', '')
        return redirect(url_for('notifications_index', page=next_page, kind=kind_filter or None))

    @bp.route('/notifications/read-all', methods=['POST'])
    @require_login
    def notification_mark_all_read():
        user = get_current_user()
        kind_filter = request.form.get('kind', '')
        q = Notification.query.filter_by(user_id=user.id, is_read=False)
        if kind_filter and kind_filter in _VALID_NOTIFICATION_KINDS:
            q = q.filter(Notification.kind == kind_filter)
        q.update({'is_read': True})
        db.session.commit()
        next_page = request.form.get('page', 1, type=int)
        return redirect(url_for('notifications_index', page=next_page, kind=kind_filter or None))

    @bp.route('/notifications/<int:id>/delete', methods=['POST'])
    @require_login
    def notification_delete(id):
        user = get_current_user()
        notification = db.session.get(Notification, id)
        if not notification or notification.user_id != user.id:
            abort(404)
        db.session.delete(notification)
        db.session.commit()
        next_page = request.form.get('page', 1, type=int)
        kind_filter = request.form.get('kind', '')
        return redirect(url_for('notifications_index', page=next_page, kind=kind_filter or None))

    @bp.route('/notifications/delete-read', methods=['POST'])
    @require_login
    def notification_delete_read():
        user = get_current_user()
        kind_filter = request.form.get('kind', '')
        q = Notification.query.filter_by(user_id=user.id, is_read=True)
        if kind_filter and kind_filter in _VALID_NOTIFICATION_KINDS:
            q = q.filter(Notification.kind == kind_filter)
        q.delete()
        db.session.commit()
        return redirect(url_for('notifications_index', kind=kind_filter or None))

    @bp.route('/audit')
    @require_admin
    def audit_logs():
        page = request.args.get('page', 1, type=int)
        q = (request.args.get('q', '') or '').strip()
        action_filter = (request.args.get('action', '') or '').strip()
        object_filter = (request.args.get('object_type', '') or '').strip()

        logs_query = AuditLog.query
        if q:
            from utils import escape_like
            pattern = f'%{escape_like(q)}%'
            logs_query = logs_query.filter(or_(
                AuditLog.user_email.ilike(pattern),
                AuditLog.user_name.ilike(pattern),
                AuditLog.endpoint.ilike(pattern),
                AuditLog.path.ilike(pattern),
                AuditLog.object_id.ilike(pattern),
            ))
        if action_filter:
            logs_query = logs_query.filter(AuditLog.action == action_filter)
        if object_filter:
            logs_query = logs_query.filter(AuditLog.object_type == object_filter)

        logs_query = logs_query.order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        logs = db.paginate(logs_query.statement, page=page, per_page=30, error_out=False)
        actions = [
            value for (value,) in db.session.query(AuditLog.action)
            .filter(AuditLog.action.isnot(None))
            .distinct()
            .order_by(AuditLog.action.asc())
            .all()
        ]
        object_types = [
            value for (value,) in db.session.query(AuditLog.object_type)
            .filter(AuditLog.object_type.isnot(None))
            .distinct()
            .order_by(AuditLog.object_type.asc())
            .all()
        ]
        return render_template(
            'audit.html',
            logs=logs,
            filters={'q': q, 'action': action_filter, 'object_type': object_filter},
            actions=actions,
            object_types=object_types,
        )

    @app.context_processor
    def inject_auth_nav():
        user = get_current_user()
        notifications = recent_notifications(user, limit=8) if user else []
        unread = sum(1 for n in notifications if not n.is_read) if notifications else 0
        return {
            'current_user_obj': user,
            'current_user_permissions': user_permissions(user) if user else {},
            'is_admin_user': is_admin(user),
            'nav_notifications': notifications,
            'nav_notifications_unread': unread,
        }
    app.register_blueprint(bp)
