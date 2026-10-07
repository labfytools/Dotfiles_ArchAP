"""Placement Limusic synthétique : vrai backend déployé, Sway TEST_ONLY."""
from unittest.mock import patch
from common import *
from lab import Lab, Surfaces, build_helper
from session_v2.applications import Catalog
from session_v2.executor import Executor
from session_v2.ipc import Sway
from session_v2.storage import private_dir, atomic
from session_v2.snapshot import capture


def main():
    with Lab() as lab:
        apps = Surfaces(lab, build_helper(lab.directory))
        lab.command('workspace TEST_ONLY_SOURCE')
        apps.create('limusic-app')
        data = fixture('A', 'TEST_ONLY_LIMUSIC')
        data['applications'] = [{'application_id': 'limusic', 'desktop_entry': 'limusic.desktop',
            'strategy': 'managed-autostart', 'expected_windows': 1, 'managed_by': 'sway-autostart', 'identity_provider': None}]
        data['window_slots'][0].update(application_id='limusic', identity_evidence={'type': 'application-singleton', 'id': 'limusic'})
        try:
            # Toute tentative de lancement serait une régression de propriété.
            with patch('session_v2.executor.launch', side_effect=lambda spec, count, env: [] if count == 0 else (_ for _ in ()).throw(AssertionError('DUPLICATE_LIMUSIC'))):
                result = Executor(Sway(lab.socket), Catalog(), None, private_dir(lab.directory / 'runtime'), build(lab.directory), lab.env).apply(data, True)
            snap = capture(Sway(lab.socket), Catalog(), None)
            assert snap['applications'][0]['managed_by'] == 'sway-autostart'
            assert result['status'] == 'success'
            atomic(private_dir(EVIDENCE) / 'limusic-test-only.json', {'result': result, 'launches': 0, 'capture_owner': 'sway-autostart'})
            print('LIMUSIC_TEST_ONLY=PASS')
        finally: apps.close()


if __name__ == '__main__': main()
