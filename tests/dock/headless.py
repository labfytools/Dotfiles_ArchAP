#!/usr/bin/env python3
"""Private Sway only; production Dock/Menu, real Python bridge and input paths."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'tests/session_v2/fixtures'))
from headless import Lab
from ipc_proxy import IpcProxy

SOURCE = REPO / 'quickshell/.config/quickshell/labfy-sway'
ARTIFACTS = REPO / 'docs/validation/quickshell-dock-tela'
NINE = ['firefox.desktop', 'kitty.desktop', 'yazi.desktop', 'nvim.desktop',
        'org.darktable.darktable.desktop', 'orca-slicer.desktop', 'org.freecad.FreeCAD.desktop',
        'org.kde.digikam.desktop', 'AppFlowy.desktop']

class DockLab(Lab):
    def __init__(self):
        super().__init__()
        self.config=self.directory/'dock-sway.conf'
        base=(REPO/'tests/session_v2/fixtures/headless.conf').read_text()
        effects=(REPO/'sway/.config/sway/swayfx').read_text().split('# CONTRACT: only the dock')[1]
        effects=effects[effects.index('layer_effects'):]
        self.config.write_text(base+'\noutput HEADLESS-1 bg #11111b solid_color\nset $bar_blur enable\n'+effects)
    def start(self, argv):
        if argv[0]==os.environ.get('LABFY_TEST_SWAY','sway'):
            argv=[*argv[:-1],str(self.config)]
        return super().start(argv)

with DockLab() as lab:
    proxy=IpcProxy(lab.directory/'dock-ipc.sock',lab.socket)
    lab.env['SWAYSOCK']=str(lab.directory/'dock-ipc.sock')
    path = Path(lab.env['XDG_STATE_HOME']) / 'labfy-sway/applications-favorites.json'
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(dict(version=1, ids=NINE)))
    qml = lab.directory / 'fixture.qml'
    qml.write_text('''//@ pragma UseQApplication
import QtQuick
import QtTest
import Quickshell
import Quickshell.Io
import "SOURCE/applications" as A
import "SOURCE/dock" as D
ShellRoot {
 D.Dock { id: dock; modelData: Quickshell.screens[0] }
 PanelWindow { id: bar; implicitWidth: 100; implicitHeight: 30; anchors.top: true; color: "transparent" }
 LazyLoader { id: menu; active: false; A.ApplicationsMenu { barWindow: bar } }
 TestCase { id: input; name: "DockInput"; when: false }
 IpcHandler {
  target: "dockTest"
  function state(): string {
   return JSON.stringify({ready:A.FavoritesService.ready, ids:A.FavoritesService.ids,
    error:A.FavoritesService.error, phase:dock.phase, revealed:dock.revealed,
    entries:dock.entries, theme:A.FavoritesService.iconTheme,
    menu:menu.active ? menu.item.favoriteIds : null,
    searchFocused:menu.active && menu.item.searchFocused,
    navFocused:menu.active && menu.item.navigationFocused,
    gridFocused:menu.active && menu.item.gridFocused,
    screenWidth:dock.screen.width,
    bodyY:dock.surfaceBody.y, width:dock.width, pointerX:dock.pointerX,

    tileWidth:dock.contentItemRow.children[0] ? dock.contentItemRow.children[0].width : 0,
    context:!!dock.contextEntry});
  }
  function edge(): void { input.mouseMove(dock.edgeArea, dock.edgeArea.width/2, 2); }
  function body(): void { input.mouseMove(dock.surfaceBody, 35, 70); }
  function leave(): void { input.mouseMove(dock.contentItem, 1, 1); }
  function menuToggle(id:string): void { if (!menu.active) menu.active=true; menu.item.toggleFavorite(id); }
  function dockToggle(id:string): void { A.FavoritesService.toggle(id); }
  function move(id:string, before:string): void { A.FavoritesService.move(id,before); }
  function closeMenu(): void { menu.active=false; }
  function tab(): void { input.keyClick(Qt.Key_Tab); }
  function clickPin(): void {
   const action=input.findChild(dock.contextCard,"dock-pin-action");
   input.mouseClick(action,action.width/2,action.height/2);
  }
  function rightClick(): void {
   input.mouseClick(dock.contentItemRow.children[0],27,65,Qt.RightButton);
  }
  function dragFirstAfterSecond(): void {
   const first=dock.contentItemRow.children[0];
   input.mousePress(first,27,65,Qt.LeftButton);
   input.mouseMove(first,125,65,100);
   input.mouseRelease(first,125,65,Qt.LeftButton);
  }
  function activateFirst(): void { input.mouseClick(dock.contentItemRow.children[0],27,65); }
  function context(): void { dock.openContext(dock.entries[0],dock.width/2); }
  function closeContext(): void { dock.closeContext(); }
  function suppress(value:bool): void { dock.suppressed=value; }
  function focus(id:string): void { A.FavoritesService.focusWindow(id); }
 }
}
'''.replace('SOURCE', SOURCE.as_uri()))
    lab.env['QT_QPA_PLATFORM'] = 'wayland'
    process = lab.start(['quickshell', '-p', str(qml)])
    def call(name, *args):
        r = subprocess.run(['quickshell','ipc','-p',str(qml),'call','dockTest',name,*map(str,args)],
                           env=lab.env, text=True, capture_output=True, timeout=8)
        if r.returncode:
            logs = '\n'.join(p.read_text()[-9000:] for p in lab.directory.glob('child-*.log'))
            raise AssertionError((name,r.stdout,r.stderr,logs))
        return json.loads(r.stdout) if r.stdout.strip() else None
    def wait(predicate, seconds=8):
        end = time.monotonic()+seconds
        while time.monotonic()<end:
            state=call('state')
            if predicate(state): return state
            time.sleep(.08)
        raise AssertionError(call('state'))
    time.sleep(1.2)
    initial=wait(lambda s:s['ready'])
    assert initial['ids']==NINE and initial['phase']=='hidden', initial
    ARTIFACTS.mkdir(parents=True,exist_ok=True)
    def capture(name):
        subprocess.run(['grim',str(ARTIFACTS / (name+'.png'))],env=lab.env,check=True)
    capture('closed')
    call('edge'); wait(lambda s:s['revealed']); time.sleep(.35)
    capture('open')
    call('body'); time.sleep(.3); zoom=call('state'); capture('zoom')
    assert zoom['tileWidth']>54, zoom
    call('leave'); wait(lambda s:s['phase']=='hidden')
    call('edge'); wait(lambda s:s['revealed']); time.sleep(.3)
    call('rightClick'); wait(lambda s:s['phase']=='held'); time.sleep(.7)
    assert call('state')['context']
    call('clickPin'); wait(lambda s:'firefox.desktop' not in s['ids'])
    call('dockToggle','firefox.desktop'); wait(lambda s:'firefox.desktop' in s['ids'])
    call('move','firefox.desktop','kitty.desktop'); wait(lambda s:s['ids']==NINE)
    call('leave'); wait(lambda s:s['phase']=='hidden')
    # Refused move leaves both interfaces at the same durable list.
    call('move','kitty.desktop','removed.desktop')
    wait(lambda s:bool(s['error']))
    assert call('state')['ids']==NINE
    call('menuToggle','fixture.desktop'); wait(lambda s:'fixture.desktop' in s['ids'] and s['menu']==s['ids'])
    # Gio catalog monitoring replaces the placeholder without dropping its ID.
    desktop=Path(lab.env['HOME'])/'.local/share/applications/fixture.desktop'
    desktop.parent.mkdir(parents=True,exist_ok=True)
    desktop.write_text('[Desktop Entry]\nType=Application\nName=Installed Fixture\nExec=/usr/bin/true\nIcon=firefox\n')
    wait(lambda s:any(e['id']=='fixture.desktop' and not e.get('missing') for e in s['entries']))
    desktop.unlink()
    wait(lambda s:any(e['id']=='fixture.desktop' and e.get('missing') for e in s['entries']))
    # Keep the virtual keyboard alive: the headless seat has no physical
    # keyboard, so destroying wtype would remove keyboard capabilities and
    # deactivate the QML focus window before we could sample its focus item.
    keyboard=lab.start(['wtype','-s','300','-k','Tab','-s','1500','-k','Tab',
                        '-s','1500','-k','Tab','-s','1500'])
    wait(lambda s:s['navFocused'])
    wait(lambda s:s['gridFocused'])
    wait(lambda s:s['searchFocused'])
    keyboard.wait(timeout=8)
    # An independent legacy CLI writer is observed by menu and dock live.
    subprocess.run(['python','-B',str(SOURCE/'applications/backend.py'),'favorites','add','external.desktop'],
                   env=lab.env,check=True,capture_output=True)
    wait(lambda s:'external.desktop' in s['ids'] and s['menu']==s['ids'])
    call('dockToggle','external.desktop'); wait(lambda s:'external.desktop' not in s['ids'])
    call('dockToggle','fixture.desktop'); wait(lambda s:'fixture.desktop' not in s['ids'] and s['menu']==s['ids'])
    call('move','kitty.desktop','firefox.desktop'); reordered=wait(lambda s:s['ids'][0]=='kitty.desktop')
    assert json.loads(path.read_text())['ids']==reordered['ids']
    call('closeMenu')
    call('edge'); wait(lambda s:s['revealed']); time.sleep(.3)
    call('dragFirstAfterSecond')
    dragged=wait(lambda s:s['ids'][0]=='firefox.desktop')
    assert dragged['ids'][1]=='kitty.desktop',dragged
    call('leave'); wait(lambda s:s['phase']=='hidden')
    # No focus changes while the pointer reveals, zooms, hides, or opens menus.
    win=lab.kitty('kitty')
    time.sleep(.5)
    focused=lambda: next(n['id'] for n in lab.windows() if n.get('focused'))
    assert focused()==win
    for action in ('edge','body','context','leave','closeContext'):
        call(action); time.sleep(.25); assert focused()==win, action
    call('suppress','true'); assert call('state')['phase']=='hidden'
    call('suppress','false')
    wait(lambda s:any(e['id']=='kitty.desktop' and len(e['windows'])==1 for e in s['entries']))
    proxy.disconnect()
    time.sleep(2)
    second=lab.kitty('kitty')
    wait(lambda s:any(e['id']=='kitty.desktop' and len(e['windows'])==2 for e in s['entries']))
    lab.command(f'[con_id={win}] floating enable')
    lab.command(f'[con_id={win}] move scratchpad')
    call('focus',str(win)); time.sleep(.3); assert focused()==win
    lab.command(f'[con_id={second}] kill')
    wait(lambda s:any(e['id']=='kitty.desktop' and len(e['windows'])==1 for e in s['entries']))
    # Firefox runs with the private HOME/profile and no inherited session bus.
    profile=lab.directory/'firefox-profile'; profile.mkdir()
    firefox=lab.start(['firefox','--no-remote','--profile',str(profile),'--new-window','about:blank'])
    firefox_state=wait(lambda s:any(e['id']=='firefox.desktop' and e['windows'] for e in s['entries']),20)
    firewin=next(e for e in firefox_state['entries'] if e['id']=='firefox.desktop')['windows'][0]['id']
    call('closeContext'); call('edge'); wait(lambda s:s['revealed']); time.sleep(.3)
    call('activateFirst'); time.sleep(.3)
    assert str(focused())==firewin
    for action in ('edge','body','leave'):
        call(action); time.sleep(.25); assert str(focused())==firewin
    # Layer-shell surfaces cannot enter the Session V2 toplevel inventory.
    assert not any('labfy-sway-dock' in str(n.get('app_id','')) for n in lab.windows())
    lab.command('output HEADLESS-1 mode 800x600')
    resized=wait(lambda s:s['screenWidth']==800)
    assert resized['width']<=776,resized
    lab.command('output HEADLESS-1 mode 1280x720')
    wait(lambda s:s['screenWidth']==1280)
    # Existing empty state must stay empty, including a bridge restart.
    for identifier in list(call('state')['ids']): call('dockToggle',identifier)
    wait(lambda s:not s['ids'])
    process.terminate(); process.wait(timeout=5)
    process=lab.start(['quickshell','-p',str(qml)])
    time.sleep(1)
    assert wait(lambda s:s['ready'])['ids']==[]
    (ARTIFACTS/'result.json').write_text(json.dumps(dict(status='PASS',initial=initial,
        reordered=reordered['ids'],checks=['shared favorites','menu and dock mutations','durable reorder',
        'empty restart','autohide','context hold','kitty multi-window','floating scratchpad explicit focus',
        'window close','no hover focus','real pointer drag','zoom growth','IPC reconnect','Firefox private profile','desktop install/remove monitoring','external writer','keyboard menu navigation','resolution change','SwayFX dock blur rule']),indent=2)+'\n')
    proxy.close()
    print('Dock headless: PASS',lab.directory)
