"""Extended tests for calculator — project-based quotes, energy cost calculation,
multi-material aggregation, history management."""
import os
import shutil
import tempfile
import unittest

from app import create_app
from auth import hash_password
from database import db
from models import (
    AppSetting, BambuJobMaterial, BambuPrintJob, Brand, Color, Filament,
    Material, PrintHistory, Project, ProjectQuote, ProjectFilament, User,
)
from database import db
from utils import utc_now


class _BaseCalculatorTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix='calculator-ext-tests-')
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

            self.filament = Filament(
                name='Calculator PLA',
                brand_id=brand.id,
                material_id=material.id,
                color_id=color.id,
                weight_total=1000.0,
                weight_remaining=1000.0,
                price=500.0,
                quantity=1,
            )
            self.project = Project(name='Calc Project', client_name='Client')
            admin = User(
                email='admin@example.com', name='Admin',
                password_hash=hash_password('password123'), role='admin',
            )
            db.session.add(admin)
            db.session.flush()
            self.project.owner_user_id = admin.id
            db.session.add_all([self.filament, self.project])

            # Ensure AppSetting exists (migration doesn't commit the seed row)
            setting = AppSetting.query.first()
            if not setting:
                setting = AppSetting(lang='cs', kwh_price=5.0, printer_power=150,
                                     currency='CZK', debug_logging=False, theme='light',
                                     nav_palette='teal', view_mode='card', items_per_page=12)
                db.session.add(setting)
            db.session.commit()
            self.filament_id = self.filament.id
            self.project_id = self.project.id

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)


# ── Calculator Page Rendering ────────────────────────────────────────────

class CalculatorPageTests(_BaseCalculatorTests):
    def test_calculator_page_renders(self):
        response = self.client.get('/calculator')
        self.assertEqual(response.status_code, 200)
        html = response.data.decode('utf-8')
        self.assertIn('Calculator PLA', html)

    def test_calculator_page_lists_projects(self):
        response = self.client.get('/calculator')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Calc Project', response.data)


# ── Quote Calculation Unit Tests ──────────────────────────────────────────

class QuoteCalculationTests(_BaseCalculatorTests):
    """Direct test of _calculate_quote and _calculate_project_quote logic."""

    def test_simple_quote_calculation(self):
        with self.app.app_context():
            from routes.calculator import _calculate_quote
            setting = AppSetting.query.first()
            filament = db.session.get(Filament, self.filament_id)
            quote = _calculate_quote(filament, 100.0, 2.0, 25.0, setting)

            # 100g at 0.50 CZK/g = 50 CZK material
            self.assertAlmostEqual(quote['material_cost'], 50.0)
            # 2 hours at 150W: 2 * 0.15kW * 5 CZK/kWh = 1.50 CZK
            self.assertAlmostEqual(quote['electricity_cost'], 1.5)
            # base = 51.50, margin 25% = 12.875
            self.assertAlmostEqual(quote['margin_amount'], 12.875)
            # total = 64.375
            self.assertAlmostEqual(quote['total_cost'], 64.375)

    def test_quote_with_different_margin(self):
        with self.app.app_context():
            from routes.calculator import _calculate_quote
            setting = AppSetting.query.first()
            filament = db.session.get(Filament, self.filament_id)
            quote = _calculate_quote(filament, 50.0, 1.0, 50.0, setting)

            # material: 50 * 0.50 = 25
            # energy: 1 * 0.15 * 5 = 0.75
            # base: 25.75, margin 50%: 12.875
            # total: 38.625
            self.assertAlmostEqual(quote['total_cost'], 38.625)

    def test_project_quote_with_bambu_jobs(self):
        with self.app.app_context():
            from routes.calculator import _calculate_project_quote
            setting = AppSetting.query.first()

            job = BambuPrintJob(
                external_id='PQ-B1',
                model_name='Part A',
                project_id=self.project_id,
                printer_name='P1P',
                status='FINISH',
                cost_time=3600,
                weight_grams=50.0,
                deducted=True,
            )
            db.session.add(job)
            db.session.flush()

            slot = BambuJobMaterial(
                job_id=job.id,
                ams_id=0,
                tray_id=0,
                material_name='PLA',
                weight_grams=50.0,
                filament_id=self.filament_id,
                deducted=True,
            )
            db.session.add(slot)
            db.session.commit()

            project = db.session.get(Project, self.project_id)
            quote = _calculate_project_quote(project, 20.0, setting)
            self.assertGreater(quote['total_material_cost'], 0)
            self.assertGreater(quote['electricity_cost'], 0)
            self.assertGreater(quote['total_cost'], 0)
            self.assertEqual(len(quote['lines']), 1)

    def test_project_quote_without_jobs_uses_plan(self):
        with self.app.app_context():
            from routes.calculator import _calculate_project_quote
            setting = AppSetting.query.first()

            # Add planned filament (no actual jobs)
            pf = ProjectFilament(
                project_id=self.project_id,
                filament_id=self.filament_id,
                estimated_weight=80.0,
            )
            db.session.add(pf)
            db.session.commit()

            project = db.session.get(Project, self.project_id)
            quote = _calculate_project_quote(project, 15.0, setting)
            self.assertGreater(quote['total_material_cost'], 0)
            self.assertEqual(len(quote['lines']), 1)

    def test_project_quote_empty_project(self):
        with self.app.app_context():
            from routes.calculator import _calculate_project_quote
            setting = AppSetting.query.first()

            project_no_data = Project(name='Empty')
            db.session.add(project_no_data)
            db.session.commit()

            quote = _calculate_project_quote(project_no_data, 20.0, setting)
            self.assertEqual(quote['total_material_cost'], 0)
            self.assertEqual(quote['total_cost'], 0)
            self.assertEqual(len(quote['lines']), 0)


