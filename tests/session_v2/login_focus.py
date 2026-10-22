"""Vérité TEST_ONLY : succès naturel requis, jamais un refus renommé PASS.

Vrais Executor/Recovery/Guard/Anchors ; surfaces GTK possédées et provider UUID
synthétique. Ce laboratoire ne valide ni Firefox réel ni le premier login réel.
Chaque scénario a un compositeur et des PID privés distincts.
"""
import argparse
import json
import socket
import struct
import threading
from unittest.mock import patch
from common import *
from lab import Lab, Surfaces, build_helper
from session_v2.executor import Executor
from session_v2.guard import Guard
from session_v2.applications import launch as real_launch
from dataclasses import replace
from session_v2.recovery import JOURNAL, focused, process_start, Recovery, recovery_status
from session_v2.ipc import Sway, location, canonical, until
from session_v2.storage import private_dir, atomic, read
from session_v2.errors import Failure

UUID = '12345678-1234-4234-8234-123456789abc'


def checkpoint():
    data = fixture({'splith': ['F', 'K']}, '1')
    music = fixture('M', '10')
    data['applications'] += music['applications']
    data['window_slots'] += music['window_slots']
    data['workspaces'] += music['workspaces']
    policies = {'F': ('firefox', 'browser-self-restore', 'firefox-session-window-uuid', None),
                'K': ('kitty', 'terminal', None, None),
                'M': ('limusic', 'managed-autostart', None, 'sway-autostart')}
    for app, slot in zip(data['applications'], data['window_slots']):
        name, strategy, provider, owner = policies[slot['slot_id']]
        app.update(application_id=name, desktop_entry=name+'.desktop', strategy=strategy,
                   identity_provider=provider, managed_by=owner)
        slot.update(application_id=name, identity_evidence={
            'type': 'firefox-session-window-uuid' if provider else 'application-singleton',
            'id': UUID if provider else name})
    data['applications'] = [data['applications'][2], data['applications'][1], data['applications'][0]]
    data['focus'] = None
    return validate(data)


class Events:
    """Trace IPC bornée ; ordonne les observations sans attribuer leur cause."""
    def __init__(self, path):
        assert path.startswith('/tmp/labfy-session-v2-TEST_ONLY-')
        self.rows, self.error, self.stopping = [], None, False
        self.connection = socket.socket(socket.AF_UNIX)
        self.connection.settimeout(3)
        self.connection.connect(path)
        payload = b'["window","workspace"]'
        self.connection.sendall(struct.pack('<6sII', b'i3-ipc', len(payload), 2) + payload)
        _, answer = self.receive()
        assert answer.get('success'), answer
        self.thread = threading.Thread(target=self.collect, daemon=True)
        self.thread.start()

    def receive(self):
        def take(size):
            data = bytearray()
            while len(data) < size:
                part = self.connection.recv(size-len(data))
                if not part: raise EOFError('TRACE_CLOSED')
                data.extend(part)
            return data
        magic, size, kind = struct.unpack('<6sII', take(14))
        assert magic == b'i3-ipc' and size <= 4*1024*1024
        return kind, json.loads(take(size))

    def collect(self):
        try:
            while not self.stopping:
                try: kind, row = self.receive()
                except socket.timeout: continue
                if len(self.rows) >= 2048: raise RuntimeError('TRACE_EVENT_LIMIT')
                node = row.get('container') or row.get('current') or {}
                self.rows.append({'ns': time.monotonic_ns(), 'kind': kind,
                                  'change': row.get('change'),
                                  'node': {k: node.get(k) for k in ('id','pid','app_id','focused','name')}})
        except Exception as exc:
            if not self.stopping: self.error = str(exc)

    def close(self):
        self.stopping = True
        self.connection.shutdown(socket.SHUT_RDWR)
        self.thread.join(timeout=4)
        self.connection.close()
        assert not self.thread.is_alive() and self.error is None, self.error


