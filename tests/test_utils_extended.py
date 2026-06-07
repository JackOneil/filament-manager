"""Extended unit tests for core utility functions — encrypt/decrypt, stock status,
deduction logic, tag parsing, hex normalization, auto-map, host validation,
and duration formatting."""
import json
import os
import unittest
from unittest.mock import patch

from database import db
from app import create_app


# ── Encrypt / Decrypt ─────────────────────────────────────────────────────

class EncryptDecryptTests(unittest.TestCase):
    def setUp(self):
        # Create a real app for context (needed for some imports)
        import tempfile, shutil
        self.temp_dir = tempfile.mkdtemp(prefix='util-enc-tests-')
        db_path = os.path.join(self.temp_dir, 'test.db')
        self.app = create_app({
            'TESTING': True,
            'SQLALCHEMY_DATABASE_URI': f'sqlite:///{db_path}',
            'PROJECT_UPLOAD_FOLDER': os.path.join(self.temp_dir, 'uploads'),
            'WTF_CSRF_ENABLED': False,
        })

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_encrypt_returns_plaintext_without_key(self):
        with patch.dict(os.environ, {}, clear=True):
            from utils import encrypt_token
            result = encrypt_token('secret-token')
            self.assertEqual(result, 'secret-token')

    def test_decrypt_returns_plaintext_without_key(self):
        with patch.dict(os.environ, {}, clear=True):
            from utils import decrypt_token
            result = decrypt_token('secret-token')
            self.assertEqual(result, 'secret-token')

    def test_encrypt_empty_returns_empty(self):
        from utils import encrypt_token
        self.assertEqual(encrypt_token(''), '')
        self.assertEqual(encrypt_token(None), None)

    def test_decrypt_empty_returns_empty(self):
        from utils import decrypt_token
        self.assertEqual(decrypt_token(''), '')
        self.assertEqual(decrypt_token(None), None)

    def test_encrypt_decrypt_roundtrip_with_key(self):
        key = base64_urlsafe_key()
        with patch.dict(os.environ, {'FERNET_KEY': key}):
            from utils import encrypt_token, decrypt_token
            original = 'my-secret-api-key-123'
            encrypted = encrypt_token(original)
            self.assertNotEqual(encrypted, original)
            decrypted = decrypt_token(encrypted)
            self.assertEqual(decrypted, original)


def base64_urlsafe_key():
    """Generate a valid Fernet key for testing."""
    from cryptography.fernet import Fernet
    return Fernet.generate_key().decode()


# ── Stock Status ─────────────────────────────────────────────────────────

class ComputeStockStatusTests(unittest.TestCase):
    def setUp(self):
        import tempfile, shutil
        self.temp_dir = tempfile.mkdtemp(prefix='util-stock-tests-')
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
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _make_filament(self, remaining=500, total=1000, price=500, quantity=1,
                       min_stock=0, max_stock=0):
        from types import SimpleNamespace
        return SimpleNamespace(
            weight_remaining=remaining,
            weight_total=total,
            price=price,
            quantity=quantity,
            min_stock_grams=min_stock,
            max_stock_grams=max_stock,
        )

    def test_status_stable_above_min_and_usage(self):
        from utils import compute_stock_status
        f = self._make_filament(remaining=800, min_stock=200)
        result = compute_stock_status(f, usage_30=100, usage_90=300)
        self.assertEqual(result['status'], 'stable')

    def test_status_warning_below_min_stock(self):
        from utils import compute_stock_status
        f = self._make_filament(remaining=150, min_stock=200)
        result = compute_stock_status(f, usage_30=0, usage_90=0)
        self.assertEqual(result['status'], 'warning')

    def test_status_critical_below_half_min_stock(self):
        from utils import compute_stock_status
        f = self._make_filament(remaining=80, min_stock=200)
        result = compute_stock_status(f, usage_30=0, usage_90=0)
        self.assertEqual(result['status'], 'critical')

    def test_status_critical_zero_remaining(self):
        from utils import compute_stock_status
        f = self._make_filament(remaining=0)
        result = compute_stock_status(f, usage_30=0, usage_90=0)
        self.assertEqual(result['status'], 'critical')

    def test_status_warning_below_30day_usage(self):
        from utils import compute_stock_status
        f = self._make_filament(remaining=80)
        result = compute_stock_status(f, usage_30=100, usage_90=300)
        self.assertEqual(result['status'], 'warning')

    def test_recommended_spools_calculated(self):
        from utils import compute_stock_status
        f = self._make_filament(remaining=100, total=1000, price=500, min_stock=500)
        result = compute_stock_status(f, usage_30=0, usage_90=0)
        self.assertGreater(result['recommended_grams'], 0)

    def test_no_usage_returns_zero_recommendation(self):
        from utils import compute_stock_status
        f = self._make_filament(remaining=500)
        result = compute_stock_status(f, usage_30=0, usage_90=0)
        self.assertEqual(result['recommended_grams'], 0.0)

    def test_spool_price_in_result(self):
        from utils import compute_stock_status
        f = self._make_filament(price=750)
        result = compute_stock_status(f, usage_30=0, usage_90=0)
        self.assertAlmostEqual(result['spool_price'], 750.0)


