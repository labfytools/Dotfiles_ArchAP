"""Scratchpad contracts against production capture/store/journal; inert IPC."""
import json
import tempfile
import unittest
from unittest.mock import patch
from common import *
from test_prewarm import Sway
from session_v2.snapshot import capture
from session_v2.checkpoint import Store
from session_v2.storage import read, private_dir
from session_v2.ipc import walk, workspace
from session_v2.errors import Failure
from session_v2.recovery import Recovery, JOURNAL, observe, command_focus, validate as validate_recovery
from session_v2.slots import assign
from session_v2.layout import compile_plan, compile_placements


def source():
    sway = Sway()
    for ws in sway.value['nodes'][0]['nodes']:
        ws['layout'] = 'splith'; ws['nodes'] = []
    sway.add('kitty', 7, focus=True)
    sway.add('kitty', 8, focus=False)
    sway.add('limusic-app', 9, focus=False)
    root = sway.value
    hidden = dict(id=80, type='workspace', name='__i3_scratch', layout='splith', nodes=[], floating_nodes=[], focused=False)
    root['nodes'].insert(0, dict(id=81, type='output', name='__i3', nodes=[hidden]))
    ws = workspace(root, '1')
    n = next(n for n in ws['nodes'] if n['id'] == 8)
    ws['nodes'].remove(n)
    n.update(scratchpad_state='fresh', floating='user_on', rect=dict(x=301,y=106,width=800,height=500))
    hidden['floating_nodes'].append(n)
    return sway


