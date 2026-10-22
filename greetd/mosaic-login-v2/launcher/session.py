#!/usr/bin/python3
"""Préparation expérimentale locale ; aucune commande de changement de session."""
import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import stat
import subprocess
import sys

LAB = Path('/var/tmp/swayfx-mosaic-session-mvp-id6h_707')
HOME = Path('/home/fy59')
CONFIG = HOME / '.config/swayfx-mosaic-test'
SELECTION_ALIAS = HOME / '.config/uwsm'
SELECTION_DIR = HOME / '.dotfiles/uwsm/.config/uwsm'
SELECTION_LINK = '../.dotfiles/uwsm/.config/uwsm'
SESSION = 'swayfx-mosaic-test.desktop'
INSTANCE = r'swayfx\x2dmosaic\x2dtest.desktop'
WM_UNIT = f'wayland-wm@{INSTANCE}.service'
SESSION_UNIT = f'wayland-session@{INSTANCE}.target'
BINARY = LAB / 'bin/swayfx-mosaic'
BINARY_SHA = '91f48aae2675331e0a2c60ec2fedf983745c521c75232c704a6516a4140801fb'
WLROOTS = Path('/usr/lib/libwlroots-0.20.so')
WLROOTS_SHA = '7edca9a7d65855addda68e29ba5db94d57c803eb5fa7d0f86db3136b90ca9837'
EXCLUDED = ('swayidle.service', 'wlsunset.service', 'cliphist-image.service',
            'cliphist-text.service', f'wayland-session-xdg-autostart@{INSTANCE}.target')


def secure_directory(path):
    """CONTRACT: walk canonical paths with dirfds; never traverse a symlink.

    Root-owned /var/tmp is the sole shared writable ancestor allowed: its
    sticky bit protects our already-created, UID-owned private LAB directory.
    """
    path = Path(path)
    if not path.is_absolute():
        raise RuntimeError('Chemin non absolu')
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        walked = Path('/')
        for name in path.parts[1:]:
            newfd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                            dir_fd=fd)
            os.close(fd)
            fd = newfd
            walked /= name
            info = os.fstat(fd)
            sticky_tmp = (walked == Path('/var/tmp') and info.st_uid == 0
                          and info.st_mode & stat.S_ISVTX)
            if info.st_uid not in (0, os.getuid()) or (info.st_mode & 0o022 and not sticky_tmp):
                raise RuntimeError(f'Ancêtre non sûr : {walked}')
        return fd
    except BaseException:
        os.close(fd)
        raise


def read_regular(path, limit=16384, owner=None):
    parent = secure_directory(Path(path).parent)
    try:
        fd = os.open(Path(path).name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                     dir_fd=parent)
        try:
            info = os.fstat(fd)
            if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                    or info.st_uid != (os.getuid() if owner is None else owner)
                    or info.st_mode & 0o022 or info.st_size > limit):
                raise RuntimeError(f'Fichier non sûr : {path}')
            with os.fdopen(fd, 'rb', closefd=False) as stream:
                data = stream.read(limit + 1)
            if len(data) > limit:
                raise RuntimeError(f'Fichier trop volumineux : {path}')
            return data
        finally:
            os.close(fd)
    finally:
        os.close(parent)


def atomic_write(directory, name, data):
    """WHY: durable complete replacement, never an in-place/truncated default-id.

    Callers serialize this kit's selection operations. UWSM does not share our
    lock, so no automatic restore/CAS claim is made against concurrent tools.
    """
    fd = secure_directory(directory)
    temporary = '.mosaic-' + os.urandom(12).hex()
    try:
        out = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                      0o600, dir_fd=fd)
        with os.fdopen(out, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, name, src_dir_fd=fd, dst_dir_fd=fd)
        os.fsync(fd)
    finally:
        try:
            os.unlink(temporary, dir_fd=fd)
        except FileNotFoundError:
            pass
        os.close(fd)


