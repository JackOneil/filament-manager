"""
Tests for the 1.107.0 UI/UX improvements.

Covers:
  1. Optimistic UI for comment reactions (renders + JS in template)
  2. Skeleton loaders (CSS + partials are served + contain expected markup)
  3. Multi-phase upload stepper (template + JS)
  4. Undo toast for project + project-file deletion (snapshot + restore)
  5. First-login onboarding tour (?welcome=1 param + cookie)
"""
import io
import json
import os
import re
import shutil
import tempfile
import unittest

from app import create_app
from auth import hash_password
from database import db
from models import (
    AppSetting,
    Project,
    ProjectFile,
    ProjectLink,
    ProjectTodo,
    User,
)


class _Base(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix='filament-ui-tests-')
        db_path = os.path.join(self.temp_dir, 'test.db')
        upload_dir = os.path.join(self.temp_dir, 'uploads')

        self.app = create_app({
            'TESTING': True,
            'AUTH_REQUIRED_IN_TESTS': True,
            'SQLALCHEMY_DATABASE_URI': f'sqlite:///{db_path}',
            'PROJECT_UPLOAD_FOLDER': upload_dir,
            'WTF_CSRF_ENABLED': False,
        })
        self.client = self.app.test_client()
        os.makedirs(upload_dir, exist_ok=True)

        with self.app.app_context():
            owner = User(
                email='owner@example.com',
                name='Owner',
                password_hash=hash_password('password123'),
                role='user',
            )
            admin = User(
                email='admin@example.com',
                name='Admin',
                password_hash=hash_password('password123'),
                role='admin',
            )
            db.session.add_all([owner, admin])
            db.session.flush()

            project = Project(
                name='UI test project',
                owner_user_id=owner.id,
                created_by_user_id=owner.id,
                status='PENDING_APPROVAL',
            )
            db.session.add(project)
            db.session.commit()

            self.owner_id = owner.id
            self.admin_id = admin.id
            self.project_id = project.id

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def login(self, email, password='password123'):
        return self.client.post(
            '/login',
            data={'email': email, 'password': password},
            follow_redirects=False,
        )


# ── 1. Optimistic UI reactions ──────────────────────────────────────────────
class ReactionOptimisticUITests(_Base):
    def test_project_overview_includes_optimistic_toggle(self):
        """The commentReactions component must apply changes locally before
        the POST resolves, and revert on failure."""
        self.login('owner@example.com')
        # Trigger a reaction so the rendered reactions dict is non-empty.
        self.client.post(
            f'/projects/{self.project_id}/comments/0/react',  # 0 = no comment; just need to render
            data={'emoji': '👍'},
            follow_redirects=True,
        )
        # Render project detail (it has no comments, but that's fine — the
        # script block is always emitted at the bottom of the overview partial).
        response = self.client.get(f'/projects/{self.project_id}')
        self.assertEqual(response.status_code, 200)
        html = response.data.decode('utf-8')

        # 1. The toggle function must read `before`, mutate, then send.
        self.assertIn('Optimistic toggle', html)
        # 2. It must save the previous state for revert.
        self.assertIn('const before = this.reactions[emoji]', html)
        # 3. It must attempt a fetch POST to the react endpoint.
        self.assertIn('/react', html)
        # 4. On error, it must revert by restoring `before`.
        self.assertIn('// Revert optimistic change.', html)
        # 5. On error, it must show a client-side toast.
        self.assertIn("window.showToast('reaction_failed'", html)


