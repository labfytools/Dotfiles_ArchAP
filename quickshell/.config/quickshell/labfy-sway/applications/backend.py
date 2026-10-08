#!/usr/bin/env python3
"""Favorites persistence and desktop-entry launch requests for the bar menu."""

import fcntl
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

import gi

gi.require_version("Gio", "2.0")
gi.require_version("GioUnix", "2.0")
from gi.repository import GioUnix, GLib


IDENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,199}\.desktop$")
MAX_FAVORITES = 64
MAX_BYTES = 16384


def state_path():
    root = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local/state")
    return root / "labfy-sway/applications-favorites.json"


def valid_id(value):
    return isinstance(value, str) and IDENT.fullmatch(value) is not None


def read_favorites(path):
    try:
        if path.is_symlink():
            raise ValueError("État des favoris invalide")
        with path.open("rb") as stream:
            raw = stream.read(MAX_BYTES + 1)
    except FileNotFoundError:
        return False, []
    if len(raw) > MAX_BYTES:
        raise ValueError("État des favoris trop volumineux")
    data = json.loads(raw)
    ids = data.get("ids") if isinstance(data, dict) and data.get("version") == 1 else None
    if (not isinstance(ids, list) or len(ids) > MAX_FAVORITES
            or any(not valid_id(item) for item in ids) or len(set(ids)) != len(ids)):
        raise ValueError("État des favoris invalide")
    return True, ids


def write_favorites(path, action, ids):
    # CONTRACT: lock the state directory across the read/replace transaction;
    # concurrent clicks cannot silently lose another favorite update.
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        fcntl.flock(directory, fcntl.LOCK_EX)
        exists, current = read_favorites(path)
        if action == "seed":
            if exists:
                return current
            current = list(dict.fromkeys(ids))[:MAX_FAVORITES]
        elif action == "add":
            if ids[0] not in current:
                if len(current) >= MAX_FAVORITES:
                    raise ValueError("Trop de favoris")
                current.append(ids[0])
        elif action == "remove":
            current = [item for item in current if item != ids[0]]
        else:
            raise ValueError("Action de favoris invalide")
        if any(not valid_id(item) for item in current):
            raise ValueError("Identifiant de favori invalide")
        # INVARIANT: the only durable payload is version and ordered IDs.
        payload = (json.dumps({"version": 1, "ids": current}, ensure_ascii=False) + "\n").encode()
        fd, temporary = tempfile.mkstemp(prefix=".favorites-", dir=path.parent)
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
            os.fsync(directory)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        return current
    finally:
        os.close(directory)


def _exec_quoted(value):
    # Desktop Exec uses double quotes, not shell single-quote syntax.
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def terminal_launch_info(app):
    filename = app.get_filename()
    if not filename:
        raise ValueError("Entrée terminal sans fichier desktop")
    keyfile = GLib.KeyFile()
    keyfile.load_from_file(filename, GLib.KeyFileFlags.NONE)
    original = keyfile.get_string("Desktop Entry", "Exec")
    # WHY: a keyfile-created DesktopAppInfo has no source filename for %k.
    # Preserve that field while GLib expands the remaining desktop field codes.
    original = re.sub(r"(?<!%)%k", _exec_quoted(filename), original)
    executable = os.path.basename(app.get_executable() or "")
    prefix = "uwsm app -t service -- "
    if executable != "kitty":
        prefix += "kitty -- "
    keyfile.set_string("Desktop Entry", "Exec", prefix + original)
    keyfile.set_boolean("Desktop Entry", "Terminal", False)
    keyfile.set_boolean("Desktop Entry", "DBusActivatable", False)
    return GioUnix.DesktopAppInfo.new_from_keyfile(keyfile)


def launch(identifier, runner=subprocess.run, loader=GioUnix.DesktopAppInfo.new):
    # CONTRACT: accept an installed desktop ID only; search text and Exec never
    # cross this boundary. UWSM/GIO interpret field codes without a shell.
    if not valid_id(identifier):
        raise ValueError("Identifiant d'application invalide")
    app = loader(identifier)
    if app is None or app.get_is_hidden() or app.get_nodisplay() or not app.should_show():
        raise ValueError("Application indisponible")
    executable = app.get_executable()
    if not app.get_boolean("DBusActivatable") and executable and not shutil.which(executable):
        raise ValueError("Exécutable introuvable")
    if app.get_boolean("Terminal"):
        if not shutil.which("kitty") or not shutil.which("uwsm"):
            raise ValueError("Kitty ou UWSM indisponible")
        if not terminal_launch_info(app).launch([], None):
            raise ValueError("Demande de lancement refusée")
        return
    if app.get_boolean("DBusActivatable"):
        if not app.launch([], None):
            raise ValueError("Activation D-Bus refusée")
        return
    result = runner(["uwsm", "app", "-t", "service", "--", identifier],
                    stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                    timeout=10, check=False)
    if result.returncode:
        raise ValueError("Demande de lancement UWSM refusée")


def main(argv):
    try:
        if len(argv) == 2 and argv == ["favorites", "read"]:
            exists, ids = read_favorites(state_path())
            result = {"exists": exists, "ids": ids}
        elif len(argv) >= 3 and argv[:2] == ["favorites", "seed"]:
            ids = argv[2:]
            if len(ids) > 4 or any(not valid_id(item) for item in ids):
                raise ValueError("Favoris initiaux invalides")
            result = {"ids": write_favorites(state_path(), "seed", ids)}
        elif len(argv) == 3 and argv[:2] in (["favorites", "add"], ["favorites", "remove"]):
            if not valid_id(argv[2]):
                raise ValueError("Identifiant de favori invalide")
            result = {"ids": write_favorites(state_path(), argv[1], [argv[2]])}
        elif len(argv) == 2 and argv[0] == "launch":
            launch(argv[1])
            result = {"ok": True}
        else:
            raise ValueError("Commande invalide")
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (OSError, ValueError, GLib.Error, json.JSONDecodeError, subprocess.TimeoutExpired) as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
