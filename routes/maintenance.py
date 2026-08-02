"""Printer maintenance routes — service records, nozzle changes, calibration, fault history."""
import json
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from flask import abort, redirect, render_template, request, session, url_for, Response, Blueprint

from database import db
from models import AppSetting, BambuPrinter, BambuPrintJob, FilamentUndoLog, PrinterMaintenance, PrusaPrinter, PrusaPrintJob
from routes.inventory_helpers import _UNDO_SESSION_KEY
from utils import translate, utc_now, safe_commit


MAINTENANCE_TYPES = ('nozzle_change', 'calibration', 'service', 'fault', 'other')
RECURRENCE_TYPES = ('none', 'hours', 'days', 'months')

# Undo TTL for maintenance-record deletion — matches the filament undo window.
_MAINTENANCE_UNDO_TTL_MINUTES = 15


def _parse_dt_local(value):
    try:
        value = (value or '').strip()
        if not value:
            return utc_now()
        dt = datetime.strptime(value, '%Y-%m-%dT%H:%M')
        # The form value is a local wall-clock time — interpret it in the
        # configured app timezone and normalize to UTC for storage, so the
        # display (fmt_dt) round-trips to the same wall-clock time.
        tz_name = 'Europe/Prague'
        try:
            setting = AppSetting.query.first()
            tz_name = (setting.app_timezone or 'Europe/Prague') if setting else 'Europe/Prague'
        except Exception:
            pass
        return dt.replace(tzinfo=ZoneInfo(tz_name)).astimezone(timezone.utc)
    except (TypeError, ValueError):
        return utc_now()


def _parse_date(value):
    try:
        value = (value or '').strip()
        return datetime.strptime(value, '%Y-%m-%d') if value else None
    except (TypeError, ValueError):
        return None


def _coerce_positive_int(value, default=0):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _coerce_positive_float(value, default=0.0):
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _calculate_next_from_recurrence(performed_at, recurrence_type, recurrence_value):
    if recurrence_type == 'hours' and recurrence_value > 0:
        return performed_at + timedelta(hours=recurrence_value)
    if recurrence_type == 'days' and recurrence_value > 0:
        return performed_at + timedelta(days=recurrence_value)
    if recurrence_type == 'months' and recurrence_value > 0:
        return performed_at + timedelta(days=recurrence_value * 30)
    return None


def _usage_metrics(printer_type, printer_id, printer_name, since=None):
    runtime_hours = 0.0
    jobs_count = 0
    filament_grams = 0.0

    if printer_type == 'bambu':
        q = BambuPrintJob.query
        if printer_id:
            printer = db.session.get(BambuPrinter, printer_id)
            if printer and printer.device_id:
                q = q.filter(BambuPrintJob.device_id == printer.device_id)
            else:
                q = q.filter(BambuPrintJob.printer_name == printer_name)
        else:
            q = q.filter(BambuPrintJob.printer_name == printer_name)
        jobs = q.all()
        for job in jobs:
            ts = job.finished_at or job.synced_at or job.started_at
            if since and ts and ts < since:
                continue
            jobs_count += 1
            runtime_hours += max(float(job.cost_time or 0), 0.0) / 3600.0
            filament_grams += max(float(job.weight_grams or 0), 0.0)
        return {
            'runtime_hours': runtime_hours,
            'jobs_count': jobs_count,
            'filament_grams': filament_grams,
        }

    q = PrusaPrintJob.query
    if printer_id:
        q = q.filter(PrusaPrintJob.printer_id == printer_id)
    else:
        q = q.filter(PrusaPrintJob.printer_name == printer_name)
    jobs = q.all()
    for job in jobs:
        ts = job.finished_at or job.synced_at or job.started_at
        if since and ts and ts < since:
            continue
        jobs_count += 1
        runtime_hours += max(float(job.cost_time or 0), 0.0) / 3600.0
        filament_grams += max(float(job.weight_grams or 0), 0.0)
    return {
        'runtime_hours': runtime_hours,
        'jobs_count': jobs_count,
        'filament_grams': filament_grams,
    }


