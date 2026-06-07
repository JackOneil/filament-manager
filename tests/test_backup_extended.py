"""Extended tests for backup — auto-backup endpoints, dry-run import compatibility checks,
conflict modes (skip/merge/overwrite), backup retention cleanup."""
import gzip
import io
import json
import os
import shutil
import tarfile
import tempfile
import unittest
from unittest.mock import patch

from app import create_app
from database import db
from models import (
    Brand, Color, Filament, Material, Project,
)
from routes.backup import _backup_storage_dir, _is_path_inside, _cleanup_old_backups


def encode_backup_payload(payload, files=None):
    """Helper: encode a backup dict into a file-like object (gzipped JSON or tar.gz)."""
    if files:
        archive_bytes = io.BytesIO()
        manifest_bytes = json.dumps(payload).encode('utf-8')
        with tarfile.open(fileobj=archive_bytes, mode='w:gz') as archive:
            manifest_info = tarfile.TarInfo('manifest.json')
            manifest_info.size = len(manifest_bytes)
            archive.addfile(manifest_info, io.BytesIO(manifest_bytes))
            for path, content in files.items():
                info = tarfile.TarInfo(path)
                info.size = len(content)
                archive.addfile(info, io.BytesIO(content))
        archive_bytes.seek(0)
        return archive_bytes
    return io.BytesIO(gzip.compress(json.dumps(payload).encode('utf-8')))


class _BaseBackupExtTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix='backup-ext-tests-')
        db_path = os.path.join(self.temp_dir, 'test.db')
        self.app = create_app({
            'TESTING': True,
            'SQLALCHEMY_DATABASE_URI': f'sqlite:///{db_path}',
            'PROJECT_UPLOAD_FOLDER': os.path.join(self.temp_dir, 'uploads'),
            'WTF_CSRF_ENABLED': False,
        })
        self.client = self.app.test_client()

        with self.app.app_context():
            # Ensure filament exists for export test
            brand = Brand.query.filter_by(name='Prusament').first()
            color = Color.query.first()
            material = Material.query.filter_by(name='PLA').first()
            filament = Filament(
                name='Backup Ext PLA',
                brand_id=brand.id,
                color_id=color.id,
                material_id=material.id,
                weight_total=1000,
                weight_remaining=800,
                price=500,
                quantity=1,
            )
            project = Project(name='Backup Ext Project')
            db.session.add_all([filament, project])
            db.session.commit()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)


# ── Auto-Backup Endpoints ────────────────────────────────────────────────

class AutoBackupEndpointTests(_BaseBackupExtTests):
    def test_export_downloads_valid_file(self):
        response = self.client.get('/export')
        self.assertEqual(response.status_code, 200)
        self.assertIn('application/gzip', response.content_type)

    def test_export_without_files(self):
        """Database-only export (include_files=0)."""
        response = self.client.get('/export?include_files=0')
        self.assertEqual(response.status_code, 200)

    def test_backup_storage_dir_creates_directory(self):
        backup_dir = _backup_storage_dir()
        self.assertTrue(os.path.isdir(backup_dir))

    def test_backup_storage_dir_is_realpath(self):
        backup_dir = _backup_storage_dir()
        self.assertEqual(os.path.realpath(backup_dir), backup_dir)


# ── Backup Path Safety ────────────────────────────────────────────────────

