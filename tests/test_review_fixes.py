"""Regression tests for the v1.120.2 review-fix batch (K1–K4, H1–H8).

Each test targets one specific bug found in the deep code review:
  K1 — project delete with todos crashed (AttributeError: 'position')
  K2 — undo of "remove spool" always failed (wrong snapshot key)
  K3 — waste/maintenance undo was dead code (NOT NULL + no session slot + 14s TTL)
  K4 — waste_record FK migration checked the wrong PRAGMA column
  H1 — quote delete/export lacked project-ownership checks
  H2 — non-admins could upload orphaned models
  H3 — calculator float() input parsing raised HTTP 500
  H4 — project create/edit crashed on malformed due_date
  H5 — partial ORM mutation leaked across requests after failed edits
  H6 — storage routes crashed on non-numeric input; shelf shrink deleted placements
  H7 — backup import had no decompression size limits
  H8 — backup import crashed/failed on unparseable timestamps
"""
import gzip
import io
import json
import os
import shutil
import sqlite3
import tarfile
import tempfile
import unittest
from unittest import mock

from app import create_app
from auth import hash_password
from database import db
from models import (
    Brand, Color, Filament, FilamentUndoLog, Material, MovementHistory,
    Project, ProjectTodo, ProjectQuote, StoragePlacement, StorageShelf,
    User, WasteRecord,
)
from routes.inventory_helpers import _UNDO_SESSION_KEY
from utils import utc_now


def _make_legacy_db(path):
    """Create a legacy-schema SQLite DB: waste_record without CASCADE FK,
    waste_file, filament_undo_log with NOT NULL snapshot_data."""
    con = sqlite3.connect(path)
    con.executescript("""
        CREATE TABLE user (
            id INTEGER NOT NULL PRIMARY KEY,
            email VARCHAR(255) NOT NULL UNIQUE,
            name VARCHAR(120),
            password_hash VARCHAR(255) NOT NULL,
            role VARCHAR(10) NOT NULL DEFAULT 'user',
            is_active BOOLEAN NOT NULL DEFAULT 1
        );
        CREATE TABLE filament (
            id INTEGER NOT NULL PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            brand_id INTEGER, color_id INTEGER, material_id INTEGER,
            weight_total FLOAT NOT NULL DEFAULT 1000,
            weight_remaining FLOAT NOT NULL DEFAULT 1000,
            price NUMERIC(10,2) NOT NULL DEFAULT 0,
            quantity INTEGER NOT NULL DEFAULT 1,
            min_stock_grams FLOAT NOT NULL DEFAULT 0,
            max_stock_grams FLOAT NOT NULL DEFAULT 0,
            tag_text TEXT, quality_stringing TEXT, quality_adhesion TEXT,
            quality_drying TEXT, quality_profile TEXT, quality_notes TEXT,
            recommended_nozzle_temp INTEGER, recommended_bed_temp INTEGER,
            reorder_alert_snoozed BOOLEAN NOT NULL DEFAULT 0,
            shop_url VARCHAR(500)
        );
        CREATE TABLE waste_record (
            id INTEGER NOT NULL PRIMARY KEY,
            filament_id INTEGER NOT NULL,
            project_id INTEGER,
            reason VARCHAR(50) NOT NULL DEFAULT 'other',
            weight_grams FLOAT NOT NULL DEFAULT 0.0,
            notes TEXT,
            created_at DATETIME NOT NULL,
            recorded_by_user_id INTEGER,
            FOREIGN KEY (filament_id) REFERENCES filament (id) ON DELETE NO ACTION,
            FOREIGN KEY (project_id) REFERENCES project (id) ON DELETE NO ACTION,
            FOREIGN KEY (recorded_by_user_id) REFERENCES user (id) ON DELETE NO ACTION
        );
        CREATE TABLE waste_file (
            id INTEGER NOT NULL PRIMARY KEY,
            waste_record_id INTEGER NOT NULL,
            filename VARCHAR(255) NOT NULL,
            filepath VARCHAR(255) NOT NULL,
            uploaded_at DATETIME,
            FOREIGN KEY (waste_record_id) REFERENCES waste_record (id) ON DELETE NO ACTION
        );
        CREATE TABLE filament_undo_log (
            id INTEGER NOT NULL PRIMARY KEY,
            created_at DATETIME NOT NULL,
            user_id INTEGER,
            action_type VARCHAR(40) NOT NULL,
            filament_id INTEGER,
            snapshot_data TEXT NOT NULL,
            expires_at DATETIME,
            is_consumed BOOLEAN NOT NULL DEFAULT 0,
            consumed_at DATETIME,
            FOREIGN KEY (user_id) REFERENCES user (id) ON DELETE CASCADE,
            FOREIGN KEY (filament_id) REFERENCES filament (id) ON DELETE CASCADE
        );
    """)
    con.execute(
        "INSERT INTO filament (id, name) VALUES (1, 'Legacy Filament')"
    )
    con.execute(
        "INSERT INTO user (id, email, name, password_hash, role) "
        "VALUES (1, 'legacy@example.com', 'Legacy', 'x', 'user')"
    )
    con.commit()
    con.close()