def run_case(case):
    evidence = {'test_only': True, 'scenario': case, 'real_login_validated': False,
                'real_applications': False, 'commands': [], 'observations': []}
    with Lab() as lab:
        evidence.update(lab=str(lab.directory), version=lab.ipc(kind='get_version'))
        binary = build_helper(lab.directory)
        apps = Surfaces(lab, binary)
        events = Events(lab.socket)
        try:
            lab.command('workspace "10"')
            music = apps.create('limusic-app')
            lab.command('workspace "1"')
            sway = Sway(lab.socket)
            assert focused(sway.tree()) == {'con_id': None, 'workspace': '1'}
            assert len(sway.windows()) == 1
            music_identity = (music['id'], music['pid'], process_start(music['pid']))
            launched, mapping_threads, mapping_errors = [], [], []
            def observe(phase):
                tree = sway.tree()
                if phase in ('before-executor', 'after-executor'):
                    evidence.setdefault('trees', {})[phase] = tree
                value = {'phase': phase, 'ns': time.monotonic_ns(), 'focus': focused(tree),
                         'windows': [{k: n.get(k) for k in ('id','pid','app_id')} |
                                     {'starttime': process_start(n['pid']),
                                      'location': [location(tree, n['id'])[0], list(location(tree, n['id'])[1])]}
                                     for n in sway.windows()]}
                evidence['observations'].append(value)
                return value
            foreign = Surfaces(lab, binary)
            foreign_node = None
            if case in ('focus-third-party', 'preserve-foreign', 'focus-external-late'):
                lab.command('workspace "TEST_ONLY_OTHER"')
                foreign_node = foreign.create('TEST_ONLY_foreign')
                lab.command('workspace "1"')
            if case in ('preserve-empty-workspace', 'preserve-foreign'):
                apps.create('kitty')
                apps.create('firefox')
                if case == 'preserve-empty-workspace': lab.command('workspace "TEST_ONLY_EMPTY"')
                else: lab.command(f'[con_id={foreign_node["id"]}] focus')
                evidence['preserved_focus'] = focused(sway.tree())
            observe('before-executor')
            test_catalog = Catalog()
            if case in ('natural', 'launch-failure-retry'):
                test_catalog = Catalog(tuple(replace(spec, argv=(str(binary), '--app-id', spec.app_ids[0],
                                                  '50' if spec.application_id == 'kitty' else '150'))
                                             if spec.application_id != 'limusic' else spec
                                             for spec in test_catalog.specs.values()))
            def launch_surface(spec, count, env):
                if spec.application_id == 'limusic':
                    assert count == 0, 'DUPLICATE_LIMUSIC'
                    return []
                assert count == 1
                if case in ('natural', 'launch-failure-retry'):
                    launched.append(spec.application_id)
                    children = real_launch(spec, count, env)
                    lab.children.extend(children)  # Enfants TEST_ONLY détenus pour cleanup du Lab.
                    return children
                launched.append(spec.application_id)
                # Retour avant mapping : Executor doit réellement attendre les
                # cartes, sans sélection de workspace ni journal prématuré.
                def mapping():
                    try:
                        time.sleep(.05 if spec.application_id == 'kitty' else .1)
                        assert not (runtime / JOURNAL).exists()
                        assert not (runtime / 'session-v2-restore-attempt.json').exists()
                        node = apps.create(spec.app_ids[0])
                        assert node['pid'] == apps.proc.pid
                        observe('mapped-'+spec.application_id)
                    except Exception as exc: mapping_errors.append(repr(exc))
                thread = threading.Thread(target=mapping)
                mapping_threads.append(thread)
                thread.start()
                return []
            class Provider:
                def resolve(self, expected, nodes):
                    assert expected == [UUID] and len(nodes) == 1
                    observe('provider-resolve')
                    if case == 'focus-third-party':
                        lab.command(f'[con_id={foreign_node["id"]}] focus')
                        evidence['third_party_focus'] = focused(sway.tree())
                    if case == 'focus-same-client':
                        # Négatif historique : changement vers un membre déjà
                        # admis AU STAGE ; aucune réinitialisation de preuve.
                        kitty = next(n for n in sway.windows() if n['app_id'] == 'kitty')
                        lab.command(f'[con_id={kitty["id"]}] focus')
                    if case == 'unowned-map':
                        # Cardinalité exacte avant resolve ; nouvel intrus après.
                        foreign.create('firefox')
                    if case == 'pinned-map':
                        # Map après épinglage : identité correcte, focus ambigu.
                        apps.create('TEST_ONLY_callback')
                    if case == 'provider-placement':
                        kitty = next(n for n in sway.windows() if n['app_id'] == 'kitty')
                        lab.command(f'[con_id={kitty["id"]}] move container to workspace "TEST_ONLY_MOVED"')
                    return {UUID: nodes[0]['id']}
                def capture(self, nodes): return {UUID: nodes[0]['id']}
            runtime = private_dir(lab.directory / 'runtime')
            helper = lab.spawn(['/usr/bin/python', '/usr/bin/autotiling', '--debug']) if case == 'autotiling' else None
            def helpers(path):
                # Only this private child is eligible. Never discover the host's
                # /proc helpers, including when running an actual autotiling.
                assert path == lab.socket
                return [dict(pid=helper.pid, fd=os.pidfd_open(helper.pid), script='/usr/bin/autotiling')] if helper else []
            class ObservedGuard(Guard):
                def prepare(self):
                    answer = super().prepare()
                    assert self.anchors.process.poll() is not None, 'ANCHOR_NOT_EXITED_BEFORE_RESUME'
                    evidence['anchor_exited_before_resume'] = True
                    return answer
                def __init__(self, sway, anchors, *args, **kwargs):
                    self.anchors = anchors
                    super().__init__(sway, anchors, *args, **kwargs)
                def resume(self):
                    answer = super().resume()
                    if case in ('focus-helper-late', 'focus-external-late'):
                        kitty = next(n for n in sway.windows() if n['app_id'] == 'kitty')
                        target = foreign_node['id'] if case == 'focus-external-late' else kitty['id']
                        lab.command(f'[con_id={target}] focus')
                        evidence['injected_focus'] = focused(sway.tree())
                    return answer
                def finish(self):
                    answer = super().finish()
                    if case == 'focus-finish-late':
                        kitty = next(n for n in sway.windows() if n['app_id'] == 'kitty')
                        lab.command(f'[con_id={kitty["id"]}] focus')
                        evidence['injected_focus'] = focused(sway.tree())
                    return answer
            raw_command = sway.command
            def command(text):
                row = {'command': text, 'ns': time.monotonic_ns(), 'before': focused(sway.tree())}
                evidence['commands'].append(row)
                try:
                    if case == 'map-in-ipc-gap' and len(evidence['commands']) == 1:
                        # Recovery a déjà contrôlé son arbre et publié
                        # l'intention. Un callback du PID déjà épinglé mappe
                        # avant RUN_COMMAND : aucun CAS n'a protégé cet intervalle.
                        callback = apps.create('TEST_ONLY_callback')
                        assert callback['pid'] == music['pid']
                        evidence['gap_map_injected'] = True
                    answer = raw_command(text)
                    if case == 'crash-mid-ipc' and len(evidence['commands']) == 1:
                        # Panne après vrai IPC, avant réponse à Recovery.
                        evidence['crash_injected'] = True
                        raise OSError('TEST_ONLY_CRASH_AFTER_IPC')
                    return answer
                finally: row['after'] = focused(sway.tree())
            sway.command = command
            try:
                with patch('session_v2.executor.launch', side_effect=launch_surface), patch('session_v2.guard.discover', side_effect=helpers), patch('session_v2.executor.Guard', ObservedGuard):
                    if case == 'launch-failure-retry':
                        bad_catalog = Catalog(tuple(replace(spec, argv=(str(lab.directory / 'TEST_ONLY_NO_EXECUTABLE'),))
                                                    if spec.application_id == 'firefox' else spec
                                                    for spec in test_catalog.specs.values()))
                        from session_v2.errors import Deferred
                        try:
                            Executor(sway, bad_catalog, Provider(), runtime, build(lab.directory), lab.env).apply(checkpoint(), True)
                        except Deferred as exc: assert exc.code == 'APPLICATION_LAUNCH_FAILED', exc.code
                        else: raise AssertionError('LAUNCH_FAILURE_EXPECTED')
                        assert not (runtime / JOURNAL).exists()
                        assert not (runtime / 'session-v2-restore-attempt.json').exists()
                        assert evidence['commands'] == []
                        assert location(sway.tree(), music['id'])[0] == '10'
                        until(lambda: any(n['app_id'] == 'kitty' for n in sway.windows()))
                        evidence['prewarm_failure_preserved'] = True
                    try:
                        report = Executor(sway, test_catalog, Provider(), runtime, build(lab.directory), lab.env).apply(checkpoint(), True)
                        evidence['outcome'] = 'success'
                    except Failure as exc:
                        evidence['outcome'] = exc.code
                for thread in mapping_threads: thread.join(timeout=5)
                assert not mapping_errors, mapping_errors
                report = read(runtime / 'session-v2-restore-attempt.json')
                journal = read(runtime / JOURNAL)
                evidence.update(report=report, journal=journal, launched=launched,
                                receipt=recovery_status(runtime))
                assert launched == ([] if case in ('preserve-empty-workspace', 'preserve-foreign') else ['kitty', 'firefox', 'firefox'] if case == 'launch-failure-retry' else ['kitty', 'firefox']), launched
                observe('after-executor')
                matches = [n for n in sway.windows() if n['app_id'] == 'limusic-app']
                assert len(matches) == 1
                assert (matches[0]['id'], matches[0]['pid'], process_start(matches[0]['pid'])) == music_identity
                # Aucun kill d'un client ; les kill du guard sont sur le helper.
                assert not any(row['command'] == f'[con_id={music["id"]}] kill' for row in evidence['commands'])
                assert not any(n['app_id'].startswith('labfy-v2-anchor-') for n in sway.windows())
                if case in ('natural', 'launch-failure-retry', 'preserve-empty-workspace', 'preserve-foreign', 'autotiling'):
                    # Le contrat de recette exige un vrai succès. Un refus sûr
                    # est conservé comme BLOCKED et retourne un code non nul.
                    evidence['requirement_met'] = (evidence['outcome'] == 'success' and
                        report['final_tree_verified'] and report['final_focus_verified'] and
                        report['anchors_swapped'] == 3 and report['slots_filled'] == 3 and
                        journal['status'] == 'complete')
                    if evidence['requirement_met']:
                        identities = {n['id']: {'firefox': 'F', 'kitty': 'K', 'limusic-app': 'M'}[n['app_id']]
                                      for n in sway.windows() if n['app_id'] in ('firefox', 'kitty', 'limusic-app')}
                        assert canonical(sway.tree(), '1', identities) == {'splith': ['F', 'K']}
                        assert canonical(sway.tree(), '10', identities) == 'M'
                        firefox = next(n for n in sway.windows() if n['app_id'] == 'firefox')
                        assert focused(sway.tree()) == (evidence['preserved_focus'] if case in ('preserve-empty-workspace', 'preserve-foreign') else {'con_id': firefox['id'], 'workspace': '1'})
                        assert not any(location(sway.tree(), n['id'])[0] == journal['stage'] for n in sway.windows())
                        assert focused(sway.tree())['workspace'] != journal['stage']
                elif case in ('focus-helper-late', 'focus-external-late', 'focus-finish-late'):
                    assert evidence['outcome'] == 'RECOVERY_FOCUS_MISMATCH', evidence['outcome']
                    assert report['anchors_swapped'] == 3 and report['slots_filled'] == 3
                    assert report['final_tree_verified'] and not report['final_focus_verified']
                    assert journal['status'] == 'required' and journal['focus_conflict']
                    assert focused(sway.tree()) == evidence['injected_focus']
                    boundary = 'after-guard-finish' if case == 'focus-finish-late' else 'after-helper-resume'
                    assert journal['focus_conflict_observation']['command'] == boundary
                    assert recovery_status(runtime)['status'] == 'RECOVERY_REQUIRED'
                    evidence['requirement_met'] = True
                else:
                    expected = {'unowned-map' : 'APPLICATION_MEMBERSHIP_CHANGED',
                                'provider-placement': 'TARGET_OBSERVATION_CHANGED',
                                'pinned-map': 'APPLICATION_MEMBERSHIP_CHANGED',
                                'map-in-ipc-gap': 'RECOVERY_FOCUS_MISMATCH',
                                'crash-mid-ipc': 'RESTORE_INTERNAL_ERROR'}.get(case, 'FOCUS_RECOVERY_NOT_PROVEN')
                    assert evidence['outcome'] == expected, evidence['outcome']
                    assert report['anchors_swapped'] == 0, report
                    assert not any('swap container' in c['command'] for c in evidence['commands'])
                    if case == 'focus-third-party':
                        assert focused(sway.tree()) == evidence['third_party_focus']
                    if case == 'map-in-ipc-gap':
                        assert evidence['gap_map_injected']
                        assert len(evidence['commands']) == 1
                        assert journal['focus_pending'] and journal['focus_conflict']
                        assert recovery_status(runtime)['status'] == 'RECOVERY_REQUIRED'
                    if case == 'crash-mid-ipc':
                        assert evidence['crash_injected']
                        assert len(evidence['commands']) == 1
                        assert journal['windows'][0]['pending'] and journal['focus_pending']
                        assert recovery_status(runtime)['status'] == 'RECOVERY_REQUIRED'
                        durable = read(runtime / JOURNAL)
                        Recovery(sway, runtime).recover()
                        assert read(runtime / JOURNAL)['intention'] == durable['intention']
                        assert len(evidence['commands']) == 1
                    evidence['requirement_met'] = True
            finally: foreign.close()
        finally:
            # Publier avant de retirer les clients synthétiques détenus.
            try:
                events.close()
                evidence['events'] = events.rows
                atomic(private_dir(EVIDENCE) / ('login-focus-'+case+'.json'), evidence)
            finally: apps.close()
    return evidence


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--case', choices=['natural','launch-failure-retry','preserve-empty-workspace','preserve-foreign','focus-third-party','focus-same-client','unowned-map','pinned-map','map-in-ipc-gap','provider-placement','crash-mid-ipc','autotiling','focus-helper-late','focus-external-late','focus-finish-late'], default='natural')
    args = parser.parse_args()
    row = run_case(args.case)
    print(json.dumps({'scenario': args.case, 'requirement_met': row['requirement_met'],
                      'outcome': row['outcome'], 'real_login_validated': False}))
    raise SystemExit(0 if row['requirement_met'] else 2)


if __name__ == '__main__': main()
