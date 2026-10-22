"""Phase 0 production, arbres inertes ; aucun IPC/processus externe autorisé.

Le chemin après admission est couvert par login_focus sur Sway headless réel.
Ici la frontière _apply sert à prouver l'absence de publication avant admission.
"""
import threading
import unittest
from unittest.mock import patch
from common import *
from login_focus import checkpoint
from session_v2.executor import Executor
from session_v2.applications import Catalog
from session_v2.recovery import Recovery, JOURNAL, focused, focus_proof
from session_v2.errors import Failure
import tempfile


class Sway:
    session = 'a' * 64
    def __init__(self):
        self.value = dict(id=1, type='root', nodes=[dict(id=2, type='output', name='HEADLESS-1', nodes=[
            dict(id=3, type='workspace', name='10', nodes=[], focused=False),
            dict(id=4, type='workspace', name='1', nodes=[], focused=True)])])
        self.commands = []
        self.add('limusic-app', 5, '10', focus=False)
    def tree(self): return copy.deepcopy(self.value)
    def windows(self):
        from session_v2.ipc import walk
        return [n for n in walk(self.tree()) if n.get('app_id')]
    def outputs(self): return [dict(name='HEADLESS-1', active=True)]
    def command(self, text): self.commands.append(text); raise AssertionError(text)
    def add(self, app, identity, where='1', focus=True):
        from session_v2.ipc import walk, workspace
        if focus:
            for n in walk(self.value): n['focused'] = False
        node = dict(id=identity, type='con', app_id=app, pid=os.getpid(), rect={}, nodes=[], focused=focus)
        workspace(self.value, where)['nodes'].append(node)
        return node


class PrewarmTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.runtime = Path(self.tmp.name)
        self.sway = Sway()
        self.engine = Executor(self.sway, Catalog(), object(), self.runtime, '/forbidden')
        self.data = checkpoint()
        self.launches = []
        self.threads = []
        self.addCleanup(lambda: [t.join(2) for t in self.threads])
        blocker = patch('subprocess.Popen', side_effect=AssertionError('process forbidden'))
        blocker.start(); self.addCleanup(blocker.stop)
    def launched(self, spec, count, env):
        self.launches.append((spec.application_id, count))
        self.assertEqual(count, 1)
        self.sway.add(spec.app_ids[0], 20 + len(self.launches))
        return []
    def assert_unpublished(self):
        self.assertFalse((self.runtime / JOURNAL).exists())
        self.assertFalse((self.runtime / 'session-v2-restore-attempt.json').exists())
        self.assertEqual(self.sway.commands, [])
    def test_async_mapping_completes_before_apply_and_focus_proof(self):
        def launch(spec, count, env):
            self.launches.append((spec.application_id, count))
            def mapped():
                time.sleep(.02 if spec.application_id == 'kitty' else .06)
                self.sway.add(spec.app_ids[0], 21 if spec.application_id == 'kitty' else 22)
            thread = threading.Thread(target=mapped); self.threads.append(thread); thread.start()
            return []
        def admitted(data, timeout, lock_fd, proof, prepared):
            self.assert_unpublished()
            self.assertEqual(focus_proof(self.sway), proof)
            self.assertEqual(proof[1][0], dict(con_id=22, workspace='1'))
            self.assertEqual(set(prepared), {5, 21, 22})
            self.assertEqual(prepared[5]['workspace'], '10')
            return 'admitted'
        with patch('session_v2.executor.launch', side_effect=launch), patch.object(self.engine, '_apply', side_effect=admitted):
            self.assertEqual(self.engine.apply(self.data, True, timeout=.5), 'admitted')
        self.assertEqual(self.launches, [('kitty', 1), ('firefox', 1)])
    def test_launch_failure_preserves_clients_and_retry_does_not_duplicate(self):
        origin = self.sway.windows()[0]
        def fail(spec, count, env):
            if spec.application_id == 'firefox': raise OSError('TEST_ONLY launch failure')
            return self.launched(spec, count, env)
        with patch('session_v2.executor.launch', side_effect=fail):
            with self.assertRaisesRegex(Failure, 'APPLICATION_LAUNCH_FAILED'): self.engine.apply(self.data, True)
        self.assert_unpublished()
        self.assertEqual(self.sway.windows()[0], origin)
        with patch('session_v2.executor.launch', side_effect=self.launched), patch.object(self.engine, '_apply', return_value='ok'):
            self.assertEqual(self.engine.apply(self.data, True), 'ok')
        self.assertEqual(self.launches, [('kitty', 1), ('firefox', 1)])
    def test_deferred_marker_and_cli_preserve_cause_for_explicit_retry(self):
        import io
        import json
        from contextlib import redirect_stdout
        from session_v2.startup import status
        from session_v2.errors import Deferred
        from session_v2.cli import main
        status(self.runtime, self.sway.session, self.data, True)
        with patch('session_v2.executor.launch', side_effect=OSError('TEST_ONLY')):
            with self.assertRaises(Deferred): self.engine.apply(self.data, True)
        seen = status(self.runtime, self.sway.session, self.data)
        self.assertTrue(seen['deferred'])
        self.assertEqual(seen['deferred_reason'], 'APPLICATION_LAUNCH_FAILED')
        output = io.StringIO()
        with patch('session_v2.cli.paths', return_value=(self.runtime/'state', self.runtime)), \
             patch('session_v2.keyring.require_ready'), \
             patch('session_v2.cli.Store'), patch('session_v2.cli.Sway'), patch('session_v2.cli.FirefoxProvider'), \
             patch('session_v2.cli.Executor.apply', side_effect=Deferred('APPLICATION_LAUNCH_FAILED')), redirect_stdout(output):
            self.assertEqual(main(['apply-last', '--execute', '--socket', '/TEST_ONLY']), 2)
        self.assertEqual(json.loads(output.getvalue()), dict(status='DEFERRED', reason='APPLICATION_LAUNCH_FAILED'))
        self.assert_unpublished()

    def test_missing_managed_autostart_refuses_before_launch(self):
        self.sway.value['nodes'][0]['nodes'][0]['nodes'] = []
        with patch('session_v2.executor.launch') as launch:
            with self.assertRaisesRegex(Failure, 'APPLICATION_WINDOWS_INCOMPLETE'): self.engine.apply(self.data, True)
            launch.assert_not_called()
        self.assert_unpublished()
    def test_existing_required_journal_refuses_before_launch(self):
        r = Recovery(self.sway, self.runtime, 'b'*32, 'labfy-v2-stage-'+'b'*32)
        r.data['status'] = 'required'; r.publish(); r.receipt('RECOVERY_REQUIRED', [], ['TEST_ONLY'])
        before = (self.runtime / JOURNAL).read_bytes()
        with patch('session_v2.executor.launch') as launch:
            with self.assertRaisesRegex(Failure, 'RECOVERY_REQUIRED'): self.engine.apply(self.data, True)
            launch.assert_not_called()
        self.assertEqual((self.runtime / JOURNAL).read_bytes(), before)
        self.assertEqual(self.sway.commands, [])
    def test_intruder_extra_identity_session_and_owner_refuse_without_publication(self):
        for mode, reason in [('foreign', 'APPLICATION_MEMBERSHIP_CHANGED'), ('extra', 'UNEXPECTED_EXTRA_WINDOW'),
                             ('identity', 'TARGET_OBSERVATION_CHANGED'), ('session', 'SWAY_SESSION_CHANGED'),
                             ('owner', 'APPLICATION_OWNER_INVALID')]:
            with self.subTest(mode=mode):
                self.sway = Sway(); self.engine.sway = self.sway
                def launch(spec, count, env):
                    self.launched(spec, count, env)
                    if spec.application_id == 'firefox':
                        if mode == 'foreign': self.sway.add('TEST_ONLY_FOREIGN', 90)
                        if mode == 'extra': self.sway.add('firefox', 90)
                        if mode == 'identity': self.sway.value['nodes'][0]['nodes'][0]['nodes'][0]['app_id'] = 'other'
                        if mode == 'session': self.sway.session = 'c'*64
                    return []
                def owner(pid): return os.getuid()+1 if mode == 'owner' else os.getuid()
                with patch('session_v2.executor.launch', side_effect=launch), patch('session_v2.executor.process_owner', side_effect=owner):
                    with self.assertRaisesRegex(Failure, reason): self.engine.apply(self.data, True)
                self.assert_unpublished()
    def test_focus_change_after_proof_refuses_without_publication(self):
        from session_v2.executor import preflight
        calls = []
        def changed(*args):
            result = preflight(*args); calls.append(True)
            # Initial + before each of the three apps, then final preflight.
            if len(calls) == 5:
                from session_v2.ipc import walk
                for n in walk(self.sway.value): n['focused'] = n['id'] == 5
            return result
        with patch('session_v2.executor.launch', side_effect=self.launched), patch('session_v2.executor.preflight', side_effect=changed):
            with self.assertRaisesRegex(Failure, 'RESTORE_FOCUS_UNSTABLE'): self.engine.apply(self.data, True)
        self.assert_unpublished()


if __name__ == '__main__': unittest.main()
