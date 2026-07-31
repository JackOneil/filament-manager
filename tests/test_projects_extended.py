"""Extended tests for project routes — status workflow, clone, templates, share tokens,
link management, filament planning, print items, and comment reactions."""
import io
import json
import math
import os
import secrets
import shutil
import tempfile
import unittest
from unittest.mock import patch

from app import create_app
from auth import hash_password
from database import db
from models import (
    AppSetting, Brand, Color, Filament, Material, Project,
    ProjectComment, ProjectCommentReaction, ProjectFile, ProjectFilament,
    ProjectLink, ProjectPrintItem, ProjectTemplate, ProjectTodo, User,
)
from utils import utc_now


class _BaseProjectTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix='proj-ext-tests-')
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
                email='admin@example.com',
                name='Admin',
                password_hash=hash_password('password123'),
                role='admin',
            )
            owner = User(
                email='owner@example.com',
                name='Owner',
                password_hash=hash_password('password123'),
                role='user',
            )
            brand = Brand.query.first()
            color = Color.query.first()
            material = Material.query.first()

            filament = Filament(
                name='Proj PLA',
                brand_id=brand.id,
                color_id=color.id,
                material_id=material.id,
                weight_total=1000,
                weight_remaining=800,
                price=500,
                quantity=2,
            )
            project = Project(
                name='Main Project',
                description='Test description',
                client_name='Client A',
                client_email='client@example.com',
                client_phone='+420123456789',
                status='PENDING_APPROVAL',
                priority='high',
                tag_text='rush, prototype',
                estimated_print_time=120,
                owner_user_id=owner.id,
                created_by_user_id=admin.id,
            )
            db.session.add_all([admin, owner, filament, project])
            db.session.commit()

            self.admin_id = admin.id
            self.owner_id = owner.id
            self.project_id = project.id
            self.filament_id = filament.id

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def login_admin(self):
        self.client.post('/logout', follow_redirects=True)
        return self.client.post(
            '/login',
            data={'email': 'admin@example.com', 'password': 'password123'},
            follow_redirects=True,
        )

    def login_owner(self):
        self.client.post('/logout', follow_redirects=True)
        return self.client.post(
            '/login',
            data={'email': 'owner@example.com', 'password': 'password123'},
            follow_redirects=True,
        )


# ── Project Status Workflow ───────────────────────────────────────────────

class ProjectStatusWorkflowTests(_BaseProjectTests):
    def test_advance_status_from_pending_to_approved(self):
        self.login_admin()
        self.client.post(f'/projects/{self.project_id}/advance_status',
                          follow_redirects=False)

        with self.app.app_context():
            project = db.session.get(Project, self.project_id)
            self.assertEqual(project.status, 'APPROVED')

    def test_advance_status_full_flow(self):
        self.login_admin()
        flow = ['NEW', 'PENDING_APPROVAL', 'APPROVED', 'PRINTING', 'DONE']
        for expected_status in flow:
            # Set status directly via DB
            with self.app.app_context():
                project = db.session.get(Project, self.project_id)
                project.status = expected_status
                db.session.commit()
            # Advance to the next status via HTTP endpoint
            response = self.client.post(f'/projects/{self.project_id}/advance_status',
                                         follow_redirects=False)
            self.assertIn(response.status_code, (302, 200))
        # After full flow, status should be DONE (cannot advance further)
        with self.app.app_context():
            project = db.session.get(Project, self.project_id)
            self.assertEqual(project.status, 'DONE')

    def test_set_status_directly(self):
        self.login_admin()
        self.client.post(f'/projects/{self.project_id}/status', data={
            'status': 'APPROVED',
        }, follow_redirects=False)

        with self.app.app_context():
            project = db.session.get(Project, self.project_id)
            self.assertEqual(project.status, 'APPROVED')

    def test_set_status_rejected(self):
        self.login_admin()
        self.client.post(f'/projects/{self.project_id}/status', data={
            'status': 'REJECTED',
        }, follow_redirects=False)

        with self.app.app_context():
            project = db.session.get(Project, self.project_id)
            self.assertEqual(project.status, 'REJECTED')

    def test_set_invalid_status_redirects(self):
        self.login_admin()
        response = self.client.post(f'/projects/{self.project_id}/status', data={
            'status': 'INVALID_STATUS',
        }, follow_redirects=False)

        # Should still be on the detail page with error flash
        self.assertEqual(response.status_code, 302)


