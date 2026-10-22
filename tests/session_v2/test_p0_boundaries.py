"""Courses déterministes aux frontières externes, sans processus ni IPC réel."""
import tempfile
import unittest
from unittest.mock import patch
from common import *
from test_prewarm import Sway
from login_focus import checkpoint, UUID
from session_v2.executor import Executor
from session_v2.anchors import Anchors
from session_v2.recovery import Recovery, RecordedSway, focus_proof
from session_v2.ipc import workspace
from session_v2.errors import Failure
from session_v2.storage import read
from session_v2.startup import acknowledge, status
from session_v2.observability import Attempt


class BoundaryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.runtime = Path(self.tmp.name)
        self.sway = Sway()
        self.sway.add('kitty', 11, focus=False)
        self.sway.add('firefox', 12)
        workspace(self.sway.value, '1')['layout'] = 'splith'
        workspace(self.sway.value, '10')['layout'] = 'splith'
        self.data = checkpoint()
        self.engine = Executor(self.sway, Catalog(), object(), self.runtime, '/forbidden', process_identity=lambda pid: 123)

    def test_guard_replacement_and_extra_refuse_before_any_mutation(self):
        for mode in ('replacement', 'extra', 'pid', 'starttime', 'placement'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                self.setUp()
                self.engine.runtime = Path(directory)
                prepared = self.engine._observe_prepared()
                proof = focus_proof(self.sway)
                def guard(*args):
                    node = next(n for n in workspace(self.sway.value, '1')['nodes'] if n['id'] == 11)
                    if mode == 'replacement': node['id'] = 21
                    if mode == 'extra': self.sway.add('kitty', 21, focus=False)
                    if mode == 'pid': node['pid'] += 1
                    if mode == 'starttime': self.engine.process_identity = lambda pid: 456
                    if mode == 'placement':
                        workspace(self.sway.value, '1')['nodes'].remove(node)
                        workspace(self.sway.value, '10')['nodes'].append(node)
                    from unittest.mock import Mock
                    return Mock(ready={'helpers_suspended': 0}, finish=lambda: {'helpers_resumed': 0, 'anchors_cleaned': 0})
                from unittest.mock import Mock
                anchors = Mock(owned=lambda n: False, close=lambda: None)
                with patch('session_v2.executor.Anchors', return_value=anchors), patch('session_v2.executor.Guard', side_effect=guard):
                    with self.assertRaises(Failure):
                        self.engine._apply(self.data, 1, -1, proof, prepared)
                self.assertEqual(self.sway.commands, [])
                attempt = read(self.engine.runtime / 'session-v2-restore-attempt.json')
                self.assertNotEqual(attempt['status'], 'success')

    def test_extra_after_first_move_refuses_before_second_staging(self):
        from unittest.mock import Mock
        from session_v2.recovery import command_focus
        from session_v2.ipc import walk
        def command(text):
            import json
            self.sway.commands.append(text)
            target = int(text.split('=', 1)[1].split(']', 1)[0])
            operation = text.split('] ', 1)[1]
            focus = command_focus(self.sway.value, target, operation)
            node = next(n for n in walk(self.sway.value) if n['id'] == target)
            for parent in walk(self.sway.value):
                if node in parent.get('nodes', []):
                    parent['nodes'].remove(node)
                    break
            stage = json.loads(operation.removeprefix('move container to workspace '))
            destination = dict(id=90, type='workspace', name=stage, nodes=[node])
            self.sway.value['nodes'][0]['nodes'].append(destination)
            for n in walk(self.sway.value):
                n['focused'] = n['id'] == focus['con_id'] if focus['con_id'] is not None else n.get('name') == focus['workspace']
            self.sway.add('kitty', 21, focus=False)
        self.sway.command = command
        anchors = Mock(owned=lambda node: False, close=lambda: None)
        guard = Mock(ready={'helpers_suspended': 0}, finish=lambda: {'helpers_resumed': 0, 'anchors_cleaned': 0})
        prepared, proof = self.engine._observe_prepared(), focus_proof(self.sway)
        # La reprise est hors de cette frontière : aucun cleanup ne doit
        # masquer combien de commandes de staging ont effectivement été émises.
        with patch('session_v2.executor.Anchors', return_value=anchors), \
             patch('session_v2.executor.Guard', return_value=guard), patch.object(Recovery, 'recover'):
            with self.assertRaisesRegex(Failure, 'APPLICATION_MEMBERSHIP_CHANGED'):
                self.engine._apply(self.data, 1, -1, proof, prepared)
        self.assertEqual(len(self.sway.commands), 1)
        self.assertFalse(any('[con_id=21]' in text for text in self.sway.commands))
        anchors.build.assert_not_called()

    def final_fixture(self):
        recovery = Recovery(self.sway, self.runtime, 'b'*32, 'labfy-v2-stage-'+'b'*32, start=lambda pid: 123)
        recovery.baseline({'kitty', 'firefox', 'limusic-app'})
        for node in self.sway.windows(): recovery.admit(node)
        self.engine.sway = RecordedSway(self.sway, recovery)
        anchors = Anchors.__new__(Anchors)
        anchors.sway, anchors.data = self.engine.sway, self.data
        anchors.owned = lambda n: False
        mapping = {'F': 12, 'K': 11, 'M': 5}
        # Le checkpoint impose F,K ; le préwarm initial créait K,F.
        workspace(self.sway.value, '1')['nodes'].reverse()
        for entry in recovery.data['windows']:
            entry['expected'] = recovery.snapshot(entry['origin']['con_id'])
        return recovery, anchors, mapping

    def test_last_provider_capture_cannot_hide_structure_or_identity_change(self):
        for mode in ('layout', 'swap', 'pid', 'starttime', 'extra', 'floating', 'output', 'focus', 'uuid'):
            with self.subTest(mode=mode):
                self.setUp()
                recovery, anchors, mapping = self.final_fixture()
                def capture(members):
                    ws = workspace(self.sway.value, '1')
                    if mode == 'layout': ws['layout'] = 'splitv'
                    if mode == 'swap': ws['nodes'].reverse()
                    if mode == 'pid': ws['nodes'][0]['pid'] += 1
                    if mode == 'starttime': recovery.start = lambda pid: 456
                    if mode == 'extra': self.sway.add('kitty', 21, focus=False)
                    if mode == 'floating': ws['nodes'][0]['floating'] = 'user_on'
                    if mode == 'output': self.sway.value['nodes'][0]['name'] = 'OTHER'
                    if mode == 'focus':
                        from session_v2.ipc import walk
                        for node in walk(self.sway.value): node['focused'] = node['id'] == 11
                    return {UUID: 11 if mode == 'uuid' else 12}
                status(self.runtime, self.sway.session, self.data, True)
                attempt = Attempt(self.runtime / 'session-v2-restore-attempt.json', 'b'*32, self.data)
                attempt.update(status='failed', reason='TEST_ONLY')
                from unittest.mock import Mock
                self.engine.provider = Mock(capture=Mock(side_effect=capture))
                with self.assertRaises(Failure):
                    self.engine._verify(self.data, mapping, {a['application_id']: Catalog().validate(a) for a in self.data['applications']}, anchors)
                self.engine.provider.capture.assert_called_once()
                with self.assertRaises(Failure): acknowledge(self.runtime, self.sway.session, 'restored', 'b'*32)

    def test_unchanged_final_observation_completes(self):
        recovery, anchors, mapping = self.final_fixture()
        from unittest.mock import Mock
        self.engine.provider = Mock(capture=lambda nodes: {UUID: 12})
        specs = {a['application_id']: Catalog().validate(a) for a in self.data['applications']}
        self.engine._verify(self.data, mapping, specs, anchors)
        recovery.complete(lambda tree: self.engine._verify_structure(self.data, mapping, specs, anchors, tree))
        self.assertEqual(recovery.data['status'], 'complete')

    def test_unary_parent_normalization_preserves_canonical_layout(self):
        recovery, anchors, mapping = self.final_fixture()
        ws = workspace(self.sway.value, '1')
        ws['nodes'] = [dict(id=90, type='con', layout='splith', nodes=ws['nodes'])]
        specs = {a['application_id']: Catalog().validate(a) for a in self.data['applications']}
        recovery.complete(lambda tree: self.engine._verify_structure(self.data, mapping, specs, anchors, tree))
        self.assertEqual(recovery.data['status'], 'complete')

    def test_layout_change_in_second_split_focus_observation_refuses(self):
        recovery, anchors, mapping = self.final_fixture()
        from session_v2.ipc import walk
        ws = workspace(self.sway.value, '1')
        for node in walk(self.sway.value): node['focused'] = False
        parent = dict(id=90, type='con', layout='splith', nodes=ws['nodes'], focused=True)
        ws['nodes'] = [parent]
        recovery.data['focus_expected'] = dict(con_id=90, workspace='1')
        raw_tree, calls = self.sway.tree, []
        def tree():
            calls.append(True)
            if len(calls) == 2: parent['layout'] = 'splitv'
            return raw_tree()
        self.sway.tree = tree
        specs = {a['application_id']: Catalog().validate(a) for a in self.data['applications']}
        with self.assertRaisesRegex(Failure, 'FINAL_TREE_MISMATCH'):
            self.engine._verify_structure(self.data, mapping, specs, anchors, self.sway.tree())
        self.assertEqual(len(calls), 2)

    def test_complete_refuses_full_identity_placement_and_pending(self):
        for mode in ('pid', 'starttime', 'placement', 'pending', 'focus_pending', 'swap'):
            with self.subTest(mode=mode):
                self.setUp()
                recovery, _, _ = self.final_fixture()
                node = workspace(self.sway.value, '1')['nodes'][0]
                if mode == 'pid': node['pid'] += 1
                if mode == 'starttime': recovery.start = lambda pid: 456
                if mode == 'placement': node['floating'] = 'user_on'
                if mode == 'pending': recovery.data['windows'][0]['pending'] = True
                if mode == 'focus_pending': recovery.data['focus_pending'] = True
                if mode == 'swap': workspace(self.sway.value, '1')['nodes'].reverse()
                with self.assertRaises(Failure): recovery.complete()
                self.assertNotEqual(recovery.data['status'], 'complete')


if __name__ == '__main__': unittest.main()
