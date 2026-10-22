import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'launcher'))
import session as s
spec = importlib.util.spec_from_file_location('qs_guard', ROOT / 'launcher/quickshell-guard.py')
g = importlib.util.module_from_spec(spec)
spec.loader.exec_module(g)


def props(unit):
    return s.isolation_properties(unit)


class LauncherTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Vraies propriétés en lecture seule, jamais de mutation du manager.
        cls.target, cls.wm = props(s.SESSION_UNIT), props(s.WM_UNIT)

    def test_real_systemd_old_parser_false_negative_new_parser_pass(self):
        raw = self.target['Conflicts']
        self.assertIn('"', raw)
        self.assertIn('\\\\x2d', raw)
        self.assertFalse(set(s.EXCLUDED).issubset(raw.split()))
        self.assertTrue(set(s.EXCLUDED).issubset(s.systemd_words(raw)))
        s.validate_isolation(self.target, self.wm)
        print('REAL_CONFLICTS=' + repr(raw))

    def test_real_loaded_properties_negative_cases(self):
        for field, value in [('Id', 'wayland-session@sway.desktop.target'), ('LoadState', 'not-found'), ('DropInPaths', '')]:
            for index in (0, 1):
                data = [copy.deepcopy(self.target), copy.deepcopy(self.wm)]
                data[index][field] = value
                with self.subTest(field=field, index=index), self.assertRaises(RuntimeError):
                    s.validate_isolation(*data)
        for excluded in s.EXCLUDED:
            target = dict(self.target)
            words = [w for w in s.systemd_words(target['Conflicts']) if w != excluded]
            # Encoder les noms exactement comme systemctl pour isoler la suppression.
            target['Conflicts'] = ' '.join(json.dumps(w) if '\\' in w else w for w in words)
            with self.subTest(excluded=excluded), self.assertRaises(RuntimeError):
                s.validate_isolation(target, self.wm)

    def test_strict_parser_rejects_malformed_extra_characters(self):
        for raw in ('"unterminated', "'swayidle.service'", 'swayidle.service;id', 'swayidle.service\n',
                    '"swayidle.service"extra', '"bad\\q.target"', 'bad\\x2d.target',
                    '$(id).service', '"bad\\\\q.target"', '"bad\\\\xZZ.target"', True, [], 'a' * 16385):
            with self.subTest(raw=raw), self.assertRaises(RuntimeError):
                s.systemd_words(raw)

    def context(self):
        env = dict(INVOCATION_ID='123', NOTIFY_SOCKET='/run/user/1000/notify', XDG_SEAT='seat0', XDG_VTNR='1')
        login = dict(User=str(os.getuid()), Class='user', Seat='seat0', VTNr='1', Active='yes', Remote='no', Type='wayland')
        return env, '0::/user.slice/' + s.WM_UNIT, login, 'tty1', [(s.WM_UNIT, 'activating')]

    def test_valid_context_and_fail_closed_mutations(self):
        baseline = self.context()
        s.validate_context(*baseline)
        for key, value in [('WAYLAND_DISPLAY', 'wayland-1'), ('SWAYSOCK', '/stable'),
                           ('DISPLAY', ':0'), ('WAYLAND_SOCKET', '3'), ('I3SOCK', '/stable'),
                           ('INVOCATION_ID', ''), ('NOTIFY_SOCKET', ''), ('XDG_SEAT', 'seat1'),
                           ('XDG_VTNR', '0'), ('WLR_BACKENDS', 'headless'), ('WLR_RENDERER', 'gles2'),
                           ('LIBSEAT_BACKEND', 'seatd'), ('WLR_DRM_DEVICES', '/dev/dri/card0')]:
            args = copy.deepcopy(baseline); args[0][key] = value
            with self.subTest(key=key), self.assertRaises(RuntimeError): s.validate_context(*args)
        for key, value in [('User', '0'), ('Class', 'greeter'), ('Active', 'no'), ('Remote', 'yes'), ('Type', 'x11'), ('Seat', 'seat1'), ('VTNr', '2')]:
            args = copy.deepcopy(baseline); args[2][key] = value
            with self.subTest(login=key), self.assertRaises(RuntimeError): s.validate_context(*args)
        for index, value in [(1, '0::/wrong'), (3, 'tty2'), (4, [('wayland-wm@sway.desktop.service', 'active')])]:
            args = list(copy.deepcopy(baseline));args[index] = value
            with self.assertRaises(RuntimeError): s.validate_context(*args)

    def test_real_launch_from_desktop_refused_before_exec(self):
        # Fichiers testés séparément ; le contexte réel ne doit jamais passer à execve.
        with patch.object(s, 'verify_files'), patch.object(os, 'execve') as execute:
            with self.assertRaises(RuntimeError): s.launch()
            execute.assert_not_called()

    def test_exact_candidate_manifest_and_hash_failures(self):
        manifest = json.loads((ROOT / 'launcher/manifest.json').read_bytes())
        mapping = {
            str(s.CONFIG / 'session.py'): ROOT / 'launcher/session.py',
            str(s.CONFIG / 'quickshell-guard.py'): ROOT / 'launcher/quickshell-guard.py',
            str(s.CONFIG / 'manifest.json'): ROOT / 'launcher/manifest.json',
            '/home/fy59/.dotfiles/systemd/.config/systemd/user/quickshell-labfy-mosaic.service': ROOT / 'systemd/quickshell-labfy-mosaic.service',
            '/home/fy59/.dotfiles/quickshell/.config/quickshell/labfy-sway/sessionui/SessionV2Service.qml': ROOT / 'quickshell/SessionV2Service.qml',
        }
        original = s.read_regular
        def mapped(path, *args, **kwargs):
            return original(mapping.get(str(path), path), *args, **kwargs)
        with patch.object(s, 'read_regular', side_effect=mapped):
            s.verify_files()
            with patch.object(s, 'BINARY_SHA', '0' * 64), self.assertRaisesRegex(RuntimeError, 'CORE-C'): s.verify_files()
            with patch.object(s, 'WLROOTS_SHA', '0' * 64), self.assertRaisesRegex(RuntimeError, 'wlroots'): s.verify_files()
            with patch.dict(os.environ, LD_PRELOAD='/bad'), self.assertRaises(RuntimeError): s.verify_files()
            with patch.object(s, 'BINARY', Path('/nonexistent')), self.assertRaises(OSError): s.verify_files()
        self.assertEqual(manifest['binary_sha256'], s.BINARY_SHA)

    def test_symlink_files_and_directories_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); (root / 'real').write_text('data');(root / 'link').symlink_to(root / 'real')
            with self.assertRaises(OSError): s.read_regular(root / 'link')
            (root / 'dir').mkdir();(root / 'dirlink').symlink_to(root / 'dir')
            with self.assertRaises(OSError): s.secure_directory(root / 'dirlink')

    def test_stable_without_lab_only_in_fake_preference_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);selection=root/'uwsm';selection.mkdir();state=root/'state';state.mkdir()
            (selection/'default-id').write_text('swayfx-mosaic-test.desktop\n')
            value=s.Selection(alias=selection,directory=selection,link=None,state=state)
            with patch.object(s, 'LAB', root/'missing'), patch.object(s, 'verify_files', side_effect=AssertionError('stable ne doit pas dépendre du binaire')):
                with patch.object(sys, 'argv', ['session.py', 'stable']), patch.object(s, 'Selection', return_value=value): s.main()
            self.assertEqual((selection/'default-id').read_text(),'sway.desktop\n')


