import unittest
from unittest.mock import Mock, patch

from utils import fetch_link_metadata, is_safe_external_url, parse_sync_status


class SafeUrlTests(unittest.TestCase):
    def test_rejects_localhost_and_loopback(self):
        self.assertFalse(is_safe_external_url('http://localhost:5000/test'))
        self.assertFalse(is_safe_external_url('http://127.0.0.1/test'))

    @patch('utils.socket.getaddrinfo')
    def test_accepts_public_http_url(self, mock_getaddrinfo):
        mock_getaddrinfo.return_value = [(None, None, None, None, ('93.184.216.34', 80))]
        self.assertTrue(is_safe_external_url('https://example.com/page'))


class LinkPreviewTests(unittest.TestCase):
    @patch('utils.requests.get')
    @patch('utils.socket.getaddrinfo')
    def test_fetch_link_metadata_uses_fallback_meta_and_resolves_relative_image(self, mock_getaddrinfo, mock_get):
        mock_getaddrinfo.return_value = [(None, None, None, None, ('93.184.216.34', 443))]
        mock_get.return_value = Mock(
            status_code=200,
            headers={'Content-Type': 'text/html; charset=utf-8'},
            text=(
                '<html><head>'
                '<title>Example Title</title>'
                '<meta name="description" content="Example description">'
                '<meta name="twitter:image" content="/images/preview.png">'
                '</head><body></body></html>'
            ),
        )

        meta = fetch_link_metadata('https://example.com/article')

        self.assertEqual(meta['og_title'], 'Example Title')
        self.assertEqual(meta['og_description'], 'Example description')
        self.assertEqual(meta['og_image'], 'https://example.com/images/preview.png')
        self.assertEqual(meta['domain'], 'example.com')

    @patch('utils.requests.get')
    @patch('utils.socket.getaddrinfo')
    def test_fetch_link_metadata_stops_on_redirect_to_loopback(self, mock_getaddrinfo, mock_get):
        mock_getaddrinfo.return_value = [(None, None, None, None, ('93.184.216.34', 443))]
        mock_get.return_value = Mock(
            status_code=302,
            headers={'Location': 'http://127.0.0.1/internal'},
            text='',
        )

        meta = fetch_link_metadata('https://example.com/article')

        self.assertIsNone(meta['og_title'])
        self.assertIsNone(meta['og_image'])
        self.assertEqual(mock_get.call_count, 1)

    @patch('utils.requests.get')
    @patch('utils.socket.getaddrinfo')
    def test_fetch_link_metadata_reads_json_ld_preview_data(self, mock_getaddrinfo, mock_get):
        mock_getaddrinfo.return_value = [(None, None, None, None, ('93.184.216.34', 443))]
        mock_get.return_value = Mock(
            status_code=200,
            headers={'Content-Type': 'text/html; charset=utf-8'},
            text=(
                '<html><head>'
                '<script type="application/ld+json">'
                '{"@context":"https://schema.org","name":"MakerWorld Axolotl",'
                '"description":"Articulated axolotl model",'
                '"image":["/assets/axolotl-cover.webp"]}'
                '</script>'
                '</head><body></body></html>'
            ),
        )

        meta = fetch_link_metadata('https://makerworld.com/en/models/989796-articulated-axolotl-multicolor')

        self.assertEqual(meta['og_title'], 'MakerWorld Axolotl')
        self.assertEqual(meta['og_description'], 'Articulated axolotl model')
        self.assertEqual(meta['og_image'], 'https://makerworld.com/assets/axolotl-cover.webp')

    @patch('utils.requests.get')
    @patch('utils.socket.getaddrinfo')
    def test_fetch_link_metadata_uses_reader_fallback_for_blocked_makerworld(self, mock_getaddrinfo, mock_get):
        # Reader fallback is opt-in — mock get_settings to enable it
        with patch('utils.get_settings') as mock_settings:
            mock_settings.return_value = Mock(link_preview_reader_enabled=True)
        with patch('utils.get_settings') as mock_settings:
            mock_settings.return_value = Mock(link_preview_reader_enabled=True)
            mock_getaddrinfo.return_value = [(None, None, None, None, ('93.184.216.34', 443))]
            mock_get.side_effect = [
                Mock(
                    status_code=403,
                    headers={'Content-Type': 'text/html; charset=utf-8'},
                    text='<title>Just a moment...</title>',
                ),
                Mock(
                    status_code=200,
                    headers={'Content-Type': 'text/plain; charset=utf-8'},
                    text=(
                        'Title: Articulated Axolotl (Multicolor) - Free 3D Print Model - MakerWorld\n\n'
                        'URL Source: https://makerworld.com/en/models/989796-articulated-axolotl-multicolor\n\n'
                        'Markdown Content:\n'
                        '![Image 1](https://makerworld.bblmw.com/makerworld/model/sample/design/cover.png)\n\n'
                        'Articulated axolotl multicolor by Molodos'
                    ),
                ),
            ]

            meta = fetch_link_metadata('https://makerworld.com/en/models/989796-articulated-axolotl-multicolor#profileId-1871919')

            self.assertEqual(meta['og_title'], 'Articulated Axolotl (Multicolor) - Free 3D Print Model - MakerWorld')
            self.assertEqual(meta['og_image'], 'https://makerworld.bblmw.com/makerworld/model/sample/design/cover.png')
            self.assertEqual(meta['og_description'], 'Articulated axolotl multicolor by Molodos')
            reader_call_url = mock_get.call_args_list[1].args[0]
            self.assertNotIn('#profileId-1871919', reader_call_url)


class SyncStatusParsingTests(unittest.TestCase):
    def test_parse_sync_status_handles_error_prefix(self):
        parsed = parse_sync_status('error: Cannot reach printer')

        self.assertFalse(parsed['ok'])
        self.assertEqual(parsed['error'], 'Cannot reach printer')
        self.assertEqual(parsed['added'], 0)

    def test_parse_sync_status_handles_json_payload(self):
        parsed = parse_sync_status('{"added":2,"updated":1,"skipped":4}')

        self.assertTrue(parsed['ok'])
        self.assertEqual(parsed['added'], 2)
        self.assertEqual(parsed['updated'], 1)
        self.assertEqual(parsed['skipped'], 4)
