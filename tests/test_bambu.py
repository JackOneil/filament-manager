"""Tests for Bambu Lab Cloud integration: sync logic, deduplication, and
filament consumption mapping."""
import json
import os
import shutil
import tempfile
import unittest
from datetime import datetime
from unittest.mock import MagicMock, patch

from app import create_app
from database import db
from models import (
    AppSetting, BambuPrintJob, BambuJobMaterial, BambuPrinter,
    Brand, Color, Material, Filament, MovementHistory, PrintHistory,
)
from routes.bambu import do_sync, _parse_ts, _resolve_status


# ─── Unit tests: helpers ────────────────────────────────────────────────────

class ParseTsTests(unittest.TestCase):
    """_parse_ts must handle epoch milliseconds, epoch seconds, and ISO strings."""

    def test_returns_none_for_none(self):
        self.assertIsNone(_parse_ts(None))

    def test_epoch_milliseconds(self):
        # 2024-01-15 10:00:00 UTC  →  1705312800 s  →  1705312800000 ms
        ms = 1705312800 * 1000
        result = _parse_ts(ms)
        self.assertIsInstance(result, datetime)
        self.assertEqual(result.year, 2024)
        self.assertEqual(result.month, 1)

    def test_epoch_seconds(self):
        ts = 1705312800  # < 1e12 so treated as seconds
        result = _parse_ts(ts)
        self.assertIsInstance(result, datetime)
        self.assertEqual(result.year, 2024)

    def test_iso_string_without_tz(self):
        result = _parse_ts('2024-03-10T14:30:00')
        self.assertIsInstance(result, datetime)
        self.assertEqual(result.hour, 14)
        self.assertEqual(result.minute, 30)

    def test_iso_string_with_z(self):
        result = _parse_ts('2024-03-10T14:30:00Z')
        self.assertIsInstance(result, datetime)
        self.assertEqual(result.hour, 14)

    def test_iso_string_with_offset(self):
        result = _parse_ts('2024-03-10T14:30:00+08:00')
        self.assertIsInstance(result, datetime)

    def test_iso_string_with_microseconds(self):
        result = _parse_ts('2024-03-10T14:30:00.123456')
        self.assertIsInstance(result, datetime)
        self.assertEqual(result.second, 0)

    def test_garbage_string_returns_none(self):
        self.assertIsNone(_parse_ts('not-a-date'))


class ResolveStatusTests(unittest.TestCase):
    def test_int_2_gives_finish(self):
        self.assertEqual(_resolve_status(2), 'FINISH')

    def test_int_4_gives_paused(self):
        self.assertEqual(_resolve_status(4), 'PAUSED')

    def test_int_1_gives_running(self):
        self.assertEqual(_resolve_status(1), 'RUNNING')

    def test_negative_7_gives_cancelled(self):
        self.assertEqual(_resolve_status(-7), 'CANCELLED')

    def test_string_digit_gives_mapped_value(self):
        self.assertEqual(_resolve_status('3'), 'FAILED')

    def test_unknown_int_gives_status_label(self):
        result = _resolve_status(99)
        self.assertIn('99', result)


# ─── Integration tests: do_sync ─────────────────────────────────────────────

def _make_task(task_id, status=2, weight=50.0, ams=None):
    """Build a minimal Bambu task dict matching real Bambu Cloud API field names."""
    return {
        'id': task_id,
        'title': f'Model_{task_id}',
        'designTitle': '',
        'status': status,
        'weight': weight,
        'costTime': 3600,
        'deviceName': 'My P1P',
        'deviceModel': 'P1P',
        'deviceId': f'DEV_{task_id}',
        'instanceId': 0,
        'startTime': '2024-03-10T10:00:00',
        'endTime': '2024-03-10T12:00:00',
        'amsDetailMappings': ams or [],
    }


def _api_response(tasks):
    return MagicMock(
        status_code=200,
        json=MagicMock(return_value={'hits': tasks, 'total': len(tasks)}),
        raise_for_status=MagicMock(),
    )


