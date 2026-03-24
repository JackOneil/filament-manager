import io
import os
import shutil
import tempfile
import unittest

from app import create_app
from database import db
from models import Project, ProjectFile


class ProjectUploadTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix='filament-tests-')
        db_path = os.path.join(self.temp_dir, 'test.db')
        upload_dir = os.path.join(self.temp_dir, 'uploads')

        self.app = create_app({
            'TESTING': True,
            'SQLALCHEMY_DATABASE_URI': f'sqlite:///{db_path}',
            'PROJECT_UPLOAD_FOLDER': upload_dir,
            'WTF_CSRF_ENABLED': False,
        })
        self.client = self.app.test_client()

        with self.app.app_context():
            project = Project(name='Test project')
            db.session.add(project)
            db.session.commit()
            self.project_id = project.id

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_rejects_unsupported_project_file_extension(self):
        response = self.client.post(
            f'/projects/{self.project_id}/upload',
            data={'file': (io.BytesIO(b'not allowed'), 'malware.exe')},
            content_type='multipart/form-data',
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn('Nepodporovaný typ souboru'.encode('utf-8'), response.data)

        with self.app.app_context():
            self.assertEqual(ProjectFile.query.count(), 0)

    def test_same_filename_is_stored_with_unique_identifier(self):
        response = self.client.post(
            f'/projects/{self.project_id}/upload',
            data={
                'file': [
                    (io.BytesIO(b'first model'), 'part.stl'),
                    (io.BytesIO(b'second model'), 'part.stl'),
                ]
            },
            content_type='multipart/form-data',
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)

        with self.app.app_context():
            files = ProjectFile.query.order_by(ProjectFile.id.asc()).all()
            self.assertEqual(len(files), 2)
            self.assertEqual(files[0].filename, 'part.stl')
            self.assertEqual(files[1].filename, 'part.stl')
            self.assertNotEqual(files[0].filepath, files[1].filepath)
            self.assertTrue(os.path.exists(files[0].filepath))
            self.assertTrue(os.path.exists(files[1].filepath))
