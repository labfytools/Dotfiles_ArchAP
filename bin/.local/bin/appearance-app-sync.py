#!/usr/bin/env python3
"""Distribuer l'état effectif Appearance aux applications du bureau."""
import argparse
import configparser
import fcntl
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[3]
PALETTE = ROOT / 'quickshell/.config/quickshell/labfy-sway/theme/catppuccin.json'
CONFIG = Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config'))
STATE_DIR = Path(os.environ.get('XDG_STATE_HOME', Path.home() / '.local/state')) / 'labfy-appearance'
STATE = STATE_DIR / 'effective.json'
RESULT = STATE_DIR / 'last-applied.json'
FLAVORS = ('latte', 'frappe', 'macchiato', 'mocha')
ACCENTS = ('rosewater', 'flamingo', 'pink', 'mauve', 'red', 'maroon', 'peach',
           'yellow', 'green', 'teal', 'sky', 'sapphire', 'blue', 'lavender')
COLOR_KEYS = set(ACCENTS) | {'text', 'subtext1', 'subtext0', 'overlay2', 'overlay1',
                            'overlay0', 'surface2', 'surface1', 'surface0',
                            'base', 'mantle', 'crust'}
HEX = re.compile(r'#[0-9a-fA-F]{6}\Z')


def atomic_write(path, data):
    """CONTRACT: un ancien fichier valide survit à tout échec avant os.replace."""
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


def read_effective(path=STATE):
    raw = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(raw, dict):
        raise ValueError('effective.json doit être un objet')
    keys = ('effectiveFlavor', 'effectiveAccent', 'effectiveDark',
            'effectiveHighContrast', 'effectiveMode', 'revision')
    value = {key: raw[key] for key in keys}
    flavor, accent = value['effectiveFlavor'], value['effectiveAccent']
    if flavor not in FLAVORS or accent not in ACCENTS:
        raise ValueError('flavor/accent invalide')
    if type(value['effectiveDark']) is not bool or type(value['effectiveHighContrast']) is not bool:
        raise ValueError('booléen effectif invalide')
    if type(value['revision']) is not int or value['revision'] < 0:
        raise ValueError('revision invalide')
    mode = value['effectiveMode']
    if mode not in ('normal', 'sun-light', 'sun-dark'):
        raise ValueError('mode invalide')
    if value['effectiveDark'] != (flavor != 'latte'):
        raise ValueError('dark/flavor incohérents')
    if value['effectiveHighContrast'] != (mode != 'normal'):
        raise ValueError('contrast/mode incohérents')
    if mode == 'sun-light' and flavor != 'latte' or mode == 'sun-dark' and flavor == 'latte':
        raise ValueError('flavor/mode incohérents')
    return value


def read_palette(path=PALETTE):
    raw = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(raw, dict) or set(raw) != set(FLAVORS) or any(
            not isinstance(p, dict) or set(p) != COLOR_KEYS or
            not all(isinstance(c, str) and HEX.fullmatch(c) for c in p.values())
            for p in raw.values()):
        raise ValueError('palette Catppuccin invalide')
    return raw


def run(*args):
    return subprocess.run(args, check=True, capture_output=True, text=True, timeout=5)


def gtk_adapter(state, colors):
    flavor = state['effectiveFlavor']
    dark = state['effectiveDark']
    # WHY: seul Mocha est installé localement ; inventer les autres noms donne
    # un fallback GTK imprévisible. Adwaita respecte au moins Light/Dark.
    name = 'Catppuccin-Mocha' if flavor == 'mocha' else 'Adwaita'
    if name == 'Catppuccin-Mocha' and not (Path.home() / '.themes/Catppuccin-Mocha/gtk-3.0').is_dir():
        name = 'Adwaita'
    scheme = 'prefer-dark' if dark else 'prefer-light'
    run('gsettings', 'set', 'org.gnome.desktop.interface', 'gtk-theme', name)
    run('gsettings', 'set', 'org.gnome.desktop.interface', 'color-scheme', scheme)
    return {'status': 'ok', 'theme': name, 'colorScheme': scheme,
            'accent': 'rosewater (installé)' if name == 'Catppuccin-Mocha' else 'default',
            'highContrast': 'unsupported' if state['effectiveHighContrast'] else 'off'}


