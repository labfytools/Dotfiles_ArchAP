"""Recette UI sans desktop utilisateur : compositor privé et CLI simulée.

Les composants QML V2 sont les vrais candidats ; seul le backend/Theme sont
des fixtures. Aucun appel logout ou restauration utilisateur n'est possible.
"""
import json
import shutil
import subprocess
from common import *
from lab import Lab, Surfaces, build_helper
from session_v2.storage import atomic, private_dir, read
from session_v2.checkpoint import Store
from session_v2.recovery import focused
from session_v2.ipc import location

SOURCE = REPO / 'quickshell/.config/quickshell/labfy-sway'
FAKE = '''import json, os, sys
from pathlib import Path
cmd = sys.argv[1]
log = Path(os.environ['LABFY_UI_LOG'])
with log.open('a') as s: s.write(cmd + '\\n')
mode = os.environ['LABFY_UI_MODE']
if cmd == 'startup-status': r = {'eligible': mode != 'claimed', 'claimed': mode != 'claimed', 'windows': 3, 'workspaces': 2}
elif cmd == 'apply-last':
 r = {'schema':'labfy.sway.session-v2-restore-attempt', 'version':1, 'status':'success', 'transaction_id':'a'*32, 'identity_level':'exact', 'final_tree_verified':mode != 'invalid', 'final_focus_verified':True, 'slots_expected':3, 'slots_filled':3, 'applications_expected':2, 'applications_observed':2, 'anchors_created':3, 'anchors_cleaned':3, 'helpers_suspended':1, 'helpers_resumed':1}
 if mode == 'failure': r = {'status':'failed', 'reason':'APPLICATION_WINDOWS_INCOMPLETE'}
elif cmd == 'acknowledge-startup': r = {'status':'acknowledged', 'choice':sys.argv[sys.argv.index('--choice')+1]}
elif cmd == 'restore-status': r = {'status':'failed', 'phase':'resolve', 'reason':'APPLICATION_WINDOWS_INCOMPLETE'}
else: raise RuntimeError('UNEXPECTED_COMMAND')
print(json.dumps(r))
'''
HARNESS = '''//@ pragma UseQApplication
import QtQuick
import Quickshell
import Quickshell.Wayland
ShellRoot {
 PanelWindow { id: bar; visible: false }
 // Cette seconde surface TEST_ONLY maintient le focus nul après le retrait
 // du chooser. Elle ne disparaît qu'après le refus, avant activation explicite.
 PanelWindow {
   id: blocker
   exclusionMode: ExclusionMode.Ignore
   exclusiveZone: 0
   WlrLayershell.layer: WlrLayer.Overlay
   WlrLayershell.keyboardFocus: visible ? WlrKeyboardFocus.Exclusive : WlrKeyboardFocus.None
   visible: Quickshell.env("LABFY_UI_MODE") === "deferred-real"
   anchors { top: true }
   implicitWidth: 80; implicitHeight: 40
 }
 SessionStartupPromptV2 { id: prompt; barWindow: bar; startupHost: true }
 Timer { interval: 600; running: true; onTriggered: {
   prompt.restoreRequested();
   if (prompt.attempted) { console.error("UI_TEST_EARLY_ACTIVATION"); Qt.quit(); }
 } }
 Timer { interval: 1000; running: true; onTriggered: {
   if (Quickshell.env("LABFY_UI_MODE") === "deferred-real") console.log("UI_TEST_NULL_READY");
 } }
 Timer { interval: 2100; running: true; onTriggered: {
   if (Quickshell.env("LABFY_UI_MODE") !== "deferred-real") return;
   if (!prompt.retryAllowed || !prompt.awaitingUserFocus || prompt.focusable || !prompt.visible) {
     console.error("UI_TEST_FAIL_DEFERRED"); Qt.quit(); return;
   }
   blocker.visible = false;
   console.log("UI_TEST_ACTIVATE_EXPLICITLY");
 } }
 Timer { interval: 2700; running: true; onTriggered: {
   if (Quickshell.env("LABFY_UI_MODE") === "deferred-real") prompt.restoreRequested();
 } }
 Timer { interval: 1400; running: true; onTriggered: {
   if (Quickshell.env("LABFY_UI_MODE") === "claimed") return;
   if (!prompt.interactionArmed) { console.error("UI_TEST_NOT_ARMED"); Qt.quit(); return; }
   if (Quickshell.env("LABFY_UI_MODE") === "new") prompt.newSessionRequested();
   else { prompt.restoreRequested(); prompt.restoreRequested(); }
 } }
 Timer { interval: 4300; running: true; onTriggered: {
   const mode = Quickshell.env("LABFY_UI_MODE");
   const okay = (mode === "success" || mode === "real" || mode === "deferred-real") ? prompt.restored && !prompt.visible
     : (mode === "failure" || mode === "invalid") ? prompt.failed && prompt.visible
     : !prompt.visible && !prompt.attempted;
   if (prompt.failed) prompt.restoreRequested();
   console.log(okay ? "UI_TEST_PASS" : "UI_TEST_FAIL"); Qt.quit();
 } }
}
'''


