"""Placement Limusic synthétique : vrai backend déployé, Sway TEST_ONLY."""
from unittest.mock import patch
from common import *
from lab import Lab, Surfaces, build_helper
from session_v2.applications import Catalog
from session_v2.executor import Executor
from session_v2.ipc import Sway
from session_v2.storage import private_dir, atomic
from session_v2.snapshot import capture
from session_v2.errors import Failure


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
            # Absente ou dupliquée : aucun lancement/kill Limusic, même en erreur.
            apps.close()
            cases = []
            for count, reason in ((0, 'APPLICATION_WINDOWS_INCOMPLETE'), (2, 'UNEXPECTED_EXTRA_WINDOW')):
                lab.command('workspace TEST_ONLY_SOURCE')
                if count:
                    apps = Surfaces(lab, build_helper(lab.directory))
                    for _ in range(count): apps.create('limusic-app')
                before = {n['id'] for n in lab.windows()}
                commands = []
                sway = Sway(lab.socket)
                raw_command = sway.command
                def command(text):
                    commands.append(text)
                    return raw_command(text)
                sway.command = command
                with patch('session_v2.executor.launch', side_effect=lambda spec, n, env: [] if n == 0 else (_ for _ in ()).throw(AssertionError('DUPLICATE_LIMUSIC'))):
                    try:
                        Executor(sway, Catalog(), None, private_dir(lab.directory / f'runtime-{count}'), build(lab.directory), lab.env).apply(data, True, timeout=.3)
                    except Failure as exc: assert exc.code == reason, exc.code
                    else: raise AssertionError('ERREUR_ATTENDUE')
                assert {n['id'] for n in lab.windows() if n['app_id'] == 'limusic-app'} == before
                if count == 2: assert commands == []
                cases.append({'windows': count, 'reason': reason, 'launches': 0, 'preserved': True})
            atomic(private_dir(EVIDENCE) / 'limusic-test-only.json', {'result': result, 'launches': 0, 'capture_owner': 'sway-autostart', 'refusals': cases})
            print('LIMUSIC_TEST_ONLY=PASS')
        finally:
            if apps.proc.poll() is None: apps.close()


if __name__ == '__main__': main()
