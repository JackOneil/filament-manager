import io
import os
import shutil
import tempfile
import unittest

from app import create_app
from auth import hash_password
from database import db
from models import Project, ProjectComment, ProjectFile, ProjectTodo, User


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

    def test_delete_file_removes_uploaded_model_file(self):
        self.client.post(
            f'/projects/{self.project_id}/upload',
            data={'file': (io.BytesIO(b'model data'), 'part.stl')},
            content_type='multipart/form-data',
            follow_redirects=False,
        )

        with self.app.app_context():
            project_file = ProjectFile.query.first()
            self.assertIsNotNone(project_file)
            self.assertTrue(os.path.exists(project_file.filepath))
            file_id = project_file.id
            filepath = project_file.filepath

        response = self.client.post(f'/projects/{self.project_id}/delete_file/{file_id}', follow_redirects=False)
        self.assertEqual(response.status_code, 302)

        with self.app.app_context():
            self.assertIsNone(db.session.get(ProjectFile, file_id))
            self.assertFalse(os.path.exists(filepath))


class ProjectSortingTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix='filament-project-sort-')
        db_path = os.path.join(self.temp_dir, 'test.db')
        self.app = create_app({
            'TESTING': True,
            'SQLALCHEMY_DATABASE_URI': f'sqlite:///{db_path}',
            'PROJECT_UPLOAD_FOLDER': os.path.join(self.temp_dir, 'uploads'),
            'WTF_CSRF_ENABLED': False,
        })
        self.client = self.app.test_client()

        with self.app.app_context():
            db.session.add_all([
                Project(name='Zulu Project'),
                Project(name='Alpha Project'),
            ])
            db.session.commit()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_projects_can_be_sorted_by_name(self):
        response = self.client.get('/projects?sort_by=name')
        self.assertEqual(response.status_code, 200)
        html = response.data.decode('utf-8')
        self.assertLess(html.index('Alpha Project'), html.index('Zulu Project'))

    def test_projects_list_is_paginated_using_app_setting(self):
        with self.app.app_context():
            for idx in range(13):
                db.session.add(Project(name=f'Paged Project {idx:02d}'))
            db.session.commit()

        response = self.client.get('/projects?sort_by=name')
        self.assertEqual(response.status_code, 200)
        html = response.data.decode('utf-8')
        self.assertIn('Paged Project 00', html)
        self.assertNotIn('Paged Project 12', html)
        self.assertIn('?sort_by=name&amp;page=2', html)

    def test_project_client_is_rendered_as_filter_link(self):
        with self.app.app_context():
            db.session.add(Project(name='Client Filter Project', client_name='ACME Studio'))
            db.session.commit()

        response = self.client.get('/projects?sort_by=name')
        self.assertEqual(response.status_code, 200)
        html = response.data.decode('utf-8')
        self.assertIn('>ACME Studio</a>', html)
        self.assertIn('?sort_by=name&amp;page=1&amp;client=ACME+Studio', html)

        filtered_response = self.client.get('/projects?sort_by=name&client=ACME+Studio')
        self.assertEqual(filtered_response.status_code, 200)
        filtered_html = filtered_response.data.decode('utf-8')
        self.assertIn('Zrušit filtry', filtered_html)


class ProjectCollaborationTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix='filament-project-collab-')
        db_path = os.path.join(self.temp_dir, 'test.db')
        self.app = create_app({
            'TESTING': True,
            'AUTH_REQUIRED_IN_TESTS': True,
            'SQLALCHEMY_DATABASE_URI': f'sqlite:///{db_path}',
            'PROJECT_UPLOAD_FOLDER': os.path.join(self.temp_dir, 'uploads'),
            'WTF_CSRF_ENABLED': False,
        })
        self.client = self.app.test_client()

        with self.app.app_context():
            owner = User(
                email='owner@example.com',
                name='Owner',
                password_hash=hash_password('password123'),
                role='user',
            )
            other = User(
                email='other@example.com',
                name='Other',
                password_hash=hash_password('password123'),
                role='user',
            )
            admin = User(
                email='admin@example.com',
                name='Admin',
                password_hash=hash_password('password123'),
                role='admin',
            )
            db.session.add_all([owner, other, admin])
            db.session.flush()

            project = Project(
                name='Collab project',
                owner_user_id=owner.id,
                created_by_user_id=owner.id,
                status='PENDING_APPROVAL',
            )
            db.session.add(project)
            db.session.flush()

            comment = ProjectComment(
                project_id=project.id,
                user_id=owner.id,
                body='Initial **comment**',
            )
            db.session.add(comment)
            db.session.commit()

            self.project_id = project.id
            self.comment_id = comment.id
            self.owner_id = owner.id
            self.other_id = other.id
            self.admin_id = admin.id

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def login(self, email):
        self.client.post('/logout', follow_redirects=True)
        return self.client.post('/login', data={'email': email, 'password': 'password123'}, follow_redirects=True)

    def test_comment_markdown_is_rendered_in_project_detail(self):
        self.login('owner@example.com')
        response = self.client.post(
            f'/projects/{self.project_id}/comments',
            data={'body': '**Bold** [link](https://example.com)'},
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        html = response.data.decode('utf-8')
        self.assertIn('<strong>Bold</strong>', html)
        self.assertIn('href="https://example.com"', html)

    def test_only_comment_author_can_edit_comment(self):
        client_admin = self.app.test_client()
        client_admin.post('/login', data={'email': 'admin@example.com', 'password': 'password123'}, follow_redirects=True)
        response = client_admin.post(
            f'/projects/{self.project_id}/comments/{self.comment_id}/edit',
            data={'body': 'Hijacked'},
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 403)

        client_owner = self.app.test_client()
        client_owner.post('/login', data={'email': 'owner@example.com', 'password': 'password123'}, follow_redirects=True)
        response = client_owner.post(
            f'/projects/{self.project_id}/comments/{self.comment_id}/edit',
            data={'body': 'Updated **comment**'},
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)

        with self.app.app_context():
            comment = db.session.get(ProjectComment, self.comment_id)
            self.assertEqual(comment.body, 'Updated **comment**')
            self.assertIsNotNone(comment.updated_at)

    def test_project_todos_can_be_added_and_toggled(self):
        self.login('owner@example.com')
        add_response = self.client.post(
            f'/projects/{self.project_id}/todos',
            data={'body': 'Prepare print profile'},
            follow_redirects=False,
        )
        self.assertEqual(add_response.status_code, 302)

        with self.app.app_context():
            todo = ProjectTodo.query.filter_by(project_id=self.project_id, body='Prepare print profile').first()
            self.assertIsNotNone(todo)
            self.assertFalse(todo.is_done)
            todo_id = todo.id

        toggle_response = self.client.post(
            f'/projects/{self.project_id}/todos/{todo_id}/toggle',
            follow_redirects=False,
        )
        self.assertEqual(toggle_response.status_code, 302)

        with self.app.app_context():
            todo = db.session.get(ProjectTodo, todo_id)
            self.assertTrue(todo.is_done)
            self.assertIsNotNone(todo.completed_at)
