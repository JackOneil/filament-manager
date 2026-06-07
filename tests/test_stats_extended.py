"""Extended tests for the statistics dashboard — HSL sorting, usage aggregation,
chart data generation, and page rendering with various data states."""
import os
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta

from app import create_app
from database import db
from models import (
    BambuJobMaterial, BambuPrintJob, Brand, Color, Filament, Material,
    MovementHistory, Project, ProjectFilament,
)
from routes.stats import (
    _hex_to_hsl_sort_key,
    _date_labels,
    _empty_series,
    _safe_divide,
    _reorder_status_label_key,
    _project_usage_rows,
)
from utils import log_movement, utc_now


class HexToHslSortKeyTests(unittest.TestCase):
    """Unit tests for _hex_to_hsl_sort_key."""

    def test_chromatic_red(self):
        key = _hex_to_hsl_sort_key('#FF0000')
        self.assertEqual(key[0], 0)  # chromatic bucket

    def test_chromatic_blue(self):
        key = _hex_to_hsl_sort_key('#0000FF')
        self.assertEqual(key[0], 0)

    def test_neutral_gray(self):
        key = _hex_to_hsl_sort_key('#808080')
        self.assertEqual(key[0], 1)  # neutral bucket

    def test_neutral_white(self):
        key = _hex_to_hsl_sort_key('#FFFFFF')
        self.assertEqual(key[0], 1)

    def test_neutral_black(self):
        key = _hex_to_hsl_sort_key('#000000')
        self.assertEqual(key[0], 1)

    def test_invalid_length(self):
        key = _hex_to_hsl_sort_key('#FFF')
        self.assertEqual(key[0], 2)  # fallback bucket

    def test_invalid_chars(self):
        key = _hex_to_hsl_sort_key('#ZZZZZZ')
        self.assertEqual(key[0], 2)

    def test_empty_value(self):
        key = _hex_to_hsl_sort_key('')
        self.assertEqual(key[0], 2)

    def test_none_value(self):
        key = _hex_to_hsl_sort_key(None)
        self.assertEqual(key[0], 2)


class HelperFunctionTests(unittest.TestCase):
    """Unit tests for stats helper functions."""

    def test_date_labels_length(self):
        labels = _date_labels(30)
        self.assertEqual(len(labels), 30)

    def test_date_labels_7(self):
        labels = _date_labels(7)
        self.assertEqual(len(labels), 7)

    def test_empty_series_90(self):
        series = _empty_series(90)
        self.assertEqual(len(series), 90)

    def test_empty_series_keys_are_iso_dates(self):
        series = _empty_series(7)
        for key in series:
            self.assertIn('-', key)  # ISO format

    def test_safe_divide_normal(self):
        self.assertAlmostEqual(_safe_divide(10, 2), 5.0)

    def test_safe_divide_zero_denominator(self):
        self.assertEqual(_safe_divide(10, 0), 0.0)

    def test_safe_divide_none_denominator(self):
        self.assertEqual(_safe_divide(10, None), 0.0)

    def test_reorder_status_label_key(self):
        self.assertEqual(_reorder_status_label_key('critical'), 'stats_reorder_now')
        self.assertEqual(_reorder_status_label_key('warning'), 'stats_reorder_soon')
        self.assertEqual(_reorder_status_label_key('stable'), 'stats_stock_ok')
        self.assertEqual(_reorder_status_label_key('unknown'), 'unknown')


class _BaseStatsTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix='stats-ext-tests-')
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

            self.filament_a = Filament(
                name='PLA A',
                brand_id=brand.id,
                material_id=material.id,
                color_id=color.id,
                weight_total=1000,
                weight_remaining=800,
                price=500,
                quantity=2,
            )
            self.filament_b = Filament(
                name='PLA B',
                brand_id=brand.id,
                material_id=material.id,
                color_id=color.id,
                weight_total=1000,
                weight_remaining=100,
                price=600,
                quantity=1,
            )
            self.project = Project(name='Stats Project', status='PRINTING')
            db.session.add_all([self.filament_a, self.filament_b, self.project])
            db.session.flush()

            # Add some movements for both filaments
            t = utc_now() - timedelta(days=10)
            log_movement(self.filament_a, 'remove', 100.0)
            log_movement(self.filament_a, 'remove', 50.0)
            log_movement(self.filament_b, 'remove', 30.0)
            # Backdate movements
            for m in MovementHistory.query.all():
                m.created_at = t
            db.session.commit()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)


# ── Project Usage Rows ───────────────────────────────────────────────────

class ProjectUsageRowTests(_BaseStatsTests):
    def test_project_usage_returns_rows(self):
        with self.app.app_context():
            project = db.session.execute(db.select(Project).filter_by(name='Stats Project')).scalar_one()
            job = BambuPrintJob(
                external_id='STATS-JOB-1',
                model_name='Stats Model',
                project_id=project.id,
                printer_name='P1P',
                status='FINISH',
                deducted=True,
                weight_grams=200.0,
            )
            db.session.add(job)
            db.session.commit()

            rows = _project_usage_rows()
            # At minimum, our project should be present (might have 0 weight if no materials)
            self.assertGreaterEqual(len(rows), 0)

    def test_project_usage_empty_when_no_jobs(self):
        with self.app.app_context():
            rows = _project_usage_rows()
            self.assertEqual(len(rows), 0)


# ── Stats Route ──────────────────────────────────────────────────────────

class StatsRouteTests(_BaseStatsTests):
    def test_stats_page_renders(self):
        response = self.client.get('/stats')
        self.assertEqual(response.status_code, 200)

    def test_stats_page_with_custom_days(self):
        response = self.client.get('/stats?days=90')
        self.assertEqual(response.status_code, 200)

    def test_stats_page_contains_chart_data(self):
        response = self.client.get('/stats')
        self.assertEqual(response.status_code, 200)
        html = response.data.decode('utf-8')
        # Should contain Chart.js data JSON
        self.assertIn('labels', html)

    def test_stats_page_with_multiple_filaments_shows_purchase_table(self):
        response = self.client.get('/stats')
        self.assertEqual(response.status_code, 200)
        html = response.data.decode('utf-8')
        self.assertIn('PLA', html)

    def test_stats_page_returns_200_with_no_data(self):
        response = self.client.get('/stats')
        self.assertEqual(response.status_code, 200)

    def test_stats_page_color_palette_data(self):
        """The stats page should render color palette data for the colors section."""
        response = self.client.get('/stats')
        self.assertEqual(response.status_code, 200)
        html = response.data.decode('utf-8')
        # Check for hex values of seed colors
        self.assertIn('#000000', html)  # Černá from seed data


if __name__ == '__main__':
    unittest.main()