class ScratchpadTests(unittest.TestCase):
    def test_capture_store_reload_and_no_internal_workspace(self):
        sway = source()
        d = capture(sway, Catalog(), None)
        self.assertEqual(d['version'], 2)
        self.assertEqual(len(d['window_slots']), 3)
        hidden = next(s for s in d['window_slots'] if s['state']['scratchpad'] == 'hidden')
        self.assertIsNone(hidden['workspace'])
        self.assertEqual(hidden['state']['geometry'], dict(x=301,y=106,width=800,height=500))
        self.assertEqual(hidden['identity_requirement'], 'interchangeable')
        self.assertEqual(d['focus'], next(s['slot_id'] for s in d['window_slots'] if s['application_id']=='kitty' and s['workspace']=='1'))
        self.assertNotIn('__i3_scratch', [o['name'] for o in d['outputs']])
        self.assertTrue(all(op.workspace != '__i3_scratch' for op in compile_plan(d,'a'*32)))
        self.assertEqual(compile_placements(d)[0]['scratchpad'], 'hidden')
        self.assertIsNone(compile_placements(d)[0]['workspace'])
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp)); store.save('test',d); store.checkpoint(d)
            self.assertEqual(store.last(),d); self.assertEqual(store.load('test'),d)
            old = fixture(); store.save('old',old)
            self.assertEqual(store.load('old'),old)

    def test_capture_is_deterministic_for_a_stable_tree(self):
        sway=source()
        with patch('session_v2.snapshot.time.time_ns',return_value=123):
            first=capture(sway,Catalog(),None)
            self.assertEqual(first,capture(sway,Catalog(),None))
        raw=json.dumps(first)
        self.assertNotIn('con_id',raw);self.assertNotIn('starttime',raw)
        self.assertNotIn('__i3_scratch',raw)

    def test_shown_and_multiple_hidden(self):
        sway=source(); hidden=workspace(sway.value,'__i3_scratch'); ws=workspace(sway.value,'1')
        shown=hidden['floating_nodes'].pop(); ws.setdefault('floating_nodes',[]).append(shown)
        for n in walk(sway.value): n['focused']=n['id']==8
        d=capture(sway,Catalog(),None)
        slot=next(s for s in d['window_slots'] if s['state']['scratchpad']=='shown')
        self.assertEqual(slot['workspace'],'1'); self.assertEqual(d['focus'],slot['slot_id'])
        for n in list(ws['nodes']):
            n.update(floating='user_on',scratchpad_state='fresh',focused=False,rect=dict(x=0,y=0,width=100,height=100))
            hidden['floating_nodes'].append(n)
        ws['nodes']=[]
        d=capture(sway,Catalog(),None)
        self.assertEqual(sum(s['state']['scratchpad']=='hidden' for s in d['window_slots']),2)

    def test_change_between_reads_and_ambiguous_focus_refuse(self):
        sway=source(); original=sway.windows
        def changed():
            result=original(); next(n for n in walk(sway.value) if n['id']==8)['scratchpad_state']='none'
            return result
        sway.windows=changed
        with self.assertRaisesRegex(Failure,'SNAPSHOT_CHANGED'):capture(sway,Catalog(),None)
        sway=source(); next(n for n in walk(sway.value) if n['id']==8)['focused']=True
        with self.assertRaisesRegex(Failure,'SNAPSHOT_FOCUS_AMBIGUOUS'):capture(sway,Catalog(),None)

    def test_strict_versions_and_scratchpad_references(self):
        d=capture(source(),Catalog(),None)
        hidden=next(i for i,s in enumerate(d['window_slots']) if s['workspace'] is None)
        mutations=[lambda v:v.update(version=1), lambda v:v['window_slots'][hidden].update(workspace='__i3_scratch'),
                   lambda v:v.update(focus=v['window_slots'][hidden]['slot_id']),
                   lambda v:v['window_slots'][hidden]['state'].update(scratchpad=True),
                   lambda v:v['window_slots'][hidden]['state'].update(floating=False)]
        for change in mutations:
            v=copy.deepcopy(d);change(v)
            with self.assertRaises(Failure):validate(v)
        try: import jsonschema
        except ImportError: self.skipTest('jsonschema unavailable')
        contract=json.loads((BACKEND/'session_v2/schema-v2.json').read_text())
        jsonschema.Draft202012Validator(contract).validate(d)

    def test_runtime_visibility_assignment_never_exposes_hidden_peer(self):
        sway=source(); d=capture(sway,Catalog(),None)
        slots=[s for s in d['window_slots'] if s['application_id']=='kitty']
        nodes=[n for n in sway.windows() if n['app_id']=='kitty']
        states={n['id']:observe(sway.tree(),n,lambda pid:123) for n in nodes}
        m=assign(slots,nodes,states=states)
        hidden=next(s for s in slots if s['workspace'] is None)
        self.assertEqual(m[hidden['slot_id']],8)
        for s in slots:s['state']['scratchpad']='none'
        with self.assertRaisesRegex(Failure,'SCRATCHPAD_ASSIGNMENT_UNPROVEN'):assign(slots,nodes,states=states)

    def test_journal_detects_identity_output_scratchpad_and_interruption(self):
        for change in ('identity','output','scratchpad','pending'):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as tmp:
                sway=source(); r=Recovery(sway,tmp,'a'*32,'labfy-v2-stage-'+'a'*32,start=lambda pid:123)
                for n in sway.windows():r.admit(n)
                r.baseline({'kitty','limusic-app'})
                if change=='identity': next(n for n in walk(sway.value) if n['id']==8)['pid']=999
                elif change=='output':sway.value['nodes'][0]['name']='moved'
                elif change=='scratchpad': next(n for n in walk(sway.value) if n['id']==8)['scratchpad_state']='none'
                else:r.data['windows'][0]['pending']=True;r.data['focus_pending']=True;r.publish()
                receipt=r.recover()
                self.assertEqual(receipt['status'],'RECOVERY_REQUIRED');self.assertEqual(sway.commands,[])
                durable=read(Path(tmp)/JOURNAL,validate_recovery)
                if change=='pending':self.assertTrue(durable['focus_pending'])

    def test_hidden_focus_is_rejected_before_command(self):
        sway=source()
        with self.assertRaisesRegex(Failure,'FOCUS_HIDDEN_SCRATCHPAD'):command_focus(sway.tree(),8,'focus')

    def test_initial_scratchpad_add_predicts_source_workspace_focus(self):
        sway=source(); ws=workspace(sway.value,'__i3_scratch')
        n=ws['floating_nodes'].pop(); n['scratchpad_state']='none'
        workspace(sway.value,'10')['floating_nodes']=[n]
        # Actual root_scratchpad_add_container semantics: even an unfocused
        # floating leaf causes source-workspace selection. Not focus-neutral.
        self.assertEqual(command_focus(sway.tree(),8,'move scratchpad'),dict(con_id=None,workspace='10'))
        self.assertEqual(command_focus(source().tree(),8,'scratchpad show'),dict(con_id=8,workspace='1'))

    def test_group_ancestor_is_not_admitted_by_leaf_identity(self):
        sway=source(); ws=workspace(sway.value,'__i3_scratch')
        n=ws['floating_nodes'].pop(); n['scratchpad_state']='none'
        ws['floating_nodes']=[dict(id=99,type='con',scratchpad_state='fresh',nodes=[n])]
        with self.assertRaisesRegex(Failure,'SCRATCHPAD_CONTAINER_UNSUPPORTED'):
            observe(sway.tree(),n,lambda pid:123)
        with self.assertRaisesRegex(Failure,'SCRATCHPAD_CONTAINER_UNSUPPORTED'):
            capture(sway,Catalog(),None)

    def test_layer_shell_can_leave_no_sway_focus(self):
        # Le panneau de déconnexion peut prendre le focus Wayland et ne
        # laisser aucune feuille Sway marquée focused. L'absence est une
        # observation légitime, distincte de plusieurs candidats ambigus.
        sway = source()
        for n in walk(sway.value): n['focused'] = False
        result = capture(sway, Catalog(), None)
        self.assertIsNone(result['focus'])
        self.assertIsNone(result['focus_workspace'])
        self.assertTrue(any(s['state']['scratchpad'] == 'hidden' for s in result['window_slots']))
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp))
            store.checkpoint(result)
            self.assertEqual(store.last(), result)
        try:
            import jsonschema
        except ImportError:
            return
        contract = json.loads((BACKEND/'session_v2/schema-v2.json').read_text())
        jsonschema.validate(result, contract)

    def test_multiple_focused_nodes_are_still_refused(self):
        sway = source()
        for n in walk(sway.value):
            if n.get('id') == 9: n['focused'] = True
        with self.assertRaisesRegex(Failure, 'SNAPSHOT_FOCUS_AMBIGUOUS'):
            capture(sway, Catalog(), None)

    def test_empty_focus_workspace_is_persisted(self):
        sway=source()
        for n in walk(sway.value): n['focused']=n['id']==3
        d=capture(sway,Catalog(),None)
        self.assertIsNone(d['focus']);self.assertEqual(d['focus_workspace'],'10')
        self.assertIn('10',[w['workspace'] for w in d['workspaces']])
        broken=copy.deepcopy(d);broken['focus_workspace']='absent'
        with self.assertRaises(Failure):validate(broken)

    def test_legacy_journal_not_reinterpreted(self):
        sway=source()
        with tempfile.TemporaryDirectory() as tmp:
            r=Recovery(sway,tmp,'a'*32,'labfy-v2-stage-'+'a'*32,start=lambda pid:123)
            r.admit(next(n for n in sway.windows() if n['id']==7))
            r.data['version']=1
            for e in r.data['windows']:
                for key in ('origin','expected'): e[key].pop('scratchpad',None)
            r.publish()
            old=Recovery(sway,tmp,start=lambda pid:123)
            self.assertNotIn('scratchpad',old.snapshot(7))
            with self.assertRaisesRegex(Failure,'LEGACY_SCRATCHPAD_UNPROVEN'):old.snapshot(8)


if __name__=='__main__':unittest.main()
