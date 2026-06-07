"""Smoke performance benchmarks — verify that key pages render within 
acceptable time limits under the test environment's capabilities."""
import os
import shutil
import tempfile
import time
import unittest

from app import create_app
from auth import hash_password
from database import db
from models import (
    AppSetting, Brand, Color, Filament, Material, Project, User,
)
from utils import utc_now


class _BasePerfTests(unittest.TestCase):
    """Base with a realistic dataset of 50 filaments + 20 projects."""

    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.mkdtemp(prefix='perf-tests-')
        db_path = os.path.join(cls.temp_dir, 'test.db')
        cls.app = create_app({
            'TESTING': True,
            'AUTH_REQUIRED_IN_TESTS': True,
            'SQLALCHEMY_DATABASE_URI': f'sqlite:///{db_path}',
            'PROJECT_UPLOAD_FOLDER': os.path.join(cls.temp_dir, 'uploads'),
            'WTF_CSRF_ENABLED': False,
        })
        cls.client = cls.app.test_client()

        with cls.app.app_context():
            admin = User(
                email='admin@example.com',
                name='Admin',
                password_hash=hash_password('password123'),
                role='admin',
            )
            db.session.add(admin)

            brand = Brand.query.filter_by(name='Prusament').first()
            color = Color.query.first()
            material = Material.query.filter_by(name='PLA').first()

            # Create 50 filaments
            for i in range(50):
                f = Filament(
                    name=f'Perf Filament {i:03d}',
                    brand_id=brand.id,
                    color_id=color.id,
                    material_id=material.id,
                    weight_total=1000,
                    weight_remaining=800 - i,
                    price=500 + i,
                    quantity=1,
                    tag_text=f'tag_{i % 10}',
                )
                db.session.add(f)

            # Create 20 projects
            for i in range(20):
                p = Project(
                    name=f'Perf Project {i:03d}',
                    status=['NEW', 'PENDING_APPROVAL', 'APPROVED', 'PRINTING', 'DONE'][i % 5],
                )
                db.session.add(p)

            db.session.commit()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.temp_dir, ignore_errors=True)

    def _login_admin(self):
        return self.client.post(
            '/login',
            data={'email': 'admin@example.com', 'password': 'password123'},
            follow_redirects=True,
        )

    def _measure(self, method, url, **kwargs):
        start = time.monotonic()
        response = method(url, **kwargs)
        elapsed = (time.monotonic() - start) * 1000  # ms
        return response, elapsed


class PerformanceBenchmarkTests(_BasePerfTests):
    """Each test verifies the page returns 200 and measures response time.
    
    Time limits are intentionally generous for CI environments — the goal
    is catching severe regressions (multi-second page loads), not measuring
    absolute performance.
    """

    def setUp(self):
        self._login_admin()

    def test_inventory_page_under_2s(self):
        response, elapsed = self._measure(self.client.get, '/filaments')
        self.assertEqual(response.status_code, 200)
        self.assertLess(elapsed, 2000, f'Inventory page took {elapsed:.0f}ms')

    def test_projects_page_under_2s(self):
        response, elapsed = self._measure(self.client.get, '/projects')
        self.assertEqual(response.status_code, 200)
        self.assertLess(elapsed, 2000, f'Projects page took {elapsed:.0f}ms')

    def test_stats_page_under_3s(self):
        response, elapsed = self._measure(self.client.get, '/stats')
        self.assertEqual(response.status_code, 200)
        self.assertLess(elapsed, 3000, f'Stats page took {elapsed:.0f}ms')

    def test_history_page_under_2s(self):
        response, elapsed = self._measure(self.client.get, '/history')
        self.assertEqual(response.status_code, 200)
        self.assertLess(elapsed, 2000, f'History page took {elapsed:.0f}ms')

    def test_calculator_page_under_2s(self):
        response, elapsed = self._measure(self.client.get, '/calculator')
        self.assertEqual(response.status_code, 200)
        self.assertLess(elapsed, 2000, f'Calculator page took {elapsed:.0f}ms')

    def test_overview_page_under_2s(self):
        response, elapsed = self._measure(self.client.get, '/')
        self.assertEqual(response.status_code, 200)
        self.assertLess(elapsed, 2000, f'Overview page took {elapsed:.0f}ms')

    def test_settings_page_under_2s(self):
        response, elapsed = self._measure(self.client.get, '/settings')
        self.assertEqual(response.status_code, 200)
        self.assertLess(elapsed, 2000, f'Settings page took {elapsed:.0f}ms')


if __name__ == '__main__':
    unittest.main()
