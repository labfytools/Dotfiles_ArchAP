"""Private real compositor only; no inherited user socket, no helper suspension.

Retains synthetic trees and screenshots under /tmp. SIGCONT is deliberately not
used by this runner, even during cleanup. No installed configuration is read.
"""
import json
import subprocess
from unittest.mock import patch
from common import *
from lab import Lab as BaseLab, Surfaces, build_helper
from session_v2.snapshot import capture
from session_v2.ipc import Sway, location
from session_v2.executor import Executor
from session_v2.checkpoint import Store
from session_v2.storage import private_dir
from session_v2.recovery import Recovery


class Lab(BaseLab):
    def __exit__(self, *_):
        for proc in reversed(self.children):
            if proc.poll() is None:
                proc.terminate()
                try: proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    proc.kill(); proc.wait(timeout=3)
        for log in self.logs: log.close()


def main():
    with Lab() as lab:
        print(lab.directory, flush=True)
        binary = build(lab.directory)
        sway = Sway(lab.socket)
        commands = []
        raw_command = sway.command
        def recorded(text):
            commands.append(text)
            return raw_command(text)
        sway.command = recorded
        # Production catalog structure, synthetic IDs. No arbitrary argv launches.
        static_kitty = ('/usr/bin/kitty', '--config', 'NONE', '--class', 'TEST_ONLY_kitty',
                        '--title', 'TEST_ONLY', '-o', 'linux_display_server=wayland',
                        '-o', 'confirm_os_window_close=0', '/usr/bin/sleep', '180')
        cat = Catalog((Spec('kitty', 'kitty.desktop', ('TEST_ONLY_kitty',), 'terminal', static_kitty),
                       *(Spec(n, n+'.desktop', ('TEST_ONLY_'+n,), 'managed-autostart', ())
                         for n in ('shown', 'float', 'split'))))

        lab.command('workspace "TEST_ONLY_TARGET"')
        ids = [lab.kitty('TEST_ONLY_'+n) for n in ('kitty','kitty','shown','float','split')]
        def command(i, operation): lab.command(f'[con_id={i}] '+operation)
        for i in ids[:1]+ids[2:4]:
            command(i, 'floating enable')
        command(ids[0], 'move scratchpad')
        command(ids[2], 'move scratchpad')
        command(ids[2], 'scratchpad show')
        # Allow GTK's real configure/ack cycle before the measured snapshot.
        time.sleep(.3)
        for i in ids[:1]+ids[2:4]:
            command(i, 'resize set width 400 px height 240 px')
            command(i, 'move absolute position 30 px 40 px')
        command(ids[1], 'focus')
        time.sleep(.3)
        def evidence(name):
            (lab.directory/(name+'.json')).write_text(json.dumps(sway.tree(),indent=2))
            subprocess.run(['grim','-o','HEADLESS-1',str(lab.directory/(name+'.png'))],env=lab.env,check=True)
        evidence('before')
        data = capture(sway, cat, None)
        store = Store(private_dir(lab.directory/'store'))
        store.save('scratch',data); store.checkpoint(data)
        assert store.load('scratch') == store.last() == data
        (lab.directory/'snapshot.json').write_text(json.dumps(data,indent=2))
        command(ids[2], 'move scratchpad')
        command(ids[3], 'floating disable')
        evidence('disturbed')
        result = Executor(sway,cat,None,private_dir(lab.directory/'runtime'),binary,lab.env).apply(store.last(),True)
        evidence('after')
        (lab.directory/'result.json').write_text(json.dumps(result,indent=2))
        (lab.directory/'commands.json').write_text(json.dumps(commands,indent=2))
        assert not any(c.startswith(f'[con_id={ids[0]}] ') and ('workspace' in c or 'scratchpad show' in c) for c in commands)
        assert result['status'] == 'success'
        assert location(sway.tree(),ids[0])[0] == '__i3_scratch'
        # User-like explicit show/hide after restore: prove real membership.
        command(ids[0], 'scratchpad show'); time.sleep(.2); evidence('user-show')
        command(ids[0], 'move scratchpad'); time.sleep(.2); evidence('user-hide')
        assert location(sway.tree(),ids[0])[0] == '__i3_scratch'

        # A new-session-like placement: membership must be created from normal
        # leaves, with the same pinned processes and trusted static catalog.
        command(ids[0], 'scratchpad show'); command(ids[0], 'floating disable')
        command(ids[2], 'floating disable')
        time.sleep(.3)
        second = Executor(sway,cat,None,private_dir(lab.directory/'runtime-new-membership'),binary,lab.env).apply(data,True)
        assert second['status'] == 'success'
        evidence('new-membership')
        # All hidden, with an explicitly focused empty workspace, remains a
        # restorable snapshot and never persists the internal scratch workspace.
        for i in ids: command(i, 'move scratchpad')
        lab.command('workspace "TEST_ONLY_EMPTY"'); time.sleep(.3)
        all_hidden = capture(sway,cat,None)
        assert all_hidden['focus'] is None and all_hidden['focus_workspace'] == 'TEST_ONLY_EMPTY'
        assert all(s['state']['scratchpad']=='hidden' for s in all_hidden['window_slots'])
        third = Executor(sway,cat,None,private_dir(lab.directory/'runtime-all-hidden'),binary,lab.env).apply(all_hidden,True)
        assert third['status'] == 'success'
        evidence('all-hidden')
        (lab.directory/'all-hidden-snapshot.json').write_text(json.dumps(all_hidden,indent=2))
        # Real prewarm launches through a static test catalog, with fresh PIDs.
        # Track returned children solely for TEST_ONLY cleanup; no launch is
        # derived from snapshot data, titles or the former terminal process.
        from session_v2.applications import launch as real_launch
        old = {n['id'] for n in sway.windows() if n['app_id']=='TEST_ONLY_kitty'}
        for i in old: command(i, 'kill')
        lab.wait_absent(old)
        launched = []
        def track_launch(spec, count, env):
            children = real_launch(spec,count,env)
            lab.children.extend(children);launched.extend(children)
            return children
        with patch('session_v2.executor.launch',side_effect=track_launch):
            engine=Executor(sway,cat,None,private_dir(lab.directory/'runtime-cold-kitty'),binary,lab.env)
            cold=engine.apply(all_hidden,True)
            assert cold['status']=='success' and len(launched)==2
            assert not old.intersection(n['id'] for n in sway.windows())
            assert all(location(sway.tree(),n['id'])[0]=='__i3_scratch' for n in sway.windows() if n['app_id']=='TEST_ONLY_kitty')
            # A further apply reuses the admitted surfaces; no duplicate launch.
            again=engine.apply(all_hidden,True)
            assert again['status']=='success' and len(launched)==2
        evidence('cold-kitty')
        (lab.directory/'cold-result.json').write_text(json.dumps(cold,indent=2))
        print('PASS save/store/restore/show/hide/new-membership/all-hidden/cold-kitty/no-duplicate', flush=True)


if __name__ == '__main__': main()
