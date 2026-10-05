"""Contrats de validation et publication du synchroniseur Appearance."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock


SOURCE = Path(__file__).resolve().parents[1] / 'bin/.local/bin/appearance-app-sync.py'
spec = importlib.util.spec_from_file_location('appearance_app_sync', SOURCE)
sync = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync)


class SyncTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.state = self.root / 'effective.json'
        self.result = self.root / 'last-applied.json'
        self.palette = sync.PALETTE
        self.value = {'effectiveFlavor': 'mocha', 'effectiveAccent': 'lavender',
                      'effectiveDark': True, 'effectiveHighContrast': False,
                      'effectiveMode': 'normal', 'revision': 4,
                      'latitude': 48.0, 'savedLocations': ['secret']}
        self.write()

    def write(self):
        self.state.write_text(json.dumps(self.value), encoding='utf-8')

    def test_projection_excludes_location(self):
        state = sync.read_effective(self.state)
        self.assertEqual(set(state), {'effectiveFlavor', 'effectiveAccent',
                                     'effectiveDark', 'effectiveHighContrast',
                                     'effectiveMode', 'revision'})

    def test_bad_state_never_runs_adapter_or_publishes(self):
        for mutation in ({'revision': None}, {'effectiveFlavor': 'invalid'},
                         {'effectiveDark': False}, {'effectiveMode': 'sun-light'}):
            with self.subTest(mutation=mutation):
                self.value.update(mutation)
                self.write()
                with mock.patch.object(sync, 'ADAPTERS', {'gtk': mock.Mock()}) as adapters:
                    with self.assertRaises(ValueError):
                        sync.reconcile(self.state, self.result, self.palette)
                    adapters['gtk'].assert_not_called()
                self.assertFalse(self.result.exists())
                self.value = {'effectiveFlavor': 'mocha', 'effectiveAccent': 'lavender',
                              'effectiveDark': True, 'effectiveHighContrast': False,
                              'effectiveMode': 'normal', 'revision': 4}
        del self.value['revision']
        self.write()
        with self.assertRaises(KeyError):
            sync.reconcile(self.state, self.result, self.palette)
        self.assertFalse(self.result.exists())

    def test_partial_failure_and_privacy(self):
        def failed(*args):
            raise OSError('indisponible')
        with mock.patch.object(sync, 'ADAPTERS', {'gtk': failed,
                                                   'qt': lambda *_: {'status': 'ok'}}):
            result = sync.reconcile(self.state, self.result, self.palette)
        self.assertEqual(result['adapters']['gtk']['status'], 'error')
        self.assertEqual(result['adapters']['qt']['status'], 'ok')
        content = self.result.read_text()
        self.assertNotIn('latitude', content)
        self.assertNotIn('secret', content)

    def test_new_revision_wins_during_adapter_execution(self):
        seen = []
        def mutate_once(state, colors):
            seen.append(state['revision'])
            if len(seen) == 1:
                self.value['revision'] = 5
                self.write()
            return {'status': 'ok'}
        with mock.patch.object(sync, 'ADAPTERS', {'gtk': mutate_once}):
            result = sync.reconcile(self.state, self.result, self.palette)
        self.assertEqual(seen, [4, 5])
        self.assertEqual(result['revision'], 5)

    def test_missing_palette_does_not_replace_config(self):
        with self.assertRaises(FileNotFoundError):
            sync.reconcile(self.state, self.result, self.root / 'missing.json')
        self.assertFalse(self.result.exists())

    def test_qt_kitty_palette_is_shared(self):
        p = sync.read_palette()['latte']
        self.assertIn(p['base'].encode(), sync.kitty_theme(p, 'lavender', True))
        self.assertIn(('#ff' + p['base'][1:]).encode(), sync.qt_palette(p, 'lavender'))
        self.assertEqual(len(sync.qt_palette(p, 'lavender').splitlines()), 4)

    def test_gtk_adapter_uses_effective_dark(self):
        self.value.update(effectiveFlavor='latte', effectiveDark=False)
        with mock.patch.object(sync, 'run') as run:
            result = sync.gtk_adapter(self.value, sync.read_palette())
        self.assertEqual(result['colorScheme'], 'prefer-light')
        self.assertEqual(result['theme'], 'Adwaita')
        self.assertEqual(run.call_count, 2)

    def test_qt_adapter_writes_both_versions(self):
        for version in ('qt5ct', 'qt6ct'):
            config = self.root / version / (version + '.conf')
            config.parent.mkdir(parents=True)
            config.write_text('[Appearance]\ncolor_scheme_path=/old\nstyle=Fusion\n')
        with mock.patch.object(sync, 'CONFIG', self.root):
            sync.qt_adapter(self.value, sync.read_palette())
        for version in ('qt5ct', 'qt6ct'):
            self.assertTrue((self.root / version / 'colors/labfy-appearance.conf').is_file())
            content = (self.root / version / (version + '.conf')).read_text()
            self.assertIn('style=Fusion', content)
            self.assertIn('labfy-appearance.conf', content)

    def test_kitty_adapter_signals_only_verified_process(self):
        kitty = self.root / 'kitty'
        kitty.mkdir()
        (kitty / 'kitty.conf').write_text('include generated-appearance.conf\n')
        with mock.patch.object(sync, 'CONFIG', self.root), \
             mock.patch.object(sync.os, 'scandir', return_value=[]):
            result = sync.kitty_adapter(self.value, sync.read_palette())
        self.assertEqual(result['instances'], 0)
        self.assertIn('foreground', (kitty / 'generated-appearance.conf').read_text())

    def test_nvim_contract_reports_revision(self):
        self.assertEqual(sync.nvim_adapter(self.value, {})['revision'], 4)

    def test_firefox_profile_is_read_only_and_reports_migration(self):
        firefox = self.root / '.mozilla/firefox'
        firefox.mkdir(parents=True)
        (firefox / 'profiles.ini').write_text('[InstallABCD]\nDefault=profile\n')
        profile = firefox / 'profile'
        profile.mkdir()
        prefs = profile / 'prefs.js'
        prefs.write_text('user_pref("extensions.activeThemeID", "firefox-compact-dark@mozilla.org");\n'
                         'user_pref("layout.css.prefers-color-scheme.content-override", 1);\n')
        before = prefs.read_bytes()
        with mock.patch.object(sync.Path, 'home', return_value=self.root):
            result = sync.firefox_adapter(self.value, {})
        self.assertEqual(result['status'], 'unsupported')
        self.assertEqual(result['contentOverride'], 1)
        self.assertEqual(prefs.read_bytes(), before)

    def test_firefox_proton_dual_palette_follows_system_without_profile_write(self):
        firefox = self.root / '.mozilla/firefox'
        firefox.mkdir(parents=True)
        (firefox / 'profiles.ini').write_text('[InstallABCD]\nDefault=profile\n')
        profile = firefox / 'profile'
        profile.mkdir()
        prefs = profile / 'prefs.js'
        prefs.write_text('user_pref("extensions.activeThemeID", "proton-theme@mozilla.org");\n')
        before = prefs.read_bytes()
        with mock.patch.object(sync.Path, 'home', return_value=self.root):
            result = sync.firefox_adapter(self.value, {})
        self.assertEqual(result['status'], 'ok')
        self.assertEqual(result['integration'], 'system')
        self.assertEqual(result['lightDark'], 'supported')
        self.assertIs(result['profileWrite'], False)
        self.assertEqual(prefs.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