# ── Calculator Route Integration ──────────────────────────────────────────

class CalculatorRouteQuoteTests(_BaseCalculatorTests):
    def test_calculator_computes_quote_via_get(self):
        response = self.client.get(
            f'/calculator?filament_id={self.filament_id}&weight=100&print_time=2'
        )
        self.assertEqual(response.status_code, 200)
        html = response.data.decode('utf-8')
        # The calculator page should render with the filament visible
        self.assertIn('Calculator PLA', html)

    def test_calculator_project_quote_via_get(self):
        response = self.client.get(
            f'/calculator/project/{self.project_id}?margin=25'
        )
        self.assertEqual(response.status_code, 200)
        html = response.data.decode('utf-8')

    def test_save_calculator_history(self):
        """Test saving a print history entry from the calculator."""
        response = self.client.post('/calculator', data={
            'action': 'save_history',
            'filament_id': self.filament_id,
            'weight': '75',
            'print_time': '3',
        }, follow_redirects=False)
        self.assertEqual(response.status_code, 200)

        with self.app.app_context():
            history = PrintHistory.query.first()
            self.assertIsNotNone(history)
            self.assertAlmostEqual(history.weight, 75.0)

    def test_calculator_history_list_renders(self):
        with self.app.app_context():
            db.session.add(PrintHistory(
                filament_name='History PLA',
                weight=120.0,
                total_cost=65.0,
            ))
            db.session.commit()

        response = self.client.get('/calculator')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'History PLA', response.data)

    def test_delete_calculator_history(self):
        with self.app.app_context():
            ph = PrintHistory(
                filament_name='Del History',
                weight=50.0,
                total_cost=25.0,
            )
            db.session.add(ph)
            db.session.commit()
            ph_id = ph.id

        response = self.client.post(f'/calculator/history/{ph_id}/delete',
                                     follow_redirects=False)
        self.assertEqual(response.status_code, 302)

        with self.app.app_context():
            self.assertIsNone(db.session.get(PrintHistory, ph_id))

    def test_calculator_save_quote_to_project(self):
        """Save a quote to a project (regression)."""
        self.client.post(
            '/login', data={'email': 'admin@example.com', 'password': 'password123'},
        )
        response = self.client.post('/calculator', data={
            'filament_id': self.filament_id,
            'project_id': self.project_id,
            'weight': '100',
            'print_time': '2',
            'margin_percent': '25',
            'action': 'save_quote',
        })
        self.assertEqual(response.status_code, 200)

        with self.app.app_context():
            quote = ProjectQuote.query.filter_by(project_id=self.project_id).first()
            self.assertIsNotNone(quote)
            self.assertEqual(quote.margin_percent, 25.0)

    def test_delete_quote(self):
        with self.app.app_context():
            quote = ProjectQuote(
                project_id=self.project_id,
                filament_id=self.filament_id,
                filament_name='Test',
                weight=100.0,
                print_time=2.0,
                material_cost=50.0,
                electricity_cost=1.5,
                base_cost=51.5,
                margin_percent=25.0,
                margin_amount=12.875,
                final_price=64.375,
                currency='CZK',
            )
            db.session.add(quote)
            db.session.commit()
            quote_id = quote.id

        response = self.client.post(f'/calculator/quote/{quote_id}/delete',
                                     follow_redirects=False)
        self.assertEqual(response.status_code, 302)

        with self.app.app_context():
            self.assertIsNone(db.session.get(ProjectQuote, quote_id))


# ── Energy Cost Computation ───────────────────────────────────────────────

class EnergyCostTests(_BaseCalculatorTests):
    def test_energy_cost_with_default_power(self):
        with self.app.app_context():
            setting = AppSetting.query.first()
            self.assertEqual(setting.kwh_price, 5.0)
            self.assertEqual(setting.printer_power, 150)

            from routes.calculator import _calculate_quote
            filament = db.session.get(Filament, self.filament_id)
            quote = _calculate_quote(filament, 100, 1, 0, setting)
            # 1h * 0.15kW * 5 = 0.75
            self.assertAlmostEqual(quote['electricity_cost'], 0.75)

    def test_energy_cost_custom_power(self):
        with self.app.app_context():
            setting = AppSetting.query.first()
            setting.printer_power = 300
            setting.kwh_price = 8.0
            db.session.commit()

            from routes.calculator import _calculate_quote
            filament = db.session.get(Filament, self.filament_id)
            quote = _calculate_quote(filament, 100, 2, 0, setting)
            # 2h * 0.30kW * 8 = 4.80
            self.assertAlmostEqual(quote['electricity_cost'], 4.80)


if __name__ == '__main__':
    unittest.main()
