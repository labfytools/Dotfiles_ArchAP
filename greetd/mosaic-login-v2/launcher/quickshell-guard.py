#!/usr/bin/python3
"""Garde en lecture seule avant QuickShell ; aucun IPC Sway, aucun démarrage."""
import hashlib
import os
from pathlib import Path
import re
import stat
import sys
import session as s

QS_UNIT = 'quickshell-labfy-mosaic.service'
STABLE_QS = 'quickshell-labfy-sway.service'


def validate_ready(env, wm, target, stable, units, cgroup):
    """CONTRACT: le service notify WM et son target sont actifs après finalize.

    INVARIANT: le manager utilisateur partagé ne peut pas fournir les sockets
    d'une ancienne session : SWAYSOCK encode exactement le MainPID vérifié.
    """
    if (wm.get('Id') != s.WM_UNIT or wm.get('ActiveState') != 'active'
            or wm.get('SubState') != 'running' or not wm.get('MainPID', '').isdigit()
            or int(wm['MainPID']) <= 1 or target.get('Id') != s.SESSION_UNIT
            or target.get('ActiveState') != 'active'):
        raise RuntimeError('Mosaic/finalize non prêt')
    if stable.get('ActiveState') not in ('inactive', 'failed'):
        raise RuntimeError('QuickShell Stable encore présent')
    if any(name != s.WM_UNIT and state in ('active', 'activating', 'deactivating')
           for name, state in units):
        raise RuntimeError('Autre WM dans le manager partagé')
    if not any(line.endswith('/' + QS_UNIT) for line in cgroup.splitlines()):
        raise RuntimeError('Garde réservée au service QuickShell Mosaic')
    runtime = f'/run/user/{os.getuid()}'
    expected = runtime + f'/sway-ipc.{os.getuid()}.{wm["MainPID"]}.sock'
    if (env.get('XDG_RUNTIME_DIR') != runtime or env.get('SWAYSOCK') != expected
            or env.get('I3SOCK') != expected
            or not re.fullmatch(r'wayland-[0-9]+', env.get('WAYLAND_DISPLAY', ''))
            or env.get('XDG_SESSION_DESKTOP') != 'swayfx-mosaic-test'
            or env.get('XDG_CURRENT_DESKTOP') != 'swayfx-mosaic-test:wlroots:sway'
            or env.get('LABFY_MOSAIC_SMOKE') != '1'):
        raise RuntimeError('Environnement/finalize Mosaic incompatible')
    return int(wm['MainPID'])


def verify_process(pid, env):
    proc = Path('/proc') / str(pid)
    exe = proc / 'exe'
    if (proc.stat().st_uid != os.getuid() or exe.resolve(strict=True) != s.BINARY
            or hashlib.sha256(exe.read_bytes()).hexdigest() != s.BINARY_SHA):
        raise RuntimeError('MainPID/binaire Mosaic non confirmé')
    if not any(line.endswith('/' + s.WM_UNIT) for line in (proc / 'cgroup').read_text().splitlines()):
        raise RuntimeError('Cgroup WM incorrect')
    providers = {line.split()[-1] for line in (proc / 'maps').read_text().splitlines()
                 if 'libwlroots-' in line}
    if providers != {str(s.WLROOTS.resolve(strict=True))}:
        raise RuntimeError('Mapping wlroots différent')
    # WHY: l'inode de chacun des sockets doit appartenir au processus WM réel.
    # Ne jamais se connecter à un socket hérité, même pour une simple requête.
    owned = set()
    for fd in (proc / 'fd').iterdir():
        try:
            link = os.readlink(fd)
        except FileNotFoundError:
            continue
        match = re.fullmatch(r'socket:\[([0-9]+)\]', link)
        if match:
            owned.add(match[1])
    sockets = {}
    for line in Path('/proc/net/unix').read_text().splitlines()[1:]:
        fields = line.split()
        if len(fields) == 8:
            sockets[fields[7]] = fields[6]
    runtime = Path(env['XDG_RUNTIME_DIR'])
    for path in (Path(env['SWAYSOCK']), runtime / env['WAYLAND_DISPLAY']):
        info = path.lstat()
        if (not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.getuid()
                or sockets.get(str(path)) not in owned):
            raise RuntimeError('Socket non possédé par Mosaic')
    # Aucun second labfy-sway (service ou lancement manuel) avant polkit/notifications.
    for other in Path('/proc').iterdir():
        if not other.name.isdigit() or other.name == str(os.getpid()):
            continue
        try:
            if other.stat().st_uid != os.getuid():
                continue
            if (other / 'exe').resolve().name in ('qs', 'quickshell'):
                raise RuntimeError('Une autre instance QuickShell existe')
        except (FileNotFoundError, ProcessLookupError):
            continue
    # La session PAM du WM reste l'autorité ; aucune variable logind globale héritée.
    wm_env = dict(part.split(b'=', 1) for part in (proc / 'environ').read_bytes().split(b'\0') if b'=' in part)
    sid = wm_env.get(b'XDG_SESSION_ID', b'').decode('ascii')
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', sid):
        raise RuntimeError('Session logind WM absente')
    login = s.properties(['/usr/bin/loginctl', 'show-session', sid, '-p', 'User',
                          '-p', 'Class', '-p', 'Seat', '-p', 'VTNr', '-p', 'Active',
                          '-p', 'Remote', '-p', 'Type'])
    if (login.get('User') != str(os.getuid()) or login.get('Class') != 'user'
            or login.get('Seat') != 'seat0' or login.get('Active') != 'yes'
            or login.get('Remote') != 'no' or login.get('Type') not in ('wayland', 'tty')
            or login.get('VTNr') != wm_env.get(b'XDG_VTNR', b'').decode('ascii')
            or Path('/sys/class/tty/tty0/active').read_text().strip() != 'tty' + login.get('VTNr', '')):
        raise RuntimeError('Session logind/VT WM non confirmée')


def main():
    s.verify_files()
    s.validate_isolation(s.isolation_properties(s.SESSION_UNIT), s.isolation_properties(s.WM_UNIT))
    def show(unit):
        return s.properties(['/usr/bin/systemctl', '--user', 'show', unit, '-p', 'Id',
                             '-p', 'ActiveState', '-p', 'SubState', '-p', 'MainPID'])
    raw = s.run(['/usr/bin/systemctl', '--user', 'list-units', 'wayland-wm@*.service',
                 '--all', '--plain', '--no-legend', '--no-pager'])
    units = [(fields[0], fields[2]) for line in raw.splitlines()
             if len(fields := line.split()) >= 3]
    pid = validate_ready(os.environ, show(s.WM_UNIT), show(s.SESSION_UNIT),
                         show(STABLE_QS), units, Path('/proc/self/cgroup').read_text())
    verify_process(pid, os.environ)
    if s.run(['/usr/bin/busctl', '--user', 'call', 'org.freedesktop.DBus',
              '/org/freedesktop/DBus', 'org.freedesktop.DBus', 'NameHasOwner',
              's', 'org.freedesktop.Notifications']) != 'b false':
        raise RuntimeError('Serveur de notifications déjà présent')
    print(f'QuickShell Mosaic prêt : unité={s.WM_UNIT}, PID={pid}, '
          f'WAYLAND_DISPLAY={os.environ["WAYLAND_DISPLAY"]}, SWAYSOCK={os.environ["SWAYSOCK"]}', flush=True)


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, RuntimeError, s.subprocess.SubprocessError) as error:
        print(f'QUICKSHELL MOSAIC REFUSÉ : {error}', file=sys.stderr)
        sys.exit(1)
