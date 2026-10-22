#!/usr/bin/env python3
"""Load the actual shell through its relative imports in a private Sway.

The session bus is private; the system bus address deliberately points to a
missing fixture socket so no real Polkit agent or system service is contacted.
"""
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tests/session_v2/fixtures'))
from headless import Lab

with Lab() as lab:
    lab.env.update(DBUS_SYSTEM_BUS_ADDRESS='unix:path='+str(lab.directory/'no-system-bus'),QT_QPA_PLATFORM='wayland')
    shell=ROOT/'quickshell/.config/quickshell/labfy-sway/shell.qml'
    process=lab.start(['dbus-run-session','--','quickshell','-p',str(shell)])
    time.sleep(3)
    log=(lab.directory/'child-1.log').read_text()
    assert 'Configuration Loaded' in log and process.poll() is None,log
    assert 'Binding loop' not in log,log
    print('Full shell private-compositor load: PASS',lab.directory)
