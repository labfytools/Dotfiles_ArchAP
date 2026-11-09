"""Run the production popup with fake commands; no package operation is reachable."""
import json
import os
from pathlib import Path
import subprocess
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'quickshell/.config/quickshell/labfy-sway'
QS = Path.home() / '.local/opt/quickshell-qt612-popup/bin/quickshell'


class UpdateUITests(unittest.TestCase):
    def test_popup_states_filters_long_list_and_preview_argv(self):
        if not QS.exists() or not os.environ.get('WAYLAND_DISPLAY'):
            self.skipTest('QuickShell et session Wayland requis')
        with tempfile.TemporaryDirectory(prefix='labfy-updates-ui-') as folder:
            p = Path(folder)
            (p/'runtime').mkdir(mode=0o700)
            shutil.copytree(BASE, p/'config')
            # All production Process commands are intercepted, including python3.
            tool = '''#!/usr/bin/python3
import os,sys,json
from pathlib import Path
p=Path(os.environ['UPDATE_UI_FIXTURE'])
name=Path(sys.argv[0]).name
with (p/'commands').open('a') as f: f.write(json.dumps([name,*sys.argv[1:]])+'\\n')
if name=='python3':
    if sys.argv[-1]=='maintenance': print(json.dumps(dict(time='fixture',history=['transaction completed'],files=['/etc/test.pacnew'],failed=[],errors=[],reboot='Unknown')))
    elif sys.argv[-1]=='news': print(json.dumps(dict(items=[dict(title='Manual intervention required',date='today',link='https://archlinux.org/news/test/',manual=True)])))
'''
            for name in ('python3', 'kitty', 'systemctl'):
                (p/name).write_text(tool)
                (p/name).chmod(0o755)
            qml = '''import QtQuick
import Quickshell
import "SOURCE" as Production
ShellRoot {
    PanelWindow { id: bar; anchors.top: true; anchors.left: true; anchors.right: true; implicitHeight: 30; exclusiveZone: 0; focusable: true }
    QtObject { id: fakeIndicator; function reload() { } }
    Production.UpdateCenter {
        id: center; barWindow: bar; indicator: fakeIndicator
        // No input serial exists in this synthetic window; real bar retains grabFocus.
        grabFocus: false
        updateState: ({repoUpdates: 0, aurUpdates: 0, totalUpdates: 0, packages: [], lastCheck: '', error: ''})
    }
    function check(value, message) { if (!value) { console.error('FAIL ' + message); Qt.exit(1); } }
    function find(item, name) {
        if (item.objectName === name) return item;
        for (const child of (item.children || [])) { const found = find(child, name); if (found) return found; }
        return null;
    }
    property int step: 0
    Timer {
        interval: 350; running: true; repeat: true
        onTriggered: {
            if (step === 0) { center.visible = true; }
            else if (step === 1) {
                check(center.visible, 'popup opens'); check(center.filtered.length === 0, 'zero');
                const rows = []; for (let i=0; i<600; i++) rows.push({name: 'pkg-' + i, installed:'1', available:'2', origin: i%2 ? 'AUR' : 'Arch', sensitive: i===0 ? 'Noyau' : ''});
                center.updateState = {repoUpdates:300,aurUpdates:300,totalUpdates:600,packages:rows,lastCheck:'2026-11-08T01:00:00Z',error:''};
            } else if (step === 2) {
                check(center.filtered.length === 600, 'long list');
                const list = find(center.contentItem, 'updatePackageList'); check(list && list.count === 600, 'production list');
                list.positionViewAtEnd(); center.origin = 'AUR';
            } else if (step === 3) {
                check(center.filtered.length === 300, 'AUR filter'); center.query = 'pkg-599';
            } else if (step === 4) {
                check(center.filtered.length === 1, 'search'); center.origin = 'Arch';
            } else if (step === 5) {
                check(center.filtered.length === 0, 'Arch filter');
                center.updateState = {repoUpdates:0,aurUpdates:0,totalUpdates:0,packages:[],lastCheck:'',error:'network failure',offline:true};
                const tabs = find(center.contentItem, 'updateTabs'); check(!!tabs, 'tabs exist'); tabs.currentIndex = 1;
            } else if (step === 6) {
                check(center.maintenance.files.length === 1, 'pacnew'); check(center.maintenance.history.length === 1, 'history');
                find(center.contentItem, 'updateTabs').currentIndex = 2;
            } else if (step === 7) {
                check(center.news.items.length === 1, 'news'); center.refresh(); center.refresh();
            } else if (step === 8) {
                center.updateState = {repoUpdates:0,aurUpdates:0,totalUpdates:0,packages:[],lastCheck:'',error:'',checking:true,checkStarted:'2000-01-01T00:00:00Z'};
                check(center.staleCheck && !center.checking, 'interrupted check recoverable');
                center.visible = false;
            } else if (step === 9) { check(!center.visible, 'popup closes'); center.visible = true; }
            else if (step === 10) { check(center.visible, 'popup reopens'); center.terminal(true); }
            else { console.info('PASS update popup states'); Qt.quit(); }
            step++;
        }
    }
}
'''.replace('SOURCE', 'config/status')
            (p/'shell.qml').write_text(qml)
            env = dict(os.environ, PATH=f'{p}:/usr/bin', UPDATE_UI_FIXTURE=folder,
                       QT_QPA_PLATFORM='wayland', WAYLAND_DISPLAY=str(Path(os.environ['XDG_RUNTIME_DIR']) / os.environ['WAYLAND_DISPLAY']), XDG_RUNTIME_DIR=str(p/'runtime'))
            result = subprocess.run([str(QS), '-p', str(p), '--no-color'], env=env, capture_output=True, text=True, timeout=20)
            logs = result.stdout + result.stderr
            self.assertEqual(result.returncode, 0, logs)
            self.assertIn('PASS update popup states', logs)
            self.assertNotIn('ReferenceError', logs)
            self.assertNotIn('TypeError', logs)
            commands = [json.loads(line) for line in (p/'commands').read_text().splitlines()]
            terminals = [cmd for cmd in commands if cmd[0] == 'kitty']
            self.assertEqual(len(terminals), 1, logs)
            self.assertEqual(terminals[0][-1], '--dry-run')
            self.assertEqual(terminals[0][1:3], ['--class', 'labfy-update-center'])
            refreshes = [cmd for cmd in commands if cmd == ['systemctl', '--user', 'start', 'labfy-quickshell-updates.service']]
            self.assertEqual(len(refreshes), 1)


if __name__ == '__main__':
    unittest.main()
