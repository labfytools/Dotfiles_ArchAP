#!/usr/bin/env python3
"""Real Wayland regression: isolated JSON, no backend commands, screenshots.

Requires a running SwayFX session, grim, Pillow, and a Quickshell executable.
Only the copied renderer is instrumented. Never write the production snapshot.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time

from PIL import Image, ImageChops, ImageStat

PARSER = argparse.ArgumentParser(description=__doc__)
PARSER.add_argument('--qs', default='qs')
PARSER.add_argument('--artifacts', type=Path)
ARGS = PARSER.parse_args()
ROOT = ARGS.artifacts or Path(tempfile.mkdtemp(prefix='removable-geometry-'))
ROOT.mkdir(parents=True, exist_ok=True)
CONFIG = ROOT / 'config'
SOURCE = Path(__file__).resolve().parents[2]
shutil.copytree(SOURCE, CONFIG, ignore=shutil.ignore_patterns('tests', '__pycache__'), dirs_exist_ok=True)
STATE = ROOT / 'snapshot.json'
COMPONENT = CONFIG / 'status/RemovableMediaIndicator.qml'
source = COMPONENT.read_text()
assert '+ "/labfy-removable-media.json"' in source
source = source.replace('Quickshell.env("XDG_RUNTIME_DIR")\n        + "/labfy-removable-media.json"', json.dumps(str(STATE)))
# INVARIANT: no test click can ever dispatch a real storage command. FileView
# still consumes actual atomic JSON replacements through production validation.
source = source.replace('function runAction(action, device) {', 'function runAction(action, device) { return;')
source = source.replace('Repeater {\n                        model: indicator.devices', 'Repeater {\n                        id: deviceRepeater\n                        model: indicator.devices')
source = source.replace('Flow {\n                                    width:', 'Flow {\n                                    id: actionRow\n                                    width:')
source = source.replace('    signal toggleRequested()', '''    function measure() {
        let cards = [];
        for (let i=0; i<deviceRepeater.count; ++i) cards.push(deviceRepeater.itemAt(i).metrics());
        return JSON.stringify({visible:popup.visible, width:popup.width, height:popup.height,
            requestedHeight:popup.implicitHeight, contentHeight:popupContent.implicitHeight,
            contentWidth:popupContent.width, cards:cards});
    }
    signal toggleRequested()''')
source = source.replace('required property var modelData', '''required property var modelData
                            function metrics() {
                                let texts=[];
                                for (let t of cardContent.children) {
                                    if (t.font && t.visible) texts.push({text:t.text,x:t.x,y:t.y,
                                        width:t.width,height:t.height,pixelSize:t.font.pixelSize});
                                }
                                let buttons=[];
                                for (let b of actionRow.children) {
                                    if (b.visible) buttons.push({label:b.label,x:b.x,y:b.y,width:b.width,height:b.height});
                                }
                                return {name:modelData.display_name,x:x,y:y,width:width,height:height,
                                    texts:texts,buttons:buttons};
                            }''')
COMPONENT.write_text(source)
# Existing neighboring popups run in their own explicit TEST_ONLY modes.
for filename in ['PrintingIndicator.qml', 'PhotoBackupIndicator.qml']:
    path = CONFIG / 'status' / filename
    text = path.read_text().replace('    signal toggleRequested()', """    function measure() {
        return JSON.stringify({visible:popup.visible,width:popup.width,height:popup.height,
            requestedHeight:popup.implicitHeight,contentHeight:content.implicitHeight});
    }
    signal toggleRequested()""")
    path.write_text(text)
FIXTURE = CONFIG / 'Fixture.qml' 
FIXTURE.write_text('''import QtQuick
import Quickshell
import Quickshell.Io
import Quickshell.Wayland
import "status"
ShellRoot {
 PanelWindow {
  WlrLayershell.namespace: "labfy-removable-geometry-test"
  exclusionMode: ExclusionMode.Ignore
  anchors {top:true; left:true}
  margins {top:100; left:100}
  implicitWidth:70; implicitHeight:32
  color:"#1e1e2e"
  RemovableMediaIndicator {id:indicator; x:22; y:3}
  PrintingIndicator {id:printing; x:22; y:3}
  PhotoBackupIndicator {id:backup; x:22; y:3}
  IpcHandler {
   target:"fixture"
   function otherOpen(kind:string):void {if(kind=="printing") printing.popupOpen=true; else backup.popupOpen=true;}
   function otherClose(kind:string):void {if(kind=="printing") printing.popupOpen=false; else backup.popupOpen=false;}
   function otherState(kind:string,mode:string):void {
       if(kind=="printing") printing.printingData=printing.fixture(mode);
       else backup.backupData=backup.fixture(mode);
   }
   function otherMeasure(kind:string):string {return kind=="printing" ? printing.measure() : backup.measure();}
   function open():void {indicator.popupOpen=true;}
   function close():void {indicator.popupOpen=false;}
   function measure():string {return indicator.measure();}
  }
 }
}
''')
VENTOY = dict(runtime_id='test-ventoy',safe_remove_runtime_id='test-drive',kind='block',
    actions=['unmount','open','safe-remove'],display_name='Ventoy',label='Ventoy',
    filesystem='exfat',size_bytes=64000000000,mount_point='/run/media/test/Ventoy',
    mounted=True,removable=True,ejectable=True,power_off_capable=False,busy=False,error=None)
PHOTO = dict(VENTOY,runtime_id='test-photo',safe_remove_runtime_id='test-drive-photo',
    display_name='PHOTO_BAK',label='PHOTO_BAK',mount_point='/run/media/test/PHOTO_BAK',size_bytes=2000000000000)
UNMOUNTED = dict(VENTOY,mounted=False,mount_point=None,actions=['mount','safe-remove'])
STEPS = [('one',[VENTOY]),('two',[VENTOY,PHOTO]),('one-again',[VENTOY]),
         ('unmounted',[UNMOUNTED]),('empty',[]),('reappeared',[VENTOY])]
records = []

def publish(devices):
    temporary = ROOT / 'snapshot.next'
    temporary.write_text(json.dumps(dict(schema='labfy.removable-media',version=2,
        updated_at=time.time_ns()//1000000,devices=devices)))
    os.replace(temporary, STATE)

def ipc(method, *arguments):
    return subprocess.run([ARGS.qs,'ipc','-p',str(FIXTURE),'call','fixture',method,*arguments],
        capture_output=True,text=True,check=True).stdout.strip()

def measure():
    return json.loads(ipc('measure'))

def wait_for(devices):
    deadline=time.monotonic()+5
    while time.monotonic()<deadline:
        value=measure()
        if [c['name'] for c in value['cards']]==[d['display_name'] for d in devices]:
            # Test settling allowance only; production contains no relayout timer.
            time.sleep(.25)
            return measure()
        time.sleep(.05)
    raise AssertionError('JSON did not propagate to the live popup')

def capture(path, value):
    subprocess.run(['grim','-g',f"122,135 400x{value['height']}",str(path)],check=True)

def check(value, devices):
    assert value['visible'], 'popup closed during a transition'
    assert value['width']==400 and value['contentWidth']==376, value
    assert value['height']==min(560,value['contentHeight']+24), value
    previous_bottom=0
    for card in value['cards']:
        assert card['width']==376 and card['height']==108, card
        assert card['y']>=previous_bottom, card
        previous_bottom=card['y']+card['height']
        assert [t['pixelSize'] for t in card['texts']]==[14,11,11], card
        previous_button=None
        for button in card['buttons']:
            assert button['height']==30 and button['x']+button['width']<=356, button
            if previous_button:
                assert button['x']>=previous_button['x']+previous_button['width']+6, card
            previous_button=button
    assert previous_bottom==value['contentHeight'] or not devices, value

publish([VENTOY])
env=dict(os.environ,WAYLAND_DEBUG='1',LABFY_REMOVABLE_MEDIA_TEST_STATE='',
    LABFY_PRINTING_TEST_STATE='empty',LABFY_PHOTO_BACKUP_TEST_STATE='idle')
with (ROOT/'wayland.log').open('w') as log:
    process=subprocess.Popen([ARGS.qs,'-p',str(FIXTURE)],stdout=log,stderr=log,env=env)
    try:
        deadline=time.monotonic()+15
        while True:
            try:
                ipc('open')
                break
            except subprocess.CalledProcessError:
                if process.poll() is not None or time.monotonic()>deadline:
                    raise RuntimeError(f'Fixture did not start: {ROOT}/wayland.log')
                time.sleep(.1)
        # CONTRACT: eighteen transitions on ONE continuously mapped popup.
        for cycle in range(3):
            for label,devices in STEPS:
                publish(devices)
                value=wait_for(devices)
                value.update(cycle=cycle,step=label)
                records.append(value)
                capture(ROOT/f'{cycle}-{label}.png',value)
                check(value,devices)
        # Reference renders use the close/reopen path only AFTER the dynamic run.
        # This catches the old stretched-buffer bug even when QML geometry passes.
        differences=[]
        for label,devices in STEPS:
            ipc('close'); publish(devices); wait_for(devices); ipc('open'); time.sleep(.3)
            value=measure(); check(value,devices)
            reference=ROOT/f'reference-{label}.png'; capture(reference,value)
            expected=Image.open(reference).convert('RGB')
            for cycle in range(3):
                actual=Image.open(ROOT/f'{cycle}-{label}.png').convert('RGB')
                assert actual.size==expected.size, (label,actual.size,expected.size)
                delta=ImageChops.difference(actual,expected)
                changed=sum(1 for px in delta.get_flattened_data() if max(px)>24)
                ratio=changed/(actual.width*actual.height)
                # Fractional-scale round trips can alter rectangle edge coverage by
                # up to 16/255 in the measured session, with identical glyphs.
                # Bound both significant differences and the mean error; a
                # stretched stale buffer fails by a wide margin.
                mean_error=max(ImageStat.Stat(delta).mean)
                differences.append(dict(cycle=cycle,step=label,changed_fraction=ratio,mean_error=mean_error))
                assert mean_error<1, (label,cycle,mean_error)
                assert ratio<.001, (label,cycle,ratio)
        (ROOT/'pixel-comparison.json').write_text(json.dumps(differences,indent=2))
        ipc('close')
        other_results=[]
        for kind,modes in [('printing',['empty','jobs','unavailable','empty']),
                           ('backup',['idle','copying','error','success','unmounted','idle'])]:
            ipc('otherOpen',kind)
            for index,mode in enumerate(modes):
                ipc('otherState',kind,mode); time.sleep(.35)
                value=json.loads(ipc('otherMeasure',kind))
                assert value['visible'] and value['height']==value['requestedHeight'], value
                live=ROOT/f'{kind}-{index}-{mode}.png'
                geometry=f"122,135 {value['width']}x{value['height']}"
                subprocess.run(['grim','-g',geometry,str(live)],check=True)
                # Keep the dynamic run open; reference comparisons follow later.
                other_results.append(dict(kind=kind,index=index,mode=mode,**value))
            ipc('otherClose',kind)
        for record in other_results:
            kind,mode,index=record['kind'],record['mode'],record['index']
            ipc('otherState',kind,mode); ipc('otherOpen',kind); time.sleep(.35)
            value=json.loads(ipc('otherMeasure',kind))
            assert value['height']==record['height'], (record,value)
            reference=ROOT/f'reference-{kind}-{index}-{mode}.png'
            subprocess.run(['grim','-g',f"122,135 {value['width']}x{value['height']}",str(reference)],check=True)
            expected=Image.open(reference).convert('RGB')
            actual=Image.open(ROOT/f'{kind}-{index}-{mode}.png').convert('RGB')
            delta=ImageChops.difference(actual,expected)
            ratio=sum(1 for px in delta.get_flattened_data() if max(px)>24)/(actual.width*actual.height)
            record['changed_fraction']=ratio
            record['mean_error']=max(ImageStat.Stat(delta).mean)
            assert record['mean_error']<1, record
            # Their glyph positions can be fractional too; the mean-error bound
            # compares the whole rendered image without demanding identical AA.
            ipc('otherClose',kind)
        (ROOT/'other-popups.json').write_text(json.dumps(other_results,indent=2))
        print(f'PASS: 18 live transitions and 18 screenshot comparisons; {ROOT}')
    finally:
        (ROOT/'measurements.json').write_text(json.dumps(records,indent=2))
        process.terminate()
        try: process.wait(timeout=5)
        except subprocess.TimeoutExpired: process.kill(); process.wait()