class Selection:
    """Only arm/stable change preference, by explicit user command.

    The existing Stow symlink is allowed only with its audited literal target;
    all canonical ancestors and the final default-id are checked independently.
    A failed launch never changes preference and never starts another session.
    """
    def __init__(self, alias=SELECTION_ALIAS, directory=SELECTION_DIR,
                 link=SELECTION_LINK, state=CONFIG):
        # CONTRACT: None décrit un répertoire direct dans les tests isolés ;
        # le déploiement réel conserve le lien Stow littéral audité.
        self.alias, self.directory, self.state = map(Path, (alias, directory, state))
        self.link = link

    def validate(self):
        fd = secure_directory(self.alias.parent)
        try:
            info = os.stat(self.alias.name, dir_fd=fd, follow_symlinks=False)
            if self.link is not None:
                if (not stat.S_ISLNK(info.st_mode) or info.st_uid != os.getuid()
                        or os.readlink(self.alias.name, dir_fd=fd) != self.link):
                    raise RuntimeError('Lien UWSM modifié ; aucune écriture')
            elif not stat.S_ISDIR(info.st_mode):
                raise RuntimeError('Répertoire UWSM attendu')
        finally:
            os.close(fd)
        current = read_regular(self.directory / 'default-id', 256)
        if not re.fullmatch(rb'[A-Za-z0-9_.:-]+\n?', current):
            raise RuntimeError('default-id invalide ; aucune écriture')
        return current

    def change(self, arm=False):
        fd = secure_directory(self.state)
        try:
            lock = os.open('selection.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW
                           | os.O_NONBLOCK, 0o600, dir_fd=fd)
        finally:
            os.close(fd)
        try:
            info = os.fstat(lock)
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                    or info.st_nlink != 1 or info.st_mode & 0o077):
                raise RuntimeError('Verrou de sélection non sûr')
            fcntl.flock(lock, fcntl.LOCK_EX)
            before = self.validate()
            if arm:
                if before.strip() == SESSION.encode():
                    return 'Mosaic déjà armé ; retour MANUEL requis'
                if before.strip() != b'sway.desktop':
                    raise RuntimeError('Sélection différente de sway.desktop ; armement refusé')
                atomic_write(self.state, 'stable-default.backup', before)
            # INVARIANT: reject a changed observed selection before replacement.
            # This is cooperative serialization, not a kernel CAS with uwsm.
            if self.validate() != before:
                raise RuntimeError('Sélection concurrente observée ; aucune écriture')
            atomic_write(self.directory, 'default-id',
                         (SESSION if arm else 'sway.desktop').encode() + b'\n')
            expected = SESSION.encode() if arm else b'sway.desktop'
            if self.validate().strip() != expected:
                raise RuntimeError('Sélection non confirmée ; vérifier default-id')
            return ('Mosaic armé MANUELLEMENT ; restaurer sway.desktop depuis Kitty avant sortie'
                    if arm else 'Préférence stable restaurée : sway.desktop ; sessions actives intactes')
        finally:
            os.close(lock)


def run(argv):
    result = subprocess.run(argv, check=True, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True, timeout=8)
    return result.stdout.strip()


def properties(argv):
    result = {}
    for line in run(argv).splitlines():
        if '=' not in line:
            raise RuntimeError('Propriété systemd malformée')
        key, value = line.split('=', 1)
        if key in result:
            raise RuntimeError('Propriété systemd dupliquée')
        result[key] = value
    return result


def systemd_words(value, paths=False):
    """CONTRACT: décoder la représentation textuelle de systemctl, jamais un shell.

    WHY: les noms contenant \\x2d sont entre guillemets, avec antislash doublé.
    Le split naïf garde cette représentation au lieu du nom d'unité réel.
    On accepte seulement la grammaire émise pour nos unités/chemins audités ;
    les escapes inconnus et tokens concaténés sont refusés avant shlex.
    """
    if type(value) is not str or len(value) > 16384 or any(ord(c) < 32 for c in value):
        raise RuntimeError('Liste systemd invalide')
    grammar = r'(?:[^\s"\x27\\]+|"(?:[^"\\]|\\[\\"])*")'
    if value and not re.fullmatch(grammar + r'(?: +' + grammar + r')*', value):
        raise RuntimeError('Encodage systemd invalide')
    words = shlex.split(value, posix=True)
    pattern = (r'/(?:[A-Za-z0-9_./@:-]|\\x[0-9a-f]{2})+' if paths else
               r'(?:[A-Za-z0-9_.@:-]|\\x[0-9a-f]{2})+\.(?:service|target|socket|slice|scope|mount|timer|path|device|swap|automount)')
    if len(words) > 128 or any(not re.fullmatch(pattern, w) for w in words):
        raise RuntimeError('Élément systemd invalide')
    return words


