import os
import shutil
import tempfile
import unittest

from app import create_app
from auth import hash_password
from database import db
from models import Brand, Color, Filament, Material, MovementHistory, User


class InventorySpoolTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix='filament-inventory-tests-')
        db_path = os.path.join(self.temp_dir, 'test.db')
        self.app = create_app({
            'TESTING': True,
            'AUTH_REQUIRED_IN_TESTS': True,
            'SQLALCHEMY_DATABASE_URI': f'sqlite:///{db_path}',
            'PROJECT_UPLOAD_FOLDER': os.path.join(self.temp_dir, 'uploads'),
            'WTF_CSRF_ENABLED': False,
        })
        self.client = self.app.test_client()

        with self.app.app_context():
            brand = Brand.query.first()
            color = Color.query.first()
            material = Material.query.first()
            admin = User(
                email='admin@example.com',
                name='Admin',
                password_hash=hash_password('password123'),
                role='admin',
            )
            filament = Filament(
                name='Test PLA Blue',
                brand_id=brand.id,
                color_id=color.id,
                material_id=material.id,
                weight_total=1000,
                weight_remaining=500,
                price=500,
                quantity=1,
            )
            db.session.add_all([admin, filament])
            db.session.commit()
            self.filament_id = filament.id

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def login_admin(self):
        return self.client.post(
            '/login',
            data={'email': 'admin@example.com', 'password': 'password123'},
            follow_redirects=True,
        )

    def test_add_spool_accepts_multiple_pieces_via_ajax(self):
        self.login_admin()
        response = self.client.post(
            f'/add_spool/{self.filament_id}',
            data={'quantity': '3'},
            headers={'X-Requested-With': 'XMLHttpRequest', 'Accept': 'application/json'},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload['ok'])
        self.assertEqual(payload['added_spools'], 3)
        self.assertEqual(payload['added_weight'], 3000)

        with self.app.app_context():
            filament = db.session.get(Filament, self.filament_id)
            movement = MovementHistory.query.order_by(MovementHistory.id.desc()).first()
            self.assertEqual(filament.quantity, 4)
            self.assertEqual(filament.weight_remaining, 3500)
            self.assertEqual(movement.weight, 3000)
            self.assertEqual(movement.note, 'Přidáno kusů: 3')

    def test_add_spool_falls_back_to_single_piece_for_bad_quantity(self):
        self.login_admin()
        response = self.client.post(
            f'/add_spool/{self.filament_id}',
            data={'quantity': '0'},
            headers={'X-Requested-With': 'XMLHttpRequest', 'Accept': 'application/json'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()['added_spools'], 1)
        with self.app.app_context():
            filament = db.session.get(Filament, self.filament_id)
            self.assertEqual(filament.quantity, 2)
            self.assertEqual(filament.weight_remaining, 1500)


if __name__ == '__main__':
    unittest.main()
