"""Waste/scrap tracking — record failed prints with reason, weight, filament and project."""
from datetime import datetime

from flask import abort, redirect, render_template, request, url_for

from auth import require_admin
from database import db
from models import Filament, Project, WasteRecord, AppSetting
from utils import utc_now


WASTE_REASONS = ['stringing', 'warping', 'bed_adhesion', 'clogging', 'layer_shift', 'spaghetti', 'broken_support', 'other']


def register(app):

    @app.route('/waste')
    def waste_index():
        from auth import get_current_user, is_admin
        user = get_current_user()
        if not is_admin(user):
            abort(403)

        filter_reason = request.args.get('reason', '')
        filter_filament = request.args.get('filament', '')
        filter_project = request.args.get('project', '')
        page = request.args.get('page', 1, type=int)

        query = WasteRecord.query.order_by(WasteRecord.created_at.desc())
        if filter_reason and filter_reason in WASTE_REASONS:
            query = query.filter(WasteRecord.reason == filter_reason)
        if filter_filament:
            query = query.filter(WasteRecord.filament_id == filter_filament)
        if filter_project:
            query = query.filter(WasteRecord.project_id == filter_project)

        paginated = db.paginate(query.statement, page=page, per_page=20, error_out=False)

        filaments = Filament.query.order_by(Filament.name).all()
        projects = Project.query.order_by(Project.name).all()

        total_waste = sum(r.weight_grams for r in WasteRecord.query.all())

        return render_template(
            'waste.html',
            records=paginated.items,
            paginated=paginated,
            filaments=filaments,
            projects=projects,
            waste_reasons=WASTE_REASONS,
            filter_reason=filter_reason,
            filter_filament=filter_filament,
            filter_project=filter_project,
            total_waste=total_waste,
        )

    @app.route('/waste/add', methods=['POST'])
    def waste_add():
        from auth import get_current_user, is_admin
        user = get_current_user()
        if not is_admin(user):
            abort(403)

        filament_id = request.form.get('filament_id', type=int)
        project_id = request.form.get('project_id', type=int) or None
        reason = request.form.get('reason', 'other')
        if reason not in WASTE_REASONS:
            reason = 'other'
        notes = request.form.get('notes', '').strip() or None

        try:
            weight_grams = float(request.form.get('weight_grams', 0))
            if weight_grams <= 0:
                weight_grams = 0.0
        except (TypeError, ValueError):
            weight_grams = 0.0

        if not filament_id:
            return redirect(url_for('waste_index'))

        db.session.add(WasteRecord(
            filament_id=filament_id,
            project_id=project_id,
            reason=reason,
            weight_grams=weight_grams,
            notes=notes,
            recorded_by_user_id=user.id if user else None,
        ))
        db.session.commit()
        return redirect(url_for('waste_index'))

    @app.route('/waste/<int:rec_id>/delete', methods=['POST'])
    def waste_delete(rec_id):
        from auth import get_current_user, is_admin
        user = get_current_user()
        if not is_admin(user):
            abort(403)
        rec = db.get_or_404(WasteRecord, rec_id)
        db.session.delete(rec)
        db.session.commit()
        return redirect(url_for('waste_index'))