# ── Project Clone ─────────────────────────────────────────────────────────

class ProjectCloneTests(_BaseProjectTests):
    def test_clone_project_creates_copy(self):
        self.login_admin()

        with self.app.app_context():
            pf = ProjectFilament(
                project_id=self.project_id,
                filament_id=self.filament_id,
                estimated_weight=50.0,
            )
            db.session.add(pf)
            db.session.commit()

        self.client.post(f'/projects/{self.project_id}/clone',
                          follow_redirects=False)

        with self.app.app_context():
            clones = Project.query.filter(Project.name.like('Main Project%')).all()
            self.assertGreater(len(clones), 1)  # original + clone

    def test_clone_preserves_description_and_tags(self):
        self.login_admin()
        self.client.post(f'/projects/{self.project_id}/clone',
                          follow_redirects=False)

        with self.app.app_context():
            clone = Project.query.filter(Project.name != 'Main Project',
                                          Project.name.like('Main Project%')).first()
            self.assertIsNotNone(clone)
            self.assertEqual(clone.description, 'Test description')
            self.assertIn('rush', clone.tag_text)

    def test_clone_resets_print_items(self):
        self.login_admin()
        with self.app.app_context():
            pi = ProjectPrintItem(
                project_id=self.project_id,
                name='Test Part',
                quantity_total=5,
                quantity_done=3,
            )
            db.session.add(pi)
            db.session.commit()

        self.client.post(f'/projects/{self.project_id}/clone',
                          follow_redirects=False)

        with self.app.app_context():
            clone = Project.query.filter(Project.name != 'Main Project',
                                          Project.name.like('Main Project%')).first()
            self.assertIsNotNone(clone)
            self.assertEqual(len(clone.print_items), 1)
            self.assertEqual(clone.print_items[0].quantity_done, 0)

    def test_clone_does_not_copy_share_token(self):
        self.login_admin()
        with self.app.app_context():
            project = db.session.get(Project, self.project_id)
            project.share_token = 'original-share-token'
            db.session.commit()

        self.client.post(f'/projects/{self.project_id}/clone',
                          follow_redirects=False)

        with self.app.app_context():
            clone = Project.query.filter(Project.name != 'Main Project',
                                          Project.name.like('Main Project%')).first()
            self.assertIsNotNone(clone)
            self.assertIsNone(clone.share_token)


# ── Project Share Tokens ─────────────────────────────────────────────────

class ProjectShareTests(_BaseProjectTests):
    def test_generate_share_token(self):
        self.login_admin()
        response = self.client.post(
            f'/projects/{self.project_id}/generate_share_token',
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)

        with self.app.app_context():
            project = db.session.get(Project, self.project_id)
            self.assertIsNotNone(project.share_token)
            self.assertEqual(len(project.share_token), 43)  # token_urlsafe(32) -> 43 chars

    def test_revoke_share_token(self):
        self.login_admin()
        with self.app.app_context():
            project = db.session.get(Project, self.project_id)
            project.share_token = 'existing-token'
            db.session.commit()

        self.client.post(f'/projects/{self.project_id}/revoke_share_token',
                          follow_redirects=False)

        with self.app.app_context():
            project = db.session.get(Project, self.project_id)
            self.assertIsNone(project.share_token)

    def test_share_public_view(self):
        token = secrets.token_urlsafe(32)
        with self.app.app_context():
            project = db.session.get(Project, self.project_id)
            project.share_token = token
            db.session.commit()

        response = self.client.get(f'/projects/share/{token}')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Main Project', response.data)

    def test_share_invalid_token_returns_404(self):
        response = self.client.get('/projects/share/invalid-token')
        self.assertEqual(response.status_code, 404)


