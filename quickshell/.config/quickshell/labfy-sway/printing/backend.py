#!/usr/bin/env python3
"""Lecture ponctuelle de CUPS pour le panneau QuickShell, sans état durable."""

import json
import re
import subprocess
import sys

try:
    import cups
except ImportError:
    cups = None


# CONTRACT: schéma public fixe entre le processus ponctuel et QuickShell.
# Les attributs IPP ne sont jamais sérialisés directement ni persistés.
SCHEMA = "labfy.printing"
VERSION = 1
JOB_ID = re.compile(r"[1-9][0-9]*\Z", re.ASCII)
PRINTER_STATES = {3: "ready", 4: "printing", 5: "stopped"}
JOB_STATES = {3: "pending", 4: "held", 5: "processing", 6: "stopped"}


def printer_state(attributes):
    """CONTRACT: l'état IPP 5 et les raisons d'erreur priment sur « prête »."""
    state = attributes.get("printer-state")
    reasons = attributes.get("printer-state-reasons") or []
    if isinstance(reasons, str):
        reasons = [reasons]
    if any("offline" in reason or "unreachable" in reason for reason in reasons):
        return "offline"
    if any("error" in reason for reason in reasons):
        return "error"
    if state == 5:
        return "stopped"
    if state == 4:
        return "printing"
    if state == 3:
        return "ready"
    return "unknown"


def job_state(attributes):
    return JOB_STATES.get(attributes.get("job-state"), "unknown")


def snapshot(connection):
    """WHY: pycups fournit les attributs IPP sans dépendre de la locale CLI."""
    default = connection.getDefault()
    printers = connection.getPrinters()
    jobs = connection.getJobs(which_jobs="not-completed", my_jobs=False)
    result = {
        "schema": SCHEMA, "version": VERSION, "scheduler": True,
        "default_printer": default if default in printers else None,
        "printers": [], "jobs": [],
    }
    for name, attributes in sorted(printers.items()):
        result["printers"].append({
            "name": name,
            "state": printer_state(attributes),
            "default": name == result["default_printer"],
        })
    for identifier, attributes in sorted(jobs.items(), key=lambda pair: int(pair[0])):
        # CONTRACT: les titres restent dans la réponse éphémère à QuickShell.
        # Aucun journal, notification ou fichier de snapshot ne les conserve.
        result["jobs"].append({
            "id": int(identifier),
            "document": str(attributes.get("job-name") or "Document sans nom"),
            "printer": str(attributes.get("job-printer-uri", "")).rsplit("/", 1)[-1],
            "state": job_state(attributes),
        })
    return result


def unavailable():
    return {"schema": SCHEMA, "version": VERSION, "scheduler": False,
            "default_printer": None, "printers": [], "jobs": []}


def validate_job_id(value):
    # CONTRACT: seul un identifiant CUPS décimal positif peut atteindre cancel.
    if not JOB_ID.fullmatch(value) or int(value) > 2147483647:
        raise ValueError("Identifiant de travail invalide")
    return value


def cancel_job(value, runner=subprocess.run):
    identifier = validate_job_id(value)
    completed = runner(["/usr/bin/cancel", identifier], capture_output=True,
                       text=True, timeout=8, check=False)
    return completed.returncode == 0


def main(argv):
    if len(argv) == 1 and argv[0] == "status":
        try:
            value = snapshot(cups.Connection()) if cups else unavailable()
        except (RuntimeError, OSError, AttributeError,
                cups.IPPError if cups else RuntimeError):
            value = unavailable()
        print(json.dumps(value, ensure_ascii=False))
        return 0
    if len(argv) == 2 and argv[0] == "cancel":
        try:
            success = cancel_job(argv[1])
        except (ValueError, OSError, subprocess.TimeoutExpired):
            success = False
        # CONTRACT: ne jamais renvoyer stderr de CUPS : il peut contenir un titre.
        print(json.dumps({"ok": success, "error": "" if success
                          else "Annulation impossible"}, ensure_ascii=False))
        return 0 if success else 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
