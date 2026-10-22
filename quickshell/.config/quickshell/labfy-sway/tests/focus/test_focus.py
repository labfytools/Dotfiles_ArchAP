"""Simulation inerte : vrais Recovery/Executor, arbres synthétiques, aucun socket."""
import copy
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
ROOT = Path(os.environ.get('FOCUS_SOURCE', Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(ROOT))
from session_v2.recovery import Recovery, focused, recovery_status, JOURNAL
from session_v2.executor import Executor
from session_v2.applications import Catalog, launch_count
from session_v2.errors import Failure
from session_v2.ipc import walk
from session_v2.storage import read


def tree(focus=None):
    music = dict(id=5, type='con', app_id='limusic-app', pid=50, rect={}, nodes=[], floating_nodes=[], focused=focus == 5)
    third = dict(id=6, type='con', app_id='other', pid=60, rect={}, nodes=[], floating_nodes=[], focused=focus == 6)
    return dict(id=1, type='root', nodes=[dict(id=2, type='output', name='TEST', nodes=[
        dict(id=3, type='workspace', layout='splith', name='10', nodes=[music], focused=focus == 3),
        dict(id=4, type='workspace', layout='splith', name='1', nodes=[third], focused=focus == 4)])])


def fixture():
    return dict(schema='labfy.sway.session-v2', version=1,
        metadata=dict(created_ns=1, sway_session='previous', reason='manual'), outputs=[dict(name='TEST')],
        applications=[dict(application_id='limusic', desktop_entry='limusic.desktop', strategy='managed-autostart', expected_windows=1, managed_by='sway-autostart', identity_provider=None)],
        window_slots=[dict(slot_id='music', application_id='limusic', workspace='10', tree_path=[], state=dict(floating=False, geometry=None, fullscreen=False, scratchpad=False), identity_requirement='exact', identity_evidence=dict(type='application-singleton', id='limusic'))],
        workspaces=[dict(workspace='10', output='TEST', root=dict(slot_id='music'))], focus='music')


class FakeSway:
    session = 'a' * 64
    def __init__(self, focus=None): self.value, self.commands = tree(focus), []
    def tree(self): return copy.deepcopy(self.value)
    def windows(self): return [n for n in walk(self.tree()) if n.get('app_id')]
    def outputs(self): return [dict(name='TEST', active=True)]
    def command(self, text):
        self.commands.append(text)
        raise AssertionError('IPC mutante interdite dans cette fixture : ' + text)


class FocusTests(unittest.TestCase):
    def setUp(self):
        owner = patch('session_v2.executor.process_owner', return_value=os.getuid())
        owner.start(); self.addCleanup(owner.stop)
        socket_guard = patch('socket.socket', side_effect=AssertionError('socket réel interdit'))
        process_guard = patch('subprocess.Popen', side_effect=AssertionError('processus réel interdit'))
        socket_guard.start(); process_guard.start()
        self.addCleanup(socket_guard.stop); self.addCleanup(process_guard.stop)
    def test_null_preflight_creates_no_journal_or_pending(self):
        with tempfile.TemporaryDirectory() as tmp:
            sway = FakeSway()
            with patch('session_v2.executor.Anchors', side_effect=AssertionError('helper interdit')):
                with self.assertRaisesRegex(Failure, 'RESTORE_FOCUS_UNAVAILABLE'):
                    Executor(sway, Catalog(), None, Path(tmp), '/forbidden', process_identity=lambda pid: pid).apply(fixture(), True)
            self.assertEqual(sway.commands, [])
            self.assertEqual(list(Path(tmp).glob('*.json')), [])

    def test_late_preflight_focus_refusal_publishes_no_transaction(self):
        # La preuve initiale est bonne ; le retrait/retour concurrent de la
        # layer pendant preflight invalide la seconde preuve avant tout journal.
        for identity, change_at in ((None, 3), (5, 3), (None, 4), (5, 4)):
            with self.subTest(identity=identity, change_at=change_at), tempfile.TemporaryDirectory() as tmp:
                sway = FakeSway(6)
                from session_v2.executor import preflight
                calls = []
                def change(*args):
                    specs = preflight(*args)
                    calls.append(True)
                    if len(calls) == change_at: sway.value = tree(identity)
                    return specs
                with patch('session_v2.executor.preflight', side_effect=change):
                    with self.assertRaisesRegex(Failure, 'RESTORE_FOCUS_UNAVAILABLE|RESTORE_FOCUS_UNSTABLE'):
                        Executor(sway, Catalog(), None, Path(tmp), '/forbidden', process_identity=lambda pid: pid).apply(fixture(), True)
                self.assertEqual(sway.commands, [])
                self.assertEqual(list(Path(tmp).glob('*.json')), [])

    def test_deferred_survives_restart_but_not_new_decision_or_collision(self):
        from session_v2.startup import status, acknowledge
        from session_v2.storage import private_dir, lock
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp)
            sway = FakeSway()
            status(runtime, sway.session, fixture(), True)
            engine = Executor(sway, Catalog(), None, runtime, '/forbidden', process_identity=lambda pid: pid)
            with self.assertRaisesRegex(Failure, 'RESTORE_FOCUS_UNAVAILABLE'):
                engine.apply(fixture(), True)
            deferred = status(runtime, sway.session, fixture(), True)
            self.assertTrue(deferred['deferred'])
            self.assertEqual(deferred['deferred_reason'], 'RESTORE_FOCUS_UNAVAILABLE')
            with lock(private_dir(runtime / 'session-v2')):
                with self.assertRaisesRegex(Failure, 'TRANSACTION_BUSY'): engine.apply(fixture(), True)
                self.assertFalse(status(runtime, sway.session, fixture(), True)['deferred'])
            self.assertTrue(status(runtime, sway.session, fixture(), True)['deferred'])
            self.assertEqual(sway.commands, [])
            self.assertEqual(list(runtime.glob('*.json')), [])
            acknowledge(runtime, sway.session, 'new')
            self.assertFalse(status(runtime, sway.session, fixture(), True)['eligible'])

    def test_focus_refusal_preserves_previous_report(self):
        from session_v2.storage import atomic
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp)
            path = runtime / 'session-v2-restore-attempt.json'
            atomic(path, {'previous': 'untouched'})
            before = path.read_bytes()
            with self.assertRaisesRegex(Failure, 'RESTORE_FOCUS_UNAVAILABLE'):
                Executor(FakeSway(), Catalog(), None, runtime, '/forbidden', process_identity=lambda pid: pid).apply(fixture(), True)
            self.assertEqual(path.read_bytes(), before)
            self.assertFalse((runtime / JOURNAL).exists())

    def test_legacy_null_refusal_never_invents_pending(self):
        with tempfile.TemporaryDirectory() as tmp:
            sway = FakeSway()
            r = Recovery(sway, tmp, 'b' * 32, 'labfy-v2-stage-' + 'b' * 32, lambda pid: pid)
            r.baseline({'limusic-app'})
            r.admit(sway.windows()[0])
            with self.assertRaisesRegex(Failure, 'FOCUS_RECOVERY_NOT_PROVEN'):
                r.command('[con_id=5] move container to workspace "10"')
            receipt = r.recover()
            durable = read(Path(tmp) / JOURNAL)
            self.assertEqual(durable['focus_origin'], dict(con_id=None, workspace=None))
            self.assertEqual(sway.commands, [])
            self.assertEqual(durable['operations'], 0)
            self.assertFalse(durable['windows'][0]['pending'])
            self.assertIsNone(durable['intention'])
            self.assertEqual(receipt['status'], 'RECOVERY_REQUIRED')


