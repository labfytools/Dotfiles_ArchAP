"""Contrats locaux du gestionnaire wallpaper, sans recharger la session réelle."""
import importlib.util
import fcntl
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from PIL import Image


SOURCE = Path(__file__).resolve().parents[1] / 'bin/.local/bin/wallpaper-manager.py'
SPEC = importlib.util.spec_from_file_location('wallpaper_manager', SOURCE)
manager = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(manager)


class WallpaperManagerTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.patchers = [
            mock.patch.object(manager, 'CACHE', self.root / 'cache'),
            mock.patch.object(manager, 'ALIASES', self.root / 'aliases'),
            mock.patch.object(manager, 'PREFERENCES', self.root / 'config/preferences.json'),
            mock.patch.object(manager, 'STATE', self.root / 'state/effective.json'),
            mock.patch.object(manager, 'GENERATED', self.root / 'sway/generated/wallpaper.conf'),
            mock.patch.object(manager, 'SWAY', self.root / 'sway'),
        ]
        for patcher in self.patchers:
            patcher.start()
        self.image = self.root / "fond d'écran (été).png"
        Image.new('RGB', (640, 360), 'blue').save(self.image)

    def tearDown(self):
        for patcher in reversed(self.patchers):
            patcher.stop()
        self.temp.cleanup()

    def test_scan_thumbnail_and_cache_key(self):
        bad = self.root / 'cassé.png'
        bad.write_text('pas une image')
        (self.root / 'notes.json').write_text('{}')
        link = self.root / 'lien.png'
        link.symlink_to(self.image)
        result = manager.scan(self.root, 0)
        self.assertEqual({x['filename'] for x in result['items']}, {self.image.name, link.name})
        self.assertEqual(len({x['thumbnail'] for x in result['items']}), 1)
        meta = manager.validate_image(self.image)
        with Image.open(Path(manager.thumbnail(meta).removeprefix('file://'))) as thumb:
            self.assertEqual(thumb.size, (320, 180))
            self.assertEqual(thumb.format, 'PNG')
        key = manager.cache_key(meta)
        meta['mtime'] += 1
        self.assertNotEqual(key, manager.cache_key(meta))

    def test_invalid_inputs_and_directory_uri(self):
        for path in (self.root / 'absent.png', self.root, self.root / 'texte.png'):
            if path.name == 'texte.png': path.write_text('invalide')
            with self.assertRaises((ValueError, OSError)):
                manager.validate_image(path)
        chosen = manager.set_directory(self.root.as_uri())
        self.assertEqual(chosen['wallpaperDirectory'], str(self.root))
        self.assertEqual(json.loads(manager.PREFERENCES.read_text())['version'], 1)

    def test_atomic_replace_keeps_old_file_on_write_failure(self):
        target = self.root / 'atomic.txt'
        target.write_bytes(b'ancien')
        with mock.patch.object(manager.os, 'replace', side_effect=OSError('échec')):
            with self.assertRaises(OSError):
                manager.atomic_write(target, b'nouveau')
        self.assertEqual(target.read_bytes(), b'ancien')

    def test_safe_alias_and_sway_syntax(self):
        meta = manager.validate_image(self.image)
        alias = manager.safe_alias(meta)
        self.assertEqual(Path(alias).resolve(), self.image.resolve())
        self.assertNotIn('é', alias)
        self.assertNotIn(' ', alias)
        content = manager.render_wallpaper(alias).decode()
        self.assertIn(alias, content)
        self.assertNotIn(str(self.image), content)
        with self.assertRaises(ValueError):
            manager.render_wallpaper(str(self.image))

    def test_validate_checks_sway_stderr_even_with_zero_exit(self):
        completed = mock.Mock(returncode=0, stderr='Error(s) loading config!', stdout='')
        with mock.patch.object(manager.subprocess, 'run', return_value=completed):
            with self.assertRaises(RuntimeError):
                manager.command('sway', '--validate')

    def test_simultaneous_apply_is_rejected_before_writing(self):
        manager.STATE.parent.mkdir(parents=True)
        lock_path = manager.STATE.parent / 'wallpaper.lock'
        with open(lock_path, 'a+b') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaises(BlockingIOError):
                manager.apply(str(self.image))
        self.assertFalse(manager.GENERATED.exists())

    def test_interrupted_thumbnail_is_not_published(self):
        meta = manager.validate_image(self.image)
        target = manager.CACHE / (manager.cache_key(meta) + '.png')
        with mock.patch.object(manager.os, 'replace', side_effect=OSError('interrompu')):
            with self.assertRaises(OSError):
                manager.thumbnail(meta)
        self.assertFalse(target.exists())
        self.assertEqual(list(manager.CACHE.glob('.thumbnail-*')), [])

    def test_reconcile_missing_image_uses_versioned_default(self):
        manager.write_json(manager.STATE, {'version': 2,
                                           'effectiveWallpaper': str(self.root / 'gone.png')})
        with mock.patch.object(manager, 'apply', return_value={'effectiveWallpaper': str(manager.DEFAULT)}) as apply:
            result = manager.reconcile()
        apply.assert_called_once_with(str(manager.DEFAULT))
        self.assertEqual(result['recoveredFromMissing'], str(self.root / 'gone.png'))

    def test_apply_preserves_theme_and_rolls_back_on_failure(self):
        old = {'version': 1, 'effectiveFlavor': 'mocha', 'effectiveAccent': 'lavender',
               'effectiveDark': True, 'effectiveHighContrast': False, 'revision': 8}
        manager.write_json(manager.STATE, old)
        manager.atomic_write(manager.GENERATED, b'ancien')
        with mock.patch.object(manager, 'command') as command, \
             mock.patch.object(manager, 'swaybg_matches', return_value=True):
            result = manager.apply(str(self.image))
        self.assertEqual(result['revision'], 9)
        state = manager.read_json(manager.STATE)
        self.assertEqual(state['effectiveFlavor'], 'mocha')
        self.assertEqual(state['effectiveAccent'], 'lavender')
        self.assertEqual(state['version'], 2)
        self.assertIn(b'set $wallpaper ', manager.GENERATED.read_bytes())
        self.assertEqual(command.call_count, 2)
        with mock.patch.object(manager, 'command', side_effect=[RuntimeError('validate'), None]):
            with self.assertRaises(RuntimeError):
                manager.apply(str(self.image))
        self.assertEqual(manager.read_json(manager.STATE), state)
        self.assertIn(b'set $wallpaper ', manager.GENERATED.read_bytes())


if __name__ == '__main__':
    unittest.main()