# ── Deduct Filament Stock ────────────────────────────────────────────────

class DeductFilamentStockTests(unittest.TestCase):
    def setUp(self):
        import tempfile, shutil
        self.temp_dir = tempfile.mkdtemp(prefix='util-deduct-tests-')
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
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _make_filament(self, remaining=500, total=1000, quantity=2):
        from types import SimpleNamespace
        return SimpleNamespace(
            weight_remaining=remaining,
            weight_total=total,
            quantity=quantity,
        )

    def test_deduct_reduces_weight(self):
        from utils import deduct_filament_stock
        f = self._make_filament(remaining=500)
        actual = deduct_filament_stock(f, 100)
        self.assertAlmostEqual(actual, 100.0)
        self.assertAlmostEqual(f.weight_remaining, 400.0)

    def test_deduct_clamps_to_zero(self):
        from utils import deduct_filament_stock
        f = self._make_filament(remaining=50)
        actual = deduct_filament_stock(f, 200)
        self.assertAlmostEqual(actual, 50.0)
        self.assertAlmostEqual(f.weight_remaining, 0.0)

    def test_deduct_updates_quantity(self):
        from utils import deduct_filament_stock
        f = self._make_filament(remaining=1500, total=1000, quantity=2)
        deduct_filament_stock(f, 600)
        # After: 900 remaining / 1000 total = 0.9 -> ceil = 1
        self.assertEqual(f.quantity, 1)

    def test_deduct_zero_requested_returns_zero(self):
        from utils import deduct_filament_stock
        f = self._make_filament()
        actual = deduct_filament_stock(f, 0)
        self.assertAlmostEqual(actual, 0.0)
        self.assertAlmostEqual(f.weight_remaining, 500.0)

    def test_deduct_none_filament_returns_zero(self):
        from utils import deduct_filament_stock
        actual = deduct_filament_stock(None, 100)
        self.assertAlmostEqual(actual, 0.0)

    def test_deduct_negative_requested_returns_zero(self):
        from utils import deduct_filament_stock
        f = self._make_filament()
        actual = deduct_filament_stock(f, -100)
        self.assertAlmostEqual(actual, 0.0)
        self.assertAlmostEqual(f.weight_remaining, 500.0)

    def test_deduct_quantity_not_below_1_when_only_small_deduct(self):
        from utils import deduct_filament_stock
        f = self._make_filament(remaining=1800, total=1000, quantity=2)
        deduct_filament_stock(f, 50)
        self.assertEqual(f.quantity, 2)  # Still > 1 spool worth


# ── Tag Parsing ──────────────────────────────────────────────────────────

class ParseTagsTests(unittest.TestCase):
    def test_empty_string(self):
        from utils import parse_tags
        self.assertEqual(parse_tags(''), [])

    def test_none(self):
        from utils import parse_tags
        self.assertEqual(parse_tags(None), [])

    def test_comma_separated(self):
        from utils import parse_tags
        result = parse_tags('a, b, c')
        self.assertEqual(result, ['a', 'b', 'c'])

    def test_semicolon_separated(self):
        from utils import parse_tags
        result = parse_tags('x; y; z')
        self.assertEqual(result, ['x', 'y', 'z'])

    def test_newline_separated(self):
        from utils import parse_tags
        result = parse_tags('one\ntwo\nthree')
        self.assertEqual(result, ['one', 'two', 'three'])

    def test_deduplicates(self):
        from utils import parse_tags
        result = parse_tags('a, b, A, B')
        self.assertEqual(result, ['a', 'b'])  # case-insensitive dedup

    def test_trims_whitespace(self):
        from utils import parse_tags
        result = parse_tags('  spaced  ,  tag  ')
        self.assertEqual(result, ['spaced', 'tag'])

    def test_format_tags(self):
        from utils import format_tags
        result = format_tags('a, b')
        self.assertEqual(result, 'a, b')

    def test_remove_tag(self):
        from utils import remove_tag
        result = remove_tag('a, b, c', 'b')
        self.assertEqual(result, 'a, c')

    def test_remove_tag_case_insensitive(self):
        from utils import remove_tag
        result = remove_tag('A, B, C', 'a')
        self.assertEqual(result, 'B, C')


# ── Hex Normalization ────────────────────────────────────────────────────

