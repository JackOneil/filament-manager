"""Extended tests for PrusaLink integration — job page rendering, printer
sync/test, job mapping, and job deletion HTTP endpoints."""
import json
import os
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from app import create_app
from database import db
from models import (
    AppSetting, PrusaPrintJob, PrusaPrinter,
    Brand, Color, Filament, Material, Project,
)
from utils import utc_now


class _BasePrusaExtTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix='prusa-ext-tests-')
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
                name='Prusa Ext PLA',
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

            # Create a Prusa printer
            self.printer = PrusaPrinter(
                name='Test MK4',
                host='http://192.168.1.100',
                api_key='dGVzdF9rZXk=',  # base64-encoded dummy key
                printer_model='MK4',
                enabled=True,
            )
            db.session.add(self.printer)
            db.session.flush()
            self.printer_id = self.printer.id

            # Create a few Prusa print jobs in various states
            for i in range(3):
                job = PrusaPrintJob(
                    printer_id=self.printer_id,
                    printer_name='MK4',
                    file_name=f'print_{i}.gcode',
                    display_name=f'Prusa Job {i}',
                    status='FINISHED' if i < 2 else 'PRINTING',
                    weight_grams=50 + i * 10,
                    cost_time=3600,
                )
                db.session.add(job)
            db.session.commit()

            self.job_id = PrusaPrintJob.query.filter_by(file_name='print_0.gcode').first().id

            # Create a project for mapping tests
            self.project = Project(
                name='Prusa Test Project',
                status='NEW',
            )
            db.session.add(self.project)
            db.session.commit()
            self.project_id = self.project.id

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)


# ── Prusa Jobs Page ─────────────────────────────────────────────────────

class PrusaJobPageTests(_BasePrusaExtTests):
    def test_prusa_page_renders(self):
        response = self.client.get('/prusa')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Prusa Job 0', response.data)

    def test_prusa_page_filter_unassigned(self):
        response = self.client.get('/prusa?filter=unassigned')
        self.assertEqual(response.status_code, 200)

    def test_prusa_page_filter_not_deducted(self):
        response = self.client.get('/prusa?filter=not_deducted')
        self.assertEqual(response.status_code, 200)

    def test_prusa_page_hide_failed(self):
        response = self.client.get('/prusa?hide_failed=1')
        self.assertEqual(response.status_code, 200)

    def test_prusa_page_with_filament_id(self):
        response = self.client.get(f'/prusa?filament_id={self.filament_id}')
        self.assertEqual(response.status_code, 200)


# ── Printer Sync ────────────────────────────────────────────────────────

class PrusaPrinterSyncTests(_BasePrusaExtTests):
    @patch('routes.prusa.do_poll')
    def test_prusa_printer_sync_success(self, mock_do_poll):
        mock_do_poll.return_value = {
            'error': None,
            'jobs_created': 1,
            'jobs_updated': 0,
        }
        response = self.client.post(f'/prusa/printer/{self.printer_id}/sync')
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data['ok'])

    @patch('routes.prusa.do_poll')
    def test_prusa_printer_sync_not_found(self, mock_do_poll):
        response = self.client.post('/prusa/printer/9999/sync')
        self.assertEqual(response.status_code, 404)
        data = response.get_json()
        self.assertFalse(data['ok'])

    @patch('routes.prusa.do_poll')
    def test_prusa_printer_sync_error(self, mock_do_poll):
        mock_do_poll.return_value = {
            'error': 'Connection refused',
            'jobs_created': 0,
            'jobs_updated': 0,
        }
        response = self.client.post(f'/prusa/printer/{self.printer_id}/sync')
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertFalse(data['ok'])


# ── Printer Test ────────────────────────────────────────────────────────

class PrusaPrinterTestTests(_BasePrusaExtTests):
    @patch('routes.prusa.prusa_test_connection')
    def test_prusa_printer_test_success(self, mock_test):
        mock_test.return_value = {
            'ok': True,
            'model': 'MK4',
        }
        response = self.client.post(f'/prusa/printer/{self.printer_id}/test')
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data['ok'])

    @patch('routes.prusa.prusa_test_connection')
    def test_prusa_printer_test_not_found(self, mock_test):
        response = self.client.post('/prusa/printer/9999/test')
        self.assertEqual(response.status_code, 404)
        data = response.get_json()
        self.assertFalse(data['ok'])

    @patch('routes.prusa.prusa_test_connection')
    def test_prusa_printer_test_does_not_overwrite_existing_model(self, mock_test):
        mock_test.return_value = {
            'ok': True,
            'model': 'MK4S',
        }
        self.client.post(f'/prusa/printer/{self.printer_id}/test')
        with self.app.app_context():
            printer = db.session.get(PrusaPrinter, self.printer_id)
            # Existing model is not overwritten (code only backfills if model is None)
            self.assertEqual(printer.printer_model, 'MK4')

    @patch('routes.prusa.prusa_test_connection')
    def test_prusa_printer_test_backfills_model_when_none(self, mock_test):
        mock_test.return_value = {
            'ok': True,
            'model': 'MK4S',
        }
        with self.app.app_context():
            printer = db.session.get(PrusaPrinter, self.printer_id)
            printer.printer_model = None
            db.session.commit()

        self.client.post(f'/prusa/printer/{self.printer_id}/test')
        with self.app.app_context():
            printer = db.session.get(PrusaPrinter, self.printer_id)
            self.assertEqual(printer.printer_model, 'MK4S')


