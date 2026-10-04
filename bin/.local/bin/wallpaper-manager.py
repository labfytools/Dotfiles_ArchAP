#!/usr/bin/env python3
"""Galerie locale et publication transactionnelle du wallpaper Sway (schéma 2)."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
import warnings
from urllib.parse import unquote, urlsplit

from PIL import Image, ImageOps, UnidentifiedImageError

# WHY: une image piégée ne doit pas faire exploser la mémoire du processus
# de scan ; la limite s'applique à un fichier, pas à la taille du dossier.
Image.MAX_IMAGE_PIXELS = 50_000_000
warnings.simplefilter('error', Image.DecompressionBombWarning)


DEFAULT = Path('/usr/share/backgrounds/sway/Sway_Wallpaper_Blue_1920x1080.png')
SUFFIXES = {'.jpg', '.jpeg', '.png', '.webp'}
THUMB_VERSION = 1
PAGE_SIZE = 24
SWAY = Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config')) / 'sway'
PREFERENCES = Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config')) / 'labfy-appearance/preferences.json'
STATE = Path(os.environ.get('XDG_STATE_HOME', Path.home() / '.local/state')) / 'labfy-appearance/effective.json'
CACHE = Path(os.environ.get('XDG_CACHE_HOME', Path.home() / '.cache')) / 'labfy-appearance/wallpapers'
GENERATED = SWAY / 'generated/wallpaper.conf'
ALIASES = Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config')) / 'labfy-appearance/wallpapers'


def atomic_write(path, data):
    """Un rename sur le même volume préserve l'ancien fichier en cas d'échec."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=path.name + '.', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
        directory = os.open(path.parent, os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        Path(name).unlink(missing_ok=True)


def write_json(path, value):
    atomic_write(path, (json.dumps(value, ensure_ascii=False, separators=(',', ':')) + '\n').encode())


def read_json(path):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}


def initial_directory():
    """Préférence valide, .wallpapers, Pictures/Wallpapers, XDG Pictures, HOME."""
    pref = read_json(PREFERENCES).get('wallpaperDirectory')
    home = Path.home()
    pictures = home / 'Pictures'
    user_dirs = home / '.config/user-dirs.dirs'
    try:
        for line in user_dirs.read_text(encoding='utf-8').splitlines():
            if line.startswith('XDG_PICTURES_DIR='):
                pictures = Path(line.split('=', 1)[1].strip('"').replace('$HOME', str(home)))
    except OSError:
        pass
    for item in (pref, str(home / '.wallpapers'), str(home / 'Pictures/Wallpapers'), str(pictures), str(home)):
        if item and Path(item).is_dir():
            return str(Path(item).expanduser().resolve())
    return str(home)


def validate_image(path):
    """La cible d'un symlink doit être régulière et décodable ; l'extension seule ne suffit pas."""
    path = Path(path).expanduser()
    if path.suffix.lower() not in SUFFIXES or not path.is_file():
        raise ValueError('Fichier image absent ou format non pris en charge')
    canonical = path.resolve(strict=True)
    if not canonical.is_file():
        raise ValueError('Cible image non régulière')
    with Image.open(canonical) as image:
        image.verify()
    with Image.open(canonical) as image:
        if image.format not in {'JPEG', 'PNG', 'WEBP'} or image.width < 1 or image.height < 1:
            raise ValueError('Image invalide ou format non pris en charge')
        image.load()
        width, height, fmt = image.width, image.height, image.format
    stat = canonical.stat()
    return {'path': str(path.absolute()), 'canonicalPath': str(canonical),
            'filename': path.name, 'width': width, 'height': height, 'format': fmt,
            'size': stat.st_size, 'mtime': stat.st_mtime_ns}


def cache_key(meta):
    payload = json.dumps([THUMB_VERSION, meta['canonicalPath'], meta['size'], meta['mtime']],
                         ensure_ascii=False, separators=(',', ':'))
    return hashlib.sha256(payload.encode()).hexdigest()


def thumbnail(meta):
    target = CACHE / (cache_key(meta) + '.png')
    if not target.is_file():
        with Image.open(meta['canonicalPath']) as image:
            image = ImageOps.exif_transpose(image)
            image.thumbnail((320, 320), Image.Resampling.LANCZOS)
            if image.mode not in ('RGB', 'RGBA'):
                image = image.convert('RGBA' if 'A' in image.getbands() else 'RGB')
            CACHE.mkdir(parents=True, exist_ok=True)
            fd, name = tempfile.mkstemp(prefix='.thumbnail-', suffix='.png', dir=CACHE)
            try:
                with os.fdopen(fd, 'wb') as stream:
                    image.save(stream, format='PNG')
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(name, target)
            finally:
                Path(name).unlink(missing_ok=True)
        # Le nettoyage n'inspecte que ce cache et garde une borne locale.
        cached = list(CACHE.glob('*.png'))
        if len(cached) > 512:
            for old in sorted(cached, key=lambda p: p.stat().st_mtime_ns)[:len(cached) - 448]:
                if old != target:
                    old.unlink(missing_ok=True)
    return target.as_uri()


