#!/usr/bin/env python3
"""Opt-in real key test in a disposable XWayland widget; never read clipboard.

Every fixture key binding returns break, so even a paste chord cannot invoke
clipboard_get or a normal editor action. Text-copy methods are mocked in the
production injector. Only keysyms/modifier masks are reported.
"""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from unittest.mock import Mock


def fixture(result, title):
    import tkinter as tk
    window = tk.Tk(className='HyprwhsprSafeFixture')
    window.title(title)
    text = tk.Text(window)
    text.insert('1.0', 'Synthetic key test; clipboard access disabled')
    text.pack(); text.focus_set()
    events = []
    def key(event):
        events.append({'keysym': event.keysym, 'state': event.state})
        Path(result).write_text(json.dumps(events))
        return 'break'
    text.bind('<KeyPress>', key)
    window.after(15000, window.destroy)
    window.mainloop()


def nodes(node):
    yield node
    for key in ('nodes', 'floating_nodes'):
        for child in node.get(key, []):
            yield from nodes(child)


def tree():
    return list(nodes(json.loads(subprocess.check_output(['swaymsg', '-t', 'get_tree', '-r']))))


def focus(identifier):
    subprocess.run(['swaymsg', f'[con_id={identifier}] focus'], check=True, capture_output=True, timeout=2)


def probe():
    overlay = Path.home()/'.local/share/hyprwhspr-swayfx/1.52.1-sway-v1/lib/src'
    sys.path.insert(0, str(overlay))
    from text_injector import TextInjector
    original = next(n['id'] for n in tree() if n.get('focused'))
    with tempfile.TemporaryDirectory(prefix='hyprwhspr-keys-') as folder:
        result = Path(folder)/'events.json'
        title = f'Hyprwhspr safe key fixture {Path(folder).name}'
        child = subprocess.Popen([sys.executable, __file__, '--fixture', str(result), title])
        injector = None
        try:
            deadline = time.monotonic()+5
            target = None
            while time.monotonic() < deadline:
                target = next((n for n in tree() if n.get('name') == title), None)
                if target: break
                time.sleep(.1)
            if not target: raise RuntimeError('Fixture did not map')
            focus(target['id'])
            injector = TextInjector()
            info = injector._get_active_window_info()
            if not info or not info.get('xwayland') or info['sway_id'] != target['id']:
                raise RuntimeError('Fixture is not focused XWayland')
            injector._save_clipboard = Mock(return_value=None)
            injector._copy_text_to_clipboard = Mock(return_value=True)
            injector._restore_clipboard = Mock()
            for label, action in [
                ('upstream-wtype', lambda: injector._send_paste_keys_wtype('ctrl+v')),
                ('patched-dispatch', lambda: injector._paste_via_clipboard(
                    'Synthetic text only', 'ctrl+v', False, False, expected_window=info))]:
                if injector._get_sway_window_info() != info:
                    raise RuntimeError('Focus changed; refusing test')
                previous = len(json.loads(result.read_text())) if result.exists() else 0
                ok = action(); time.sleep(.15)
                events = json.loads(result.read_text())[previous:] if result.exists() else []
                print(label, ok, events)
                if label == 'patched-dispatch' and not (ok and any(e['keysym']=='v' and e['state'] & 4 for e in events)):
                    raise RuntimeError('Patched Ctrl+V not observed')
        finally:
            if injector: injector.close()
            child.terminate()
            try: child.wait(timeout=3)
            except subprocess.TimeoutExpired:
                child.kill(); child.wait(timeout=3)
            focus(original)


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--fixture': fixture(*sys.argv[2:])
    else: probe()