# Les appels réseau et sous-processus sont interdits même si une régression
# contourne FakeSway. Seuls les helpers explicitement substitués sont autorisés.
class MutationSway(FakeSway):
    def __init__(self, focus=6):
        super().__init__(focus)
        self.runtime = None
        self.fail_at = None
        self.overlay_after = None
    def command(self, text):
        from session_v2.recovery import command_focus
        from session_v2.ipc import workspace
        import re
        import json
        durable = read(self.runtime / JOURNAL)
        assert durable['intention']['command'] == text
        assert 'expected_after' in durable['intention']
        assert durable['focus_pending']
        assert all(e['pending'] for e in durable['windows'])
        self.commands.append(text)
        if self.fail_at == len(self.commands): raise OSError('simulation panne IPC')
        match = re.match(r'\[con_id=(\d+)\] (.*)', text)
        target, operation = (int(match[1]), match[2]) if match else (None, text)
        expected = command_focus(self.value, target, operation)
        if operation.startswith('move container to workspace '):
            name = json.loads(operation.removeprefix('move container to workspace '))
            node = next(n for n in walk(self.value) if n['id'] == target)
            for parent in list(walk(self.value)):
                if node in parent.get('nodes', []): parent['nodes'].remove(node); break
            destination = workspace(self.value, name)
            if destination is None:
                destination = dict(id=100 + len(self.commands), type='workspace', layout='splith', name=name, nodes=[])
                self.value['nodes'][0]['nodes'].append(destination)
            destination['nodes'].append(node)
        elif not (operation.startswith('workspace ') or operation == 'focus' or operation == 'floating disable'):
            raise AssertionError('commande non simulée : ' + text)
        for n in walk(self.value):
            n['focused'] = n['id'] == expected['con_id'] if expected['con_id'] is not None else (n.get('type') == 'workspace' and n.get('name') == expected['workspace'])
        if self.overlay_after == len(self.commands):
            for n in walk(self.value): n['focused'] = False

