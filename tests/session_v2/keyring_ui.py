"""Actual chooser/Secret Service client on private Sway and private D-Bus only."""
import json
import shutil
import subprocess
from common import *
from lab import Lab
from test_keyring import KeyringTests

SOURCE = BACKEND
HARNESS = '''//@ pragma UseQApplication
import QtQuick
import Quickshell
import "sessionui"
ShellRoot {
 PanelWindow { id: bar; visible: false }
 SessionStartupPromptV2 { id: prompt; barWindow: bar; startupHost: true }
 Timer { interval: 1250; running: true; onTriggered: {
   if (!prompt.interactionArmed) { console.error("KEYRING_UI_FAIL_NOT_ARMED"); Qt.quit(); return; }
   if (Quickshell.env("CASE") !== "ready") {
     prompt.restoreRequested();
     if (prompt.attempted) { console.error("KEYRING_UI_FAIL_BYPASS"); Qt.quit(); return; }
     if (Quickshell.env("CASE") !== "restart-check") prompt.unlockRequested();
   }
 } }
 Timer { interval: 2300; running: true; onTriggered: {
   const mode = Quickshell.env("CASE");
   if (prompt.attempted || prompt.inProgress) { console.error("KEYRING_UI_FAIL_AUTORESTORE"); Qt.quit(); return; }
   if (mode === "ready" || mode === "accept") {
     if (!prompt.keyringReady) { console.error("KEYRING_UI_FAIL_NOT_READY"); Qt.quit(); return; }
     prompt.restoreRequested();
   } else {
     if (prompt.keyringReady) { console.error("KEYRING_UI_FAIL_FALSE_READY"); Qt.quit(); return; }
     prompt.newSessionRequested();
   }
 } }
 Timer { interval: 3700; running: true; onTriggered: {
   const mode = Quickshell.env("CASE");
   const okay = mode === "ready" || mode === "accept" ? prompt.restored && !prompt.visible : !prompt.visible && !prompt.attempted;
   console.log(okay ? "KEYRING_UI_PASS" : "KEYRING_UI_FAIL_FINAL"); Qt.quit();
 } }
}
'''
# The chooser and gate are production. Only restoration/checkpoint discovery are
# synthetic here; actual Executor/focus behavior is tested in keyring_runtime.py.
WRAPPER = '''import sys, json, os
from pathlib import Path
sys.path.insert(0, SOURCE)
from session_v2.cli import main
cmd=sys.argv[1]
with Path(os.environ['CALLS']).open('a') as log: log.write(cmd+'\\n')
if cmd.startswith('keyring-'): sys.exit(main())
if cmd == 'startup-status': value={'eligible':True,'claimed':True,'windows':4,'workspaces':2}
elif cmd == 'apply-last': value={'schema':'labfy.sway.session-v2-restore-attempt','version':1,'status':'success','transaction_id':'a'*32,'identity_level':'exact','final_tree_verified':True,'final_focus_verified':True,'slots_expected':4,'slots_filled':4,'applications_expected':3,'applications_observed':3,'anchors_created':3,'anchors_cleaned':3,'helpers_suspended':0,'helpers_resumed':0}
elif cmd == 'acknowledge-startup': value={'status':'acknowledged','choice':sys.argv[sys.argv.index('--choice')+1]}
else: raise RuntimeError('TEST_ONLY_UNEXPECTED')
print(json.dumps(value))
'''


