#!/usr/bin/env python3
"""STEP15A: synthetic production components on an owned headless Sway.

CONTRACT: no inherited compositor, bus, clipboard, notifications or HOME.
Copies add measurement hooks only; the production geometry remains unchanged.
Artifacts contain only synthetic pixels and aggregate performance measurements.
"""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'tests/session_v2/fixtures'))
from headless import Lab
SOURCE = REPO / 'quickshell/.config/quickshell/labfy-sway'
QS = str(Path.home() / '.local/opt/quickshell-qt612-popup/bin/quickshell')
ART = Path(os.environ['STEP15A_ARTIFACTS'])
ART.mkdir(parents=True, exist_ok=True, mode=0o700)


def call(lab, path, name, *args):
    p = subprocess.run([QS, 'ipc', '-p', str(path), 'call', 'fixture', name, *map(str,args)],
                       env=lab.env, capture_output=True, text=True, timeout=5)
    if p.returncode:
        raise RuntimeError('Synthetic IPC failed: ' + p.stderr[-1000:])
    return json.loads(p.stdout) if p.stdout.strip() else None


def wait(lab, path):
    end = time.monotonic()+12
    while time.monotonic()<end:
        try:
            return call(lab,path,'state')
        except RuntimeError:
            time.sleep(.1)
    raise RuntimeError('Synthetic fixture did not load: '+str(lab.directory))


