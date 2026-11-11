"""Shared application catalog, private icon theme and bounded Sway requests.

No session/restore state is consulted or changed. The only persistent write
remains backend.write_favorites, under its existing directory transaction lock.
"""
import json
import os
import re
from pathlib import Path
import socket
import struct
import sys
import time

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gio, GioUnix, GLib, Gtk
from backend import state_path, read_favorites, write_favorites, valid_id
from dock_separators import path_for as separators_path_for, read as read_separators, write as write_separators

# CONTRACT: private GtkIconTheme instance, never Gtk settings or desktop-wide
# theme changes. GTK implements theme inheritance and absolute GIcon lookup.
ICON_THEME = 'Tela-circle-purple-dark'
# CONTRACT: middle-click is conservative. These terminal launchers create a
# new toplevel per invocation. Unknown and single-instance GUI applications
# retain their ordinary Open action without promising another instance.
NEW_INSTANCE_IDS = frozenset(('kitty.desktop', 'foot.desktop', 'Alacritty.desktop',
                              'org.wezfurlong.wezterm.desktop'))


class IconResolver:
    def __init__(self, theme=ICON_THEME):
        self.theme = Gtk.IconTheme.new()
        self.theme.set_custom_theme(theme)

    def resolve(self, icon):
        if icon:
            info = self.theme.lookup_by_gicon(icon, 48, Gtk.IconLookupFlags.FORCE_SIZE)
            if info and Path(info.get_filename()).is_file():
                return Path(info.get_filename()).as_uri()
        info = self.theme.lookup_icon('application-x-executable', 48, 0)
        return Path(info.get_filename()).as_uri() if info and Path(info.get_filename()).is_file() else ''


def catalog():
    resolver = IconResolver()
    result = []
    for app in Gio.AppInfo.get_all():
        identifier = app.get_id()
        if not valid_id(identifier) or not app.should_show() or not isinstance(app, GioUnix.DesktopAppInfo):
            continue
        icon = app.get_icon()
        # WHY: StartupWMClass is the desktop author's declared window identity.
        # Filename stem and executable basename cover standard Wayland app_ids;
        # ambiguous aliases are deliberately left unmatched by the UI model.
        aliases = [identifier[:-8], app.get_startup_wm_class(),
                   os.path.basename(app.get_executable() or '')]
        result.append(dict(id=identifier, name=app.get_display_name(),
                           genericName=app.get_generic_name() or '',
                           keywords=list(app.get_keywords() or []),
                           categories=(app.get_categories() or '').split(';'),
                           icon=icon.to_string() if icon else '', iconSource=resolver.resolve(icon),
                           aliases=sorted({v.casefold() for v in aliases if v}),
                           # D-Bus activation may only activate an existing window;
                           # do not promise a new instance for these applications.
                           newInstance=identifier in NEW_INSTANCE_IDS and not app.get_boolean('DBusActivatable')))
    return sorted(result, key=lambda a: a['id'])


def sway_request(kind, payload):
    # CONTRACT: direct IPC, explicit little-endian widths, bounded reply and
    # timeout. No shell, no inherited process, no background focus operations.
    data = payload.encode()
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        deadline = time.monotonic() + 2
        sock.settimeout(2)
        sock.connect(os.environ['SWAYSOCK'])
        sock.sendall(b'i3-ipc' + struct.pack('<II', len(data), kind) + data)
        def receive(size):
            parts = bytearray()
            while len(parts) < size:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError('Délai IPC Sway dépassé')
                sock.settimeout(remaining)
                block = sock.recv(size - len(parts))
                if not block:
                    raise ValueError('IPC Sway interrompu')
                parts.extend(block)
            return parts
        header = receive(14)
        length, reply_kind = struct.unpack('<II', header[6:])
        if header[:6] != b'i3-ipc' or reply_kind != kind or length > 16 * 1024 * 1024:
            raise ValueError('Réponse IPC Sway invalide')
        return json.loads(receive(length))


