import os
import shutil
import tempfile
import unittest

from app import create_app
from auth import hash_password
from database import db
from models import Brand, Color, Filament, Material, Project, ProjectQuote, User


class CalculatorQuoteTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix='calculator-tests-')
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
                name='Quote PLA',
                brand_id=brand.id,
                material_id=material.id,
                color_id=color.id,
                weight_total=1000.0,
                weight_remaining=1000.0,
                price=500.0,
                quantity=1,
            )
            admin = User(
                email='admin@example.com', name='Admin',
                password_hash=hash_password('password123'), role='admin',
            )
            db.session.add(admin)
            db.session.flush()
            project = Project(name='Customer Box', client_name='Acme', owner_user_id=admin.id)
            db.session.add_all([filament, project])
            db.session.commit()
            self.filament_id = filament.id
            self.project_id = project.id
            self.admin_id = admin.id

        # Quote saving requires an authenticated user (admin or project owner).
        self.client.post(
            '/login', data={'email': 'admin@example.com', 'password': 'password123'},
        )

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_calculator_can_save_quote_to_project(self):
        response = self.client.post('/calculator', data={
            'filament_id': self.filament_id,
            'project_id': self.project_id,
            'weight': '100',
            'print_time': '2',
            'margin_percent': '25',
            'action': 'save_quote',
        })

        self.assertEqual(response.status_code, 200)
        self.assertIn('Nabídka uložená k projektu'.encode('utf-8'), response.data)

        with self.app.app_context():
            quote = ProjectQuote.query.filter_by(project_id=self.project_id).first()
            self.assertIsNotNone(quote)
            self.assertEqual(quote.margin_percent, 25.0)
            self.assertGreater(quote.final_price, quote.base_cost)

    def test_export_quote_renders_offer_page(self):
        with self.app.app_context():
            quote = ProjectQuote(
                project_id=self.project_id,
                filament_id=self.filament_id,
                filament_name='Quote PLA | Prusament PLA',
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

        response = self.client.get(f'/calculator/quote/{quote_id}/export')

        self.assertEqual(response.status_code, 200)
        self.assertIn('Cenová nabídka'.encode('utf-8'), response.data)
        self.assertIn('Customer Box'.encode('utf-8'), response.data)
        self.assertIn('64.38 CZK'.encode('utf-8'), response.data)
