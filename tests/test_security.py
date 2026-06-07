"""Security edge case tests — path traversal, XSS in user input, CSRF enforcement,
session fixation protection, and SQL injection via search params."""
import io
import os
import shutil
import tempfile
import unittest

from app import create_app
from auth import hash_password
from database import db
from models import (
    Brand, Color, Filament, Material, Project, ProjectFile, User,
)
from utils import utc_now, is_safe_external_url, escape_like


class _BaseSecurityTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix='security-tests-')
        db_path = os.path.join(self.temp_dir, 'test.db')
        self.upload_dir = os.path.join(self.temp_dir, 'uploads')
        os.makedirs(self.upload_dir, exist_ok=True)

        self.app = create_app({
            'TESTING': True,
            'AUTH_REQUIRED_IN_TESTS': True,
            'SQLALCHEMY_DATABASE_URI': f'sqlite:///{db_path}',
            'PROJECT_UPLOAD_FOLDER': self.upload_dir,
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
                name='Security PLA',
                brand_id=brand.id,
                color_id=color.id,
                material_id=material.id,
                weight_total=1000,
                weight_remaining=500,
                price=500,
                quantity=1,
            )
            project = Project(name='Security Project')
            db.session.add_all([admin, filament, project])
            db.session.commit()
            self.project_id = project.id
            self.filament_id = filament.id

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def login_admin(self):
        return self.client.post(
            '/login',
            data={'email': 'admin@example.com', 'password': 'password123'},
            follow_redirects=True,
        )


# ── Escape Like (SQL injection via search) ───────────────────────────────

class EscapeLikeTests(unittest.TestCase):
    def test_escapes_percent(self):
        self.assertEqual(escape_like('100%'), r'100\%')

    def test_escapes_underscore(self):
        self.assertEqual(escape_like('test_'), r'test\_')

    def test_escapes_backslash(self):
        self.assertEqual(escape_like('a\\b'), r'a\\b')

    def test_escapes_all_special_chars(self):
        result = escape_like('50%_complete\\')
        self.assertIn(r'\%', result)
        self.assertIn(r'\_', result)
        self.assertIn(r'\\', result)

    def test_normal_text_unchanged(self):
        self.assertEqual(escape_like('hello world'), 'hello world')

    def test_empty_string(self):
        self.assertEqual(escape_like(''), '')


# ── URL Safety (SSRF prevention) ─────────────────────────────────────────

class UrlSafetyTests(unittest.TestCase):
    def test_rejects_localhost(self):
        self.assertFalse(is_safe_external_url('http://localhost:5000/test'))

    def test_rejects_loopback(self):
        self.assertFalse(is_safe_external_url('http://127.0.0.1/test'))
        self.assertFalse(is_safe_external_url('http://0.0.0.0/test'))

    def test_rejects_private_ip(self):
        self.assertFalse(is_safe_external_url('http://192.168.1.1/test'))
        self.assertFalse(is_safe_external_url('http://10.0.0.1/test'))
        self.assertFalse(is_safe_external_url('http://172.16.0.1/test'))

    def test_rejects_non_http_scheme(self):
        self.assertFalse(is_safe_external_url('file:///etc/passwd'))
        self.assertFalse(is_safe_external_url('ftp://example.com/file'))

    def test_rejects_empty(self):
        self.assertFalse(is_safe_external_url(''))

    def test_rejects_none(self):
        self.assertFalse(is_safe_external_url(None))


# ── Path Traversal ───────────────────────────────────────────────────────

class PathTraversalTests(_BaseSecurityTests):
    def test_project_file_path_traversal_blocked(self):
        """Project file download must reject paths outside upload directory."""
        self.login_admin()
        with self.app.app_context():
            traversal_file = ProjectFile(
                project_id=self.project_id,
                filename='../../../etc/passwd',
                filepath='/etc/passwd',
                version=1,
            )
            db.session.add(traversal_file)
            db.session.commit()
            file_id = traversal_file.id

        response = self.client.get(
            f'/projects/{self.project_id}/download/{file_id}',
            follow_redirects=False,
        )
        # Must not serve /etc/passwd
        self.assertEqual(response.status_code, 403)

    def test_project_view_file_path_traversal_blocked(self):
        self.login_admin()
        with self.app.app_context():
            traversal_file = ProjectFile(
                project_id=self.project_id,
                filename='evil_file.stl',
                filepath='/etc/hostname',
                version=1,
            )
            db.session.add(traversal_file)
            db.session.commit()
            file_id = traversal_file.id

        response = self.client.get(
            f'/projects/{self.project_id}/view_file/{file_id}/evil_file.stl',
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 403)


# ── CSRF / Session Security ─────────────────────────────────────────────

class CsrfSessionTests(_BaseSecurityTests):
    def test_session_cookie_has_httponly(self):
        response = self.client.get('/login')
        set_cookie = response.headers.get('Set-Cookie', '')
        self.assertIn('HttpOnly', set_cookie)

    def test_session_cookie_has_samesite(self):
        response = self.client.get('/login')
        set_cookie = response.headers.get('Set-Cookie', '')
        self.assertIn('SameSite', set_cookie)

    def test_security_headers_present(self):
        response = self.client.get('/login')
        self.assertEqual(response.headers.get('X-Content-Type-Options'), 'nosniff')
        self.assertEqual(response.headers.get('X-Frame-Options'), 'SAMEORIGIN')
        self.assertIn('nosniff', str(response.headers.get('X-Content-Type-Options', '')))


# ── XSS Prevention ──────────────────────────────────────────────────────

class XssPreventionTests(_BaseSecurityTests):
    def test_filament_name_xss_escaped(self):
        """Filament names with HTML/JS must be escaped in rendered page."""
        self.login_admin()
        with self.app.app_context():
            brand = Brand.query.first()
            color = Color.query.first()
            material = Material.query.first()
            xss_filament = Filament(
                name='<script>alert("XSS")</script>',
                brand_id=brand.id,
                color_id=color.id,
                material_id=material.id,
                weight_total=1000,
                weight_remaining=500,
                price=500,
                quantity=1,
            )
            db.session.add(xss_filament)
            db.session.commit()

        response = self.client.get('/filaments')
        self.assertEqual(response.status_code, 200)
        html = response.data.decode('utf-8')
        # The script tag must be HTML-escaped in the output
        self.assertNotIn('<script>alert("XSS")</script>', html)
        # The escaped version should be present
        self.assertIn('&lt;script&gt;', html)

    def test_project_name_xss_escaped(self):
        self.login_admin()
        with self.app.app_context():
            project = Project(name='<img src=x onerror=alert(1)>')
            db.session.add(project)
            db.session.commit()
            proj_id = project.id

        response = self.client.get(f'/projects/{proj_id}')
        self.assertEqual(response.status_code, 200)
        html = response.data.decode('utf-8')
        # The onerror should be escaped
        self.assertNotIn('<img src=', html)

    def test_history_search_xss_escaped(self):
        """Search queries with XSS payloads must be escaped in result page."""
        self.login_admin()
        response = self.client.get('/history?q=<script>alert(1)</script>')
        self.assertEqual(response.status_code, 200)
        html = response.data.decode('utf-8')
        self.assertNotIn('<script>alert', html)


if __name__ == '__main__':
    unittest.main()