def windows(tree):
    result = []
    pending = [(tree, '')]
    while pending:
        node, workspace = pending.pop()
        if node.get('type') == 'workspace':
            workspace = node.get('name', '')
        pending.extend((child, workspace) for child in
                       node.get('nodes', []) + node.get('floating_nodes', []))
        props = node.get('window_properties') or {}
        if not (node.get('app_id') or node.get('window')):
            continue
        foreign = node.get('foreign_toplevel_identifier') or ''
        if not isinstance(foreign, str) or re.fullmatch(r'[a-f0-9]{32}', foreign) is None:
            foreign = ''
        result.append(dict(id=str(node['id']), title=node.get('name') or 'Fenêtre',
                           appId=node.get('app_id') or '', wmClass=props.get('class') or '',
                           instance=props.get('instance') or '', workspace=workspace,
                           foreignId=foreign, focused=bool(node.get('focused'))))
    return sorted(result, key=lambda w: int(w['id']))


def focus(identifier):
    if not isinstance(identifier, str) or not identifier.isascii() or not identifier.isdigit():
        raise ValueError('Identifiant de fenêtre invalide')
    target = next((w for w in windows(sway_request(4, '')) if w['id'] == identifier), None)
    if not target:
        raise ValueError('Fenêtre fermée')
    command = f'[con_id={int(identifier)}] '
    if target['workspace'] == '__i3_scratch':
        replies = sway_request(0, command + 'scratchpad show')
        if not all(reply.get('success') for reply in replies):
            raise ValueError('Scratchpad indisponible')
    if not all(reply.get('success') for reply in sway_request(0, command + 'focus')):
        raise ValueError('Focus refusé')


def serve():
    """Single stream serializes UI mutations and disk notifications.

    INVARIANT: every published list is re-read from disk. A rejected mutation
    publishes the unchanged durable state plus an error, never an optimistic
    list. File monitoring survives atomic replacement by watching the directory.
    """
    path = state_path()
    separators_path = separators_path_for(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    apps = catalog()
    def publish(error=''):
        try:
            exists, ids = read_favorites(path)
            separators = read_separators(separators_path)
            print(json.dumps(dict(ids=ids, exists=exists, apps=apps,
                                  separators=separators, theme=ICON_THEME,
                                  error=error)), flush=True)
        except (OSError, ValueError) as exc:
            print(json.dumps(dict(error=str(exc))), flush=True)
        return False
    monitor = Gio.File.new_for_path(str(path.parent)).monitor_directory(Gio.FileMonitorFlags.NONE, None)
    pending = [0]
    def changed(*_args):
        if not pending[0]:
            pending[0] = GLib.timeout_add(35, refresh)
    def refresh():
        pending[0] = 0
        return publish()
    monitor.connect('changed', changed)
    app_monitor = Gio.AppInfoMonitor.get()
    def apps_changed(*_args):
        nonlocal apps
        apps = catalog()
        publish()
    app_monitor.connect('changed', apps_changed)
    loop = GLib.MainLoop()
    # CONTRACT: newline JSON input is bounded before parsing. GLib owns the
    # single main thread; EOF ends this helper with its QuickShell owner.
    buffer = bytearray()
    def request(fd, condition):
        chunk = os.read(fd, 4096)
        if not chunk:
            loop.quit()
            return False
        buffer.extend(chunk)
        if len(buffer) > 16384:
            loop.quit()
            return False
        while b'\n' in buffer:
            line, _, rest = buffer.partition(b'\n')
            buffer[:] = rest
            try:
                data = json.loads(line)
                action = data.get('action')
                ids = data.get('ids')
                if not isinstance(ids, list):
                    raise ValueError('Commande invalide')
                if action in ('dock-separator-add', 'dock-separator-remove', 'dock-separator-move'):
                    write_separators(separators_path, action.removeprefix('dock-separator-'), ids)
                elif action in ('add', 'remove', 'toggle', 'move', 'seed'):
                    if action == 'seed' and (len(ids) > 4 or any(not valid_id(i) for i in ids)):
                        raise ValueError('Favoris initiaux invalides')
                    write_favorites(path, action, ids)
                else:
                    raise ValueError('Commande invalide')
                publish()
            except (OSError, ValueError, TypeError) as exc:
                publish(str(exc))
        return True
    GLib.io_add_watch(sys.stdin.fileno(), GLib.IO_IN | GLib.IO_HUP, request)
    publish()
    loop.run()
    monitor.cancel()
    return 0