# ── Project Templates ────────────────────────────────────────────────────

class ProjectTemplateTests(_BaseProjectTests):
    def test_save_template(self):
        self.login_admin()
        response = self.client.post(
            f'/projects/{self.project_id}/save_as_template',
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)

        with self.app.app_context():
            template = ProjectTemplate.query.first()
            self.assertIsNotNone(template)
            self.assertEqual(template.name, 'Main Project')
            self.assertEqual(template.description, 'Test description')

    def test_templates_index_renders(self):
        self.login_admin()
        with self.app.app_context():
            db.session.add(ProjectTemplate(
                name='Template 1',
                description='A reusable template',
                created_by_user_id=self.admin_id,
            ))
            db.session.commit()

        response = self.client.get('/projects/templates')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Template 1', response.data)

    def test_delete_template(self):
        self.login_admin()
        with self.app.app_context():
            tpl = ProjectTemplate(
                name='To Delete',
                created_by_user_id=self.admin_id,
            )
            db.session.add(tpl)
            db.session.commit()
            tpl_id = tpl.id

        response = self.client.post(f'/projects/templates/{tpl_id}/delete',
                                     follow_redirects=False)
        self.assertEqual(response.status_code, 302)

        with self.app.app_context():
            self.assertIsNone(db.session.get(ProjectTemplate, tpl_id))

    def test_create_from_template_renders(self):
        self.login_admin()
        with self.app.app_context():
            tpl = ProjectTemplate(
                name='From Tpl',
                description='Template desc',
                created_by_user_id=self.admin_id,
            )
            db.session.add(tpl)
            db.session.commit()
            tpl_id = tpl.id

        response = self.client.get(f'/projects/create/from_template/{tpl_id}')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'From Tpl', response.data)


# ── Project Link Management ──────────────────────────────────────────────

class ProjectLinkTests(_BaseProjectTests):
    def test_add_link(self):
        self.login_admin()
        response = self.client.post(
            f'/projects/{self.project_id}/add_link',
            data={'url': 'https://example.com/model', 'name': 'Example Model'},
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)

        with self.app.app_context():
            link = ProjectLink.query.filter_by(project_id=self.project_id).first()
            self.assertIsNotNone(link)
            self.assertEqual(link.url, 'https://example.com/model')

    def test_delete_link(self):
        self.login_admin()
        with self.app.app_context():
            link = ProjectLink(
                project_id=self.project_id,
                url='https://example.com/delete-me',
            )
            db.session.add(link)
            db.session.commit()
            link_id = link.id

        response = self.client.post(
            f'/projects/{self.project_id}/delete_link/{link_id}',
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)

        with self.app.app_context():
            self.assertIsNone(db.session.get(ProjectLink, link_id))

    @patch('routes.projects._schedule_link_preview_refresh')
    def test_add_link_with_external_refresh(self, mock_schedule):
        """Setting ?refresh=1 triggers link preview fetch."""
        self.login_admin()
        response = self.client.post(
            f'/projects/{self.project_id}/add_link',
            data={'url': 'https://example.com/refresh-test', 'name': 'Refresh'},
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)
        # The background preview refresh must be scheduled, but never perform
        # real network fetches inside the test suite.
        mock_schedule.assert_called_once()

        with self.app.app_context():
            link = ProjectLink.query.filter_by(project_id=self.project_id).first()
            self.assertIsNotNone(link)
            self.assertEqual(link.url, 'https://example.com/refresh-test')


# ── Project Filament Planning ────────────────────────────────────────────

