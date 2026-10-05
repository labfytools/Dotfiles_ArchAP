"""Propriétés de l'analyse locale, sur des images synthétiques temporaires."""
import sys
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'bin/.local/bin'))
import wallpaper_analysis as analysis
import importlib.util

source = Path(__file__).resolve().parents[1] / 'bin/.local/bin/wallpaper-manager.py'
spec = importlib.util.spec_from_file_location('wallpaper_manager_analysis_tests', source)
manager = importlib.util.module_from_spec(spec)
spec.loader.exec_module(manager)


class WallpaperAnalysisTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.cache_patch = mock.patch.object(analysis, 'CACHE', self.root / 'cache')
        self.cache_patch.start()

    def tearDown(self):
        self.cache_patch.stop()
        self.temp.cleanup()

    def result(self, name, image):
        path = self.root / name
        image.save(path)
        return analysis.analyze(manager.validate_image(path))

    def test_linear_luminance_and_four_flavors(self):
        self.assertAlmostEqual(analysis.linear_channel(0), 0)
        self.assertAlmostEqual(analysis.linear_channel(1), 1)
        self.assertAlmostEqual(analysis.linear_channel(128 / 255), 0.21586, places=4)
        colors = [(0, 'mocha'), (40, 'mocha'), (80, 'mocha'),
                  (128, 'macchiato'), (192, 'frappe'),
                  (224, 'latte'), (255, 'latte')]
        for value, flavor in colors:
            with self.subTest(value=value):
                result = self.result(f'gris {value} été.png', Image.new('RGB', (100, 80), (value, value, value)))
                self.assertEqual(result['flavor'], flavor)
                self.assertAlmostEqual(result['mean'], result['median'], places=6)
                self.assertLessEqual(result['p10'], result['p90'])

    def test_bimodal_weight_and_gradient(self):
        split = Image.new('RGB', (100, 40), 'black')
        split.paste('white', (50, 0, 100, 40))
        result = self.result('moitié noir blanc.png', split)
        self.assertEqual(result['flavor'], 'frappe')
        self.assertGreater(result['p90'], 0.9)
        self.assertLess(result['p10'], 0.1)
        dark = Image.new('RGB', (100, 40), 'black')
        dark.paste('white', (80, 0, 100, 40))
        self.assertEqual(self.result('majorité sombre.png', dark)['flavor'], 'mocha')
        bright = Image.new('RGB', (100, 40), 'white')
        bright.paste('black', (0, 0, 20, 40))
        self.assertEqual(self.result('majorité claire.png', bright)['flavor'], 'latte')
        gradient = Image.new('RGB', (256, 8))
        gradient.putdata([(x, x, x) for _ in range(8) for x in range(256)])
        graded = self.result('gradient.png', gradient)
        self.assertEqual(graded['flavor'], 'macchiato')
        self.assertLess(graded['p10'], graded['median'])
        self.assertLess(graded['median'], graded['p90'])

    def test_cache_invalidated_by_content_and_version(self):
        path = self.root / 'image.png'
        Image.new('RGB', (20, 20), 'black').save(path)
        first = manager.validate_image(path)
        self.assertEqual(analysis.analyze(first)['flavor'], 'mocha')
        key = analysis.cache_key(first)
        Image.new('RGB', (25, 25), 'white').save(path)
        second = manager.validate_image(path)
        self.assertNotEqual(key, analysis.cache_key(second))
        self.assertEqual(analysis.analyze(second)['flavor'], 'latte')
        second_key = analysis.cache_key(second)
        with mock.patch.object(analysis, 'ALGORITHM_VERSION', analysis.ALGORITHM_VERSION + 1):
            self.assertNotEqual(analysis.cache_key(second), second_key)

    def test_invalid_image_rejected(self):
        path = self.root / 'faux.png'
        path.write_text('pas une image')
        with self.assertRaises(Exception):
            manager.validate_image(path)


if __name__ == '__main__':
    unittest.main()
