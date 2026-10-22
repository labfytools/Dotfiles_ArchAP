#!/usr/bin/env python3
"""Run existing production chooser/restore scenarios with the dock present.

Only the test harness is extended in memory. No Session V2 source, journal,
keyring/PAM configuration or active graphical environment is changed.
"""
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tests/session_v2'))
import keyring_ui
import phase3b_ui

source=(ROOT/'quickshell/.config/quickshell/labfy-sway/dock').as_uri()
for module in (keyring_ui,phase3b_ui):
    module.HARNESS=module.HARNESS.replace('import Quickshell\n',
        'import Quickshell\nimport "'+source+'" as D\n')
    module.HARNESS=module.HARNESS.replace('ShellRoot {','''ShellRoot {
 D.Dock { id: compatibilityDock; modelData: Quickshell.screens[0] }
 Timer { interval: 3500; running: true; onTriggered: {
   if (compatibilityDock.phase !== "hidden") {
     console.error("DOCK_COMPAT_FAIL_NOT_HIDDEN"); Qt.quit();
   }
 } }
''')
    module.main()
    print(module.__name__+' WITH_DOCK PASS',flush=True)
