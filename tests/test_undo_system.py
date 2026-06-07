"""Tests for the database-backed undo system — FilamentUndoLog model, snapshot creation,
consumption, expiration, and filament restoration."""
import json
import os
import shutil
import tempfile
import unittest
from datetime import timedelta

from app import create_app
from auth import hash_password
from database import db
from models import (
    Brand, Color, Filament, FilamentUndoLog, Material, ProjectFilament,
    ProjectQuote, User,
)
from utils import utc_now


class _BaseUndoTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix='undo-tests-')
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
            admin = User(
                email='admin@example.com',
                name='Admin',
                password_hash=hash_password('password123'),
                role='admin',
            )
            brand = Brand.query.first()
            color = Color.query.first()
            material = Material.query.first()

            self.filament = Filament(
                name='Undo PLA',
                brand_id=brand.id,
                color_id=color.id,
                material_id=material.id,
                weight_total=1000,
                weight_remaining=800,
                price=500,
                quantity=2,
                tag_text='undo_test',
                min_stock_grams=100,
                quality_stringing='low',
            )
            db.session.add_all([admin, self.filament])
            db.session.commit()
            self.admin_id = admin.id
            self.filament_id = self.filament.id

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def login_admin(self):
        return self.client.post(
            '/login',
            data={'email': 'admin@example.com', 'password': 'password123'},
            follow_redirects=True,
        )


class UndoSnapshotCreationTests(_BaseUndoTests):
    def test_create_snapshot_stores_data(self):
        with self.app.app_context():
            from utils import create_undo_snapshot
            undo_log = create_undo_snapshot(
                user_id=self.admin_id,
                action_type='delete_filament',
                filament=self.filament,
            )
            self.assertIsNotNone(undo_log)
            self.assertEqual(undo_log.user_id, self.admin_id)
            self.assertEqual(undo_log.action_type, 'delete_filament')
            self.assertEqual(undo_log.filament_id, self.filament_id)
            self.assertFalse(undo_log.is_consumed)

    def test_create_snapshot_with_project_references(self):
        with self.app.app_context():
            from utils import create_undo_snapshot
            pf = ProjectFilament(
                project_id=1,
                filament_id=self.filament_id,
                estimated_weight=50.0,
                is_used=False,
            )
            undo_log = create_undo_snapshot(
                user_id=self.admin_id,
                action_type='delete_filament',
                filament=self.filament,
                project_filaments=[pf],
                project_quote_ids=[1, 2],
            )
            snapshot = json.loads(undo_log.snapshot_data)
            self.assertEqual(len(snapshot['project_filaments']), 1)
            self.assertEqual(snapshot['project_quote_ids'], [1, 2])

    def test_create_bulk_snapshot(self):
        with self.app.app_context():
            from utils import create_bulk_undo_snapshot
            entries = [{
                'filament': self.filament,
                'project_filaments': [],
                'project_quote_ids': [1],
            }]
            bulk_log = create_bulk_undo_snapshot(self.admin_id, entries)
            self.assertIsNotNone(bulk_log)
            self.assertEqual(bulk_log.action_type, 'bulk_delete')
            snapshot = json.loads(bulk_log.snapshot_data)
            self.assertEqual(snapshot['type'], 'bulk_delete')

    def test_snapshot_expires_future(self):
        with self.app.app_context():
            from utils import create_undo_snapshot
            undo_log = create_undo_snapshot(
                user_id=self.admin_id,
                action_type='delete_filament',
                filament=self.filament,
            )
            self.assertGreater(undo_log.expires_at, utc_now())

    def test_snapshot_contains_full_filament_data(self):
        with self.app.app_context():
            from utils import create_undo_snapshot
            undo_log = create_undo_snapshot(
                user_id=self.admin_id,
                action_type='delete_filament',
                filament=self.filament,
            )
            snapshot = json.loads(undo_log.snapshot_data)
            self.assertEqual(snapshot['filament']['name'], 'Undo PLA')
            self.assertAlmostEqual(snapshot['filament']['weight_remaining'], 800.0)
            self.assertAlmostEqual(snapshot['filament']['min_stock_grams'], 100.0)


class GetPendingUndoTests(_BaseUndoTests):
    def test_get_pending_finds_recent(self):
        with self.app.app_context():
            from utils import create_undo_snapshot, get_pending_undo
            create_undo_snapshot(
                user_id=self.admin_id,
                action_type='delete_filament',
                filament=self.filament,
            )
            pending = get_pending_undo(self.admin_id)
            self.assertIsNotNone(pending)
            self.assertEqual(pending.action_type, 'delete_filament')

    def test_get_pending_returns_none_when_expired(self):
        with self.app.app_context():
            from utils import get_pending_undo
            # Create an expired log
            log = FilamentUndoLog(
                user_id=self.admin_id,
                action_type='delete_filament',
                filament_id=self.filament_id,
                snapshot_data='{}',
                expires_at=utc_now() - timedelta(minutes=1),
                is_consumed=False,
            )
            db.session.add(log)
            db.session.commit()

            pending = get_pending_undo(self.admin_id)
            self.assertIsNone(pending)

    def test_get_pending_returns_none_when_consumed(self):
        with self.app.app_context():
            from utils import get_pending_undo
            log = FilamentUndoLog(
                user_id=self.admin_id,
                action_type='delete_filament',
                filament_id=self.filament_id,
                snapshot_data='{}',
                expires_at=utc_now() + timedelta(hours=1),
                is_consumed=True,
            )
            db.session.add(log)
            db.session.commit()

            pending = get_pending_undo(self.admin_id)
            self.assertIsNone(pending)


