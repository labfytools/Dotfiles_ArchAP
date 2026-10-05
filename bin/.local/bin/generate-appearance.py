#!/usr/bin/env python3
"""Générer et appliquer les couleurs Sway depuis la palette Catppuccin unique."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
PALETTE = ROOT / 'quickshell/.config/quickshell/labfy-sway/theme/catppuccin.json'
SWAY = Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config')) / 'sway'
STATE = Path(os.environ.get('XDG_STATE_HOME', Path.home() / '.local/state')) / 'labfy-appearance/effective.json'
ACCENTS = ('rosewater', 'flamingo', 'pink', 'mauve', 'red', 'maroon', 'peach',
           'yellow', 'green', 'teal', 'sky', 'sapphire', 'blue', 'lavender')
HEX = re.compile(r'#[0-9a-fA-F]{6}\Z')


def palette_data():
    data = json.loads(PALETTE.read_text(encoding='utf-8'))
    if set(data) != {'latte', 'frappe', 'macchiato', 'mocha'}:
        raise ValueError('Palette incomplète')
    for colors in data.values():
        if len(colors) != 26 or not all(HEX.fullmatch(v) for v in colors.values()):
            raise ValueError('Palette invalide')
    return data


def render(flavor, accent, profile='default'):
    data = palette_data()
    if flavor not in data:
        raise ValueError('flavor invalide: ' + flavor)
    if accent not in ACCENTS:
        raise ValueError('accent invalide: ' + accent)
    if profile != 'default':
        raise ValueError('profile invalide: ' + profile)
    p = data[flavor]
    # CONTRACT: toutes les valeurs interpolées proviennent de clés bornées ou
    # de chaînes hex validées ; aucune entrée utilisateur ne devient une commande.
    lines = ['# Généré depuis theme/catppuccin.json ; ne pas éditer.']
    lines += [f'set ${name} {value}' for name, value in p.items()]
    lines += [f'set $accent {p[accent]}',
              'set $shadow_active #00000055',
              'set $shadow_inactive #00000035',
              'set $inactive_opacity 0.85']
    return '\n'.join(lines) + '\n'


def atomic_write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.tmp')
    # CONTRACT: le fichier précédent reste intact jusqu'au rename sur le même FS.
    try:
        with open(tmp, 'wb') as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)
        fd = os.open(path.parent, os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    finally:
        tmp.unlink(missing_ok=True)


def checked(args):
    return subprocess.run(args, check=True, capture_output=True, text=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('flavor', choices=('latte', 'frappe', 'macchiato', 'mocha'))
    parser.add_argument('--accent', default='lavender', choices=ACCENTS)
    parser.add_argument('--profile', default='default')
    parser.add_argument('--output', type=Path, default=SWAY / 'generated/theme.conf')
    parser.add_argument('--apply', action='store_true', help='valider puis recharger Sway et QuickShell')
    args = parser.parse_args()
    if args.apply and args.output != SWAY / 'generated/theme.conf':
        parser.error('--apply exige la sortie runtime par défaut')
    try:
        # CONTRACT: les applications 17D empruntent le verrou et la publication
        # uniques du gestionnaire Appearance ; ce CLI garde le rendu hors ligne.
        if args.apply:
            if args.accent != 'lavender' or args.profile != 'default':
                raise ValueError('17D applique uniquement Lavender avec le profil default')
            checked([sys.executable, str(Path(__file__).with_name('wallpaper-manager.py')),
                     'set-manual-flavor', args.flavor])
            print(f'{args.flavor}/lavender: {args.output}')
            return 0
        content = render(args.flavor, args.accent, args.profile).encode('utf-8')
        atomic_write(args.output, content)
        print(f'{args.flavor}/{args.accent}: {args.output}')
    except (OSError, ValueError, subprocess.CalledProcessError, RuntimeError) as exc:
        print(f'Erreur : {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
