"""Régressions P0 avec vrais Executor/Guard/Recovery et fenêtres GTK privées."""
from unittest.mock import patch
from common import *
from lab import Lab, Surfaces, build_helper, until
from login_focus import checkpoint, UUID
from session_v2.executor import Executor
from session_v2.guard import Guard
from session_v2.ipc import Sway
from session_v2.storage import private_dir, read, atomic
from session_v2.startup import status, acknowledge
from session_v2.errors import Failure


def run_case(case):
    with Lab() as lab:
        apps = Surfaces(lab, build_helper(lab.directory))
        try:
            lab.command('workspace "10"')
            apps.create('limusic-app')
            lab.command('workspace "1"')
            kitty = apps.create('kitty')
            firefox = apps.create('firefox')
            runtime = private_dir(lab.directory / 'runtime')
            data = checkpoint()
            sway = Sway(lab.socket)
            commands, captures, injected = [], [], []
            raw_command = sway.command
            def command(text):
                commands.append(text)
                return raw_command(text)
            sway.command = command
            def corrupt_layout():
                lab.command(f'[con_id={firefox["id"]}] focus')
                lab.command('layout splitv')
                injected.append(True)
            class Provider:
                def resolve(self, expected, nodes, timeout=6): return {UUID: nodes[0]['id']}
                def capture(self, nodes, timeout=6):
                    captures.append(True)
                    # Trois vérifications : avant focus, après resume, après finish.
                    if case in ('last-capture-layout', 'last-capture-swap') and len(captures) == 3:
                        if case == 'last-capture-layout': corrupt_layout()
                        else:
                            lab.command(f'[con_id={firefox["id"]}] swap container with con_id {kitty["id"]}')
                            injected.append(True)
                    return {UUID: nodes[0]['id']}
            raw_finish = Guard.finish
            def finish(guard):
                answer = raw_finish(guard)
                if case == 'guard-finish-layout' and not injected: corrupt_layout()
                return answer
            def guard(*args):
                value = Guard(*args)
                if case in ('guard-replacement', 'guard-extra'):
                    if case == 'guard-replacement':
                        lab.command(f'[con_id={kitty["id"]}] kill')
                        until(lambda: not any(n['id'] == kitty['id'] for n in lab.windows()))
                    new = apps.create('kitty')
                    assert new['id'] != kitty['id']
                    injected.append(new['id'])
                return value
            status(runtime, sway.session, data, True)
            with patch('session_v2.executor.Guard', side_effect=guard), patch.object(Guard, 'finish', finish), \
                 patch('session_v2.guard.discover', return_value=[]), \
                 patch('session_v2.executor.launch', side_effect=AssertionError('LAUNCH_FORBIDDEN')):
                try: Executor(sway, Catalog(), Provider(), runtime, build(lab.directory), lab.env).apply(data, True)
                except Failure as exc: reason = exc.code
                else: raise AssertionError('P0_FALSE_SUCCESS')
            report = read(runtime / 'session-v2-restore-attempt.json')
            assert injected and report['status'] == 'failed', report
            assert read(runtime / 'session-v2-recovery.json')['status'] != 'complete'
            if case.startswith('guard-') and case != 'guard-finish-layout':
                assert commands == [], commands
                assert reason == 'APPLICATION_MEMBERSHIP_CHANGED', reason
            else:
                expected = 'RECOVERY_ORDER_CHANGED' if case == 'last-capture-swap' else 'FINAL_TREE_MISMATCH'
                assert reason == expected, reason
                if case.startswith('last-capture'): assert len(captures) == 3
            try: acknowledge(runtime, sway.session, 'restored', report['transaction_id'])
            except Failure: pass
            else: raise AssertionError('P0_FALSE_ACK')
            row = {'scenario': case, 'reason': reason, 'commands': commands, 'report': report,
                   'captures': len(captures), 'no_ack': True, 'real_login_validated': False}
            atomic(private_dir(EVIDENCE) / ('p0-'+case+'.json'), row)
            print(case, 'PASS', reason, flush=True)
        finally: apps.close()


if __name__ == '__main__':
    for case in ('guard-replacement', 'guard-extra', 'last-capture-layout', 'last-capture-swap', 'guard-finish-layout'):
        run_case(case)
