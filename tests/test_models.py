import io
import os
import shutil
import tempfile
import unittest
import hashlib
from datetime import datetime

from app import create_app
from auth import hash_password
from database import db
from models import Project, ProjectFile, User, AppSetting
from utils import utc_now


class ModelsFeatureTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix='filament-model-tests-')
        db_path = os.path.join(self.temp_dir, 'test.db')
        self.upload_dir = os.path.join(self.temp_dir, 'uploads')
        os.makedirs(self.upload_dir, exist_ok=True)

        self.app = create_app({
            'TESTING': True,
            'SQLALCHEMY_DATABASE_URI': f'sqlite:///{db_path}',
            'PROJECT_UPLOAD_FOLDER': self.upload_dir,
            'WTF_CSRF_ENABLED': False,
            'AUTH_REQUIRED_IN_TESTS': True,
        })
        self.client = self.app.test_client()

        with self.app.app_context():
            # Setup users
            self.admin = User(
                email='admin@example.com',
                name='Admin User',
                password_hash=hash_password('password123'),
                role='admin'
            )
            self.user1 = User(
                email='user1@example.com',
                name='User One',
                password_hash=hash_password('password123'),
                role='user'
            )
            self.user2 = User(
                email='user2@example.com',
                name='User Two',
                password_hash=hash_password('password123'),
                role='user'
            )
            db.session.add_all([self.admin, self.user1, self.user2])
            db.session.flush()

            # Setup projects
            self.project1 = Project(name='Alpha Project', owner_user_id=self.user1.id)
            self.project2 = Project(name='Beta Project', owner_user_id=self.user2.id)
            db.session.add_all([self.project1, self.project2])
            db.session.flush()

            self.project1_id = self.project1.id
            self.project2_id = self.project2.id
            self.user1_id = self.user1.id
            self.user2_id = self.user2.id

            db.session.commit()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def login(self, email):
        self.client.post('/logout', follow_redirects=True)
        return self.client.post('/login', data={'email': email, 'password': 'password123'}, follow_redirects=True)

    def test_list_contains_only_supported_3d_file_extensions(self):
        self.login('admin@example.com')
        
        # Create some files under project 1
        with self.app.app_context():
            file_stl = ProjectFile(
                project_id=self.project1_id,
                filename='test_model.stl',
                filepath=os.path.join(self.upload_dir, 'test_model.stl'),
                version=1
            )
            file_3mf = ProjectFile(
                project_id=self.project1_id,
                filename='test_model.3mf',
                filepath=os.path.join(self.upload_dir, 'test_model.3mf'),
                version=1
            )
            file_txt = ProjectFile(
                project_id=self.project1_id,
                filename='notes.txt',
                filepath=os.path.join(self.upload_dir, 'notes.txt'),
                version=1
            )
            db.session.add_all([file_stl, file_3mf, file_txt])
            db.session.commit()

        # Call the api list
        response = self.client.get('/api/models-list')
        self.assertEqual(response.status_code, 200)
        
        data = response.get_json()
        html = data['html']

        # stl and 3mf should be present, txt should not
        self.assertIn('test_model.stl', html)
        self.assertIn('test_model.3mf', html)
        self.assertNotIn('notes.txt', html)

    def test_sorting_and_filtering(self):
        self.login('admin@example.com')

        with self.app.app_context():
            # Add files to different projects with different display names and sizes
            f1 = ProjectFile(
                project_id=self.project1_id,
                filename='cube.stl',
                filepath=os.path.join(self.upload_dir, 'cube.stl'),
                display_name='Cube Model',
                file_size_bytes=1000,
                version=1
            )
            f2 = ProjectFile(
                project_id=self.project2_id,
                filename='sphere.3mf',
                filepath=os.path.join(self.upload_dir, 'sphere.3mf'),
                display_name='Sphere Model',
                file_size_bytes=5000,
                version=1
            )
            db.session.add_all([f1, f2])
            db.session.commit()

        # Filter by project 1
        res = self.client.get(f'/api/models-list?project_id={self.project1_id}')
        html = res.get_json()['html']
        self.assertIn('Cube Model', html)
        self.assertNotIn('Sphere Model', html)

        # Filter by file type 3mf
        res = self.client.get('/api/models-list?file_type=3mf')
        html = res.get_json()['html']
        self.assertNotIn('Cube Model', html)
        self.assertIn('Sphere Model', html)

        # Search fulltext
        res = self.client.get('/api/models-list?fulltext=sphere')
        html = res.get_json()['html']
        self.assertNotIn('Cube Model', html)
        self.assertIn('Sphere Model', html)

        # Sort by size
        res = self.client.get('/api/models-list?sort_by=size_desc')
        html = res.get_json()['html']
        # Sphere Model (5000) should appear before Cube Model (1000)
        self.assertLess(html.index('Sphere Model'), html.index('Cube Model'))

    def test_model_editing_metadata(self):
        self.login('user1@example.com')

        with self.app.app_context():
            f = ProjectFile(
                project_id=self.project1_id,
                filename='nozzle.stl',
                filepath=os.path.join(self.upload_dir, 'nozzle.stl'),
                display_name='Initial Name',
                version=1
            )
            db.session.add(f)
            db.session.commit()
            file_id = f.id

        # Edit metadata
        response = self.client.post(
            f'/models/{file_id}/edit',
            data={
                'display_name': 'Updated Model Name',
                'version_note': 'First version note'
            },
            follow_redirects=True
        )
        self.assertEqual(response.status_code, 200)

        with self.app.app_context():
            file_obj = db.session.get(ProjectFile, file_id)
            self.assertEqual(file_obj.display_name, 'Updated Model Name')
            self.assertEqual(file_obj.version_note, 'First version note')

    def test_upload_new_version_increments_and_chains(self):
        self.login('user1@example.com')

        with self.app.app_context():
            f = ProjectFile(
                project_id=self.project1_id,
                filename='gear.stl',
                filepath=os.path.join(self.upload_dir, 'gear.stl'),
                display_name='Custom Gear',
                version=1
            )
            db.session.add(f)
            db.session.commit()
            root_id = f.id

        # Upload a new version
        file_data = b'updated binary content'
        response = self.client.post(
            f'/models/{root_id}/upload-version',
            data={
                'file': (io.BytesIO(file_data), 'gear_v2.stl'),
                'version_note': 'Uploaded second version'
            },
            content_type='multipart/form-data',
            follow_redirects=True
        )
        self.assertEqual(response.status_code, 200)

        with self.app.app_context():
            root_file = db.session.get(ProjectFile, root_id)
            self.assertEqual(len(root_file.versions), 1)
            
            child_file = root_file.versions[0]
            self.assertEqual(child_file.version, 2)
            self.assertEqual(child_file.parent_file_id, root_id)
            self.assertEqual(child_file.filename, 'gear_v2.stl')
            self.assertEqual(child_file.version_note, 'Uploaded second version')
            self.assertEqual(child_file.file_size_bytes, len(file_data))

    def test_same_checksum_warning(self):
        self.login('user1@example.com')

        with self.app.app_context():
            f = ProjectFile(
                project_id=self.project1_id,
                filename='plate.stl',
                filepath=os.path.join(self.upload_dir, 'plate.stl'),
                display_name='Plate',
                version=1,
                checksum_sha256=hashlib.sha256(b'same content').hexdigest()
            )
            db.session.add(f)
            db.session.commit()
            root_id = f.id

        # Upload version with same content
        response = self.client.post(
            f'/models/{root_id}/upload-version',
            data={
                'file': (io.BytesIO(b'same content'), 'plate_new.stl'),
                'version_note': 'No changes really'
            },
            content_type='multipart/form-data',
            follow_redirects=True
        )
        self.assertEqual(response.status_code, 200)
        # Verify same_checksum parameter was redirected with 'same_checksum=1'
        self.assertIn(b'same_checksum=1', response.data or b'')

    def test_download_version_endpoints(self):
        self.login('user1@example.com')

        # Create physical files in upload folder
        filepath = os.path.join(self.upload_dir, 'bracket.stl')
        with open(filepath, 'wb') as f:
            f.write(b'bracket model data')

        with self.app.app_context():
            root_file = ProjectFile(
                project_id=self.project1_id,
                filename='bracket.stl',
                filepath=filepath,
                version=1
            )
            db.session.add(root_file)
            db.session.commit()
            root_id = root_file.id

        # Download latest
        response = self.client.get(f'/models/{root_id}/download')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, b'bracket model data')
        self.assertIn('attachment', response.headers.get('Content-Disposition', ''))

        # Download specific version
        response = self.client.get(f'/models/version/{root_id}/download')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, b'bracket model data')

        # View specific version (inline)
        response = self.client.get(f'/models/version/{root_id}/view/bracket.stl')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, b'bracket model data')
        self.assertNotIn('attachment', response.headers.get('Content-Disposition', ''))

    def test_path_traversal_protection(self):
        self.login('admin@example.com')

        with self.app.app_context():
            # Stored filepath pointing to system directory (outside sandbox)
            traversal_file = ProjectFile(
                project_id=self.project1_id,
                filename='etc_passwd.stl',
                filepath='/etc/passwd',
                version=1
            )
            db.session.add(traversal_file)
            db.session.commit()
            file_id = traversal_file.id

        response = self.client.get(f'/models/version/{file_id}/download')
        # Path traversal should be blocked with 403 Forbidden
        self.assertEqual(response.status_code, 403)

    def test_role_based_permissions(self):
        # 1. User 1 logs in
        self.login('user1@example.com')

        with self.app.app_context():
            # Project 1 is owned by User 1
            f1 = ProjectFile(
                project_id=self.project1_id,
                filename='user1_model.stl',
                filepath=os.path.join(self.upload_dir, 'user1_model.stl'),
                display_name='User1 Owned',
                version=1
            )
            # Project 2 is owned by User 2
            f2 = ProjectFile(
                project_id=self.project2_id,
                filename='user2_model.stl',
                filepath=os.path.join(self.upload_dir, 'user2_model.stl'),
                display_name='User2 Owned',
                version=1
            )
            db.session.add_all([f1, f2])
            db.session.commit()
            f1_id = f1.id
            f2_id = f2.id

        # User 1 can see owned project files
        res = self.client.get('/api/models-list')
        html = res.get_json()['html']
        self.assertIn('User1 Owned', html)
        self.assertNotIn('User2 Owned', html)

        # User 1 can view detail of owned model
        res = self.client.get(f'/models/{f1_id}')
        self.assertEqual(res.status_code, 200)

        # User 1 cannot view details of other's model
        res = self.client.get(f'/models/{f2_id}')
        self.assertEqual(res.status_code, 404)

        # User 1 cannot edit other's model
        res = self.client.post(f'/models/{f2_id}/edit', data={'display_name': 'Hacked'})
        self.assertEqual(res.status_code, 404)

        # User 2 logs in
        self.login('user2@example.com')
        res = self.client.get('/api/models-list')
        html = res.get_json()['html']
        self.assertNotIn('User1 Owned', html)
        self.assertIn('User2 Owned', html)

        # Admin logs in
        self.login('admin@example.com')
        # Admin can see all model files
        res = self.client.get('/api/models-list')
        html = res.get_json()['html']
        self.assertIn('User1 Owned', html)
        self.assertIn('User2 Owned', html)

    def test_model_public_share_with_valid_token(self):
        """Public (no-auth) share view with a valid token."""
        self.login('admin@example.com')

        # Create a model file and generate a share token
        with self.app.app_context():
            root_file = ProjectFile(
                project_id=self.project1_id,
                filename='public_model.stl',
                filepath=os.path.join(self.upload_dir, 'public_model.stl'),
                version=1,
                file_size_bytes=1024,
                share_token='public-test-token-123',
            )
            # Create a physical file so the page renders
            with open(root_file.filepath, 'w') as f:
                f.write('dummy model data')
            db.session.add(root_file)
            db.session.commit()
            self.root_file_id = root_file.id

        # Access public share WITHOUT login
        self.client.get('/logout', follow_redirects=True)
        response = self.client.get('/models/share/public-test-token-123')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'public_model.stl', response.data)

    def test_model_public_share_with_invalid_token(self):
        """Public (no-auth) share view with an invalid token returns 404."""
        self.client.get('/logout', follow_redirects=True)
        response = self.client.get('/models/share/invalid-token-xyz')
        self.assertEqual(response.status_code, 404)

    def test_model_generate_and_revoke_share_token(self):
        """Generate a share token for a model, then revoke it."""
        self.login('admin@example.com')

        with self.app.app_context():
            root_file = ProjectFile(
                project_id=self.project1_id,
                filename='shareable.stl',
                filepath=os.path.join(self.upload_dir, 'shareable.stl'),
                version=1,
            )
            with open(root_file.filepath, 'w') as f:
                f.write('shareable data')
            db.session.add(root_file)
            db.session.commit()
            root_id = root_file.id

        # Generate share token
        resp = self.client.post(f'/models/{root_id}/share/generate', follow_redirects=True)
        self.assertEqual(resp.status_code, 200)

        with self.app.app_context():
            f = db.session.get(ProjectFile, root_id)
            self.assertIsNotNone(f.share_token)

        # Revoke share token
        resp = self.client.post(f'/models/{root_id}/share/revoke', follow_redirects=True)
        self.assertEqual(resp.status_code, 200)

        with self.app.app_context():
            f = db.session.get(ProjectFile, root_id)
            self.assertIsNone(f.share_token)

