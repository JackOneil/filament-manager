"""Printer maintenance routes — service records, nozzle changes, calibration, fault history."""
from datetime import datetime

from flask import abort, redirect, render_template, request, url_for

from auth import require_admin
from database import db
from models import BambuPrinter, PrinterMaintenance, PrusaPrinter
from utils import utc_now


def register(app):

    @app.route('/maintenance')
    def maintenance_index():
        from auth import get_current_user, is_admin
        user = get_current_user()
        if not is_admin(user):
            abort(403)

        filter_printer = request.args.get('printer', '')
        filter_type = request.args.get('type', '')
        page = request.args.get('page', 1, type=int)

        query = PrinterMaintenance.query.order_by(PrinterMaintenance.performed_at.desc())
        if filter_printer:
            query = query.filter(PrinterMaintenance.printer_name == filter_printer)
        if filter_type:
            query = query.filter(PrinterMaintenance.maintenance_type == filter_type)

        paginated = db.paginate(query.statement, page=page, per_page=20, error_out=False)

        bambu_printers = BambuPrinter.query.order_by(BambuPrinter.name).all()
        prusa_printers = PrusaPrinter.query.order_by(PrusaPrinter.name).all()
        all_printer_names = sorted(set(
            [p.name for p in bambu_printers] + [p.name for p in prusa_printers]
        ))

        now = utc_now()
        records = []
        for rec in paginated.items:
            is_overdue = rec.next_service_at and rec.next_service_at < now
            is_due_soon = (rec.next_service_at and not is_overdue and
                           (rec.next_service_at - now).days <= 14)
            records.append({
                'rec': rec,
                'is_overdue': is_overdue,
                'is_due_soon': is_due_soon,
            })

        return render_template(
            'maintenance.html',
            records=records,
            paginated=paginated,
            all_printer_names=all_printer_names,
            bambu_printers=bambu_printers,
            prusa_printers=prusa_printers,
            filter_printer=filter_printer,
            filter_type=filter_type,
            maintenance_types=['nozzle_change', 'calibration', 'service', 'fault', 'other'],
        )

    @app.route('/maintenance/add', methods=['POST'])
    def maintenance_add():
        from auth import get_current_user, is_admin
        user = get_current_user()
        if not is_admin(user):
            abort(403)

        printer_type = request.form.get('printer_type', 'bambu')
        printer_id = request.form.get('printer_id', type=int)
        printer_name = request.form.get('printer_name', '').strip()
        maintenance_type = request.form.get('maintenance_type', 'other')
        if maintenance_type not in ('nozzle_change', 'calibration', 'service', 'fault', 'other'):
            maintenance_type = 'other'
        notes = request.form.get('notes', '').strip() or None

        try:
            performed_at_raw = request.form.get('performed_at', '').strip()
            performed_at = datetime.strptime(performed_at_raw, '%Y-%m-%dT%H:%M') if performed_at_raw else utc_now()
        except (TypeError, ValueError):
            performed_at = utc_now()

        try:
            next_service_raw = request.form.get('next_service_at', '').strip()
            next_service_at = datetime.strptime(next_service_raw, '%Y-%m-%d') if next_service_raw else None
        except (TypeError, ValueError):
            next_service_at = None

        db.session.add(PrinterMaintenance(
            printer_type=printer_type,
            printer_id=printer_id,
            printer_name=printer_name,
            maintenance_type=maintenance_type,
            notes=notes,
            performed_at=performed_at,
            next_service_at=next_service_at,
        ))
        db.session.commit()
        return redirect(url_for('maintenance_index'))

    @app.route('/maintenance/<int:rec_id>/delete', methods=['POST'])
    def maintenance_delete(rec_id):
        from auth import get_current_user, is_admin
        user = get_current_user()
        if not is_admin(user):
            abort(403)
        rec = db.get_or_404(PrinterMaintenance, rec_id)
        db.session.delete(rec)
        db.session.commit()
        return redirect(url_for('maintenance_index'))
