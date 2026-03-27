import os
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta

from app import create_app
from database import db
from models import BambuPrintJob, Brand, Color, Filament, Material, MovementHistory, Project, ProjectFilament
from utils import log_movement


class StatsDashboardTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix='stats-tests-')
        db_path = os.path.join(self.temp_dir, 'test.db')
        self.app = create_app({
            'TESTING': True,
            'SQLALCHEMY_DATABASE_URI': f'sqlite:///{db_path}',
            'PROJECT_UPLOAD_FOLDER': os.path.join(self.temp_dir, 'uploads'),
            'WTF_CSRF_ENABLED': False,
        })
        self.client = self.app.test_client()

        with self.app.app_context():
            brand = Brand.query.filter_by(name='Prusament').first()
            material = Material.query.filter_by(name='PLA').first()
            color = Color.query.first()

            filament = Filament(
                name='PLA Basic',
                brand_id=brand.id,
                material_id=material.id,
                color_id=color.id,
                weight_total=1000.0,
                weight_remaining=10.0,
                price=500.0,
                quantity=1,
            )
            project = Project(name='Case Build', status='PRINTING')
            db.session.add_all([filament, project])
            db.session.flush()

            db.session.add(ProjectFilament(
                project_id=project.id,
                filament_id=filament.id,
                estimated_weight=25.0,
                is_used=True,
            ))
            db.session.add(BambuPrintJob(
                external_id='job-1',
                model_name='Case Lid',
                project_id=project.id,
                filament_id=filament.id,
                deducted=True,
                weight_grams=40.0,
            ))

            log_movement(filament, 'add', 1000.0)
            log_movement(filament, 'remove', 30.0)
            log_movement(filament, 'bambu_print', 30.0)
            db.session.commit()

            movements = MovementHistory.query.order_by(MovementHistory.id.asc()).all()
            movements[0].created_at = datetime.utcnow() - timedelta(days=3)
            movements[1].created_at = datetime.utcnow() - timedelta(days=2)
            movements[2].created_at = datetime.utcnow() - timedelta(days=1)
            db.session.commit()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_stats_dashboard_renders_aggregated_usage_project_and_forecast(self):
        response = self.client.get('/stats?days=30')

        self.assertEqual(response.status_code, 200)
        html = response.data.decode('utf-8')

        self.assertIn('Statistiky skladu a spotřeby', html)
        self.assertIn('60.0 g', html)
        self.assertIn('1000.0 g', html)
        self.assertIn('Case Build', html)
        self.assertIn('65.0 g', html)
        self.assertIn('PLA Basic', html)
        self.assertIn('Objednat hned', html)
