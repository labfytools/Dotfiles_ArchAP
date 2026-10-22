#!/usr/bin/python3
"""Bundle utilisateur V2 : préparation, préflight, publication et rollback sans activation."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile

HOME = Path('/home/fy59')
SOURCE = Path(__file__).resolve().parents[1] / 'mosaic-login-v2'
STATE = HOME / '.local/state/labfy-greeter-mosaic-login-v2'
UID = 1000
INSTANCE = r'swayfx\x2dmosaic\x2dtest.desktop'
WANTS = HOME / '.dotfiles/systemd/.config/systemd/user' / f'wayland-session@{INSTANCE}.target.wants'
# CONTRACT: liste fermée ; le manifeste ne fournit jamais une destination libre.
TARGETS = {
    'session': (HOME / '.config/swayfx-mosaic-test/session.py', 0o600, 'launcher/session.py'),
    'manifest': (HOME / '.config/swayfx-mosaic-test/manifest.json', 0o600, 'launcher/manifest.json'),
    'guard': (HOME / '.config/swayfx-mosaic-test/quickshell-guard.py', 0o600, 'launcher/quickshell-guard.py'),
    'service': (HOME / '.dotfiles/systemd/.config/systemd/user/quickshell-labfy-mosaic.service', 0o644, 'systemd/quickshell-labfy-mosaic.service'),
    'qml': (HOME / '.dotfiles/quickshell/.config/quickshell/labfy-sway/sessionui/SessionV2Service.qml', 0o644, 'quickshell/SessionV2Service.qml'),
    'wants': (WANTS / 'quickshell-labfy-mosaic.service', None, None),
}
LINK = '../quickshell-labfy-mosaic.service'
ALIASES = {
    HOME / '.config/systemd': '../.dotfiles/systemd/.config/systemd',
    HOME / '.config/quickshell': '../.dotfiles/quickshell/.config/quickshell',
}
MAX_FILE = 1024 * 1024


def validate_aliases():
    # CONTRACT: Stow reste propriétaire ; vérifier les liens littéraux puis écrire
    # aux seuls chemins canoniques, sans traversée de symlink pendant publication.
    for path, link in ALIASES.items():
        parents(path)
        info = path.lstat()
        if not stat.S_ISLNK(info.st_mode) or info.st_uid != UID or os.readlink(path) != link:
            raise ValueError('Lien Stow divergent : ' + str(path))


def digest(data):
    return hashlib.sha256(data).hexdigest()


def parents(path):
    """INVARIANT: aucun ancêtre symlink ; /var/tmp sticky root est l'unique exception."""
    for parent in path.parents:
        if not os.path.lexists(parent):
            if parent == WANTS:
                continue
            raise ValueError('Parent absent : ' + str(parent))
        info = parent.lstat()
        shared = parent == Path('/var/tmp') and info.st_uid == 0 and info.st_mode & stat.S_ISVTX
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid not in (0, UID)
                or (info.st_mode & 0o022 and not shared)):
            raise ValueError('Parent non sûr : ' + str(parent))


def read(path, mode=None):
    parents(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != UID
                or info.st_gid != UID or info.st_mode & 0o022 or info.st_size > MAX_FILE
                or (mode is not None and stat.S_IMODE(info.st_mode) != mode)):
            raise ValueError('Fichier non sûr : ' + str(path))
        data = stream.read(MAX_FILE + 1)
        if len(data) > MAX_FILE:
            raise ValueError('Fichier trop grand')
        return data