with Lab() as lab:
    lab.env['DBUS_SESSION_BUS_ADDRESS'] = os.environ['DBUS_SESSION_BUS_ADDRESS']
    config=Path(lab.env['XDG_CONFIG_HOME'])/'quickshell/labfy-sway'
    config.mkdir(parents=True)
    # Production modules are referenced by absolute import; writable generated
    # appearance/session paths resolve only inside the isolated environment.
    for name in ['theme','components']:
        (config/name).symlink_to(SOURCE/name, target_is_directory=True)
    dc=config/'datecenter'; dc.mkdir()
    for p in (SOURCE/'datecenter').glob('*.qml'):
        text=p.read_text()
        if p.name=='NotificationList.qml':
            text=text.replace('    id: list', '''    id: list
    function scrollEnd() { notificationView.positionViewAtEnd(); }
    function measureList() { return { y:notificationView.contentY, content:notificationView.contentHeight,
        viewport:notificationView.height, count:rows.length }; }''')
        if p.name=='MediaPlayer.qml':
            a=text.index('    readonly property var player: {');b=text.index('\n    visible:',a)
            text=text[:a]+'    property var player: null\n'+text[b:]
            text=text.replace('    property var player: null', '''    property var player: null
    function artMetrics() { return { width:artwork.sourceSize.width,height:artwork.sourceSize.height,
        status:artwork.status }; }''')
        if p.name=='DateCenter.qml':
            text=text.replace('MediaPlayer { width:', 'MediaPlayer { id: media; width:').replace('NotificationList { width:', 'NotificationList { id: notices; width:')
            text=text.replace('MediaPlayer { id: mediaCard;', 'MediaPlayer { id: media;').replace('mediaCard.', 'media.').replace('NotificationList {\n', 'NotificationList {\n                id: notices\n')
            text=text.replace('    property bool opening: false', '''    property bool opening: false
    function setPlayer(value) { media.player = value; }
    function scrollList() { notices.scrollEnd(); }
    function metrics() {
        return {width:width,height:height,implicitHeight:implicitHeight,
            availableHeight:barWindow.screen.height-barWindow.height-22,player:media.visible,playerHeight:media.height,playerY:media.y,
            listY:notices.y,listHeight:notices.height,contentHeight:content.childrenRect.height,
            art:media.artMetrics(),list:notices.measureList()};
    }''')
        (dc/p.name).write_text(text)
    art=lab.directory/'large-art.png'
    subprocess.run(['magick','-size','4096x4096','xc:#b4befe',str(art)],check=True,env=lab.env)
    fixture=config/'fixture.qml'
    fixture.write_text('''//@ pragma UseQApplication
import QtQuick
import Quickshell
import Quickshell.Io
import "datecenter"
ShellRoot {
 PanelWindow { id:bar; anchors {top:true;left:true;right:true} implicitHeight:34
  Item {id:clockItem; x:parent.width/2; width:1; height:20}
 }
 QtObject {id:fakePlayer; property string dbusName:"org.mpris.MediaPlayer2.TEST_ONLY"
  property string trackTitle:"TEST_ONLY long title "+"x".repeat(2000)
  property string trackArtist:"TEST_ONLY artist"; property string trackArtUrl:"ART"
  property bool isPlaying:false; property bool canGoPrevious:true
  property bool canTogglePlaying:true; property bool canGoNext:true
  function previous() {} function next() {} function togglePlaying() {}
 }
 QtObject {id:service; property var records:[]
  function setDateCenterVisible(value) {} function live(id) {return null}
  function dismiss(id) {records=records.filter(r=>r.internalId!==id)}
  function clearAll() {records=[]}
 }
 DateCenter {id:popup;barWindow:bar;clockItem:clockItem;notificationService:service}
 IpcHandler {target:"fixture"
  function state():string {return JSON.stringify(popup.metrics())}
  function setup(count:int,player:bool):void {
   popup.setPlayer(player?fakePlayer:null);
   service.records=Array.from({length:count},(_,i)=>({internalId:i+1,appName:"TEST_ONLY",
    summary:"TEST_ONLY notification "+i,body:"synthetic long body ".repeat(40),image:""}));
   popup.requestOpen();
  }
  function remove():void {service.dismiss(1)}
  function clear():void {service.clearAll()}
  function incoming():void {service.records=[{internalId:999,appName:"TEST_ONLY",summary:"Incoming",body:""}].concat(service.records)}
  function hide():void {popup.requestClose()}
  function scroll():void {popup.scrollList()}
 }
}
'''.replace('ART',art.as_uri()))
    proc=lab.start([QS,'-p',str(fixture),'--no-color'])
    wait(lab,fixture)
    results=[]
    for scale in [1,1.4]:
        lab.command(f'output HEADLESS-1 scale {scale}')
        for player in [False,True]:
            for n in [0,1,5,200]:
                call(lab,fixture,'setup',n,str(player).lower());time.sleep(.25)
                m=call(lab,fixture,'state');m.update(scale=scale,notifications=n)
                results.append(m)
                if player: assert m['playerHeight']==116,m
                else: assert m['playerHeight']==0,m
                assert m['height']>=m['contentHeight']+32-1,('clipping',m)
                assert m['height']<=m['availableHeight']+1,('screen overflow',m)
                if n==200:
                    call(lab,fixture,'scroll');time.sleep(.15)
                    scrolled=call(lab,fixture,'state')
                    assert scrolled['playerY']==m['playerY'] and scrolled['playerHeight']==m['playerHeight']
                    assert scrolled['list']['y']>0,scrolled
                    assert scrolled['list']['y']+scrolled['list']['viewport']>=scrolled['list']['content']-2,scrolled
                    if player:
                        assert scrolled['art']['width']<=144 and scrolled['art']['height']<=144,scrolled
                if n in [0,200]:
                    subprocess.run(['grim','-o','HEADLESS-1',str(ART/f'date-{scale}-{player}-{n}.png')],env=lab.env,check=True)
        call(lab,fixture,'setup',5,'true');call(lab,fixture,'remove');time.sleep(.15)
        results.append(dict(action='remove',**call(lab,fixture,'state')))
        call(lab,fixture,'clear');time.sleep(.15)
        results.append(dict(action='clear',**call(lab,fixture,'state')))
        call(lab,fixture,'incoming');time.sleep(.15)
        results.append(dict(action='incoming',**call(lab,fixture,'state')))
        call(lab,fixture,'setup',0,'false');time.sleep(.15)
        results.append(dict(action='player-disappeared',**call(lab,fixture,'state')))
    (ART/'date-metrics.json').write_text(json.dumps(results,indent=2))
    call(lab,fixture,'hide')
    print(json.dumps({'dateCases':len(results),'lab':str(lab.directory)}))
