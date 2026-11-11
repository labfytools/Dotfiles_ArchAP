#!/usr/bin/env python3
"""Private Sway only; production Dock/Menu, real Python bridge and input paths."""
import json
import os
import shutil
from pathlib import Path
import subprocess
import sys
import time

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'tests/session_v2/fixtures'))
from headless import Lab
from ipc_proxy import IpcProxy

SOURCE = REPO / 'quickshell/.config/quickshell/labfy-sway'
ARTIFACTS = Path(os.environ.get('LABFY_DOCK_TEST_ARTIFACTS',
                                str(REPO / 'docs/validation/quickshell-dock-tela-polish-v2')))
NINE = ['firefox.desktop', 'kitty.desktop', 'yazi.desktop', 'nvim.desktop',
        'org.darktable.darktable.desktop', 'orca-slicer.desktop', 'org.freecad.FreeCAD.desktop',
        'org.kde.digikam.desktop', 'AppFlowy.desktop']

class DockLab(Lab):
    def __init__(self):
        super().__init__()
        self.config=self.directory/'dock-sway.conf'
        base=(REPO/'tests/session_v2/fixtures/headless.conf').read_text()
        effects=(REPO/'sway/.config/sway/swayfx').read_text().split('layer_effects "labfy-sway-dock"')[1]
        effects='layer_effects "labfy-sway-dock"'+effects
        self.config.write_text(base+'\noutput HEADLESS-1 bg #11111b solid_color\nset $bar_blur enable\n'+effects)
    def start(self, argv):
        if argv[0]==os.environ.get('LABFY_TEST_SWAY','sway'):
            argv=[*argv[:-1],str(self.config)]
        return super().start(argv)