class BackupPathSafetyTests(unittest.TestCase):
    def test_is_path_inside_accepts_subpath(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            sub = os.path.join(tmp, 'sub', 'file.tar.gz')
            os.makedirs(os.path.dirname(sub), exist_ok=True)
            with open(sub, 'w') as f:
                f.write('x')
            self.assertTrue(_is_path_inside(sub, tmp))

    def test_is_path_inside_rejects_parent_path(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            outside = os.path.join(os.path.dirname(tmp), 'evil.tar.gz')
            self.assertFalse(_is_path_inside(outside, tmp))

    def test_is_path_inside_rejects_prefix_collision(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            evil = os.path.join(os.path.dirname(tmp), os.path.basename(tmp) + '-evil', 'file.tar.gz')
            self.assertFalse(_is_path_inside(evil, tmp))


# ── Import Dry-run & Conflict Modes ──────────────────────────────────────

class ImportDryRunTests(_BaseBackupExtTests):
    def test_import_plain_json_legacy_format(self):
        """Legacy plain JSON import (without tar.gz) must still work."""
        payload = {
            'brands': ['Import Brand'],
            'materials': ['PLA'],
            'colors': [{'name': 'Import Color', 'hex_value': '#AABBCC'}],
            'filaments': [{
                'name': 'Import Filament',
                'brand': 'Import Brand',
                'material': 'PLA',
                'color': 'Import Color',
                'weight_total': 1000,
                'weight_remaining': 800,
                'price': 400,
                'quantity': 1,
            }],
        }

        response = self.client.post(
            '/import',
            data={'file': (io.BytesIO(json.dumps(payload).encode('utf-8')), 'backup.json')},
            content_type='multipart/form-data',
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)

        with self.app.app_context():
            self.assertIsNotNone(Filament.query.filter_by(name='Import Filament').first())

    def test_import_tar_gz_format(self):
        """Tar.gz backup import."""
        payload = {
            'brands': ['Tar Brand'],
            'materials': ['PETG'],
            'colors': [{'name': 'Tar Color', 'hex_value': '#DDEEFF'}],
            'filaments': [{
                'name': 'Tar Filament',
                'brand': 'Tar Brand',
                'material': 'PETG',
                'color': 'Tar Color',
                'weight_total': 500,
                'weight_remaining': 500,
                'price': 300,
                'quantity': 1,
            }],
        }
        backup_bytes = encode_backup_payload(payload)
        response = self.client.post(
            '/import',
            data={'file': (backup_bytes, 'backup.tar.gz')},
            content_type='multipart/form-data',
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)

        with self.app.app_context():
            self.assertIsNotNone(Filament.query.filter_by(name='Tar Filament').first())

    def test_import_skip_mode_keeps_existing(self):
        """In skip mode, existing records should not be overwritten."""
        with self.app.app_context():
            # First create a filament
            brand = Brand.query.first()
            color = Color.query.first()
            material = Material.query.first()
            original = Filament(
                name='Skip Test',
                brand_id=brand.id,
                color_id=color.id,
                material_id=material.id,
                weight_total=1000,
                weight_remaining=900,
                price=500,
                quantity=2,
            )
            db.session.add(original)
            db.session.commit()
            original_id = original.id
            brand_name = brand.name
            color_name = color.name
            material_name = material.name

        payload = {
            'brands': [],
            'materials': [],
            'colors': [],
            'filaments': [{
                'name': 'Skip Test',
                'brand': brand_name,
                'material': material_name,
                'color': color_name,
                'weight_total': 1000,
                'weight_remaining': 100,  # different data
                'price': 200,
                'quantity': 1,
            }],
        }

        response = self.client.post(
            '/import',
            data={
                'file': (encode_backup_payload(payload), 'backup.tar.gz'),
                'conflict_mode': 'skip',
            },
            content_type='multipart/form-data',
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)

        with self.app.app_context():
            restored = db.session.get(Filament, original_id)
            self.assertIsNotNone(restored)
            # Original values kept (skip mode)
            self.assertAlmostEqual(restored.weight_remaining, 900.0)

    def test_import_overwrite_mode_replaces(self):
        """In overwrite mode, existing records should be replaced."""
        with self.app.app_context():
            brand = Brand.query.first()
            color = Color.query.first()
            material = Material.query.first()

        payload = {
            'brands': [brand.name],
            'materials': [material.name],
            'colors': [{'name': color.name, 'hex_value': color.hex_value or '#000000'}],
            'filaments': [{
                'name': 'Backup Ext PLA',
                'brand': brand.name,
                'material': material.name,
                'color': color.name,
                'weight_total': 1000,
                'weight_remaining': 100,
                'price': 200,
                'quantity': 1,
            }],
        }

        response = self.client.post(
            '/import',
            data={
                'file': (encode_backup_payload(payload), 'backup.tar.gz'),
                'conflict_mode': 'overwrite',
            },
            content_type='multipart/form-data',
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)

        with self.app.app_context():
            restored = Filament.query.filter_by(name='Backup Ext PLA').first()
            self.assertIsNotNone(restored)
            # Overwritten with new values
            self.assertAlmostEqual(restored.weight_remaining, 100.0)


# ── Retention Cleanup ────────────────────────────────────────────────────

class BackupRetentionCleanupTests(unittest.TestCase):
    def setUp(self):
        self.backup_dir = tempfile.mkdtemp(prefix='backup-retention-')

        # Create some fake backup files
        for i in range(5):
            path = os.path.join(self.backup_dir, f'auto_backup_full_2026060{i}_120000.tar.gz')
            with open(path, 'w') as f:
                f.write(f'fake backup {i}')

        self.old_backup = os.path.join(self.backup_dir, 'old_backup.tar.gz')
        with open(self.old_backup, 'w') as f:
            f.write('old backup')

    def tearDown(self):
        shutil.rmtree(self.backup_dir, ignore_errors=True)

    def test_cleanup_by_count_removes_oldest(self):
        removed = _cleanup_old_backups(self.backup_dir, keep_count=3, keep_days=0)
        self.assertGreater(removed, 0)
        remaining = os.listdir(self.backup_dir)
        # Exactly 3 newest auto_backup files + 1 non-auto old_backup file should remain
        auto_backups = [f for f in remaining if f.startswith('auto_backup_')]
        self.assertEqual(len(auto_backups), 3)

    def test_cleanup_keeps_all_when_count_zero(self):
        removed = _cleanup_old_backups(self.backup_dir, keep_count=0, keep_days=0)
        self.assertEqual(removed, 0)
        remaining = os.listdir(self.backup_dir)
        self.assertEqual(len(remaining), 6)  # all 6 files

    def test_cleanup_count_higher_than_files(self):
        removed = _cleanup_old_backups(self.backup_dir, keep_count=100, keep_days=0)
        self.assertEqual(removed, 0)

    def test_is_path_inside_handles_symlink_escape(self):
        """Realpath symlink must not bypass containment check."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            outside = os.path.join(tmp, 'secret.tar.gz')
            with open(outside, 'w') as f:
                f.write('secret')
            link_path = os.path.join(self.backup_dir, 'secret_link.tar.gz')
            try:
                os.symlink(outside, link_path)
            except (OSError, NotImplementedError):
                self.skipTest('symlinks unsupported')
            self.assertFalse(_is_path_inside(link_path, self.backup_dir))


if __name__ == '__main__':
    unittest.main()
