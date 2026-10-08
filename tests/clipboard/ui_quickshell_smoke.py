import json
import os
from pathlib import Path
import subprocess
import tempfile
import time

# Exécuter dans une session Wayland ; base et wl-copy restent privés au test.
REPO = Path(__file__).resolve().parents[2]

with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    db = root / "db"
    output = root / "copied"
    mime = root / "mime"
    fake = root / "wl-copy"
    png = subprocess.run(["magick", "-size", "2x2", "xc:blue", "png:-"],
                         capture_output=True, check=True).stdout
    for index in range(14):
        subprocess.run(["cliphist", "-db-path", str(db), "store"],
                       input=("fixture-%02d" % index).encode(), check=True)
    fake.write_text("#!/usr/bin/env python3\nimport os,sys,pathlib\n"
                    "pathlib.Path(os.environ['TEST_OUT']).write_bytes(sys.stdin.buffer.read())\n"
                    "pathlib.Path(os.environ['TEST_MIME']).write_text(sys.argv[2])\n")
    fake.chmod(0o700)
    qml = root / "shell.qml"
    qml.write_text('''import QtQuick
import QtTest
import Quickshell
import Quickshell.Io
import "file:/home/fy59/.dotfiles/quickshell/.config/quickshell/labfy-sway/status" as S
import "file:/home/fy59/.dotfiles/quickshell/.config/quickshell/labfy-sway/clipboard" as C
ShellRoot {
 id: root
 PanelWindow {
  id: bar
  screen: Quickshell.screens[0]
  anchors { top: true; right: true }
  implicitWidth: 100
  implicitHeight: 34
  S.ClipboardIndicator { id: icon; open: loader.active; anchors.centerIn: parent;
   onToggled: { if (loader.active) loader.item.dismiss(true); else loader.active = true; } }
 }
 LazyLoader { id: loader; active: false; C.ClipboardPanel { barWindow: bar; onCleanupFinished: loader.active = false } }
 TestCase { id: tester; name: "Fixture"; when: false }
 IpcHandler {
  target: "clipboardMouseFixture"
  function state(): string {
   const p = loader.item;
   return JSON.stringify({loaded: loader.active, visible: !!p && p.visible, focused: !!p && p.searchFocused,
      results: p ? p.results.length : 0, images: p ? p.results.filter(x => x.image).length : 0,
      thumbnail: p ? p.thumbnail : "", operation: p ? p.operation : "",
      message: p ? p.message : "", selected: p ? p.selected : -1,
      confirming: !!p && p.confirming, listY: p ? p.resultList.contentY : 0,
      contentHeight: p ? p.resultList.contentHeight : 0, listHeight: p ? p.resultList.height : 0,
      bounds: p ? {x:p.cardX,y:p.cardY,w:p.cardWidth,h:p.cardHeight} : null});
  }
  function clickIcon(): bool { tester.mouseClick(icon, 13, 13); return true; }
  function clickItem(index: int): bool {
   const item = loader.item.resultList.itemAtIndex(index);
   if (!item) return false;
   tester.mouseClick(item, 30, item.height / 2);
   return true;
  }
  function clickClear(): bool {
   const item = loader.item.clearActionItem;
   tester.mouseClick(item, item.width / 2, item.height / 2);
   return true;
  }
  function clickConfirm(): bool {
   const item = loader.item.confirmActionItem;
   tester.mouseClick(item, item.width / 2, item.height / 2);
   return true;
  }
  function clickCancel(): bool {
   const item = loader.item.cancelActionItem;
   tester.mouseClick(item, item.width / 2, item.height / 2);
   return true;
  }
  function clickRemove(): bool {
   const item = loader.item.removeActionItem;
   tester.mouseClick(item, item.width / 2, item.height / 2);
   return true;
  }
  function wheel(): bool {
   const item = loader.item.resultList;
   tester.mouseWheel(item, item.width / 2, item.height / 2, 0, -120);
   return true;
  }
  function clickOutside(): bool {
   tester.mouseClick(loader.item.interactionRoot, 2, 2);
   return true;
  }
  function refresh(): bool { loader.item.refresh(); return true; }
 }
}
'''.replace("file:/home/fy59/.dotfiles", REPO.as_uri()))
    environment = dict(os.environ, LABFY_CLIPHIST_TEST_DB=str(db),
                       LABFY_CLIPHIST_TEST_CACHE_DIR=str(root),
                       LABFY_CLIPHIST_TEST_WL_COPY=str(fake), TEST_OUT=str(output),
                       TEST_MIME=str(mime))
    # CONTRACT: le chemin absolu injecté dans QML doit viser le collecteur factice,
    # car un vrai wl-copy dans la session écraserait les données personnelles.
    assert Path(environment["LABFY_CLIPHIST_TEST_WL_COPY"]).resolve() == fake.resolve()
    assert fake.is_file() and os.access(fake, os.X_OK)
    process = subprocess.Popen(["quickshell", "-p", str(qml)], env=environment,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

    def call(name, *args):
        result = subprocess.run(["quickshell", "ipc", "-p", str(qml), "call",
                                 "clipboardMouseFixture", name, *map(str, args)],
                                capture_output=True, text=True)
        if result.returncode:
            raise AssertionError((name, result.stdout[:200], result.stderr[:200]))
        return json.loads(result.stdout)

    def wait_for(predicate, seconds=3):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            value = call("state")
            if predicate(value):
                return value
            time.sleep(0.04)
        raise AssertionError(("state timeout", call("state")))

    try:
        time.sleep(0.3)
        assert call("clickIcon")
        opened = wait_for(lambda state: state["loaded"] and state["focused"] and state["results"] == 14)
        assert opened["bounds"]["w"] == 540 and opened["bounds"]["y"] == 46
        if os.environ.get("CLIPBOARD_UI_CAPTURE"):
            box = opened["bounds"]
            # Le recadrage intérieur ne montre que la carte alimentée par les données factices.
            geometry = f"{box['x'] + 2},{box['y'] + 2} {box['w'] - 4}x{box['h'] - 4}"
            subprocess.run(["grim", "-g", geometry, os.environ["CLIPBOARD_UI_CAPTURE"]], check=True)
        assert call("clickIcon")
        wait_for(lambda state: not state["loaded"])
        assert call("clickIcon")
        wait_for(lambda state: state["results"] == 14)
        assert call("wheel")
        scrolled = wait_for(lambda state: state["listY"] > 0)
        assert scrolled["contentHeight"] > scrolled["listHeight"]
        time.sleep(0.4)
        assert call("clickItem", 5)
        wait_for(lambda state: not state["loaded"])
        assert output.read_bytes() == b"fixture-08"
        assert call("clickIcon")
        wait_for(lambda state: state["results"] == 14)
        assert call("clickRemove")
        wait_for(lambda state: state["results"] == 13)
        current = subprocess.run(["cliphist", "-db-path", str(db), "list"],
                                 capture_output=True, check=True).stdout.splitlines()
        assert len(current) == 13
        assert call("clickClear")
        assert call("state")["confirming"]
        assert call("clickCancel")
        assert not call("state")["confirming"]
        assert len(subprocess.run(["cliphist", "-db-path", str(db), "list"],
                                  capture_output=True, check=True).stdout.splitlines()) == 13
        assert call("clickClear")
        subprocess.run(["wtype", "-k", "Escape"], check=True)
        wait_for(lambda state: not state["confirming"] and state["visible"])
        assert call("clickClear")
        assert call("clickIcon")
        wait_for(lambda state: not state["loaded"])
        assert call("clickIcon")
        wait_for(lambda state: state["results"] == 13)
        assert call("clickClear")
        assert call("clickConfirm")
        wait_for(lambda state: state["results"] == 0)
        print("icon_click_toggle=true geometry=true focus=true mouse_selection=true click_restore=true"
              " scroll=true delete=true purge_confirm=true purge_cancel=true escape_cancel=true"
              " purge_forced_close=true empty=true")
        subprocess.run(["cliphist", "-db-path", str(db), "store"], input=png, check=True)
        assert call("refresh")
        state = wait_for(lambda state: state["results"] == 1 and state["images"] == 1
                         and state["thumbnail"].startswith("file:"))
        assert state["thumbnail"]
        assert call("clickItem", 0)
        wait_for(lambda state: not state["loaded"])
        assert output.read_bytes() == png and mime.read_text() == "image/png"
        print("image_mouse_restore=true image_mime=true")
        assert call("clickIcon")
        wait_for(lambda state: state["results"] == 1)
        subprocess.run(["ydotool", "key", "28:1", "28:0"], check=True)
        wait_for(lambda state: not state["loaded"])
        assert output.read_bytes() == png and mime.read_text() == "image/png"
        print("image_visible=true thumbnail=true image_keyboard_restore=true")
        assert call("clickIcon")
        wait_for(lambda state: state["results"] == 1)
        assert call("clickOutside")
        wait_for(lambda state: not state["loaded"])
        assert not list(root.glob("labfy-cliphist-panel-*/*.png"))
        print("outside_click_close=true")
    finally:
        process.terminate()
        try:
            log = process.communicate(timeout=4)[0]
        except subprocess.TimeoutExpired:
            process.kill()
            log = process.communicate()[0]
        errors = [line for line in log.splitlines() if "ERROR" in line]
        if errors:
            raise AssertionError("QuickShell reported errors: " + str(errors[-2:]))
