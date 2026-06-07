"""Extended tests for Bambu integration — job page rendering with filters, 
auto-mapping, job remap, and create_project endpoint edge cases."""
import json
import os
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from app import create_app
from database import db
from models import (
    AppSetting, BambuPrintJob, BambuJobMaterial, BambuPrinter,
    Brand, Color, Filament, Material, PrintHistory, Project, ProjectFilament,
)
from utils import utc_now


class _BaseBambuExtTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix='bambu-ext-tests-')
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
            mat = Material.query.filter_by(name='PLA').first()
            color = Color.query.first()

            self.filament = Filament(
                name='Bambu Ext PLA',
                brand_id=brand.id,
                color_id=color.id,
                material_id=mat.id,
                weight_total=1000,
                weight_remaining=900,
                price=500,
                quantity=2,
            )
            db.session.add(self.filament)
            db.session.flush()
            self.filament_id = self.filament.id

            # Create a few Bambu print jobs in various states
            for i in range(3):
                job = BambuPrintJob(
                    external_id=f'EXT-JOB-{i}',
                    model_name=f'Bambu Model {i}',
                    printer_name='P1P',
                    printer_model='P1P',
                    device_id=f'DEV_{i}',
                    status='FINISH' if i < 2 else 'RUNNING',
                    weight_grams=50 + i * 10,
                    cost_time=3600,
                )
                db.session.add(job)
            db.session.commit()

            self.job_id = BambuPrintJob.query.filter_by(external_id='EXT-JOB-0').first().id

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _login_admin(self):
        return self.client.post(
            '/login',
            data={'email': 'admin@example.com', 'password': 'password123'},
            follow_redirects=True,
        )


# ── Bambu Jobs Page ─────────────────────────────────────────────────────

class BambuJobPageTests(_BaseBambuExtTests):
    def test_bambu_page_renders(self):
        response = self.client.get('/bambu')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Bambu Model', response.data)

    def test_bambu_page_filter_by_status(self):
        response = self.client.get('/bambu?filter=RUNNING')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Bambu Model 2', response.data)

    def test_bambu_page_search_filter(self):
        response = self.client.get('/bambu?search=Model+0')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Model 0', response.data)

    def test_bambu_page_search_no_results(self):
        response = self.client.get('/bambu?search=NONEXISTENT')
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(b'Bambu Model', response.data)

    def test_bambu_page_filament_filter(self):
        response = self.client.get(f'/bambu?filament_id={self.filament_id}')
        self.assertEqual(response.status_code, 200)

    def test_bambu_page_pagination(self):
        response = self.client.get('/bambu?page=1')
        self.assertEqual(response.status_code, 200)

    def test_bambu_page_contains_cleaned_titles(self):
        with self.app.app_context():
            job = BambuPrintJob(
                external_id='CLEAN-JOB',
                model_name='Model.stl_1',
                printer_name='P1P',
                status='FINISH',
            )
            db.session.add(job)
            db.session.commit()

        response = self.client.get('/bambu')
        self.assertEqual(response.status_code, 200)
        html = response.data.decode('utf-8')
        # The cleaned title should be in the JS data
        self.assertIn('cleanedTitle', html)


# ── Bambu Job Management ────────────────────────────────────────────────

