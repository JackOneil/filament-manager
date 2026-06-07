"""Extended tests for waste tracking — file upload, serving, downloading, 
and deletion for waste record photo attachments."""
import io
import os
import shutil
import tempfile
import unittest

from app import create_app
from auth import hash_password
from database import db
from models import (
    AppSetting, Brand, Color, Filament, Material, User, WasteFile, WasteRecord,
)


class _BaseWasteExtTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix='waste-ext-tests-')
        db_path = os.path.join(self.temp_dir, 'test.db')
        upload_dir = os.path.join(self.temp_dir, 'uploads')
        os.makedirs(upload_dir, exist_ok=True)

        self.app = create_app({
            'TESTING': True,
            'AUTH_REQUIRED_IN_TESTS': True,
            'SQLALCHEMY_DATABASE_URI': f'sqlite:///{db_path}',
            'PROJECT_UPLOAD_FOLDER': upload_dir,
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
            brand = Brand.query.first()
            color = Color.query.first()
            material = Material.query.first()
            filament = Filament(
                name='Waste Ext PLA',
                brand_id=brand.id,
                color_id=color.id,
                material_id=material.id,
                weight_total=1000,
                weight_remaining=800,
                price=500,
                quantity=1,
            )
            self.waste_record = WasteRecord(
                filament_id=1,  # will get real ID after flush
                reason='stringing',
                weight_grams=15.0,
                notes='Test waste',
                recorded_by_user_id=1,
            )
            db.session.add_all([admin, filament])
            db.session.flush()
            self.filament_id = filament.id
            # Re-create waste record with real filament_id
            self.waste_record = WasteRecord(
                filament_id=self.filament_id,
                reason='stringing',
                weight_grams=15.0,
                notes='Test waste',
            )
            db.session.add(self.waste_record)
            db.session.commit()
            self.waste_id = self.waste_record.id
            self.admin_id = admin.id

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def login_admin(self):
        return self.client.post(
            '/login',
            data={'email': 'admin@example.com', 'password': 'password123'},
            follow_redirects=True,
        )


class WasteFileUploadTests(_BaseWasteExtTests):
    def _upload_waste_file(self, filename, content):
        """Helper to upload a waste file."""
        return self.client.post(
            f'/waste/{self.waste_id}/upload',
            data={
                'file': (io.BytesIO(content), filename),
            },
            content_type='multipart/form-data',
            follow_redirects=False,
        )

    def test_upload_waste_image(self):
        self.login_admin()
        response = self._upload_waste_file('photo.png', b'\x89PNG\r\n\x1a\n' + b'\x00' * 50)
        self.assertEqual(response.status_code, 302)

        with self.app.app_context():
            files = WasteFile.query.filter_by(waste_record_id=self.waste_id).all()
            self.assertEqual(len(files), 1)
            self.assertEqual(files[0].filename, 'photo.png')
            self.assertTrue(os.path.exists(files[0].filepath))

    def test_upload_invalid_extension_rejected(self):
        self.login_admin()
        response = self._upload_waste_file('document.pdf', b'not an image')
        self.assertEqual(response.status_code, 302)

        with self.app.app_context():
            count = WasteFile.query.filter_by(waste_record_id=self.waste_id).count()
            self.assertEqual(count, 0)

    def test_upload_waste_serves_file(self):
        self.login_admin()
        self._upload_waste_file('test_photo.png', b'fake-image-data')

        with self.app.app_context():
            wf = WasteFile.query.filter_by(waste_record_id=self.waste_id).first()
            file_id = wf.id

        response = self.client.get(f'/waste/file/{file_id}')
        self.assertEqual(response.status_code, 200)
        self.assertIn('image', response.content_type)

    def test_upload_waste_downloads_file(self):
        self.login_admin()
        self._upload_waste_file('download.png', b'download-data')

        with self.app.app_context():
            wf = WasteFile.query.filter_by(waste_record_id=self.waste_id).first()
            file_id = wf.id

        response = self.client.get(f'/waste/file/{file_id}/download')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, b'download-data')
        self.assertIn('attachment', response.headers.get('Content-Disposition', ''))

    def test_delete_waste_file(self):
        self.login_admin()
        self._upload_waste_file('delete.png', b'to-delete')

        with self.app.app_context():
            wf = WasteFile.query.filter_by(waste_record_id=self.waste_id).first()
            file_id = wf.id
            filepath = wf.filepath

        response = self.client.post(
            f'/waste/file/{file_id}/delete',
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)

        with self.app.app_context():
            self.assertIsNone(db.session.get(WasteFile, file_id))
            self.assertFalse(os.path.exists(filepath))

    def test_delete_nonexistent_waste_file_returns_404(self):
        self.login_admin()
        response = self.client.post('/waste/file/99999/delete',
                                     follow_redirects=False)
        self.assertEqual(response.status_code, 404)


# ── Waste Record Filters ────────────────────────────────────────────────

class WasteFilterTests(_BaseWasteExtTests):
    def test_waste_index_filter_by_reason(self):
        self.login_admin()
        response = self.client.get('/waste?reason=stringing')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'stringing', response.data)

    def test_waste_index_filter_by_filament(self):
        self.login_admin()
        response = self.client.get(f'/waste?filament={self.filament_id}')
        self.assertEqual(response.status_code, 200)

    def test_waste_index_empty_reason_filter(self):
        self.login_admin()
        response = self.client.get('/waste?reason=nonexistent')
        self.assertEqual(response.status_code, 200)

    def test_waste_index_pagination(self):
        self.login_admin()
        response = self.client.get('/waste?page=1')
        self.assertEqual(response.status_code, 200)


if __name__ == '__main__':
    unittest.main()