class HelperAnchors:
    def __init__(self, sway, data, *args): self.sway, self.data = sway, data
    def owned(self, node): return False
    def build(self, progress): pass
    def swap(self, slot, target, workspace, stage, ids): self.sway.command(f'[con_id={target["id"]}] move container to workspace "{workspace}"')
    def cleanup(self, progress): pass
    def verify(self, mapping, tree=None):
        if mapping:
            from session_v2.ipc import canonical
            assert canonical(self.sway.tree() if tree is None else tree, '10', {5: 'music'}) == 'music'
    def close(self): pass

class HelperGuard:
    ready = dict(helpers_suspended=0)
    def __init__(self, *args): pass
    def prepare(self): return dict(status="prepared")
    def resume(self): return dict(helpers_resumed=0)
    def finish(self): return dict(helpers_resumed=0, anchors_cleaned=0)

class ExtendedTests(unittest.TestCase):
    def setUp(self):
        owner = patch('session_v2.executor.process_owner', return_value=os.getuid())
        owner.start(); self.addCleanup(owner.stop)
        self.block_socket = patch('socket.socket', side_effect=AssertionError('socket réel interdit'))
        self.block_process = patch('subprocess.Popen', side_effect=AssertionError('processus réel interdit'))
        self.block_socket.start(); self.block_process.start()
        self.addCleanup(self.block_socket.stop); self.addCleanup(self.block_process.stop)
    def execute(self, sway, runtime):
        sway.runtime = runtime
        with patch('session_v2.executor.Anchors', HelperAnchors), patch('session_v2.executor.Guard', HelperGuard):
            return Executor(sway, Catalog(), None, runtime, '/forbidden', process_identity=lambda pid: pid).apply(fixture(), True)
    def test_null_then_valid_real_executor_success_unique_music(self):
        with tempfile.TemporaryDirectory() as tmp:
            sway = MutationSway(None)
            self.assertEqual(focused(sway.tree()), dict(con_id=None, workspace=None))
            from session_v2.startup import status
            status(Path(tmp), sway.session, fixture(), True)
            with self.assertRaisesRegex(Failure, 'RESTORE_FOCUS_UNAVAILABLE'):
                self.execute(sway, Path(tmp))
            self.assertTrue(status(Path(tmp), sway.session, fixture(), True)['deferred'])
            sway.value = tree(6)  # Simulation explicite du retrait de layer-shell.
            foreign = copy.deepcopy(sway.windows()[1])
            result = self.execute(sway, Path(tmp))
            self.assertEqual(result['status'], 'success')
            self.assertTrue(result['final_focus_verified'])
            self.assertEqual(len([n for n in sway.windows() if n['app_id'] == 'limusic-app']), 1)
            self.assertEqual(next(n for n in sway.windows() if n['id'] == 6), foreign)
            self.assertEqual(focused(sway.tree()), dict(con_id=6, workspace='1'))
            self.assertEqual(recovery_status(tmp)['status'], 'complete')
            self.assertFalse(status(Path(tmp), sway.session, fixture(), True)['deferred'])
    def test_watchdog_boundary_focus_changes_refuse_without_refocusing(self):
        for phase, boundary in (('prepare', 'after-guard-prepare'),
                                ('resume', 'after-helper-resume'),
                                ('finish', 'after-guard-finish')):
            with self.subTest(phase=phase), tempfile.TemporaryDirectory() as tmp:
                sway = MutationSway(6)
                sway.runtime = Path(tmp)
                class ChangedGuard(HelperGuard):
                    def change(self):
                        for n in walk(sway.value): n['focused'] = n['id'] == 5
                    def prepare(self):
                        if phase == 'prepare': self.change()
                        return super().prepare()
                    def resume(self):
                        if phase == 'resume': self.change()
                        return super().resume()
                    def finish(self):
                        if phase == 'finish': self.change()
                        return super().finish()
                with patch('session_v2.executor.Anchors', HelperAnchors), patch('session_v2.executor.Guard', ChangedGuard):
                    with self.assertRaisesRegex(Failure, 'RECOVERY_FOCUS_MISMATCH'):
                        Executor(sway, Catalog(), None, Path(tmp), '/forbidden', process_identity=lambda pid: pid).apply(fixture(), True)
                report = read(Path(tmp)/'session-v2-restore-attempt.json')
                journal = read(Path(tmp)/JOURNAL)
                self.assertTrue(report['final_tree_verified'])
                self.assertFalse(report['final_focus_verified'])
                self.assertEqual(journal['focus_conflict_observation']['command'], boundary)
                self.assertEqual(journal['focus_boundaries'][-1]['boundary'], boundary)
                self.assertEqual(focused(sway.tree()), dict(con_id=5, workspace='10'))
                # After the unexpected focus, even recovery emits no refocus.
                expected = 0 if phase == 'prepare' else 1
                self.assertEqual(sum(text == '[con_id=6] focus' for text in sway.commands), expected)

    def test_snapshot_focus_retained_when_baseline_belongs_to_batch(self):
        with tempfile.TemporaryDirectory() as tmp:
            sway = MutationSway(5)
            result = self.execute(sway, Path(tmp))
            self.assertEqual(result['status'], 'success')
            self.assertEqual(focused(sway.tree()), dict(con_id=5, workspace='10'))

    def test_ipc_failure_mid_operation_stays_ambiguous(self):
        with tempfile.TemporaryDirectory() as tmp:
            sway = MutationSway(); sway.fail_at = 2
            with self.assertRaises(Failure): self.execute(sway, Path(tmp))
            durable = read(Path(tmp) / JOURNAL)
            self.assertEqual(durable['status'], 'required')
            self.assertTrue(durable['windows'][0]['pending'])
            self.assertEqual(durable['intention']['command'], sway.commands[-1])
            self.assertEqual(len(sway.commands), 2)
    def test_layer_reappears_during_restore_no_next_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            sway = MutationSway(); sway.overlay_after = 1
            with self.assertRaisesRegex(Failure, 'RECOVERY_FOCUS_MISMATCH'): self.execute(sway, Path(tmp))
            self.assertEqual(len(sway.commands), 1)
            self.assertEqual(recovery_status(tmp)['status'], 'RECOVERY_REQUIRED')
    def test_session_pid_con_id_reuse_never_recovered(self):
        with tempfile.TemporaryDirectory() as tmp:
            sway = FakeSway(6)
            r = Recovery(sway, tmp, 'b'*32, 'labfy-v2-stage-'+'b'*32, lambda pid: pid)
            r.admit(sway.windows()[0])
            sway.session = 'c'*64  # Même con_id/PID, nouvelle autorité compositeur.
            receipt = r.recover()
            self.assertEqual(receipt['windows'][0]['reason'], 'SESSION_CHANGED')
            self.assertEqual(sway.commands, [])
    def test_process_starttime_reuse_never_recovered(self):
        with tempfile.TemporaryDirectory() as tmp:
            sway = FakeSway(6)
            r = Recovery(sway, tmp, 'b'*32, 'labfy-v2-stage-'+'b'*32, lambda pid: pid)
            r.admit(sway.windows()[0]); r.start = lambda pid: pid + 1
            self.assertEqual(r.recover()['windows'][0]['reason'], 'IDENTITY_OR_MEMBERSHIP_CHANGED')
            self.assertEqual(sway.commands, [])
    def test_structural_and_workspace_focus_proven_no_invented_leaf(self):
        from session_v2.recovery import focus_proof
        for identity in (3, 4, 6):
            sway = FakeSway(identity)
            self.assertEqual(focus_proof(sway)[1][0], focused(sway.value))
        sway = FakeSway()
        sway.value['nodes'][0]['nodes'][0]['nodes'] = [dict(id=7, type='con', nodes=sway.value['nodes'][0]['nodes'][0]['nodes'], focused=True)]
        self.assertEqual(focus_proof(sway)[1][0], dict(con_id=7, workspace='10'))
        sway.value['nodes'][0]['nodes'][1]['focused'] = True
        with self.assertRaisesRegex(Failure, 'RESTORE_FOCUS_UNAVAILABLE'): focus_proof(sway)
    def test_external_focus_change_is_never_refocused(self):
        with tempfile.TemporaryDirectory() as tmp:
            sway = FakeSway(6)
            r = Recovery(sway, tmp, 'b'*32, 'labfy-v2-stage-'+'b'*32, lambda pid: pid)
            r.baseline({'limusic-app'}); r.admit(sway.windows()[0])
            sway.value = tree(5)
            with self.assertRaisesRegex(Failure, 'FOCUS_RECOVERY_NOT_PROVEN'):
                r.command('[con_id=5] move container to workspace "stage"')
            self.assertEqual(sway.commands, [])
            self.assertFalse(read(Path(tmp)/JOURNAL)['windows'][0]['pending'])
    def test_idle_after_archive_and_limusic_launch_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(recovery_status(tmp), dict(status='idle', reason='NO_RECOVERY_JOURNAL'))
        for n in (0, 1): self.assertEqual(launch_count(fixture()['applications'][0], n), 0)
    def test_unstable_and_changed_session_focus_preflight(self):
        from session_v2.recovery import focus_proof
        for mode in ('focus', 'session'):
            sway = FakeSway(6); original = sway.tree; calls = []
            def changing():
                calls.append(1)
                if len(calls) == 2:
                    if mode == 'focus': sway.value = tree(5)
                    else: sway.session = 'd'*64
                return original()
            sway.tree = changing
            with self.assertRaisesRegex(Failure, 'RESTORE_FOCUS_UNSTABLE|SWAY_SESSION_CHANGED'): focus_proof(sway)
            self.assertEqual(sway.commands, [])
    def test_startup_claim_restart_and_backend_lock(self):
        from session_v2.startup import status, acknowledge
        from session_v2.storage import private_dir, lock
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp)
            first = status(runtime, 'session', fixture(), True)
            self.assertTrue(first['claimed']); self.assertFalse(first['interrupted'])
            self.assertTrue(status(runtime, 'session', fixture(), True)['interrupted'])
            with lock(private_dir(runtime/'session-v2')):
                self.assertTrue(status(runtime, 'session', fixture(), True)['in_progress'])
            acknowledge(runtime, 'session', 'new')
            self.assertFalse(status(runtime, 'session', fixture(), True)['eligible'])

    def test_third_party_placement_and_focus_unchanged_by_unfocused_move(self):
        with tempfile.TemporaryDirectory() as tmp:
            sway = MutationSway(); sway.runtime = Path(tmp)
            r = Recovery(sway, tmp, 'b'*32, 'labfy-v2-stage-'+'b'*32, lambda pid: pid)
            r.baseline({'limusic-app'}); r.admit(sway.windows()[0])
            before = r.snapshot(6)
            r.command('[con_id=5] move container to workspace "10"')
            self.assertEqual(r.snapshot(6), before)
            self.assertEqual(focused(sway.tree()), dict(con_id=6, workspace='1'))
    def test_first_ipc_crash_even_at_origin_remains_ambiguous(self):
        with tempfile.TemporaryDirectory() as tmp:
            sway = MutationSway(); sway.fail_at = 1
            with self.assertRaises(Failure): self.execute(sway, Path(tmp))
            durable = read(Path(tmp)/JOURNAL)
            self.assertTrue(durable['windows'][0]['pending'])
            self.assertEqual(durable['status'], 'required')
            self.assertEqual(recovery_status(tmp)['windows'][0]['reason'], 'AMBIGUOUS_INTENTION')

    def test_first_focus_observation_survives_cleanup_and_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            sway = FakeSway(4)  # Workspace explicite, aucune feuille active.
            r = Recovery(sway, tmp, 'b'*32, 'labfy-v2-stage-'+'b'*32, lambda pid: pid)
            r.admit(sway.windows()[0])
            sway.value = tree(5)
            with self.assertRaisesRegex(Failure, 'FOCUS_RECOVERY_NOT_PROVEN'):
                r.command('[con_id=5] move container to workspace "stage"')
            first = read(Path(tmp)/JOURNAL)['focus_conflict_observation']
            self.assertEqual(first['phase'], 'before-command')
            self.assertEqual(first['before'], dict(con_id=None, workspace='1'))
            self.assertEqual(first['observed'], dict(con_id=5, workspace='10'))
            # Une nouvelle instance simule le guard ; ni son refus local ni
            # une divergence post-IPC tardive ne doivent effacer cet indice.
            r = Recovery(sway, tmp, start=lambda pid: pid)
            with self.assertRaises(Failure):
                r.check_focus_preservation(sway.tree(), dict(con_id=6, workspace='1'), '[con_id=8] kill')
            with self.assertRaises(Failure):
                r.check_command_focus(sway.tree(), dict(con_id=6, workspace='1'), 'cleanup')
            r.recover()
            self.assertEqual(read(Path(tmp)/JOURNAL)['focus_conflict_observation'], first)
            self.assertEqual(sway.commands, [])

    def test_readmission_preserves_pinned_runtime_identity(self):
        for change in ('pid', 'starttime', 'app_id', 'session'):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as tmp:
                sway = FakeSway(4)
                r = Recovery(sway, tmp, 'b'*32, 'labfy-v2-stage-'+'b'*32, lambda pid: pid)
                r.admit(sway.windows()[0])
                before = read(Path(tmp)/JOURNAL)
                if change == 'starttime': r.start = lambda pid: pid + 1
                elif change == 'session': sway.session = 'c'*64
                else: sway.value['nodes'][0]['nodes'][0]['nodes'][0][change] = 999 if change == 'pid' else 'other'
                with self.assertRaisesRegex(Failure, 'TARGET_IDENTITY_CHANGED|SWAY_SESSION_CHANGED'):
                    r.admit(sway.windows()[0])
                self.assertEqual(read(Path(tmp)/JOURNAL), before)
                self.assertEqual(sway.commands, [])

    def test_foreign_focus_conflict_blocks_even_focus_neutral_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            sway = FakeSway(4)
            r = Recovery(sway, tmp, 'b'*32, 'labfy-v2-stage-'+'b'*32, lambda pid: pid)
            r.baseline({'limusic-app'}); r.admit(sway.windows()[0])
            sway.value = tree(6)  # Le tiers devient actif, Limusic reste en 10.
            with self.assertRaisesRegex(Failure, 'FOCUS_RECOVERY_NOT_PROVEN'):
                r.command('[con_id=5] move container to workspace "10"')
            self.assertEqual(sway.commands, [])
            self.assertEqual(r.data['operations'], 0)
            r = Recovery(sway, tmp, start=lambda pid: pid)
            with self.assertRaisesRegex(Failure, 'FOCUS_RECOVERY_NOT_PROVEN'):
                r.recovery_command('[con_id=5] floating disable')
            self.assertEqual(sway.commands, [])

    def test_owned_anchor_map_does_not_authorize_unowned_focus(self):
        # L'exception historique de helper exige une propriété runtime ; le
        # préfixe app_id seul ne suffit pas, même avant toute permutation.
        with tempfile.TemporaryDirectory() as tmp:
            sway = FakeSway(4)
            r = Recovery(sway, tmp, 'b'*32, 'labfy-v2-stage-'+'b'*32, lambda pid: pid)
            n = sway.value['nodes'][0]['nodes'][1]['nodes'][0]
            n.update(id=8, app_id='labfy-v2-anchor-faux', pid=80, focused=True)
            sway.value['nodes'][0]['nodes'][1]['focused'] = False
            r.anchor_owned = lambda node: node.get('pid') == 90
            with self.assertRaisesRegex(Failure, 'FOCUS_RECOVERY_NOT_PROVEN'):
                r.command('[con_id=8] focus')
            self.assertEqual(sway.commands, [])

    def test_new_map_focus_is_not_authorized_by_admission(self):
        # Cas réduit du login : Limusic existe en 10, aucune Firefox/Kitty,
        # focus workspace 1 ; les nouveaux clients apparaissent après stage.
        # Le faux IPC sert à injecter le timing, jamais à prouver Sway réel.
        with tempfile.TemporaryDirectory() as tmp:
            sway = MutationSway(4); sway.runtime = Path(tmp)
            sway.value['nodes'][0]['nodes'][1]['nodes'] = []
            r = Recovery(sway, tmp, 'b'*32, 'labfy-v2-stage-'+'b'*32, lambda pid: pid)
            r.admit(sway.windows()[0])
            stage = r.data['stage']
            r.command('[con_id=5] move container to workspace "' + stage + '"')
            r.command('workspace "' + stage + '"')
            from session_v2.ipc import workspace
            for identity, app_id in ((13, 'firefox'), (14, 'kitty')):
                n = dict(id=identity, type='con', app_id=app_id, pid=identity*10,
                         rect={}, nodes=[], floating_nodes=[], focused=False)
                workspace(sway.value, stage)['nodes'].append(n)
                # Injection déterministe au map, pas une conclusion causale.
                for item in walk(sway.value): item['focused'] = item['id'] == identity
                r.admit(n)
            self.assertEqual(len(r.data['windows']), 3)
            before = len(sway.commands)
            with self.assertRaisesRegex(Failure, 'FOCUS_RECOVERY_NOT_PROVEN'):
                r.command('workspace "1"')
            self.assertEqual(len(sway.commands), before)
            self.assertEqual(r.data['focus_conflict_observation']['observed'], dict(con_id=14, workspace=stage))
            self.assertTrue(all(not e['pending'] for e in r.data['windows']))

    def test_focus_change_during_guard_finish_never_publishes_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            sway = MutationSway(6)
            class LateGuard(HelperGuard):
                def finish(self):
                    for n in walk(sway.value): n['focused'] = n['id'] == 5
                    return super().finish()
            sway.runtime = Path(tmp)
            with patch('session_v2.executor.Anchors', HelperAnchors), patch('session_v2.executor.Guard', LateGuard):
                with self.assertRaisesRegex(Failure, 'RECOVERY_FOCUS_MISMATCH'):
                    Executor(sway, Catalog(), None, Path(tmp), '/forbidden', process_identity=lambda pid: pid).apply(fixture(), True)
            report = read(Path(tmp) / 'session-v2-restore-attempt.json')
            self.assertFalse(report['final_focus_verified'])
            self.assertEqual(report['status'], 'failed')
            self.assertTrue(read(Path(tmp) / JOURNAL)['focus_conflict'])
            self.assertEqual(focused(sway.tree()), dict(con_id=5, workspace='10'))

    def test_complete_refuses_an_empty_stage_even_when_it_is_expected(self):
        with tempfile.TemporaryDirectory() as tmp:
            sway = FakeSway(4)
            stage = 'labfy-v2-stage-'+'b'*32
            sway.value['nodes'][0]['nodes'][1].update(name=stage, nodes=[])
            r = Recovery(sway, tmp, 'b'*32, stage, lambda pid: pid)
            with self.assertRaisesRegex(Failure, 'FINAL_FOCUS_IN_STAGE'): r.complete()
            self.assertEqual(read(Path(tmp) / JOURNAL)['status'], 'active')
            self.assertEqual(sway.commands, [])

    def test_first_admission_checks_observation_before_provider_wait(self):
        for change in ('starttime', 'pid', 'app_id', 'workspace', 'session'):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as tmp:
                sway = FakeSway(4)
                r = Recovery(sway, tmp, 'b'*32, 'labfy-v2-stage-'+'b'*32, lambda pid: pid)
                node = sway.windows()[0]
                pinned = r.pin(node)
                before = (Path(tmp)/JOURNAL).read_bytes()
                if change == 'starttime': r.start = lambda pid: pid+1
                elif change == 'session': sway.session = 'c'*64
                elif change == 'workspace': sway.value['nodes'][0]['nodes'][0]['name'] = 'moved'
                else: sway.value['nodes'][0]['nodes'][0]['nodes'][0][change] = 999 if change == 'pid' else 'other'
                with self.assertRaisesRegex(Failure, 'TARGET_OBSERVATION_CHANGED|TARGET_IDENTITY_CHANGED|SWAY_SESSION_CHANGED'):
                    r.admit(node, pinned)
                self.assertEqual((Path(tmp)/JOURNAL).read_bytes(), before)
                self.assertEqual(sway.commands, [])

    def test_pinned_observation_admits_without_granting_focus_authority(self):
        with tempfile.TemporaryDirectory() as tmp:
            sway = FakeSway(4)
            r = Recovery(sway, tmp, 'b'*32, 'labfy-v2-stage-'+'b'*32, lambda pid: pid)
            node = sway.windows()[0]
            pinned = r.pin(node)
            sway.value = tree(5)  # Identité/placement exacts, focus concurrent.
            r.admit(node, pinned)
            with self.assertRaisesRegex(Failure, 'FOCUS_RECOVERY_NOT_PROVEN'):
                r.command('[con_id=5] move container to workspace "10"')
            self.assertEqual(sway.commands, [])
            self.assertEqual(r.data['focus_expected'], dict(con_id=None, workspace='1'))

    def test_readmission_refuses_pending_or_changed_placement(self):
        for change in ('pending', 'workspace'):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as tmp:
                sway = FakeSway(4)
                r = Recovery(sway, tmp, 'b'*32, 'labfy-v2-stage-'+'b'*32, lambda pid: pid)
                node = sway.windows()[0]
                r.admit(node)
                if change == 'pending': r.data['windows'][0]['pending'] = True; r.publish()
                else: sway.value['nodes'][0]['nodes'][0]['name'] = 'elsewhere'
                before = (Path(tmp)/JOURNAL).read_bytes()
                with self.assertRaisesRegex(Failure, 'RECOVERY_STATE_CHANGED'): r.admit(node)
                self.assertEqual((Path(tmp)/JOURNAL).read_bytes(), before)
                self.assertEqual(sway.commands, [])

if __name__ == '__main__': unittest.main()
