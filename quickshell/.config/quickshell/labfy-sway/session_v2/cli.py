"""CLI backend ; pas d'appel logout/reboot, pas d'intégration QuickShell V1."""
import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path
import sys
import uuid
from .errors import Failure, require
from .storage import paths, read, atomic, lock, private_dir
from .schema import validate
from .checkpoint import Store
from .ipc import Sway
from .applications import Catalog
from .firefox_identity import FirefoxProvider
from .snapshot import capture
from .layout import compile_plan
from .executor import Executor
from .observability import validate as validate_report
from .startup import acknowledge


def migration(path):
    value = read(path)
    require(type(value) is dict, "V1_FORMAT_UNRECOGNIZED")
    require(value.get("schema") == "labfy.sway.session-snapshot" and type(value.get("version")) is int and value["version"] == 1, "V1_FORMAT_UNRECOGNIZED")
    # Analyse conservatrice, jamais de conversion ni copie des identités runtime.
    windows = value.get("windows", [])
    require(type(windows) is list and len(windows) <= 256, "V1_FORMAT_UNRECOGNIZED")
    require(all(type(w) is dict for w in windows), "V1_FORMAT_UNRECOGNIZED")
    require(all(type(w.get("scratchpad", {})) is dict for w in windows), "V1_FORMAT_UNRECOGNIZED")
    known = all(w.get("app_id") in ("kitty", "firefox", "org.mozilla.firefox") for w in windows)
    unsupported = any(w.get("fullscreen_mode") or w.get("scratchpad", {}).get("member") for w in windows)
    classification = "unsupported" if not known or unsupported or not windows else "needs exact identity" if any(w.get("app_id") in ("firefox", "org.mozilla.firefox") for w in windows) else "migratable"
    return {"classification": classification, "windows": len(windows), "migratable": classification == "migratable",
            "reason": "READ_ONLY_ANALYSIS_NO_CONVERSION"}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Backend de restauration de session V2")
    parser.add_argument("command", choices=("capture", "save", "list", "show", "delete", "plan", "apply", "checkpoint-last", "startup-status", "acknowledge-startup", "apply-last", "restore-status", "analyze-v1-migration"))
    parser.add_argument("name", nargs="?")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--stdout", action="store_true")
    parser.add_argument("--choice", choices=("new", "restored"))
    parser.add_argument("--transaction-id")
    parser.add_argument("--reason", choices=("logout", "reboot", "poweroff"), default="logout")
    parser.add_argument("--socket", default=os.environ.get("SWAYSOCK", ""))
    parser.add_argument("--anchor-binary", default=str(Path(__file__).parent / "libexec/labfy-v2-anchor"))
    args = parser.parse_args(argv)
    try:
        if args.command in ("capture", "save", "delete", "apply", "checkpoint-last", "apply-last", "acknowledge-startup"):
            require(args.execute, "EXECUTE_REQUIRED")
        state, runtime = paths()
        store = Store(state)
        command = args.command
        if command == "list": result = {"sessions": store.list()}
        elif command == "show": result = store.load(args.name)
        elif command == "delete": store.delete(args.name); result = {"status": "deleted"}
        elif command == "restore-status":
            try: result = read(runtime / "session-v2-restore-attempt.json", validate_report)
            except FileNotFoundError: result = {"status": "idle", "reason": "NO_RESTORE_ATTEMPT"}
        elif command == "analyze-v1-migration": result = migration(args.name)
        elif command == "plan": result = {"operations": [asdict(x) for x in compile_plan(store.load(args.name), "0" * 32)]}
        else:
            sway = Sway(args.socket)
            catalog = Catalog()
            provider = FirefoxProvider(sway, runtime)
            if command == "acknowledge-startup":
                result = acknowledge(runtime, sway.session, args.choice, args.transaction_id)
            elif command == "startup-status":
                try: last = store.last()
                except FileNotFoundError: last = None
                if last is None:
                    result = {"eligible": False, "claimed": False}
                else:
                    marker = private_dir(runtime / "session-v2") / "startup.json"
                    with lock(marker.parent):
                        seen = read(marker) if marker.exists() else {}
                        eligible = last["metadata"]["sway_session"] != sway.session and seen.get("session") != sway.session
                        if args.execute and eligible: atomic(marker, {"session": sway.session})
                    result = {"eligible": eligible, "claimed": bool(args.execute and eligible)}
                    result.update(windows=len(last['window_slots']), workspaces=len(last['workspaces']))
            elif command in ("capture", "save", "checkpoint-last"):
                with lock(private_dir(runtime / "session-v2")):
                    data = capture(sway, catalog, provider, args.reason if command == "checkpoint-last" else "manual")
                    if command == "save": store.save(args.name, data)
                    elif command == "checkpoint-last": store.checkpoint(data)
                    result = data if command == "capture" else {"status": "saved"}
            else:
                data = store.last() if command == "apply-last" else store.load(args.name)
                result = Executor(sway, catalog, provider, runtime, args.anchor_binary).apply(data, execute=True)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except Failure as exc:
        print(json.dumps({"status": "failed", "reason": exc.code}))
        return 2
    except (OSError, TypeError, ValueError):
        print(json.dumps({"status": "failed", "reason": "BACKEND_IO_OR_FORMAT_ERROR"}))
        return 2


if __name__ == "__main__": sys.exit(main())
