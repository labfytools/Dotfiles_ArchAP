#!/usr/bin/python3
"""Coordonne les deux bundles durables V2, sans démarrer/recharger aucun service."""
import argparse
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess

ROOT_BUNDLE = Path('/var/lib/labfy-greeter/login-recovery-v2')
USER_BUNDLE = Path('/home/fy59/.local/state/labfy-greeter-mosaic-login-v2/v2')
UID = 1000
PROTECTED = (
    Path('/etc/greetd/config.toml'),
    Path('/usr/local/libexec/labfy-greeter/start-compositor'),
    Path('/usr/local/libexec/labfy-greeter/run-ui'),
    Path('/home/fy59/.dotfiles/systemd/.config/systemd/user/quickshell-labfy-sway.service'),
    Path('/home/fy59/.dotfiles/uwsm/.config/uwsm/default-id'),
    Path('/var/tmp/swayfx-mosaic-session-mvp-id6h_707/bin/swayfx-mosaic'),
    Path('/usr/lib/libwlroots-0.20.so'),
)


def load_root(bundle):
    # CONTRACT: les imports root viennent exclusivement d'une copie durable root.
    # Pour check non-root, le bundle de revue est lu sans opération privilégiée.
    if os.geteuid() == 0:
        for p in (bundle, *bundle.parents):
            info = p.lstat()
            if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or info.st_gid != 0 or info.st_mode & 0o022:
                raise ValueError('Parent root non sûr : ' + str(p))
        script = bundle / 'session-update.py'
        info = script.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_gid != 0 or stat.S_IMODE(info.st_mode) != 0o600:
            raise ValueError('Outil root non sûr')
    spec = importlib.util.spec_from_file_location('root_update', bundle / 'session-update.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def seal_user(root, user, tool):
    # INVARIANT: ne pas exécuter/consommer un bundle utilisateur différent du lot revu.
    # Tous les chemins de cibles restent définis dans les outils, jamais dans ce seal.
    seal = json.loads(tool.read_regular(root / 'user-seal.json', 0 if os.geteuid() == 0 else None, 0o600))
    required = {'manifest.json', 'mosaic-user-update.py',
                *(key + '.old' for key in ('session', 'manifest', 'qml')),
                *(key + '.new' for key in ('session', 'manifest', 'guard', 'service', 'qml'))}
    if type(seal) is not dict or set(seal) != required:
        raise ValueError('Seal utilisateur hors périmètre')
    # Répertoires canoniques, UID attendu et absence d'écriture groupe/autres.
    for p in (user, *user.parents):
        info = p.lstat()
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid not in (0, UID)
                or (info.st_mode & 0o022 and not (p == Path('/var/tmp') and info.st_uid == 0 and info.st_mode & stat.S_ISVTX))):
            raise ValueError('Parent utilisateur non sûr')
    for name, expected in seal.items():
        data = tool.read_regular(user / name, UID, 0o600)
        if hashlib.sha256(data).hexdigest() != expected:
            raise ValueError('Bundle utilisateur divergent : ' + name)


def user_action(user, operation):
    # WHY: même lancé par root, l'outil utilisateur s'exécute après abandon d'UID/GID.
    # Aucun shell, sudo, activation, ni configuration héritée de Python/du bureau.
    kwargs = dict(user=UID, group=UID, extra_groups=[]) if os.geteuid() == 0 else {}
    subprocess.run(['/usr/bin/python3', '-I', '-B', str(user / 'mosaic-user-update.py'), operation, str(user)],
                   check=True, timeout=60,
                   env={'HOME': '/home/fy59', 'PATH': '/usr/bin', 'LANG': 'C.UTF-8'}, **kwargs)