# ── 2. Skeleton loaders ─────────────────────────────────────────────────────
class SkeletonLoaderTests(_Base):
    def test_skeleton_css_is_served(self):
        response = self.client.get('/static/css/skeleton.css')
        self.assertEqual(response.status_code, 200)
        css = response.data.decode('utf-8')
        self.assertIn('@keyframes skeleton-shimmer', css)
        self.assertIn('.skeleton-card', css)
        self.assertIn('.skeleton-row', css)

    def test_skeleton_partials_render(self):
        """The _skeleton_cards / _skeleton_rows partials are rendered via
        innerHTML swap in JS (not via Jinja include on the server). Verify
        the static HTML files exist with the expected markup."""
        from pathlib import Path
        cards = (Path('templates') / '_skeleton_cards.html').read_text(encoding='utf-8')
        rows = (Path('templates') / '_skeleton_rows.html').read_text(encoding='utf-8')
        self.assertIn('skeleton-grid', cards)
        self.assertIn('skeleton-card', cards)
        self.assertIn('skeleton-row', rows)

    def test_projects_index_injects_skeleton_during_fetch(self):
        """The projects fetchContent must set wrapper content to skeleton
        cards/rows at the start of the AJAX call."""
        self.login('admin@example.com')
        response = self.client.get('/projects')
        self.assertEqual(response.status_code, 200)
        html = response.data.decode('utf-8')
        self.assertIn('skeleton-card', html)
        self.assertIn('skeleton-row', html)
        # The skeleton must be injected into the kanban/calendar/table containers.
        for needle in (
            'kanban-items-pending_approval',
            'kanban-items-approved',
            'kanban-items-printing',
            'kanban-items-done',
            'kanban-items-rejected',
            'projects-calendar-items',
            'project-table-body',
        ):
            self.assertIn(needle, html)

    def test_inventory_skeleton_helper_still_present(self):
        """The pre-existing inventory skeleton helper must remain."""
        self.login('admin@example.com')
        response = self.client.get('/filaments')
        self.assertEqual(response.status_code, 200)
        # The JS helper is loaded as a separate static file.
        helper_path = 'static/js/inventory.js'
        helper = open(helper_path, encoding='utf-8').read()
        self.assertIn('buildInventorySkeletonHtml', helper)
        self.assertIn('ui-skeleton', helper)


# ── 3. Upload stepper ───────────────────────────────────────────────────────
class UploadStepperTests(_Base):
    def test_project_detail_uses_alpine_upload_stepper(self):
        self.login('owner@example.com')
        response = self.client.get(f'/projects/{self.project_id}')
        self.assertEqual(response.status_code, 200)
        html = response.data.decode('utf-8')
        # Alpine x-data
        self.assertIn('x-data="uploadStepper({', html)
        # 4 step labels (translated text, not the i18n key)
        from messages import TRANSLATIONS
        cs = TRANSLATIONS['cs']
        self.assertIn(cs['upload_step_validate'], html)
        self.assertIn(cs['upload_step_upload'], html)
        self.assertIn(cs['upload_step_preview'], html)
        self.assertIn(cs['upload_step_done'], html)
        # Progress bar bound to phase
        self.assertIn("x-show=\"phase === 'uploading'\"", html)
        # stepIndex computed drives the stepper styling
        self.assertIn('stepIndex >= 1', html)
        self.assertIn('stepIndex >= 4', html)

    def test_upload_stepper_i18n_keys_present(self):
        from messages import TRANSLATIONS
        for key in ('upload_step_validate', 'upload_step_upload',
                    'upload_step_preview', 'upload_step_done'):
            self.assertIn(key, TRANSLATIONS['cs'])
            self.assertIn(key, TRANSLATIONS['en'])

    def test_legacy_dropzone_js_removed(self):
        """The legacy `dropZone` / `fileInput` / `uploadForm` JS must be
        removed (it would break the Alpine stepper)."""
        detail = open('templates/project_detail.html', encoding='utf-8').read()
        # The new comment must be present.
        self.assertIn('Legacy drop-zone JS removed', detail)
        # The legacy getElementById code must be gone.
        self.assertNotIn("getElementById('drop-zone')", detail)
        self.assertNotIn("getElementById('file-input')", detail)
        self.assertNotIn("getElementById('upload-form')", detail)


