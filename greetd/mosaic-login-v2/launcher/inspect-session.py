#!/usr/bin/python3
"""Read-only smoke identity; refuse stable IPC before invoking swaymsg."""
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys

spec = importlib.util.spec_from_file_location('session', Path(__file__).with_name('session.py'))
s = importlib.util.module_from_spec(spec)
spec.loader.exec_module(s)


def main():
    s.verify_files()
    socket = os.environ.get('SWAYSOCK', '')
    match = re.fullmatch(r'/run/user/1000/sway-ipc\.1000\.([0-9]+)\.sock', socket)
    if not match:
        raise RuntimeError('Socket Mosaic non reconnu')
    pid = int(match.group(1))
    exe = Path(f'/proc/{pid}/exe')
    # WHY: inherited stable sockets must never be used, even for read-only IPC.
    if exe.resolve(strict=True) != s.BINARY:
        raise RuntimeError('Le processus de ce socket n’est pas la copie CORE-C V2 ; aucun IPC envoyé')
    if Path(f'/proc/{pid}').stat().st_uid != os.getuid():
        raise RuntimeError('Propriétaire du processus incorrect')
    info = Path(socket).lstat()
    if not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.getuid():
        raise RuntimeError('Socket non sûr')
    import hashlib
    if hashlib.sha256(exe.read_bytes()).hexdigest() != s.BINARY_SHA:
        raise RuntimeError('SHA du processus incorrect')
    maps = Path(f'/proc/{pid}/maps').read_text()
    providers = sorted({line.split()[-1] for line in maps.splitlines()
                        if 'libwlroots-' in line})
    if providers != [str(s.WLROOTS.resolve())]:
        raise RuntimeError(f'Provider wlroots inattendu : {providers}')
    print(json.dumps({'pid': pid, 'exe': str(exe.resolve()), 'sha256': s.BINARY_SHA,
                      'SWAYSOCK': socket, 'WAYLAND_DISPLAY': os.environ.get('WAYLAND_DISPLAY'),
                      'wlroots_loaded': providers}, indent=2))
    print('Chaîne des parents (lecture /proc, pas de recherche par nom sway) :')
    for _ in range(12):
        fields = Path(f'/proc/{pid}/stat').read_text().rsplit(') ', 1)[1].split()
        print(pid, Path(f'/proc/{pid}/comm').read_text().strip())
        pid = int(fields[1])
        if pid <= 0:
            break
    # Only after exact process identity, use the explicit verified Mosaic socket.
    for query in ('get_outputs', 'get_inputs', 'get_workspaces'):
        print(query)
        result = subprocess.run(['/usr/bin/swaymsg', '-s', socket, '-t', query],
                                capture_output=True, text=True, timeout=5, check=True)
        print(result.stdout[:16384])
    print('Identité locale confirmée ; observations visuelles/input restent à renseigner.')


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        print(f'Inspection refusée : {error}', file=sys.stderr)
        sys.exit(1)
