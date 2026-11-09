"""Exercise production RGB QML with an executable fixture; never open real HID."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'quickshell/.config/quickshell/labfy-sway'

class RgbKeyboardTests(unittest.TestCase):
    def test_production_process_flow_and_opt_out(self):
        qs = shutil.which('qs')
        if not qs:
            self.skipTest('QuickShell unavailable')
        with tempfile.TemporaryDirectory(prefix='labfy-rgb-qml-') as folder:
            p = Path(folder)
            (p/'runtime').mkdir(mode=0o700)
            (p/'config').mkdir()
            (p/'rgbkeyboard').mkdir()
            shutil.copy(BASE/'rgbkeyboard/qmldir', p/'rgbkeyboard/qmldir')
            source = (BASE/'rgbkeyboard/RgbKeyboardService.qml').read_text()
            old = 'readonly property string executable: (Quickshell.env("HOME") || "") + "/.local/bin/labfy-rgb"'
            self.assertIn(old, source)
            source = source.replace(old, 'readonly property string executable: ' + json.dumps(str(p/'fake-cli')))
            (p/'rgbkeyboard/RgbKeyboardService.qml').write_text(source)
            # Only the executable path is replaced. All Process/state/validation
            # logic is production code. Preferences and endpoint state are isolated.
            (p/'fake-cli').write_text('''#!/usr/bin/python3
import json, os, sys
from pathlib import Path
p=Path(os.environ['RGB_FIXTURE'])
a=sys.argv[1:]
with (p/'calls').open('a') as f: f.write(json.dumps(a)+'\\n')
s=dict(schema=1,available=True,device='/dev/hidraw77',commanded_mode='unknown',last_color=None,last_percent=None)
if (p/'state').exists(): s=json.loads((p/'state').read_text())
if a[0]=='set' and a[1]=='#010101': print('fixture access denied',file=sys.stderr); sys.exit(4)
if a[0]=='set' and a[1]=='#000001': Path(sys.argv[0]).unlink()
if a[0]=='status': print(json.dumps(s))
elif a[0]=='set': s.update(commanded_mode='software',last_color=a[1],last_percent=int(a[2]) if len(a)>2 else 100); (p/'state').write_text(json.dumps(s))
elif a[0]=='brightness': s['last_percent']=int(a[1]); (p/'state').write_text(json.dumps(s))
elif a[0]=='off': s['last_percent']=0; (p/'state').write_text(json.dumps(s))
elif a[0]=='auto': s.update(commanded_mode='firmware',last_color=None,last_percent=None); (p/'state').write_text(json.dumps(s))
else: sys.exit(2)
''')
            (p/'fake-cli').chmod(0o700)
            (p/'shell.qml').write_text('''import QtQuick
import Quickshell
import "rgbkeyboard"
ShellRoot {
    id: root
    property int step: 0
    property int presetIndex: 0
    property int ticks: 0
    function check(ok, message) { if (!ok) { console.error("RGB_FAIL " + message); Qt.exit(1); } }
    Timer {
        interval: 80; running: true; repeat: true
        onTriggered: {
            root.ticks++;
            if (root.ticks > 100) { console.error("RGB_TIMEOUT"); Qt.exit(1); return; }
            if (RgbKeyboardService.busy || RgbKeyboardService.refreshPending) return;
            if (root.step === 0) {
                root.check(!RgbKeyboardService.restoreEnabled, "default opt out");
                root.check(RgbKeyboardService.palette.length === 8, "eight presets");
                const golden = ["#8000FF","#0040FF","#00FFFF","#00FF40","#FF0080","#FF0000","#FF6000","#FFFF00"];
                for (let i = 0; i < golden.length; ++i) root.check(RgbKeyboardService.palette[i].color === golden[i], "preset wire color");
                root.check(!RgbKeyboardService.applyColor("#bad", 60), "reject bad color");
                root.check(!RgbKeyboardService.intensity(101), "reject intensity");
                RgbKeyboardService.refresh(); root.step++;
            } else if (root.step === 1 && RgbKeyboardService.available) {
                root.check(RgbKeyboardService.preset("#8000ff"), "apply");
                root.check(!RgbKeyboardService.firmware(), "serialize writes"); root.step++;
            } else if (root.step === 2 && RgbKeyboardService.lastColor === RgbKeyboardService.palette[root.presetIndex].color) {
                root.check(RgbKeyboardService.lastPercent === 100, "preset CLI default percent");
                root.presetIndex++;
                if (root.presetIndex < RgbKeyboardService.palette.length) {
                    root.check(RgbKeyboardService.preset(RgbKeyboardService.palette[root.presetIndex].color), "next preset");
                } else { RgbKeyboardService.intensity(30); root.step++; }
            } else if (root.step === 3 && RgbKeyboardService.lastPercent === 30) {
                RgbKeyboardService.off(); root.step++;
            } else if (root.step === 4 && RgbKeyboardService.lastPercent === 0) {
                RgbKeyboardService.firmware(); root.step++;
            } else if (root.step === 5 && RgbKeyboardService.commandedMode === "firmware") {
                root.check(RgbKeyboardService.lastColor === "", "no physical firmware color claim");
                root.check(!RgbKeyboardService.restoreEnabled, "opt in not activated");
                RgbKeyboardService.applyColor("#010101", 100); root.step++;
            } else if (root.step === 6 && RgbKeyboardService.message.indexOf("code 4") >= 0) {
                RgbKeyboardService.applyColor("#000001", 100); root.step++;
            } else if (root.step === 7 && !RgbKeyboardService.available) {
                root.check(!RgbKeyboardService.busy, "failed executable start releases ownership");
                console.log("RGB_PASS"); Qt.exit(0);
            }
        }
    }
}
''')
            env = dict(os.environ, RGB_FIXTURE=str(p), XDG_CONFIG_HOME=str(p/'config'),
                       XDG_RUNTIME_DIR=str(p/'runtime'), QT_QPA_PLATFORM='offscreen')
            result = subprocess.run([qs, '-p', str(p/'shell.qml')], env=env,
                                    capture_output=True, text=True, timeout=15)
            log = result.stdout + result.stderr
            self.assertEqual(result.returncode, 0, log)
            self.assertIn('RGB_PASS', log)
            self.assertNotIn('Failed to initialize QSettings', log)
            commands = [json.loads(line) for line in (p/'calls').read_text().splitlines()]
            writes = [args for args in commands if args[0] != 'status']
            self.assertEqual(writes, [['set',c] for c in ['#8000FF','#0040FF','#00FFFF','#00FF40','#FF0080','#FF0000','#FF6000','#FFFF00']] + [['brightness','30'],['off'],['auto'],['set','#010101','100'],['set','#000001','100']])
            self.assertTrue(all(args == ['status','--json'] for args in commands if args[0]=='status'))

    def test_startup_opt_in_firmware_priority_and_invalid_preferences(self):
        qs = shutil.which('qs')
        if not qs:
            self.skipTest('QuickShell unavailable')
        cases = [(False, 'software', 'unknown', '#B4BEFE', False),
                 (True, 'software', 'unknown', '#B4BEFE', True),
                 (True, 'firmware', 'unknown', '#B4BEFE', False),
                 (True, 'software', 'firmware', '#B4BEFE', False),
                 (True, 'software', 'unknown', '#INVALID', False)]
        for enabled, saved_mode, native_mode, color, expect_set in cases:
            with self.subTest(enabled=enabled, saved_mode=saved_mode, native_mode=native_mode, color=color), tempfile.TemporaryDirectory(prefix='labfy-rgb-startup-') as folder:
                p = Path(folder)
                (p/'runtime').mkdir(mode=0o700)
                (p/'config/labfy-rgb').mkdir(parents=True)
                (p/'rgbkeyboard').mkdir()
                shutil.copy(BASE/'rgbkeyboard/qmldir', p/'rgbkeyboard/qmldir')
                source = (BASE/'rgbkeyboard/RgbKeyboardService.qml').read_text()
                old = 'readonly property string executable: (Quickshell.env("HOME") || "") + "/.local/bin/labfy-rgb"'
                self.assertIn(old, source)
                (p/'rgbkeyboard/RgbKeyboardService.qml').write_text(source.replace(old, 'readonly property string executable: '+json.dumps(str(p/'fake-cli'))))
                (p/'config/labfy-rgb/quickshell.ini').write_text('[General]\nrestoreEnabled='+str(enabled).lower()+'\nsavedMode='+saved_mode+'\nsavedColor='+color+'\nsavedPercent=60\n')
                (p/'fake-cli').write_text('''#!/usr/bin/python3
import os,sys,json
from pathlib import Path
p=Path(os.environ['RGB_FIXTURE'])
a=sys.argv[1:]
with (p/'calls').open('a') as f: f.write(json.dumps(a)+'\\n')
if a[0]=='status': print(json.dumps(dict(schema=1,available=True,device='/dev/hidraw77',commanded_mode=os.environ['NATIVE_MODE'],last_color=None,last_percent=None)))
''')
                (p/'fake-cli').chmod(0o700)
                (p/'shell.qml').write_text('''import QtQuick
import Quickshell
import "rgbkeyboard"
ShellRoot {
    Component.onCompleted: console.log("OPT_IN", RgbKeyboardService.restoreEnabled)
    Timer { running: true; interval: 2400; onTriggered: Qt.exit(0) }
}
''')
                env = dict(os.environ, RGB_FIXTURE=str(p), NATIVE_MODE=native_mode,
                           XDG_CONFIG_HOME=str(p/'config'), XDG_RUNTIME_DIR=str(p/'runtime'), QT_QPA_PLATFORM='offscreen')
                result = subprocess.run([qs,'-p',str(p/'shell.qml')],env=env,capture_output=True,text=True,timeout=8)
                self.assertEqual(result.returncode,0,result.stdout+result.stderr)
                commands = [json.loads(line) for line in (p/'calls').read_text().splitlines()]
                writes = [args for args in commands if args[0] != 'status']
                self.assertEqual(writes, [['set','#B4BEFE','60']] if expect_set else [])

if __name__ == '__main__':
    unittest.main()