class DoSyncTests(unittest.TestCase):
    """Integration tests for do_sync() against an in-memory SQLite database."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix='bambu-tests-')
        db_path = os.path.join(self.temp_dir, 'test.db')
        self.app = create_app({
            'TESTING': True,
            'SQLALCHEMY_DATABASE_URI': f'sqlite:///{db_path}',
            'PROJECT_UPLOAD_FOLDER': os.path.join(self.temp_dir, 'uploads'),
            'WTF_CSRF_ENABLED': False,
        })
        self.ctx = self.app.app_context()
        self.ctx.push()

    def tearDown(self):
        self.ctx.pop()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @patch('routes.bambu.requests.get')
    def test_adds_new_jobs(self, mock_get):
        mock_get.return_value = _api_response([_make_task(1001), _make_task(1002)])
        result = do_sync('fake-token', 'global')

        self.assertIsNone(result['error'])
        self.assertEqual(result['added'], 2)
        self.assertEqual(BambuPrintJob.query.count(), 2)

    @patch('routes.bambu.requests.get')
    def test_idempotent_no_duplicates(self, mock_get):
        """Calling sync twice with the same jobs must not create duplicates."""
        tasks = [_make_task(2001)]
        mock_get.return_value = _api_response(tasks)

        r1 = do_sync('token', 'global')
        mock_get.return_value = _api_response(tasks)
        r2 = do_sync('token', 'global')

        self.assertEqual(r1['added'], 1)
        self.assertEqual(r2['added'], 0)
        self.assertEqual(r2['skipped'], 1)
        self.assertEqual(BambuPrintJob.query.count(), 1)

    @patch('routes.bambu.requests.get')
    def test_updates_status_for_existing_job(self, mock_get):
        """A job that changes from RUNNING to FINISH must be updated, not duplicated."""
        mock_get.return_value = _api_response([_make_task(3001, status=1)])  # RUNNING
        do_sync('token', 'global')

        mock_get.return_value = _api_response([_make_task(3001, status=2)])  # FINISH
        r2 = do_sync('token', 'global')

        self.assertEqual(r2['updated'], 1)
        self.assertEqual(r2['added'], 0)
        job = BambuPrintJob.query.filter_by(external_id='3001').first()
        self.assertEqual(job.status, 'FINISH')
        self.assertEqual(BambuPrintJob.query.count(), 1)

    @patch('routes.bambu.requests.get')
    def test_stores_per_slot_materials(self, mock_get):
        ams = [
            {'amsId': 0, 'trayId': 0, 'color': '#FF0000', 'materialName': 'PLA', 'weight': 30.0},
            {'amsId': 0, 'trayId': 1, 'color': '#0000FF', 'materialName': 'PETG', 'weight': 20.0},
        ]
        mock_get.return_value = _api_response([_make_task(4001, ams=ams)])
        do_sync('token', 'global')

        job = BambuPrintJob.query.filter_by(external_id='4001').first()
        self.assertIsNotNone(job)
        self.assertEqual(len(job.materials), 2)

        mat_names = {m.material_name for m in job.materials}
        self.assertIn('PLA', mat_names)
        self.assertIn('PETG', mat_names)

    @patch('routes.bambu.requests.get')
    def test_total_weight_derived_from_ams_when_missing(self, mock_get):
        """If task weight is 0/None, sum AMS slot weights instead."""
        ams = [
            {'amsId': 0, 'trayId': 0, 'materialName': 'PLA', 'weight': 18.5},
            {'amsId': 0, 'trayId': 1, 'materialName': 'PLA', 'weight': 12.0},
        ]
        task = _make_task(5001, weight=0, ams=ams)
        mock_get.return_value = _api_response([task])
        do_sync('token', 'global')

        job = BambuPrintJob.query.filter_by(external_id='5001').first()
        self.assertAlmostEqual(job.weight_grams, 30.5)

    @patch('routes.bambu.requests.get')
    def test_auto_registers_printer(self, mock_get):
        mock_get.return_value = _api_response([_make_task(6001)])
        do_sync('token', 'global')

        printer = BambuPrinter.query.filter_by(device_id='DEV_6001').first()
        self.assertIsNotNone(printer)
        self.assertEqual(printer.printer_model, 'P1P')

    @patch('routes.bambu.requests.get')
    def test_api_error_returns_error_key(self, mock_get):
        mock_get.side_effect = Exception('Connection refused')
        result = do_sync('bad-token', 'global')

        self.assertIsNotNone(result['error'])
        self.assertIn('Connection refused', result['error'])
        self.assertEqual(result['added'], 0)

    @patch('routes.bambu.requests.get')
    def test_tasks_with_no_id_are_skipped(self, mock_get):
        task_no_id = {'title': 'Ghost', 'status': 4, 'weight': 5.0}
        mock_get.return_value = _api_response([task_no_id, _make_task(7001)])
        result = do_sync('token', 'global')

        self.assertEqual(result['added'], 1)
        self.assertEqual(result['skipped'], 1)


# ─── Integration tests: filament deduction via HTTP route ───────────────────

class BambuDeductionRouteTests(unittest.TestCase):
    """Tests for stock deduction through the /bambu/job/<id>/map endpoint."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix='bambu-deduct-tests-')
        db_path = os.path.join(self.temp_dir, 'test.db')
        self.app = create_app({
            'TESTING': True,
            'SQLALCHEMY_DATABASE_URI': f'sqlite:///{db_path}',
            'PROJECT_UPLOAD_FOLDER': os.path.join(self.temp_dir, 'uploads'),
            'WTF_CSRF_ENABLED': False,
        })
        self.client = self.app.test_client()

        with self.app.app_context():
            # Use existing seed data created by create_app/_setup_database
            brand = Brand.query.filter_by(name='Prusament').first()
            mat = Material.query.filter_by(name='PLA').first()
            color = Color.query.filter_by(name='Černá').first()

            self.filament = Filament(
                name='TestPLA',
                brand_id=brand.id,
                color_id=color.id,
                material_id=mat.id,
                weight_total=1000.0,
                weight_remaining=800.0,
                price=500.0,
                quantity=1,
            )
            db.session.add(self.filament)
            db.session.flush()

            self.job = BambuPrintJob(
                external_id='TEST_JOB_001',
                model_name='TestModel',
                printer_name='P1P',
                status='FINISH',
                weight_grams=75.0,
            )
            db.session.add(self.job)
            db.session.commit()

            self.filament_id = self.filament.id
            self.job_id = self.job.id

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_deduct_reduces_filament_stock(self):
        resp = self.client.post(
            f'/bambu/job/{self.job_id}/map',
            data={
                'filament_id': str(self.filament_id),
                'deduct': '1',
            },
            follow_redirects=False,
        )
        self.assertEqual(resp.status_code, 302)

        with self.app.app_context():
            f = db.session.get(Filament, self.filament_id)
            self.assertAlmostEqual(f.weight_remaining, 800.0 - 75.0)

            job = db.session.get(BambuPrintJob, self.job_id)
            self.assertTrue(job.deducted)

    def test_no_double_deduction(self):
        """Submitting the deduct form twice must only deduct once."""
        for _ in range(2):
            self.client.post(
                f'/bambu/job/{self.job_id}/map',
                data={'filament_id': str(self.filament_id), 'deduct': '1'},
                follow_redirects=False,
            )

        with self.app.app_context():
            f = db.session.get(Filament, self.filament_id)
            self.assertAlmostEqual(f.weight_remaining, 800.0 - 75.0)

    def test_deduct_creates_print_history_entry(self):
        self.client.post(
            f'/bambu/job/{self.job_id}/map',
            data={'filament_id': str(self.filament_id), 'deduct': '1'},
            follow_redirects=False,
        )
        with self.app.app_context():
            self.assertEqual(PrintHistory.query.count(), 1)
            ph = PrintHistory.query.first()
            self.assertAlmostEqual(ph.weight, 75.0)

    def test_deduct_creates_movement_history_entry(self):
        self.client.post(
            f'/bambu/job/{self.job_id}/map',
            data={'filament_id': str(self.filament_id), 'deduct': '1'},
            follow_redirects=False,
        )
        with self.app.app_context():
            mh = MovementHistory.query.filter_by(action_type='bambu_print').first()
            self.assertIsNotNone(mh)
            self.assertAlmostEqual(mh.weight, 75.0)

    def test_slot_deduction(self):
        with self.app.app_context():
            slot = BambuJobMaterial(
                job_id=self.job_id,
                ams_id=0,
                tray_id=0,
                material_name='PLA',
                weight_grams=30.0,
            )
            db.session.add(slot)
            db.session.commit()
            slot_id = slot.id

        self.client.post(
            f'/bambu/job/{self.job_id}/deduct-slot',
            data={
                'slot_id': str(slot_id),
                'filament_id': str(self.filament_id),
            },
            follow_redirects=False,
        )

        with self.app.app_context():
            f = db.session.get(Filament, self.filament_id)
            self.assertAlmostEqual(f.weight_remaining, 800.0 - 30.0)
            s = db.session.get(BambuJobMaterial, slot_id)
            self.assertTrue(s.deducted)


# ─── Integration tests: sync endpoint ───────────────────────────────────────

class BambuSyncEndpointTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix='bambu-ep-tests-')
        db_path = os.path.join(self.temp_dir, 'test.db')
        self.app = create_app({
            'TESTING': True,
            'SQLALCHEMY_DATABASE_URI': f'sqlite:///{db_path}',
            'PROJECT_UPLOAD_FOLDER': os.path.join(self.temp_dir, 'uploads'),
        })
        self.client = self.app.test_client()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_sync_returns_400_when_no_token(self):
        resp = self.client.post('/bambu/sync')
        self.assertEqual(resp.status_code, 400)
        data = resp.get_json()
        self.assertFalse(data['ok'])

    @patch('routes.bambu.requests.get')
    def test_sync_returns_json_on_success(self, mock_get):
        mock_get.return_value = _api_response([_make_task(9001)])
        with self.app.app_context():
            setting = AppSetting.query.first()
            if not setting:
                setting = AppSetting()
                db.session.add(setting)
            setting.bambu_token = 'fake-token'
            db.session.commit()

        resp = self.client.post('/bambu/sync')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data['ok'])
        self.assertEqual(data['added'], 1)


if __name__ == '__main__':
    unittest.main()
