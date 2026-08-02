"""Tests for translated, entity-aware application breadcrumbs."""
import os
import shutil
import tempfile
import unittest

from app import create_app
from database import db
from models import Brand, Color, Filament, Material, Project
from utils.breadcrumbs import build_breadcrumbs


class BreadcrumbTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix='breadcrumb-tests-')
        self.app = create_app({
            'TESTING': True,
            'SQLALCHEMY_DATABASE_URI': f"sqlite:///{os.path.join(self.temp_dir, 'test.db')}",
            'PROJECT_UPLOAD_FOLDER': os.path.join(self.temp_dir, 'uploads'),
            'WTF_CSRF_ENABLED': False,
        })
        with self.app.app_context():
            brand = Brand.query.first()
            material = Material.query.first()
            color = Color.query.first()
            self.filament = Filament(
                name='<script>alert(1)</script>',
                brand_id=brand.id,
                material_id=material.id,
                color_id=color.id,
                weight_total=1000,
                weight_remaining=1000,
                price=100,
                quantity=1,
            )
            self.project = Project(name='Breadcrumb project', status='NEW')
            db.session.add_all([self.filament, self.project])
            db.session.commit()
            self.filament_id = self.filament.id

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_detail_breadcrumb_uses_plain_entity_name(self):
        with self.app.test_request_context('/filament/1'):
            crumbs = build_breadcrumbs(
                lambda key: {'title': 'Filament Manager', 'filaments_nav': 'Filaments'}.get(key, key),
                'inventory.filament_detail',
                {'id': self.filament_id},
            )
        self.assertEqual(crumbs[-1]['label'], '<script>alert(1)</script>')
        self.assertIsNone(crumbs[-1]['url'])

    def test_public_page_does_not_link_to_protected_sections(self):
        with self.app.test_request_context('/projects/share/token'):
            crumbs = build_breadcrumbs(lambda key: key, 'projects.project_share', {'token': 'token'})
        self.assertEqual(len(crumbs), 1)
        self.assertIsNone(crumbs[0]['url'])

    def test_unknown_endpoint_keeps_safe_fallback(self):
        with self.app.test_request_context('/'):
            crumbs = build_breadcrumbs(lambda key: key, 'unknown.endpoint', {})
        self.assertEqual(crumbs[-1]['label'], 'nav_admin_tools')
        self.assertIsNone(crumbs[-1]['url'])