with DockLab() as lab:
    proxy=IpcProxy(lab.directory/'dock-ipc.sock',lab.socket)
    lab.env['SWAYSOCK']=str(lab.directory/'dock-ipc.sock')
    # Capture helper in private HOME, bound only to the private Wayland socket.
    capture_tool=Path(lab.env['HOME'])/'.local/libexec/labfy-wlthumbs'
    capture_tool.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(Path.home()/'.local/libexec/labfy-wlthumbs',capture_tool)
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
 // TEST_ONLY: one pointer move per animation frame avoids measuring IPC
 // process startup instead of continuous production hover. These are Qt
 // animation intervals, not hardware presentation timestamps.
 FrameAnimation {
  id: sweepFrames
  property var intervals: []
  property real origin: 0
  property bool geometryChanged: false
  property bool imageChanged: false
  property var baseline: []
  running: false
  onTriggered: {
   if (currentFrame > 1) intervals.push(frameTime * 1000);
   const cycle = (elapsedTime * 0.7) % 2;
   input.mouseMove(dock.surfaceBody, 51 + 420 * (cycle <= 1 ? cycle : 2 - cycle), 70);
   const tiles=Array.from(dock.contentItemRow.children).filter(t => t.modelData);
   for (let i=0; i<tiles.length; ++i) {
    const t=tiles[i], b=baseline[i];
    if (t.x!==b.x || t.width!==b.width || t.children[1].width!==46 || dock.width!==origin)
     geometryChanged=true;
    if (t.children[1].children[0].status!==b.status) imageChanged=true;
   }
   if (elapsedTime >= 4.5) running=false;
  }
 }
 TestCase { id: input; name: "DockInput"; when: false }
 IpcHandler {
  target: "dockTest"
  function state(): string {
   return JSON.stringify({ready:A.FavoritesService.ready, ids:A.FavoritesService.ids,
    error:A.FavoritesService.error, phase:dock.phase, revealed:dock.revealed,
    separators:A.FavoritesService.separators,
    dividerIds:Array.from(dock.contentItemRow.children).filter(t=>t.modelData && t.modelData.kind).map(t=>t.modelData.id),
    entries:dock.entries, theme:A.FavoritesService.iconTheme,
    menu:menu.active ? menu.item.favoriteIds : null,
    searchFocused:menu.active && menu.item.searchFocused,
    navFocused:menu.active && menu.item.navigationFocused,
    gridFocused:menu.active && menu.item.gridFocused,
    screenWidth:dock.screen.width,
    bodyY:dock.surfaceBody.y, width:dock.width, pointerX:dock.pointerX,
    bodyX:dock.surfaceBody.x, bodyWidth:dock.surfaceBody.width,
    sensorWidth:dock.edgeArea.width,
    bodyMaskWidth:dock.bodyMaskRegion.width,
    dismissMaskWidth:dock.dismissMaskRegion.width,
    contextMaskWidth:dock.contextMaskRegion.width,
    previewMaskWidth:dock.previewMaskRegion.width,
    previewVisible:dock.previewVisible,
    pendingPreviewId:dock.pendingPreviewId,
    previewArmRunning:dock.previewArmRunning,
    previewGeneration:dock.previewGeneration,
    previewWindowIds:dock.previewEntry ? dock.previewEntry.windows.map(w=>w.id) : [],
    previewCardCount:Array.from(dock.previewCardsRow.children).filter(c=>c.windowData).length,
    previewImageCount:Object.keys(dock.previewImages).length,
    hoveredTiles:Array.from(dock.contentItemRow.children)
      .filter(t=>t.modelData && t.children[3] && t.children[3].containsMouse)
      .map(t=>t.modelData.id),
    dockPressed:dock.pressed,
    dotCounts:Array.from(dock.contentItemRow.children)
      .filter(t=>t.modelData && !t.modelData.kind)
      .map(t=>({id:t.modelData.id,dots:t.dotCount})),

    tileWidth:dock.contentItemRow.children[0] ? dock.contentItemRow.children[0].width : 0,
    tiles:Array.from(dock.contentItemRow.children).filter(t => t.modelData).map(t => ({
      x:t.x, width:t.width, growth:t.growth, scale:t.children[1].scale,
      visualLeft:t.children[1].mapToItem(dock.contentItemRow.parent.parent,0,0).x,
      visualRight:t.children[1].mapToItem(dock.contentItemRow.parent.parent,46,0).x,
      iconWidth:t.children[1].width, imageStatus:t.children[1].children[0].status})),
    context:!!dock.contextEntry,
    contextAlpha:dock.contextCard.color.a,
    dismissVisible:dock.contextDismissArea.visible});
  }
  function startFrames(): void {
   sweepFrames.intervals=[]; sweepFrames.origin=dock.width;
   sweepFrames.baseline=Array.from(dock.contentItemRow.children).filter(t => t.modelData)
    .map(t => ({x:t.x,width:t.width,status:t.children[1].children[0].status}));
   sweepFrames.start();
  }
  function frames(): string {
   return JSON.stringify({running:sweepFrames.running, intervals:sweepFrames.intervals,
    geometryChanged:sweepFrames.geometryChanged,imageChanged:sweepFrames.imageChanged});
  }
  function edge(): void { input.mouseMove(dock.edgeArea, dock.edgeArea.width/2, 2); }
  function edgeLeft(): void { input.mouseMove(dock.edgeArea, 2, 2); }
  function edgeRight(): void { input.mouseMove(dock.edgeArea, dock.edgeArea.width-3, 2); }
  function body(): void { input.mouseMove(dock.surfaceBody, 35, 70); }
  function hoverPinned(id:string): void {
   const tile=Array.from(dock.contentItemRow.children).find(t=>t.modelData && t.modelData.id===id);
   if(!tile) throw new Error('No tile '+id);
   input.mouseMove(tile.children[3],tile.width/2,65);
  }
  function hoverPreview(): void { input.mouseMove(dock.previewPopupItem,25,30); }
  function clickPreview(index:int): void {
   const cards=Array.from(dock.previewCardsRow.children).filter(c=>c.windowData);
   if(index<0 || index>=cards.length) throw new Error('No preview card');
   input.mouseClick(cards[index],cards[index].width/2,cards[index].height/2);
  }
  function sweep(x:real): void { input.mouseMove(dock.surfaceBody, x, 70); }
  function scrollEnd(): void {
   const v=dock.contentItemRow.parent.parent; v.contentX=Math.max(0,v.contentWidth-v.width);
  }
  function scrollStart(): void { dock.contentItemRow.parent.parent.contentX=0; }
  function leave(): void { input.mouseMove(dock.contentItem, 1, 1); }
  function menuToggle(id:string): void { if (!menu.active) menu.active=true; menu.item.toggleFavorite(id); }
  function dockToggle(id:string): void { A.FavoritesService.toggle(id); }
  function addSeparatorAt(position:int): void { A.FavoritesService.addSeparator(position); }
  function moveSeparatorTo(id:string,position:int): void { A.FavoritesService.moveSeparator(id,position); }
  function removeSeparator(id:string): void { A.FavoritesService.removeSeparator(id); }
  function openSeparatorMenu(): void {
   const tile=Array.from(dock.contentItemRow.children).find(t=>t.modelData && t.modelData.kind==="separator");
   if (!tile) throw new Error("missing separator tile");
   input.mouseClick(tile,tile.width/2,65,Qt.RightButton);
  }
  function removeSeparatorFromMenu(): void {
   const action=input.findChild(dock.contextCard,"dock-remove-separator");
   input.mouseClick(action,action.width/2,action.height/2);
  }
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
  function hoverContext(): void { input.mouseMove(dock.contextCard,15,15); }
  function clickAside(): void {
   const area=dock.contextDismissArea;
   input.mouseClick(area,5,Math.min(95,area.height-8));
  }
  function dragFirstAfterSecond(): void {
   const first=dock.contentItemRow.children[0];
   input.mousePress(first,27,65,Qt.LeftButton);
   input.mouseMove(first,125,65,100);
   input.mouseRelease(first,125,65,Qt.LeftButton);
  }
  function activateFirst(): void { input.mouseClick(dock.contentItemRow.children[0],27,65); }
  function context(): void { dock.openContext(dock.entries[0],dock.surfaceBody.width/2); }
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
    # Regression: hidden popup areas must NOT subtract holes from the
    # four-pixel sensor (especially at the centered dock position).
    assert initial['sensorWidth']==initial['screenWidth'], initial
    assert initial['previewMaskWidth']==0 and not initial['previewVisible'],initial
    assert all(initial[key]==0 for key in
               ('bodyMaskWidth', 'dismissMaskWidth', 'contextMaskWidth')), initial
    ARTIFACTS.mkdir(parents=True,exist_ok=True)
    def capture(name):
        subprocess.run(['grim',str(ARTIFACTS / (name+'.png'))],env=lab.env,check=True)
    capture('closed')
    # Separator mutations must be durable and visible to the same live model.
    call('edge'); wait(lambda s:s['revealed'])
    call('addSeparatorAt',2)
    state=wait(lambda s:len(s['separators'])==1 and len(s['dividerIds'])==1)
    separator_id=state['separators'][0]['id']
    assert state['separators'][0]['position']==2,state
    assert state['dividerIds']==[separator_id],state
    separator_file=Path(lab.env['XDG_STATE_HOME'])/'labfy-sway/dock-separators.json'
    assert json.loads(separator_file.read_text())['separators'][0]['id']==separator_id
    call('moveSeparatorTo',separator_id,3)
    wait(lambda s:s['separators'][0]['position']==3)
    call('openSeparatorMenu')
    wait(lambda s:s['context'] and s['phase']=='held')
    call('removeSeparatorFromMenu')
    wait(lambda s:not s['separators'] and not s['dividerIds'] and not s['context'])
    assert json.loads(separator_file.read_text())['separators']==[]
    call('leave'); wait(lambda s:s['phase']=='hidden')
    # Translucent menu; hover keeps it open, clicking beside closes at once;
    # moving away allows a short grace without a visible close button.
    call('edge'); wait(lambda s:s['revealed'])
    call('rightClick')
    opened=wait(lambda s:s['context'])
    assert opened['dismissVisible'],opened
    assert opened['dismissMaskWidth'] > 0 and opened['contextMaskWidth'] > 0, opened
    assert abs(opened['contextAlpha'] - .85) < .01,opened
    call('hoverContext'); time.sleep(.72)
    assert call('state')['context'],call('state')
    call('clickAside')
    after_close=wait(lambda s:not s['context'])
    assert after_close['dismissMaskWidth']==0 and after_close['contextMaskWidth']==0, after_close
    call('edge'); wait(lambda s:s['revealed'])
    call('rightClick'); wait(lambda s:s['context'])
    call('leave'); wait(lambda s:not s['context'],2)
    hidden_after_popup=wait(lambda s:s['phase']=='hidden')
    assert all(hidden_after_popup[key]==0 for key in
               ('bodyMaskWidth', 'dismissMaskWidth', 'contextMaskWidth')), hidden_after_popup
    # A fresh center-edge hover must work after dismissing a popup.
    call('edge')
    center=wait(lambda s:s['revealed'])
    assert center['sensorWidth']==center['screenWidth'], center
    call('leave'); wait(lambda s:s['phase']=='hidden')
    # Every horizontal position of the four-pixel strip must arm the same
    # centered dock, including both physical screen corners.
    assert initial['width']==initial['screenWidth'], initial
    assert initial['sensorWidth']==initial['screenWidth'], initial
    assert initial['bodyWidth']<initial['width'], initial
    assert abs(initial['bodyX']*2 + initial['bodyWidth']-initial['width'])<1.1, initial
    for corner in ('edgeLeft', 'edgeRight'):
        call(corner)
        revealed=wait(lambda s:s['revealed'])
        assert revealed['sensorWidth']==revealed['screenWidth'], revealed
        assert abs(revealed['bodyX']*2+revealed['bodyWidth']-revealed['width'])<1.1, revealed
        call('leave'); wait(lambda s:s['phase']=='hidden')
    call('edge'); wait(lambda s:s['revealed']); time.sleep(.35)
    capture('open')
    resting=call('state')
    call('body'); time.sleep(.3); zoom=call('state'); capture('zoom')
    lab.command('output HEADLESS-1 bg #aab4c8 solid_color')
    time.sleep(.2); capture('zoom-light')
    lab.command('output HEADLESS-1 bg #11111b solid_color')
    assert zoom['tileWidth']==54 and zoom['tiles'][0]['scale']>1, zoom
    assert zoom['tiles'][0]['visualLeft']>=0,zoom
    # Exercise production hover across slot boundaries. Layout and image
    # readiness must remain stable while visual transforms change.
    samples=[]
    for x in range(45, 480, 6):
        call('sweep',x)
        state=call('state')
        assert state['phase']=='shown',state
        assert state['width']==resting['width'],state
        assert [(t['x'],t['width'],t['iconWidth']) for t in state['tiles']]==[(t['x'],t['width'],t['iconWidth']) for t in resting['tiles']],state
        assert sum(t['growth']>0 for t in state['tiles'])<=3,state
        assert [t['imageStatus'] for t in state['tiles']]==[t['imageStatus'] for t in resting['tiles']],state
        samples.append({'pointerX':state['pointerX'],'scales':[t['scale'] for t in state['tiles']]})
    call('startFrames')
    time.sleep(4.8)
    frames=call('frames')
    assert not frames['running'] and len(frames['intervals'])>30,frames
    assert not frames['geometryChanged'] and not frames['imageChanged'],frames
    intervals=sorted(frames['intervals'])
    timing={'frames':len(intervals),'meanMs':sum(intervals)/len(intervals),
            'p95Ms':intervals[int((len(intervals)-1)*.95)],'maxMs':max(intervals)}
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
    # Three real test windows must show three dots and three selectable cards.
    extra1=lab.kitty('kitty')
    extra2=lab.kitty('kitty')
    grouped=wait(lambda s:any(e['id']=='kitty.desktop' and len(e['windows'])==3 for e in s['entries']))
    dots=next(t for t in grouped['dotCounts'] if t['id']=='kitty.desktop')
    assert dots['dots']==3,grouped
    focus_before=focused()
    call('edge'); wait(lambda s:s['revealed'])
    call('hoverPinned','kitty.desktop')
    peek=wait(lambda s:s['previewVisible'] and s['previewCardCount']==3,12)
    assert peek['previewMaskWidth']>0 and len(peek['previewWindowIds'])==3,peek
    assert focused()==focus_before,'Hover changed focus'
    call('hoverPreview'); time.sleep(.8)
    active_preview=call('state')
    assert active_preview['previewVisible'],'Preview must stay open on hover'
    captured=wait(lambda s:s['previewImageCount']>=1,5)
    assert captured['previewImageCount'] <= 3,captured
    print('PRIVATE_CAPTURED_PREVIEWS=',captured['previewImageCount'])
    target=int(peek['previewWindowIds'][0])
    call('clickPreview',0)
    wait(lambda s:not s['previewVisible'])
    for _ in range(20):
        if focused()==target:break
        time.sleep(.1)
    assert focused()==target,(focused(),target)
    call('leave'); wait(lambda s:s['phase']=='hidden')
    cache=Path(lab.env['XDG_RUNTIME_DIR'])/'labfy-dock-window-thumbnails'
    for _ in range(30):
        if not cache.exists() or not list(cache.iterdir()):break
        time.sleep(.15)
    assert not cache.exists() or not list(cache.iterdir()),cache
    # Layer-shell surfaces cannot enter the Session V2 toplevel inventory.
    assert not any('labfy-sway-dock' in str(n.get('app_id','')) for n in lab.windows())
    lab.command('output HEADLESS-1 mode 800x600')
    resized=wait(lambda s:s['screenWidth']==800)
    assert resized['width']==800 and resized['bodyWidth']<=776,resized
    # Magnified end icons keep their visual margin at both scroll limits.
    lab.command('output HEADLESS-1 mode 400x600')
    wait(lambda s:s['screenWidth']==400)
    call('edge'); wait(lambda s:s['revealed']); time.sleep(.3)
    call('scrollEnd'); call('sweep',325); time.sleep(.15)
    end=call('state')
    assert end['tiles'][-1]['scale']>1 and end['tiles'][-1]['visualRight']<=end['bodyWidth']-24,end
    call('scrollStart'); call('sweep',51); time.sleep(.15)
    start=call('state')
    assert start['tiles'][0]['scale']>1 and start['tiles'][0]['visualLeft']>=0,start
    lab.command('output HEADLESS-1 mode 1280x720')
    wait(lambda s:s['screenWidth']==1280)
    # Existing empty state must stay empty, including a bridge restart.
    for identifier in list(call('state')['ids']): call('dockToggle',identifier)
    wait(lambda s:not s['ids'])
    process.terminate(); process.wait(timeout=5)
    process=lab.start(['quickshell','-p',str(qml)])
    time.sleep(1)
    assert wait(lambda s:s['ready'])['ids']==[]
    (ARTIFACTS/'result.json').write_text(json.dumps(dict(status='PASS',initial=initial,hoverSamples=samples,animationTiming=timing,frameSweep=frames,
        reordered=reordered['ids'],checks=['shared favorites','menu and dock mutations','durable reorder',
        'empty restart','autohide','full-width left/right edge activation','centered visual dock',
        'context hold','kitty multi-window','floating scratchpad explicit focus',
        'window close','no hover focus','real pointer drag','fixed layout transform hover', 'stable SVG readiness', 'lateral sweep 73 samples','IPC reconnect','Firefox private profile','desktop install/remove monitoring','external writer','keyboard menu navigation','resolution change','SwayFX dock blur disabled']),indent=2)+'\n')
    proxy.close()
    print('Dock headless: PASS',lab.directory)