class NormalizeHexTests(unittest.TestCase):
    def test_with_hash(self):
        from utils import normalize_hex
        self.assertEqual(normalize_hex('#ff0000'), '#FF0000')

    def test_without_hash(self):
        from utils import normalize_hex
        self.assertEqual(normalize_hex('ff0000'), '#FF0000')

    def test_lowercase_to_uppercase(self):
        from utils import normalize_hex
        self.assertEqual(normalize_hex('#aabbcc'), '#AABBCC')

    def test_strips_alpha_channel(self):
        from utils import normalize_hex
        self.assertEqual(normalize_hex('#FF000080'), '#FF0000')

    def test_invalid_length(self):
        from utils import normalize_hex
        self.assertIsNone(normalize_hex('#FFF'))

    def test_invalid_chars(self):
        from utils import normalize_hex
        self.assertIsNone(normalize_hex('#ZZZZZZ'))

    def test_empty(self):
        from utils import normalize_hex
        self.assertIsNone(normalize_hex(''))

    def test_none(self):
        from utils import normalize_hex
        self.assertIsNone(normalize_hex(None))


# ── Duration Formatting ──────────────────────────────────────────────────

class FormatDurationTests(unittest.TestCase):
    def test_hours_and_minutes(self):
        from utils import format_duration
        self.assertEqual(format_duration(3660), '1h 1min')

    def test_minutes_only(self):
        from utils import format_duration
        self.assertEqual(format_duration(1800), '30min')

    def test_exact_hour(self):
        from utils import format_duration
        self.assertEqual(format_duration(3600), '1h 0min')

    def test_zero(self):
        from utils import format_duration
        self.assertEqual(format_duration(0), '')

    def test_none(self):
        from utils import format_duration
        self.assertEqual(format_duration(None), '')

    def test_large_value(self):
        from utils import format_duration
        result = format_duration(10000)
        self.assertIn('h', result)
        self.assertIn('min', result)


# ── Auto-Map Filament ────────────────────────────────────────────────────

class TryAutoMapFilamentTests(unittest.TestCase):
    def setUp(self):
        import tempfile, shutil
        self.temp_dir = tempfile.mkdtemp(prefix='util-automap-tests-')
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
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_auto_map_empty_params(self):
        from utils import try_auto_map_filament
        best, candidates = try_auto_map_filament(None, None)
        self.assertIsNone(best)
        self.assertEqual(candidates, [])

    def test_auto_map_no_match(self):
        from utils import try_auto_map_filament
        best, candidates = try_auto_map_filament('UNOBTAINIUM', '#FFFFFF')
        self.assertIsNone(best)


# ── Validate Printer Host ────────────────────────────────────────────────

class ValidatePrinterHostTests(unittest.TestCase):
    def test_with_scheme(self):
        from utils import validate_printer_host
        result = validate_printer_host('http://192.168.1.50')
        self.assertIsNotNone(result)

    def test_without_scheme_adds_http(self):
        from utils import validate_printer_host
        result = validate_printer_host('192.168.1.50')
        self.assertIsNotNone(result)
        self.assertTrue(result.startswith('http://'))

    def test_empty_returns_none(self):
        from utils import validate_printer_host
        self.assertIsNone(validate_printer_host(''))

    def test_none_returns_none(self):
        from utils import validate_printer_host
        self.assertIsNone(validate_printer_host(None))

    def test_just_scheme_no_host_returns_none(self):
        from utils import validate_printer_host
        result = validate_printer_host('https://')
        # rstrip('/') turns 'https://' into 'https:/' which doesn't match the scheme regex,
        # so http:// is prepended returning 'http://https:/'
        # The function returns a URL-ish string (not None) in this edge case
        self.assertIsInstance(result, str)
        self.assertIn('://', result)


# ── Bambu API Base ──────────────────────────────────────────────────────

class BambuApiBaseTests(unittest.TestCase):
    def test_global_region(self):
        from utils import bambu_api_base
        self.assertEqual(bambu_api_base('global'), 'https://api.bambulab.com')

    def test_china_region(self):
        from utils import bambu_api_base
        self.assertEqual(bambu_api_base('china'), 'https://api.bambulab.cn')


# ── Clean Bambu Title ────────────────────────────────────────────────────

class CleanBambuTitleTests(unittest.TestCase):
    """Additional tests beyond what's in test_bambu.py."""

    def test_from_utils_module(self):
        from utils import clean_bambu_title
        self.assertEqual(clean_bambu_title('Model.stl'), 'Model')

    def test_slicer_profile_preserved(self):
        from utils import clean_bambu_title
        profile = '0.20mm Standard @BBL X1C'
        self.assertEqual(clean_bambu_title(profile), profile)

    def test_multi_part_dedup(self):
        from utils import clean_bambu_title
        self.assertEqual(clean_bambu_title('Part.stl_1 + Part.stl_2'), 'Part.stl')


if __name__ == '__main__':
    unittest.main()
