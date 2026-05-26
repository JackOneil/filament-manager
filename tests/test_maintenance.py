"""Tests for printer maintenance log module (routes/maintenance.py)."""
import os
import shutil
import tempfile
import unittest
from datetime import datetime

from app import create_app
from auth import hash_password
from database import db
from models import BambuPrinter, PrinterMaintenance, User


class MaintenanceRecordTests(unittest.TestCase):
    """CRUD operations for maintenance records and ICS calendar export."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix='filament-maintenance-tests-')
        db_path = os.path.join(self.temp_dir, 'test.db')
        self.app = create_app({
            'TESTING': True,
            'SQLALCHEMY_DATABASE_URI': f'sqlite:///{db_path}',
            'PROJECT_UPLOAD_FOLDER': os.path.join(self.temp_dir, 'uploads'),
            'WTF_CSRF_ENABLED': False,
        })
        self.client = self.app.test_client()

        with self.app.app_context():
            admin = User(
                email='admin@example.com',
                name='Admin',
                password_hash=hash_password('password123'),
                role='admin',
            )
            printer = BambuPrinter(
                device_id='DEV_MAINT_001',
                name='Test P1P',
                printer_model='P1P',
            )
            db.session.add_all([admin, printer])
            db.session.commit()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _login_admin(self):
        return self.client.post(
            '/login',
            data={'email': 'admin@example.com', 'password': 'password123'},
            follow_redirects=True,
        )

    # ── Smoke tests ────────────────────────────────────────────────────────

    def test_maintenance_index_renders_for_admin(self):
        self._login_admin()
        resp = self.client.get('/maintenance')
        self.assertEqual(resp.status_code, 200)

    def test_maintenance_index_requires_login(self):
        resp = self.client.get('/maintenance', follow_redirects=False)
        self.assertIn(resp.status_code, (302, 403))

    # ── Add ────────────────────────────────────────────────────────────────

    def test_add_maintenance_record_creates_db_entry(self):
        self._login_admin()
        resp = self.client.post('/maintenance/add', data={
            'printer_type': 'bambu',
            'printer_name': 'Test P1P',
            'maintenance_type': 'nozzle_change',
            'performed_at': '2026-05-01T10:00',
            'notes': 'Replaced 0.4mm nozzle',
        }, follow_redirects=False)
        self.assertEqual(resp.status_code, 302)

        with self.app.app_context():
            rec = PrinterMaintenance.query.first()
            self.assertIsNotNone(rec)
            self.assertEqual(rec.maintenance_type, 'nozzle_change')
            self.assertEqual(rec.printer_name, 'Test P1P')
            self.assertEqual(rec.notes, 'Replaced 0.4mm nozzle')

    def test_add_maintenance_invalid_type_defaults_to_other(self):
        self._login_admin()
        self.client.post('/maintenance/add', data={
            'printer_type': 'bambu',
            'printer_name': 'Test P1P',
            'maintenance_type': 'totally_invalid_type',
            'performed_at': '2026-05-01T10:00',
        }, follow_redirects=False)

        with self.app.app_context():
            rec = PrinterMaintenance.query.first()
            self.assertIsNotNone(rec)
            self.assertEqual(rec.maintenance_type, 'other')

    def test_add_maintenance_recurrence_auto_calculates_next_service(self):
        self._login_admin()
        self.client.post('/maintenance/add', data={
            'printer_type': 'bambu',
            'printer_name': 'Test P1P',
            'maintenance_type': 'service',
            'performed_at': '2026-05-01T10:00',
            'recurrence_enabled': '1',
            'recurrence_type': 'days',
            'recurrence_value': '30',
        }, follow_redirects=False)

        with self.app.app_context():
            rec = PrinterMaintenance.query.first()
            self.assertIsNotNone(rec)
            self.assertTrue(rec.recurrence_enabled)
            self.assertIsNotNone(rec.next_service_at)
            delta = (rec.next_service_at - rec.performed_at).days
            self.assertEqual(delta, 30)

    # ── Edit ───────────────────────────────────────────────────────────────

    def test_edit_maintenance_record_updates_fields(self):
        self._login_admin()
        self.client.post('/maintenance/add', data={
            'printer_type': 'bambu',
            'printer_name': 'Test P1P',
            'maintenance_type': 'calibration',
            'performed_at': '2026-05-01T10:00',
        }, follow_redirects=False)

        with self.app.app_context():
            rec_id = PrinterMaintenance.query.first().id

        resp = self.client.post(f'/maintenance/{rec_id}/edit', data={
            'printer_type': 'bambu',
            'printer_name': 'Test P1P',
            'maintenance_type': 'fault',
            'performed_at': '2026-05-10T12:00',
            'notes': 'Layer shift fault',
        }, follow_redirects=False)
        self.assertEqual(resp.status_code, 302)

        with self.app.app_context():
            rec = db.session.get(PrinterMaintenance, rec_id)
            self.assertEqual(rec.maintenance_type, 'fault')
            self.assertEqual(rec.notes, 'Layer shift fault')

    # ── Delete ─────────────────────────────────────────────────────────────

    def test_delete_maintenance_record_removes_db_entry(self):
        self._login_admin()
        self.client.post('/maintenance/add', data={
            'printer_type': 'bambu',
            'printer_name': 'Test P1P',
            'maintenance_type': 'service',
            'performed_at': '2026-05-01T10:00',
        }, follow_redirects=False)

        with self.app.app_context():
            rec_id = PrinterMaintenance.query.first().id

        resp = self.client.post(f'/maintenance/{rec_id}/delete', follow_redirects=False)
        self.assertEqual(resp.status_code, 302)

        with self.app.app_context():
            self.assertIsNone(db.session.get(PrinterMaintenance, rec_id))

    # ── ICS export ─────────────────────────────────────────────────────────

    def test_ics_export_contains_vcalendar_structure(self):
        self._login_admin()
        # Add a record with a future service date so it appears in the ICS feed
        self.client.post('/maintenance/add', data={
            'printer_type': 'bambu',
            'printer_name': 'Test P1P',
            'maintenance_type': 'nozzle_change',
            'performed_at': '2026-05-01T10:00',
            'next_service_at': '2026-06-01',
        }, follow_redirects=False)

        resp = self.client.get('/maintenance/calendar.ics')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('text/calendar', resp.content_type)
        body = resp.data.decode('utf-8')
        self.assertIn('BEGIN:VCALENDAR', body)
        self.assertIn('BEGIN:VEVENT', body)
        self.assertIn('END:VCALENDAR', body)

    def test_ics_export_contains_printer_name_in_summary(self):
        self._login_admin()
        self.client.post('/maintenance/add', data={
            'printer_type': 'bambu',
            'printer_name': 'My Printer X1',
            'maintenance_type': 'service',
            'performed_at': '2026-05-01T10:00',
            'next_service_at': '2026-07-01',
        }, follow_redirects=False)

        resp = self.client.get('/maintenance/calendar.ics')
        body = resp.data.decode('utf-8')
        self.assertIn('My Printer X1', body)


if __name__ == '__main__':
    unittest.main()
