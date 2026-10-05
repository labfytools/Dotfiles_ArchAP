"""Contrats locaux du gestionnaire wallpaper, sans recharger la session réelle."""
import importlib.util
import fcntl
import json
from pathlib import Path
import tempfile
import unittest
import sys
from unittest import mock

from PIL import Image


SOURCE = Path(__file__).resolve().parents[1] / 'bin/.local/bin/wallpaper-manager.py'
sys.path.insert(0, str(SOURCE.parent))
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
            mock.patch.object(manager, 'GENERATED_THEME', self.root / 'sway/generated/theme.conf'),
            mock.patch.object(manager, 'SWAY', self.root / 'sway'),
            mock.patch.object(manager, 'refresh_opacity'),
        ]
        for patcher in self.patchers:
            patcher.start()
        # Les tests de transaction utilisent un service simulé : aucune unité
        # systemd réelle ne doit être touchée depuis des fixtures temporaires.
        self.night = mock.Mock()
        self.night.normalized.side_effect = lambda pref: pref
        self.night_patch = mock.patch.object(manager, 'night_module', return_value=self.night)
        self.night_patch.start()
        self.image = self.root / "fond d'écran (été).png"
        Image.new('RGB', (640, 360), 'blue').save(self.image)

    def tearDown(self):
        self.night_patch.stop()
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
        self.assertEqual(json.loads(manager.PREFERENCES.read_text())['version'], 4)

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
             mock.patch.object(manager, 'swaybg_matches', return_value=True), \
             mock.patch.object(manager, 'publish_live'):
            result = manager.apply(str(self.image))
        self.assertEqual(result['revision'], 9)
        state = manager.read_json(manager.STATE)
        self.assertEqual(state['effectiveFlavor'], 'mocha')
        self.assertEqual(state['effectiveAccent'], 'lavender')
        self.assertEqual(state['version'], 4)
        self.assertIn(b'set $wallpaper ', manager.GENERATED.read_bytes())
        self.assertEqual(command.call_count, 2)
        newer = self.root / 'autre.png'
        Image.new('RGB', (32, 32), 'black').save(newer)
        with mock.patch.object(manager, 'command', side_effect=[RuntimeError('validate'), None]):
            with self.assertRaises(RuntimeError):
                manager.apply(str(newer))
        self.assertEqual(manager.read_json(manager.STATE), state)
        self.assertIn(b'set $wallpaper ', manager.GENERATED.read_bytes())

    def test_manual_wallpaper_does_not_change_theme(self):
        manager.write_json(manager.STATE, {'version': 3, 'effectiveFlavor': 'mocha',
            'effectiveWallpaper': str(self.image), 'wallpaperMtime': 0, 'revision': 3,
            'themeMode': 'manual', 'manualFlavor': 'mocha'})
        bright = self.root / 'clair.png'
        Image.new('RGB', (48, 48), 'white').save(bright)
        with mock.patch.object(manager, 'command'), mock.patch.object(manager, 'publish_live'), \
                mock.patch.object(manager, 'swaybg_matches', return_value=True):
            result = manager.apply(str(bright))
        self.assertEqual(result['effectiveFlavor'], 'mocha')
        self.assertFalse(manager.GENERATED_THEME.exists())
        self.assertEqual(result['revision'], 4)

    def test_auto_activation_and_manual_restoration(self):
        manager.write_json(manager.STATE, {'version': 3, 'effectiveFlavor': 'mocha',
            'effectiveWallpaper': str(self.image), 'revision': 3,
            'themeMode': 'manual', 'manualFlavor': 'mocha'})
        with mock.patch.object(manager, 'command'), mock.patch.object(manager, 'publish_live'):
            automatic = manager.set_theme_mode('wallpaper')
            self.assertEqual(automatic['manualFlavor'], 'mocha')
            self.assertEqual(automatic['effectiveFlavor'], 'mocha')
            restored = manager.set_theme_mode('manual')
        self.assertEqual(restored['effectiveFlavor'], 'mocha')
        self.assertEqual(restored['manualFlavor'], 'mocha')
        self.assertEqual(restored['revision'], 5)

    def test_auto_wallpaper_and_rollback(self):
        manager.write_json(manager.STATE, {'version': 3, 'effectiveFlavor': 'mocha',
            'effectiveWallpaper': str(self.image), 'revision': 5,
            'themeMode': 'wallpaper', 'manualFlavor': 'mocha'})
        bright = self.root / 'clair.png'
        Image.new('RGB', (48, 48), 'white').save(bright)
        with mock.patch.object(manager, 'command'), mock.patch.object(manager, 'publish_live'), \
                mock.patch.object(manager, 'swaybg_matches', return_value=True):
            result = manager.apply(str(bright))
        self.assertEqual(result['effectiveFlavor'], 'latte')
        self.assertFalse(result['effectiveDark'])
        previous_theme = manager.GENERATED_THEME.read_bytes()
        previous_wallpaper = manager.GENERATED.read_bytes()
        previous_state = manager.STATE.read_bytes()
        dark = self.root / 'sombre.png'
        Image.new('RGB', (48, 48), 'black').save(dark)
        with mock.patch.object(manager, 'command', side_effect=[None, RuntimeError('reload'), None]):
            with self.assertRaises(RuntimeError):
                manager.apply(str(dark))
        self.assertEqual(manager.GENERATED_THEME.read_bytes(), previous_theme)
        self.assertEqual(manager.GENERATED.read_bytes(), previous_wallpaper)
        self.assertEqual(manager.STATE.read_bytes(), previous_state)

    def test_schema_two_migration_keeps_previous_fields(self):
        legacy = {'version': 2, 'effectiveFlavor': 'macchiato',
                  'effectiveAccent': 'lavender', 'effectiveDark': True,
                  'effectiveHighContrast': False, 'effectiveMode': 'normal',
                  'effectiveWallpaper': str(self.image), 'revision': 47,
                  'customFutureField': 'conservé'}
        manager.write_json(manager.STATE, legacy)
        manager.write_json(manager.PREFERENCES, {'version': 1,
            'wallpaperDirectory': str(self.root), 'wallpaperMode': 'fill'})
        with mock.patch.object(manager, 'command') as command:
            result = manager.reconcile_state()
        self.assertEqual(result['version'], 4)
        self.assertEqual(result['revision'], 47)
        self.assertEqual(result['customFutureField'], 'conservé')
        self.assertEqual(result['effectiveFlavor'], 'macchiato')
        self.assertEqual(result['themeMode'], 'manual')
        self.assertEqual(result['manualFlavor'], 'macchiato')
        self.assertEqual(result['wallpaperDirectory'], str(self.root))
        self.assertEqual(command.call_count, 2)

    def test_crash_like_reconciliation_uses_effective_state(self):
        manager.write_json(manager.STATE, {'version': 3, 'effectiveFlavor': 'mocha',
            'effectiveWallpaper': str(self.image), 'revision': 6,
            'themeMode': 'manual', 'manualFlavor': 'mocha'})
        manager.write_json(manager.PREFERENCES, {'version': 2,
            'themeMode': 'wallpaper', 'manualFlavor': 'latte',
            'wallpaperDirectory': str(self.root)})
        manager.atomic_write(manager.GENERATED_THEME, b'interrompu')
        manager.atomic_write(manager.GENERATED, b'interrompu')
        with mock.patch.object(manager, 'command') as command:
            result = manager.reconcile_state()
        self.assertEqual(result['revision'], 6)
        self.assertEqual(result['themeMode'], 'manual')
        self.assertEqual(result['manualFlavor'], 'mocha')
        self.assertIn(b'set $base ', manager.GENERATED_THEME.read_bytes())
        self.assertIn(b'set $wallpaper ', manager.GENERATED.read_bytes())
        self.assertEqual(command.call_count, 2)

    def test_auto_analysis_failure_does_not_change_files(self):
        old = {'version': 3, 'effectiveFlavor': 'mocha',
               'effectiveWallpaper': str(self.image), 'revision': 6,
               'themeMode': 'manual', 'manualFlavor': 'mocha'}
        manager.write_json(manager.STATE, old)
        with mock.patch.object(manager, 'analyze_wallpaper', side_effect=ValueError('décodeur')):
            with self.assertRaisesRegex(ValueError, 'Analyse Auto Theme'):
                manager.set_theme_mode('wallpaper')
        self.assertEqual(manager.read_json(manager.STATE), old)
        self.assertFalse(manager.GENERATED_THEME.exists())

    def test_auto_reconcile_restores_missing_analysis_without_revision(self):
        meta = manager.validate_image(self.image)
        manager.write_json(manager.STATE, {'version': 3, 'effectiveFlavor': 'mocha',
            'effectiveWallpaper': str(self.image), 'wallpaperMtime': meta['mtime'],
            'revision': 12, 'themeMode': 'wallpaper', 'manualFlavor': 'latte'})
        with mock.patch.object(manager, 'command'):
            result = manager.reconcile_state()
        self.assertEqual(result['revision'], 12)
        self.assertEqual(result['effectiveFlavor'], 'mocha')
        self.assertEqual(result['manualFlavor'], 'latte')
        self.assertEqual(result['wallpaperAnalysis']['algorithmVersion'], 1)

    def test_sun_priority_and_exact_manual_restoration(self):
        manager.write_json(manager.STATE, {'version': 4, 'effectiveFlavor': 'frappe',
            'effectiveMode': 'normal', 'effectiveWallpaper': str(self.image),
            'themeMode': 'manual', 'manualFlavor': 'frappe', 'revision': 9})
        manager.write_json(manager.PREFERENCES, {'version': 4, 'themeMode': 'manual',
            'manualFlavor': 'frappe', 'nightLightMode': 'off'})
        with mock.patch.object(manager, 'command'), mock.patch.object(manager, 'publish_live'), \
             mock.patch.object(manager, 'refresh_opacity') as opacity:
            light = manager.transaction(sun_mode='on')
            self.assertEqual((light['effectiveFlavor'], light['effectiveMode'], light['revision']),
                             ('latte', 'sun-light', 10))
            self.assertTrue(light['effectiveHighContrast'])
            self.assertFalse(light['effectiveDark'])
            self.assertEqual(light['manualFlavor'], 'frappe')
            dark = manager.transaction(sun_variant='dark')
            self.assertEqual((dark['effectiveFlavor'], dark['effectiveMode']), ('mocha', 'sun-dark'))
            for flavor in ('frappe', 'macchiato', 'mocha'):
                dark = manager.transaction(sun_dark_flavor=flavor)
                self.assertEqual(dark['effectiveFlavor'], flavor)
                self.assertTrue(dark['effectiveDark'])
                self.assertTrue(dark['effectiveHighContrast'])
            normal = manager.transaction(sun_mode='off')
            self.assertEqual((normal['effectiveFlavor'], normal['effectiveMode']), ('frappe', 'normal'))
            self.assertEqual(normal['manualFlavor'], 'frappe')
            self.assertEqual(normal['themeMode'], 'manual')
            self.assertFalse(normal['effectiveHighContrast'])
            self.assertGreaterEqual(opacity.call_count, 3)
        self.night.apply_service.assert_any_call(mock.ANY, True)
        self.night.apply_service.assert_any_call(mock.ANY, False)

    def test_inactive_sun_flavor_preference_does_not_advance_revision(self):
        manager.write_json(manager.STATE, {'version': 4, 'effectiveFlavor': 'mocha',
            'effectiveMode': 'normal', 'effectiveWallpaper': str(self.image),
            'themeMode': 'manual', 'manualFlavor': 'mocha', 'revision': 8})
        with mock.patch.object(manager, 'publish_live'):
            result = manager.transaction(sun_dark_flavor='frappe')
        self.assertEqual(result['revision'], 8)
        self.assertEqual(result['effectiveFlavor'], 'mocha')
        self.assertEqual(result['sunDarkFlavor'], 'frappe')

    def test_sun_rollback_restores_state_files_and_night_service(self):
        manager.write_json(manager.STATE, {'version': 4, 'effectiveFlavor': 'mocha',
            'effectiveMode': 'normal', 'effectiveWallpaper': str(self.image),
            'themeMode': 'manual', 'manualFlavor': 'mocha', 'revision': 4})
        manager.write_json(manager.PREFERENCES, {'version': 4, 'themeMode': 'manual',
            'manualFlavor': 'mocha', 'nightLightMode': 'off'})
        before = (manager.STATE.read_bytes(), manager.PREFERENCES.read_bytes())
        with mock.patch.object(manager, 'command'), mock.patch.object(manager, 'refresh_opacity'), \
             mock.patch.object(manager, 'publish_live', side_effect=RuntimeError('IPC')):
            with self.assertRaisesRegex(RuntimeError, 'IPC'):
                manager.transaction(sun_mode='on')
        self.assertEqual((manager.STATE.read_bytes(), manager.PREFERENCES.read_bytes()), before)
        self.assertEqual(self.night.apply_service.call_count, 2)

    def test_no_location_fresh_preferences_enable_and_disable_sun(self):
        manager.write_json(manager.STATE, {'version': 4, 'effectiveFlavor': 'mocha',
            'effectiveMode': 'normal', 'effectiveWallpaper': str(self.image),
            'themeMode': 'manual', 'manualFlavor': 'mocha', 'revision': 0})
        with mock.patch.object(manager, 'command'), mock.patch.object(manager, 'publish_live'), \
             mock.patch.object(manager, 'refresh_opacity'):
            self.assertEqual(manager.transaction(sun_mode='on')['effectiveNightLightMode'], 'off')
            self.assertEqual(manager.transaction(sun_mode='off')['effectiveFlavor'], 'mocha')


if __name__ == '__main__':
    unittest.main()
