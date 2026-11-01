#!/usr/bin/env python3
"""Synthetic dashboard on an isolated headless Sway; never touches the live shell."""
import json
import resource
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tests/session_v2/fixtures'))
from headless import Lab
SOURCE = ROOT / 'quickshell/.config/quickshell/labfy-sway'
QS = str(Path.home() / '.local/opt/quickshell-qt612-popup/bin/quickshell')


def call(lab, fixture, name, *args):
    result = subprocess.run([QS, 'ipc', '-p', str(fixture), 'call', 'fixture', name, *map(str,args)],
                            env=lab.env, text=True, capture_output=True, timeout=5)
    if result.returncode:
        raise RuntimeError(result.stderr[-1500:])
    if not result.stdout.strip():
        return None
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return result.stdout.strip()


with Lab() as lab:
    lab.env['DBUS_SESSION_BUS_ADDRESS'] = os.environ['DBUS_SESSION_BUS_ADDRESS']
    config = Path(lab.env['XDG_CONFIG_HOME']) / 'quickshell/labfy-sway'
    config.mkdir(parents=True)
    (config / 'theme').symlink_to(SOURCE / 'theme', target_is_directory=True)
    monitor = config / 'systemmonitor'
    monitor.mkdir()
    for name in ('Sparkline.qml', 'MonitorPanel.qml'):
        content = (SOURCE / 'systemmonitor' / name).read_text()
        if name == 'MonitorPanel.qml':
            content = content.replace('    grabFocus: true', '    grabFocus: false')
            content = content.replace('    signal dismissed()', '''    signal dismissed()
    function metrics(): string {
        return JSON.stringify({width:width,height:height,screenWidth:barWindow.screen.width,
            screenHeight:barWindow.screen.height,gridHeight:grid.height,viewport:dashboard.height,
            cpu:[cpuBox.x,cpuBox.y,cpuBox.width,cpuBox.height],gpu:[gpuBox.x,gpuBox.y,gpuBox.width,gpuBox.height],
            memory:[memoryBox.x,memoryBox.y,memoryBox.width,memoryBox.height],
            processes:[processBox.x,processBox.y,processBox.width,processBox.height],
            disk:[diskBox.x,diskBox.y,diskBox.width,diskBox.height],
            network:[netBox.x,netBox.y,netBox.width,netBox.height],rows:processList.count,
            cores:coreKeys().length,visible:visible,collect:service.processesVisible});
    }''')
        (monitor / name).write_text(content)
    fixture = config / 'fixture.qml'
    fixture.write_text('''//@ pragma UseQApplication
import QtQuick
import Quickshell
import Quickshell.Io
import "systemmonitor"
ShellRoot {
 PanelWindow {id:bar; anchors {top:true;left:true;right:true} implicitHeight:34; focusable:true; color:"#1e1e2e"
  Item {id:indicator; x:parent.width-30; width:26; height:26}
 }
 QtObject { id:service; property bool processesVisible:false
  property var data: ({memory:{used:8e9,total:16e9,available:8e9,cache:1e9,swapUsed:1e9,swapTotal:6e9},gpu:null,zram:null,
    psi:{some:[1,2,3],full:[0,0,0]},temperatures:{cpu:65,gpu:null},disk:{used:400e9,total:1000e9,available:500e9,filesystem:"btrfs"},
    load:["1.2","1.1","1.0"],frequencies:[{currentMHz:3000}],network:null})
  property var usage: ({cpu:42,threads:{cpu0:10,cpu1:20,cpu2:30,cpu3:40,cpu4:50,cpu5:60,cpu6:70,cpu7:80,
    cpu8:11,cpu9:21,cpu10:31,cpu11:41,cpu12:51,cpu13:61,cpu14:71,cpu15:81}})
  property var rates: ({rx:100000,tx:50000})
  property var processRows: []
  property var histories: ({cpu:Array.from({length:600},(_,i)=>({value:i%100})),gpu:[],ram:[],psi:[],rx:[],tx:[]})
 }
 MonitorPanel {id:popup;barWindow:bar;indicator:indicator;service:service;}
 IpcHandler { target:"fixture"
  function state(): string {return popup.metrics()}
  function setRows(count:int): void { service.processRows=Array.from({length:count},(_,i)=>({pid:i+1,name:"processus très long "+i,cpu:i%100,rss:i*1000000})); }
  function hide(): void {popup.visible=false}
  function show(): void {popup.visible=true}
 }
}
''')
    proc = lab.start([QS, '-p', str(fixture), '--no-color'])
    deadline = time.monotonic() + 12
    while True:
        try:
            call(lab, fixture, 'state')
            break
        except RuntimeError:
            if time.monotonic() > deadline:
                raise RuntimeError('Fixture failed to load: ' + str(lab.directory) + '\n' + (lab.directory / 'child-1.log').read_text()[-5000:])
            time.sleep(.1)
    call(lab,fixture,'show')
    for scale in (1, 1.4):
        lab.command(f'output HEADLESS-1 scale {scale}')
        for count in (0, 80):
            call(lab, fixture, 'setRows', count)
            time.sleep(.15)
            state = call(lab, fixture, 'state')
            assert state['visible'] and state['collect'], state
            assert state['cores'] == 16 and state['rows'] == count, state
            assert state['width'] <= state['screenWidth'] - 20, state
            assert state['height'] <= state['screenHeight'] - 34, state
            for key in ('cpu','gpu','memory','processes','disk','network'):
                x,y,w,h = state[key]
                assert x >= 0 and y >= 0 and w > 0 and h > 0 and x+w <= state['width'] and y+h <= state['gridHeight'], (key,state)
            if scale == 1 and count == 80:
                image = Path('/tmp/step15b2-dashboard-headless.png')
                subprocess.run(['grim','-o','HEADLESS-1',str(image)], env=lab.env, check=True)
                print('SCREENSHOT',image)
            print('PASS',scale,count,state['width'],state['height'])
    call(lab,fixture,'hide')
    assert not call(lab,fixture,'state')['collect']
    call(lab,fixture,'show')
    print('PASS close stops process collection')
    stat = Path(f'/proc/{proc.pid}/stat').read_text().split()
    rss = int(Path(f'/proc/{proc.pid}/status').read_text().split('VmRSS:')[1].split()[0])
    print('FIXTURE_QS_RSS_KIB', rss)

    errors = [line for line in (lab.directory / 'child-1.log').read_text().splitlines() if 'ERROR:' in line]
    assert not errors, errors[-20:]