def _predictive_state(rec, now, cache):
    if not rec.predictive_enabled:
        return {
            'enabled': False,
            'predicted_next_at': None,
            'is_overdue': False,
            'stats': {},
        }

    key_since = (rec.printer_type, rec.printer_id, rec.printer_name, rec.performed_at.isoformat() if rec.performed_at else '')
    since_stats = cache.get(key_since)
    if since_stats is None:
        since_stats = _usage_metrics(rec.printer_type, rec.printer_id, rec.printer_name, rec.performed_at)
        cache[key_since] = since_stats

    targets = {
        'runtime_hours': max(float(rec.predictive_runtime_hours or 0.0), 0.0),
        'jobs_count': max(int(rec.predictive_jobs_count or 0), 0),
        'filament_grams': max(float(rec.predictive_filament_grams or 0.0), 0.0),
    }
    active = [k for k, v in targets.items() if v > 0]
    if not active:
        return {
            'enabled': True,
            'predicted_next_at': None,
            'is_overdue': False,
            'stats': since_stats,
        }

    is_overdue = False
    remaining = {}
    for key in active:
        current_val = float(since_stats.get(key, 0.0))
        rem = float(targets[key]) - current_val
        remaining[key] = rem
        if rem <= 0:
            is_overdue = True

    window_days = max(int(rec.predictive_window_days or 30), 1)
    window_start = now - timedelta(days=window_days)
    key_window = (rec.printer_type, rec.printer_id, rec.printer_name, window_start.date().isoformat())
    window_stats = cache.get(key_window)
    if window_stats is None:
        window_stats = _usage_metrics(rec.printer_type, rec.printer_id, rec.printer_name, window_start)
        cache[key_window] = window_stats

    predicted_days = []
    for key in active:
        rem = remaining.get(key, 0.0)
        if rem <= 0:
            continue
        rate_per_day = float(window_stats.get(key, 0.0)) / float(window_days)
        if rate_per_day <= 0:
            continue
        predicted_days.append(rem / rate_per_day)

    predicted_next_at = None
    if predicted_days:
        predicted_next_at = now + timedelta(days=min(predicted_days))

    return {
        'enabled': True,
        'predicted_next_at': predicted_next_at,
        'is_overdue': is_overdue,
        'stats': since_stats,
    }


def _sop_templates():
    return [
        {
            'id': 'nozzle_quick',
            'label': translate('maintenance_sop_nozzle_quick'),
            'notes': translate('maintenance_sop_nozzle_quick_notes'),
            'maintenance_type': 'nozzle_change',
        },
        {
            'id': 'calibration_full',
            'label': translate('maintenance_sop_calibration_full'),
            'notes': translate('maintenance_sop_calibration_full_notes'),
            'maintenance_type': 'calibration',
        },
        {
            'id': 'service_monthly',
            'label': translate('maintenance_sop_service_monthly'),
            'notes': translate('maintenance_sop_service_monthly_notes'),
            'maintenance_type': 'service',
        },
        {
            'id': 'fault_diagnosis',
            'label': translate('maintenance_sop_fault_diagnosis'),
            'notes': translate('maintenance_sop_fault_diagnosis_notes'),
            'maintenance_type': 'fault',
        },
    ]


def _validate_printer_exists(printer_type, printer_id):
    """Verify that the printer_id references a real printer in the DB."""
    if printer_id is None:
        return True  # No printer selected — valid (record is unattached)
    if printer_type == 'bambu':
        return db.session.get(BambuPrinter, printer_id) is not None
    elif printer_type == 'prusa':
        return db.session.get(PrusaPrinter, printer_id) is not None
    return False