# ── 4. Project / file undo ──────────────────────────────────────────────────
class ProjectUndoTests(_Base):
    def test_delete_project_records_undo_in_session(self):
        self.login('admin@example.com')
        response = self.client.post(
            f'/projects/{self.project_id}/delete',
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)
        # The session should now contain a project_pending_undo slot.
        with self.client.session_transaction() as sess:
            slot = sess.get('project_pending_undo')
            self.assertIsNotNone(slot)
            self.assertEqual(slot.get('kind'), 'project')
            self.assertIsNotNone(slot.get('undo_log_id'))
            self.assertEqual(slot.get('title_key'), 'project_undo_toast_title')
            self.assertIsNotNone(slot.get('expires_at'))

    def test_delete_project_file_records_undo_in_session(self):
        self.login('admin@example.com')
        # Create a project file in the upload folder.
        upload_folder = self.app.config['PROJECT_UPLOAD_FOLDER']
        stored_filename = 'test_part.stl'
        target = os.path.join(upload_folder, stored_filename)
        with open(target, 'wb') as f:
            f.write(b'solid hello\nendsolid hello\n')

        with self.app.app_context():
            pf = ProjectFile(
                project_id=self.project_id,
                filename='part.stl',
                filepath=target,
                version=1,
            )
            db.session.add(pf)
            db.session.commit()
            pf_id = pf.id

        response = self.client.post(
            f'/projects/{self.project_id}/delete_file/{pf_id}',
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)
        with self.client.session_transaction() as sess:
            slot = sess.get('project_pending_undo')
            self.assertIsNotNone(slot)
            self.assertEqual(slot.get('kind'), 'file')
            self.assertEqual(slot.get('title_key'), 'project_file_undo_toast_title')
            self.assertEqual(slot.get('project_id'), self.project_id)

    def test_undo_route_restores_deleted_project(self):
        self.login('admin@example.com')
        self.client.post(f'/projects/{self.project_id}/delete', follow_redirects=False)
        # Read the undo id.
        with self.client.session_transaction() as sess:
            slot = sess.get('project_pending_undo')
            self.assertIsNotNone(slot)
            undo_id = slot.get('undo_log_id')
        # POST to the undo endpoint.
        response = self.client.post(
            '/projects/undo',
            data={'undo_log_id': undo_id},
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)
        # The project should exist again.
        with self.app.app_context():
            self.assertEqual(Project.query.count(), 1)
            restored = Project.query.first()
            self.assertEqual(restored.name, 'UI test project')
            self.assertEqual(restored.status, 'PENDING_APPROVAL')

    def test_undo_route_restores_deleted_file(self):
        self.login('admin@example.com')
        # Seed a file.
        upload_folder = self.app.config['PROJECT_UPLOAD_FOLDER']
        stored_filename = 'restorable.stl'
        target = os.path.join(upload_folder, stored_filename)
        original_bytes = b'solid restorable\nendsolid restorable\n'
        with open(target, 'wb') as f:
            f.write(original_bytes)

        with self.app.app_context():
            pf = ProjectFile(
                project_id=self.project_id,
                filename='restorable.stl',
                filepath=target,
                version=1,
            )
            db.session.add(pf)
            db.session.commit()
            pf_id = pf.id

        self.client.post(
            f'/projects/{self.project_id}/delete_file/{pf_id}',
            follow_redirects=False,
        )
        with self.client.session_transaction() as sess:
            slot = sess.get('project_pending_undo')
            self.assertIsNotNone(slot)
            undo_id = slot.get('undo_log_id')

        # The original on-disk file was deleted by the handler. The undo
        # restores it from the temp snapshot.
        with self.app.app_context():
            self.assertEqual(ProjectFile.query.count(), 0)

        response = self.client.post(
            '/projects/undo',
            data={'undo_log_id': undo_id},
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)

        with self.app.app_context():
            restored = ProjectFile.query.first()
            self.assertIsNotNone(restored)
            self.assertEqual(restored.filename, 'restorable.stl')
            self.assertEqual(restored.filepath, target)
            # File content was restored.
            self.assertTrue(os.path.isfile(restored.filepath))
            with open(restored.filepath, 'rb') as f:
                self.assertEqual(f.read(), original_bytes)

    def test_undo_route_with_no_slot_reports_failure(self):
        self.login('admin@example.com')
        response = self.client.post(
            '/projects/undo',
            data={'undo_log_id': '99999'},
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)
        # The flash for "not available" should be present.
        from messages import TRANSLATIONS
        cs = TRANSLATIONS['cs']
        self.assertIn(cs['undo_toast_not_available'].encode('utf-8'), response.data)


