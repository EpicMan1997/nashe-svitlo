"""Android installability contract, intentionally static with no browser mock."""
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / 'site'

class AndroidPwaTests(unittest.TestCase):
    def test_android_manifest_and_install_icons(self):
        manifest = json.loads((SITE / 'manifest.webmanifest').read_text(encoding='utf-8'))
        self.assertEqual(manifest['name'], 'Наше Світло')
        self.assertEqual(manifest['display'], 'standalone')
        self.assertEqual(manifest['start_url'], './')
        self.assertEqual(manifest['scope'], './')
        self.assertEqual(manifest['id'], './')
        icon_sizes = {icon['sizes']: icon for icon in manifest['icons']}
        for size in ('192x192', '512x512'):
            icon = icon_sizes[size]
            self.assertEqual(icon['type'], 'image/svg+xml')
            svg = (SITE / icon['src']).read_text(encoding='utf-8')
            pixel = size.split('x')[0]
            self.assertIn(f'width="{pixel}" height="{pixel}"', svg)
            self.assertIn('viewBox="0 0 64 64"', svg)
        self.assertIn('180x180', icon_sizes)
        self.assertEqual(icon_sizes['180x180']['type'], 'image/png')

    def test_manifest_and_service_worker_are_relative_to_renamed_site(self):
        html = (SITE / 'index.html').read_text(encoding='utf-8')
        worker = (SITE / 'sw.js').read_text(encoding='utf-8')
        self.assertIn('<link rel="manifest" href="./manifest.webmanifest">', html)
        self.assertIn("navigator.serviceWorker.register('./sw.js'", html)
        self.assertIn('nashe-svitlo-static-v55', worker)
        self.assertIn('"./pwa-icon-192.svg"', worker)
        self.assertIn('"./pwa-icon-512.svg"', worker)
        self.assertNotIn('svitlo-dubechnya', html)
        self.assertNotIn('svitlo-dubechnya', worker)
