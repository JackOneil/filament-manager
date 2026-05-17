"""Printer maintenance routes — service records, nozzle changes, calibration, fault history."""
from datetime import datetime, timedelta

from flask import abort, redirect, render_template, request, url_for, Response

from auth import require_admin
from database import db
from models import BambuPrinter, PrinterMaintenance, PrusaPrinter
from utils import translate, utc_now


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
            recurrence_text = ''
            if rec.recurrence_enabled and rec.recurrence_type != 'none':
                unit = rec.recurrence_type
                val = rec.recurrence_value
                if unit == 'hours':
                    recurrence_text = translate('maintenance_recurrence_every_hours').format(hours=val)
                elif unit == 'days':
                    recurrence_text = translate('maintenance_recurrence_every_days').format(days=val)
                elif unit == 'months':
                    recurrence_text = translate('maintenance_recurrence_every_months').format(months=val)
            records.append({
                'rec': rec,
                'is_overdue': is_overdue,
                'is_due_soon': is_due_soon,
                'recurrence_text': recurrence_text,
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
            recurrence_types=[('none', translate('maintenance_recurrence_none')), ('hours', translate('maintenance_recurrence_hours')), ('days', translate('maintenance_recurrence_days')), ('months', translate('maintenance_recurrence_months'))],
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

        recurrence_type = request.form.get('recurrence_type', 'none')
        if recurrence_type not in ('none', 'hours', 'days', 'months'):
            recurrence_type = 'none'
        recurrence_value = request.form.get('recurrence_value', 0, type=int) or 0
        recurrence_enabled = request.form.get('recurrence_enabled') == '1'

        # If recurrence is enabled and next_service_at is not explicitly set, auto-calculate it
        if recurrence_enabled and recurrence_type != 'none' and recurrence_value > 0 and not next_service_at:
            if recurrence_type == 'hours':
                next_service_at = performed_at + timedelta(hours=recurrence_value)
            elif recurrence_type == 'days':
                next_service_at = performed_at + timedelta(days=recurrence_value)
            elif recurrence_type == 'months':
                next_service_at = performed_at + timedelta(days=recurrence_value * 30)

        db.session.add(PrinterMaintenance(
            printer_type=printer_type,
            printer_id=printer_id,
            printer_name=printer_name,
            maintenance_type=maintenance_type,
            notes=notes,
            performed_at=performed_at,
            next_service_at=next_service_at,
            recurrence_type=recurrence_type,
            recurrence_value=recurrence_value,
            recurrence_enabled=recurrence_enabled,
        ))
        db.session.commit()
        return redirect(url_for('maintenance_index'))

    @app.route('/maintenance/<int:rec_id>/edit', methods=['POST'])
    def maintenance_edit(rec_id):
        from auth import get_current_user, is_admin
        user = get_current_user()
        if not is_admin(user):
            abort(403)
        rec = db.get_or_404(PrinterMaintenance, rec_id)

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

        rec.printer_type = printer_type
        rec.printer_id = printer_id
        rec.printer_name = printer_name
        rec.maintenance_type = maintenance_type
        rec.notes = notes
        rec.performed_at = performed_at
        rec.next_service_at = next_service_at

        recurrence_type = request.form.get('recurrence_type', 'none')
        if recurrence_type not in ('none', 'hours', 'days', 'months'):
            recurrence_type = 'none'
        recurrence_value = request.form.get('recurrence_value', 0, type=int) or 0
        recurrence_enabled = request.form.get('recurrence_enabled') == '1'

        # If recurrence is enabled and next_service_at is not explicitly set, auto-calculate it
        if recurrence_enabled and recurrence_type != 'none' and recurrence_value > 0 and not next_service_at:
            if recurrence_type == 'hours':
                next_service_at = performed_at + timedelta(hours=recurrence_value)
            elif recurrence_type == 'days':
                next_service_at = performed_at + timedelta(days=recurrence_value)
            elif recurrence_type == 'months':
                next_service_at = performed_at + timedelta(days=recurrence_value * 30)
            rec.next_service_at = next_service_at

        rec.recurrence_type = recurrence_type
        rec.recurrence_value = recurrence_value
        rec.recurrence_enabled = recurrence_enabled

        db.session.commit()
        return redirect(url_for('maintenance_index'))

    @app.route('/maintenance/calendar.ics')
    def maintenance_ics():
        from auth import get_current_user, is_admin
        user = get_current_user()
        if not is_admin(user):
            abort(403)

        rows = PrinterMaintenance.query.filter(PrinterMaintenance.next_service_at.isnot(None)).order_by(PrinterMaintenance.next_service_at).all()

        def _fmt_dt(dt):
            return dt.strftime('%Y%m%dT%H%M%SZ')

        lines = [
            'BEGIN:VCALENDAR',
            'VERSION:2.0',
            'PRODID:-//Filament Manager//Maintenance Calendar//EN',
            'CALSCALE:GREGORIAN',
            'METHOD:PUBLISH',
        ]
        for rec in rows:
            if not rec.next_service_at:
                continue
            uid = f'filament-maint-{rec.id}@filament-manager'
            dtstart = _fmt_dt(rec.next_service_at)
            dtend = _fmt_dt(rec.next_service_at + timedelta(hours=1))
            summary = f"{translate('maintenance_type_' + rec.maintenance_type)} — {rec.printer_name}"
            lines.extend([
                'BEGIN:VEVENT',
                f'UID:{uid}',
                f'DTSTART:{dtstart}',
                f'DTEND:{dtend}',
                f'SUMMARY:{summary}',
                f'DESCRIPTION:{rec.notes or ""}',
                f'CATEGORIES:3D Printer Maintenance',
                'END:VEVENT',
            ])
        lines.append('END:VCALENDAR')
        ics_content = '\r\n'.join(lines)
        return Response(ics_content, mimetype='text/calendar', headers={
            'Content-Disposition': 'attachment; filename=maintenance_calendar.ics'
        })

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