# ── Job Map ─────────────────────────────────────────────────────────────

class PrusaJobMapTests(_BasePrusaExtTests):
    def test_prusa_job_map_assign_filament(self):
        response = self.client.post(f'/prusa/job/{self.job_id}/map', data={
            'filament_id': str(self.filament_id),
        }, follow_redirects=False)
        self.assertEqual(response.status_code, 302)

        with self.app.app_context():
            job = db.session.get(PrusaPrintJob, self.job_id)
            self.assertEqual(job.filament_id, self.filament_id)

    def test_prusa_job_map_assign_project(self):
        response = self.client.post(f'/prusa/job/{self.job_id}/map', data={
            'project_id': str(self.project_id),
        }, follow_redirects=False)
        self.assertEqual(response.status_code, 302)

        with self.app.app_context():
            job = db.session.get(PrusaPrintJob, self.job_id)
            self.assertEqual(job.project_id, self.project_id)

    def test_prusa_job_map_not_found(self):
        response = self.client.post('/prusa/job/9999/map')
        self.assertEqual(response.status_code, 302)

    def test_prusa_job_map_ajax_not_found(self):
        response = self.client.post('/prusa/job/9999/map?ajax=1')
        self.assertEqual(response.status_code, 404)
        data = response.get_json()
        self.assertFalse(data['ok'])

    def test_prusa_job_map_assign_display_name(self):
        response = self.client.post(f'/prusa/job/{self.job_id}/map', data={
            'display_name': 'My Custom Name',
        }, follow_redirects=False)
        self.assertEqual(response.status_code, 302)

        with self.app.app_context():
            job = db.session.get(PrusaPrintJob, self.job_id)
            self.assertEqual(job.display_name, 'My Custom Name')

    def test_prusa_job_map_ajax_success(self):
        response = self.client.post(f'/prusa/job/{self.job_id}/map?ajax=1', data={
            'filament_id': str(self.filament_id),
        })
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data['ok'])

    def test_prusa_job_map_ajax_returns_filter_counts(self):
        response = self.client.post(f'/prusa/job/{self.job_id}/map?ajax=1', data={
            'filament_id': str(self.filament_id),
        })
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIn('filter_counts', data)
        self.assertIn('all', data['filter_counts'])
        self.assertIn('unassigned', data['filter_counts'])
        self.assertIn('not_deducted', data['filter_counts'])

    def test_prusa_job_map_deduct_now(self):
        with self.app.app_context():
            job = db.session.get(PrusaPrintJob, self.job_id)
            job.status = 'FINISHED'
            job.weight_grams = 50.0
            db.session.commit()

        response = self.client.post(f'/prusa/job/{self.job_id}/map?ajax=1', data={
            'filament_id': str(self.filament_id),
            'deduct': '1',
            'project_id': str(self.project_id),
        })
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data['ok'])

        with self.app.app_context():
            job = db.session.get(PrusaPrintJob, self.job_id)
            self.assertTrue(job.deducted)


# ── Job Delete ──────────────────────────────────────────────────────────

class PrusaJobDeleteTests(_BasePrusaExtTests):
    def test_prusa_job_delete_existing(self):
        response = self.client.post(f'/prusa/job/{self.job_id}/delete',
                                     follow_redirects=False)
        self.assertEqual(response.status_code, 302)

        with self.app.app_context():
            self.assertIsNone(db.session.get(PrusaPrintJob, self.job_id))

    def test_prusa_job_delete_nonexistent(self):
        response = self.client.post('/prusa/job/9999/delete',
                                     follow_redirects=False)
        self.assertEqual(response.status_code, 302)

    def test_prusa_job_delete_decrements_count(self):
        with self.app.app_context():
            before = PrusaPrintJob.query.count()

        self.client.post(f'/prusa/job/{self.job_id}/delete')

        with self.app.app_context():
            after = PrusaPrintJob.query.count()
            self.assertEqual(after, before - 1)
