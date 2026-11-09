#!/usr/bin/python3
"""Interactive, user-owned full upgrade; --dry-run never executes a package manager."""
import fcntl
import os
from pathlib import Path
import shutil
import subprocess
import sys


def main():
    if sys.argv[1:] not in ([], ["--dry-run"]):
        return 2
    dry = sys.argv[1:] == ["--dry-run"]
    print("Labfy Update Center\n")
    print("Mise à jour complète des dépôts officiels et de l’AUR : yay -Syu --confirm")
    print("Consultez les annonces Arch, les différences des PKGBUILD et les questions de yay.")
    print("Aucune fusion de .pacnew, aucun nettoyage de cache automatique par Labfy.")
    if dry:
        print("\nAPERÇU : aucune installation ne sera exécutée.")
        input("Entrée pour fermer cet aperçu… ")
        return 0
    if not sys.stdin.isatty() or os.geteuid() == 0 or not shutil.which("yay"):
        print("Un terminal utilisateur et yay sont nécessaires.")
        return 1
    if input("\nSaisissez METTRE A JOUR pour continuer : ").strip() != "METTRE A JOUR":
        print("Opération annulée.")
        return 0
    code = 1
    with open(Path(os.environ["XDG_RUNTIME_DIR"]) / "labfy-updates.lock", "w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("Une vérification ou une mise à jour Labfy est déjà en cours. Réessayez ensuite.")
            input("Entrée pour fermer… ")
            return 1
        try:
            # CONTRACT: argv is fixed; no remote text or selected package enters it.
            # --confirm overrides a possible user configuration disabling questions.
            code = subprocess.call(["yay", "-Syu", "--confirm", "--sudoloop=false", "--cleanafter=false", "--useask=false", "--askremovemake",
                                    "--noanswerclean", "--noanswerdiff", "--noansweredit", "--noanswerupgrade"])
        except (OSError, KeyboardInterrupt) as exc:
            print("Opération interrompue :", exc)
        finally:
            # Release before asking the existing service to collect the new state.
            fcntl.flock(lock, fcntl.LOCK_UN)
    print("\nRésultat de yay :", code, "(0 = succès)")
    if code:
        print("Résolvez les erreurs et terminez la mise à jour complète avant toute autre installation.")
    subprocess.run(["systemctl", "--user", "start", "labfy-quickshell-updates.service"], check=False)
    input("\nConsultez le résultat ci-dessus. Entrée pour fermer… ")
    return code


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (EOFError, KeyboardInterrupt):
        raise SystemExit(130)
