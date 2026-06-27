"""
Tests for the v1.119.0 UI/UX enhancements.

Covers:
  1. Chart.js theming (palette tokens, light/dark transitions)
  2. Heatmap data structure produced by /stats
  3. Responsive table markup (data-label attributes) in users, history, audit
  4. Mobile row actions markup (enh-mobile-actions class)
  5. KPI counter + sparkline data attributes rendered by /stats
  6. Enhancements.css / enhancements.js assets are served
  7. New translations present in both languages
  8. Reaction buttons apply heart-pop animation
"""
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
    Brand,
    Color,
    Filament,
    Material,
    MovementHistory,
    User,
)
from utils import log_movement, utc_now


class _Base(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix='filament-v119-tests-')
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
            admin = User(
                email='admin119@example.com',
                name='Admin v119',
                password_hash=hash_password('password123'),
                role='admin',
            )
            db.session.add(admin)
            db.session.flush()

            brand = Brand.query.first()
            material = Material.query.first()
            color = Color.query.first()
            filament = Filament(
                name='Heatmap Test PLA',
                brand_id=brand.id,
                material_id=material.id,
                color_id=color.id,
                weight_total=1000.0,
                weight_remaining=500.0,
                price=200.0,
                quantity=1,
            )
            db.session.add(filament)
            db.session.flush()
            self.filament_id = filament.id
            self.admin_id = admin.id

            # A few historical moves at varied weekdays/hours to test the
            # heatmap aggregation. 5 moves, distributed across the week.
            now = utc_now()
            for offset_days in (0, 1, 3, 5, 6):
                ts = now - __import__('datetime').timedelta(days=offset_days, hours=2)
                db.session.add(MovementHistory(
                    filament_id=filament.id,
                    filament_name=filament.name,
                    action_type='remove',
                    weight=10.0,
                    cost=0.0,
                    currency='CZK',
                    note='v119 test',
                    created_at=ts,
                ))
            db.session.commit()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def login(self, email='admin119@example.com', password='password123'):
        return self.client.post(
            '/login',
            data={'email': email, 'password': password},
            follow_redirects=False,
        )


# ── 1. Static assets served ──────────────────────────────────────────────────
class EnhancementsAssetsTests(_Base):
    def test_enhancements_css_served(self):
        resp = self.client.get('/static/css/enhancements.css')
        self.assertEqual(resp.status_code, 200, 'enhancements.css must be served')
        body = resp.get_data(as_text=True)
        # Must include the theme tokens and at least one of the new components
        for needle in (
            '--enh-chart-grid',
            'ui-responsive-table',
            'enh-sparkline',
            'enh-heatmap',
            'enh-ripple',
            'enh-bounce-in',
        ):
            self.assertIn(needle, body, f'enhancements.css missing rule: {needle}')

    def test_enhancements_js_served(self):
        resp = self.client.get('/static/js/enhancements.js')
        self.assertEqual(resp.status_code, 200, 'enhancements.js must be served')
        body = resp.get_data(as_text=True)
        for needle in (
            'window.enh',
            'registerChart',
            'animateCounter',
            'initSparklines',
            'initHeatmaps',
            'watchTheme',
        ):
            self.assertIn(needle, body, f'enhancements.js missing: {needle}')

    def test_enhancements_loaded_in_base(self):
        self.login()
        resp = self.client.get('/')
        body = resp.get_data(as_text=True)
        self.assertIn('enhancements.css', body, 'base.html must load enhancements.css')
        self.assertIn('enhancements.js', body, 'base.html must load enhancements.js')


# ── 2. Heatmap data structure on /stats ──────────────────────────────────────
class StatsHeatmapTests(_Base):
    def test_stats_heatmap_data_shape(self):
        self.login()
        resp = self.client.get('/stats?days=30')
        self.assertEqual(resp.status_code, 200)
        body = resp.get_data(as_text=True)
        # The heatmap block must include the 7×24 matrix rendered into the
        # data-enh-heatmap attribute (a JSON payload).
        match = re.search(r"data-enh-heatmap='([^']+)'", body)
        self.assertIsNotNone(match, 'stats.html missing data-enh-heatmap element')
        import json as _json
        payload = _json.loads(match.group(1))
        self.assertIn('matrix', payload)
        self.assertIsInstance(payload['matrix'], list)
        self.assertEqual(len(payload['matrix']), 7, 'heatmap must have 7 weekday rows')
        for row in payload['matrix']:
            self.assertEqual(len(row), 24, 'each heatmap row must have 24 hours')
        # With the seeded data we should see at least 1 non-zero cell
        flat = [v for row in payload['matrix'] for v in row]
        self.assertGreater(sum(flat), 0, 'heatmap matrix must aggregate seed data')

    def test_stats_sparkline_data_attributes(self):
        self.login()
        resp = self.client.get('/stats?days=14')
        body = resp.get_data(as_text=True)
        # The 14-day window should produce 14 numbers in the sparkline.
        matches = re.findall(r'data-enh-sparkline="([^"]+)"', body)
        self.assertGreaterEqual(len(matches), 2, 'KPI cards must carry sparkline data')
        for m in matches:
            nums = [float(x) for x in m.split(',')]
            self.assertGreaterEqual(len(nums), 2, 'sparkline series too short')

    def test_stats_kpi_counter_attributes(self):
        self.login()
        resp = self.client.get('/stats?days=7')
        body = resp.get_data(as_text=True)
        # The 4 KPI cards must render enh-kpi-value with data-enh-counter
        self.assertIn('enh-kpi-value', body, 'KPI cards missing enh-kpi-value class')
        self.assertIn('data-enh-counter="', body, 'KPI cards missing data-enh-counter')