class _BaseFixesTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix='review-fixes-')
        db_path = os.path.join(self.temp_dir, 'test.db')
        self.upload_dir = os.path.join(self.temp_dir, 'uploads')
        os.makedirs(self.upload_dir, exist_ok=True)
        self.app = create_app({
            'TESTING': True,
            'AUTH_REQUIRED_IN_TESTS': True,
            'SQLALCHEMY_DATABASE_URI': f'sqlite:///{db_path}',
            'PROJECT_UPLOAD_FOLDER': self.upload_dir,
            'WTF_CSRF_ENABLED': False,
        })
        self.client = self.app.test_client()

        with self.app.app_context():
            admin = User(
                email='admin@example.com', name='Admin',
                password_hash=hash_password('password123'), role='admin',
            )
            owner = User(
                email='owner@example.com', name='Owner',
                password_hash=hash_password('password123'), role='user',
            )
            db.session.add_all([admin, owner])
            db.session.commit()
            self.admin_id = admin.id
            self.owner_id = owner.id

            brand = Brand.query.filter_by(name='Prusament').first()
            material = Material.query.filter_by(name='PLA').first()
            color = Color.query.first()
            self.filament = Filament(
                name='Fix PLA', brand_id=brand.id, material_id=material.id,
                color_id=color.id, weight_total=1000, weight_remaining=1000,
                price=500, quantity=1,
            )
            db.session.add(self.filament)
            db.session.commit()
            self.filament_id = self.filament.id

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def login(self, email='admin@example.com'):
        return self.client.post(
            '/login',
            data={'email': email, 'password': 'password123'},
            follow_redirects=True,
        )


# ── K1: project delete/undo with todos ────────────────────────────────────

