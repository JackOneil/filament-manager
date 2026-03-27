import io
import json
import os
import shutil
import tempfile
import unittest

from app import create_app
from database import db
from models import Brand, Color, Filament, Material, Project, ProjectQuote


class ImportAtomicityTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix='filament-import-tests-')
        db_path = os.path.join(self.temp_dir, 'test.db')
        self.app = create_app({
            'TESTING': True,
            'SQLALCHEMY_DATABASE_URI': f'sqlite:///{db_path}',
            'PROJECT_UPLOAD_FOLDER': os.path.join(self.temp_dir, 'uploads'),
            'WTF_CSRF_ENABLED': False,
        })
        self.client = self.app.test_client()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_import_rolls_back_everything_when_later_stage_fails(self):
        payload = {
            'brands': ['Atomic Brand'],
            'materials': ['PLA'],
            'colors': [{'name': 'Atomic Color', 'hex_value': '#123456'}],
            'filaments': [{
                'name': 'Atomic Filament',
                'brand': 'Atomic Brand',
                'material': 'PLA',
                'color': 'Atomic Color',
                'weight_total': 1000,
                'weight_remaining': 1000,
                'price': 500,
                'quantity': 1,
            }],
            'bambu_jobs': [{
                'external_id': 'BROKEN_JOB',
                'printer_name': 'P1P',
                'printer_model': 'P1P',
                'device_id': 'DEV_BROKEN',
                'model_name': 'Broken import',
                'status': 'FINISH',
                'weight_grams': 10,
                'cost_time': 60,
                'started_at': 'not-a-date',
                'finished_at': None,
                'synced_at': None,
                'deducted': False,
                'filament_name': None,
                'project_name': None,
                'materials': [],
            }],
        }

        response = self.client.post(
            '/import',
            data={'file': (io.BytesIO(json.dumps(payload).encode('utf-8')), 'backup.json')},
            content_type='multipart/form-data',
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)

        with self.app.app_context():
            self.assertIsNone(Brand.query.filter_by(name='Atomic Brand').first())
            self.assertIsNone(Filament.query.filter_by(name='Atomic Filament').first())

    def test_export_and_import_include_project_quotes(self):
        with self.app.app_context():
            project = Project(name='Quoted Project')
            db_path_brand = Brand.query.filter_by(name='Prusament').first()
            color = Color.query.first()
            material = Material.query.filter_by(name='PLA').first()
            filament = Filament(
                name='Quoted Filament',
                brand_id=db_path_brand.id,
                material_id=material.id,
                color_id=color.id,
                weight_total=1000,
                weight_remaining=900,
                price=500,
                quantity=1,
            )
            db.session.add_all([project, filament])
            db.session.flush()
            db.session.add(ProjectQuote(
                project_id=project.id,
                filament_id=filament.id,
                filament_name='Quoted Filament | Prusament PLA',
                weight=120,
                print_time=3.5,
                material_cost=60,
                electricity_cost=2,
                base_cost=62,
                margin_percent=30,
                margin_amount=18.6,
                final_price=80.6,
                currency='CZK',
            ))
            db.session.commit()

        export_response = self.client.get('/export')
        self.assertEqual(export_response.status_code, 200)
        exported = export_response.get_json()
        self.assertEqual(exported['projects'][0]['quotes'][0]['final_price'], 80.6)

        with self.app.app_context():
            db.drop_all()
            db.create_all()

        import_response = self.client.post(
            '/import',
            data={'file': (io.BytesIO(json.dumps(exported).encode('utf-8')), 'backup.json')},
            content_type='multipart/form-data',
            follow_redirects=False,
        )

        self.assertEqual(import_response.status_code, 302)

        with self.app.app_context():
            quote = ProjectQuote.query.first()
            self.assertIsNotNone(quote)
            self.assertEqual(quote.final_price, 80.6)


if __name__ == '__main__':
    unittest.main()