# ── 3. Responsive tables (users / history / audit) ───────────────────────────
class ResponsiveTablesTests(_Base):
    def test_users_table_responsive(self):
        self.login()
        resp = self.client.get('/users')
        body = resp.get_data(as_text=True)
        self.assertIn('ui-responsive-table', body, 'users table must be responsive')
        # Mobile action wrapper present
        self.assertIn('enh-mobile-actions', body, 'users table rows must be tap-revealable')
        # data-label attributes for the row-as-card layout
        self.assertIn('data-label="', body, 'responsive table cells must declare data-label')

    def test_history_table_responsive(self):
        self.login()
        resp = self.client.get('/history')
        body = resp.get_data(as_text=True)
        self.assertIn('ui-responsive-table', body, 'history table must be responsive')
        self.assertIn('enh-mobile-actions', body)

    def test_audit_table_responsive(self):
        self.login()
        resp = self.client.get('/audit')
        body = resp.get_data(as_text=True)
        # The audit page may be empty (no logs) — verify the template itself
        # is set up correctly. ui-responsive-table is rendered unconditionally.
        self.assertIn('ui-responsive-table', body, 'audit table must be responsive')
        # enh-mobile-actions only appears once per row; with zero rows it is
        # absent in the rendered HTML. Verify the source template wires it.
        with open(os.path.join(
            os.path.dirname(__file__), '..', 'templates', 'audit.html'
        ), encoding='utf-8') as f:
            template_src = f.read()
        self.assertIn('enh-mobile-actions', template_src, 'audit template must wire enh-mobile-actions')


# ── 4. Overview widget stagger animation ─────────────────────────────────────
class OverviewStaggerTests(_Base):
    def test_overview_widgets_have_stagger(self):
        self.login()
        resp = self.client.get('/')
        body = resp.get_data(as_text=True)
        # Container has data-stagger
        self.assertIn('data-stagger="10"', body, 'overview layout must declare stagger count')
        # Multiple data-animate children
        animate_count = body.count('data-animate')
        self.assertGreaterEqual(animate_count, 8, 'overview widgets should animate on reveal')


# ── 5. Reaction buttons apply heart-pop animation ────────────────────────────
class ReactionAnimationTests(_Base):
    def test_reaction_partial_has_heart_pop(self):
        """The _project_overview.html partial must trigger enh-heart-pop on click."""
        partial_path = os.path.join(
            os.path.dirname(__file__), '..', 'templates', '_project_overview.html'
        )
        with open(partial_path, 'r', encoding='utf-8') as f:
            content = f.read()
        self.assertIn('enh-heart-pop', content, 'reaction button must trigger heart-pop animation')


# ── 6. Translations (Rule 1) ─────────────────────────────────────────────────
class TranslationTests(unittest.TestCase):
    def test_heatmap_keys_in_both_languages(self):
        from messages import TRANSLATIONS
        for key in ('stats_heatmap_section', 'stats_heatmap_title', 'stats_heatmap_hint'):
            self.assertIn(key, TRANSLATIONS['cs'], f'cs missing {key}')
            self.assertIn(key, TRANSLATIONS['en'], f'en missing {key}')
            self.assertTrue(TRANSLATIONS['cs'][key].strip())
            self.assertTrue(TRANSLATIONS['en'][key].strip())

    def test_enh_row_actions_hint_in_both_languages(self):
        from messages import TRANSLATIONS
        self.assertIn('enh_row_actions_hint', TRANSLATIONS['cs'])
        self.assertIn('enh_row_actions_hint', TRANSLATIONS['en'])


# ── 7. Compliance re-check (no datetime.utcnow / no request.form[]) ──────────
class ComplianceSmokeTests(_Base):
    def test_no_datetime_utcnow_in_new_files(self):
        """The new files must not introduce datetime.utcnow usage."""
        for path in (
            'routes/stats.py',
            'static/css/enhancements.css',
            'static/js/enhancements.js',
        ):
            full = os.path.join(os.path.dirname(__file__), '..', path)
            with open(full, 'r', encoding='utf-8') as f:
                content = f.read()
            self.assertNotIn('datetime.utcnow', content, f'{path} still uses datetime.utcnow')

    def test_no_request_form_bracket_in_new_files(self):
        for path in (
            'routes/stats.py',
        ):
            full = os.path.join(os.path.dirname(__file__), '..', path)
            with open(full, 'r', encoding='utf-8') as f:
                content = f.read()
            # Allow request.form.get() but disallow request.form['key']
            self.assertNotIn("request.form['", content, f'{path} uses request.form[]')


if __name__ == '__main__':
    unittest.main()
