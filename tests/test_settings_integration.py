"""Tests for Settings page — dictionaries, Bambu Cloud, company details, reorder shop, 
waste reasons customization, and auto-backup configuration."""
import json
import os
import shutil
import tempfile
import unittest
from unittest.mock import patch

from app import create_app
from auth import hash_password
from database import db
from models import (
    AppSetting, BambuPrinter, Brand, Color, Filament, Material, 
    PrusaPrinter, Project, User,
)
from utils import utc_now


class _BaseSettingsTests(unittest.TestCase):
    """Shared setUp / tearDown for all settings test classes."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix='filament-settings-tests-')
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
            # Ensure AppSetting row exists
            setting = AppSetting.query.first()
            if not setting:
                setting = AppSetting(lang='cs')
                db.session.add(setting)
            db.session.commit()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _login_admin(self):
        return self.client.post(
            '/login',
            data={'email': 'admin@example.com', 'password': 'password123'},
            follow_redirects=True,
        )


# ── Dictionary Management ──────────────────────────────────────────────────

class DictionaryBrandTests(_BaseSettingsTests):
    """CRUD for brand dictionary entries."""

    def test_add_brand(self):
        self._login_admin()
        response = self.client.post('/settings', data={
            'action': 'brand',
            'name': 'Test Brand',
        }, follow_redirects=False)
        self.assertEqual(response.status_code, 302)

        with self.app.app_context():
            brand = Brand.query.filter_by(name='Test Brand').first()
            self.assertIsNotNone(brand)

    def test_add_brand_duplicate_is_rejected(self):
        self._login_admin()
        self.client.post('/settings', data={'action': 'brand', 'name': 'Dupe'})
        response = self.client.post('/settings', data={
            'action': 'brand', 'name': 'Dupe',
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)

        with self.app.app_context():
            count = Brand.query.filter_by(name='Dupe').count()
            self.assertEqual(count, 1)

    def test_add_brand_empty_name_is_rejected(self):
        self._login_admin()
        response = self.client.post('/settings', data={
            'action': 'brand', 'name': '',
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)

        with self.app.app_context():
            self.assertIsNone(Brand.query.filter_by(name='').first())

    def test_edit_brand(self):
        self._login_admin()
        with self.app.app_context():
            brand = Brand(name='Old Name')
            db.session.add(brand)
            db.session.commit()
            brand_id = brand.id

        self.client.post('/settings', data={
            'action': 'edit_brand',
            'id': brand_id,
            'name': 'New Name',
            'shop_url': 'https://shop.example.com',
        }, follow_redirects=False)

        with self.app.app_context():
            brand = db.session.get(Brand, brand_id)
            self.assertEqual(brand.name, 'New Name')
            self.assertEqual(brand.shop_url, 'https://shop.example.com')

    def test_delete_brand_without_filaments(self):
        self._login_admin()
        with self.app.app_context():
            brand = Brand(name='Deletable')
            db.session.add(brand)
            db.session.commit()
            brand_id = brand.id

        self.client.post('/settings', data={
            'action': 'delete_brand',
            'id': brand_id,
        }, follow_redirects=False)

        with self.app.app_context():
            self.assertIsNone(db.session.get(Brand, brand_id))

    def test_delete_brand_with_filaments_is_blocked(self):
        self._login_admin()
        with self.app.app_context():
            brand = Brand(name='Protected')
            mat = Material.query.first()
            col = Color.query.first()
            db.session.add(brand)
            db.session.flush()
            db.session.add(Filament(
                name='Protected Filament',
                brand_id=brand.id,
                color_id=col.id,
                material_id=mat.id,
                weight_total=1000,
                weight_remaining=800,
                price=500,
                quantity=1,
            ))
            db.session.commit()
            brand_id = brand.id

        self.client.post('/settings', data={
            'action': 'delete_brand',
            'id': brand_id,
        }, follow_redirects=False)

        with self.app.app_context():
            self.assertIsNotNone(db.session.get(Brand, brand_id))


class DictionaryColorTests(_BaseSettingsTests):
    """CRUD for color dictionary entries."""

    def test_add_color(self):
        self._login_admin()
        self.client.post('/settings', data={
            'action': 'color',
            'name': 'Neon Green',
            'hex_value': '#39FF14',
        }, follow_redirects=False)

        with self.app.app_context():
            color = Color.query.filter_by(name='Neon Green').first()
            self.assertIsNotNone(color)
            self.assertEqual(color.hex_value, '#39FF14')

    def test_add_color_empty_name_rejected(self):
        self._login_admin()
        response = self.client.post('/settings', data={
            'action': 'color', 'name': '',
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)

    def test_edit_color(self):
        self._login_admin()
        with self.app.app_context():
            color = Color(name='Old Color', hex_value='#000000')
            db.session.add(color)
            db.session.commit()
            color_id = color.id

        self.client.post('/settings', data={
            'action': 'edit_color',
            'id': color_id,
            'name': 'New Color',
            'hex_value': '#FFFFFF',
        }, follow_redirects=False)

        with self.app.app_context():
            c = db.session.get(Color, color_id)
            self.assertEqual(c.name, 'New Color')
            self.assertEqual(c.hex_value, '#FFFFFF')

    def test_delete_color_without_filaments(self):
        self._login_admin()
        with self.app.app_context():
            color = Color(name='Temp Color', hex_value='#123456')
            db.session.add(color)
            db.session.commit()
            color_id = color.id

        self.client.post('/settings', data={
            'action': 'delete_color',
            'id': color_id,
        }, follow_redirects=False)

        with self.app.app_context():
            self.assertIsNone(db.session.get(Color, color_id))


class DictionaryMaterialTests(_BaseSettingsTests):
    """CRUD for material dictionary entries."""

    def test_add_material(self):
        self._login_admin()
        self.client.post('/settings', data={
            'action': 'material',
            'name': 'PEEK',
        }, follow_redirects=False)

        with self.app.app_context():
            self.assertIsNotNone(Material.query.filter_by(name='PEEK').first())

    def test_edit_material(self):
        self._login_admin()
        with self.app.app_context():
            mat = Material(name='OldMat')
            db.session.add(mat)
            db.session.commit()
            mat_id = mat.id

        self.client.post('/settings', data={
            'action': 'edit_material',
            'id': mat_id,
            'name': 'NewMat',
        }, follow_redirects=False)

        with self.app.app_context():
            self.assertEqual(db.session.get(Material, mat_id).name, 'NewMat')

    def test_delete_material_without_filaments(self):
        self._login_admin()
        with self.app.app_context():
            mat = Material(name='TempMat')
            db.session.add(mat)
            db.session.commit()
            mat_id = mat.id

        self.client.post('/settings', data={
            'action': 'delete_material',
            'id': mat_id,
        }, follow_redirects=False)

        with self.app.app_context():
            self.assertIsNone(db.session.get(Material, mat_id))

    def test_delete_material_with_filaments_is_blocked(self):
        self._login_admin()
        with self.app.app_context():
            mat = Material(name='ProtectedMat')
            brand = Brand.query.first()
            col = Color.query.first()
            db.session.add(mat)
            db.session.flush()
            db.session.add(Filament(
                name='Protected Filament',
                brand_id=brand.id,
                color_id=col.id,
                material_id=mat.id,
                weight_total=1000,
                weight_remaining=800,
                price=500,
                quantity=1,
            ))
            db.session.commit()
            mat_id = mat.id

        self.client.post('/settings', data={
            'action': 'delete_material',
            'id': mat_id,
        }, follow_redirects=False)

        with self.app.app_context():
            self.assertIsNotNone(db.session.get(Material, mat_id))


# ── Bambu Cloud Integration ────────────────────────────────────────────────

class BambuCloudSettingsTests(_BaseSettingsTests):
    """Bambu Cloud connection, disconnect, and sync configuration."""

    def test_bambu_cloud_settings_page_renders(self):
        self._login_admin()
        response = self.client.get('/settings?tab=integrations')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'bambu', response.data.lower())

    def test_save_bambu_cloud_token_and_region(self):
        self._login_admin()
        with patch.dict(os.environ, {'FERNET_KEY': ''}):
            self.client.post('/settings', data={
                'action': 'bambu_cloud_settings',
                'bambu_token': 'test-token-123',
                'bambu_region': 'china',
                'bambu_auto_sync_enabled': 'on',
                'bambu_auto_sync_interval_minutes': '30',
                'auto_filament_mapping_enabled': 'on',
            }, follow_redirects=False)

        with self.app.app_context():
            setting = AppSetting.query.first()
            # Without FERNET_KEY, token is stored as plaintext
            self.assertIn('test-token-123', setting.bambu_token)
            self.assertEqual(setting.bambu_region, 'china')
            self.assertTrue(setting.bambu_auto_sync_enabled)
            self.assertEqual(setting.bambu_auto_sync_interval_minutes, 30)
            self.assertTrue(setting.auto_filament_mapping_enabled)

    def test_bambu_cloud_disconnect_clears_token(self):
        self._login_admin()
        with self.app.app_context():
            setting = AppSetting.query.first()
            setting.bambu_token = 'existing-token'
            db.session.commit()

        self.client.post('/settings', data={
            'action': 'bambu_cloud_disconnect',
        }, follow_redirects=False)

        with self.app.app_context():
            setting = AppSetting.query.first()
            self.assertIsNone(setting.bambu_token)

    def test_bambu_test_without_token_returns_400(self):
        self._login_admin()
        response = self.client.post('/settings/bambu/test', data={
            'bambu_token': '',
            'bambu_region': 'global',
        })
        self.assertEqual(response.status_code, 400)
        data = response.get_json()
        self.assertFalse(data['ok'])

    @patch('routes.settings.requests.get')
    def test_bambu_test_with_valid_token(self, mock_get):
        self._login_admin()
        mock_get.return_value.status_code = 200
        mock_get.return_value.ok = True
        mock_get.return_value.headers = {'Content-Type': 'application/json'}

        response = self.client.post('/settings/bambu/test', data={
            'bambu_token': 'valid-token',
            'bambu_region': 'global',
        })
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data['ok'])

    @patch('routes.settings.requests.get')
    def test_bambu_test_with_invalid_token(self, mock_get):
        self._login_admin()
        mock_get.return_value.status_code = 401
        mock_get.return_value.ok = False
        mock_get.return_value.headers = {'Content-Type': 'application/json'}

        response = self.client.post('/settings/bambu/test', data={
            'bambu_token': 'bad-token',
            'bambu_region': 'global',
        })
        self.assertEqual(response.status_code, 400)
        data = response.get_json()
        self.assertFalse(data['ok'])

    @patch('routes.settings.requests.get')
    def test_bambu_test_uses_stored_token_when_form_empty(self, mock_get):
        self._login_admin()
        with self.app.app_context():
            setting = AppSetting.query.first()
            setting.bambu_token = 'stored-token'
            db.session.commit()

        mock_get.return_value.status_code = 200
        mock_get.return_value.ok = True
        mock_get.return_value.headers = {'Content-Type': 'application/json'}

        response = self.client.post('/settings/bambu/test', data={
            'bambu_token': '',
            'bambu_region': 'global',
        })
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data['ok'])

    def test_settings_page_shows_printer_health(self):
        self._login_admin()
        with self.app.app_context():
            printer = BambuPrinter(
                device_id='DEV001',
                name='Test Printer',
                printer_model='X1C',
            )
            db.session.add(printer)
            db.session.commit()

        response = self.client.get('/settings')
        self.assertEqual(response.status_code, 200)
        html = response.data.decode('utf-8')
        self.assertIn('Test Printer', html)


# ── Company / Billing ──────────────────────────────────────────────────────

class CompanySettingsTests(_BaseSettingsTests):
    """Company billing details and invoice numbering."""

    def test_save_billing_details(self):
        self._login_admin()
        self.client.post('/settings', data={
            'action': 'billing_settings',
            'company_name': 'My 3D Print s.r.o.',
            'company_street': 'Street 123',
            'company_city': 'Prague',
            'company_zip': '11000',
            'company_id': '12345678',
            'company_vat_id': 'CZ12345678',
            'company_bank_account': 'CZ6508000000192000145399',
        }, follow_redirects=False)

        with self.app.app_context():
            setting = AppSetting.query.first()
            self.assertEqual(setting.company_name, 'My 3D Print s.r.o.')
            self.assertEqual(setting.company_id, '12345678')

    def test_clear_billing_details(self):
        self._login_admin()
        with self.app.app_context():
            setting = AppSetting.query.first()
            setting.company_name = 'Old Name'
            db.session.commit()

        self.client.post('/settings', data={
            'action': 'billing_settings',
            'company_name': '',
            'company_street': '',
            'company_city': '',
            'company_zip': '',
            'company_id': '',
            'company_vat_id': '',
            'company_bank_account': '',
        }, follow_redirects=False)

        with self.app.app_context():
            setting = AppSetting.query.first()
            self.assertIsNone(setting.company_name)


# ── Reorder Shop URL ───────────────────────────────────────────────────────

class ReorderShopTests(_BaseSettingsTests):
    """Shop URL template configuration."""

    def test_save_valid_reorder_shop_url(self):
        self._login_admin()
        self.client.post('/settings', data={
            'action': 'reorder_shop_settings',
            'reorder_shop_url': 'https://example.com/search?q={query}',
        }, follow_redirects=False)

        with self.app.app_context():
            setting = AppSetting.query.first()
            self.assertEqual(setting.reorder_shop_url, 'https://example.com/search?q={query}')

    def test_reject_url_without_query_placeholder(self):
        self._login_admin()
        self.client.post('/settings', data={
            'action': 'reorder_shop_settings',
            'reorder_shop_url': 'https://example.com/no-placeholder',
        }, follow_redirects=True)

        with self.app.app_context():
            setting = AppSetting.query.first()
            self.assertIsNone(setting.reorder_shop_url)

    def test_clear_reorder_shop_url(self):
        self._login_admin()
        with self.app.app_context():
            setting = AppSetting.query.first()
            setting.reorder_shop_url = 'https://example.com/?q={query}'
            db.session.commit()

        self.client.post('/settings', data={
            'action': 'reorder_shop_settings',
            'reorder_shop_url': '',
        }, follow_redirects=False)

        with self.app.app_context():
            setting = AppSetting.query.first()
            self.assertIsNone(setting.reorder_shop_url)

    def test_reject_non_https_url(self):
        self._login_admin()
        self.client.post('/settings', data={
            'action': 'reorder_shop_settings',
            'reorder_shop_url': 'http://example.com/?q={query}',
        }, follow_redirects=True)

        with self.app.app_context():
            setting = AppSetting.query.first()
            self.assertIsNone(setting.reorder_shop_url)


# ── Waste Reasons Customization ────────────────────────────────────────────

class WasteReasonsTests(_BaseSettingsTests):
    """Customizable waste reasons stored in AppSetting."""

    def test_save_custom_waste_reasons(self):
        self._login_admin()
        response = self.client.post('/settings', data={
            'action': 'waste_reasons',
            'waste_reasons_json': '["stringing", "failed print"]',
        }, follow_redirects=False)
        self.assertIn(response.status_code, (200, 302))

        with self.app.app_context():
            setting = AppSetting.query.first()
            self.assertIsNotNone(setting)
            self.assertEqual(setting.waste_reasons_json, '["stringing", "failed print"]')

    def test_invalid_waste_reasons_json_is_ignored(self):
        self._login_admin()
        self.client.post('/settings', data={
            'action': 'waste_reasons',
            'waste_reasons_json': '{not valid json',
        }, follow_redirects=True)

        with self.app.app_context():
            setting = AppSetting.query.first()
            self.assertIsNotNone(setting)
            # Invalid JSON must not be stored — the previous value survives.
            self.assertNotEqual(setting.waste_reasons_json, '{not valid json')


# ── Auto-Backup Configuration ──────────────────────────────────────────────

class AutoBackupConfigTests(_BaseSettingsTests):
    """Automatic backup schedule configuration via settings."""

    def test_enable_auto_backup_daily(self):
        self._login_admin()
        self.client.post('/settings', data={
            'action': 'backup_auto_settings',
            'backup_auto_enabled': 'on',
            'backup_auto_frequency': 'daily',
            'backup_auto_time': '02:30',
            'backup_auto_day': '0',
            'backup_auto_include_files': 'on',
            'backup_auto_keep_count': '5',
            'backup_auto_keep_days': '30',
        }, follow_redirects=False)

        with self.app.app_context():
            setting = AppSetting.query.first()
            self.assertTrue(setting.backup_auto_enabled)
            self.assertEqual(setting.backup_auto_frequency, 'daily')
            self.assertEqual(setting.backup_auto_time, '02:30')
            self.assertTrue(setting.backup_auto_include_files)
            self.assertEqual(setting.backup_auto_keep_count, 5)
            self.assertEqual(setting.backup_auto_keep_days, 30)

    def test_enable_auto_backup_weekly(self):
        self._login_admin()
        self.client.post('/settings', data={
            'action': 'backup_auto_settings',
            'backup_auto_enabled': 'on',
            'backup_auto_frequency': 'weekly',
            'backup_auto_time': '03:00',
            'backup_auto_day': '2',  # Wednesday
            'backup_auto_include_files': '',
        }, follow_redirects=False)

        with self.app.app_context():
            setting = AppSetting.query.first()
            self.assertEqual(setting.backup_auto_frequency, 'weekly')
            self.assertEqual(setting.backup_auto_day, 2)
            self.assertFalse(setting.backup_auto_include_files)

    def test_enable_auto_backup_monthly(self):
        self._login_admin()
        self.client.post('/settings', data={
            'action': 'backup_auto_settings',
            'backup_auto_enabled': 'on',
            'backup_auto_frequency': 'monthly',
            'backup_auto_time': '04:00',
            'backup_auto_day': '15',
        }, follow_redirects=False)

        with self.app.app_context():
            setting = AppSetting.query.first()
            self.assertEqual(setting.backup_auto_frequency, 'monthly')
            self.assertEqual(setting.backup_auto_day, 15)

    def test_disable_auto_backup(self):
        self._login_admin()
        with self.app.app_context():
            setting = AppSetting.query.first()
            setting.backup_auto_enabled = True
            db.session.commit()

        self.client.post('/settings', data={
            'action': 'backup_auto_settings',
            'backup_auto_enabled': '',
        }, follow_redirects=False)

        with self.app.app_context():
            setting = AppSetting.query.first()
            self.assertFalse(setting.backup_auto_enabled)

    def test_auto_backup_invalid_frequency_defaults_to_weekly(self):
        self._login_admin()
        self.client.post('/settings', data={
            'action': 'backup_auto_settings',
            'backup_auto_enabled': 'on',
            'backup_auto_frequency': 'invalid',
            'backup_auto_time': '03:00',
        }, follow_redirects=False)

        with self.app.app_context():
            setting = AppSetting.query.first()
            self.assertEqual(setting.backup_auto_frequency, 'weekly')

    def test_auto_backup_retention_zero_values(self):
        """Zero keep_count/keep_days means unlimited."""
        self._login_admin()
        self.client.post('/settings', data={
            'action': 'backup_auto_settings',
            'backup_auto_enabled': 'on',
            'backup_auto_frequency': 'daily',
            'backup_auto_time': '03:00',
            'backup_auto_keep_count': '0',
            'backup_auto_keep_days': '0',
        }, follow_redirects=False)

        with self.app.app_context():
            setting = AppSetting.query.first()
            self.assertEqual(setting.backup_auto_keep_count, 0)
            self.assertEqual(setting.backup_auto_keep_days, 0)


# ── Language & Locale ──────────────────────────────────────────────────────

class LocaleSettingsTests(_BaseSettingsTests):
    """Language, currency, timezone, and appearance settings."""

    def test_change_language(self):
        self._login_admin()
        self.client.post('/settings', data={
            'action': 'language',
            'lang': 'en',
        }, follow_redirects=False)

        with self.app.app_context():
            setting = AppSetting.query.first()
            self.assertEqual(setting.lang, 'en')

    def test_change_currency(self):
        self._login_admin()
        self.client.post('/settings', data={
            'action': 'currency',
            'currency': 'EUR',
        }, follow_redirects=False)

        with self.app.app_context():
            setting = AppSetting.query.first()
            self.assertEqual(setting.currency, 'EUR')

    def test_change_nav_palette(self):
        self._login_admin()
        response = self.client.post('/settings', data={
            'action': 'nav_palette',
            'nav_palette': 'sunset',
        }, follow_redirects=False)
        self.assertEqual(response.status_code, 302)

        with self.app.app_context():
            setting = AppSetting.query.first()
            self.assertEqual(setting.nav_palette, 'sunset')

    def test_invalid_nav_palette_defaults_to_teal(self):
        self._login_admin()
        self.client.post('/settings', data={
            'action': 'nav_palette',
            'nav_palette': 'invalid',
        }, follow_redirects=False)

        with self.app.app_context():
            setting = AppSetting.query.first()
            self.assertEqual(setting.nav_palette, 'teal')

    def test_set_valid_timezone(self):
        self._login_admin()
        self.client.post('/settings', data={
            'action': 'app_timezone',
            'app_timezone': 'America/New_York',
        }, follow_redirects=False)

        with self.app.app_context():
            setting = AppSetting.query.first()
            self.assertEqual(setting.app_timezone, 'America/New_York')

    def test_set_invalid_timezone_rejected(self):
        self._login_admin()
        self.client.post('/settings', data={
            'action': 'app_timezone',
            'app_timezone': 'Not/A_Zone',
        }, follow_redirects=True)

        with self.app.app_context():
            setting = AppSetting.query.first()
            self.assertNotEqual(setting.app_timezone, 'Not/A_Zone')

    def test_toggle_theme(self):
        self._login_admin()
        with self.app.app_context():
            setting = AppSetting.query.first()
            setting.theme = 'light'
            db.session.commit()

        self.client.post('/toggle-theme', follow_redirects=False)

        with self.app.app_context():
            setting = AppSetting.query.first()
            self.assertEqual(setting.theme, 'dark')

    def test_onboarding_dismiss(self):
        self._login_admin()
        with self.app.app_context():
            setting = AppSetting.query.first()
            setting.onboarding_dismissed = False
            db.session.commit()

        self.client.post('/onboarding/dismiss', follow_redirects=False)

        with self.app.app_context():
            setting = AppSetting.query.first()
            self.assertTrue(setting.onboarding_dismissed)

    def test_toggle_debug_logging(self):
        self._login_admin()
        self.client.post('/settings', data={
            'action': 'debug_logging',
            'debug_logging': 'on',
        }, follow_redirects=False)

        with self.app.app_context():
            setting = AppSetting.query.first()
            self.assertTrue(setting.debug_logging)

    def test_toggle_audit_logging(self):
        self._login_admin()
        with self.app.app_context():
            setting = AppSetting.query.first()
            setting.audit_logging_enabled = True
            db.session.commit()

        self.client.post('/settings', data={
            'action': 'audit_logging',
            'audit_logging_enabled': '',
        }, follow_redirects=False)

        with self.app.app_context():
            setting = AppSetting.query.first()
            self.assertFalse(setting.audit_logging_enabled)


# ── Settings Page Smoke Test ───────────────────────────────────────────────

class SettingsPageRenderingTests(_BaseSettingsTests):
    """The settings page renders with all sections."""

    def test_settings_page_renders_all_tabs(self):
        self._login_admin()
        response = self.client.get('/settings')
        self.assertEqual(response.status_code, 200)
        html = response.data.decode('utf-8')

        # All major tabs should be present
        for section in ('Obecné', 'Číselníky', 'Tiskárny', 'Integrace', 'Firma', 'Data'):
            self.assertIn(section, html)

    def test_settings_page_shows_backup_meta(self):
        self._login_admin()
        with self.app.app_context():
            setting = AppSetting.query.first()
            setting.backup_last_export_meta = json.dumps({
                'app_version': '1.107.0',
                'timestamp': '2026-01-01T00:00:00',
                'include_files': True,
                'counts': {'filaments': 5},
            })
            db.session.commit()

        response = self.client.get('/settings')
        self.assertEqual(response.status_code, 200)
        html = response.data.decode('utf-8')
        self.assertIn('Záloha', html)


if __name__ == '__main__':
    unittest.main()