def qt_palette(p, accent):
    # CONTRACT: Qt ColorScheme contient 22 rôles QColor, en ordre documenté par
    # les fichiers qt5ct/qt6ct existants ; alpha explicite, aucune struct native.
    roles = ('text', 'surface1', 'surface2', 'surface0', 'crust', 'mantle',
             'text', 'text', 'text', 'base', 'mantle', 'crust', accent,
             'crust', 'blue', accent, 'mantle', 'text', 'base', 'text',
             'overlay0', accent)
    active = ['#ff' + p[r][1:] for r in roles]
    inactive = active.copy()
    disabled = active.copy()
    for index in (0, 6, 8, 13, 14, 15):
        inactive[index] = '#ff' + p['subtext0'][1:]
        disabled[index] = '#ff' + p['overlay0'][1:]
    return ('[ColorScheme]\n' +
            'active_colors=' + ', '.join(active) + '\n' +
            'inactive_colors=' + ', '.join(inactive) + '\n' +
            'disabled_colors=' + ', '.join(disabled) + '\n').encode()


def qt_adapter(state, colors):
    # WHY: les deux versions doivent pointer sur des palettes cohérentes.
    # Les instances Qt déjà ouvertes peuvent garder la palette chargée.
    for version in ('qt5ct', 'qt6ct'):
        directory = CONFIG / version
        settings = directory / (version + '.conf')
        target = directory / 'colors/labfy-appearance.conf'
        if not settings.is_file():
            raise FileNotFoundError(settings)
        content = settings.read_text(encoding='utf-8')
        updated, count = re.subn(r'(?m)^color_scheme_path=.*$',
                                  'color_scheme_path=' + str(target), content)
        if count != 1:
            raise ValueError('color_scheme_path manquant ou dupliqué: ' + str(settings))
        atomic_write(target, qt_palette(colors[state['effectiveFlavor']], state['effectiveAccent']))
        if updated != content:
            atomic_write(settings, updated.encode())
    return {'status': 'ok', 'flavor': state['effectiveFlavor'], 'live': 'new-window'}


def kitty_theme(p, accent, opaque):
    def line(key, value):
        return key + ' ' + value
    lines = ['# Généré depuis theme/catppuccin.json ; ne pas éditer.',
             line('foreground', p['text']), line('background', p['base']),
             line('selection_foreground', p['base']),
             line('selection_background', p['rosewater']),
             line('cursor', p['rosewater']), line('cursor_text_color', p['base']),
             line('active_border_color', p[accent]),
             line('inactive_border_color', p['overlay0']),
             line('active_tab_foreground', p['crust']),
             line('active_tab_background', p[accent]),
             line('inactive_tab_foreground', p['text']),
             line('inactive_tab_background', p['mantle']),
             line('tab_bar_background', p['crust']),
             line('background_opacity', '1.0' if opaque else '1.0')]
    # CONTRACT: l'opacité normale était la valeur implicite Kitty 1.0.
    ansi = ('surface1', 'red', 'green', 'yellow', 'blue', 'pink', 'teal', 'subtext1',
            'surface2', 'red', 'green', 'yellow', 'blue', 'pink', 'teal', 'text')
    lines.extend(line('color' + str(i), p[name]) for i, name in enumerate(ansi))
    return ('\n'.join(lines) + '\n').encode()


def kitty_adapter(state, colors):
    path = CONFIG / 'kitty/generated-appearance.conf'
    config = CONFIG / 'kitty/kitty.conf'
    if 'include generated-appearance.conf' not in config.read_text(encoding='utf-8'):
        raise ValueError('include Kitty manquant')
    atomic_write(path, kitty_theme(colors[state['effectiveFlavor']], state['effectiveAccent'],
                                   state['effectiveHighContrast']))
    # WHY: l'instance actuelle surveille kitty.conf, mais pas nécessairement
    # l'include créé après son lancement. Kitty 0.49.2 documente SIGUSR1 pour
    # recharger la configuration sans exposer de socket remote-control.
    signalled = 0
    for entry in os.scandir('/proc'):
        if not entry.name.isdecimal():
            continue
        try:
            if entry.stat().st_uid == os.getuid() and os.readlink(entry.path + '/exe') == '/usr/bin/kitty':
                os.kill(int(entry.name), signal.SIGUSR1)
                signalled += 1
        except (FileNotFoundError, PermissionError, ProcessLookupError):
            continue
    return {'status': 'ok', 'reload': 'SIGUSR1', 'instances': signalled, 'opacity': '1.0'}


