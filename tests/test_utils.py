import unittest
from unittest.mock import Mock, patch

from utils import fetch_link_metadata, is_safe_external_url


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
