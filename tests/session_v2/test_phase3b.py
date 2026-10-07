"""Delta de déploiement : propriétaire autostart et acknowledgement durable."""
import copy
from pathlib import Path
import tempfile
import unittest
from common import *
from session_v2.applications import Catalog, launch_count
from session_v2.errors import Failure
from session_v2.storage import atomic, read, private_dir
from session_v2.startup import acknowledge, successful
from session_v2.observability import Attempt


class DeploymentTests(unittest.TestCase):
    def test_limusic_never_launched(self):
        spec = Catalog().classify({'app_id': 'limusic-app'})
        app = {'application_id': 'limusic', 'desktop_entry': 'limusic.desktop', 'strategy': 'managed-autostart',
               'managed_by': 'sway-autostart', 'expected_windows': 1, 'identity_provider': None}
        self.assertEqual(Catalog().validate(app), spec)
        self.assertEqual(spec.argv, ())
        self.assertEqual(launch_count(app, 0), 0)
        self.assertEqual(launch_count(app, 1), 0)
        with self.assertRaisesRegex(Failure, 'UNEXPECTED_EXTRA_WINDOW'): launch_count(app, 2)
        app['managed_by'] = 'autostart'
        with self.assertRaises(Failure): Catalog().validate(app)

    def test_ack_requires_verified_current_transaction(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = private_dir(Path(directory))
            acknowledge(runtime, 'session', 'new')
            attempt = Attempt(runtime / 'session-v2-restore-attempt.json', 'a' * 32, fixture())
            with self.assertRaises(Failure): acknowledge(runtime, 'session', 'restored', 'a' * 32)
            attempt.update(status='success', phase='complete', reason='SUCCESS', final_tree_verified=True,
                           final_focus_verified=True, slots_filled=3, applications_observed=3)
            self.assertTrue(successful(attempt.data))
            with self.assertRaises(Failure): acknowledge(runtime, 'other-session', 'restored', 'a' * 32)
            with self.assertRaises(Failure): acknowledge(runtime, 'session', 'restored', 'b' * 32)
            self.assertEqual(acknowledge(runtime, 'session', 'restored', 'a' * 32)['status'], 'acknowledged')
            self.assertEqual(read(runtime / 'session-v2/startup.json')['choice'], 'restored')
            for change in ({'final_tree_verified': False}, {'final_focus_verified': False},
                           {'anchors_created': 1}, {'helpers_suspended': 1}, {'slots_filled': 2}, {'applications_observed': 2}):
                self.assertFalse(successful({**attempt.data, **change}))


if __name__ == '__main__': unittest.main()