def validate_isolation(target, wm):
    """INVARIANT: l'isolation existe dans le manager chargé, pas seulement sur disque."""
    base = HOME / '.local/share/systemd/user'
    for props, unit in ((target, SESSION_UNIT), (wm, WM_UNIT)):
        expected = str(base / (unit + '.d') / '20-mosaic-smoke.conf')
        if (props.get('Id') != unit or props.get('LoadState') != 'loaded'
                or expected not in systemd_words(props.get('DropInPaths', ''), paths=True)):
            raise RuntimeError('Unité/drop-in Mosaic non chargé')
    if not set(EXCLUDED).issubset(systemd_words(target.get('Conflicts', ''))):
        raise RuntimeError('Isolation swayidle/autostart non chargée')


def isolation_properties(unit):
    return properties(['/usr/bin/systemctl', '--user', 'show', unit,
                       '-p', 'Id', '-p', 'LoadState', '-p', 'DropInPaths', '-p', 'Conflicts'])


def verify_files():
    if os.getuid() != 1000 or Path(os.environ.get('HOME', '')) != HOME:
        raise RuntimeError('Compte/HOME inattendu')
    if os.environ.get('XDG_CONFIG_HOME', str(HOME / '.config')) != str(HOME / '.config'):
        raise RuntimeError('XDG_CONFIG_HOME inattendu')
    # CONTRACT: qs -c labfy-sway et le manager utilisent les alias Stow audités.
    # Le manifeste lit leurs destinations canoniques sans traverser ces liens.
    for name, target in (('systemd', '../.dotfiles/systemd/.config/systemd'),
                         ('quickshell', '../.dotfiles/quickshell/.config/quickshell')):
        alias = HOME / '.config' / name
        info = alias.lstat()
        if (not stat.S_ISLNK(info.st_mode) or info.st_uid != os.getuid()
                or os.readlink(alias) != target):
            raise RuntimeError('Lien Stow incompatible : ' + name)
    # WHY: dynamic-loader overrides could invalidate the audited provider pair.
    for name in ('LD_PRELOAD', 'LD_LIBRARY_PATH', 'LD_AUDIT'):
        if os.environ.get(name):
            raise RuntimeError(f'Variable chargeur incompatible : {name}')
    binary = read_regular(BINARY, 16 * 1024 * 1024)
    if hashlib.sha256(binary).hexdigest() != BINARY_SHA:
        raise RuntimeError('Identité CORE-C V2 invalide ou LAB temporaire supprimé')
    if BINARY.stat().st_mode & 0o222 or not os.access(BINARY, os.X_OK):
        raise RuntimeError('Copie binaire non figée/exécutable')
    # This installed SONAME path is allowed to be a root-owned library symlink;
    # resolve, then validate the resulting regular file and exact bytes.
    resolved = WLROOTS.resolve(strict=True)
    provider = read_regular(resolved, 32 * 1024 * 1024, owner=0)
    if hashlib.sha256(provider).hexdigest() != WLROOTS_SHA:
        raise RuntimeError('wlroots a changé ; requalification obligatoire')
    manifest = json.loads(read_regular(CONFIG / 'manifest.json'))
    for filename, expected in manifest['files'].items():
        if not Path(filename).is_absolute():
            raise RuntimeError('Chemin manifest invalide')
        data = read_regular(Path(filename), 131072)
        if hashlib.sha256(data).hexdigest() != expected:
            raise RuntimeError(f'Fichier préparé modifié : {filename}')
    Selection().validate()


def validate_context(env, cgroup, login, foreground, units):
    """CONTRACT: authenticate context before any physical compositor exec.

    UWSM runs the WM in the user manager, not directly under PAM. Validate the
    login session carried by env_session.conf against logind, and the actual
    service cgroup independently; never replace PAM's XDG_RUNTIME_DIR.
    """
    for name in ('WAYLAND_DISPLAY', 'DISPLAY', 'SWAYSOCK', 'I3SOCK', 'WAYLAND_SOCKET'):
        if env.get(name):
            raise RuntimeError(f'Session graphique parente/héritée détectée : {name}')
    if not any(line.endswith('/' + WM_UNIT) for line in cgroup.splitlines()):
        raise RuntimeError('Lancement réservé à l’unité UWSM Mosaic authentifiée')
    if not env.get('INVOCATION_ID') or not env.get('NOTIFY_SOCKET'):
        raise RuntimeError('Contexte systemd notify absent')
    if (env.get('XDG_SEAT') != 'seat0' or not env.get('XDG_VTNR', '').isdigit()
            or not 1 <= int(env['XDG_VTNR']) <= 63
            or foreground != 'tty' + env['XDG_VTNR']):
        raise RuntimeError('Siège/VT actif incompatible')
    if (login.get('User') != str(os.getuid()) or login.get('Class') != 'user'
            or login.get('Seat') != 'seat0' or login.get('VTNr') != env['XDG_VTNR']
            or login.get('Active') != 'yes' or login.get('Remote') != 'no'
            or login.get('Type') not in ('wayland', 'tty')):
        raise RuntimeError('Session logind authentifiée/active non confirmée')
    for name in ('WLR_BACKENDS', 'WLR_RENDERER', 'WLR_HEADLESS_OUTPUTS',
                 'WLR_DRM_DEVICES', 'WLR_LIBINPUT_NO_DEVICES', 'LIBSEAT_BACKEND'):
        if env.get(name):
            raise RuntimeError(f'Override expérimental hérité : {name}')
    # A second UWSM WM, including a stable WM still stopping, is not admissible.
    if any(name != WM_UNIT and (state in ('active', 'activating', 'deactivating'))
           for name, state in units):
        raise RuntimeError('Un autre compositeur UWSM est encore présent')


