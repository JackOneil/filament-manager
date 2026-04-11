"""Movement history route."""
from flask import render_template, request, redirect, url_for, make_response
from database import db
from models import MovementHistory
from utils import log_movement

_VALID_PER_PAGE = [10, 20, 50, 100]
_COOKIE_KEY = 'history_per_page'


def register(app):

    @app.route('/history')
    def history():
        page = request.args.get('page', 1, type=int)

        # per_page priority: URL param > cookie > default (10)
        if 'per_page' in request.args:
            per_page = request.args.get('per_page', 10, type=int)
            if per_page not in _VALID_PER_PAGE:
                per_page = 10
            save_cookie = True
        else:
            # Read from cookie — no redirect needed
            try:
                per_page = int(request.cookies.get(_COOKIE_KEY, 10))
            except (TypeError, ValueError):
                per_page = 10
            if per_page not in _VALID_PER_PAGE:
                per_page = 10
            save_cookie = False

        movements_paginated = db.paginate(
            MovementHistory.query.order_by(MovementHistory.created_at.desc()),
            page=page, per_page=per_page, error_out=False,
        )

        resp = make_response(
            render_template('history.html', movements=movements_paginated, per_page=per_page)
        )
        if save_cookie:
            # Persist preference for 1 year; SameSite=Lax is safe for this.
            resp.set_cookie(_COOKIE_KEY, str(per_page), max_age=365 * 24 * 3600, samesite='Lax')
        return resp

    @app.route('/history/clear', methods=['POST'])
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
