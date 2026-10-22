"""Late synthetic keyring-like surface: real focus proof must still fail.

CONTRACT: the surface is TEST_ONLY and does not establish the historical
identity of con_id 18. No event infers user-vs-IPC causality from app_id.
"""
import json
from unittest.mock import patch
from common import *
from lab import Lab, Surfaces, build_helper
from session_v2.executor import Executor
from session_v2.recovery import Recovery, recovery_status
from session_v2.ipc import Sway
from session_v2.errors import Failure
from session_v2.storage import private_dir, read


def main():
    for late in (False, True):
        with Lab() as lab:
            print(lab.directory, flush=True)
            helper = build_helper(lab.directory)
            apps = Surfaces(lab, helper)
            lab.command('workspace TEST_ONLY_TARGET')
            apps.create('TEST_ONLY_app-A')
            data = fixture('A')
            sway = Sway(lab.socket)
            runtime = private_dir(lab.directory / 'runtime')
            binary = build(lab.directory)
            original = Recovery.boundary
            observed = []
            def boundary(recovery, phase):
                original(recovery, phase)
                if phase == 'after-guard-finish' and late:
                    # Same placement in the lifecycle as the historical race.
                    # A real compositor maps/focuses this independent surface.
                    observed.append(apps.create('TEST_ONLY_keyring_prompt'))
            engine = Executor(sway, catalog(data), None, runtime, binary, lab.env)
            with patch.object(Recovery, 'boundary', boundary):
                if late:
                    try: engine.apply(data, True)
                    except Failure as exc: assert exc.code == 'RECOVERY_FOCUS_MISMATCH', exc.code
                    else: raise AssertionError('LATE_FOCUS_WAS_ACCEPTED')
                else:
                    value = engine.apply(data, True)
                    assert value['status'] == 'success' and value['final_focus_verified']
            report = read(runtime / 'session-v2-restore-attempt.json')
            if late:
                assert report['status'] == 'failed' and report['reason'] == 'RECOVERY_FOCUS_MISMATCH', report
                assert not report['final_focus_verified']
                assert recovery_status(runtime)['status'] == 'RECOVERY_REQUIRED'
                # Attribution remains an observation; no focus correction to
                # manufacture success after an unexpected late activation.
                assert observed[0]['app_id'] == 'TEST_ONLY_keyring_prompt'
            print('late-refused' if late else 'stable-final-focus', 'PASS', flush=True)
            apps.close()


if __name__ == '__main__': main()