def main():
    with Lab() as lab:
        print(lab.directory, flush=True)
        for mode in ('ready', 'accept', 'cancel', 'timeout', 'absent', 'still-locked', 'different'):
            with KeyringTests().service(mode) as (busenv, _):
                base = lab.directory / mode / 'config/quickshell/labfy-sway'
                base.mkdir(parents=True)
                for item in ('sessionui', 'controlcenter', 'theme'):
                    shutil.copytree(SOURCE / item, base / item)
                shutil.copy(SOURCE / 'SessionStartupPromptV2.qml', base)
                (base / 'shell.qml').write_text(HARNESS)
                (base / 'session-v2.py').write_text(WRAPPER.replace('SOURCE', repr(str(SOURCE))))
                calls = lab.directory / (mode + '.calls')
                env = {**lab.env, 'DBUS_SESSION_BUS_ADDRESS': busenv['DBUS_SESSION_BUS_ADDRESS'],
                       'XDG_CONFIG_HOME': str(base.parents[1]), 'XDG_RUNTIME_DIR': busenv['XDG_RUNTIME_DIR'],
                       'WAYLAND_DISPLAY': str(lab.directory / lab.env['WAYLAND_DISPLAY']),
                       'CASE': mode, 'CALLS': str(calls)}
                proc = subprocess.run(['qs', '-p', str(base), '--no-color'], env=env,
                                      capture_output=True, text=True, timeout=12)
                output = proc.stdout + proc.stderr
                (lab.directory / (mode + '.qml.log')).write_text(output)
                assert 'KEYRING_UI_PASS' in output and 'KEYRING_UI_FAIL' not in output, output
                seen = calls.read_text().splitlines()
                assert seen.count('apply-last') == (1 if mode in ('ready', 'accept') else 0), seen
                assert seen.count('acknowledge-startup') == 1, seen
                print(mode, 'PASS', flush=True)
        # Real QuickShell process destruction, not just a reset QML boolean.
        with KeyringTests().service('timeout') as (busenv, server):
            base = lab.directory / 'restart/config/quickshell/labfy-sway'
            base.mkdir(parents=True)
            for item in ('sessionui', 'controlcenter', 'theme'):
                shutil.copytree(SOURCE / item, base / item)
            shutil.copy(SOURCE / 'SessionStartupPromptV2.qml', base)
            (base / 'shell.qml').write_text(HARNESS)
            (base / 'session-v2.py').write_text(WRAPPER.replace('SOURCE', repr(str(SOURCE))))
            calls = lab.directory / 'restart.calls'
            env = {**lab.env, 'DBUS_SESSION_BUS_ADDRESS': busenv['DBUS_SESSION_BUS_ADDRESS'],
                   'XDG_CONFIG_HOME': str(base.parents[1]), 'XDG_RUNTIME_DIR': busenv['XDG_RUNTIME_DIR'],
                   'WAYLAND_DISPLAY': str(lab.directory / lab.env['WAYLAND_DISPLAY']),
                   'CASE': 'timeout', 'CALLS': str(calls)}
            first = subprocess.Popen(['qs', '-p', str(base), '--no-color'], env=env,
                                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            try:
                import select
                # Read raw pipe so TextIO buffering cannot hide the second line.
                observed = b''
                deadline = time.monotonic() + 8
                while b'PROMPT\n' not in observed and time.monotonic() < deadline:
                    if select.select([server.stdout], [], [], .2)[0]:
                        observed += os.read(server.stdout.fileno(), 4096)
                assert b'UNLOCK\n' in observed and b'PROMPT\n' in observed, observed
            finally:
                first.terminate()
                first.communicate(timeout=5)
            # A replacement shell reconstructs locked/busy from backend/D-Bus;
            # it must not reissue Unlock or Restore just because it restarted.
            env['CASE'] = 'restart-check'
            restarted = subprocess.run(['qs', '-p', str(base), '--no-color'], env=env,
                                       capture_output=True, text=True, timeout=12)
            output = restarted.stdout + restarted.stderr
            assert 'KEYRING_UI_PASS' in output and 'KEYRING_UI_FAIL' not in output, output
            seen = calls.read_text().splitlines()
            assert seen.count('keyring-unlock') == 1 and 'apply-last' not in seen, seen
            print('quickshell-restart-during-unlock PASS', flush=True)


if __name__ == '__main__': main()