def fsync_dir(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def write(path, data, mode=0o600):
    parents(path)
    fd, name = tempfile.mkstemp(prefix='.labfy-v2-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fchmod(stream.fileno(), mode)
            os.fsync(stream.fileno())
        os.replace(name, path)
        fsync_dir(path.parent)
    finally:
        if os.path.lexists(name):
            os.unlink(name)


def snapshot(path, mode):
    parents(path)
    if not os.path.lexists(path):
        return {'kind': 'absent'}
    if mode is None:
        info = path.lstat()
        if not stat.S_ISLNK(info.st_mode) or info.st_uid != UID or os.readlink(path) != LINK:
            raise ValueError('Activation divergente : ' + str(path))
        return {'kind': 'symlink', 'link': LINK}
    return {'kind': 'file', 'sha256': digest(read(path, mode)), 'mode': mode}


def prepare(bundle):
    validate_aliases()
    parents(bundle)
    if os.path.lexists(WANTS):
        raise ValueError('Répertoire wants déjà présent ; nouvelle revue requise')
    bundle.mkdir(mode=0o700)
    manifest = {'version': 2, 'files': {}}
    for key, (path, mode, source) in TARGETS.items():
        before = snapshot(path, mode)
        if key in ('session', 'manifest', 'qml') and before['kind'] != 'file':
            raise ValueError('Original requis absent : ' + key)
        if key in ('guard', 'service', 'wants') and before['kind'] != 'absent':
            raise ValueError('Nouvelle cible déjà présente : ' + key)
        if before['kind'] == 'file':
            write(bundle / (key + '.old'), read(path, mode))
        if source:
            data = read(SOURCE / source)
            write(bundle / (key + '.new'), data)
            after = {'kind': 'file', 'sha256': digest(data), 'mode': mode}
        else:
            after = {'kind': 'symlink', 'link': LINK}
        manifest['files'][key] = {'old': before, 'new': after}
    write(bundle / 'manifest.json', (json.dumps(manifest, indent=2) + '\n').encode())
    write(bundle / 'mosaic-user-update.py', Path(__file__).read_bytes())
    print('Bundle utilisateur préparé, aucune cible modifiée :', bundle)


def load(bundle):
    manifest = json.loads(read(bundle / 'manifest.json', 0o600))
    if set(manifest) != {'version', 'files'} or manifest['version'] != 2 or set(manifest['files']) != set(TARGETS):
        raise ValueError('Manifeste hors périmètre')
    contents = {}
    for key, states in manifest['files'].items():
        if set(states) != {'old', 'new'}:
            raise ValueError('États invalides')
        contents[key] = {}
        for kind, record in states.items():
            expected_kind = 'symlink' if key == 'wants' else 'file'
            if kind == 'old' and key in ('guard', 'service', 'wants'):
                expected_kind = 'absent'
            if not isinstance(record, dict) or record.get('kind') != expected_kind:
                raise ValueError('Type de cible invalide')
            if record['kind'] == 'file':
                if set(record) != {'kind', 'sha256', 'mode'} or record['mode'] != TARGETS[key][1]:
                    raise ValueError('Mode invalide')
                data = read(bundle / (key + '.' + kind), 0o600)
                if digest(data) != record['sha256']:
                    raise ValueError('SHA invalide : ' + key)
                contents[key][kind] = data
            elif record != ({'kind': 'symlink', 'link': LINK} if record['kind'] == 'symlink' else {'kind': 'absent'}):
                raise ValueError('Lien/absence invalide')
    return manifest, contents


def check(bundle):
    validate_aliases()
    manifest, contents = load(bundle)
    current = {}
    for key, (path, mode, _) in TARGETS.items():
        row = snapshot(path, mode)
        if row not in manifest['files'][key].values():
            raise ValueError('Destination divergente : ' + str(path))
        current[key] = row
    return manifest, contents, current


def journal(bundle, state):
    write(bundle / 'state', (state + '\n').encode())


def publish(bundle, manifest, contents, kind):
    # WHY: le lien wants paraît en dernier ; aucun rechargement/activation implicite.
    # Le journal durable précède chaque lot ; la reprise accepte old/new uniquement.
    for key, (path, mode, _) in TARGETS.items():
        wanted = manifest['files'][key][kind]
        if snapshot(path, mode) == wanted:
            continue
        if wanted['kind'] == 'absent':
            path.unlink()
            fsync_dir(path.parent)
        elif wanted['kind'] == 'file':
            write(path, contents[key][kind], mode)
        else:
            if not WANTS.exists():
                WANTS.mkdir(mode=0o755)
                fsync_dir(WANTS.parent)
            temporary = path.with_name('.labfy-v2-' + os.urandom(12).hex())
            try:
                temporary.symlink_to(LINK)
                os.replace(temporary, path)
                fsync_dir(path.parent)
            finally:
                if os.path.lexists(temporary):
                    temporary.unlink()
    for key, (path, mode, _) in TARGETS.items():
        if snapshot(path, mode) != manifest['files'][key][kind]:
            raise ValueError('Publication non confirmée')
    if kind == 'old' and WANTS.exists():
        try:
            WANTS.rmdir()
            fsync_dir(WANTS.parent)
        except OSError:
            pass  # Un autre lien n'appartient pas à cette transaction.


def durable_bundle(bundle, manifest=None):
    # WHY: conserver le secours autonome et les entrées des nouveaux répertoires
    # est nécessaire même si la copie du bundle n'a jamais été synchronisée.
    # CONTRACT: barrière complète avant journal/publication, sans rollback si échec.
    if manifest is None:
        manifest, _ = load(bundle)
    names = ['manifest.json', 'mosaic-user-update.py']
    names += [key + '.' + kind for key, states in manifest['files'].items()
              for kind, record in states.items() if record['kind'] == 'file']
    if (bundle / 'state').exists():
        names.append('state')
    parents(bundle / 'manifest.json')
    for name in names:
        fd = os.open(bundle / name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            info = os.fstat(fd)
            if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                    or info.st_uid != UID or info.st_gid != UID
                    or stat.S_IMODE(info.st_mode) != 0o600 or info.st_size > MAX_FILE):
                raise ValueError('Fichier de secours non sûr : ' + str(bundle / name))
            os.fsync(fd)
        finally:
            os.close(fd)
    # INVARIANT: synchroniser les contenus avant leurs entrées, jusqu'à /.
    for directory in (bundle, *bundle.parents):
        fsync_dir(directory)


def transact(bundle, operation):
    manifest, contents, current = check(bundle)
    state = read(bundle / 'state', 0o600).decode().strip() if (bundle / 'state').exists() else 'original'
    if state not in ('original', 'applying', 'applied', 'rolling-back'):
        raise ValueError('Journal invalide')
    durable_bundle(bundle, manifest)
    if operation == 'apply' and state in ('applying', 'rolling-back'):
        journal(bundle, 'rolling-back')
        publish(bundle, manifest, contents, 'old')
        journal(bundle, 'original')
        raise ValueError('Interruption restaurée ; vérifier puis relancer explicitement')
    kind = 'new' if operation == 'apply' else 'old'
    if operation == 'apply' and state == 'original' and any(current[k] != manifest['files'][k]['old'] for k in TARGETS):
        raise ValueError('État mixte sans journal ; rollback requis')
    journal(bundle, 'applying' if kind == 'new' else 'rolling-back')
    try:
        publish(bundle, manifest, contents, kind)
        journal(bundle, 'applied' if kind == 'new' else 'original')
    except BaseException:
        journal(bundle, 'rolling-back')
        check(bundle)
        publish(bundle, manifest, contents, 'old')
        journal(bundle, 'original')
        raise
    print('Utilisateur :', operation, 'vérifié ; aucun daemon-reload/enable/start')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('operation', choices=('prepare', 'check', 'durable-barrier', 'apply', 'rollback'))
    p.add_argument('bundle', type=Path)
    args = p.parse_args()
    if os.getuid() != UID or os.geteuid() != UID:
        p.error('Compte utilisateur attendu ; jamais root')
    bundle = args.bundle.absolute()
    if args.operation == 'prepare':
        prepare(bundle)
        return
    if args.operation == 'check':
        check(bundle)
        print('Préflight utilisateur PASS ; lecture seule')
        return
    # Le secours doit survivre au nettoyage de /var/tmp et ne pas importer session.py.
    if not bundle.is_relative_to(STATE):
        p.error('Bundle durable sous ' + str(STATE) + ' requis après approbation')
    parents(bundle / 'state')
    info = bundle.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != UID or stat.S_IMODE(info.st_mode) != 0o700:
        p.error('Bundle privé 0700 requis')
    fd = os.open(STATE / 'update.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != UID or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) != 0o600:
            raise ValueError('Verrou invalide')
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.operation == 'durable-barrier':
            manifest, _, _ = check(bundle)
            durable_bundle(bundle, manifest)
        else:
            transact(bundle, args.operation)
    finally:
        os.close(fd)


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError) as error:
        raise SystemExit('Arrêt sans activation : ' + str(error))
