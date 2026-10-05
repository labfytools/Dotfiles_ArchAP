"""Tests du contrat voyage, avec coordonnées exclusivement synthétiques."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1] / 'bin/.local/bin/location-time-manager.py'
SPEC = importlib.util.spec_from_file_location('location_time_manager', SOURCE)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class LocationTimeTests(unittest.TestCase):
    def test_zone1970_and_search(self):
        entries = MODULE.presets()
        self.assertGreater(len(entries), 200)
        self.assertTrue(MODULE.search(entries, 'Europe/Paris'))
        self.assertTrue(MODULE.search(entries, 'London'))
        self.assertTrue(MODULE.search(entries, 'madrid'))
        self.assertEqual(MODULE.search(entries, 'lieu-introuvable'), [])

    def test_zone1970_synthetic_fixture(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = Path(directory) / 'zone1970.tab'
            fixture.write_text('# synthetic\nXX,YY\t+1230-04515\tEurope/Paris\tLieu synthétique\n', encoding='utf-8')
            items = MODULE.presets(fixture)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['countries'], ['XX', 'YY'])
        self.assertEqual(items[0]['comment'], 'Lieu synthétique')
        self.assertEqual((items[0]['latitude'], items[0]['longitude']), (12.5, -45.25))

    def test_invalid_timezone(self):
        for value in ('', '../../etc/passwd', '/etc/passwd', 'Europe/Impossible',
                      'Europe/Paris\n', 'Europe/Paris\0', 'Europe/../Paris'):
            with self.subTest(value=repr(value)):
                self.assertFalse(MODULE.timezone_valid(value))
        self.assertTrue(MODULE.timezone_valid('Europe/Paris'))
        self.assertTrue(MODULE.timezone_valid('UTC'))

    def test_invalid_coordinates(self):
        for lat, lon in ((91, 0), (0, 181), ('nan', 0), ('', 0), ('texte', 0), (0, '')):
            with self.subTest(lat=lat, lon=lon):
                with self.assertRaises(ValueError):
                    MODULE.coordinates(lat, lon)
        self.assertEqual(MODULE.coordinates('12.5', '-30'), (12.5, -30.0))

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name)
        self.config = base / 'preferences.json'
        self.state = base / 'effective.json'
        self.lock = base / 'wallpaper.lock'
        self.config.write_text(json.dumps({'version': 4, 'nightLightMode': 'auto',
            'nightTemperature': 3000, 'dayTemperature': 6500, 'scheduleType': 'solar',
            'latitude': 10, 'longitude': 20}), encoding='utf-8')
        self.state.write_text('{}', encoding='utf-8')
        self.original = self.config.read_bytes()
        for name, value in (('CONFIG', self.config), ('STATE', self.state), ('LOCK', self.lock)):
            patcher = patch.object(MODULE, name, value)
            patcher.start(); self.addCleanup(patcher.stop)
        self.zone = ['Europe/Paris']
        patcher = patch.object(MODULE, 'current_timezone', side_effect=lambda: self.zone[0])
        patcher.start(); self.addCleanup(patcher.stop)
        patcher = patch.object(MODULE, 'set_timezone', side_effect=lambda tz: self.zone.__setitem__(0, tz))
        self.setter = patcher.start(); self.addCleanup(patcher.stop)
        original_night = MODULE.night_module
        def mocked_night():
            night = original_night()
            night.apply_service = self.service
            night.verify = self.verify
            return night
        self.service_calls = []
        self.service = lambda pref, suspended: self.service_calls.append((pref['nightLightMode'], suspended))
        self.verify = lambda pref, suspended: None
        patcher = patch.object(MODULE, 'night_module', side_effect=mocked_night)
        patcher.start(); self.addCleanup(patcher.stop)

    def test_timezone_only(self):
        MODULE.apply('timezone', timezone='Europe/London')
        self.assertEqual(self.zone[0], 'Europe/London')
        self.assertEqual(self.config.read_bytes(), self.original)
        self.assertEqual(self.service_calls, [])

    def test_solar_only_auto(self):
        MODULE.apply('solar', latitude=11, longitude=21)
        self.assertEqual(self.zone[0], 'Europe/Paris')
        self.assertEqual(self.service_calls, [('auto', False)])
        pref = json.loads(self.config.read_text())
        self.assertEqual((pref['latitude'], pref['longitude']), (11, 21))

    def test_both_and_timezone_failure(self):
        MODULE.apply('both', timezone='Europe/London', latitude=11, longitude=21)
        self.assertEqual(self.zone[0], 'Europe/London')
        self.assertEqual(len(self.service_calls), 1)
        self.zone[0] = 'Europe/Paris'
        self.config.write_bytes(self.original)
        self.setter.side_effect = RuntimeError('authentification refusée')
        with self.assertRaises(RuntimeError):
            MODULE.apply('both', timezone='Europe/London', latitude=11, longitude=21)
        self.assertEqual(self.config.read_bytes(), self.original)

    def test_rollback_on_reconcile_failure(self):
        def fail(pref, suspended):
            if pref['latitude'] == 11:
                raise RuntimeError('service indisponible')
        self.service = fail
        with self.assertRaises(RuntimeError):
            MODULE.apply('both', timezone='Europe/London', latitude=11, longitude=21)
        self.assertEqual(self.zone[0], 'Europe/Paris')
        self.assertEqual(self.config.read_bytes(), self.original)

    def test_timezone_rollback_even_if_service_rollback_fails(self):
        self.service = lambda pref, suspended: (_ for _ in ()).throw(RuntimeError('service indisponible'))
        with self.assertRaisesRegex(RuntimeError, 'rollback incomplet'):
            MODULE.apply('both', timezone='Europe/London', latitude=11, longitude=21)
        self.assertEqual(self.zone[0], 'Europe/Paris')
        self.assertEqual(self.config.read_bytes(), self.original)

    def test_off_on_and_sun_do_not_restart(self):
        pref = json.loads(self.original)
        pref['nightLightMode'] = 'off'
        self.config.write_text(json.dumps(pref))
        MODULE.apply('solar', latitude=11, longitude=21)
        self.assertEqual(self.service_calls, [])
        pref['nightLightMode'] = 'on'
        self.config.write_text(json.dumps(pref))
        MODULE.apply('solar', latitude=12, longitude=22)
        self.assertEqual(self.service_calls, [])
        pref['nightLightMode'] = 'auto'
        self.config.write_text(json.dumps(pref))
        self.state.write_text(json.dumps({'effectiveMode': 'sun-light'}))
        MODULE.apply('solar', latitude=12, longitude=22)
        self.assertEqual(self.service_calls, [])

    def test_saved_location(self):
        MODULE.save_location('Lieu synthétique', 'Europe/London', 11, 22)
        result = json.loads(self.config.read_text())
        self.assertEqual(len(result['savedLocations']), 1)
        self.assertEqual(result['savedLocations'][0]['name'], 'Lieu synthétique')
        with self.assertRaises(ValueError):
            MODULE.save_location('', 'Europe/London', 11, 22)


if __name__ == '__main__':
    unittest.main()
