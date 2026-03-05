"""Movement history route."""
from flask import render_template, request, redirect, url_for
from database import db
from models import MovementHistory
from utils import log_movement


def register(app):

    @app.route('/history')
    def history():
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 10, type=int)
        if per_page not in [10, 20, 50, 100]:
            per_page = 10

        movements_paginated = db.paginate(
            MovementHistory.query.order_by(MovementHistory.created_at.desc()),
            page=page, per_page=per_page, error_out=False,
        )

        return render_template('history.html', movements=movements_paginated, per_page=per_page)

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
