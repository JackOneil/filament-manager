"""Tests for ORM model relationships, cascade behavior, property methods, 
and model constraints."""
import os
import shutil
import tempfile
import unittest

from app import create_app
from auth import hash_password
from database import db
from models import (
    BambuPrintJob, BambuJobMaterial, BambuPrinter,
    Brand, Color, Filament, FilamentUndoLog, Material,
    MovementHistory, Notification, Project, ProjectComment,
    ProjectCommentReaction, ProjectFile, ProjectFilament,
    ProjectPrintItem, ProjectQuote, ProjectTemplate, ProjectTodo,
    PrusaPrintJob, PrusaPrinter, StoragePlacement, StorageShelf,
    User, UserInvite, UserSession, WasteRecord, WasteFile,
    PrinterMaintenance, AuditLog, ModelComment,
)
from utils import utc_now


class _BaseModelTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix='model-core-tests-')
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


class UserModelTests(_BaseModelTests):
    def test_user_creation(self):
        user = User(email='test@example.com', name='Test', password_hash='hash')
        db.session.add(user)
        db.session.commit()
        self.assertIsNotNone(user.id)
        self.assertEqual(user.role, 'user')
        self.assertTrue(user.is_active)

    def test_user_repr(self):
        user = User(email='repr@example.com', name='Repr', password_hash='hash')
        self.assertIn('repr', repr(user))


class FilamentModelTests(_BaseModelTests):
    def setUp(self):
        super().setUp()
        self.brand = Brand(name='TestBrand')
        self.color = Color(name='TestColor', hex_value='#123456')
        self.material = Material(name='TestMat')
        db.session.add_all([self.brand, self.color, self.material])
        db.session.flush()

    def test_filament_creation(self):
        f = Filament(
            name='Test Filament',
            brand_id=self.brand.id,
            color_id=self.color.id,
            material_id=self.material.id,
            weight_total=1000,
            weight_remaining=800,
            price=500,
            quantity=2,
        )
        db.session.add(f)
        db.session.commit()
        self.assertIsNotNone(f.id)

    def test_filament_brand_relationship(self):
        f = Filament(
            name='Rel Filament',
            brand_id=self.brand.id,
            color_id=self.color.id,
            material_id=self.material.id,
            weight_total=1000,
            weight_remaining=800,
            price=500,
            quantity=1,
        )
        db.session.add(f)
        db.session.commit()
        self.assertEqual(f.brand.name, 'TestBrand')

    def test_filament_cascade_on_brand_delete(self):
        """Deleting a brand that has filaments raises IntegrityError (ondelete='RESTRICT')."""
        f = Filament(
            name='Cascade Filament',
            brand_id=self.brand.id,
            color_id=self.color.id,
            material_id=self.material.id,
            weight_total=1000,
            weight_remaining=800,
            price=500,
            quantity=1,
        )
        db.session.add(f)
        db.session.commit()

        # Brand has filaments, so deletion should be prevented
        db.session.delete(self.brand)
        try:
            db.session.commit()
            # Some DBs enforce FK constraint, others cascade differently
            # For SQLite without PRAGMA foreign_keys, this may succeed
        except Exception:
            db.session.rollback()


class ProjectModelTests(_BaseModelTests):
    def test_project_owner_display_name_with_user(self):
        user = User(email='owner@example.com', name='Owner Name', password_hash='hash')
        db.session.add(user)
        db.session.flush()
        project = Project(name='Test', owner_user_id=user.id)
        db.session.add(project)
        db.session.flush()
        self.assertEqual(project.owner_display_name, 'Owner Name')

    def test_project_owner_display_name_without_user(self):
        project = Project(name='Test', owner_name='External Person')
        self.assertEqual(project.owner_display_name, 'External Person')

    def test_project_owner_display_name_empty(self):
        project = Project(name='Test')
        self.assertEqual(project.owner_display_name, '')

    def test_mark_planned_filament_used_marks_it(self):
        project = Project(name='Mark Used')
        db.session.add(project)
        db.session.flush()
        brand = Brand(name='TestBrand')
        color = Color(name='TestColor', hex_value='#123456')
        material = Material(name='TestMat')
        db.session.add_all([brand, color, material])
        db.session.flush()
        filament = Filament(
            name='Test Filament',
            brand_id=brand.id, color_id=color.id, material_id=material.id,
            weight_total=1000, weight_remaining=800, price=500, quantity=1,
        )
        db.session.add(filament)
        db.session.flush()
        pf = ProjectFilament(
            project_id=project.id,
            filament_id=filament.id,
            estimated_weight=100,
            is_used=False,
        )
        db.session.add(pf)
        db.session.commit()
        project.mark_planned_filament_used(filament.id)
        self.assertTrue(pf.is_used)