def check_protected(root, tool):
    """Préflight apply uniquement : le rollback ne dépend jamais du binaire temporaire."""
    expected = json.loads(tool.read_regular(root / 'protected.json', 0 if os.geteuid() == 0 else None, 0o600))
    if type(expected) is not dict or set(expected) != {str(p) for p in PROTECTED}:
        raise ValueError('Inventaire protégé invalide')
    for path in PROTECTED:
        # Le SONAME système est un symlink root audité ; les autres chemins
        # sont canoniques. Aucun de ces fichiers n'est une destination écrite.
        actual = path.resolve(strict=True) if str(path) == '/usr/lib/libwlroots-0.20.so' else path
        info = actual.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_size > 32 * 1024 * 1024:
            raise ValueError('Fichier protégé invalide')
        if hashlib.sha256(actual.read_bytes()).hexdigest() != expected[str(path)]:
            raise ValueError('Fichier protégé divergent : ' + str(path))


def coordinate(root, operation, tool, user):
    """CONTRACT: journal global AVANT user, greeter en dernier ; rollback inverse.

    L'ensemble multi-fichiers n'est pas atomique. Après panne, la relance restaure
    les deux sous-lots et refuse d'avancer sans nouvel essai explicite. L'utilisateur
    doit éviter une nouvelle connexion pendant cette courte publication.
    """
    state_file = root / 'batch-state'
    state = tool.read_regular(state_file, tool.OWNER, 0o600).decode().strip() if state_file.exists() else 'original'
    if state not in ('original', 'applying', 'applied', 'rolling-back'):
        raise ValueError('Journal global invalide')
    # WHY: user est publié en premier mais dépend aussi du secours root complet.
    # CONTRACT: les DEUX barrières précèdent toute mutation, y compris rollback.
    # INVARIANT: leur échec reste hors du handler de rollback de publication.
    extra = ('login-recovery-update.py', 'user-seal.json', 'protected.json')
    if state_file.exists():
        extra += ('batch-state',)
    tool.durable_bundle(root, extra)
    user_action(user, 'durable-barrier')
    def journal(value):
        tool.atomic_write(state_file, (value + '\n').encode(), 0o600, tool.OWNER)
    def rollback():
        journal('rolling-back')
        errors = []
        # Toujours tenter les DEUX restaurations, même si l'une est empêchée.
        for action in (lambda: tool.transact(root, 'rollback'), lambda: user_action(user, 'rollback')):
            try:
                action()
            except Exception as error:
                errors.append(str(error))
        if errors:
            raise ValueError('Rollback incomplet ; journal conservé : ' + '; '.join(errors))
        journal('original')
    if operation == 'rollback':
        rollback()
        return
    if state in ('applying', 'rolling-back'):
        rollback()
        raise ValueError('Lot interrompu restauré ; vérifier avant un nouvel apply')
    journal('applying')
    try:
        user_action(user, 'apply')
        tool.transact(root, 'apply')
        journal('applied')
    except BaseException:
        rollback()
        raise
    print('Lot V2 publié/vérifié ; aucun service rechargé/redémarré, aucune session arrêtée')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('check', 'apply', 'rollback'))
    parser.add_argument('root_bundle', nargs='?', type=Path, default=ROOT_BUNDLE)
    parser.add_argument('user_bundle', nargs='?', type=Path, default=USER_BUNDLE)
    args = parser.parse_args()
    root, user = args.root_bundle.absolute(), args.user_bundle.absolute()
    if args.operation != 'check' and (os.geteuid() != 0 or root != ROOT_BUNDLE or user != USER_BUNDLE):
        parser.error('Publication réservée aux chemins durables et à root après approbation')
    tool = load_root(root)
    seal_user(root, user, tool)
    if args.operation != 'rollback':
        check_protected(root, tool)
    tool.check_targets(tool.load_bundle(root, 0 if os.geteuid() == 0 else None))
    user_action(user, 'check')
    if args.operation == 'check':
        print('Préflight global PASS ; aucune écriture')
        return
    tool.trusted_parents(tool.LOCK)
    fd = os.open(tool.LOCK, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_gid != 0 or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) != 0o600:
            raise ValueError('Verrou root invalide')
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        # Les deux préflights sont répétés sous verrou avant le journal global.
        seal_user(root, user, tool)
        if args.operation != 'rollback':
            check_protected(root, tool)
        tool.check_targets(tool.load_bundle(root, 0))
        user_action(user, 'check')
        coordinate(root, args.operation, tool, user)
    finally:
        os.close(fd)


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        raise SystemExit('Arrêt V2 sans activation : ' + str(error))
