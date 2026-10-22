#!/usr/bin/python3
"""Prépare hors ligne puis applique/restaure quatre fichiers, sans activer greetd."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile

# CONTRACT: périmètre fermé ; aucune configuration, commande système ou préférence UWSM.
TARGETS = {
    "greetd_ipc.py": Path("/usr/local/libexec/labfy-greeter/greetd_ipc.py"),
    "auth.py": Path("/usr/local/libexec/labfy-greeter/auth.py"),
    "labfy_greeter.py": Path("/usr/local/libexec/labfy-greeter/labfy_greeter.py"),
    "labfy-greeter.css": Path("/usr/local/share/labfy-greeter/labfy-greeter.css"),
}
ORIGINALS = {
    "greetd_ipc.py": "07ea7542051ca433cf9ee0e2e6fd7971cfdf103ca7095dac3887e0e8c3309583",
    "auth.py": "e05f2262695f1ec82fede031f284da75f6144e2f14b8cb106dea2dc1aa2e9859",
    "labfy_greeter.py": "b7f0b6e7cf612c4962e9265e4b4fa31ac8c7a3d5b33854c0e8675291ce221326",
    "labfy-greeter.css": "0ffc151cf6eb68b6e0774c69ec799cfafaa92c447626a187d429e162655cee1a",
}
MAX_FILE = 1024 * 1024
OWNER = 0
LOCK = Path("/var/lib/labfy-greeter/session-selector-update.lock")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read_regular(path, uid=None, mode=None):
    # INVARIANT: pas de liens symboliques, taille bornée et métadonnées vérifiées
    # sur le descripteur ouvert, avant de lire le contenu qui sera publié.
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_FILE:
            raise ValueError("Fichier non régulier ou trop grand : " + str(path))
        if uid is not None and (info.st_uid != uid or info.st_gid != uid):
            raise ValueError("Propriétaire inattendu : " + str(path))
        if mode is not None and stat.S_IMODE(info.st_mode) != mode:
            raise ValueError("Mode inattendu : " + str(path))
        data = stream.read(MAX_FILE + 1)
        if len(data) > MAX_FILE:
            raise ValueError("Fichier trop grand")
        return data


def sync_dir(directory):
    fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def atomic_write(path, data, mode, owner=None):
    # WHY: rename ne publie jamais un fichier tronqué ; fsync rend fichier et
    # renommage durables. Les temporaires sont sur le même système de fichiers.
    fd, name = tempfile.mkstemp(prefix=".labfy-session-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            if owner is not None:
                os.fchown(stream.fileno(), owner, owner)
            os.fchmod(stream.fileno(), mode)
            os.fsync(stream.fileno())
        os.replace(name, path)
        sync_dir(path.parent)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def prepare(bundle):
    root = Path(__file__).resolve().parents[1]
    # Refuse de remplacer une préparation existante et ses sauvegardes.
    bundle.mkdir(mode=0o700)
    manifest = {"version": 1, "files": {}}
    for name, target in TARGETS.items():
        before = read_regular(target, 0, 0o644)
        if digest(before) != ORIGINALS[name]:
            raise ValueError("Original installé divergent : " + str(target))
        source = root / ("style" if name.endswith(".css") else "src") / name
        after = read_regular(source)
        atomic_write(bundle / (name + ".old"), before, 0o600)
        atomic_write(bundle / (name + ".new"), after, 0o600)
        manifest["files"][name] = {"old": digest(before), "new": digest(after)}
    atomic_write(bundle / "manifest.json", (json.dumps(manifest, indent=2) + "\n").encode(), 0o600)
    atomic_write(bundle / "session-update.py", Path(__file__).read_bytes(), 0o600)
    print("Préparation seulement :", bundle)


def load_bundle(bundle, owner=None):
    manifest = json.loads(read_regular(bundle / "manifest.json", owner))
    if manifest.get("version") != 1 or set(manifest.get("files", {})) != set(TARGETS):
        raise ValueError("Manifeste hors périmètre")
    contents = {}
    for name, hashes in manifest["files"].items():
        if set(hashes) != {"old", "new"} or hashes["old"] != ORIGINALS[name]:
            raise ValueError("Original non reconnu")
        contents[name] = {}
        for kind in ("old", "new"):
            data = read_regular(bundle / (name + "." + kind), owner)
            if digest(data) != hashes[kind]:
                raise ValueError("SHA256 invalide : " + name + "." + kind)
            contents[name][kind] = data
    return contents


def trusted_parents(path):
    for parent in path.parents:
        info = parent.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != OWNER or info.st_gid != OWNER or info.st_mode & 0o022:
            raise ValueError("Répertoire non sûr : " + str(parent))


def check_targets(contents):
    # CONTRACT: préflight complet avant la première écriture, y compris rollback.
    # Une modification extérieure n'est jamais écrasée, même pendant la reprise.
    current = {}
    for name, path in TARGETS.items():
        trusted_parents(path)
        data = read_regular(path, OWNER, 0o644)
        if data not in contents[name].values():
            raise ValueError("Destination divergente : " + str(path))
        current[name] = data
    return current


def publish(contents, current, kind):
    for name, path in TARGETS.items():
        if current[name] != contents[name][kind]:
            atomic_write(path, contents[name][kind], 0o644, OWNER)
    # CONTRACT: un journal « applied/original » certifie aussi la relecture des
    # octets et métadonnées publiés ; un rename seul n'est pas un résultat vérifié.
    verified = check_targets(contents)
    if any(verified[name] != contents[name][kind] for name in TARGETS):
        raise ValueError("Publication non confirmée")


def set_state(bundle, value):
    atomic_write(bundle / "state", (value + "\n").encode(), 0o600)


def durable_bundle(bundle, extra=()):
    # WHY: une copie récente doit conserver aussi ses outils de secours et son
    # entrée dans chaque parent après une panne, pas seulement ses sauvegardes.
    # CONTRACT: terminer cette barrière AVANT journal/publication ; toute erreur
    # interdit la mutation et ne constitue pas une demande de rollback mutateur.
    names = ("manifest.json", "session-update.py",
             *(n + ".old" for n in TARGETS), *(n + ".new" for n in TARGETS), *extra)
    if (bundle / "state").exists():
        names += ("state",)
    trusted_parents(bundle / "manifest.json")
    for name in names:
        fd = os.open(bundle / name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            info = os.fstat(fd)
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != OWNER
                    or info.st_gid != OWNER or stat.S_IMODE(info.st_mode) != 0o600
                    or info.st_size > MAX_FILE):
                raise ValueError("Fichier de secours non sûr : " + str(bundle / name))
            os.fsync(fd)
        finally:
            os.close(fd)
    # INVARIANT: fichiers d'abord, puis répertoires de bas en haut, jusqu'à /.
    for directory in (bundle, *bundle.parents):
        sync_dir(directory)


def transact(bundle, operation):
    # CONTRACT: un journal durable précède les remplacements. Les quatre rename
    # ne sont pas atomiques ensemble : après SIGKILL/panne, rollback explicite
    # ou prochain apply restaure les originaux avant tout nouvel essai.
    # Aucune activation/restart n'est effectuée, même après succès.
    contents = load_bundle(bundle, OWNER)
    current = check_targets(contents)
    durable_bundle(bundle)
    state_path = bundle / "state"
    state = read_regular(state_path, OWNER, 0o600).decode().strip() if state_path.exists() else "original"
    if state not in ("original", "applying", "applied", "rolling-back"):
        raise ValueError("Journal invalide")
    if operation == "apply" and state in ("applying", "rolling-back"):
        set_state(bundle, "rolling-back")
        publish(contents, current, "old")
        set_state(bundle, "original")
        raise ValueError("Transaction interrompue restaurée ; relancer apply après vérification")
    kind = "new" if operation == "apply" else "old"
    if operation == "apply" and state == "original" and any(current[n] != contents[n]["old"] for n in TARGETS):
        raise ValueError("État mixte sans journal ; rollback requis")
    set_state(bundle, "applying" if kind == "new" else "rolling-back")
    try:
        publish(contents, current, kind)
        set_state(bundle, "applied" if kind == "new" else "original")
    except BaseException:
        # Erreur ordinaire/interruption Python : rollback immédiat de tout le lot.
        # Une panne empêchant ce rollback laisse le journal récupérable.
        set_state(bundle, "rolling-back")
        publish(contents, check_targets(contents), "old")
        set_state(bundle, "original")
        raise
    print("Fichiers " + ("mis à jour" if kind == "new" else "restaurés") + " ; greetd non redémarré")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("prepare", "check", "apply", "rollback"))
    parser.add_argument("bundle", type=Path)
    args = parser.parse_args()
    bundle = args.bundle.absolute()
    if args.operation == "prepare":
        prepare(bundle)
        return
    if args.operation == "check":
        check_targets(load_bundle(bundle))
        print("SHA256, périmètre, permissions : OK ; aucune écriture")
        return
    if os.geteuid() != 0:
        parser.error("apply/rollback nécessitent root après approbation distincte")
    trusted_parents(bundle)
    info = bundle.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or info.st_gid != 0 or stat.S_IMODE(info.st_mode) != 0o700:
        parser.error("bundle attendu root:root en mode 0700")
    # INVARIANT: un verrou global empêche deux bundles distincts de publier
    # simultanément sur les mêmes cibles ; journal/sauvegardes restent privés.
    trusted_parents(LOCK)
    fd = os.open(LOCK, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    try:
        lock_info = os.fstat(fd)
        if not stat.S_ISREG(lock_info.st_mode) or lock_info.st_uid != 0 or lock_info.st_gid != 0 or stat.S_IMODE(lock_info.st_mode) != 0o600:
            raise ValueError("Verrou non sûr")
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        transact(bundle, args.operation)
    finally:
        os.close(fd)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError) as exc:
        raise SystemExit("Arrêt sans activation : " + str(exc))