def launch():
    verify_files()
    runtime = Path(os.environ.get('XDG_RUNTIME_DIR', ''))
    if str(runtime) != f'/run/user/{os.getuid()}':
        raise RuntimeError('XDG_RUNTIME_DIR PAM inattendu')
    fd = secure_directory(runtime)
    info = os.fstat(fd)
    os.close(fd)
    if info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise RuntimeError('Runtime PAM non privé')
    sid = os.environ.get('XDG_SESSION_ID', '')
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', sid):
        raise RuntimeError('Identité logind absente')
    login = properties(['/usr/bin/loginctl', 'show-session', sid, '-p', 'User',
                        '-p', 'Class', '-p', 'Seat', '-p', 'VTNr', '-p', 'Active',
                        '-p', 'Remote', '-p', 'Type'])
    raw_units = run(['/usr/bin/systemctl', '--user', 'list-units', 'wayland-wm@*.service',
                     '--all', '--plain', '--no-legend', '--no-pager'])
    units = [(fields[0], fields[2]) for line in raw_units.splitlines()
             if len(fields := line.split()) >= 3]
    validate_context(os.environ, Path('/proc/self/cgroup').read_text(), login,
                     Path('/sys/class/tty/tty0/active').read_text().strip(), units)
    # Confirm the session-specific isolation is loaded, without altering manager
    # state, stopping a service or talking to any compositor IPC socket.
    validate_isolation(isolation_properties(SESSION_UNIT), isolation_properties(WM_UNIT))
    env = dict(os.environ)
    for name in ('WAYLAND_DISPLAY', 'WAYLAND_SOCKET', 'DISPLAY', 'SWAYSOCK', 'I3SOCK'):
        env.pop(name, None)
    env['XDG_CURRENT_DESKTOP'] = 'swayfx-mosaic-test:wlroots:sway'
    env['XDG_SESSION_DESKTOP'] = 'swayfx-mosaic-test'
    env['XDG_SESSION_TYPE'] = 'wayland'
    # WHY: the Sway IPC namespace, logind context and runtime directory belong
    # to this process. Finalization happens later from this compositor's exec.
    print('MOSAIC: CORE-C V2 vérifié ; lancement direct seat0 ; retour MANUEL stable requis',
          flush=True)
    os.chdir(HOME)
    os.execve(str(BINARY), [str(BINARY), '-c', str(CONFIG / 'config')], env)


def receipt():
    """Systemd owns exit status after exec; save only fixed bounded fields."""
    fields = {name: os.environ.get(name, 'unknown')[:128]
              for name in ('SERVICE_RESULT', 'EXIT_CODE', 'EXIT_STATUS')}
    fields['time_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    atomic_write(LAB / 'logs', 'last-exit.json',
                 (json.dumps(fields, indent=2) + '\n').encode())


def main():
    if len(sys.argv) != 2:
        raise RuntimeError('Usage : session.py check|arm|stable|launch|exit-receipt')
    action = sys.argv[1]
    if action == 'check':
        verify_files()
        print('Préparation et identités PASS ; matériel NOT_RUN ; aucune sélection modifiée')
    elif action == 'arm':
        verify_files()
        print(Selection().change(arm=True))
    elif action == 'stable':
        print(Selection().change())
    elif action == 'launch':
        launch()
    elif action == 'exit-receipt':
        receipt()
    else:
        raise RuntimeError('Action inconnue')


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        print(f'MOSAIC REFUSÉ : {error}. Retour : ~/.config/swayfx-mosaic-test/swayfx-mosaic-test-stable',
              file=sys.stderr)
        sys.exit(1)
