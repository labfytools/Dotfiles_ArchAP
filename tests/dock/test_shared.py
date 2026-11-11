"""Durable real backend operations and private toolkit icon resolution."""
import concurrent.futures
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT/'quickshell/.config/quickshell/labfy-sway/applications'
sys.path.insert(0, str(APP))
import backend
import shared
from gi.repository import Gio

NINE = ['firefox.desktop','kitty.desktop','yazi.desktop','nvim.desktop',
        'org.darktable.darktable.desktop','orca-slicer.desktop','org.freecad.FreeCAD.desktop',
        'org.kde.digikam.desktop','AppFlowy.desktop']


class Persistence(unittest.TestCase):
    def test_nine_move_missing_anchor_and_empty(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'labfy-sway/applications-favorites.json'
            path.parent.mkdir()
            path.write_text(json.dumps(dict(version=1,ids=NINE)))
            self.assertEqual(backend.read_favorites(path)[1],NINE)
            expected=[NINE[1],NINE[0]]+NINE[2:]
            self.assertEqual(backend.write_favorites(path,'move',[NINE[1],NINE[0]]),expected)
            before=path.read_bytes()
            for pair in ([NINE[0],'absent.desktop'], ['absent.desktop',NINE[0]], [NINE[0],'../bad']):
                with self.assertRaises(ValueError): backend.write_favorites(path,'move',pair)
                self.assertEqual(before,path.read_bytes())
            for identifier in NINE: backend.write_favorites(path,'remove',[identifier])
            self.assertEqual(backend.write_favorites(path,'seed',NINE[:4]),[])
            self.assertEqual(backend.read_favorites(path),(True,[]))

    def test_toggle_is_atomic_and_does_not_depend_on_a_stale_ui_list(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'favorites.json'
            backend.write_favorites(path,'toggle',['kitty.desktop'])
            self.assertEqual(backend.write_favorites(path,'toggle',['kitty.desktop']),[])

    def test_real_concurrent_processes_keep_all_additions_during_moves(self):
        with tempfile.TemporaryDirectory() as temp:
            env=dict(os.environ,XDG_STATE_HOME=temp)
            path=Path(temp)/'labfy-sway/applications-favorites.json'
            backend.write_favorites(path,'seed',['a.desktop','b.desktop'])
            def run(args):
                result=subprocess.run([sys.executable,'-B',str(APP/'backend.py'),'favorites',*args],
                                      env=env,capture_output=True,text=True,timeout=10)
                self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            jobs=[['add',f'added{i}.desktop'] for i in range(24)]
            jobs += [['move','b.desktop','a.desktop'] for _ in range(10)]
            with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
                list(executor.map(run,jobs))
            ids=backend.read_favorites(path)[1]
            self.assertEqual(ids[:2],['b.desktop','a.desktop'])
            self.assertEqual(len(ids),26)
            self.assertEqual(set(ids[2:]),{f'added{i}.desktop' for i in range(24)})


class Icons(unittest.TestCase):
    def test_tela_desktop_icon_and_absolute(self):
        resolver=shared.IconResolver()
        self.assertIn('/Tela-circle-purple-dark/',resolver.resolve(Gio.ThemedIcon.new('firefox')))
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'custom icon.svg'
            path.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="48" height="48"/>')
            self.assertEqual(resolver.resolve(Gio.FileIcon.new(Gio.File.new_for_path(str(path)))),path.as_uri())
        self.assertTrue(resolver.resolve(Gio.ThemedIcon.new('labfy-icon-does-not-exist')))
        self.assertTrue(resolver.resolve(Gio.FileIcon.new(Gio.File.new_for_path('/missing/icon.svg'))))

    def test_inheritance_from_a_private_test_theme(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            for name,parent in [('Child','Parent'),('Parent','hicolor')]:
                directory=root/name; (directory/'48x48/apps').mkdir(parents=True)
                (directory/'index.theme').write_text('[Icon Theme]\nName='+name+'\nInherits='+parent+
                    '\nDirectories=48x48/apps\n[48x48/apps]\nSize=48\nType=Fixed\nContext=Applications\n')
            icon=root/'Parent/48x48/apps/inherited.svg'
            icon.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="48" height="48"/>')
            resolver=shared.IconResolver('Child')
            resolver.theme.set_search_path([temp])
            self.assertEqual(resolver.resolve(Gio.ThemedIcon.new('inherited')),icon.as_uri())


class Sway(unittest.TestCase):
    def test_wayland_xwayland_scratchpad_and_explicit_focus(self):
        tree=dict(nodes=[dict(type='workspace',name='__i3_scratch',floating_nodes=[
            dict(id=42,window=3,window_properties={'class':'Fixture','instance':'fixture'},
                 foreign_toplevel_identifier='a'*32,name='Arbitrary'),
            dict(id=43,app_id='kitty',foreign_toplevel_identifier='../invalid',
                 name='Completely different title')])])
        windows=shared.windows(tree)
        self.assertEqual(windows[0]['wmClass'],'Fixture')
        self.assertEqual(windows[1]['appId'],'kitty')
        self.assertEqual(windows[0]['workspace'],'__i3_scratch')
        self.assertEqual(windows[0]['foreignId'],'a'*32)
        self.assertEqual(windows[1]['foreignId'],'')
        with patch.object(shared,'sway_request',side_effect=[tree,[{'success':True}],[{'success':True}]]) as ipc:
            shared.focus('42')
            self.assertEqual([c.args for c in ipc.call_args_list],[(4,''),(0,'[con_id=42] scratchpad show'),
                                                                  (0,'[con_id=42] focus')])
        with patch.object(shared,'sway_request') as ipc:
            with self.assertRaises(ValueError): shared.focus('42] focus; exec bad')
            ipc.assert_not_called()

if __name__=='__main__': unittest.main()
