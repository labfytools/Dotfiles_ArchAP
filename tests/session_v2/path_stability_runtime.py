"""Quatre slots réels TEST_ONLY ; injection unaire aux frontières de Guard.

Les UUID sont synthétiques et stables, même pour deux Firefox de même PID.
Aucun résultat de ce laboratoire ne valide le login graphique physique.
"""
from unittest.mock import patch
from common import *
from lab import Lab, Surfaces, build_helper
from login_focus import checkpoint, UUID
from session_v2.executor import Executor
from session_v2.guard import Guard, verify_helper
from session_v2.anchors import Anchors
from session_v2.ipc import Sway, canonical
from session_v2.recovery import focus_proof, JOURNAL
from session_v2.storage import private_dir, read, atomic
from session_v2.errors import Failure

UUID2 = '22345678-1234-4234-8234-123456789abc'


def four_slots():
    data = checkpoint()
    second = copy.deepcopy(next(s for s in data['window_slots'] if s['slot_id'] == 'F'))
    second.update(slot_id='G', tree_path=[1, 0], identity_evidence={'type': 'firefox-session-window-uuid', 'id': UUID2})
    data['window_slots'].append(second)
    for slot in data['window_slots']:
        if slot['slot_id'] == 'F': slot['tree_path'] = [0]
        if slot['slot_id'] == 'K': slot['tree_path'] = [1, 1]
    next(a for a in data['applications'] if a['application_id'] == 'firefox')['expected_windows'] = 2
    data['workspaces'][0]['root'] = {'layout': 'splitv', 'children': [
        {'slot_id': 'F'}, {'layout': 'splith', 'children': [{'slot_id': 'G'}, {'slot_id': 'K'}]}]}
    return validate(data)


def run_case(case):
    row = {'scenario': case, 'test_only': True, 'login_physique_valide': False, 'commands': [], 'injections': []}
    with Lab() as lab:
        apps = Surfaces(lab, build_helper(lab.directory))
        try:
            lab.command('workspace "10"')
            music = apps.create('limusic-app')
            lab.command('workspace "1"')
            kitty = apps.create('kitty')
            first, second = apps.create('firefox'), apps.create('firefox')
            sway = Sway(lab.socket)
            engine = Executor(sway, Catalog(), None, private_dir(lab.directory / 'restore'), build(lab.directory), lab.env)
            identities = {UUID: first['id'], UUID2: second['id']}
            class Provider:
                def resolve(self, expected, nodes):
                    row['commands_avant_provider'] = len(row['commands'])
                    if case == 'provider-unaire': inject('provider')
                    return identities.copy()
                def capture(self, nodes): return identities.copy()
            engine.provider = Provider()
            raw_command = sway.command
            def command(text):
                row['commands'].append(text)
                return raw_command(text)
            sway.command = command
            def inject(phase):
                before, proof = engine._observe_prepared(), focus_proof(sway)
                for node, layout in ((kitty, 'splitv'), (first, 'splith'), (second, 'splitv')):
                    if case == 'deux-frontieres' and ((phase == 'apres-phase0') != (node['id'] == kitty['id'])):
                        continue
                    lab.command(f'[con_id={node["id"]}] {layout}')
                after = engine._observe_prepared()
                engine._check_prepared(before, after)
                assert before != after, ('Injection sans changement de chemin', before, after)
                assert proof[0] == focus_proof(sway)[0] and proof[1][0] == focus_proof(sway)[1][0], 'Focus modifié'
                row['injections'].append({'phase': phase, 'before': {str(k): v for k, v in before.items()}, 'after': {str(k): v for k, v in after.items()}})
            def anchors(*args):
                value = Anchors(*args)
                # Après la preuve de phase0 validée par Recovery, avant Guard.
                if case in ('apres-phase0', 'deux-frontieres'): inject('apres-phase0')
                return value
            helper = None
            if case == 'autotiling-guard':
                helper = lab.spawn(['/usr/bin/autotiling'])
                time.sleep(.2)
                assert helper.poll() is None, 'Autotiling enfant arrêté'
            def discover_owned(socket):
                # Seul cet enfant est inspecté/signalé, jamais les helpers du bureau.
                if helper is None: return []
                verify_helper(helper.pid, socket, '/usr/bin/autotiling')
                return [{'pid': helper.pid, 'fd': os.pidfd_open(helper.pid), 'script': '/usr/bin/autotiling'}]
            def guard(*args):
                value = Guard(*args)
                if case in ('pendant-guard', 'deux-frontieres', 'autotiling-guard'): inject('pendant-guard')
                return value
            with patch('session_v2.executor.Anchors', side_effect=anchors), \
                 patch('session_v2.executor.Guard', side_effect=guard), \
                 patch('session_v2.guard.discover', side_effect=discover_owned), \
                 patch('session_v2.executor.launch', side_effect=AssertionError('Lancement interdit')):
                try:
                    report = engine.apply(four_slots(), True)
                    row['resultat'] = 'success'
                except Failure as exc:
                    row['resultat'] = exc.code
                    report = read(engine.runtime / 'session-v2-restore-attempt.json')
            row.update(report=report, journal=read(engine.runtime / JOURNAL), final=sway.tree())
            atomic(private_dir(EVIDENCE) / ('chemins-'+case+'.json'), row)
            if case == 'provider-unaire':
                assert row['resultat'] == 'TARGET_OBSERVATION_CHANGED', row['resultat']
                assert report['anchors_swapped'] == 0
                # Recovery peut tenter son cleanup ensuite ; aucune commande
                # normale ne suit la divergence observée pendant le provider.
                assert row['commands'][row['commands_avant_provider']:] == []
                print(case, 'SUCCÈS : changement externe refusé avant IPC suivant', flush=True)
                return
            if helper is not None:
                assert report['helpers_suspended'] == report['helpers_resumed'] == 1
            assert row['resultat'] == 'success', (row['resultat'], len(row['commands']))
            assert report['anchors_swapped'] == report['slots_filled'] == 4, report
            assert report['final_tree_verified'] and report['final_focus_verified']
            assert row['journal']['status'] == 'complete'
            names = {first['id']: 'F', second['id']: 'G', kitty['id']: 'K', music['id']: 'M'}
            assert canonical(sway.tree(), '1', names) == {'splitv': ['F', {'splith': ['G', 'K']}]}
            assert canonical(sway.tree(), '10', names) == 'M'
            assert len([n for n in sway.windows() if n['app_id'] == 'limusic-app']) == 1
            print(case, 'SUCCÈS : quatre swaps, quatre slots, arbre exact, focus vérifié', flush=True)
        finally: apps.close()


if __name__ == '__main__':
    for case in ('pendant-guard', 'apres-phase0', 'deux-frontieres', 'autotiling-guard', 'provider-unaire'): run_case(case)
