#!/usr/bin/env python3
"""Synthetic clipboard on a private Wayland server; never log payloads.

Sensitive sentinels exist only in memory and must not reach the test DB.
Only aggregate counts and clipboard state labels are retained as evidence.
"""
import json
import os
from pathlib import Path
import secrets
import signal
import subprocess
import sys
import time

REPO=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(REPO/'tests/session_v2/fixtures'))
from headless import Lab
ART=Path(os.environ['STEP15A_ARTIFACTS']);ART.mkdir(mode=0o700,parents=True,exist_ok=True)
with Lab() as lab:
    counter=lab.directory/'counts'
    spy=lab.directory/'spy.py'
    spy.write_text('import os,sys\nsys.stdin.buffer.read()\nwith open(os.environ["TEST_COUNTS"],"a") as f:f.write(sys.argv[1]+" "+os.environ.get("CLIPBOARD_STATE","")+"\\n")\n')
    lab.env['TEST_COUNTS']=str(counter)
    def copy(payload,kind='text/plain',sensitive=False):
        p=subprocess.Popen(['wl-copy','--foreground','--type',kind,*(['--sensitive'] if sensitive else [])],env=lab.env,stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
        lab.children.append(p);p.stdin.write(payload);p.stdin.close();time.sleep(.2)
    def stop(procs):
        for p in procs:
            if p.poll() is None:
                os.killpg(p.pid,signal.SIGTERM);p.wait(timeout=3)
    png=subprocess.run(['magick','-size','2x2','xc:blue','png:-'],capture_output=True,env=lab.env,check=True).stdout
    phases=[]
    for mode in ['legacy','disjoint']:
        before=len(counter.read_text().splitlines()) if counter.exists() else 0
        watchers=[lab.start(['wl-paste',*(['--type','text'] if mode=='disjoint' else []),'--watch','python3',str(spy),'general']),lab.start(['wl-paste','--type','image/png','--watch','python3',str(spy),'image'])]
        time.sleep(.2)
        # Ignore the already-owned previous selection replayed to new watchers.
        base=len(counter.read_text().splitlines()) if counter.exists() else 0
        copy(png,'image/png');time.sleep(.2)
        entries=counter.read_text().splitlines()[base:]
        counts={name:sum(e.startswith(name+' ') for e in entries) for name in ['general','image']}
        phases.append(dict(mode=mode,offer='PNG-only',callbacks=counts))
        assert counts=={'general':0,'image':1},counts
        # A data-control owner can offer both MIME types without focus/input.
        protocol='/usr/share/qt6/wayland/protocols/wlr-data-control/wlr-data-control-unstable-v1.xml'
        header=lab.directory/'data-control.h';code=lab.directory/'data-control.c'
        subprocess.run(['wayland-scanner','client-header',protocol,str(header)],check=True)
        subprocess.run(['wayland-scanner','private-code',protocol,str(code)],check=True)
        provider=lab.directory/'mime-provider'
        subprocess.run(['cc','-std=c17','-Wall','-Wextra','-I',str(lab.directory),str(REPO/'tests/step15a/mime-provider.c'),str(code),'-lwayland-client','-o',str(provider)],check=True)
        base=len(counter.read_text().splitlines())
        owner=lab.start([str(provider)]);time.sleep(.4)
        entries=counter.read_text().splitlines()[base:]
        counts={name:sum(e==name+' data' for e in entries) for name in ['general','image']}
        assert counts=={'general':1,'image':1},counts
        phases.append(dict(mode=mode,offer='text-and-PNG',callbacks=counts))
        stop([owner])
        stop(watchers)
        subprocess.run(['wl-copy','--clear'],env=lab.env,check=True)
    db=lab.directory/'db'
    watchers=[lab.start(['wl-paste','--type','text','--watch','cliphist','-db-path',str(db),'store'])]
    time.sleep(.15)
    def stored_count():
        p=subprocess.run(['cliphist','-db-path',str(db),'list'],env=lab.env,capture_output=True)
        return len(p.stdout.splitlines()) if p.returncode==0 else 0
    copy(b'TEST_ONLY ordinary');time.sleep(.2);assert stored_count()==1
    # Random synthetic sensitive sentinel is never printed or written by tests.
    sensitive=b'TEST_ONLY-'+secrets.token_bytes(32).hex().encode()
    copy(sensitive,sensitive=True);time.sleep(.25);assert stored_count()==1
    stop(watchers)
    watchers=[lab.start(['wl-paste','--type','image/png','--watch','cliphist','-db-path',str(db),'store'])]
    time.sleep(.15)
    copy(png,'image/png');time.sleep(.2);assert stored_count()==2
    copy(png,'image/png',sensitive=True);time.sleep(.2);assert stored_count()==2
    stop(watchers)
    # Also exercise the backend marker directly, independent of Wayland timing.
    absent=lab.directory/'sensitive-only-db'
    subprocess.run(['cliphist','-db-path',str(absent),'store'],input=sensitive,env=dict(lab.env,CLIPBOARD_STATE='sensitive'),check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    assert not absent.exists()
    result=dict(overlap=phases,sensitive_wayland_text_retained=False,sensitive_wayland_png_retained=False,sensitive_direct_db_created=False,
                real_clipboard_access=False,lab=str(lab.directory))
    (ART/'clipboard-metrics.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
