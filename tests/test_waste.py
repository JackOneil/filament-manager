"""Tests for waste/scrap tracking module (routes/waste.py)."""
import os
import shutil
import tempfile
import unittest

from app import create_app
from auth import hash_password
from database import db
from models import Brand, Color, Filament, Material, User, WasteRecord


class WasteRecordTests(unittest.TestCase):
    """CRUD operations for waste records, admin-only access."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix='filament-waste-tests-')
        db_path = os.path.join(self.temp_dir, 'test.db')
        self.app = create_app({
            'TESTING': True,
            'SQLALCHEMY_DATABASE_URI': f'sqlite:///{db_path}',
            'PROJECT_UPLOAD_FOLDER': os.path.join(self.temp_dir, 'uploads'),
            'WTF_CSRF_ENABLED': False,
        })
        self.client = self.app.test_client()

        with self.app.app_context():
            brand = Brand.query.first()
            color = Color.query.first()
            material = Material.query.first()
            admin = User(
                email='admin@example.com',
                name='Admin',
                password_hash=hash_password('password123'),
                role='admin',
            )
            filament = Filament(
                name='Waste PLA',
                brand_id=brand.id,
                color_id=color.id,
                material_id=material.id,
                weight_total=1000,
                weight_remaining=800,
                price=500,
                quantity=1,
            )
            db.session.add_all([admin, filament])
            db.session.commit()
            self.filament_id = filament.id

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _login_admin(self):
        return self.client.post(
            '/login',
            data={'email': 'admin@example.com', 'password': 'password123'},
            follow_redirects=True,
        )

    # ── Smoke tests ────────────────────────────────────────────────────────

    def test_waste_index_renders_for_admin(self):
        self._login_admin()
        resp = self.client.get('/waste')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'waste', resp.data.lower())

    def test_waste_index_requires_login(self):
        resp = self.client.get('/waste', follow_redirects=False)
        # Unauthenticated → redirect to login
        self.assertIn(resp.status_code, (302, 403))

    # ── Add ────────────────────────────────────────────────────────────────

    def test_add_waste_record_creates_db_entry(self):
        self._login_admin()
        resp = self.client.post('/waste/add', data={
            'filament_id': str(self.filament_id),
            'weight_grams': '12.5',
            'reason': 'stringing',
            'notes': 'Too much stringing on top layer',
        }, follow_redirects=False)
        self.assertEqual(resp.status_code, 302)

        with self.app.app_context():
            rec = WasteRecord.query.first()
            self.assertIsNotNone(rec)
            self.assertAlmostEqual(rec.weight_grams, 12.5)
            self.assertEqual(rec.reason, 'stringing')
            self.assertEqual(rec.notes, 'Too much stringing on top layer')

    def test_add_waste_record_invalid_reason_defaults_to_other(self):
        self._login_admin()
        self.client.post('/waste/add', data={
            'filament_id': str(self.filament_id),
            'weight_grams': '5',
            'reason': 'totally_made_up_reason',
        }, follow_redirects=False)

        with self.app.app_context():
            rec = WasteRecord.query.first()
            self.assertIsNotNone(rec)
            self.assertEqual(rec.reason, 'other')

    def test_add_waste_record_without_filament_id_redirects_without_creating(self):
        self._login_admin()
        resp = self.client.post('/waste/add', data={
            'weight_grams': '5',
            'reason': 'warping',
        }, follow_redirects=False)
        # Should redirect (302) back to the form without creating a record
        self.assertEqual(resp.status_code, 302)

        with self.app.app_context():
            self.assertEqual(WasteRecord.query.count(), 0)

    # ── Edit ───────────────────────────────────────────────────────────────

    def test_edit_waste_record_updates_fields(self):
        self._login_admin()
        self.client.post('/waste/add', data={
            'filament_id': str(self.filament_id),
            'weight_grams': '10',
            'reason': 'warping',
        }, follow_redirects=False)

        with self.app.app_context():
            rec_id = WasteRecord.query.first().id

        resp = self.client.post(f'/waste/{rec_id}/edit', data={
            'filament_id': str(self.filament_id),
            'weight_grams': '20',
            'reason': 'clogging',
            'notes': 'Nozzle clogged mid-print',
        }, follow_redirects=False)
        self.assertEqual(resp.status_code, 302)

        with self.app.app_context():
            rec = db.session.get(WasteRecord, rec_id)
            self.assertAlmostEqual(rec.weight_grams, 20.0)
            self.assertEqual(rec.reason, 'clogging')
            self.assertEqual(rec.notes, 'Nozzle clogged mid-print')

    # ── Delete ─────────────────────────────────────────────────────────────

    def test_delete_waste_record_removes_db_entry(self):
        self._login_admin()
        self.client.post('/waste/add', data={
            'filament_id': str(self.filament_id),
            'weight_grams': '8',
            'reason': 'spaghetti',
        }, follow_redirects=False)

        with self.app.app_context():
            rec_id = WasteRecord.query.first().id

        resp = self.client.post(f'/waste/{rec_id}/delete', follow_redirects=False)
        self.assertEqual(resp.status_code, 302)

        with self.app.app_context():
            self.assertIsNone(db.session.get(WasteRecord, rec_id))


if __name__ == '__main__':
    unittest.main()
