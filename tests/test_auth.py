import os
import shutil
import tempfile
import unittest

from app import create_app
from auth import hash_password, password_needs_rehash
from database import db
from models import Filament, Brand, Color, Material, Notification, Project, User


class AuthAccessTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix='filament-auth-tests-')
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
            brand = Brand.query.first()
            color = Color.query.first()
            material = Material.query.first()
            admin = User(
                email='admin@example.com',
                name='Admin',
                password_hash=hash_password('password123'),
                role='admin',
            )
            user = User(
                email='user@example.com',
                name='User',
                password_hash=hash_password('password123'),
                role='user',
            )
            db.session.add_all([admin, user])
            db.session.flush()
            db.session.add_all([
                Project(name='Admin project', owner_user_id=admin.id, created_by_user_id=admin.id, status='APPROVED'),
                Project(name='User project', owner_user_id=user.id, created_by_user_id=user.id, status='PENDING_APPROVAL'),
                Filament(
                    name='Prusament PLA Black',
                    brand_id=brand.id,
                    color_id=color.id,
                    material_id=material.id,
                    weight_total=1000,
                    weight_remaining=850,
                    price=599,
                    quantity=1,
                ),
            ])
            db.session.commit()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def login(self, email):
        return self.client.post('/login', data={'email': email, 'password': 'password123'}, follow_redirects=True)

    def test_protected_route_redirects_to_login(self):
        response = self.client.get('/projects', follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login', response.headers['Location'])

    def test_passwords_are_hashed_with_modern_scheme(self):
        hashed = hash_password('password123')
        self.assertNotEqual(hashed, 'password123')
        self.assertTrue(hashed.startswith('scrypt:'))
        self.assertFalse(password_needs_rehash(hashed))

    def test_user_sees_only_owned_projects(self):
        self.login('user@example.com')
        response = self.client.get('/projects')
        html = response.data.decode('utf-8')
        self.assertEqual(response.status_code, 200)
        self.assertIn('User project', html)
        self.assertNotIn('Admin project', html)

    def test_user_cannot_open_foreign_project(self):
        self.login('user@example.com')
        response = self.client.get('/projects/1')
        self.assertEqual(response.status_code, 404)

    def test_admin_can_open_user_management(self):
        self.login('admin@example.com')
        response = self.client.get('/users')
        self.assertEqual(response.status_code, 200)
        self.assertIn('user@example.com', response.data.decode('utf-8'))

    def test_admin_can_open_user_detail(self):
        self.login('admin@example.com')
        response = self.client.get('/users/2')
        self.assertEqual(response.status_code, 200)
        html = response.data.decode('utf-8')
        self.assertIn('user@example.com', html)
        self.assertIn('Přístupová práva', html)

    def test_user_cannot_open_user_management(self):
        self.login('user@example.com')
        response = self.client.get('/users')
        self.assertEqual(response.status_code, 403)
        self.assertIn('Na tuto část aplikace nemáte přístup', response.data.decode('utf-8'))

    def test_user_filaments_page_hides_admin_actions_and_prices(self):
        self.login('user@example.com')
        response = self.client.get('/filaments')
        self.assertEqual(response.status_code, 200)
        html = response.data.decode('utf-8')
        self.assertIn('Prusament PLA Black', html)
        self.assertNotIn('/add', html)
        self.assertNotIn('599.00', html)
        self.assertNotIn('subtract_usage', html)
        self.assertNotIn('/filament/1', html)

    def test_user_cannot_open_filament_detail_or_edit(self):
        self.login('user@example.com')
        detail_response = self.client.get('/filament/1')
        edit_response = self.client.get('/edit/1')
        self.assertEqual(detail_response.status_code, 403)
        self.assertEqual(edit_response.status_code, 403)

    def test_user_filaments_page_is_paginated(self):
        with self.app.app_context():
            brand = Brand.query.first()
            color = Color.query.first()
            material = Material.query.first()
            for idx in range(2, 16):
                db.session.add(Filament(
                    name=f'Filament {idx}',
                    brand_id=brand.id,
                    color_id=color.id,
                    material_id=material.id,
                    weight_total=1000,
                    weight_remaining=700,
                    price=400,
                    quantity=1,
                ))
            db.session.commit()

        self.login('user@example.com')
        response_page_1 = self.client.get('/filaments')
        response_page_2 = self.client.get('/filaments?page=2')
        html_page_1 = response_page_1.data.decode('utf-8')
        html_page_2 = response_page_2.data.decode('utf-8')

        self.assertEqual(response_page_1.status_code, 200)
        self.assertEqual(response_page_2.status_code, 200)
        self.assertIn('Strana 1 z 2', html_page_1)
        self.assertIn('Filament 12', html_page_1)
        self.assertIn('Strana 2 z 2', html_page_2)
        self.assertNotIn('Prusament PLA Black', html_page_1)
        self.assertIn('Prusament PLA Black', html_page_2)

    def test_user_filaments_page_supports_custom_per_page(self):
        with self.app.app_context():
            brand = Brand.query.first()
            color = Color.query.first()
            material = Material.query.first()
            for idx in range(2, 16):
                db.session.add(Filament(
                    name=f'Filament {idx}',
                    brand_id=brand.id,
                    color_id=color.id,
                    material_id=material.id,
                    weight_total=1000,
                    weight_remaining=700,
                    price=400,
                    quantity=1,
                ))
            db.session.commit()

        self.login('user@example.com')
        response = self.client.get('/filaments?per_page=24')
        html = response.data.decode('utf-8')

        self.assertEqual(response.status_code, 200)
        self.assertIn('option value="24" selected', html)
        self.assertIn('Prusament PLA Black', html)
        self.assertIn('Filament 15', html)
        self.assertNotIn('Strana 1 z 2', html)

    def test_user_project_create_uses_account_name_as_client(self):
        self.login('user@example.com')
        response = self.client.get('/projects/create')
        self.assertEqual(response.status_code, 200)
        html = response.data.decode('utf-8')
        self.assertIn('User', html)
        self.assertNotIn('name="client_name"', html)

        self.client.post(
            '/projects/create',
            data={
                'name': 'New request',
                'description': 'Please print this',
                'client_name': 'Injected client',
            },
            follow_redirects=False,
        )

        with self.app.app_context():
            project = Project.query.filter_by(name='New request').first()
            self.assertIsNotNone(project)
            self.assertEqual(project.client_name, 'User')

    def test_notifications_are_paginated(self):
        with self.app.app_context():
            user = User.query.filter_by(email='user@example.com').first()
            for idx in range(25):
                db.session.add(Notification(
                    user_id=user.id,
                    title=f'Notification {idx}',
                    body='Body',
                ))
            db.session.commit()

        self.login('user@example.com')
        response_page_1 = self.client.get('/notifications')
        response_page_2 = self.client.get('/notifications?page=2')
        html_page_1 = response_page_1.data.decode('utf-8')
        html_page_2 = response_page_2.data.decode('utf-8')

        self.assertEqual(response_page_1.status_code, 200)
        self.assertEqual(response_page_2.status_code, 200)
        self.assertIn('Strana 1 z 2', html_page_1)
        self.assertIn('Strana 2 z 2', html_page_2)

    def test_login_rejects_external_next_redirect(self):
        response = self.client.post(
            '/login?next=https://evil.example/phish',
            data={'email': 'user@example.com', 'password': 'password123'},
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers['Location'], '/')

    def test_security_headers_are_present(self):
        response = self.client.get('/login')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get('X-Content-Type-Options'), 'nosniff')
        self.assertEqual(response.headers.get('X-Frame-Options'), 'SAMEORIGIN')
        self.assertEqual(response.headers.get('Referrer-Policy'), 'strict-origin-when-cross-origin')
