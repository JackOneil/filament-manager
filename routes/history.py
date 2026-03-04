"""Movement history route."""
from flask import render_template, request
from database import db
from models import MovementHistory


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
