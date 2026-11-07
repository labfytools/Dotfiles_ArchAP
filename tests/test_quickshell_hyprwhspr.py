"""Exercise the production QML backend with fake CLI tools, never the microphone."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / 'quickshell/.config/quickshell/labfy-sway/status'
LOCAL_QS = Path.home() / '.local/opt/quickshell-qt612-popup/bin/quickshell'
QS = os.environ.get('QUICKSHELL_BIN', str(LOCAL_QS) if LOCAL_QS.exists() else shutil.which('quickshell'))


class DictationTest(unittest.TestCase):
    def test_production_backend(self):
        self.run_backend("idle")

    def test_starting_during_recording(self):
        self.run_backend("recording")

    def run_backend(self, initial):
        with tempfile.TemporaryDirectory(prefix='qs-dictation-test-') as folder:
            p = Path(folder)
            (p/'runtime').mkdir(mode=0o700)
            (p/'runtime/hyprwhspr').mkdir()
            # CONTRACT: PATH isolates both CLI names; toggles touch a fake marker
            # only. No live Hyprwhspr command is reachable from this fixture.
            tool = '''#!/usr/bin/python3
import os, pathlib, sys, time
p = pathlib.Path(os.environ['DICTATION_FIXTURE'])
mode = (p/'mode').read_text()
if pathlib.Path(sys.argv[0]).name == 'systemctl':
    print('inactive' if mode == 'offline' else 'active')
    sys.exit(3 if mode == 'offline' else 0)
if sys.argv[-1] == 'toggle':
    with (p/'toggles').open('a') as f: f.write('toggle\\n')
    if mode == 'reject': print('[ERROR] Service not listening on control FIFO')
    else:
        (p/'mode').write_text('recording')
        print('[SUCCESS] Recording started')
else:
    if mode == 'slow': time.sleep(20)
    print('[INFO] Status: Recording in progress' if mode == 'recording' else
          'unexpected' if mode == 'bad' else '[INFO] Status: Idle')
'''
            for name in ['systemctl', 'hyprwhspr']:
                (p/name).write_text(tool)
                (p/name).chmod(0o755)
            (p/'mode').write_text(initial)
            (p/'shell.qml').write_text('''import QtQuick
import Quickshell
import Quickshell.Io
import "BACKEND"
ShellRoot {
    HyprwhsprService { id: backend }
    FileView { id: mode; path: "FOLDER/mode" }
    FileView { id: visual; path: "FOLDER/runtime/hyprwhspr/visualizer_state" }
    property int step: 0
    property int ticks: 0
    function check(ok, message) {
        if (!ok) { console.error("FAIL " + message); Qt.exit(1); }
    }
    function setMode(value) { mode.setText(value); }
    Timer {
        interval: 100; running: true; repeat: true
        onTriggered: {
            if (++ticks > 180) { console.error("FAIL deadline"); Qt.exit(1); }
            if (backend.phase !== "" || backend.commandBusy) return;
            if (step === 0) {
                check(backend.state === "INITIAL", "initial state");
                setMode("recording"); backend.refresh();
            } else if (step === 1) {
                check(backend.state === "recording", "external recording");
                setMode("idle"); backend.refresh();
            } else if (step === 2) {
                check(backend.state === "idle", "external stop");
                setMode("offline"); backend.refresh();
            } else if (step === 3) {
                check(backend.state === "error", "offline");
                setMode("idle"); backend.refresh();
            } else if (step === 4) {
                check(backend.state === "idle", "restart");
                backend.toggle(); backend.toggle();
            } else if (step === 5) {
                check(backend.state === "recording", "confirmed toggle");
                setMode("reject"); backend.toggle();
            } else if (step === 6) {
                check(backend.state === "error", "zero exit command failure");
                setMode("bad"); backend.refresh();
            } else if (step === 7) {
                check(backend.state === "error", "unknown status");
                setMode("idle"); visual.setText("processing"); backend.refresh();
            } else if (step === 8) {
                check(backend.state === "processing", "native processing");
                check(backend.pollInterval === 400, "processing cadence");
                visual.setText("success"); backend.refresh();
            } else if (step === 9) {
                check(backend.state === "idle", "native processing end");
                setMode("slow"); backend.refresh(); backend.refresh(); backend.refresh();
            } else if (step === 10) {
                check(backend.state === "error", "bounded slow command");
                setMode("idle"); backend.refresh();
            } else {
                check(backend.state === "idle", "recovery after timeout");
                console.info("PASS backend transitions"); Qt.quit();
            }
            step++;
        }
    }
}
'''.replace('INITIAL', initial).replace('BACKEND', BACKEND.as_uri()).replace('FOLDER', str(p)))
            env = dict(os.environ, PATH=f'{p}:/usr/bin', DICTATION_FIXTURE=str(p),
                       QT_QPA_PLATFORM='offscreen', XDG_RUNTIME_DIR=str(p/'runtime'))
            result = subprocess.run([QS, '-p', str(p), '--no-color'], env=env,
                                    capture_output=True, text=True, timeout=25)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('PASS backend transitions', result.stdout + result.stderr)
            self.assertEqual((p/'toggles').read_text().splitlines(), ['toggle', 'toggle'])


if __name__ == '__main__':
    unittest.main()
