#!/usr/bin/env python3
"""Owned headless compositor, synthetic windows, aggregate capture metrics only."""
import json
import os
from pathlib import Path
import resource
import subprocess
import sys
import time

REPO=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(REPO/'tests/session_v2/fixtures'))
from headless import Lab
SRC=REPO/'quickshell/.config/quickshell/labfy-sway'
QS=str(Path.home()/'.local/opt/quickshell-qt612-popup/bin/quickshell')
ART=Path(os.environ['STEP15A_ARTIFACTS']);ART.mkdir(mode=0o700,parents=True,exist_ok=True)

def rss(pid):
    for l in Path(f'/proc/{pid}/status').read_text().splitlines():
        if l.startswith('VmRSS:'):return int(l.split()[1])*1024

def cpu(pid):
    v=Path(f'/proc/{pid}/stat').read_text().rsplit(')',1)[1].split()
    return sum(int(v[i]) for i in [11,12,13,14])/os.sysconf('SC_CLK_TCK')

with Lab() as lab:
    lab.env['DBUS_SESSION_BUS_ADDRESS']=os.environ['DBUS_SESSION_BUS_ADDRESS']
    config=Path(lab.env['XDG_CONFIG_HOME'])/'quickshell/labfy-sway';config.mkdir(parents=True)
    for name in ['overview','theme','components']:(config/name).symlink_to(SRC/name,target_is_directory=True)
    # This compositor has never seen personal windows or clipboard data.
    lab.kitty('TEST_ONLY_INCLUDED');lab.kitty('TEST_ONLY_EXCLUDED')
    policy=Path(lab.env['XDG_CONFIG_HOME'])/'labfy-sway/overview-capture.json';policy.parent.mkdir()
    policy.write_text(json.dumps({'enabled':True,'excludeApps':['TEST_ONLY_EXCLUDED']}))
    binary=lab.directory/'bin';binary.mkdir()
    counter=lab.directory/'capture-count'
    wrapper=binary/'grim'
    wrapper.write_text('#!/usr/bin/python3\nimport os,time\nwith open(os.environ["TEST_CAPTURE_COUNT"],"a") as f:f.write(str(time.monotonic())+"\\n")\nos.execv("/usr/bin/grim",["grim",*__import__("sys").argv[1:]])\n')
    wrapper.chmod(0o700);lab.env.update(PATH=str(binary)+':/usr/bin:/bin',TEST_CAPTURE_COUNT=str(counter))
    # Compare one old output-capture operation on the same synthetic desktop.
    # This does not run the old timer or touch any physical output.
    old=lab.directory/'baseline-backend.py'
    old.write_bytes(subprocess.check_output(['git','show','HEAD:quickshell/.config/quickshell/labfy-sway/overview/backend.py'],cwd=REPO))
    usage=resource.getrusage(resource.RUSAGE_CHILDREN);t0=time.monotonic()
    old_result=subprocess.run(['python3','-B',str(old),'capture','--output','HEADLESS-1'],env=lab.env,capture_output=True,text=True,check=True)
    after_usage=resource.getrusage(resource.RUSAGE_CHILDREN)
    baseline_capture=dict(wall_ms=(time.monotonic()-t0)*1000,
        cpu_seconds=after_usage.ru_utime+after_usage.ru_stime-usage.ru_utime-usage.ru_stime,
        captured=json.loads(old_result.stdout)['captured'])
    fixture=config/'fixture.qml'
    fixture.write_text('''//@ pragma UseQApplication
import QtQuick
import Quickshell
import Quickshell.Io
import "overview"
ShellRoot {
 PanelWindow {id:bar;anchors {top:true;left:true;right:true} implicitHeight:34}
 FileView {id:guard;path:Quickshell.env("XDG_RUNTIME_DIR")+"/labfy-lock.capture-guard";watchChanges:true;onFileChanged:reload();printErrors:false}
 readonly property bool locked:guard.text().trim()==="active"
 onLockedChanged: {if(locked){if(view.item)view.item.dismiss();purger.running=true;}}
 Process {id:purger;command:["python3","-B","HELPER","purge"]}
 LazyLoader {id:view;active:false;WorkspaceOverview {barWindow:bar;onOverviewDismissed:view.active=false}}
 IpcHandler {target:"fixture"
  function open():void {view.active=true}
  function close():void {if(view.item)view.item.dismiss()}
  function state():string {return JSON.stringify({loaded:view.active,cards:view.item?view.item.cards:[]})}
  function move(id:int,number:int):void {view.item.moveWindow(id,number)}
 }
}
'''.replace('HELPER',str(SRC/'overview/backend.py')))
    proc=lab.start([QS,'-p',str(fixture),'--no-color'])
    def call(name,*args):
        r=subprocess.run([QS,'ipc','-p',str(fixture),'call','fixture',name,*map(str,args)],env=lab.env,capture_output=True,text=True,timeout=5)
        if r.returncode:raise RuntimeError('Synthetic fixture IPC unavailable')
        return json.loads(r.stdout) if r.stdout.strip() else None
    def until(predicate,seconds=10):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            try:
                value=call('state')
                if predicate(value):return value
            except RuntimeError:pass
            time.sleep(.05)
        raise RuntimeError('Synthetic overview timeout '+str(lab.directory))
    def count():return len(counter.read_text().splitlines()) if counter.exists() else 0
    until(lambda v:not v['loaded'])
    time.sleep(1)
    before=dict(rss=rss(proc.pid),cpu=cpu(proc.pid),captures=count())
    start=time.monotonic();call('open');until(lambda v:len(v['cards'])==10)
    panel_ms=(time.monotonic()-start)*1000
    state=until(lambda v:any(w.get('preview') for c in v['cards'] for w in c['windows']))
    thumb_ms=(time.monotonic()-start)*1000
    for c in state['cards']:
        for w in c['windows']:
            if w['app']=='TEST_ONLY_EXCLUDED':assert w['excluded'] and not w['preview']
    # Measure the real move route without closing the panel; the source is synthetic.
    ident=next(w['id'] for c in state['cards'] for w in c['windows'] if w['app']=='TEST_ONLY_INCLUDED')
    call('move',ident,2)
    until(lambda v:any(c['number']==2 and any(w['id']==ident for w in c['windows']) for c in v['cards']))
    time.sleep(1.3)
    subprocess.run(['/usr/bin/grim','-o','HEADLESS-1',str(ART/'overview.png')],env=lab.env,check=True)
    opened=dict(rss=rss(proc.pid),cpu=cpu(proc.pid),captures=count())
    cache_open=sum(p.stat().st_size for p in (lab.directory/'labfy-workspace-overview').iterdir() if p.is_file())
    call('close');until(lambda v:not v['loaded']);time.sleep(.4)
    closed_count=count()
    # Longer than the removed 15-second timer, with native workspace changes.
    lab.command('workspace number 3');time.sleep(16)
    assert count()==closed_count,('closed capture',count(),closed_count)
    closed=dict(rss=rss(proc.pid),cpu=cpu(proc.pid),captures=count())
    cycles=[]
    for _ in range(3):
        call('open');until(lambda v:len(v['cards'])==10);time.sleep(1.4)
        call('close');until(lambda v:not v['loaded']);time.sleep(.3)
        cycles.append(rss(proc.pid))
    assert max(cycles)-min(cycles)<64*1024*1024,cycles
    # Real per-window capture unavailable => fallback; policy re-read while open.
    disabled_start_count=count()
    policy.write_text(json.dumps({'enabled':False}))
    call('open');state=until(lambda v:len(v['cards'])==10);time.sleep(1.3)
    state=call('state');assert all(not w['preview'] for c in state['cards'] for w in c['windows'])
    assert count()==disabled_start_count
    subprocess.run(['/usr/bin/grim','-o','HEADLESS-1',str(ART/'overview-disabled.png')],env=lab.env,check=True)
    # Lock guard is exclusively in this test's private runtime. No session lock.
    guard=lab.directory/'labfy-lock.capture-guard';guard.write_text('active\n')
    until(lambda v:not v['loaded'])
    time.sleep(.3)
    helper=SRC/'overview/backend.py'
    r=subprocess.run(['python3','-B',str(helper),'state'],env=lab.env,capture_output=True,text=True,check=True)
    assert not json.loads(r.stdout)['captureEnabled']
    files=list((lab.directory/'labfy-workspace-overview').glob('*.jpg'));assert not files
    result=dict(closed_cycle_rss_bytes=cycles,baseline_output_capture=baseline_capture,cache_open_bytes=cache_open,panel_ms=panel_ms,thumbnail_ms=thumb_ms,before=before,opened=opened,closed=closed,
                cache_bytes=sum(p.stat().st_size for p in (lab.directory/'labfy-workspace-overview').iterdir() if p.is_file()),
                closed_observation_seconds=16,closed_new_captures=closed['captures']-closed_count,lab=str(lab.directory))
    (ART/'overview-metrics.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