def nvim_adapter(state, colors):
    # CONTRACT: Neovim lit effective.json directement au démarrage et via fs_event.
    return {'status': 'ok', 'contract': 'effective.json', 'revision': state['revision']}


def firefox_adapter(state, colors):
    # CONTRACT: lecture seule de deux préférences ; jamais de modification du
    # profil Firefox ouvert, de prefs.js ou des bases de données.
    root = Path.home() / '.mozilla/firefox'
    profiles = configparser.ConfigParser()
    if not profiles.read(root / 'profiles.ini'):
        return {'status': 'unsupported', 'reason': 'profiles.ini absent'}
    install = next((s for s in profiles.sections() if s.startswith('Install')), None)
    if not install:
        return {'status': 'unsupported', 'reason': 'profil actif indéterminé'}
    profile = (root / profiles[install]['Default']).resolve()
    if not profile.is_relative_to(root.resolve()):
        raise ValueError('chemin de profil Firefox invalide')
    prefs = profile / 'prefs.js'
    if prefs.stat().st_size > 4_000_000:
        raise ValueError('prefs.js trop volumineux pour audit borné')
    content = prefs.read_text(encoding='utf-8')
    theme_match = re.search(r'^user_pref\("extensions.activeThemeID", "([^"\\]+)"\);$', content, re.M)
    override_match = re.search(r'^user_pref\("layout.css.prefers-color-scheme.content-override", (\d+)\);$', content, re.M)
    theme = theme_match.group(1) if theme_match else 'indéterminé'
    override = int(override_match.group(1)) if override_match else 2
    # WHY: Proton 1.1 fournit `theme` et `dark_theme` dans son manifeste ;
    # le test Firefox ouvert a confirmé ses deux palettes avec le portail.
    # CONTRACT: seuls les thèmes audités suivent le système ; l'override Auto
    # reste obligatoire et cet adaptateur ne fait aucune écriture de profil.
    if theme in ('default-theme@mozilla.org', 'proton-theme@mozilla.org') and override == 2:
        return {'status': 'ok', 'integration': 'system', 'lightDark': 'supported',
                'profileWrite': False, 'theme': theme,
                'colorScheme': 'dark' if state['effectiveDark'] else 'light'}
    return {'status': 'unsupported', 'theme': theme, 'contentOverride': override,
            'reason': 'migration Firefox vers thème System et contenu Auto nécessaire'}


ADAPTERS = {'gtk': gtk_adapter, 'qt': qt_adapter, 'kitty': kitty_adapter,
            'nvim': nvim_adapter, 'firefox': firefox_adapter}


def reconcile(state_path=STATE, result_path=RESULT, palette_path=PALETTE):
    result_path.parent.mkdir(parents=True, exist_ok=True)
    with open(result_path.parent / 'app-sync.lock', 'a+b') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        # INVARIANT: lecture sous verrou après tout prédécesseur ; une révision
        # arrivée pendant l'application est relue avant de publier le résultat.
        colors = read_palette(palette_path)
        while True:
            state = read_effective(state_path)
            outcomes = {}
            for name, adapter in ADAPTERS.items():
                try:
                    outcomes[name] = adapter(state, colors)
                except (OSError, ValueError, KeyError, subprocess.CalledProcessError,
                        subprocess.TimeoutExpired) as exc:
                    outcomes[name] = {'status': 'error', 'reason': str(exc)[:300]}
            if read_effective(state_path) != state:
                continue
            result = {'revision': state['revision'], 'timestamp': int(time.time()),
                      'adapters': outcomes}
            atomic_write(result_path, (json.dumps(result, ensure_ascii=False) + '\n').encode())
            if read_effective(state_path) == state:
                return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('reconcile',))
    parser.parse_args()
    try:
        result = reconcile()
        print(json.dumps(result, ensure_ascii=False))
        return 1 if any(v['status'] == 'error' for v in result['adapters'].values()) else 0
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print('Erreur Appearance : ' + str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
