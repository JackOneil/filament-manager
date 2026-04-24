from datetime import datetime

from flask import abort, flash, redirect, render_template, request, url_for
from sqlalchemy import or_

from auth import (
    create_invite,
    create_notification,
    default_section_permissions,
    get_current_user,
    hash_password,
    invite_is_valid,
    is_admin,
    login_user,
    logout_user,
    recent_notifications,
    require_admin,
    require_login,
    safe_redirect_target,
    serialize_permissions,
    unread_notifications_count,
    user_permissions,
    verify_password,
)
from database import db
from models import Notification, User, UserInvite


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


def register(app):
    @app.route('/login', methods=['GET', 'POST'])
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
                return redirect(safe_redirect_target(request.args.get('next'), fallback_endpoint='index'))
            flash('auth_login_failed', 'error')
        return render_template('auth_login.html', user_count=User.query.count())

    @app.route('/logout', methods=['POST'])
    @require_login
    def logout():
        logout_user()
        flash('auth_logout_success', 'success')
        return redirect(url_for('login'))

    @app.route('/register', methods=['GET', 'POST'])
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

    @app.route('/activate', methods=['GET', 'POST'])
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

    @app.route('/users', methods=['GET', 'POST'])
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
        q = request.args.get('q', '').strip()
        role = request.args.get('role', '').strip()
        status = request.args.get('status', '').strip()
        sort_by = request.args.get('sort_by', 'created_at')
        sort_direction = request.args.get('sort_direction', 'desc')

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
            users_query = users_query.order_by(order_expr.desc() if sort_direction == 'desc' else order_expr.asc(), User.name.asc())
        else:
            null_rank = db.case((order_expr.is_(None), 1), else_=0)
            if sort_direction == 'asc':
                users_query = users_query.order_by(null_rank.asc(), order_expr.asc(), User.name.asc())
            else:
                users_query = users_query.order_by(null_rank.asc(), order_expr.desc(), User.name.asc())

        users = users_query.all()
        invites = UserInvite.query.order_by(UserInvite.created_at.desc()).limit(10).all()
        return render_template(
            'users.html',
            users=users,
            invites=invites,
            generated_invite=request.args.get('invite', ''),
            filters={
                'q': q,
                'role': role,
                'status': status,
                'sort_by': sort_by,
                'sort_direction': sort_direction,
            },
            default_permissions=default_section_permissions(),
        )

    @app.route('/users/<int:user_id>', methods=['GET', 'POST'])
    @require_admin
    def user_detail(user_id):
        user = db.get_or_404(User, user_id)
        if request.method == 'POST':
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
        return render_template(
            'user_detail.html',
            managed_user=user,
            managed_user_permissions=user_permissions(user),
            default_permissions=default_section_permissions(),
            user_projects_count=len(user_projects),
            user_last_project_at=max((project.created_at for project in user_projects), default=None),
            now=datetime.utcnow(),
        )

    @app.route('/account', methods=['GET', 'POST'])
    @require_login
    def account_settings():
        user = get_current_user()
        if request.method == 'POST':
            action = request.form.get('action', '')
            if action == 'profile':
                user.name = request.form.get('name', '').strip() or user.name
                user.notify_project_created = _bool_field('notify_project_created')
                user.notify_project_status_changed = _bool_field('notify_project_status_changed')
                user.notify_project_comment = _bool_field('notify_project_comment')
                db.session.commit()
                flash('account_updated', 'success')
            elif action == 'password':
                current_password = request.form.get('current_password', '')
                new_password = request.form.get('new_password', '')
                if not verify_password(user, current_password) or len(new_password) < 8:
                    flash('account_password_invalid', 'error')
                else:
                    user.password_hash = hash_password(new_password)
                    db.session.commit()
                    flash('account_password_updated', 'success')
            return redirect(url_for('account_settings'))
        return render_template('account.html', user=user, permissions=user_permissions(user))

    @app.route('/notifications')
    @require_login
    def notifications_index():
        user = get_current_user()
        page = request.args.get('page', 1, type=int)
        notifications = db.paginate(
            Notification.query
            .filter_by(user_id=user.id)
            .order_by(Notification.created_at.desc())
            ,
            page=page,
            per_page=20,
            error_out=False,
        )
        return render_template('notifications.html', notifications=notifications)

    @app.route('/notifications/<int:id>/read', methods=['POST'])
    @require_login
    def notification_mark_read(id):
        user = get_current_user()
        notification = db.session.get(Notification, id)
        if not notification or notification.user_id != user.id:
            abort(404)
        notification.is_read = True
        db.session.commit()
        next_page = request.form.get('page', 1, type=int)
        return redirect(request.form.get('next') or url_for('notifications_index', page=next_page))

    @app.route('/notifications/read-all', methods=['POST'])
    @require_login
    def notification_mark_all_read():
        user = get_current_user()
        Notification.query.filter_by(user_id=user.id, is_read=False).update({'is_read': True})
        db.session.commit()
        next_page = request.form.get('page', 1, type=int)
        return redirect(url_for('notifications_index', page=next_page))

    @app.context_processor
    def inject_auth_nav():
        user = get_current_user()
        return {
            'current_user_obj': user,
            'current_user_permissions': user_permissions(user) if user else {},
            'is_admin_user': is_admin(user),
            'nav_notifications': recent_notifications(user, limit=6) if user else [],
            'nav_notifications_unread': unread_notifications_count(user) if user else 0,
        }