class QuickShellTests(unittest.TestCase):
    def ready(self):
        env=dict(XDG_RUNTIME_DIR=f'/run/user/{os.getuid()}', SWAYSOCK=f'/run/user/{os.getuid()}/sway-ipc.{os.getuid()}.456.sock', I3SOCK=f'/run/user/{os.getuid()}/sway-ipc.{os.getuid()}.456.sock', WAYLAND_DISPLAY='wayland-7', XDG_SESSION_DESKTOP='swayfx-mosaic-test',XDG_CURRENT_DESKTOP='swayfx-mosaic-test:wlroots:sway',LABFY_MOSAIC_SMOKE='1')
        return [env, dict(Id=s.WM_UNIT, ActiveState='active',SubState='running',MainPID='456'),dict(Id=s.SESSION_UNIT,ActiveState='active'),dict(ActiveState='inactive'),[(s.WM_UNIT,'active')],'0::/user.slice/'+g.QS_UNIT]

    def test_finalize_and_socket_identity_rejections(self):
        self.assertEqual(g.validate_ready(*self.ready()),456)
        for key in self.ready()[0]:
            args=self.ready();args[0][key]='wrong'
            with self.subTest(env=key),self.assertRaises(RuntimeError):g.validate_ready(*args)
        for index,key,value in [(1,'ActiveState','activating'),(1,'MainPID','0'),(1,'Id','wrong'),(2,'ActiveState','inactive'),(3,'ActiveState','active')]:
            args=self.ready();args[index][key]=value
            with self.assertRaises(RuntimeError):g.validate_ready(*args)
        args=self.ready();args[4].append(('wayland-wm@sway.desktop.service','active'))
        with self.assertRaises(RuntimeError):g.validate_ready(*args)
        args=self.ready();args[5]='0::/manual'
        with self.assertRaises(RuntimeError):g.validate_ready(*args)

    def test_real_stable_pid_rejected_without_socket_ipc(self):
        pid=subprocess.check_output(['systemctl','--user','show','wayland-wm@sway.desktop.service','-p','MainPID','--value'],text=True).strip()
        self.assertGreater(int(pid),1)
        with self.assertRaisesRegex(RuntimeError,'MainPID/binaire'):g.verify_process(int(pid),self.ready()[0])

    def test_process_sockets_mapping_and_logind_with_isolated_proc_fixture(self):
        # Vrais sockets de fichiers sous LAB, faux /proc/logind : aucun compositor/IPC.
        # L'identité des bytes du binaire/provider reste celle du couple réel audité.
        import socket
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);proc=root/'proc';wm=proc/'456';wm.mkdir(parents=True)
            runtime=root/'runtime';runtime.mkdir();(proc/'net').mkdir()
            tty=root/'active-tty';tty.write_text('tty1\n')
            (wm/'exe').symlink_to(s.BINARY);(wm/'cgroup').write_text('0::/user.slice/'+s.WM_UNIT+'\n')
            (wm/'maps').write_text('0-1 r-xp 0 00:00 1 '+str(s.WLROOTS.resolve())+'\n')
            (wm/'environ').write_bytes(b'XDG_SESSION_ID=fixture\0XDG_VTNR=1\0')
            fd=wm/'fd';fd.mkdir()
            (fd/'3').symlink_to('socket:[101]');(fd/'4').symlink_to('socket:[102]')
            paths=[runtime/'sway-fixture.sock',runtime/'wayland-7'];sockets=[]
            try:
                for path in paths:
                    sock=socket.socket(socket.AF_UNIX);sock.bind(str(path));sockets.append(sock)
                unix=proc/'net/unix'
                net='Header\n'+'\n'.join('0000: 2 0 10000 1 01 '+str(101+i)+' '+str(path) for i,path in enumerate(paths))+'\n'
                unix.write_text(net)
                env=dict(self.ready()[0],XDG_RUNTIME_DIR=str(runtime),SWAYSOCK=str(paths[0]))
                login=dict(User=str(os.getuid()),Class='user',Seat='seat0',VTNr='1',Active='yes',Remote='no',Type='wayland')
                def path_adapter(value):
                    value=str(value)
                    if value=='/proc':return proc
                    if value=='/proc/net/unix':return unix
                    if value=='/sys/class/tty/tty0/active':return tty
                    return Path(value)
                with patch.object(g,'Path',side_effect=path_adapter),patch.object(s,'properties',return_value=login):
                    g.verify_process(456,env)
                    unix.write_text(net.replace(' 101 ',' 999 '))
                    with self.assertRaisesRegex(RuntimeError,'Socket'):g.verify_process(456,env)
                    unix.write_text(net)
                    maps=(wm/'maps').read_text();(wm/'maps').write_text('')
                    with self.assertRaisesRegex(RuntimeError,'Mapping'):g.verify_process(456,env)
                    (wm/'maps').write_text(maps)
                    other=proc/'987';other.mkdir();(other/'exe').symlink_to('/usr/bin/qs')
                    with self.assertRaisesRegex(RuntimeError,'QuickShell'):g.verify_process(456,env)
                    (other/'exe').unlink();other.rmdir()
                    for key,value in [('User','0'),('Active','no'),('Seat','seat1'),('VTNr','2')]:
                        with patch.object(s,'properties',return_value=dict(login,**{key:value})),self.assertRaisesRegex(RuntimeError,'logind/VT'):
                            g.verify_process(456,env)
                    tty.write_text('tty2\n')
                    with self.assertRaisesRegex(RuntimeError,'logind/VT'):g.verify_process(456,env)
                    tty.write_text('tty1\n');(wm/'environ').write_bytes(b'XDG_VTNR=1\0')
                    with self.assertRaisesRegex(RuntimeError,'logind WM absente'):g.verify_process(456,env)
            finally:
                for sock in sockets:sock.close()

    def test_unit_transaction_and_stop_propagation(self):
        import configparser
        parser=configparser.ConfigParser(interpolation=None);parser.read(ROOT/'systemd/quickshell-labfy-mosaic.service')
        target=s.SESSION_UNIT;wm=s.WM_UNIT
        self.assertEqual(parser['Install']['WantedBy'],target)
        self.assertEqual(parser['Unit']['PartOf'],target)
        self.assertEqual(parser['Unit']['BindsTo'],target)
        self.assertEqual(set(parser['Unit']['After'].split()),{target,wm})
        self.assertEqual(set(parser['Unit']['Requisite'].split()),{target,wm})
        self.assertEqual(parser['Service']['Restart'],'no')
        self.assertEqual(parser['Service']['ExecStart'],'/usr/bin/qs -c labfy-sway --no-color')
        stable=(Path('/home/fy59/.config/systemd/user/quickshell-labfy-sway.service')).read_text()
        self.assertNotIn(target,stable)
        # Modèle de transaction des arêtes réellement lues, sans manager ni activation.
        wants={}
        for directory in (ROOT / 'systemd').glob('*.target.wants'):
            wants[directory.name.removesuffix('.wants')] = {p.name for p in directory.iterdir() if p.is_symlink() and p.resolve().is_file()}
        stable_wants=Path('/home/fy59/.config/systemd/user/wayland-session@sway.desktop.target.wants')
        wants['wayland-session@sway.desktop.target']={p.name for p in stable_wants.iterdir() if p.is_symlink()}
        stops={name:{g.QS_UNIT} for name in parser['Unit']['PartOf'].split()}
        self.assertEqual(wants[target],{g.QS_UNIT})
        self.assertTrue(wants[target].isdisjoint(wants['wayland-session@sway.desktop.target']))
        self.assertIn(g.QS_UNIT,stops[target])
        self.assertNotIn('Conflicts',parser['Unit'])


if __name__=='__main__':unittest.main()
