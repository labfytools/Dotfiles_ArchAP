#!/usr/bin/env python3
"""Galerie locale et publication compensable wallpaper/thème Sway (schéma 3)."""
import argparse
import fcntl
import hashlib
import importlib.util
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
from wallpaper_analysis import ALGORITHM_VERSION, analyze as analyze_wallpaper

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
GENERATED_THEME = SWAY / 'generated/theme.conf'
ALIASES = Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config')) / 'labfy-appearance/wallpapers'
FLAVORS = ('latte', 'frappe', 'macchiato', 'mocha')
STATE_VERSION = 3
PREF_VERSION = 3


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


def preferences(state=None):
    """Migration non destructive des préférences 17C et de l'état 17B/17C."""
    state = state if state is not None else read_json(STATE)
    value = read_json(PREFERENCES)
    mode = value.get('themeMode', state.get('themeMode', 'manual'))
    manual = value.get('manualFlavor', state.get('manualFlavor', state.get('effectiveFlavor', 'mocha')))
    if mode not in ('manual', 'wallpaper'):
        mode = 'manual'
    if manual not in FLAVORS:
        manual = 'mocha'
    return {**value, 'version': PREF_VERSION, 'themeMode': mode,
            'manualFlavor': manual, 'accent': 'lavender', 'wallpaperMode': 'fill',
            'wallpaperDirectory': initial_directory()}


def rendered_theme(flavor):
    """Réutilise le générateur 17B : aucune seconde palette ni formule Sway."""
    source = Path(__file__).with_name('generate-appearance.py')
    spec = importlib.util.spec_from_file_location('generate_appearance', source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.render(flavor, 'lavender').encode('utf-8')


def publish_live(state, pref):
    # CONTRACT: IPC seulement après Sway et les écritures durables ; le QML
    # reprend exactement la révision persistée, sans incrément local supplémentaire.
    payload = json.dumps({'state': state, 'preferences': pref}, ensure_ascii=False,
                         separators=(',', ':'))
    result = command('qs', '-c', 'labfy-sway', 'ipc', 'call', 'appearance', 'publishState', payload)
    if result.stdout.strip() != 'true':
        raise RuntimeError('QuickShell a refusé le nouvel état Appearance')


def restore_file(path, previous):
    if previous is None:
        path.unlink(missing_ok=True)
    else:
        atomic_write(path, previous)


def state_response(state, pref, analysis=None):
    result = dict(state)
    result.update(themeMode=pref['themeMode'], manualFlavor=pref['manualFlavor'],
                  wallpaperDirectory=pref['wallpaperDirectory'])
    if analysis is not None:
        result['analysis'] = analysis
    return result


def transaction(wallpaper=None, mode=None, manual_flavor=None):
    """Applique un état compensable sous un verrou commun thème/wallpaper."""
    STATE.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE.parent / 'wallpaper.lock', 'a+b') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        old_wallpaper = GENERATED.read_bytes() if GENERATED.exists() else None
        old_theme = GENERATED_THEME.read_bytes() if GENERATED_THEME.exists() else None
        old_state = STATE.read_bytes() if STATE.exists() else None
        old_preferences = PREFERENCES.read_bytes() if PREFERENCES.exists() else None
        old = read_json(STATE)
        previous_pref = preferences(old)
        pref = dict(previous_pref)
        if mode is not None:
            if mode not in ('manual', 'wallpaper'):
                raise ValueError('Mode de thème invalide')
            pref['themeMode'] = mode
        if manual_flavor is not None:
            if manual_flavor not in FLAVORS:
                raise ValueError('Flavor manuel invalide')
            if pref['themeMode'] != 'manual':
                raise ValueError('Revenir en mode Manuel avant de choisir un flavor')
            pref['manualFlavor'] = manual_flavor
        meta = validate_image(wallpaper) if wallpaper is not None else None
        target = meta['path'] if meta else old.get('effectiveWallpaper') or active_wallpaper()
        if not Path(target).is_file():
            raise ValueError('Wallpaper courant introuvable')
        analysis = None
        if pref['themeMode'] == 'wallpaper':
            try:
                analysis = analyze_wallpaper(meta or validate_image(target))
            except Exception as exc:
                # L'analyse précède toute écriture ; un échec ne laisse aucun
                # état hybride et ne retire jamais un wallpaper déjà appliqué.
                raise ValueError('Analyse Auto Theme : ' + str(exc)) from exc
            flavor = analysis['flavor']
        else:
            flavor = pref['manualFlavor'] if mode is not None or manual_flavor is not None \
                else old.get('effectiveFlavor', pref['manualFlavor'])
        if flavor not in FLAVORS:
            raise ValueError('Flavor effectif invalide')
        previous_wallpaper = old.get('effectiveWallpaper') or active_wallpaper()
        wallpaper_changed = meta is not None and (target != previous_wallpaper
                             or old.get('wallpaperMtime') != meta['mtime'])
        flavor_changed = flavor != old.get('effectiveFlavor', 'mocha')
        mode_changed = pref['themeMode'] != previous_pref['themeMode']
        state = dict(old)
        state.update(version=STATE_VERSION, effectiveFlavor=flavor,
                     effectiveMode='normal', effectiveDark=flavor != 'latte',
                     effectiveHighContrast=False, effectiveAccent='lavender',
                     effectiveWallpaper=target, wallpaperMode='fill',
                     themeMode=pref['themeMode'], manualFlavor=pref['manualFlavor'],
                     revision=max(0, int(old.get('revision', 0)))
                     + int(wallpaper_changed or flavor_changed or mode_changed))
        if meta is not None:
            state['wallpaperMtime'] = meta['mtime']
        if analysis is not None:
            state['wallpaperAnalysis'] = analysis
        elif pref['themeMode'] == 'manual':
            state.pop('wallpaperAnalysis', None)
        if not (wallpaper_changed or flavor_changed or mode_changed
                or pref != previous_pref or old.get('version') != STATE_VERSION):
            return state_response(state, pref, analysis)
        alias = None
        wrote_config = False
        try:
            if wallpaper_changed:
                alias = safe_alias(meta)
                atomic_write(GENERATED, render_wallpaper(alias))
                wrote_config = True
            if flavor_changed:
                atomic_write(GENERATED_THEME, rendered_theme(flavor))
                wrote_config = True
            if wrote_config:
                command('sway', '--validate', '-c', str(SWAY / 'config'))
                command('swaymsg', 'reload')
            if wallpaper_changed:
                deadline = time.monotonic() + 4
                while time.monotonic() < deadline and not swaybg_matches(alias):
                    time.sleep(0.1)
                if not swaybg_matches(alias):
                    raise RuntimeError('Sway n’a pas appliqué le fond demandé')
            write_json(STATE, state)
            write_json(PREFERENCES, pref)
            publish_live(state, pref)
            # Seul l'alias actif est requis au prochain login ; les anciens
            # liens créés par ce backend ne doivent pas s'accumuler.
            if alias:
                for previous_alias in ALIASES.glob('image-*'):
                    if str(previous_alias) != alias and previous_alias.is_symlink():
                        try:
                            previous_alias.unlink()
                        except OSError:
                            pass
            return state_response(state, pref, analysis)
        except Exception:
            restore_file(GENERATED, old_wallpaper)
            restore_file(GENERATED_THEME, old_theme)
            restore_file(STATE, old_state)
            restore_file(PREFERENCES, old_preferences)
            if wrote_config:
                command('swaymsg', 'reload')
            raise