class ProjectFilamentPlanningTests(_BaseProjectTests):
    def test_add_planned_filament(self):
        self.login_admin()
        response = self.client.post(
            f'/projects/{self.project_id}/add_filament',
            data={
                'filament_id': self.filament_id,
                'estimated_weight': '75.0',
            },
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)

        with self.app.app_context():
            pf = ProjectFilament.query.filter_by(
                project_id=self.project_id,
                filament_id=self.filament_id,
            ).first()
            self.assertIsNotNone(pf)
            self.assertAlmostEqual(pf.estimated_weight, 75.0)

    def test_remove_planned_filament(self):
        self.login_admin()
        with self.app.app_context():
            pf = ProjectFilament(
                project_id=self.project_id,
                filament_id=self.filament_id,
                estimated_weight=50.0,
            )
            db.session.add(pf)
            db.session.commit()
            pf_id = pf.id

        response = self.client.post(
            f'/projects/{self.project_id}/remove_filament/{pf_id}',
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)

        with self.app.app_context():
            self.assertIsNone(db.session.get(ProjectFilament, pf_id))

    def test_update_planned_filament_weight(self):
        self.login_admin()
        with self.app.app_context():
            pf = ProjectFilament(
                project_id=self.project_id,
                filament_id=self.filament_id,
                estimated_weight=30.0,
            )
            db.session.add(pf)
            db.session.commit()
            pf_id = pf.id

        self.client.post(
            f'/projects/{self.project_id}/update_filament/{pf_id}',
            data={'estimated_weight': '60.0'},
            follow_redirects=False,
        )

        with self.app.app_context():
            pf = db.session.get(ProjectFilament, pf_id)
            self.assertAlmostEqual(pf.estimated_weight, 60.0)

    def test_consume_filament_deducts_stock(self):
        self.login_admin()
        with self.app.app_context():
            pf = ProjectFilament(
                project_id=self.project_id,
                filament_id=self.filament_id,
                estimated_weight=100.0,
            )
            db.session.add(pf)
            db.session.commit()
            pf_id = pf.id
            initial_weight = db.session.get(Filament, self.filament_id).weight_remaining

        self.client.post(
            f'/projects/{self.project_id}/consume/{pf_id}',
            follow_redirects=False,
        )

        with self.app.app_context():
            f = db.session.get(Filament, self.filament_id)
            self.assertAlmostEqual(f.weight_remaining, initial_weight - 100.0)
            pf = db.session.get(ProjectFilament, pf_id)
            self.assertTrue(pf.is_used)


# ── Project Print Items ──────────────────────────────────────────────────