class BambuJobManagementTests(_BaseBambuExtTests):
    def test_job_delete_removes_job(self):
        response = self.client.post(f'/bambu/job/{self.job_id}/delete',
                                     follow_redirects=False)
        self.assertEqual(response.status_code, 302)

        with self.app.app_context():
            self.assertIsNone(db.session.get(BambuPrintJob, self.job_id))

    def test_job_delete_nonexistent_returns_404(self):
        response = self.client.post('/bambu/job/99999/delete',
                                     follow_redirects=False)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json, {'ok': False, 'error': 'not found'})

    def test_job_map_assigns_filament(self):
        with self.app.app_context():
            job = BambuPrintJob(
                external_id='MAP-JOB',
                model_name='Map Test',
                printer_name='P1P',
                status='FINISH',
                weight_grams=60.0,
            )
            db.session.add(job)
            db.session.commit()
            job_id = job.id

        response = self.client.post(f'/bambu/job/{job_id}/map', data={
            'filament_id': str(self.filament_id),
        }, follow_redirects=False)
        self.assertEqual(response.status_code, 302)

        with self.app.app_context():
            job = db.session.get(BambuPrintJob, job_id)
            self.assertEqual(job.filament_id, self.filament_id)

    def test_job_map_with_deduct_reduces_stock(self):
        with self.app.app_context():
            job = BambuPrintJob(
                external_id='DEDUCT-JOB',
                model_name='Deduct Test',
                printer_name='P1P',
                status='FINISH',
                weight_grams=100.0,
            )
            db.session.add(job)
            db.session.commit()
            job_id = job.id

        self.client.post(f'/bambu/job/{job_id}/map', data={
            'filament_id': str(self.filament_id),
            'deduct': '1',
        }, follow_redirects=False)

        with self.app.app_context():
            f = db.session.get(Filament, self.filament_id)
            self.assertAlmostEqual(f.weight_remaining, 800.0)

    def test_multimaterial_slot_remap(self):
        with self.app.app_context():
            job = BambuPrintJob(
                external_id='REMAP-JOB',
                model_name='Remap Test',
                printer_name='P1P',
                status='FINISH',
            )
            db.session.add(job)
            db.session.flush()
            slot = BambuJobMaterial(
                job_id=job.id,
                ams_id=0,
                tray_id=0,
                material_name='PLA',
                weight_grams=30.0,
            )
            db.session.add(slot)
            db.session.commit()
            job_id = job.id
            slot_id = slot.id

        response = self.client.post(f'/bambu/job/{job_id}/remap-slot', data={
            'slot_id': str(slot_id),
            'filament_id': str(self.filament_id),
        }, follow_redirects=False)
        self.assertEqual(response.status_code, 302)

        with self.app.app_context():
            slot = db.session.get(BambuJobMaterial, slot_id)
            self.assertEqual(slot.filament_id, self.filament_id)

    def test_create_project_from_job(self):
        with self.app.app_context():
            job = BambuPrintJob(
                external_id='CREATE-PROJ',
                model_name='New Project Model',
                printer_name='P1P',
                status='FINISH',
                weight_grams=75.0,
            )
            db.session.add(job)
            db.session.commit()
            job_id = job.id

        response = self.client.post(f'/bambu/job/{job_id}/create_project', data={
            'project_name': 'Job Project',
        })
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data['ok'])

        with self.app.app_context():
            project = Project.query.filter_by(name='Job Project').first()
            self.assertIsNotNone(project)

    def test_create_project_empty_name_returns_400(self):
        with self.app.app_context():
            job = BambuPrintJob(
                external_id='BAD-PROJ',
                model_name='Bad',
                printer_name='P1P',
                status='FINISH',
            )
            db.session.add(job)
            db.session.commit()
            job_id = job.id

        response = self.client.post(f'/bambu/job/{job_id}/create_project', data={
            'project_name': '',
        })
        self.assertEqual(response.status_code, 400)

    def test_auto_map_history_endpoint(self):
        """POST /bambu/auto-map-history should exist and process jobs."""
        with self.app.app_context():
            # Create an unmapped job
            job = BambuPrintJob(
                external_id='AUTO-MAP-HIST',
                model_name='Auto Map',
                printer_name='P1P',
                status='FINISH',
                weight_grams=50.0,
                filament_id=None,
            )
            db.session.add(job)
            db.session.commit()

        response = self.client.post('/bambu/auto-map-history')
        # May return 200 with auto-mapping results, or redirect
        self.assertIn(response.status_code, (200, 302))

    def test_refetch_thumbnails_endpoint(self):
        """POST /bambu/refetch-thumbnails should return stats."""
        response = self.client.post('/bambu/refetch-thumbnails')
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIn('ok', data)

    def test_sync_endpoint_without_token_returns_400(self):
        """POST /bambu/sync without token returns 400."""
        response = self.client.post('/bambu/sync')
        self.assertEqual(response.status_code, 400)
        data = response.get_json()
        self.assertFalse(data['ok'])

    def test_multimaterial_job_deduct_slot(self):
        with self.app.app_context():
            job = BambuPrintJob(
                external_id='SLOT-DEDUCT',
                model_name='Slot Deduct',
                printer_name='P1P',
                status='FINISH',
            )
            db.session.add(job)
            db.session.flush()
            slot = BambuJobMaterial(
                job_id=job.id,
                ams_id=0,
                tray_id=0,
                material_name='PLA',
                weight_grams=40.0,
            )
            db.session.add(slot)
            db.session.commit()
            job_id = job.id
            slot_id = slot.id

        response = self.client.post(f'/bambu/job/{job_id}/deduct-slot', data={
            'slot_id': str(slot_id),
            'filament_id': str(self.filament_id),
        }, follow_redirects=False)
        self.assertEqual(response.status_code, 302)

        with self.app.app_context():
            f = db.session.get(Filament, self.filament_id)
            self.assertAlmostEqual(f.weight_remaining, 860.0)  # 900 - 40


if __name__ == '__main__':
    unittest.main()
