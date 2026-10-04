"""Contrats du générateur : validation et remplacement non destructif."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / 'bin/.local/bin/generate-appearance.py'
spec = importlib.util.spec_from_file_location('appearance_generator', SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class AppearanceGeneratorTest(unittest.TestCase):
    def test_all_flavors_and_valid_accent(self):
        palette = module.palette_data()
        for flavor in palette:
            result = module.render(flavor, 'lavender')
            self.assertIn(f'set $accent {palette[flavor]["lavender"]}', result)
            self.assertIn(f'set $base {palette[flavor]["base"]}', result)
        self.assertIn('set $accent ' + palette['mocha']['mauve'],
                      module.render('mocha', 'mauve'))

    def test_invalid_inputs(self):
        for flavor, accent, profile in [('invalid', 'lavender', 'default'),
                                        ('mocha', 'invalid', 'default'),
                                        ('mocha', 'lavender', 'invalid')]:
            with self.subTest(flavor=flavor, accent=accent, profile=profile):
                with self.assertRaises(ValueError):
                    module.render(flavor, accent, profile)

    def test_atomic_replace_and_failed_replace(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / 'theme.conf'
            output.write_bytes(b'old\n')
            module.atomic_write(output, b'new\n')
            self.assertEqual(output.read_bytes(), b'new\n')
            with patch.object(module.os, 'replace', side_effect=OSError('échec')):
                with self.assertRaises(OSError):
                    module.atomic_write(output, b'broken\n')
            self.assertEqual(output.read_bytes(), b'new\n')
            self.assertFalse((Path(folder) / 'theme.conf.tmp').exists())


if __name__ == '__main__':
    unittest.main()