class ProjectPrintItemTests(_BaseProjectTests):
    def test_add_print_item(self):
        self.login_admin()
        response = self.client.post(
            f'/projects/{self.project_id}/printitems/add',
            data={'name': 'Test Part', 'quantity_total': '3'},
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)

        with self.app.app_context():
            item = ProjectPrintItem.query.filter_by(project_id=self.project_id).first()
            self.assertIsNotNone(item)
            self.assertEqual(item.name, 'Test Part')
            self.assertEqual(item.quantity_total, 3)
            self.assertEqual(item.quantity_done, 0)

    def test_edit_print_item(self):
        self.login_admin()
        with self.app.app_context():
            item = ProjectPrintItem(
                project_id=self.project_id,
                name='Old Name',
                quantity_total=2,
                quantity_done=1,
            )
            db.session.add(item)
            db.session.commit()
            item_id = item.id

        self.client.post(
            f'/projects/{self.project_id}/printitems/{item_id}/edit',
            data={
                'name': 'Updated Name',
                'quantity_total': '5',
                'quantity_done': '3',
            },
            follow_redirects=False,
        )

        with self.app.app_context():
            item = db.session.get(ProjectPrintItem, item_id)
            self.assertEqual(item.name, 'Updated Name')
            self.assertEqual(item.quantity_total, 5)
            self.assertEqual(item.quantity_done, 3)

    def test_delete_print_item(self):
        self.login_admin()
        with self.app.app_context():
            item = ProjectPrintItem(
                project_id=self.project_id,
                name='Delete Me',
                quantity_total=1,
            )
            db.session.add(item)
            db.session.commit()
            item_id = item.id

        self.client.post(
            f'/projects/{self.project_id}/printitems/{item_id}/delete',
            follow_redirects=False,
        )

        with self.app.app_context():
            self.assertIsNone(db.session.get(ProjectPrintItem, item_id))

    def test_increment_print_item(self):
        self.login_admin()
        with self.app.app_context():
            item = ProjectPrintItem(
                project_id=self.project_id,
                name='Increment Test',
                quantity_total=5,
                quantity_done=2,
            )
            db.session.add(item)
            db.session.commit()
            item_id = item.id

        self.client.post(
            f'/projects/{self.project_id}/printitems/{item_id}/increment',
            follow_redirects=False,
        )

        with self.app.app_context():
            item = db.session.get(ProjectPrintItem, item_id)
            self.assertEqual(item.quantity_done, 3)

    def test_decrement_print_item(self):
        self.login_admin()
        with self.app.app_context():
            item = ProjectPrintItem(
                project_id=self.project_id,
                name='Decrement Test',
                quantity_total=5,
                quantity_done=3,
            )
            db.session.add(item)
            db.session.commit()
            item_id = item.id

        self.client.post(
            f'/projects/{self.project_id}/printitems/{item_id}/decrement',
            follow_redirects=False,
        )

        with self.app.app_context():
            item = db.session.get(ProjectPrintItem, item_id)
            self.assertEqual(item.quantity_done, 2)

    def test_increment_beyond_total_is_clamped(self):
        self.login_admin()
        with self.app.app_context():
            item = ProjectPrintItem(
                project_id=self.project_id,
                name='Clamp Test',
                quantity_total=3,
                quantity_done=3,
            )
            db.session.add(item)
            db.session.commit()
            item_id = item.id

        self.client.post(
            f'/projects/{self.project_id}/printitems/{item_id}/increment',
            follow_redirects=False,
        )

        with self.app.app_context():
            item = db.session.get(ProjectPrintItem, item_id)
            self.assertEqual(item.quantity_done, 3)  # no change

    def test_decrement_below_zero_is_clamped(self):
        self.login_admin()
        with self.app.app_context():
            item = ProjectPrintItem(
                project_id=self.project_id,
                name='Neg Clamp',
                quantity_total=3,
                quantity_done=0,
            )
            db.session.add(item)
            db.session.commit()
            item_id = item.id

        self.client.post(
            f'/projects/{self.project_id}/printitems/{item_id}/decrement',
            follow_redirects=False,
        )

        with self.app.app_context():
            item = db.session.get(ProjectPrintItem, item_id)
            self.assertEqual(item.quantity_done, 0)

    def test_increment_via_ajax_returns_json(self):
        self.login_admin()
        with self.app.app_context():
            item = ProjectPrintItem(
                project_id=self.project_id,
                name='Ajax Inc',
                quantity_total=10,
                quantity_done=5,
            )
            db.session.add(item)
            db.session.commit()
            item_id = item.id

        response = self.client.post(
            f'/projects/{self.project_id}/printitems/{item_id}/increment',
            headers={'X-Requested-With': 'XMLHttpRequest'},
        )
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data['quantity_done'], 6)
        self.assertEqual(data['quantity_total'], 10)


# ── Comment Reactions ────────────────────────────────────────────────────