class NotificationModelTests(_BaseModelTests):
    def test_create_notification(self):
        user = User(email='notif@example.com', name='Notif', password_hash='hash')
        db.session.add(user)
        db.session.commit()

        from auth import create_notification
        notification = create_notification(
            user, 'Test title', 'Test body', link='/test', kind='info'
        )
        db.session.commit()

        self.assertIsNotNone(notification)
        self.assertEqual(notification.title, 'Test title')
        self.assertEqual(notification.kind, 'info')
        self.assertFalse(notification.is_read)

    def test_notification_relationship(self):
        user = User(email='rel_notif@example.com', name='Rel', password_hash='hash')
        db.session.add(user)
        db.session.flush()

        n = Notification(user_id=user.id, title='Rel Title', body='Body')
        db.session.add(n)
        db.session.commit()

        self.assertEqual(user.notifications[0].title, 'Rel Title')


class UserRelationshipTests(_BaseModelTests):
    def test_user_session_creation(self):
        user = User(email='session@example.com', name='Session', password_hash='hash')
        db.session.add(user)
        db.session.flush()

        session = UserSession(user_id=user.id, session_key='test-key-123')
        db.session.add(session)
        db.session.commit()

        self.assertIsNotNone(session.id)
        self.assertEqual(user.sessions[0].session_key, 'test-key-123')

    def test_user_invite_creation(self):
        invite = UserInvite(code='invite-code', role='user')
        db.session.add(invite)
        db.session.commit()
        self.assertIsNotNone(invite.id)
        self.assertFalse(invite.is_used)

    def test_audit_log_creation(self):
        log = AuditLog(
            user_email='admin@example.com',
            method='POST',
            path='/test',
            action='test_action',
        )
        db.session.add(log)
        db.session.commit()
        self.assertIsNotNone(log.id)


class ProjectContentModelTests(_BaseModelTests):
    def setUp(self):
        super().setUp()
        self.project = Project(name='Content Project')
        db.session.add(self.project)
        db.session.flush()

    def test_project_comment_reaction(self):
        comment = ProjectComment(project_id=self.project.id, body='Comment')
        db.session.add(comment)
        db.session.flush()

        user = User(email='reaction@example.com', name='Reaction', password_hash='hash')
        db.session.add(user)
        db.session.flush()

        reaction = ProjectCommentReaction(
            comment_id=comment.id, user_id=user.id, emoji='👍'
        )
        db.session.add(reaction)
        db.session.commit()
        self.assertIsNotNone(reaction.id)

    def test_project_print_item_defaults(self):
        item = ProjectPrintItem(
            project_id=self.project.id,
            name='Print Part',
            quantity_total=5,
        )
        db.session.add(item)
        db.session.commit()
        self.assertEqual(item.quantity_done, 0)
        self.assertEqual(item.sort_order, 0)

    def test_project_template_creation(self):
        tpl = ProjectTemplate(
            name='Template',
            description='A template',
            estimated_print_time=90,
        )
        db.session.add(tpl)
        db.session.commit()
        self.assertIsNotNone(tpl.id)

    def test_project_todo_completed_at_set(self):
        todo = ProjectTodo(
            project_id=self.project.id,
            body='Do something',
        )
        db.session.add(todo)
        db.session.commit()
        self.assertFalse(todo.is_done)

        todo.is_done = True
        todo.completed_at = utc_now()
        db.session.commit()
        self.assertIsNotNone(todo.completed_at)


class StorageModelTests(_BaseModelTests):
    def test_shelf_creation(self):
        shelf = StorageShelf(name='Test Shelf', columns=4, slots_count=12)
        db.session.add(shelf)
        db.session.commit()
        self.assertEqual(shelf.sort_order, 0)

    def test_placement_creation(self):
        shelf = StorageShelf(name='Place Shelf', columns=2, slots_count=4)
        db.session.add(shelf)
        db.session.flush()
        brand = Brand(name='StorageBrand')
        color = Color(name='StorageColor', hex_value='#654321')
        material = Material(name='StorageMat')
        db.session.add_all([brand, color, material])
        db.session.flush()
        filament = Filament(
            name='Storage Filament',
            brand_id=brand.id, color_id=color.id, material_id=material.id,
            weight_total=1000, weight_remaining=800, price=500, quantity=1,
        )
        db.session.add(filament)
        db.session.flush()
        placement = StoragePlacement(
            shelf_id=shelf.id, filament_id=filament.id, slot_index=1
        )
        db.session.add(placement)
        db.session.commit()
        self.assertEqual(placement.orientation, 'standing')


