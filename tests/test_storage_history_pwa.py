"""Tests for storage, history, and PWA routes that previously had no coverage."""
import json
import os
import tempfile
import unittest

from app import create_app
from auth import hash_password
from database import db
from models import (
    Brand, Color, Filament, Material, MovementHistory,
    StoragePlacement, StorageShelf, User,
)
from utils import log_movement, utc_now


class StorageRouteTests(unittest.TestCase):
    """Coverage for /storage CRUD: shelves, slot assignments, placements."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix='filament-storage-tests-')
        db_path = os.path.join(self.temp_dir, 'test.db')
        self.app = create_app({
            'TESTING': True,
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
            self.brand_id = brand.id
            self.color_id = color.id
            self.material_id = material.id
            filament = Filament(
                name='Storage Test PLA',
                brand_id=brand.id,
                color_id=color.id,
                material_id=material.id,
                weight_total=1000,
                weight_remaining=800,
                price=500,
                quantity=1,
            )
            shelf = StorageShelf(name='Shelf A', columns=4, slots_count=8, sort_order=1)
            db.session.add_all([admin, filament, shelf])
            db.session.commit()
            self.filament_id = filament.id
            self.shelf_id = shelf.id

        # Log in as admin
        self.client.post('/login', data={
            'email': 'admin@example.com',
            'password': 'password123',
        }, follow_redirects=True)

    def test_storage_page_renders(self):
        """Storage index renders with shelves and filaments."""
        resp = self.client.get('/storage')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'Shelf A', resp.data)

    def test_storage_page_public(self):
        """Storage page is accessible without authentication."""
        with self.app.test_client() as anon:
            resp = anon.get('/storage')
            self.assertEqual(resp.status_code, 200)

    def test_add_shelf(self):
        """POST /storage/shelf creates a new shelf."""
        self.client.post('/storage/shelf', data={
            'name': 'Shelf B',
            'columns': 3,
            'slots_count': 6,
        })
        with self.app.app_context():
            shelf = StorageShelf.query.filter_by(name='Shelf B').first()
            self.assertIsNotNone(shelf)
            self.assertEqual(shelf.columns, 3)
            self.assertEqual(shelf.slots_count, 6)

    def test_add_shelf_duplicate_name_skipped(self):
        """Adding a shelf with an existing name is silently skipped."""
        resp = self.client.post('/storage/shelf', data={
            'name': 'Shelf A',
            'columns': 2,
            'slots_count': 4,
        })
        # Should redirect (302) or return OK — the key is no duplicate is created
        self.assertIn(resp.status_code, (302, 200))
        with self.app.app_context():
            count = StorageShelf.query.filter_by(name='Shelf A').count()
            self.assertEqual(count, 1)

    def test_update_shelf(self):
        """POST /storage/shelf/<id>/update renames and resizes a shelf."""
        self.client.post(f'/storage/shelf/{self.shelf_id}/update', data={
            'name': 'Shelf A+',
            'columns': 6,
            'slots_count': 12,
        })
        with self.app.app_context():
            shelf = db.session.get(StorageShelf, self.shelf_id)
            self.assertEqual(shelf.name, 'Shelf A+')
            self.assertEqual(shelf.columns, 6)
            self.assertEqual(shelf.slots_count, 12)

    def test_delete_shelf(self):
        """POST /storage/shelf/<id>/delete removes a shelf."""
        # Create a shelf to delete
        self.client.post('/storage/shelf', data={
            'name': 'Shelf To Delete',
            'columns': 2,
            'slots_count': 4,
        })
        with self.app.app_context():
            shelf = StorageShelf.query.filter_by(name='Shelf To Delete').first()
            delete_id = shelf.id

        self.client.post(f'/storage/shelf/{delete_id}/delete')
        with self.app.app_context():
            self.assertIsNone(db.session.get(StorageShelf, delete_id))

    def test_assign_slot(self):
        """POST /storage/slot/assign places a filament on a shelf slot."""
        self.client.post('/storage/slot/assign', data={
            'shelf_id': self.shelf_id,
            'filament': f'{self.filament_id} - Storage Test PLA',
            'slot_index': 1,
        })
        with self.app.app_context():
            placement = StoragePlacement.query.filter_by(
                shelf_id=self.shelf_id, slot_index=1,
            ).first()
            self.assertIsNotNone(placement)
            self.assertEqual(placement.filament_id, self.filament_id)
            self.assertEqual(placement.orientation, 'standing')

    def test_assign_slot_rejects_duplicate(self):
        """Assigning to an occupied slot is rejected (quiet no-op)."""
        # First assignment
        self.client.post('/storage/slot/assign', data={
            'shelf_id': self.shelf_id,
            'filament': f'{self.filament_id} - Storage Test PLA',
            'slot_index': 1,
        })
        # Second assignment to same slot
        self.client.post('/storage/slot/assign', data={
            'shelf_id': self.shelf_id,
            'filament': f'{self.filament_id} - Storage Test PLA',
            'slot_index': 1,
        })
        with self.app.app_context():
            count = StoragePlacement.query.filter_by(
                shelf_id=self.shelf_id, slot_index=1,
            ).count()
            self.assertEqual(count, 1)

    def test_move_placement(self):
        """POST /storage/placement/<id>/move swaps or moves slot assignments."""
        # A filament may only occupy ONE slot (unique filament_id) — assigning
        # it to slot 2 MOVES it there instead of creating a second placement.
        self.client.post('/storage/slot/assign', data={
            'shelf_id': self.shelf_id,
            'filament': f'{self.filament_id} - Storage Test PLA',
            'slot_index': 1,
        })
        self.client.post('/storage/slot/assign', data={
            'shelf_id': self.shelf_id,
            'filament': f'{self.filament_id} - Storage Test PLA',
            'slot_index': 2,
        })
        with self.app.app_context():
            placements = StoragePlacement.query.filter_by(shelf_id=self.shelf_id).all()
            self.assertEqual(len(placements), 1)
            self.assertEqual(placements[0].slot_index, 2)
            p1 = placements[0]

        # Now place a SECOND filament so the move can swap two slots.
        with self.app.app_context():
            second = Filament(
                name='Storage Test PLA 2', brand_id=self.brand_id,
                color_id=self.color_id, material_id=self.material_id,
                weight_total=1000, weight_remaining=1000, price=500, quantity=1,
            )
            db.session.add(second)
            db.session.commit()
            second_id = second.id
        self.client.post('/storage/slot/assign', data={
            'shelf_id': self.shelf_id,
            'filament': f'{second_id} - Storage Test PLA 2',
            'slot_index': 1,
        })
        with self.app.app_context():
            p2 = StoragePlacement.query.filter_by(shelf_id=self.shelf_id, slot_index=1).first()
            self.assertIsNotNone(p2)
            self.assertNotEqual(p1.id, p2.id)

        self.client.post(f'/storage/placement/{p1.id}/move', data={
            'shelf_id': self.shelf_id,
            'slot_index': 1,
        })
        with self.app.app_context():
            p1_after = db.session.get(StoragePlacement, p1.id)
            p2_after = db.session.get(StoragePlacement, p2.id)
            self.assertEqual(p1_after.slot_index, 1)
            self.assertEqual(p2_after.slot_index, 2)

    def test_update_orientation(self):
        """POST /storage/placement/<id>/orientation changes orientation value."""
        self.client.post('/storage/slot/assign', data={
            'shelf_id': self.shelf_id,
            'filament': f'{self.filament_id} - Storage Test PLA',
            'slot_index': 1,
        })
        with self.app.app_context():
            p = StoragePlacement.query.filter_by(shelf_id=self.shelf_id, slot_index=1).first()
        self.client.post(f'/storage/placement/{p.id}/orientation', data={
            'orientation': 'lying',
        })
        with self.app.app_context():
            p_after = db.session.get(StoragePlacement, p.id)
            self.assertEqual(p_after.orientation, 'lying')

    def test_delete_placement(self):
        """POST /storage/placement/<id>/delete removes a slot assignment."""
        self.client.post('/storage/slot/assign', data={
            'shelf_id': self.shelf_id,
            'filament': f'{self.filament_id} - Storage Test PLA',
            'slot_index': 1,
        })
        with self.app.app_context():
            p = StoragePlacement.query.filter_by(shelf_id=self.shelf_id, slot_index=1).first()
            placement_id = p.id
        self.client.post(f'/storage/placement/{placement_id}/delete')
        with self.app.app_context():
            self.assertIsNone(db.session.get(StoragePlacement, placement_id))

    def test_reorder_shelves(self):
        """POST /storage/shelf/reorder updates sort_order via JSON."""
        # Add a second shelf
        self.client.post('/storage/shelf', data={
            'name': 'Shelf B',
            'columns': 2,
            'slots_count': 4,
        })
        with self.app.app_context():
            shelf_b = StorageShelf.query.filter_by(name='Shelf B').first()
        resp = self.client.post(
            '/storage/shelf/reorder',
            data=json.dumps({'order': [shelf_b.id, self.shelf_id]}),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(json.loads(resp.data)['ok'], True)
        with self.app.app_context():
            a = db.session.get(StorageShelf, self.shelf_id)
            b = db.session.get(StorageShelf, shelf_b.id)
            self.assertLess(b.sort_order, a.sort_order)


class HistoryRouteTests(unittest.TestCase):
    """Coverage for /history page rendering, filtering, pagination, and clearing."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix='filament-history-tests-')
        db_path = os.path.join(self.temp_dir, 'test.db')
        self.app = create_app({
            'TESTING': True,
            'SQLALCHEMY_DATABASE_URI': f'sqlite:///{db_path}',
            'PROJECT_UPLOAD_FOLDER': os.path.join(self.temp_dir, 'uploads'),
            'WTF_CSRF_ENABLED': False,
        })
        self.client = self.app.test_client()

        with self.app.app_context():
            admin = User(
                email='admin@example.com',
                name='Admin',
                password_hash=hash_password('password123'),
                role='admin',
            )
            db.session.add(admin)
            db.session.commit()

        self.client.post('/login', data={
            'email': 'admin@example.com',
            'password': 'password123',
        }, follow_redirects=True)

    def test_history_page_renders(self):
        """GET /history renders the movement history page."""
        resp = self.client.get('/history')
        self.assertEqual(resp.status_code, 200)

    def test_history_page_public(self):
        """History page is accessible without authentication."""
        with self.app.test_client() as anon:
            resp = anon.get('/history')
            self.assertEqual(resp.status_code, 200)

    def test_history_with_records(self):
        """Page renders when movement history records exist."""
        with self.app.app_context():
            m = MovementHistory(
                filament_name='Test PLA',
                action_type='add',
                weight=500.0,
                cost=0.0,
                currency='CZK',
                created_at=utc_now(),
            )
            db.session.add(m)
            db.session.commit()
        resp = self.client.get('/history')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'Test PLA', resp.data)

    def test_history_filter_by_action_type(self):
        """Query parameter ?action_type= filters movements."""
        with self.app.app_context():
            m1 = MovementHistory(
                filament_name='PLA A',
                action_type='add',
                weight=100.0,
                cost=0.0,
                currency='CZK',
                created_at=utc_now(),
            )
            m2 = MovementHistory(
                filament_name='PLA B',
                action_type='remove',
                weight=50.0,
                cost=0.0,
                currency='CZK',
                created_at=utc_now(),
            )
            db.session.add_all([m1, m2])
            db.session.commit()
        resp = self.client.get('/history?action_type=add')
        self.assertIn(b'PLA A', resp.data)
        self.assertNotIn(b'PLA B', resp.data)

    def test_history_filter_by_date_range(self):
        """Query params ?date_from= and ?date_to= filter by date range."""
        from datetime import timedelta
        now = utc_now()
        yesterday = now - timedelta(days=1)
        very_old = now - timedelta(days=30)
        with self.app.app_context():
            old = MovementHistory(
                filament_name='Old PLA',
                action_type='add',
                weight=100.0,
                cost=0.0,
                currency='CZK',
                created_at=very_old,
            )
            recent = MovementHistory(
                filament_name='Recent PETG',
                action_type='add',
                weight=200.0,
                cost=0.0,
                currency='CZK',
                created_at=yesterday,
            )
            db.session.add_all([old, recent])
            db.session.commit()
        # date_from=yesterday should include yesterday's record but not the old one
        date_str = yesterday.strftime('%Y-%m-%d')
        resp = self.client.get(f'/history?date_from={date_str}')
        self.assertIn(b'Recent PETG', resp.data)
        self.assertNotIn(b'Old PLA', resp.data)

    def test_history_pagination(self):
        """History page accepts ?per_page= query parameter."""
        from datetime import timedelta
        base_time = utc_now()
        with self.app.app_context():
            for i in range(25):
                db.session.add(MovementHistory(
                    filament_name=f'Filament #{i:02d}',
                    action_type='add',
                    weight=100.0,
                    cost=0.0,
                    currency='CZK',
                    created_at=base_time + timedelta(seconds=i),
                ))
            db.session.commit()
        # Page 1 (10 per page default): most recent 10
        resp = self.client.get('/history?per_page=10')
        self.assertEqual(resp.status_code, 200)
        # First page shows the most recently added (Filament #24 down to #15)
        self.assertIn(b'Filament #24', resp.data)
        self.assertIn(b'Filament #15', resp.data)
        # Page 2: next 10 (#14 down to #5)
        resp2 = self.client.get('/history?per_page=10&page=2')
        self.assertIn(b'Filament #14', resp2.data)
        self.assertNotIn(b'Filament #24', resp2.data)

    def test_history_clear(self):
        """POST /history/clear deletes all movement history records."""
        with self.app.app_context():
            db.session.add(MovementHistory(
                filament_name='To Be Cleared',
                action_type='add',
                weight=100.0,
                cost=0.0,
                currency='CZK',
                created_at=utc_now(),
            ))
            db.session.commit()
        self.client.post('/history/clear', follow_redirects=True)
        with self.app.app_context():
            count = MovementHistory.query.count()
            self.assertEqual(count, 0)


