#!/usr/bin/python

# This script requires i3ipc-python package (install it from a system package manager
# or pip).
# It makes inactive windows transparent. Use `transparency_val` variable to control
# transparency strength in range of 0…1 or use the command line argument -o.

import argparse
import json
import os
import signal
import sys
from functools import partial
from pathlib import Path

import i3ipc

STATE = Path(os.environ.get('XDG_STATE_HOME', Path.home() / '.local/state')) / 'labfy-appearance/effective.json'


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

    # To get the workspace for a container, we need to have received its
    # parents, so fetch the whole tree
    tree = ipc.get_tree()

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
