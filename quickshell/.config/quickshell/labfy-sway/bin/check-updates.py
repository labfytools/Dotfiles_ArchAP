#!/usr/bin/python3
"""Publie un instantané Arch/AUR borné pour la barre QuickShell."""

import datetime
import json
import os
import pathlib
import subprocess
import sys
import tempfile


def count(command):
    # CONTRACT: aucune mise à jour n'est appliquée ; chaque vérification est bornée.
    result = subprocess.run(command, capture_output=True, text=True, timeout=120, check=False)
    # CONTRACT: checkupdates utilise le code 2 pour « aucune mise à jour » ;
    # INVARIANT: une sortie inattendue garde le chemin d'erreur existant.
    if command[0] == "checkupdates" and result.returncode == 2 and not result.stdout.strip() and not result.stderr.strip():
        return 0
    # yay -Qua retourne 1 avec stdout/stderr vides quand aucune entrée AUR n'existe.
    if command[0] == "yay" and result.returncode == 1 and not result.stdout.strip() and not result.stderr.strip():
        return 0
    if result.returncode != 0:
        message = (result.stderr or result.stdout).strip().splitlines()
        raise RuntimeError((message[-1] if message else f"{command[0]} : code {result.returncode}")[:160])
    return len([line for line in result.stdout.splitlines() if line.strip()])


def main():
    runtime = pathlib.Path(os.environ["XDG_RUNTIME_DIR"])
    destination = runtime / "labfy-quickshell-updates.json"
    state = {"repoUpdates": 0, "aurUpdates": 0, "totalUpdates": 0,
             "lastCheck": datetime.datetime.now().astimezone().isoformat(timespec="seconds"), "error": ""}
    try:
        state["repoUpdates"] = count(["checkupdates"])
        state["aurUpdates"] = count(["yay", "-Qua"])
        state["totalUpdates"] = state["repoUpdates"] + state["aurUpdates"]
    except (OSError, subprocess.TimeoutExpired, RuntimeError) as exc:
        # INVARIANT: une vérification incomplète ne peut jamais publier un faux zéro.
        state["error"] = str(exc).splitlines()[0][:160]
        print(state["error"], file=sys.stderr)
    fd, temporary = tempfile.mkstemp(prefix="labfy-updates-", dir=runtime)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(state, stream, ensure_ascii=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return 1 if state["error"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
