"""Contrats Night Light sur préférences et service simulés, sans localisation réelle."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

SOURCE = Path(__file__).resolve().parents[1] / 'bin/.local/bin/night-light-manager.py'
SPEC = importlib.util.spec_from_file_location('night_light_manager', SOURCE)
night = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(night)


class NightLightTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.patchers = [mock.patch.object(night, 'CONFIG', self.root / 'preferences.json'),
                         mock.patch.object(night, 'STATE', self.root / 'effective.json'),
                         mock.patch.object(night, 'LOCK', self.root / 'wallpaper.lock')]
        for patcher in self.patchers:
            patcher.start()
        self.pref = {'version': 2, 'themeMode': 'manual', 'manualFlavor': 'mocha',
                     'wallpaperDirectory': '/fixture', 'nightLightMode': 'auto',
                     'nightTemperature': 3000, 'dayTemperature': 6500,
                     'scheduleType': 'solar', 'latitude': '12.5', 'longitude': '-8.25'}
        night.atomic_json(night.CONFIG, self.pref)
        night.atomic_json(night.STATE, {'effectiveFlavor': 'mocha', 'revision': 5})

    def tearDown(self):
        for patcher in reversed(self.patchers):
            patcher.stop()
        self.temp.cleanup()

    def test_migration_preserves_other_preferences(self):
        result = night.normalized(self.pref)
        self.assertEqual(result['version'], 3)
        self.assertEqual(result['themeMode'], 'manual')
        self.assertEqual(result['wallpaperDirectory'], '/fixture')

    def test_auto_argv_uses_solar_and_baseline(self):
        self.assertEqual(night.argv(self.pref), ['/usr/bin/wlsunset', '-l', '12.5', '-L', '-8.25',
                                                '-t', '3000', '-T', '6500'])

    def test_on_argv_uses_manual_schedule_for_force_low(self):
        pref = {**self.pref, 'nightLightMode': 'on'}
        self.assertEqual(night.argv(pref), ['/usr/bin/wlsunset', '-S', '06:00', '-s', '18:00',
                                            '-t', '3000', '-T', '6500'])

    def test_off_has_no_process_argv(self):
        self.assertIsNone(night.argv({**self.pref, 'nightLightMode': 'off'}))

    def test_invalid_mode_and_temperature(self):
        for mode in ('invalid', '', None):
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                night.normalized({**self.pref, 'nightLightMode': mode})
        for value in ('3500', '', None, float('nan'), 2400, 5100, 3550, True):
            with self.subTest(value=value), self.assertRaises(ValueError):
                night.temperature(value)

    def test_fresh_install_has_no_invented_coordinates(self):
        self.assertEqual(night.normalized({})['nightLightMode'], 'off')
        with self.assertRaisesRegex(ValueError, 'Planification à configurer'):
            night.normalized({'nightLightMode': 'auto'})

    def test_atomic_write_keeps_previous_on_replace_failure(self):
        before = night.CONFIG.read_bytes()
        with mock.patch.object(night.os, 'replace', side_effect=OSError('échec')):
            with self.assertRaises(OSError):
                night.atomic_json(night.CONFIG, {'bad': True})
        self.assertEqual(night.CONFIG.read_bytes(), before)

    def test_change_rolls_back_preferences_and_state(self):
        before_pref = night.CONFIG.read_bytes()
        before_state = night.STATE.read_bytes()
        with mock.patch.object(night, 'apply_service', side_effect=[RuntimeError('service'), None]) as apply:
            with self.assertRaisesRegex(RuntimeError, 'service'):
                night.change(mode='off')
        self.assertEqual(apply.call_count, 2)
        self.assertEqual(night.CONFIG.read_bytes(), before_pref)
        self.assertEqual(night.STATE.read_bytes(), before_state)

    def test_change_keeps_appearance_fields(self):
        with mock.patch.object(night, 'apply_service'), mock.patch.object(night, 'publish'):
            result = night.change(mode='off')
        self.assertEqual(result['nightLightMode'], 'off')
        self.assertEqual(json.loads(night.STATE.read_text())['effectiveFlavor'], 'mocha')
        self.assertEqual(json.loads(night.CONFIG.read_text())['manualFlavor'], 'mocha')

    def test_reconcile_repairs_missing_service(self):
        with mock.patch.object(night, 'verify', side_effect=RuntimeError('absent')), \
             mock.patch.object(night, 'unit_state', return_value=(False, 0)), \
             mock.patch.object(night, 'wlsunset_pids', return_value=[]), \
             mock.patch.object(night, 'apply_service') as apply:
            result = night.reconcile()
        apply.assert_called_once()
        self.assertEqual(result['effectiveNightLightMode'], 'auto')

    def test_future_suspension_preserves_preference(self):
        pref = night.normalized(self.pref)
        state = {'nightLightSuspended': True}
        result = night.snapshot(pref, state)
        self.assertEqual(result['nightLightMode'], 'auto')
        self.assertEqual(result['effectiveNightLightMode'], 'off')
        self.assertEqual(night.effective('on', True), 'off')


if __name__ == '__main__':
    unittest.main()