class ProjectDeleteWithTodosTests(_BaseFixesTests):
    def _project_with_todo(self):
        with self.app.app_context():
            project = Project(
                name='Todo Project', status='APPROVED', owner_user_id=self.owner_id,
                due_date=utc_now() + __import__('datetime').timedelta(days=3),
            )
            db.session.add(project)
            db.session.flush()
            db.session.add(ProjectTodo(project_id=project.id, body='Do the thing', is_done=False))
            db.session.commit()
            return project.id

    def test_project_delete_with_todos_succeeds(self):
        self.login()
        project_id = self._project_with_todo()
        response = self.client.post(f'/projects/{project_id}/delete', follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            self.assertIsNone(db.session.get(Project, project_id))

    def test_project_undo_restores_todos_and_due_date(self):
        self.login()
        project_id = self._project_with_todo()
        self.client.post(f'/projects/{project_id}/delete', follow_redirects=False)
        with self.client.session_transaction() as sess:
            self.assertIn('project_pending_undo', sess)
        response = self.client.post('/projects/undo', follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            restored = Project.query.filter_by(name='Todo Project').first()
            self.assertIsNotNone(restored)
            self.assertIsNotNone(restored.due_date, 'due_date must survive the undo round-trip')
            self.assertEqual(len(restored.todos), 1)
            self.assertEqual(restored.todos[0].body, 'Do the thing')


# ── K2: undo of remove-spool ──────────────────────────────────────────────

class RemoveSpoolUndoTests(_BaseFixesTests):
    def test_remove_spool_undo_restores_stock(self):
        self.login()
        response = self.client.post(f'/remove_spool/{self.filament_id}', follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        with self.client.session_transaction() as sess:
            slot = sess.get(_UNDO_SESSION_KEY)
            self.assertIsNotNone(slot, 'remove-spool must set the undo session slot')
            undo_log_id = slot['undo_log_id']

        response = self.client.post('/inventory/undo', data={'undo_log_id': undo_log_id},
                                    follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            filament = db.session.get(Filament, self.filament_id)
            self.assertEqual(filament.quantity, 1)
            self.assertEqual(filament.weight_remaining, 1000)


# ── K3: waste undo (undo log + session slot + restore) ────────────────────

class WasteUndoFixesTests(_BaseFixesTests):
    def _waste_record(self):
        with self.app.app_context():
            rec = WasteRecord(
                filament_id=self.filament_id, reason='stringing',
                weight_grams=42.0, notes='waste it',
                recorded_by_user_id=self.admin_id,
            )
            db.session.add(rec)
            db.session.commit()
            return rec.id

    def test_waste_delete_creates_undo_log_and_session_slot(self):
        self.login()
        rec_id = self._waste_record()
        response = self.client.post(f'/waste/{rec_id}/_delete')
        self.assertEqual(response.status_code, 200)
        with self.app.app_context():
            log = FilamentUndoLog.query.filter_by(action_type='delete_waste').first()
            self.assertIsNotNone(log)
            self.assertIsNone(log.snapshot_data, 'snapshot_data must accept NULL')
            self.assertGreaterEqual(
                (log.expires_at - utc_now()).total_seconds(), 60,
                'undo TTL must be minutes, not 14 seconds',
            )
        with self.client.session_transaction() as sess:
            self.assertIn(_UNDO_SESSION_KEY, sess)
            self.assertEqual(sess[_UNDO_SESSION_KEY]['title_key'],
                             'undo_toast_waste_delete_title')

    def test_waste_undo_restores_record(self):
        self.login()
        rec_id = self._waste_record()
        self.client.post(f'/waste/{rec_id}/_delete')
        with self.client.session_transaction() as sess:
            undo_log_id = sess[_UNDO_SESSION_KEY]['undo_log_id']
        response = self.client.post('/inventory/undo', data={'undo_log_id': undo_log_id},
                                    follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            restored = WasteRecord.query.filter_by(notes='waste it').first()
            self.assertIsNotNone(restored)
            self.assertEqual(restored.weight_grams, 42.0)
            self.assertEqual(restored.reason, 'stringing')


# ── K4 + K3-migration: legacy schema migrations ───────────────────────────

class LegacySchemaMigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix='migration-fixes-')
        self.db_path = os.path.join(self.temp_dir, 'legacy.db')
        _make_legacy_db(self.db_path)
        self.app = create_app({
            'TESTING': True,
            'SQLALCHEMY_DATABASE_URI': f'sqlite:///{self.db_path}',
            'PROJECT_UPLOAD_FOLDER': os.path.join(self.temp_dir, 'uploads'),
            'WTF_CSRF_ENABLED': False,
        })
        self.ctx = self.app.app_context()
        self.ctx.push()
        from migrations import run_migrations
        run_migrations(self.app)

    def tearDown(self):
        self.ctx.pop()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_waste_fk_migration_applies_cascade(self):
        con = sqlite3.connect(self.db_path)
        rows = list(con.execute("PRAGMA foreign_key_list(waste_record)"))
        con.close()
        filament_fk = [r for r in rows if r[3] == 'filament_id']
        self.assertTrue(filament_fk, 'filament_id FK must exist')
        self.assertEqual(filament_fk[0][6], 'CASCADE')

    def test_undo_log_snapshot_made_nullable(self):
        con = sqlite3.connect(self.db_path)
        row = [r for r in con.execute("PRAGMA table_info(filament_undo_log)")
               if r[1] == 'snapshot_data'][0]
        con.close()
        self.assertEqual(row[3], 0, 'snapshot_data must be nullable after migration')

    def test_legacy_rows_survive_migrations(self):
        con = sqlite3.connect(self.db_path)
        count = con.execute("SELECT COUNT(*) FROM filament_undo_log").fetchone()[0]
        con.close()
        self.assertEqual(count, 0)  # empty legacy table rebuilt without error

    def test_null_snapshot_insert_works_after_migration(self):
        con = sqlite3.connect(self.db_path)
        con.execute("PRAGMA foreign_keys=ON")
        con.execute(
            "INSERT INTO filament_undo_log (created_at, action_type, snapshot_data) "
            "VALUES ('2026-07-31 10:00:00', 'delete_waste', NULL)"
        )
        con.commit()
        con.close()


# ── H1: quote authorization ───────────────────────────────────────────────

class QuoteAuthorizationTests(_BaseFixesTests):
    def _quote(self, owner_id):
        with self.app.app_context():
            project = Project(name=f'Project {owner_id}', owner_user_id=owner_id)
            db.session.add(project)
            db.session.flush()
            quote = ProjectQuote(
                project_id=project.id, filament_id=self.filament_id,
                filament_name='Quote', weight=100, print_time=0,
                final_price=250, currency='CZK',
            )
            db.session.add(quote)
            db.session.commit()
            return quote.id, project.id

    def test_delete_quote_denied_for_non_owner(self):
        self.login('owner@example.com')
        quote_id, _ = self._quote(self.admin_id)
        response = self.client.post(f'/calculator/quote/{quote_id}/delete', follow_redirects=False)
        self.assertEqual(response.status_code, 403)
        with self.app.app_context():
            self.assertIsNotNone(db.session.get(ProjectQuote, quote_id))

    def test_export_quote_denied_for_non_owner(self):
        self.login('owner@example.com')
        quote_id, _ = self._quote(self.admin_id)
        response = self.client.get(f'/calculator/quote/{quote_id}/export')
        self.assertEqual(response.status_code, 403)

    def test_owner_can_delete_own_quote(self):
        self.login('owner@example.com')
        quote_id, _ = self._quote(self.owner_id)
        response = self.client.post(f'/calculator/quote/{quote_id}/delete', follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            self.assertIsNone(db.session.get(ProjectQuote, quote_id))

    def test_calculator_project_denied_for_non_owner(self):
        self.login('owner@example.com')
        with self.app.app_context():
            project = Project(name='Admin Project', owner_user_id=self.admin_id)
            db.session.add(project)
            db.session.commit()
            project_id = project.id
        response = self.client.get(f'/calculator/project/{project_id}')
        self.assertEqual(response.status_code, 403)


# ── H2: orphan model upload ───────────────────────────────────────────────

class ModelUploadOrphanTests(_BaseFixesTests):
    def _upload(self):
        return self.client.post(
            '/models/upload',
            data={'file': (io.BytesIO(b'stl-bytes'), 'test_model.stl')},
            content_type='multipart/form-data',
            follow_redirects=False,
        )

    def test_non_admin_orphan_upload_denied(self):
        self.login('owner@example.com')
        response = self._upload()
        self.assertEqual(response.status_code, 302)
        from models import ProjectFile
        with self.app.app_context():
            self.assertEqual(ProjectFile.query.count(), 0)

    def test_admin_orphan_upload_allowed(self):
        self.login()
        response = self._upload()
        self.assertEqual(response.status_code, 302)
        from models import ProjectFile
        with self.app.app_context():
            orphan = ProjectFile.query.first()
            self.assertIsNotNone(orphan)
            self.assertIsNone(orphan.project_id)


# ── H3/H4: malformed input handling ───────────────────────────────────────

class MalformedInputTests(_BaseFixesTests):
    def test_calculator_invalid_weight_no_500(self):
        self.login()
        response = self.client.post('/calculator', data={
            'filament_id': self.filament_id,
            'weight': 'abc',
            'print_time': 'xyz',
            'margin_percent': '12%',
        })
        self.assertEqual(response.status_code, 200)

    def test_calculator_project_invalid_margin_no_500(self):
        self.login()
        with self.app.app_context():
            project = Project(name='Calc Project', owner_user_id=self.admin_id)
            db.session.add(project)
            db.session.commit()
            project_id = project.id
        response = self.client.get(f'/calculator/project/{project_id}?margin=oops')
        self.assertEqual(response.status_code, 200)

    def test_project_create_invalid_due_date_no_500(self):
        self.login()
        response = self.client.post('/projects/create', data={
            'name': 'Bad Date Project',
            'due_date': 'not-a-date',
        }, follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            self.assertIsNotNone(Project.query.filter_by(name='Bad Date Project').first())


# ── H5: no partial ORM mutation after failed edit ─────────────────────────

class InventoryEditNoPartialSaveTests(_BaseFixesTests):
    def test_failed_edit_keeps_original_values(self):
        self.login()
        response = self.client.post(f'/edit/{self.filament_id}', data={
            'name': 'Should Not Stick',
            'weight_remaining': 'not-a-number',
            'price': '10',
        }, follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            filament = db.session.get(Filament, self.filament_id)
            self.assertEqual(filament.name, 'Fix PLA')
            self.assertEqual(filament.weight_remaining, 1000)
            self.assertEqual(float(filament.price), 500.0)


# ── H6: storage input robustness ──────────────────────────────────────────

class StorageInputRobustnessTests(_BaseFixesTests):
    def test_add_shelf_invalid_columns_no_500(self):
        self.login()
        response = self.client.post('/storage/shelf', data={
            'name': 'Weird Shelf',
            'columns': 'abc',
            'slots_count': 'xyz',
        }, follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            shelf = StorageShelf.query.filter_by(name='Weird Shelf').first()
            self.assertIsNotNone(shelf)
            self.assertEqual(shelf.columns, 4)
            self.assertEqual(shelf.slots_count, 12)

    def test_shelf_shrink_never_deletes_placements(self):
        self.login()
        with self.app.app_context():
            shelf = StorageShelf(name='Full Shelf', columns=1, slots_count=3)
            db.session.add(shelf)
            db.session.flush()
            for slot in (1, 2, 3):
                db.session.add(StoragePlacement(
                    shelf_id=shelf.id, filament_id=self.filament_id,
                    slot_index=slot, orientation='standing',
                ))
            db.session.commit()
            shelf_id = shelf.id

        response = self.client.post(f'/storage/shelf/{shelf_id}/update', data={
            'name': 'Full Shelf',
            'columns': '1',
            'slots_count': '1',
        }, follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            shelf = db.session.get(StorageShelf, shelf_id)
            placements = StoragePlacement.query.filter_by(shelf_id=shelf_id).all()
            self.assertEqual(len(placements), 3, 'shrinking must not delete placements')
            self.assertGreaterEqual(shelf.slots_count, 3, 'shelf must expand to fit placements')


# ── H7/H8: backup import robustness ───────────────────────────────────────

class BackupImportRobustnessTests(_BaseFixesTests):
    def _post_import(self, manifest, extra_members=None):
        import tarfile as tf
        buf = io.BytesIO()
        with tf.open(fileobj=buf, mode='w:gz') as archive:
            mb = json.dumps(manifest, ensure_ascii=False).encode('utf-8')
            info = tf.TarInfo('manifest.json')
            info.size = len(mb)
            archive.addfile(info, io.BytesIO(mb))
            for name, content in (extra_members or {}).items():
                info = tf.TarInfo(name)
                info.size = len(content)
                archive.addfile(info, io.BytesIO(content))
        buf.seek(0)
        return self.client.post(
            '/import',
            data={'file': (buf, 'backup.tar.gz'), 'conflict_mode': 'merge'},
            content_type='multipart/form-data',
            follow_redirects=False,
        )

    def test_import_with_invalid_timestamp_fails_atomically(self):
        """A corrupt timestamp aborts the whole import (atomicity) — no 500,
        no partial data, and the import transaction issue (already-begun
        session) does not surface."""
        self.login()
        manifest = {
            'backup_meta': {'format_version': 2},
            'brands': [{'name': 'Atomic Brand', 'shop_url': None}],
            'movement_history': [{
                'filament_name': 'Ghost PLA',
                'action_type': 'add',
                'weight': 10.0,
                'cost': 1.0,
                'currency': 'CZK',
                'created_at': 'total-garbage-timestamp',
                'note': None,
            }],
        }
        response = self._post_import(manifest)
        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            from models import Brand
            self.assertIsNone(
                Brand.query.filter_by(name='Atomic Brand').first(),
                'import must roll back atomically on corrupt data',
            )
            self.assertIsNone(MovementHistory.query.filter_by(filament_name='Ghost PLA').first())

    def test_import_oversized_member_fails_gracefully(self):
        self.login()
        manifest = {'backup_meta': {'format_version': 2}}
        with mock.patch('routes.backup_helpers._MAX_BACKUP_MEMBER_BYTES', 1024):
            response = self._post_import(
                manifest,
                extra_members={'uploads/big.bin': b'x' * 4096},
            )
        self.assertEqual(response.status_code, 302)


if __name__ == '__main__':
    unittest.main()
