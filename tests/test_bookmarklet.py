import os
import sys
import unittest
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote

os.environ['GEMINI_API_KEY'] = 'unit-test-not-a-key'
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import main
from fastapi.testclient import TestClient
from bookmarklet_routes import HEADERS


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.bookmarks = []
        self.external_resources = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'a' and attrs.get('href', '').startswith('javascript:'):
            self.bookmarks.append(attrs)
        if tag in ('script', 'link', 'iframe', 'img'):
            self.external_resources.append(attrs)


class PublicEndpoints(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(main.app)
        self.addCleanup(self.client.close)

    def test_install_links_and_public_content(self):
        response = self.client.get('/install')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers['content-type'], 'text/html; charset=utf-8')
        parser = Links()
        parser.feed(response.text)
        self.assertEqual(len(parser.bookmarks), 2)
        self.assertFalse(parser.external_resources)
        for link in parser.bookmarks:
            self.assertEqual(link['draggable'], 'true')
            self.assertTrue(unquote(link['href']).startswith('javascript:void '))
        self.assertIn('🎤 q — автономная', response.text)
        self.assertIn('🎤 q — автообновление', response.text)
        self.assertIn('← qwerty was here', unquote(parser.bookmarks[0]['href']))
        self.assertIn('https://voice-recognision-server-production.up.railway.app/q-runtime.js', unquote(parser.bookmarks[1]['href']))
        for forbidden in ('unit-test-not-a-key', 'GEMINI_API_KEY', 'GEMINI_MODEL', '/Users/admin'):
            self.assertNotIn(forbidden, response.text)

    def test_runtime_is_generated_artifact(self):
        response = self.client.get('/q-runtime.js?qv=123')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.headers['content-type'].startswith('application/javascript'))
        generated = Path(__file__).resolve().parents[1] / 'public/q-runtime.js'
        self.assertEqual(response.content, generated.read_bytes())
        self.assertIn('VoiceMessage', response.text)
        self.assertIn('CircleVideo', response.text)
        self.assertIn('__qInstalled', response.text)
        for forbidden in ('unit-test-not-a-key', 'GEMINI_API_KEY', '/Users/admin'):
            self.assertNotIn(forbidden, response.text)

    def test_headers_cors_and_preflight(self):
        for endpoint in ('/install', '/q-runtime.js'):
            response = self.client.get(endpoint, headers={'Origin':'https://web.gemspace.com'})
            for key, value in HEADERS.items():
                self.assertEqual(response.headers[key], value)
            self.assertEqual(response.headers['access-control-allow-origin'], 'https://web.gemspace.com')
            self.assertNotIn('access-control-allow-credentials', response.headers)
            other = self.client.get(endpoint, headers={'Origin':'https://untrusted.example'})
            self.assertNotIn('access-control-allow-origin', other.headers)
            preflight = self.client.options(endpoint, headers={
                'Origin':'https://web.gemspace.com', 'Access-Control-Request-Method':'GET'})
            self.assertEqual(preflight.status_code, 200)

    def test_no_directory_or_secrets_exposed_and_health_unchanged(self):
        for endpoint in ('/.env', '/public/.env', '/public/', '/test.txt', '/bookmarklet_routes.py'):
            self.assertEqual(self.client.get(endpoint).status_code, 404)
        health = self.client.get('/health')
        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.json()['provider'], 'gemini')
        self.assertEqual(health.json()['model'], main.GEMINI_MODEL)
        self.assertNotIn('content-security-policy', health.headers)


if __name__ == '__main__':
    unittest.main()
