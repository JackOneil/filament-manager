import io
import gzip
import json
import os
import shutil
import tarfile
import tempfile
import unittest

from app import create_app
from database import db
from models import (
    AuditLog, BambuPrintJob, Brand, Color, Filament, Material, MovementHistory,
    Project, ProjectFile, ProjectFilament, ProjectQuote, StoragePlacement, StorageShelf, User,
)


def unpack_backup_bytes(payload):
    try:
        with tarfile.open(fileobj=io.BytesIO(payload), mode='r:*') as archive:
            manifest = archive.extractfile('manifest.json')
            if manifest is None:
                raise AssertionError('Backup archive missing manifest.json')
            data = json.loads(manifest.read().decode('utf-8'))
            files = {}
            for member in archive.getmembers():
                if not member.isfile() or member.name == 'manifest.json':
                    continue
                extracted = archive.extractfile(member)
                if extracted is not None:
                    files[member.name] = extracted.read()
            return data, files
    except tarfile.TarError:
        pass

    if payload[:2] == b'\x1f\x8b':
        payload = gzip.decompress(payload)
    return json.loads(payload.decode('utf-8')), {}


def unpack_backup_response(response):
    return unpack_backup_bytes(response.data)


def decode_backup_response(response):
    data, _ = unpack_backup_response(response)
    return data


def encode_backup_payload(payload, files=None):
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


class ImportAtomicityTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix='filament-import-tests-')
        db_path = os.path.join(self.temp_dir, 'test.db')
        self.app = create_app({
            'TESTING': True,
            'SQLALCHEMY_DATABASE_URI': f'sqlite:///{db_path}',
            'PROJECT_UPLOAD_FOLDER': os.path.join(self.temp_dir, 'uploads'),
            'WTF_CSRF_ENABLED': False,
        })
        self.client = self.app.test_client()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_import_rolls_back_everything_when_later_stage_fails(self):
        payload = {
            'brands': ['Atomic Brand'],
            'materials': ['PLA'],
            'colors': [{'name': 'Atomic Color', 'hex_value': '#123456'}],
            'filaments': [{
                'name': 'Atomic Filament',
                'brand': 'Atomic Brand',
                'material': 'PLA',
                'color': 'Atomic Color',
                'weight_total': 1000,
                'weight_remaining': 1000,
                'price': 500,
                'quantity': 1,
            }],
            'bambu_jobs': [{
                'external_id': 'BROKEN_JOB',
                'printer_name': 'P1P',
                'printer_model': 'P1P',
                'device_id': 'DEV_BROKEN',
                'model_name': 'Broken import',
                'status': 'FINISH',
                'weight_grams': 10,
                'cost_time': 60,
                'started_at': 'not-a-date',
                'finished_at': None,
                'synced_at': None,
                'deducted': False,
                'filament_name': None,
                'project_name': None,
                'materials': [],
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
            self.assertIsNone(Brand.query.filter_by(name='Atomic Brand').first())
            self.assertIsNone(Filament.query.filter_by(name='Atomic Filament').first())

    def test_export_and_import_include_project_quotes(self):
        with self.app.app_context():
            project = Project(name='Quoted Project')
            db_path_brand = Brand.query.filter_by(name='Prusament').first()
            color = Color.query.first()
            material = Material.query.filter_by(name='PLA').first()
            filament = Filament(
                name='Quoted Filament',
                brand_id=db_path_brand.id,
                material_id=material.id,
                color_id=color.id,
                weight_total=1000,
                weight_remaining=900,
                price=500,
                quantity=1,
            )
            db.session.add_all([project, filament])
            db.session.flush()
            db.session.add(ProjectQuote(
                project_id=project.id,
                filament_id=filament.id,
                filament_name='Quoted Filament | Prusament PLA',
                weight=120,
                print_time=3.5,
                material_cost=60,
                electricity_cost=2,
                base_cost=62,
                margin_percent=30,
                margin_amount=18.6,
                final_price=80.6,
                currency='CZK',
            ))
            db.session.commit()

        export_response = self.client.get('/export')
        self.assertEqual(export_response.status_code, 200)
        self.assertEqual(export_response.headers.get('Content-Disposition'), 'attachment; filename=filament_backup.tar.gz')
        exported, exported_files = unpack_backup_response(export_response)
        self.assertEqual(exported['projects'][0]['quotes'][0]['final_price'], 80.6)

        with self.app.app_context():
            db.drop_all()
            db.create_all()

        import_response = self.client.post(
            '/import',
            data={'file': (encode_backup_payload(exported, exported_files), 'backup.tar.gz')},
            content_type='multipart/form-data',
            follow_redirects=False,
        )

        self.assertEqual(import_response.status_code, 302)

        with self.app.app_context():
            quote = ProjectQuote.query.first()
            self.assertIsNotNone(quote)
            self.assertEqual(quote.final_price, 80.6)

    def test_export_and_import_preserve_audit_logs(self):
        with self.app.app_context():
            admin = User(email='audit-admin@example.com', name='Audit Admin', password_hash='hash', role='admin')
            db.session.add(admin)
            db.session.flush()
            db.session.add(AuditLog(
                user_id=admin.id,
                user_email=admin.email,
                user_name=admin.name,
                session_id='session-1',
                ip_address='127.0.0.1',
                user_agent='UnitTest',
                method='POST',
                endpoint='settings',
                path='/settings',
                action='brand_add',
                object_type='Brand',
                object_id='1',
                before_data='{"object":null}',
                after_data='{"form":{"name":"Audit Brand"}}',
            ))
            db.session.commit()

        exported, exported_files = unpack_backup_response(self.client.get('/export'))
        self.assertEqual(exported['audit_logs'][0]['action'], 'brand_add')
        self.assertEqual(exported['audit_logs'][0]['user_email'], 'audit-admin@example.com')

        with self.app.app_context():
            db.drop_all()
            db.create_all()

        import_response = self.client.post(
            '/import',
            data={'file': (encode_backup_payload(exported, exported_files), 'backup.tar.gz')},
            content_type='multipart/form-data',
            follow_redirects=False,
        )

        self.assertEqual(import_response.status_code, 302)

        with self.app.app_context():
            audit = AuditLog.query.first()
            self.assertIsNotNone(audit)
            self.assertEqual(audit.action, 'brand_add')
            self.assertEqual(audit.user_email, 'audit-admin@example.com')
            self.assertEqual(audit.after_data, '{"form":{"name":"Audit Brand"}}')

    def test_export_and_import_preserve_project_owner_name(self):
        with self.app.app_context():
            user = User(email='owner@example.com', name='Owner', password_hash='hash', role='user')
            db.session.add(user)
            db.session.flush()
            db.session.add_all([
                Project(name='External owner project', owner_name='Client Contact'),
                Project(name='User owner project', owner_user_id=user.id),
            ])
            db.session.commit()

        exported, exported_files = unpack_backup_response(self.client.get('/export'))
        external = next((p for p in exported['projects'] if p['name'] == 'External owner project'), None)
        user_owned = next((p for p in exported['projects'] if p['name'] == 'User owner project'), None)
        self.assertIsNotNone(external)
        self.assertEqual(external['owner_name'], 'Client Contact')
        self.assertIsNotNone(user_owned)
        self.assertIsNone(user_owned['owner_name'])

        with self.app.app_context():
            db.drop_all()
            db.create_all()

        response = self.client.post(
            '/import',
            data={'file': (encode_backup_payload(exported, exported_files), 'backup.tar.gz')},
            content_type='multipart/form-data',
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)

        with self.app.app_context():
            external_restored = Project.query.filter_by(name='External owner project').first()
            user_restored = Project.query.filter_by(name='User owner project').first()
            self.assertIsNotNone(external_restored)
            self.assertEqual(external_restored.owner_name, 'Client Contact')
            self.assertIsNone(external_restored.owner_user_id)
            self.assertIsNotNone(user_restored)
            self.assertEqual(user_restored.owner_name, None)
            self.assertIsNotNone(user_restored.owner_user_id)

    def test_export_and_import_preserve_new_filament_fields_and_movement_links(self):
        with self.app.app_context():
            brand = Brand.query.filter_by(name='Prusament').first()
            color = Color.query.first()
            material = Material.query.filter_by(name='PLA').first()
            project = Project(name='Backup Project', tag_text='customer, rush')
            filament = Filament(
                name='Backup Filament',
                brand_id=brand.id,
                material_id=material.id,
                color_id=color.id,
                weight_total=1000,
                weight_remaining=640,
                price=720,
                quantity=1,
                min_stock_grams=250,
                max_stock_grams=2000,
                tag_text='matte, proto',
                quality_stringing='low',
                quality_adhesion='great',
                quality_drying='dry box',
                quality_profile='0.20 structural',
                quality_notes='stable',
                recommended_nozzle_temp=220,
                recommended_bed_temp=60,
                reorder_alert_snoozed=True,
            )
            db.session.add_all([project, filament])
            db.session.flush()
            sample_path = os.path.join(self.temp_dir, 'sample.3mf')
            with open(sample_path, 'wb') as handle:
                handle.write(b'3mf-backup-content')
            db.session.add(ProjectFile(project_id=project.id, filename='sample.3mf', filepath=sample_path))
            job = BambuPrintJob(external_id='BKP-1', model_name='Backup job', filament_id=filament.id, project_id=project.id)
            db.session.add(job)
            db.session.flush()
            db.session.add(MovementHistory(
                filament_id=filament.id,
                project_id=project.id,
                bambu_job_id=job.id,
                filament_name='Backup Filament | Prusament PLA',
                action_type='bambu_print',
                weight=42,
                cost=30,
                currency='CZK',
                note='Linked movement',
            ))
            db.session.commit()

        exported, exported_files = unpack_backup_response(self.client.get('/export'))
        self.assertEqual(exported['projects'][0]['files'][0]['content_b64'], None)
        archive_path = exported['projects'][0]['files'][0]['archive_path']
        self.assertIn(archive_path, exported_files)
        self.assertEqual(exported_files[archive_path], b'3mf-backup-content')

        with self.app.app_context():
            db.drop_all()
            db.create_all()

        response = self.client.post(
            '/import',
            data={'file': (encode_backup_payload(exported, exported_files), 'backup.tar.gz')},
            content_type='multipart/form-data',
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)

        with self.app.app_context():
            filament = Filament.query.filter_by(name='Backup Filament').first()
            self.assertIsNotNone(filament)
            self.assertEqual(filament.min_stock_grams, 250)
            self.assertEqual(filament.tag_text, 'matte, proto')
            self.assertEqual(filament.quality_profile, '0.20 structural')
            self.assertEqual(filament.recommended_nozzle_temp, 220)
            self.assertTrue(filament.reorder_alert_snoozed)

            movement = MovementHistory.query.filter_by(note='Linked movement').first()
            self.assertIsNotNone(movement)
            self.assertIsNotNone(movement.project_id)
            self.assertIsNotNone(movement.bambu_job_id)
            restored_file = ProjectFile.query.filter_by(filename='sample.3mf').first()
            self.assertIsNotNone(restored_file)
            self.assertTrue(os.path.exists(restored_file.filepath))
            with open(restored_file.filepath, 'rb') as handle:
                self.assertEqual(handle.read(), b'3mf-backup-content')

    def test_export_and_import_preserve_storage_layout(self):
        with self.app.app_context():
            brand = Brand.query.filter_by(name='Prusament').first()
            color = Color.query.first()
            material = Material.query.filter_by(name='PLA').first()
            filament = Filament(
                name='Storage Filament',
                brand_id=brand.id,
                material_id=material.id,
                color_id=color.id,
                weight_total=1000,
                weight_remaining=480,
                price=500,
                quantity=1,
            )
            shelf = StorageShelf(name='Rack A', columns=3, slots_count=9, sort_order=1)
            db.session.add_all([filament, shelf])
            db.session.flush()
            db.session.add(StoragePlacement(
                shelf_id=shelf.id,
                filament_id=filament.id,
                slot_index=4,
                orientation='flat',
            ))
            db.session.commit()

        exported, exported_files = unpack_backup_response(self.client.get('/export'))
        self.assertEqual(exported['storage_shelves'][0]['name'], 'Rack A')
        self.assertEqual(exported['storage_placements'][0]['slot_index'], 4)

        with self.app.app_context():
            db.drop_all()
            db.create_all()

        response = self.client.post(
            '/import',
            data={'file': (encode_backup_payload(exported, exported_files), 'backup.tar.gz')},
            content_type='multipart/form-data',
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)

        with self.app.app_context():
            shelf = StorageShelf.query.filter_by(name='Rack A').first()
            self.assertIsNotNone(shelf)
            placement = StoragePlacement.query.filter_by(slot_index=4).first()
            self.assertIsNotNone(placement)
            self.assertEqual(placement.orientation, 'flat')
            self.assertEqual(placement.filament.name, 'Storage Filament')

    def test_export_and_import_preserve_duplicate_name_filament_references(self):
        with self.app.app_context():
            brand_a = Brand.query.filter_by(name='Prusament').first()
            brand_b = Brand(name='Alt Brand')
            color_a = Color.query.first()
            color_b = Color(name='Signal Orange', hex_value='#ff6600')
            material = Material.query.filter_by(name='PLA').first()
            project = Project(name='Duplicate Names Project')
            db.session.add_all([brand_b, color_b, project])
            db.session.flush()

            primary = Filament(
                name='Shared Name',
                brand_id=brand_a.id,
                material_id=material.id,
                color_id=color_a.id,
                weight_total=1000,
                weight_remaining=700,
                price=500,
                quantity=1,
            )
            secondary = Filament(
                name='Shared Name',
                brand_id=brand_b.id,
                material_id=material.id,
                color_id=color_b.id,
                weight_total=850,
                weight_remaining=500,
                price=420,
                quantity=1,
            )
            db.session.add_all([primary, secondary])
            db.session.flush()

            db.session.add(ProjectFilament(project_id=project.id, filament_id=secondary.id, estimated_weight=55, is_used=True))
            job = BambuPrintJob(
                external_id='DUPL-1',
                model_name='Dual choice',
                filament_id=secondary.id,
                project_id=project.id,
            )
            shelf = StorageShelf(name='Duplicate Shelf', columns=2, slots_count=2, sort_order=1)
            db.session.add_all([job, shelf])
            db.session.flush()
            db.session.add(StoragePlacement(shelf_id=shelf.id, filament_id=secondary.id, slot_index=1, orientation='standing'))
            db.session.add(MovementHistory(
                filament_id=secondary.id,
                project_id=project.id,
                bambu_job_id=job.id,
                filament_name='Shared Name | Alt Brand PLA',
                action_type='remove',
                weight=55,
                cost=27,
                currency='CZK',
                note='duplicate-ref',
            ))
            db.session.commit()

        exported, exported_files = unpack_backup_response(self.client.get('/export'))

        with self.app.app_context():
            db.drop_all()
            db.create_all()

        response = self.client.post(
            '/import',
            data={'file': (encode_backup_payload(exported, exported_files), 'backup.tar.gz')},
            content_type='multipart/form-data',
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)

        with self.app.app_context():
            brand_b = Brand.query.filter_by(name='Alt Brand').first()
            color_b = Color.query.filter_by(name='Signal Orange').first()
            self.assertIsNotNone(brand_b)
            self.assertIsNotNone(color_b)
            restored_filament = Filament.query.filter_by(
                name='Shared Name',
                brand_id=brand_b.id,
                color_id=color_b.id,
            ).first()
            self.assertIsNotNone(restored_filament)
            self.assertEqual(ProjectFilament.query.first().filament_id, restored_filament.id)
            self.assertEqual(BambuPrintJob.query.filter_by(external_id='DUPL-1').first().filament_id, restored_filament.id)
            self.assertEqual(StoragePlacement.query.filter_by(slot_index=1).first().filament_id, restored_filament.id)
            self.assertEqual(MovementHistory.query.filter_by(note='duplicate-ref').first().filament_id, restored_filament.id)

    def test_import_accepts_legacy_plain_json_backup(self):
        payload = {
            'brands': ['Legacy Brand'],
            'materials': ['PLA'],
            'colors': [{'name': 'Legacy Color', 'hex_value': '#112233'}],
            'filaments': [{
                'name': 'Legacy Filament',
                'brand': 'Legacy Brand',
                'material': 'PLA',
                'color': 'Legacy Color',
                'weight_total': 1000,
                'weight_remaining': 850,
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
            self.assertIsNotNone(Filament.query.filter_by(name='Legacy Filament').first())


class SettingsTagManagementTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix='filament-settings-tags-')
        db_path = os.path.join(self.temp_dir, 'test.db')
        self.app = create_app({
            'TESTING': True,
            'SQLALCHEMY_DATABASE_URI': f'sqlite:///{db_path}',
            'PROJECT_UPLOAD_FOLDER': os.path.join(self.temp_dir, 'uploads'),
            'WTF_CSRF_ENABLED': False,
        })
        self.client = self.app.test_client()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_settings_show_clickable_filament_tag_filters(self):
        with self.app.app_context():
            brand = Brand.query.filter_by(name='Prusament').first()
            color = Color.query.first()
            material = Material.query.filter_by(name='PLA').first()
            db.session.add(Filament(
                name='Clickable Tag Filament',
                brand_id=brand.id,
                material_id=material.id,
                color_id=color.id,
                weight_total=1000,
                weight_remaining=800,
                price=500,
                quantity=1,
                tag_text='matte, prototype',
            ))
            db.session.commit()

        response = self.client.get('/settings')

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'/filaments?tag=matte', response.data)

    def test_delete_filament_tag_removes_it_from_all_filaments(self):
        with self.app.app_context():
            brand = Brand.query.filter_by(name='Prusament').first()
            color = Color.query.first()
            material = Material.query.filter_by(name='PLA').first()
            db.session.add_all([
                Filament(
                    name='Tag Delete A',
                    brand_id=brand.id,
                    material_id=material.id,
                    color_id=color.id,
                    weight_total=1000,
                    weight_remaining=800,
                    price=500,
                    quantity=1,
                    tag_text='matte, prototype',
                ),
                Filament(
                    name='Tag Delete B',
                    brand_id=brand.id,
                    material_id=material.id,
                    color_id=color.id,
                    weight_total=1000,
                    weight_remaining=700,
                    price=550,
                    quantity=1,
                    tag_text='Matte, engineering',
                ),
            ])
            db.session.commit()

        response = self.client.post('/settings', data={
            'action': 'delete_filament_tag',
            'tag': 'matte',
        }, follow_redirects=False)

        self.assertEqual(response.status_code, 302)

        with self.app.app_context():
            tags_a = Filament.query.filter_by(name='Tag Delete A').first().tag_text
            tags_b = Filament.query.filter_by(name='Tag Delete B').first().tag_text
            self.assertEqual(tags_a, 'prototype')
            self.assertEqual(tags_b, 'engineering')

    def test_delete_project_tag_removes_it_from_all_projects(self):
        with self.app.app_context():
            db.session.add_all([
                Project(name='Project A', tag_text='rush, client'),
                Project(name='Project B', tag_text='Rush, internal'),
            ])
            db.session.commit()

        response = self.client.post('/settings', data={
            'action': 'delete_project_tag',
            'tag': 'rush',
        }, follow_redirects=False)

        self.assertEqual(response.status_code, 302)

        with self.app.app_context():
            project_a = Project.query.filter_by(name='Project A').first()
            project_b = Project.query.filter_by(name='Project B').first()
            self.assertEqual(project_a.tag_text, 'client')
            self.assertEqual(project_b.tag_text, 'internal')


if __name__ == '__main__':
    unittest.main()
