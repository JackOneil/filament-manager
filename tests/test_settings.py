import io
import json
import os
import shutil
import tempfile
import unittest

from app import create_app
from database import db
from models import (
    BambuPrintJob, Brand, Color, Filament, Material, MovementHistory,
    Project, ProjectFile, ProjectQuote, StoragePlacement, StorageShelf,
)


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

    def test_export_and_import_preserve_new_filament_fields_and_movement_links(self):
        with self.app.app_context():
            brand = Brand.query.filter_by(name='Prusament').first()
            color = Color.query.first()
            material = Material.query.filter_by(name='PLA').first()
            project = Project(name='Backup Project', tag_text='customer, rush')
            filament = Filament(
                name='Backup Filament',
                brand_id=brand.id,
                material_id=material.id,
                color_id=color.id,
                weight_total=1000,
                weight_remaining=640,
                price=720,
                quantity=1,
                min_stock_grams=250,
                max_stock_grams=2000,
                tag_text='matte, proto',
                quality_stringing='low',
                quality_adhesion='great',
                quality_drying='dry box',
                quality_profile='0.20 structural',
                quality_notes='stable',
                recommended_nozzle_temp=220,
                recommended_bed_temp=60,
            )
            db.session.add_all([project, filament])
            db.session.flush()
            db.session.add(ProjectFile(project_id=project.id, filename='sample.3mf', filepath='/tmp/sample.3mf'))
            job = BambuPrintJob(external_id='BKP-1', model_name='Backup job', filament_id=filament.id, project_id=project.id)
            db.session.add(job)
            db.session.flush()
            db.session.add(MovementHistory(
                filament_id=filament.id,
                project_id=project.id,
                bambu_job_id=job.id,
                filament_name='Backup Filament | Prusament PLA',
                action_type='bambu_print',
                weight=42,
                cost=30,
                currency='CZK',
                note='Linked movement',
            ))
            db.session.commit()

        exported = self.client.get('/export').get_json()

        with self.app.app_context():
            db.drop_all()
            db.create_all()

        response = self.client.post(
            '/import',
            data={'file': (io.BytesIO(json.dumps(exported).encode('utf-8')), 'backup.json')},
            content_type='multipart/form-data',
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)

        with self.app.app_context():
            filament = Filament.query.filter_by(name='Backup Filament').first()
            self.assertIsNotNone(filament)
            self.assertEqual(filament.min_stock_grams, 250)
            self.assertEqual(filament.tag_text, 'matte, proto')
            self.assertEqual(filament.quality_profile, '0.20 structural')
            self.assertEqual(filament.recommended_nozzle_temp, 220)

            movement = MovementHistory.query.filter_by(note='Linked movement').first()
            self.assertIsNotNone(movement)
            self.assertIsNotNone(movement.project_id)
            self.assertIsNotNone(movement.bambu_job_id)
            self.assertIsNotNone(ProjectFile.query.filter_by(filename='sample.3mf').first())

    def test_export_and_import_preserve_storage_layout(self):
        with self.app.app_context():
            brand = Brand.query.filter_by(name='Prusament').first()
            color = Color.query.first()
            material = Material.query.filter_by(name='PLA').first()
            filament = Filament(
                name='Storage Filament',
                brand_id=brand.id,
                material_id=material.id,
                color_id=color.id,
                weight_total=1000,
                weight_remaining=480,
                price=500,
                quantity=1,
            )
            shelf = StorageShelf(name='Rack A', columns=3, slots_count=9, sort_order=1)
            db.session.add_all([filament, shelf])
            db.session.flush()
            db.session.add(StoragePlacement(
                shelf_id=shelf.id,
                filament_id=filament.id,
                slot_index=4,
                orientation='flat',
            ))
            db.session.commit()

        exported = self.client.get('/export').get_json()
        self.assertEqual(exported['storage_shelves'][0]['name'], 'Rack A')
        self.assertEqual(exported['storage_placements'][0]['slot_index'], 4)

        with self.app.app_context():
            db.drop_all()
            db.create_all()

        response = self.client.post(
            '/import',
            data={'file': (io.BytesIO(json.dumps(exported).encode('utf-8')), 'backup.json')},
            content_type='multipart/form-data',
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)

        with self.app.app_context():
            shelf = StorageShelf.query.filter_by(name='Rack A').first()
            self.assertIsNotNone(shelf)
            placement = StoragePlacement.query.filter_by(slot_index=4).first()
            self.assertIsNotNone(placement)
            self.assertEqual(placement.orientation, 'flat')
            self.assertEqual(placement.filament.name, 'Storage Filament')


if __name__ == '__main__':
    unittest.main()