def _apply_form_to_record(rec):
    printer_type = request.form.get('printer_type', 'bambu')
    if printer_type not in ('bambu', 'prusa'):
        printer_type = 'bambu'
    printer_id = request.form.get('printer_id', type=int)
    if printer_id is not None and not _validate_printer_exists(printer_type, printer_id):
        printer_id = None
    printer_name = request.form.get('printer_name', '').strip()
    maintenance_type = request.form.get('maintenance_type', 'other')
    if maintenance_type not in MAINTENANCE_TYPES:
        maintenance_type = 'other'
    notes = request.form.get('notes', '').strip() or None
    notes_is_markdown = request.form.get('notes_is_markdown') == '1'

    performed_at = _parse_dt_local(request.form.get('performed_at', ''))
    next_service_at = _parse_date(request.form.get('next_service_at', ''))

    recurrence_type = request.form.get('recurrence_type', 'none')
    if recurrence_type not in RECURRENCE_TYPES:
        recurrence_type = 'none'
    recurrence_value = request.form.get('recurrence_value', 0, type=int) or 0
    recurrence_enabled = request.form.get('recurrence_enabled') == '1'
    if recurrence_enabled and recurrence_type != 'none' and recurrence_value > 0 and not next_service_at:
        next_service_at = _calculate_next_from_recurrence(performed_at, recurrence_type, recurrence_value)

    predictive_enabled = request.form.get('predictive_enabled') == '1'
    predictive_runtime_hours = _coerce_positive_float(request.form.get('predictive_runtime_hours'), 0.0)
    predictive_jobs_count = _coerce_positive_int(request.form.get('predictive_jobs_count'), 0)
    predictive_filament_grams = _coerce_positive_float(request.form.get('predictive_filament_grams'), 0.0)
    predictive_window_days = _coerce_positive_int(request.form.get('predictive_window_days'), 30)
    if predictive_window_days <= 0:
        predictive_window_days = 30

    rec.printer_type = printer_type
    rec.printer_id = printer_id
    rec.printer_name = printer_name
    rec.maintenance_type = maintenance_type
    rec.notes = notes
    rec.notes_is_markdown = notes_is_markdown
    rec.performed_at = performed_at
    rec.next_service_at = next_service_at
    rec.recurrence_type = recurrence_type
    rec.recurrence_value = recurrence_value
    rec.recurrence_enabled = recurrence_enabled
    rec.predictive_enabled = predictive_enabled
    rec.predictive_runtime_hours = predictive_runtime_hours
    rec.predictive_jobs_count = predictive_jobs_count
    rec.predictive_filament_grams = predictive_filament_grams
    rec.predictive_window_days = predictive_window_days

    if rec.maintenance_type != 'fault':
        rec.fault_resolved = False
        rec.fault_resolved_at = None


