"""Movement history route."""
from datetime import datetime
from flask import render_template, request, redirect, url_for, make_response, Blueprint
from database import db
from models import MovementHistory
from utils import escape_like


_VALID_PER_PAGE = [10, 20, 50, 100]
_COOKIE_KEY = 'history_per_page'

_ALL_ACTION_TYPES = [
    'add', 'remove', 'bambu_print',
    'bulk_add_weight', 'bulk_delete',
    'bulk_add_spool', 'bulk_remove_spool',
]


def register(app):
    bp = Blueprint('history', __name__)

    @bp.route('/history')
    def history():
        page = request.args.get('page', 1, type=int)

        # ── Read filter parameters ──────────────────────────────────────────
        q = request.args.get('q', '').strip()
        action_type = request.args.get('action_type', '').strip()
        date_from = request.args.get('date_from', '').strip()
        date_to = request.args.get('date_to', '').strip()

        # ── per_page priority: URL param > cookie > default (10) ────────────
        if 'per_page' in request.args:
            per_page = request.args.get('per_page', 10, type=int)
            if per_page not in _VALID_PER_PAGE:
                per_page = 10
            save_cookie = True
        else:
            try:
                per_page = int(request.cookies.get(_COOKIE_KEY, 10))
            except (TypeError, ValueError):
                per_page = 10
            if per_page not in _VALID_PER_PAGE:
                per_page = 10
            save_cookie = False

        # ── Build filtered query ────────────────────────────────────────────
        query = MovementHistory.query

        # Fulltext search: filament_name OR note
        if q:
            safe_q = escape_like(q)
            like_pattern = f'%{safe_q}%'
            query = query.filter(
                db.or_(
                    MovementHistory.filament_name.ilike(like_pattern),
                    MovementHistory.note.ilike(like_pattern),
                )
            )

        # Action type filter
        if action_type in _ALL_ACTION_TYPES:
            query = query.filter(MovementHistory.action_type == action_type)

        # Date range filters
        if date_from:
            try:
                dt_from = datetime.strptime(date_from, '%Y-%m-%d')
                query = query.filter(MovementHistory.created_at >= dt_from)
            except ValueError:
                pass  # Ignore invalid date

        if date_to:
            try:
                # Include the entire "date_to" day
                dt_to = datetime.strptime(date_to, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
                query = query.filter(MovementHistory.created_at <= dt_to)
            except ValueError:
                pass  # Ignore invalid date

        movements_paginated = db.paginate(
            query.order_by(MovementHistory.created_at.desc()).statement,
            page=page, per_page=per_page, error_out=False,
        )

        # ── Gather available action types from DB for the filter dropdown ────
        db_action_types = [
            row[0] for row in
            db.session.query(MovementHistory.action_type).distinct().order_by(MovementHistory.action_type).all()
        ]

        resp = make_response(render_template(
            'history.html',
            movements=movements_paginated,
            per_page=per_page,
            # Filter values (for form persistence)
            filter_q=q,
            filter_action_type=action_type,
            filter_date_from=date_from,
            filter_date_to=date_to,
            # Distinct action types from DB for dropdown
            db_action_types=db_action_types,
            all_action_types=_ALL_ACTION_TYPES,
        ))
        if save_cookie:
            resp.set_cookie(_COOKIE_KEY, str(per_page), max_age=365 * 24 * 3600, samesite='Lax')
        return resp

    @bp.route('/history/clear', methods=['POST'])
    def clear_history():
        """Delete all movement history records."""
        try:
            db.session.query(MovementHistory).delete()
            db.session.commit()
            app.logger.info("All movement history was cleared.")
        except Exception as e:
            db.session.rollback()
            app.logger.error(f"Error clearing movement history: {e}")
        return redirect(url_for('history'))
    app.register_blueprint(bp)