def scan(directory, page):
    if not Path(directory).is_dir():
        raise ValueError('Dossier introuvable')
    # WHY: seules 24 images par requête sont décodées ; l'UI demande la page
    # suivante sur action explicite, sans daemon, polling ni processus par delegate.
    candidates = sorted((p for p in Path(directory).iterdir() if not p.name.startswith('.')
                         and p.suffix.lower() in SUFFIXES and p.is_file()),
                        key=lambda p: (p.name.casefold(), p.name))
    entries = []
    offset = page * PAGE_SIZE
    for item in candidates[offset:offset + PAGE_SIZE]:
        try:
            meta = validate_image(item)
            meta['thumbnail'] = thumbnail(meta)
            entries.append(meta)
        except (OSError, ValueError, UnidentifiedImageError,
                Image.DecompressionBombError, Image.DecompressionBombWarning):
            continue
    return {'version': 1, 'directory': str(Path(directory).resolve()), 'page': page,
            'hasMore': offset + PAGE_SIZE < len(candidates), 'items': entries}


def render_wallpaper(path):
    # CONTRACT: SwayFX 0.6 ne parse pas les chemins cités avec espaces.
    # Le chemin transmis ici est un alias ASCII du fichier utilisateur.
    if not re.fullmatch(r'/[A-Za-z0-9_./-]+', path):
        raise ValueError('Chemin alias non représentable dans Sway')
    return ('# Généré par wallpaper-manager.py ; ne pas éditer.\n'
            + 'set $wallpaper ' + path + '\n').encode('utf-8')


def safe_alias(meta):
    """Lien persistant sans caractères spéciaux pour le parseur Sway."""
    ALIASES.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(meta['canonicalPath'].encode()).hexdigest()[:24]
    alias = ALIASES / ('image-' + digest + Path(meta['path']).suffix.lower())
    fd, temporary = tempfile.mkstemp(prefix='.link-', dir=ALIASES)
    os.close(fd)
    Path(temporary).unlink()
    try:
        os.symlink(meta['canonicalPath'], temporary)
        os.replace(temporary, alias)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return str(alias)


def command(*args):
    result = subprocess.run(args, capture_output=True, text=True, timeout=15, check=False)
    # WHY: SwayFX 0.6 peut renvoyer 0 avec « Error(s) loading config! ».
    if result.returncode or 'Error(s) loading config!' in result.stderr:
        raise RuntimeError((result.stderr or result.stdout).strip() or 'Commande Sway échouée')
    if args[0] == 'swaymsg':
        try:
            if any(not item.get('success', False) for item in json.loads(result.stdout)):
                raise RuntimeError('Sway a refusé le rechargement')
        except (ValueError, TypeError, AttributeError) as exc:
            raise RuntimeError('Réponse swaymsg invalide') from exc
    return result


def swaybg_matches(path):
    """Vérifie le fond réellement transmis au swaybg lancé par Sway."""
    for proc in Path('/proc').iterdir():
        if not proc.name.isdecimal():
            continue
        try:
            args = (proc / 'cmdline').read_bytes().split(b'\0')
            if args and Path(os.fsdecode(args[0])).name == 'swaybg':
                decoded = [os.fsdecode(a) for a in args]
                if '-i' in decoded and decoded[decoded.index('-i') + 1] == path and '-m' in decoded \
                        and decoded[decoded.index('-m') + 1] == 'fill':
                    return True
        except (OSError, IndexError):
            pass
    return False


def active_wallpaper():
    """Migration 17B : découvrir l'image en cours sans changer Sway."""
    for proc in Path('/proc').iterdir():
        if not proc.name.isdecimal():
            continue
        try:
            args = [os.fsdecode(a) for a in (proc / 'cmdline').read_bytes().split(b'\0')]
            if args and Path(args[0]).name == 'swaybg' and '-i' in args:
                path = Path(args[args.index('-i') + 1])
                return str(path.resolve()) if path.is_file() else str(path)
        except (OSError, IndexError):
            pass
    return str(DEFAULT)


def current():
    state = read_json(STATE)
    path = state.get('effectiveWallpaper') or active_wallpaper()
    if not Path(path).is_file():
        return {'version': 2, 'effectiveWallpaper': path, 'wallpaperMissing': True,
                'fallback': str(DEFAULT), 'wallpaperDirectory': initial_directory(),
                'wallpaperMode': 'fill', 'revision': state.get('revision', 0)}
    return {'version': 2, 'effectiveWallpaper': path, 'wallpaperMissing': False,
            'wallpaperDirectory': initial_directory(), 'wallpaperMode': 'fill',
            'revision': state.get('revision', 0)}