class PWARouteTests(unittest.TestCase):
    """Coverage for PWA manifest.json and sw.js endpoints."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix='filament-pwa-tests-')
        db_path = os.path.join(self.temp_dir, 'test.db')
        self.app = create_app({
            'TESTING': True,
            'SQLALCHEMY_DATABASE_URI': f'sqlite:///{db_path}',
            'PROJECT_UPLOAD_FOLDER': os.path.join(self.temp_dir, 'uploads'),
            'WTF_CSRF_ENABLED': False,
        })
        self.client = self.app.test_client()

    def test_manifest_returns_json(self):
        """GET /manifest.json returns valid JSON with correct content type."""
        resp = self.client.get('/manifest.json')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.content_type, 'application/json')
        data = json.loads(resp.data)
        self.assertEqual(data['name'], 'Filament Manager')
        self.assertEqual(data['display'], 'standalone')
        self.assertIn('icons', data)
        self.assertGreater(len(data['icons']), 0)

    def test_manifest_no_auth_required(self):
        """Manifest is publicly accessible (no login required)."""
        resp = self.client.get('/manifest.json')
        self.assertEqual(resp.status_code, 200)

    def test_service_worker_returns_js(self):
        """GET /sw.js returns JavaScript with correct content type."""
        resp = self.client.get('/sw.js')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.content_type, 'application/javascript')
        self.assertIn(b'CACHE_NAME', resp.data)
        self.assertIn(b'skipWaiting', resp.data)

    def test_service_worker_no_auth_required(self):
        """Service worker is publicly accessible (no login required)."""
        resp = self.client.get('/sw.js')
        self.assertEqual(resp.status_code, 200)


if __name__ == '__main__':
    unittest.main()
