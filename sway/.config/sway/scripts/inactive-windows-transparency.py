#!/usr/bin/python

# This script requires i3ipc-python package (install it from a system package manager
# or pip).
# It makes inactive windows transparent and corrects borders on floating events.
# Use the command line argument -o to control inactive opacity in range 0…1.

import argparse
import json
import os
import signal
import sys
import time
from functools import partial
from pathlib import Path

import i3ipc

STATE = Path(os.environ.get('XDG_STATE_HOME', Path.home() / '.local/state')) / 'labfy-appearance/effective.json'

# INVARIANT: seules les bordures de mosaïque remplacées en flottant sont
# mémorisées, puis oubliées au retour en mosaïque ou à la fermeture.
previous_tiled_borders = {}


def inactive_opacity():
    # CONTRACT: lecture uniquement sur événement IPC ou SIGUSR1 de la
    # transaction ; aucune boucle de sondage ni valeur Sun mémorisée.
    try:
        state = json.loads(STATE.read_text(encoding='utf-8'))
        return '1.0' if state.get('effectiveMode') in ('sun-light', 'sun-dark') else '0.85'
    except (OSError, ValueError):
        return '0.85'


def apply_all(ipc):
    tree = ipc.get_tree()
    opacity = inactive_opacity()
    for window in tree.leaves():
        window.command('opacity ' + ('1.0' if window.focused else opacity))


def on_window(args, ipc, event):
    global focused_set

    # WHY: Sway émet window::floating avant de finir le passage à csd de
    # certaines fenêtres. Attendre uniquement cette transition évite qu'une
    # bordure corrigée aussitôt soit écrasée dans la même opération.
    if event.change == 'floating' and event.container.floating in ('user_on', 'auto_on'):
        time.sleep(0.05)

    # L'arbre courant remplace l'instantané trop précoce de l'événement.
    tree = ipc.get_tree()

    # WHY: for_window ne se rejoue pas sur une transition IPC vers floating.
    # CONTRACT: la bordure serveur ne s'applique qu'au conteneur devenu
    # flottant ; sa décoration précédente revient lors du retour en mosaïque.
    # INVARIANT: une bordure déjà correcte ne déclenche aucune commande, donc
    # aucune réaction répétée à un éventuel événement causé par border.
    if event.change == 'floating':
        window = tree.find_by_id(event.container.id)
        if window is not None and window.floating in ('user_on', 'auto_on'):
            if window.border != 'pixel' or window.current_border_width != 2:
                # L'instantané de l'événement garde la bordure d'entrée,
                # même si l'arbre courant montre déjà csd en flottant.
                previous_tiled_borders[window.id] = (
                    event.container.border, event.container.current_border_width)
                window.command('border pixel 2')
        elif event.container.id in previous_tiled_borders:
            border, width = previous_tiled_borders.pop(event.container.id)
            if border in ('normal', 'pixel') and isinstance(width, int) and 0 <= width <= 1000:
                event.container.command(f'border {border} {width}')
            elif border in ('none', 'csd'):
                event.container.command(f'border {border}')
    elif event.change == 'close':
        previous_tiled_borders.pop(event.container.id, None)

    args.opacity = inactive_opacity()
    focused = tree.find_focused()
    if focused is None:
        return

    focused_workspace = focused.workspace()

    focused.command("opacity " + args.focused)
    focused_set.add(focused.id)

    to_remove = set()
    for window_id in focused_set:
        if window_id == focused.id:
            continue
        window = tree.find_by_id(window_id)
        if window is None:
            to_remove.add(window_id)
        elif args.global_focus or window.workspace() == focused_workspace:
            window.command("opacity " + args.opacity)
            to_remove.add(window_id)

    focused_set -= to_remove

def remove_opacity(ipc, focused_opacity):
    for workspace in ipc.get_tree().workspaces():
        for w in workspace:
            w.command("opacity " + focused_opacity)
    ipc.main_quit()
    sys.exit(0)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="This script allows you to set the transparency of unfocused windows in sway."
    )
    parser.add_argument('--refresh', action='store_true',
                        help='réappliquer immédiatement toutes les fenêtres puis quitter')
    parser.add_argument(
        "--opacity",
        "-o",
        type=str,
        default="0.85",
        help="set inactive opacity value in range 0...1",
    )
    parser.add_argument(
        "--focused",
        "-f",
        type=str,
        default="1.0",
        help="set focused opacity value in range 0...1",
    )
    parser.add_argument(
        "--global-focus",
        "-g",
        action="store_true",
        help="only have one opaque window across all workspaces",
    )
    args = parser.parse_args()

    ipc = i3ipc.Connection()
    if args.refresh:
        apply_all(ipc)
        sys.exit(0)
    focused_set = set()

    args.opacity = inactive_opacity()
    apply_all(ipc)
    focused = ipc.get_tree().find_focused()
    if focused:
        focused_set.add(focused.id)
    for sig in [signal.SIGINT, signal.SIGTERM]:
        signal.signal(sig, lambda signal, frame: remove_opacity(ipc, args.focused))
    ipc.on("window", partial(on_window, args))
    ipc.main()