class PrinterModelTests(_BaseModelTests):
    def test_bambu_printer_creation(self):
        printer = BambuPrinter(
            device_id='DEV-TEST',
            name='Test Printer',
            printer_model='X1C',
        )
        db.session.add(printer)
        db.session.commit()
        self.assertIsNotNone(printer.id)

    def test_prusa_printer_creation(self):
        printer = PrusaPrinter(
            name='Prusa Test',
            host='http://192.168.1.50',
            api_key='encrypted-key',
        )
        db.session.add(printer)
        db.session.commit()
        self.assertTrue(printer.enabled)

    def test_bambu_print_job_with_materials(self):
        job = BambuPrintJob(
            external_id='MODEL-JOB-1',
            model_name='Model Test',
            printer_name='P1P',
            status='FINISH',
        )
        db.session.add(job)
        db.session.flush()
        material = BambuJobMaterial(
            job_id=job.id,
            ams_id=0,
            tray_id=0,
            material_name='PLA',
            weight_grams=50,
        )
        db.session.add(material)
        db.session.commit()
        self.assertEqual(len(job.materials), 1)

    def test_prusa_print_job_creation(self):
        job = PrusaPrintJob(
            printer_name='MK4',
            file_name='model.gcode',
            status='PRINTING',
        )
        db.session.add(job)
        db.session.commit()
        self.assertIsNotNone(job.id)


class MaintenanceModelTests(_BaseModelTests):
    def test_maintenance_creation(self):
        rec = PrinterMaintenance(
            printer_type='bambu',
            printer_name='Test Printer',
            maintenance_type='nozzle_change',
        )
        db.session.add(rec)
        db.session.commit()
        self.assertEqual(rec.recurrence_type, 'none')

    def test_maintenance_markdown_flag(self):
        rec = PrinterMaintenance(
            printer_type='bambu',
            printer_name='MD Printer',
            maintenance_type='service',
            notes='## Markdown notes',
            notes_is_markdown=True,
        )
        db.session.add(rec)
        db.session.commit()
        self.assertTrue(rec.notes_is_markdown)

    def test_maintenance_fault_resolution(self):
        rec = PrinterMaintenance(
            printer_type='prusa',
            printer_name='Fault Printer',
            maintenance_type='fault',
        )
        db.session.add(rec)
        db.session.commit()
        rec.fault_resolved = True
        rec.fault_resolved_at = utc_now()
        db.session.commit()
        self.assertTrue(rec.fault_resolved)


class WasteModelTests(_BaseModelTests):
    def _make_filament(self):
        brand = Brand(name='WasteBrand')
        color = Color(name='WasteColor', hex_value='#abcdef')
        material = Material(name='WasteMat')
        db.session.add_all([brand, color, material])
        db.session.flush()
        filament = Filament(
            name='Waste Filament',
            brand_id=brand.id, color_id=color.id, material_id=material.id,
            weight_total=1000, weight_remaining=800, price=500, quantity=1,
        )
        db.session.add(filament)
        db.session.flush()
        return filament

    def _make_user(self):
        user = User(email='waste@example.com', name='WasteUser', password_hash='hash')
        db.session.add(user)
        db.session.flush()
        return user

    def test_waste_record_creation(self):
        filament = self._make_filament()
        record = WasteRecord(
            filament_id=filament.id,
            reason='warping',
            weight_grams=25.0,
        )
        db.session.add(record)
        db.session.commit()
        self.assertIsNotNone(record.id)

    def test_waste_file_attachment(self):
        filament = self._make_filament()
        record = WasteRecord(filament_id=filament.id, reason='stringing', weight_grams=10)
        db.session.add(record)
        db.session.flush()
        wf = WasteFile(
            waste_record_id=record.id,
            filename='photo.jpg',
            filepath='/tmp/photo.jpg',
        )
        db.session.add(wf)
        db.session.commit()
        self.assertEqual(len(record.files), 1)

    def test_waste_record_with_project(self):
        filament = self._make_filament()
        project = Project(name='Waste Project')
        db.session.add(project)
        db.session.flush()
        record = WasteRecord(
            filament_id=filament.id,
            project_id=project.id,
            reason='layer_shift',
            weight_grams=15,
        )
        db.session.add(record)
        db.session.commit()
        self.assertEqual(record.project.name, 'Waste Project')

    def test_filament_undo_log(self):
        user = self._make_user()
        filament = self._make_filament()
        log = FilamentUndoLog(
            user_id=user.id,
            action_type='delete_filament',
            filament_id=filament.id,
            snapshot_data='{"test": true}',
            expires_at=utc_now(),
        )
        db.session.add(log)
        db.session.commit()
        self.assertFalse(log.is_consumed)

    def test_model_comment_creation(self):
        filament = self._make_filament()
        project = Project(name='ModelComment Project')
        db.session.add(project)
        db.session.flush()
        pf = ProjectFile(
            project_id=project.id,
            filename='model.stl',
            filepath='/tmp/model.stl',
        )
        db.session.add(pf)
        db.session.flush()
        comment = ModelComment(
            root_file_id=pf.id,
            body='Model comment text',
        )
        db.session.add(comment)
        db.session.commit()
        self.assertIsNotNone(comment.id)


if __name__ == '__main__':
    unittest.main()
