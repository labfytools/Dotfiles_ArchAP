"""Incidents du 22 octobre : arbres inertes et helper headless privé seulement."""
import unittest
import tempfile
from unittest.mock import patch
from common import *
from test_prewarm import Sway
from session_v2.recovery import Recovery, JOURNAL, focused
from session_v2.ipc import walk, workspace
from session_v2.storage import read
from session_v2.errors import Failure


class FocusRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.runtime = Path(self.tmp.name)
        self.sway = Sway()
        for ws in self.sway.value['nodes'][0]['nodes']: ws['layout'] = 'splith'
        self.sway.add('firefox', 8, focus=True)
        self.sway.add('kitty', 7, focus=False)
        self.recovery = Recovery(self.sway, self.runtime, 'b'*32, 'labfy-v2-stage-'+'b'*32, start=lambda pid: 123)
        for n in self.sway.windows(): self.recovery.admit(n)
        self.recovery.baseline({'firefox', 'kitty', 'limusic-app'})
        # Production command, independently simulated focus effect, no socket.
        def command(text):
            self.sway.commands.append(text)
            self.assertEqual(text, '[con_id=8] focus')
            for n in walk(self.sway.value): n['focused'] = n['id'] == 8
        self.sway.command = command
        self.recovery.command('[con_id=8] focus')

    def unary(self):
        ws = workspace(self.sway.value, '1')
        ws['nodes'] = [dict(id=80+i, type='con', layout='splitv', nodes=[n], focused=False)
                       for i, n in enumerate(ws['nodes'])]

    def test_firefox_command_proven_then_kitty_late_conflict_is_preserved(self):
        self.assertFalse(self.recovery.data['focus_pending'])
        for n in walk(self.sway.value): n['focused'] = n['id'] == 7
        with self.assertRaisesRegex(Failure, 'RECOVERY_FOCUS_MISMATCH'):
            self.recovery.validate_final(self.sway.tree())
        first = read(self.runtime/JOURNAL)['focus_conflict_observation']
        self.assertEqual(first['before'], dict(con_id=8, workspace='1'))
        self.assertEqual(first['observed'], dict(con_id=7, workspace='1'))
        self.sway.commands.clear()
        receipt = Recovery(self.sway, self.runtime, start=lambda pid: 123).recover()
        self.assertEqual(receipt['status'], 'RECOVERY_REQUIRED')
        self.assertIn('FOCUS_RECOVERY_NOT_PROVEN', receipt['issues'])
        self.assertEqual(self.sway.commands, [])
        self.assertEqual(read(self.runtime/JOURNAL)['focus_conflict_observation'], first)

    def test_equivalent_unary_paths_are_not_identity_changes(self):
        self.unary()
        # A conflict forbids IPC, but exact already-at-origin windows can be
        # recognized without stealing the user's new focus or clearing incident.
        self.recovery.record_focus_conflict({'phase': 'TEST_ONLY'})
        self.sway.commands.clear()
        receipt = Recovery(self.sway, self.runtime, start=lambda pid: 123).recover()
        self.assertEqual(receipt['windows'], [])
        durable = read(self.runtime/JOURNAL)
        paths = {row['con_id']: row for row in durable['path_reconciliations'][0]}
        self.assertEqual(paths[8], dict(con_id=8, before=[0], after=[0, 0]))
        self.assertEqual(paths[7], dict(con_id=7, before=[1], after=[1, 0]))
        self.assertEqual(receipt['status'], 'RECOVERY_REQUIRED')
        self.assertEqual(self.sway.commands, [])

    def test_path_evidence_limit_refuses_without_overwriting_history(self):
        self.recovery.data['path_reconciliations'] = [[] for _ in range(4)]
        self.unary()
        self.recovery.record_focus_conflict({'phase': 'TEST_ONLY'})
        receipt = self.recovery.recover()
        self.assertEqual(receipt['status'], 'RECOVERY_REQUIRED')
        self.assertTrue(any(w['reason'] == 'PATH_EQUIVALENCE_NOT_PROVEN' for w in receipt['windows']))
        self.assertEqual(read(self.runtime/JOURNAL)['path_reconciliations'], [[], [], [], []])

    def test_layout_change_with_identical_raw_paths_still_refuses(self):
        workspace(self.sway.value, '1')['layout'] = 'splitv'
        self.sway.commands.clear()
        receipt = self.recovery.recover()
        self.assertEqual(receipt['status'], 'RECOVERY_REQUIRED')
        self.assertTrue(any(e['reason'] == 'STRUCTURE_OR_ORDER_CHANGED' for e in receipt['windows']))
        self.assertEqual(self.sway.commands, [])

    def test_interrupted_intention_preserves_all_evidence(self):
        self.unary()
        self.recovery.data['windows'][1]['pending'] = True
        self.recovery.data['focus_pending'] = True
        self.recovery.publish()
        intention = copy.deepcopy(self.recovery.data['intention'])
        expected = copy.deepcopy(self.recovery.data['windows'][1]['expected'])
        self.sway.commands.clear()
        receipt = Recovery(self.sway, self.runtime, start=lambda pid: 123).recover()
        self.assertEqual(receipt['status'], 'RECOVERY_REQUIRED')
        self.assertTrue(any(e['reason'] == 'AMBIGUOUS_INTENTION' for e in receipt['windows']))
        durable = read(self.runtime/JOURNAL)
        self.assertEqual(durable['intention'], intention)
        self.assertEqual(durable['windows'][1]['expected'], expected)
        self.assertTrue(durable['focus_pending'])
        self.assertEqual(self.sway.commands, [])

    def test_real_identity_order_workspace_and_branch_changes_still_refuse(self):
        for mode in ('pid', 'starttime', 'app_id', 'con_id', 'order', 'workspace', 'output', 'branch', 'tabbed', 'geometry', 'floating', 'pending', 'legacy'):
            with self.subTest(mode=mode):
                tree = copy.deepcopy(self.sway.value)
                saved = copy.deepcopy(self.recovery.data)
                self.unary()
                nodes = {n['id']: n for n in walk(self.sway.value)}
                if mode == 'pid': nodes[8]['pid'] += 1
                if mode == 'starttime': self.recovery.start = lambda pid: 999
                if mode == 'app_id': nodes[8]['app_id'] = 'kitty'
                if mode == 'con_id': nodes[8]['id'] = 88
                if mode == 'order': workspace(self.sway.value, '1')['nodes'].reverse()
                if mode == 'workspace': workspace(self.sway.value, '1')['name'] = 'OTHER'
                if mode == 'output': self.sway.value['nodes'][0]['name'] = 'OTHER'
                if mode == 'branch': workspace(self.sway.value, '1')['layout'] = 'splitv'
                if mode == 'tabbed': nodes[80]['layout'] = 'tabbed'
                if mode == 'geometry':
                    nodes[8].update(floating='user_on', rect=dict(x=0, y=0, width=200, height=100))
                if mode == 'floating': nodes[8]['floating'] = 'user_on'
                if mode == 'pending': self.recovery.data['windows'][1]['pending'] = True
                if mode == 'legacy': self.recovery.data.pop('structure_expected', None)
                self.recovery.record_focus_conflict({'phase': 'TEST_ONLY'})
                self.sway.commands.clear()
                receipt = self.recovery.recover()
                self.assertEqual(receipt['status'], 'RECOVERY_REQUIRED')
                self.assertTrue(receipt['windows'])
                self.assertEqual(self.sway.commands, [])
                self.sway.value, self.recovery.data = tree, saved
                self.recovery.start = lambda pid: 123


if __name__ == '__main__': unittest.main()