class CommentReactionTests(_BaseProjectTests):
    def setUp(self):
        super().setUp()
        with self.app.app_context():
            project = db.session.get(Project, self.project_id)
            comment = ProjectComment(
                project_id=project.id,
                user_id=self.admin_id,
                body='Test comment',
            )
            db.session.add(comment)
            db.session.commit()
            self.comment_id = comment.id

    def test_add_reaction(self):
        self.login_admin()
        response = self.client.post(
            f'/projects/{self.project_id}/comments/{self.comment_id}/react',
            data={'emoji': '👍'},
        )
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data['reacted'])
        self.assertEqual(data['count'], 1)

    def test_toggle_reaction_off(self):
        self.login_admin()
        self.client.post(
            f'/projects/{self.project_id}/comments/{self.comment_id}/react',
            data={'emoji': '👍'},
        )
        response = self.client.post(
            f'/projects/{self.project_id}/comments/{self.comment_id}/react',
            data={'emoji': '👍'},
        )
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertFalse(data['reacted'])
        self.assertEqual(data['count'], 0)

    def test_invalid_emoji_rejected(self):
        self.login_admin()
        response = self.client.post(
            f'/projects/{self.project_id}/comments/{self.comment_id}/react',
            data={'emoji': '💀'},  # Not in ALLOWED_EMOJIS
        )
        self.assertEqual(response.status_code, 400)

    def test_reaction_requires_auth(self):
        self.client.post('/logout', follow_redirects=False)
        response = self.client.post(
            f'/projects/{self.project_id}/comments/{self.comment_id}/react',
            data={'emoji': '👍'},
        )
        # Without auth, the endpoint either returns 401 (unauthorized) or 302 (redirect to login)
        self.assertIn(response.status_code, (401, 302))


# ── Project Detail ──────────────────────────────────────────────────────

class ProjectDetailTests(_BaseProjectTests):
    def test_project_detail_renders_all_tabs(self):
        self.login_admin()
        response = self.client.get(f'/projects/{self.project_id}')
        self.assertEqual(response.status_code, 200)
        html = response.data.decode('utf-8')
        for section in ('Přehled', 'Materiál', 'Soubory', 'Úkoly'):
            self.assertIn(section, html)

    def test_project_edit_updates_fields(self):
        self.login_admin()
        with self.app.app_context():
            project = db.session.get(Project, self.project_id)

        response = self.client.post(
            f'/projects/{self.project_id}/edit',
            data={
                'name': 'Updated Name',
                'description': 'Updated description',
                'client_name': 'Updated Client',
                'client_email': 'updated@example.com',
                'client_phone': '+420987654321',
                'tag_text': 'updated, tagged',
                'estimated_print_time': '180',
                'due_date': '2026-12-31',
            },
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)

        with self.app.app_context():
            project = db.session.get(Project, self.project_id)
            self.assertEqual(project.name, 'Updated Name')
            self.assertEqual(project.description, 'Updated description')
            self.assertEqual(project.client_email, 'updated@example.com')

    def test_project_delete(self):
        self.login_admin()
        response = self.client.post(
            f'/projects/{self.project_id}/delete',
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)

        with self.app.app_context():
            self.assertIsNone(db.session.get(Project, self.project_id))

    def test_project_detail_render_with_comment_and_edit_button(self):
        self.login_admin()
        with self.app.app_context():
            comment = ProjectComment(
                project_id=self.project_id,
                user_id=self.admin_id,
                body='Admin **comment**',
            )
            db.session.add(comment)
            db.session.commit()

        response = self.client.get(f'/projects/{self.project_id}')
        self.assertEqual(response.status_code, 200)
        html = response.data.decode('utf-8')
        self.assertIn('Admin', html)
        self.assertIn('comment', html)


# ── Project Search & Filter ──────────────────────────────────────────────

class ProjectFilterTests(_BaseProjectTests):
    def test_filter_by_status(self):
        self.login_admin()
        response = self.client.get('/projects?status=PENDING_APPROVAL')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Main Project', response.data)

    def test_filter_by_priority(self):
        self.login_admin()
        response = self.client.get('/projects?priority=high')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Main Project', response.data)

    def test_filter_by_tag(self):
        self.login_admin()
        response = self.client.get('/projects?tag=rush')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Main Project', response.data)

    def test_fulltext_search(self):
        self.login_admin()
        response = self.client.get('/projects?q=Main')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Main Project', response.data)


if __name__ == '__main__':
    unittest.main()