class ConsumeUndoTests(_BaseUndoTests):
    def test_consume_marks_as_consumed(self):
        with self.app.app_context():
            from utils import create_undo_snapshot, consume_undo_log
            undo_log = create_undo_snapshot(
                user_id=self.admin_id,
                action_type='delete_filament',
                filament=self.filament,
            )
            data = consume_undo_log(undo_log.id, self.admin_id)
            self.assertIsNotNone(data)
            self.assertEqual(data['filament']['name'], 'Undo PLA')

            # Verify consumed
            log = db.session.get(FilamentUndoLog, undo_log.id)
            self.assertTrue(log.is_consumed)
            self.assertIsNotNone(log.consumed_at)

    def test_consume_twice_returns_none(self):
        with self.app.app_context():
            from utils import create_undo_snapshot, consume_undo_log
            undo_log = create_undo_snapshot(
                user_id=self.admin_id,
                action_type='delete_filament',
                filament=self.filament,
            )
            consume_undo_log(undo_log.id, self.admin_id)
            data = consume_undo_log(undo_log.id, self.admin_id)
            self.assertIsNone(data)

    def test_consume_wrong_user_returns_none(self):
        with self.app.app_context():
            from utils import create_undo_snapshot, consume_undo_log
            undo_log = create_undo_snapshot(
                user_id=self.admin_id,
                action_type='delete_filament',
                filament=self.filament,
            )
            data = consume_undo_log(undo_log.id, 99999)
            self.assertIsNone(data)

    def test_consume_nonexistent_returns_none(self):
        with self.app.app_context():
            from utils import consume_undo_log
            data = consume_undo_log(99999, self.admin_id)
            self.assertIsNone(data)

    def test_consume_expired_returns_none(self):
        with self.app.app_context():
            from utils import consume_undo_log
            log = FilamentUndoLog(
                user_id=self.admin_id,
                action_type='delete_filament',
                filament_id=self.filament_id,
                snapshot_data='{"test": true}',
                expires_at=utc_now() - timedelta(minutes=1),
                is_consumed=False,
            )
            db.session.add(log)
            db.session.commit()

            data = consume_undo_log(log.id, self.admin_id)
            self.assertIsNone(data)


class PurgeExpiredTests(_BaseUndoTests):
    def test_purge_expired_removes_old(self):
        with self.app.app_context():
            from utils import purge_expired_undo_logs
            # Create expired
            log1 = FilamentUndoLog(
                user_id=self.admin_id,
                action_type='delete_filament',
                filament_id=self.filament_id,
                snapshot_data='{}',
                expires_at=utc_now() - timedelta(minutes=1),
                is_consumed=False,
            )
            # Create valid
            log2 = FilamentUndoLog(
                user_id=self.admin_id,
                action_type='delete_filament',
                filament_id=self.filament_id,
                snapshot_data='{}',
                expires_at=utc_now() + timedelta(hours=1),
                is_consumed=False,
            )
            db.session.add_all([log1, log2])
            db.session.commit()

            count = purge_expired_undo_logs()
            self.assertGreaterEqual(count, 1)

            remaining = FilamentUndoLog.query.count()
            self.assertEqual(remaining, 1)


class RestoreFromSnapshotTests(_BaseUndoTests):
    def test_restore_deleted_filament(self):
        with self.app.app_context():
            from utils import restore_filament_from_snapshot, create_undo_snapshot
            undo_log = create_undo_snapshot(
                user_id=self.admin_id,
                action_type='delete_filament',
                filament=self.filament,
            )
            snapshot = json.loads(undo_log.snapshot_data)

            # Delete then restore
            db.session.delete(self.filament)
            db.session.commit()

            restored = restore_filament_from_snapshot(snapshot)
            self.assertIsNotNone(restored)
            self.assertEqual(restored.name, 'Undo PLA')
            self.assertAlmostEqual(restored.weight_remaining, 800.0)

    def test_restore_updates_existing_filament(self):
        with self.app.app_context():
            from utils import create_undo_snapshot, restore_filament_from_snapshot
            undo_log = create_undo_snapshot(
                user_id=self.admin_id,
                action_type='delete_filament',
                filament=self.filament,
            )
            snapshot = json.loads(undo_log.snapshot_data)

            # Modify then restore
            self.filament.name = 'Modified'
            self.filament.weight_remaining = 300
            db.session.commit()

            restored = restore_filament_from_snapshot(snapshot)
            self.assertEqual(restored.name, 'Undo PLA')
            self.assertAlmostEqual(restored.weight_remaining, 800.0)

    def test_restore_bulk(self):
        with self.app.app_context():
            from utils import restore_bulk_from_snapshot, create_bulk_undo_snapshot
            entry = {
                'filament': self.filament,
                'project_filaments': [],
                'project_quote_ids': [],
            }
            bulk_log = create_bulk_undo_snapshot(self.admin_id, [entry])
            snapshot = json.loads(bulk_log.snapshot_data)

            restored = restore_bulk_from_snapshot(snapshot)
            self.assertEqual(len(restored), 1)
            self.assertEqual(restored[0].name, 'Undo PLA')


if __name__ == '__main__':
    unittest.main()