def main():
    rows = []
    with Lab() as lab:
        for mode in ('success', 'failure', 'invalid', 'new', 'claimed', 'real', 'deferred-real'):
            config = lab.directory / mode / 'config'
            base = config / 'quickshell/labfy-sway'
            base.mkdir(parents=True)
            shutil.copytree(SOURCE / 'sessionui', base / 'sessionui')
            (base / 'controlcenter').mkdir()
            shutil.copyfile(SOURCE / 'SessionStartupPromptV2.qml', base / 'SessionStartupPromptV2.qml')
            shutil.copyfile((BACKEND / 'controlcenter/ActionButton.qml'), base / 'controlcenter/ActionButton.qml')
            (base / 'theme').mkdir()
            (base / 'theme/qmldir').write_text('singleton Theme 1.0 Theme.qml\n')
            colors = 'popupBackground foreground secondaryForeground lavender buttonBackground emphasisBackground border danger'
            (base / 'theme/Theme.qml').write_text('pragma Singleton\nimport QtQuick\nQtObject {\n' + '\n'.join('property color ' + c + ': "#333333"' for c in colors.split()) + '\n}\n')
            (base / 'session-v2.py').write_text(FAKE)
            (base / 'shell.qml').write_text(HARNESS)
            log = lab.directory / (mode + '.calls')
            env = {**lab.env, 'XDG_CONFIG_HOME': str(config), 'LABFY_UI_MODE': mode, 'LABFY_UI_LOG': str(log)}
            apps = None
            if mode in ('real', 'deferred-real'):
                # Vrai moteur avec chooser visible : tester aussi l'interaction
                # entre focus layer-shell et la postcondition finale Sway.
                env['XDG_STATE_HOME'] = str(private_dir(lab.directory / (mode + '-state')))
                env['XDG_RUNTIME_DIR'] = str(private_dir(lab.directory / (mode + '-runtime')))
                # Le display absolu conserve le socket Wayland privé alors que
                # les journaux backend sont propres à ce scénario.
                env['WAYLAND_DISPLAY'] = str(lab.directory / lab.env['WAYLAND_DISPLAY'])
                real_backend = BACKEND
                anchor_binary = build(lab.directory)
                (base / 'session-v2.py').write_text('import sys, os\nfrom pathlib import Path\nsys.path.insert(0, ' + repr(str(real_backend)) + ')\nfrom session_v2.cli import main\nwith Path(os.environ["LABFY_UI_LOG"]).open("a") as s: s.write(sys.argv[1] + "\\n")\nsys.exit(main(sys.argv[1:] + [\"--anchor-binary\", ' + repr(str(anchor_binary)) + ']))\n')
                apps = Surfaces(lab, build_helper(lab.directory))
                lab.command('workspace TEST_ONLY_SOURCE')
                music = apps.create('limusic-app')
                music_origin = location(lab.tree(), music['id'])
                foreign = None
                if mode == 'deferred-real':
                    lab.command('workspace TEST_ONLY_FOREIGN')
                    foreign = apps.create('TEST_ONLY_FOREIGN')
                data = fixture('A', 'TEST_ONLY_TARGET')
                data['metadata']['sway_session'] = 'previous-session'
                data['applications'] = [{'application_id': 'limusic', 'desktop_entry': 'limusic.desktop', 'strategy': 'managed-autostart',
                                         'managed_by': 'sway-autostart', 'expected_windows': 1, 'identity_provider': None}]
                data['window_slots'][0].update(application_id='limusic', identity_evidence={'type': 'application-singleton', 'id': 'limusic'})
                Store(Path(env['XDG_STATE_HOME']) / 'labfy-sway/session-v2').checkpoint(data)
            argv = ['qs', '-p', str(base), '--no-color']
            if mode == 'deferred-real':
                # Le contrôleur observe le vrai Sway puis simule uniquement
                # l'action utilisateur explicite. Aucun focus produit par l'UI.
                with subprocess.Popen(argv, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True) as proc:
                    output = ''
                    try:
                        import select
                        import time
                        deadline = time.monotonic() + 15
                        activated = False
                        null_seen = False
                        while proc.poll() is None and time.monotonic() < deadline:
                            if not select.select([proc.stdout], [], [], .2)[0]: continue
                            line = proc.stdout.readline()
                            output += line
                            if 'UI_TEST_NULL_READY' in line:
                                assert focused(lab.tree()) == {'con_id': None, 'workspace': None}, (focused(lab.tree()), output)
                                null_seen = True
                            if 'UI_TEST_ACTIVATE_EXPLICITLY' in line:
                                assert log.read_text().splitlines().count('apply-last') == 1
                                runtime = Path(env['XDG_RUNTIME_DIR']) / 'labfy-sway'
                                assert not (runtime / 'session-v2-recovery.json').exists()
                                assert not (runtime / 'session-v2-restore-attempt.json').exists()
                                assert location(lab.tree(), music['id']) == music_origin
                                lab.command(f'[con_id={foreign["id"]}] focus')
                                activated = True
                        proc.wait(timeout=2)
                        output += proc.stdout.read()
                        assert null_seen and activated, output
                    finally:
                        if proc.poll() is None: proc.kill(); proc.wait(timeout=3)
                assert focused(lab.tree()) == {'con_id': foreign['id'], 'workspace': 'TEST_ONLY_FOREIGN'}
                assert len([n for n in lab.windows() if n['app_id'] == 'limusic-app']) == 1
            else:
                result = subprocess.run(argv, env=env, capture_output=True, text=True, timeout=15)
                output = result.stdout + result.stderr
            if mode in ('real', 'deferred-real'):
                report = read(Path(env['XDG_RUNTIME_DIR']) / 'labfy-sway/session-v2-restore-attempt.json')
                assert report['status'] == 'success', report
                apps.close()
            assert 'UI_TEST_PASS' in output and 'UI_TEST_FAIL' not in output, output
            calls = log.read_text().splitlines()
            assert calls.count('apply-last') == (2 if mode == 'deferred-real' else 1 if mode in ('success', 'failure', 'invalid', 'real') else 0), calls
            assert calls.count('acknowledge-startup') == (1 if mode in ('success', 'new', 'real', 'deferred-real') else 0), calls
            rows.append({'case': mode, 'calls': calls, 'result': 'PASS'})
            print(mode, 'PASS', flush=True)
    atomic(private_dir(EVIDENCE) / 'ui-test-only.json', {'cases': rows})


if __name__ == '__main__': main()