def apply(path):
    # INVARIANT: lock couvre config, reload et état ; deux appels ne s'entremêlent pas.
    STATE.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE.parent / 'wallpaper.lock', 'a+b') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        meta = validate_image(path)
        target = meta['path']
        old_config = GENERATED.read_bytes() if GENERATED.exists() else None
        old_state = STATE.read_bytes() if STATE.exists() else None
        old = read_json(STATE)
        try:
            alias = safe_alias(meta)
            if old.get('effectiveWallpaper', active_wallpaper()) == target and swaybg_matches(alias):
                return current()
            atomic_write(GENERATED, render_wallpaper(alias))
            command('sway', '--validate', '-c', str(SWAY / 'config'))
            command('swaymsg', 'reload')
            deadline = time.monotonic() + 4
            while time.monotonic() < deadline and not swaybg_matches(alias):
                time.sleep(0.1)
            if not swaybg_matches(alias):
                raise RuntimeError('Sway n’a pas appliqué le fond demandé')
            # WHY: préserver tous les champs 17B et inconnus pour la migration
            # et les futurs consommateurs ; seul le wallpaper et sa révision changent.
            new_state = dict(old)
            new_state.setdefault('effectiveFlavor', 'mocha')
            new_state.setdefault('effectiveAccent', 'lavender')
            new_state.setdefault('effectiveMode', 'normal')
            new_state.setdefault('effectiveDark', new_state['effectiveFlavor'] != 'latte')
            new_state.setdefault('effectiveHighContrast', False)
            new_state.update(version=2, effectiveWallpaper=target, wallpaperMode='fill',
                             revision=max(0, int(old.get('revision', 0))) + 1)
            write_json(STATE, new_state)
            # Seul l'alias actif est requis au prochain login ; les anciens
            # liens créés par ce backend ne doivent pas s'accumuler.
            for previous_alias in ALIASES.glob('image-*'):
                if str(previous_alias) != alias and previous_alias.is_symlink():
                    try:
                        previous_alias.unlink()
                    except OSError:
                        pass
            return current()
        except Exception:
            if old_config is None:
                GENERATED.unlink(missing_ok=True)
            else:
                atomic_write(GENERATED, old_config)
            if old_state is None:
                STATE.unlink(missing_ok=True)
            else:
                atomic_write(STATE, old_state)
            command('swaymsg', 'reload')
            raise


def set_directory(path):
    if path.startswith('file:'):
        uri = urlsplit(path)
        if uri.scheme != 'file' or uri.netloc not in ('', 'localhost'):
            raise ValueError('URI de dossier non locale')
        path = unquote(uri.path)
    directory = Path(path).expanduser().resolve(strict=True)
    if not directory.is_dir():
        raise ValueError('Dossier introuvable')
    pref = read_json(PREFERENCES)
    pref.update(version=1, wallpaperDirectory=str(directory), wallpaperMode='fill')
    write_json(PREFERENCES, pref)
    return {'version': 1, 'wallpaperDirectory': str(directory), 'wallpaperMode': 'fill'}


def reconcile():
    """Après suppression de l'image active, revenir explicitement au repli versionné."""
    state = current()
    if not state['wallpaperMissing']:
        return state
    missing = state['effectiveWallpaper']
    result = apply(str(DEFAULT))
    result['recoveredFromMissing'] = missing
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    sub.add_parser('current')
    sub.add_parser('reconcile')
    scan_parser = sub.add_parser('scan')
    scan_parser.add_argument('directory')
    scan_parser.add_argument('--page', type=int, default=0)
    for action in ('validate', 'thumbnail', 'apply', 'set-directory'):
        sub.add_parser(action).add_argument('path')
    args = parser.parse_args()
    try:
        if args.action == 'current': result = current()
        elif args.action == 'reconcile': result = reconcile()
        elif args.action == 'scan':
            if args.page < 0: raise ValueError('Page invalide')
            result = scan(args.directory, args.page)
        elif args.action == 'validate': result = validate_image(args.path)
        elif args.action == 'thumbnail':
            result = validate_image(args.path)
            result['thumbnail'] = thumbnail(result)
        elif args.action == 'apply': result = apply(args.path)
        else: result = set_directory(args.path)
        print(json.dumps(result, ensure_ascii=False, separators=(',', ':')))
        return 0
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired,
            UnidentifiedImageError, Image.DecompressionBombError,
            Image.DecompressionBombWarning, BlockingIOError) as exc:
        print('Erreur : ' + str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