def apply(path):
    return transaction(wallpaper=path)


def set_theme_mode(mode):
    return transaction(mode=mode)


def set_manual_flavor(flavor):
    return transaction(manual_flavor=flavor)


def set_directory(path):
    if path.startswith('file:'):
        uri = urlsplit(path)
        if uri.scheme != 'file' or uri.netloc not in ('', 'localhost'):
            raise ValueError('URI de dossier non locale')
        path = unquote(uri.path)
    directory = Path(path).expanduser().resolve(strict=True)
    if not directory.is_dir():
        raise ValueError('Dossier introuvable')
    STATE.parent.mkdir(parents=True, exist_ok=True)
    # INVARIANT: le picker ne doit pas perdre un changement de dossier si une
    # application thème/wallpaper publie simultanément les préférences.
    with open(STATE.parent / 'wallpaper.lock', 'a+b') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        pref = preferences()
        pref.update(wallpaperDirectory=str(directory))
        write_json(PREFERENCES, pref)
    return {'version': PREF_VERSION, 'wallpaperDirectory': str(directory), 'wallpaperMode': 'fill'}


def reconcile():
    """Après suppression de l'image active, revenir explicitement au repli versionné."""
    state = current()
    if not state['wallpaperMissing']:
        return state
    missing = state['effectiveWallpaper']
    result = apply(str(DEFAULT))
    result['recoveredFromMissing'] = missing
    return result