# ── 5. First-login onboarding wizard ───────────────────────────────────────
class FirstLoginTourTests(_Base):
    def test_login_redirect_appends_welcome_when_cookie_missing(self):
        """A successful login without the first_login_tour_v1 cookie must
        redirect with ?welcome=1 and set the cookie."""
        response = self.login('admin@example.com')
        self.assertEqual(response.status_code, 302)
        self.assertIn('welcome=1', response.headers.get('Location', ''))
        # The cookie must be in the response.
        set_cookie = response.headers.get('Set-Cookie', '')
        self.assertIn('first_login_tour_v1=done', set_cookie)
        self.assertIn('Max-Age=', set_cookie)

    def test_login_does_not_append_welcome_when_cookie_present(self):
        """If the cookie is already set, the login must NOT re-trigger."""
        self.client.set_cookie('first_login_tour_v1', 'done')
        response = self.login('admin@example.com')
        self.assertEqual(response.status_code, 302)
        self.assertNotIn('welcome=1', response.headers.get('Location', ''))

    def test_first_login_tour_engine_chain_starts_on_overview(self):
        """The auto-start handler in tour.js must read ?welcome=1 and call
        startFirstLoginTour(). Verify both the URL param and the function
        are exposed in the rendered base template."""
        self.login('admin@example.com')
        response = self.client.get('/?welcome=1')
        self.assertEqual(response.status_code, 200)
        html = response.data.decode('utf-8')
        self.assertIn("window.__firstLoginTour", html)
        # The tour.js must define startFirstLoginTour.
        tour_js = open('static/js/tour.js', encoding='utf-8').read()
        self.assertIn('window.startFirstLoginTour', tour_js)
        self.assertIn('FIRST_LOGIN_STEPS', tour_js)
        # The 4 step tours referenced must exist.
        for section in ('filaments', 'projects', 'settings', 'stats'):
            self.assertIn(f"{section}:", tour_js, f"section {section} missing in TOUR_STEPS")
        # The chain must honour the cross-page ?first_login= param.
        self.assertIn('first_login=', tour_js)
        # Escape must cancel the chain.
        self.assertIn('onCancel', tour_js)

    def test_help_panel_includes_full_wizard_button(self):
        """The help panel must include a button to start the full wizard."""
        self.login('admin@example.com')
        response = self.client.get('/?welcome=1')
        self.assertEqual(response.status_code, 200)
        html = response.data.decode('utf-8')
        from messages import TRANSLATIONS
        cs = TRANSLATIONS['cs']
        self.assertIn(cs['tour_full_wizard_btn'], html)
        self.assertIn('startFirstLoginTour(1)', html)

    def test_full_wizard_button_translated_in_both_languages(self):
        from messages import TRANSLATIONS
        self.assertIn('tour_full_wizard_btn', TRANSLATIONS['cs'])
        self.assertIn('tour_full_wizard_btn', TRANSLATIONS['en'])


# ── 6. Compliance / sanity ─────────────────────────────────────────────────
class ComplianceTests(_Base):
    def test_no_datetime_utcnow_in_app_code(self):
        """Rule 24: must use utc_now() from utils."""
        for path in ('app.py', 'auth.py', 'utils/__init__.py'):
            content = open(path, encoding='utf-8').read()
            self.assertNotIn('datetime.utcnow()', content,
                f"datetime.utcnow() found in {path}")

    def test_no_request_form_bracket_access(self):
        """Rule 20: must use request.form.get()."""
        import re
        for path in ('app.py', 'auth.py', 'routes/auth.py'):
            if not os.path.isfile(path):
                continue
            content = open(path, encoding='utf-8').read()
            matches = re.findall(r"request\.form\[['\"][^'\"]+['\"]\]", content)
            self.assertEqual(matches, [], f"request.form[] found in {path}: {matches}")

    def test_i18n_keys_added_in_both_languages(self):
        from messages import TRANSLATIONS
        for key in (
            'project_undo_toast_title',
            'project_file_undo_toast_title',
            'tour_full_wizard_btn',
        ):
            self.assertIn(key, TRANSLATIONS['cs'], f"{key} missing in CS")
            self.assertIn(key, TRANSLATIONS['en'], f"{key} missing in EN")


if __name__ == '__main__':
    unittest.main()