def register(app):
    bp = Blueprint('maintenance', __name__)

    @bp.route('/maintenance')
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
        usage_cache = {}
        for rec in paginated.items:
            predictive_state = _predictive_state(rec, now, usage_cache)
            effective_next = rec.next_service_at
            if predictive_state['predicted_next_at'] and (not effective_next or predictive_state['predicted_next_at'] < effective_next):
                effective_next = predictive_state['predicted_next_at']

            is_overdue = bool((effective_next and effective_next < now) or predictive_state['is_overdue'])
            is_due_soon = bool(effective_next and not is_overdue and (effective_next - now).days <= 14)
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
                'effective_next': effective_next,
                'predictive': predictive_state,
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
            maintenance_types=list(MAINTENANCE_TYPES),
            recurrence_types=[('none', translate('maintenance_recurrence_none')), ('hours', translate('maintenance_recurrence_hours')), ('days', translate('maintenance_recurrence_days')), ('months', translate('maintenance_recurrence_months'))],
            sop_templates=_sop_templates(),
        )

    @bp.route('/maintenance/add', methods=['POST'])
    def maintenance_add():
        from auth import get_current_user, is_admin
        user = get_current_user()
        if not is_admin(user):
            abort(403)

        rec = PrinterMaintenance()
        _apply_form_to_record(rec)
        db.session.add(rec)
        safe_commit()
        return redirect(url_for('maintenance_index'))

    @bp.route('/maintenance/<int:rec_id>/edit', methods=['POST'])
    def maintenance_edit(rec_id):
        from auth import get_current_user, is_admin
        user = get_current_user()
        if not is_admin(user):
            abort(403)
        rec = db.get_or_404(PrinterMaintenance, rec_id)

        _apply_form_to_record(rec)

        safe_commit()
        return redirect(url_for('maintenance_index'))

    @bp.route('/maintenance/<int:rec_id>/duplicate', methods=['POST'])
    def maintenance_duplicate(rec_id):
        from auth import get_current_user, is_admin
        user = get_current_user()
        if not is_admin(user):
            abort(403)

        rec = db.get_or_404(PrinterMaintenance, rec_id)
        now = utc_now()
        next_service_at = rec.next_service_at
        if rec.recurrence_enabled and rec.recurrence_type != 'none' and rec.recurrence_value > 0:
            next_service_at = _calculate_next_from_recurrence(now, rec.recurrence_type, rec.recurrence_value)
        elif rec.next_service_at and rec.performed_at and rec.next_service_at > rec.performed_at:
            next_service_at = now + (rec.next_service_at - rec.performed_at)

        db.session.add(PrinterMaintenance(
            printer_type=rec.printer_type,
            printer_id=rec.printer_id,
            printer_name=rec.printer_name,
            maintenance_type=rec.maintenance_type,
            notes=rec.notes,
            notes_is_markdown=rec.notes_is_markdown,
            performed_at=now,
            next_service_at=next_service_at,
            recurrence_type=rec.recurrence_type,
            recurrence_value=rec.recurrence_value,
            recurrence_enabled=rec.recurrence_enabled,
            predictive_enabled=rec.predictive_enabled,
            predictive_runtime_hours=rec.predictive_runtime_hours,
            predictive_jobs_count=rec.predictive_jobs_count,
            predictive_filament_grams=rec.predictive_filament_grams,
            predictive_window_days=rec.predictive_window_days,
            fault_resolved=False,
            fault_resolved_at=None,
        ))
        safe_commit()
        return redirect(url_for('maintenance_index'))

    @bp.route('/maintenance/<int:rec_id>/schedule-30', methods=['POST'])
    def maintenance_schedule_30(rec_id):
        from auth import get_current_user, is_admin
        user = get_current_user()
        if not is_admin(user):
            abort(403)

        rec = db.get_or_404(PrinterMaintenance, rec_id)
        base = rec.next_service_at or utc_now()
        rec.next_service_at = base + timedelta(days=30)
        safe_commit()
        return redirect(url_for('maintenance_index'))

    @bp.route('/maintenance/<int:rec_id>/resolve-fault', methods=['POST'])
    def maintenance_resolve_fault(rec_id):
        from auth import get_current_user, is_admin
        user = get_current_user()
        if not is_admin(user):
            abort(403)

        rec = db.get_or_404(PrinterMaintenance, rec_id)
        if rec.maintenance_type == 'fault':
            rec.fault_resolved = True
            rec.fault_resolved_at = utc_now()
            safe_commit()
        return redirect(url_for('maintenance_index'))

    @bp.route('/maintenance/calendar.ics')
    def maintenance_ics():
        from auth import get_current_user, is_admin
        user = get_current_user()
        if not is_admin(user):
            abort(403)

        rows = PrinterMaintenance.query.filter(PrinterMaintenance.next_service_at.isnot(None)).order_by(PrinterMaintenance.next_service_at).all()

        def _fmt_dt(dt):
            return dt.strftime('%Y%m%dT%H%M%SZ')

        def _ics_escape(text):
            """Escape special iCalendar characters and strip newlines to prevent injection."""
            if not text:
                return ''
            # Strip all newline variants to prevent CRLF injection
            text = text.replace('\r\n', ' ').replace('\r', ' ').replace('\n', ' ')
            # Escape iCalendar special characters (backslash first to avoid double-escaping)
            text = text.replace('\\', '\\\\').replace(';', '\\;').replace(',', '\\,')
            return text

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
            summary = _ics_escape(f"{translate('maintenance_type_' + rec.maintenance_type)} — {rec.printer_name}")
            # RFC 5545 requires DTSTAMP (creation timestamp, UTC, basic format)
            dtstamp = utc_now().strftime('%Y%m%dT%H%M%SZ')
            lines.extend([
                'BEGIN:VEVENT',
                f'UID:{uid}',
                f'DTSTAMP:{dtstamp}',
                f'DTSTART:{dtstart}',
                f'DTEND:{dtend}',
                f'SUMMARY:{summary}',
                f'DESCRIPTION:{_ics_escape(rec.notes)}',
                f'CATEGORIES:3D Printer Maintenance',
                'END:VEVENT',
            ])
        lines.append('END:VCALENDAR')
        # RFC 5545 §3.1: lines longer than 75 octets must be folded with
        # CRLF + single space. Fold every line defensively.
        folded = []
        for line in lines:
            encoded = line.encode('utf-8')
            if len(encoded) <= 75:
                folded.append(line)
                continue
            parts = []
            for i in range(0, len(encoded), 73):
                parts.append(encoded[i:i + 73].decode('utf-8'))
            folded.append('\r\n '.join(parts))
        ics_content = '\r\n'.join(folded)
        return Response(ics_content, mimetype='text/calendar', headers={
            'Content-Disposition': 'attachment; filename=maintenance_calendar.ics'
        })

    @bp.route('/maintenance/<int:rec_id>/delete', methods=['POST'])
    def maintenance_delete(rec_id):
        from auth import get_current_user, is_admin
        user = get_current_user()
        if not is_admin(user):
            abort(403)
        rec = db.get_or_404(PrinterMaintenance, rec_id)

        # Create undo log
        undo_data = json.dumps({
            'printer_type': rec.printer_type,
            'printer_id': rec.printer_id,
            'printer_name': rec.printer_name,
            'maintenance_type': rec.maintenance_type,
            'notes': rec.notes,
            'notes_is_markdown': rec.notes_is_markdown,
            'performed_at': rec.performed_at.isoformat() if rec.performed_at else None,
            'next_service_at': rec.next_service_at.strftime('%Y-%m-%d') if rec.next_service_at else None,
            'recurrence_type': rec.recurrence_type,
            'recurrence_value': rec.recurrence_value,
            'recurrence_enabled': rec.recurrence_enabled,
            'predictive_enabled': rec.predictive_enabled,
            'predictive_runtime_hours': rec.predictive_runtime_hours,
            'predictive_jobs_count': rec.predictive_jobs_count,
            'predictive_filament_grams': rec.predictive_filament_grams,
            'predictive_window_days': rec.predictive_window_days,
        })
        undo_log = FilamentUndoLog(
            user_id=user.id,
            action_type='delete_maintenance',
            target_type='maintenance',
            target_key=undo_data,
            snapshot_data=None,
            expires_at=utc_now() + timedelta(minutes=_MAINTENANCE_UNDO_TTL_MINUTES),
        )
        db.session.add(undo_log)
        safe_commit()
        # Populate the undo toast slot so the toast renders on the redirect
        # and the /inventory/undo endpoint can consume the snapshot.
        session[_UNDO_SESSION_KEY] = {
            'undo_log_id': undo_log.id,
            'title_key': 'undo_toast_maintenance_delete_title',
            'detail': rec.printer_name or '',
        }

        db.session.delete(rec)
        safe_commit()
        return redirect(url_for('maintenance_index'))

    @bp.route('/maintenance/<int:rec_id>/data')
    def maintenance_data(rec_id):
        from auth import get_current_user, is_admin
        user = get_current_user()
        if not is_admin(user):
            abort(403)
        rec = db.get_or_404(PrinterMaintenance, rec_id)
        return {
            'printer_type': rec.printer_type,
            'printer_id': rec.printer_id,
            'printer_name': rec.printer_name,
            'maintenance_type': rec.maintenance_type,
            'notes': rec.notes or '',
            'notes_is_markdown': rec.notes_is_markdown or False,
            'performed_at': rec.performed_at.strftime('%Y-%m-%dT%H:%M') if rec.performed_at else '',
            'next_service_at': rec.next_service_at.strftime('%Y-%m-%d') if rec.next_service_at else '',
            'recurrence_type': rec.recurrence_type or 'none',
            'recurrence_value': rec.recurrence_value or 1,
            'recurrence_enabled': rec.recurrence_enabled or False,
            'predictive_enabled': rec.predictive_enabled or False,
            'predictive_runtime_hours': rec.predictive_runtime_hours or 0,
            'predictive_jobs_count': rec.predictive_jobs_count or 0,
            'predictive_filament_grams': rec.predictive_filament_grams or 0,
            'predictive_window_days': rec.predictive_window_days or 30,
        }
    app.register_blueprint(bp)