def reconcile_state():
    """Au restart, effective.json tranche toute publication interrompue."""
    STATE.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE.parent / 'wallpaper.lock', 'a+b') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        state = read_json(STATE)
        pref = preferences(state)
        if state.get('version') == STATE_VERSION:
            # Une préférence écrite avant un crash n'est pas une application.
            applied_mode = state.get('themeMode')
            applied_manual = state.get('manualFlavor')
            pref['themeMode'] = applied_mode if applied_mode in ('manual', 'wallpaper') else pref['themeMode']
            pref['manualFlavor'] = applied_manual if applied_manual in FLAVORS else pref['manualFlavor']
            state.update(themeMode=pref['themeMode'], manualFlavor=pref['manualFlavor'])
        else:
            state.update(version=STATE_VERSION, themeMode=pref['themeMode'],
                         manualFlavor=pref['manualFlavor'])
        flavor = state.get('effectiveFlavor', 'mocha')
        if flavor not in FLAVORS:
            raise ValueError('État effectif invalide')
        state.update(effectiveFlavor=flavor, effectiveAccent='lavender',
                     effectiveDark=flavor != 'latte', effectiveHighContrast=False,
                     effectiveMode='normal', wallpaperMode='fill',
                     effectiveWallpaper=state.get('effectiveWallpaper') or active_wallpaper(),
                     revision=max(0, int(state.get('revision', 0))))
        if not Path(state['effectiveWallpaper']).is_file():
            # Le fond déjà rendu peut survivre à la suppression ; l'UI reçoit
            # le signal de manque et un futur apply/reconcile utilise le repli.
            return state_response(state, pref)
        expected_theme = rendered_theme(flavor)
        meta = validate_image(state['effectiveWallpaper'])
        if pref['themeMode'] == 'wallpaper':
            previous_analysis = state.get('wallpaperAnalysis')
            stale = (not isinstance(previous_analysis, dict)
                     or previous_analysis.get('algorithmVersion') != ALGORITHM_VERSION
                     or previous_analysis.get('path') != state['effectiveWallpaper']
                     or state.get('wallpaperMtime') != meta['mtime'])
            if stale:
                # CONTRACT: rétablir les mesures manquantes sans inventer une
                # nouvelle application. Le flavor publié reste celui du dernier
                # état validé ; un fichier modifié doit être appliqué explicitement.
                refreshed = analyze_wallpaper(meta)
                if (refreshed['flavor'] == flavor
                        and state.get('wallpaperMtime') == meta['mtime']):
                    state['wallpaperAnalysis'] = refreshed
        alias = safe_alias(meta)
        expected_wallpaper = render_wallpaper(alias)
        previous_theme = GENERATED_THEME.read_bytes() if GENERATED_THEME.exists() else None
        previous_wallpaper = GENERATED.read_bytes() if GENERATED.exists() else None
        repair_theme = previous_theme != expected_theme
        repair_wallpaper = previous_wallpaper != expected_wallpaper
        try:
            if repair_theme:
                atomic_write(GENERATED_THEME, expected_theme)
            if repair_wallpaper:
                atomic_write(GENERATED, expected_wallpaper)
            if repair_theme or repair_wallpaper:
                command('sway', '--validate', '-c', str(SWAY / 'config'))
                command('swaymsg', 'reload')
            if STATE.exists():
                if read_json(STATE) != state:
                    write_json(STATE, state)
            else:
                write_json(STATE, state)
            if read_json(PREFERENCES) != pref:
                write_json(PREFERENCES, pref)
            return state_response(state, pref)
        except Exception:
            restore_file(GENERATED_THEME, previous_theme)
            restore_file(GENERATED, previous_wallpaper)
            if repair_theme or repair_wallpaper:
                command('swaymsg', 'reload')
            raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    sub.add_parser('current')
    sub.add_parser('reconcile')
    sub.add_parser('status')
    sub.add_parser('preferences')
    scan_parser = sub.add_parser('scan')
    scan_parser.add_argument('directory')
    scan_parser.add_argument('--page', type=int, default=0)
    for action in ('validate', 'thumbnail', 'analyze', 'apply', 'set-directory',
                   'set-theme-mode', 'set-manual-flavor'):
        sub.add_parser(action).add_argument('path')
    args = parser.parse_args()
    try:
        if args.action == 'current': result = current()
        elif args.action == 'reconcile': result = reconcile()
        elif args.action == 'status': result = reconcile_state()
        elif args.action == 'preferences': result = preferences()
        elif args.action == 'scan':
            if args.page < 0: raise ValueError('Page invalide')
            result = scan(args.directory, args.page)
        elif args.action == 'validate': result = validate_image(args.path)
        elif args.action == 'thumbnail':
            result = validate_image(args.path)
            result['thumbnail'] = thumbnail(result)
        elif args.action == 'analyze': result = analyze_wallpaper(validate_image(args.path))
        elif args.action == 'apply': result = apply(args.path)
        elif args.action == 'set-theme-mode': result = set_theme_mode(args.path)
        elif args.action == 'set-manual-flavor': result = set_manual_flavor(args.path)
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
