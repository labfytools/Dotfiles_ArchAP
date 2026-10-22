"""Refus à la frontière Guard sur le lot exact de quatre fenêtres du ticket."""
import tempfile
import unittest
from unittest.mock import Mock, patch
from common import *
from test_prewarm import Sway
from path_stability_runtime import four_slots, UUID, UUID2
from session_v2.executor import Executor
from session_v2.recovery import Recovery, focus_proof
from session_v2.ipc import workspace, walk
from session_v2.errors import Failure


class PathTests(unittest.TestCase):
    def fixture(self, directory):
        sway = Sway()
        sway.add('kitty', 7, focus=False)
        sway.add('firefox', 8, focus=False)
        sway.add('firefox', 10)
        provider = Mock(resolve=lambda *args: {UUID: 8, UUID2: 10}, capture=lambda *args: {UUID: 8, UUID2: 10})
        engine = Executor(sway, Catalog(), provider, Path(directory), '/interdit', process_identity=lambda pid: 123)
        return sway, engine

    @staticmethod
    def unary(sway):
        ws = workspace(sway.value, '1')
        ws['nodes'] = [dict(id=90+i, type='con', layout='splitv' if i % 2 else 'splith', nodes=[n])
                       for i, n in enumerate(ws['nodes'])]

    def test_guard_refuse_les_divergences_avant_tout_ipc(self):
        for mode in ('ordre', 'pid', 'starttime', 'remplacement', 'extra', 'workspace', 'output',
                     'floating', 'focus-tiers', 'limusic-duplique'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                sway, engine = self.fixture(directory)
                # Le tiers appartient à la baseline, sans occuper un workspace cible.
                if mode == 'focus-tiers':
                    sway.value['nodes'][0]['nodes'].append(dict(id=50, type='workspace', name='tiers', nodes=[]))
                    sway.add('tiers', 51, 'tiers', focus=False)
                prepared, proof = engine._observe_prepared(), focus_proof(sway)
                anchors = Mock(owned=lambda n: False, close=lambda: None)
                def guard(recorded, *args):
                    self.unary(sway)
                    ws = workspace(sway.value, '1')
                    first = next(n for n in walk(ws) if n['id'] == 8)
                    if mode == 'ordre': ws['nodes'].reverse()
                    if mode == 'pid': first['pid'] = os.getppid()
                    if mode == 'starttime': engine.process_identity = lambda pid: 456
                    if mode == 'remplacement': first['id'] = 21
                    if mode == 'extra': sway.add('firefox', 21, focus=False)
                    if mode == 'workspace':
                        moved = ws['nodes'].pop(1)
                        workspace(sway.value, '10')['nodes'].append(moved)
                    if mode == 'output': sway.value['nodes'][0]['name'] = 'AUTRE'
                    if mode == 'floating': first['floating'] = 'user_on'
                    if mode == 'focus-tiers':
                        for node in walk(sway.value): node['focused'] = node['id'] == 51
                    if mode == 'limusic-duplique': sway.add('limusic-app', 22, '10', focus=False)
                    return Mock(ready={'helpers_suspended': 0}, finish=lambda: {'helpers_resumed': 0, 'anchors_cleaned': 0})
                with patch('session_v2.executor.Anchors', return_value=anchors), \
                     patch('session_v2.executor.Guard', side_effect=guard), patch.object(Recovery, 'recover'):
                    with self.assertRaises(Failure) as failure:
                        engine._apply(four_slots(), 1, -1, proof, prepared)
                expected = {'remplacement': 'APPLICATION_MEMBERSHIP_CHANGED', 'extra': 'APPLICATION_MEMBERSHIP_CHANGED',
                            'limusic-duplique': 'APPLICATION_MEMBERSHIP_CHANGED', 'focus-tiers': 'FOCUS_RECOVERY_NOT_PROVEN'}
                self.assertEqual(failure.exception.code, expected.get(mode, 'TARGET_OBSERVATION_CHANGED'))
                self.assertEqual(sway.commands, [], 'Aucun déplacement autorisé après divergence')
                anchors.build.assert_not_called()

    def test_changement_apres_capture_canonique_refuse_avant_deplacement(self):
        for mode in ('chemin', 'pid', 'starttime', 'remplacement', 'extra', 'focus', 'pending'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                sway, engine = self.fixture(directory)
                prepared, proof = engine._observe_prepared(), focus_proof(sway)
                anchors = Mock(owned=lambda n: False, close=lambda: None)
                guard = Mock(ready={'helpers_suspended': 0}, finish=lambda: {'helpers_resumed': 0, 'anchors_cleaned': 0})
                admit = Recovery.admit
                def changed(recovery, node, observed=None):
                    # La dernière fenêtre change après la capture du lot. Les
                    # premières admissions restent possibles, aucun move ne l'est.
                    if node['id'] == 10:
                        target = next(n for n in walk(sway.value) if n['id'] == 10)
                        if mode == 'chemin': self.unary(sway)
                        if mode == 'pid': target['pid'] += 1
                        if mode == 'starttime': recovery.start = lambda pid: 456
                        if mode == 'remplacement': target['id'] = 21
                        if mode == 'extra': sway.add('firefox', 21, focus=False)
                        if mode == 'focus':
                            for n in walk(sway.value): n['focused'] = n['id'] == 5
                    result = admit(recovery, node, observed)
                    if mode == 'pending' and node['id'] == 10:
                        recovery.data['windows'][0]['pending'] = True
                    return result
                with patch('session_v2.executor.Anchors', return_value=anchors), \
                     patch('session_v2.executor.Guard', return_value=guard), \
                     patch.object(Recovery, 'admit', changed), patch.object(Recovery, 'recover'):
                    with self.assertRaises(Failure) as failure:
                        engine._apply(four_slots(), 1, -1, proof, prepared)
                expected = {'pid': 'TARGET_IDENTITY_CHANGED', 'remplacement': 'TARGET_IDENTITY_CHANGED',
                            'extra': 'APPLICATION_MEMBERSHIP_CHANGED', 'focus': 'FOCUS_RECOVERY_NOT_PROVEN',
                            'pending': 'RECOVERY_STATE_CHANGED'}
                self.assertEqual(failure.exception.code, expected.get(mode, 'TARGET_OBSERVATION_CHANGED'))
                self.assertEqual(sway.commands, [])
                anchors.build.assert_not_called()


if __name__ == '__main__': unittest.main()
