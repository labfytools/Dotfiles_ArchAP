#!/usr/bin/env python3
"""Source bornée des cartes Sway et des captures de sorties visibles."""

import argparse
import hashlib
import json
import os
import fnmatch
import stat
import signal
import fcntl
import resource
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time


# CONTRACT: local operational bounds, never a bound on the Sway inventory.
MAX_CACHE_FILES = 256
MAX_CACHE_BYTES = 32 * 1024 * 1024
MAX_IMAGE_BYTES = 4 * 1024 * 1024
MAX_BATCH = 4
CAPTURE_SECONDS = 2
_cache_fd = None
_cache_identity = None
_cache_public = None
_deadline = None


def lock_capture_guard_active():
    # WHY: malformed/inaccessible guards fail closed; absence means unlocked.
    runtime = os.environ.get("XDG_RUNTIME_DIR")
    if not runtime:
        return True
    try:
        fd = os.open(Path(runtime) / "labfy-lock.capture-guard", os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd, "rb") as stream:
            return stream.read(32) != b"released\n"
    except FileNotFoundError:
        return False
    except OSError:
        return True


def lock_revision():
    try:
        info = (Path(os.environ["XDG_RUNTIME_DIR"]) / "labfy-lock.capture-guard").lstat()
        return [info.st_ino, info.st_mtime_ns, info.st_size]
    except FileNotFoundError:
        return []


def sway(kind):
    remaining = 5 if _deadline is None else min(5, _deadline - time.monotonic())
    if remaining <= 0:
        raise RuntimeError("Budget capture expiré")
    result = subprocess.run(["swaymsg", "-t", kind, "-r"], capture_output=True,
                            text=True, timeout=remaining, check=True)
    return json.loads(result.stdout)


def cache_dir():
    global _cache_fd, _cache_identity, _cache_public
    # CONTRACT: no /tmp fallback. Pin the directory inode so replacements and
    # symlinks cannot redirect reads, grim output, or cleanup outside this cache.
    runtime = os.environ.get("XDG_RUNTIME_DIR")
    if not runtime or not Path(runtime).is_absolute():
        raise RuntimeError("Runtime privé indisponible")
    base = Path(runtime)
    info = base.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise RuntimeError("Runtime non privé")
    parent = os.open(base, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        info = os.fstat(parent)
        if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
            raise RuntimeError("Runtime non privé")
        try:
            os.mkdir("labfy-workspace-overview", 0o700, dir_fd=parent)
        except FileExistsError:
            pass
        fd = os.open("labfy-workspace-overview", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
    finally:
        os.close(parent)
    info = os.fstat(fd)
    if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
        os.close(fd)
        raise RuntimeError("Cache non privé")
    identity = (info.st_dev, info.st_ino)
    if _cache_identity == identity and _cache_fd is not None:
        os.close(fd)
    else:
        if _cache_fd is not None:
            os.close(_cache_fd)
        _cache_fd, _cache_identity = fd, identity
    _cache_public = base / "labfy-workspace-overview"
    return Path(f"/proc/{os.getpid()}/fd/{_cache_fd}")


def image_url(path):
    return (_cache_public / path.name).as_uri()


def private_file(path, limit):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    info = os.fstat(fd)
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1 or info.st_size > limit):
        os.close(fd)
        raise ValueError("Fichier de cache non privé")
    return os.fdopen(fd, "rb"), info


def policy():
    # CONTRACT: missing policy enables per-window captures. Invalid policy
    # disables them. Rules match app_id or XWayland class, never window titles.
    path = Path(os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")) / "labfy-sway/overview-capture.json"
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid():
                raise ValueError()
            raw = stream.read(16385)
        if len(raw) > 16384:
            raise ValueError()
        data = json.loads(raw)
        rules = data.get("excludeApps", [])
        if (not isinstance(data.get("enabled", True), bool) or not isinstance(rules, list)
                or len(rules) > 64 or any(not isinstance(r, str) or len(r) > 200 for r in rules)):
            raise ValueError()
        return {"enabled": data.get("enabled", True), "excludeApps": rules}
    except FileNotFoundError:
        return {"enabled": True, "excludeApps": []}
    except (OSError, ValueError, TypeError, AttributeError):
        return {"enabled": False, "excludeApps": []}


def excluded(window, rules):
    return not rules["enabled"] or any(fnmatch.fnmatchcase(window.get("app", ""), rule) for rule in rules["excludeApps"])


def purge():
    # INVARIANT: unlink only cache-owned names, without following symlinks.
    for path in cache_dir().iterdir():
        if re.fullmatch(r"(?:window-[0-9]+|[A-Za-z0-9_.-]+-workspace-[0-9]+|tmp[A-Za-z0-9_-]+)\.(?:jpg|json)", path.name):
            if not stat.S_ISDIR(path.lstat().st_mode):
                path.unlink(missing_ok=True)
    return {"ok": True}


def enforce_quota():
    entries = []
    for path in cache_dir().iterdir():
        if not re.fullmatch(r"(?:window-[0-9]+|[A-Za-z0-9_.-]+-workspace-[0-9]+|tmp[A-Za-z0-9_-]+)\.(?:jpg|json)", path.name):
            continue
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1:
            if not stat.S_ISDIR(info.st_mode):
                path.unlink(missing_ok=True)
            continue
        entries.append((info.st_mtime_ns, path, info.st_size))
    total = sum(item[2] for item in entries)
    count = len(entries)
    for _, path, size in sorted(entries):
        if count <= MAX_CACHE_FILES and total <= MAX_CACHE_BYTES:
            break
        path.unlink(missing_ok=True)
        count -= 1
        total -= size


def overview_open():
    return any(surface.get("namespace") == "labfy-workspace-overview"
               for output in sway("get_outputs") if output.get("active")
               for surface in output.get("layer_shell_surfaces") or [])


def snapshot_path(output, number):
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", output)
    return cache_dir() / f"{safe}-workspace-{number}.jpg"


def snapshot_metadata_path(output, number):
    return snapshot_path(output, number).with_suffix(".json")


def window_preview_path(con_id):
    return cache_dir() / f"window-{con_id}.jpg"


def window_preview_metadata_path(con_id):
    return window_preview_path(con_id).with_suffix(".json")


def valid_window_preview(con_id, foreign_id):
    # CONTRACT: le con_id donne l'identité Sway, l'identifiant foreign toplevel
    # est celui attendu par grim -T. Leur égalité n'est jamais supposée.
    if not isinstance(foreign_id, str) or not re.fullmatch(r"[0-9a-f]{32}", foreign_id):
        return None
    path = window_preview_path(con_id)
    metadata_path = window_preview_metadata_path(con_id)
    try:
        image, image_stat = private_file(path, MAX_IMAGE_BYTES)
        image.close()
        if image_stat.st_size == 0:
            return None
        stream, _ = private_file(metadata_path, 2048)
        with stream:
            metadata = json.load(stream)
        if (metadata.get("version") != 1 or metadata.get("conId") != con_id
                or metadata.get("foreignId") != foreign_id
                or metadata.get("imageMtimeNs") != image_stat.st_mtime_ns
                or metadata.get("lockRevision") != lock_revision()
                or not isinstance(metadata.get("capturedNs"), int)):
            return None
        return image_url(path), str(metadata["capturedNs"])
    except (OSError, ValueError, AttributeError, TypeError, json.JSONDecodeError):
        return None


def prune_window_previews(live_ids):
    # INVARIANT: un fichier de fenêtre fermée ne peut ni devenir une fenêtre
    # fantôme ni croître indéfiniment dans le cache de la session.
    for path in cache_dir().glob("window-*.*"):
        match = re.fullmatch(r"window-([0-9]+)\.(?:jpg|json)", path.name)
        if match and int(match.group(1)) not in live_ids:
            path.unlink(missing_ok=True)
    # WHY: une interruption brutale peut laisser un JPEG temporaire. Une
    # période de grâce protège les captures encore en cours dans un autre helper.
    cutoff = time.time() - 600
    for path in cache_dir().glob("tmp*.*"):
        try:
            if path.suffix in (".jpg", ".json") and path.lstat().st_mtime < cutoff:
                path.unlink(missing_ok=True)
        except OSError:
            pass


def structure_revision(node, workspace, output_rect):
    # CONTRACT: seuls identité, hiérarchie, ordre, disposition et géométrie
    # rendent un JPEG incompatible. Un titre ou un focus ne le font pas.
    def geometry(item):
        rect = item.get("rect") or {}
        return [rect.get(key) for key in ("x", "y", "width", "height")]

    def structure(item):
        return [item.get("type"), item.get("id"), item.get("layout"),
                item.get("floating"), geometry(item),
                [structure(child) for child in item.get("nodes") or []],
                [structure(child) for child in item.get("floating_nodes") or []]]

    value = [workspace["id"], workspace["num"], workspace.get("output"),
             geometry({"rect": output_rect}), structure(node)]
    encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def forget_snapshot(output, number):
    # INVARIANT: un workspace vide ne garde pas une ancienne image susceptible
    # de réapparaître après une autre transition.
    snapshot_metadata_path(output, number).unlink(missing_ok=True)
    snapshot_path(output, number).unlink(missing_ok=True)


def forget_other_outputs(number, output):
    # WHY: un workspace supprimé ou déplacé de sortie n'est plus atteignable
    # par son ancien chemin de cache ; retirer uniquement ses anciens fichiers.
    keep = {snapshot_path(output, number), snapshot_metadata_path(output, number)} if output else set()
    for suffix in ("jpg", "json"):
        for path in cache_dir().glob(f"*-workspace-{number}.{suffix}"):
            if path not in keep:
                path.unlink(missing_ok=True)


def valid_snapshot(output, number, workspace_id, revision):
    path = snapshot_path(output, number)
    metadata_path = snapshot_metadata_path(output, number)
    try:
        image, image_stat = private_file(path, MAX_IMAGE_BYTES)
        image.close()
        if image_stat.st_size == 0:
            return None
        stream, _ = private_file(metadata_path, 2048)
        with stream:
            metadata = json.load(stream)
        if (metadata.get("version") != 1 or metadata.get("output") != output
                or metadata.get("number") != number
                or metadata.get("workspaceId") != workspace_id
                or metadata.get("revision") != revision
                or metadata.get("imageMtimeNs") != image_stat.st_mtime_ns
                or metadata.get("lockRevision") != lock_revision()
                or not isinstance(metadata.get("capturedNs"), int)):
            return None
        return image_url(path), str(metadata["capturedNs"])
    except (OSError, ValueError, AttributeError, TypeError, json.JSONDecodeError):
        return None


def windows_in(node):
    found = []

    def visit(item, floating=False):
        app = item.get("app_id") or (item.get("window_properties") or {}).get("class")
        # SwayFX publie une fenêtre flottante directement comme floating_con.
        # Son wrapper possède le vrai con_id, app_id et rect ; l'ignorer ferait
        # disparaître précisément les fenêtres flottantes de l'Overview.
        if item.get("type") in ("con", "floating_con") and app:
            rect = item.get("rect") or {}
            if all(isinstance(rect.get(key), int) for key in ("x", "y", "width", "height")):
                found.append({"id": item["id"], "foreignId": item.get("foreign_toplevel_identifier") or "",
                              "title": item.get("name") or app,
                              "app": app, "rect": rect, "focused": item.get("focused") is True,
                              "floating": floating or item.get("floating") in ("user_on", "auto_on"),
                              "layout": item.get("layout") or ""})
        for child in item.get("nodes") or []:
            visit(child, floating)
        for child in item.get("floating_nodes") or []:
            visit(child, True)

    visit(node)
    return found


def state():
    rules = policy()
    cache_ok = True
    try:
        if lock_capture_guard_active() or not rules["enabled"]:
            purge()
        enforce_quota()
    except (OSError, ValueError, RuntimeError):
        # CONTRACT: an unsafe/unavailable cache disables images, never IPC
        # navigation. Do not repair or traverse a suspicious directory.
        cache_ok = False
    tree = sway("get_tree")
    workspaces = sway("get_workspaces")
    outputs = sway("get_outputs")
    by_number = {item["num"]: item for item in workspaces if item.get("num") in range(1, 11)}
    output_info = {item["name"]: item for item in outputs if item.get("active")}
    overlay_outputs = [item["name"] for item in outputs if item.get("active")
                       and any(surface.get("namespace") in {
                           "labfy-workspace-overview", "labfy-applications-menu",
                           "labfy-scratchpad-drawer", "labfy-setting-osd"}
                               for surface in item.get("layer_shell_surfaces") or [])]
    workspace_nodes = {}

    def visit(item):
        if item.get("type") == "workspace":
            workspace_nodes[item.get("id")] = item
        for child in (item.get("nodes") or []) + (item.get("floating_nodes") or []):
            visit(child)

    visit(tree)
    cards = []
    for number in range(1, 11):
        workspace = by_number.get(number)
        node = workspace_nodes.get(workspace["id"]) if workspace else None
        output = workspace.get("output") if workspace else ""
        if cache_ok:
            forget_other_outputs(number, output)
        windows = windows_in(node) if node else []
        for window in windows:
            window["excluded"] = excluded(window, rules)
            if cache_ok and window["excluded"]:
                window_preview_path(window["id"]).unlink(missing_ok=True)
                window_preview_metadata_path(window["id"]).unlink(missing_ok=True)
            preview = (None if not cache_ok or window["excluded"] or lock_capture_guard_active()
                       else valid_window_preview(window["id"], window["foreignId"]))
            window["preview"] = preview[0] if preview else ""
            window["previewTime"] = preview[1] if preview else ""
        revision = (structure_revision(node, workspace, output_info.get(output, {}).get("rect"))
                    if node and workspace else "")
        # WHY: composed output pixels cannot safely exclude an application.
        # Retire legacy output snapshots even when their geometry is compatible.
        if cache_ok and output:
            forget_snapshot(output, number)
        snapshot = None
        if not windows:
            snapshot = None
            if cache_ok and output:
                forget_snapshot(output, number)
        cards.append({"number": number, "exists": bool(workspace),
                      "workspaceId": workspace["id"] if workspace else 0,
                      "revision": revision,
                      "visible": bool(workspace and workspace.get("visible")),
                      "focused": bool(workspace and workspace.get("focused")),
                      "output": output, "outputRect": output_info.get(output, {}).get("rect"),
                      "rect": node.get("rect") if node else None,
                      "layout": node.get("layout") if node else "",
                      "windows": windows,
                      "snapshot": snapshot[0] if snapshot else "",
                      # INVARIANT: l'URL QML change à chaque remplacement, même
                      # si deux captures surviennent pendant la même seconde.
                      "snapshotTime": snapshot[1] if snapshot else ""})
    if cache_ok:
        prune_window_previews({window["id"] for card in cards for window in card["windows"]})
    return {"cards": cards, "outputs": [item["name"] for item in outputs if item.get("active")],
            "focusedOutput": next((item["name"] for item in outputs if item.get("focused")), ""),
            "overlayOutputs": overlay_outputs, "captureEnabled": cache_ok and rules["enabled"] and not lock_capture_guard_active()}


def capture(output, expected_number=None, expected_workspace_id=None,
            expected_revision=None, settle_ms=0):
    # CONTRACT: retained CLI returns a fallback; whole-output capture is disabled
    # because it cannot honor per-application exclusions, even before opening.
    return {"captured": False}


def grim_limits():
    # WHY: grim uses file-backed Wayland buffers before encoding the JPEG.
    # RLIMIT_FSIZE also limits those buffers and can kill a valid capture with
    # SIGXFSZ even when its final JPEG is small. The timeout and address-space
    # limit bound the child; the encoded file is checked before publication.
    resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))


def capture_windows(numbers, cursor=0):
    global _deadline
    _deadline = time.monotonic() + 8
    # CONTRACT: serialize all output panels using a private advisory lock.
    # A busy batch falls back without spawning another grim process.
    fd = os.open(cache_dir() / "capture.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1):
            raise ValueError("Verrou de cache non privé")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return {"captured": [], "nextCursor": 0}
        return _capture_windows(numbers, cursor)
    finally:
        _deadline = None
        os.close(fd)


def _capture_windows(numbers, cursor=0):
    if lock_capture_guard_active() or not policy()["enabled"]:
        purge()
        return {"captured": [], "nextCursor": 0}
    if not overview_open():
        return {"captured": [], "nextCursor": 0}
    if cursor < 0:
        raise ValueError("Curseur de capture invalide")
    generation = lock_revision()
    before = state()
    candidates = [window for card in before["cards"] if card["number"] in numbers
                  for window in card["windows"]
                  if not excluded(window, policy()) and re.fullmatch(r"[0-9a-f]{32}", window["foreignId"])]
    # CONTRACT: at most four windows, two seconds each and six seconds per batch.
    # The panel retries only on a new open/structural event, never while closed.
    batch = candidates[cursor:cursor + MAX_BATCH]
    captures = []
    deadline = min(time.monotonic() + 6, _deadline or float("inf"))
    try:
        for window in batch:
            if (lock_capture_guard_active() or generation != lock_revision() or not overview_open()
                    or time.monotonic() >= deadline or excluded(window, policy())):
                break
            with tempfile.NamedTemporaryFile(dir=cache_dir(), suffix=".jpg", delete=False) as temp:
                temporary = Path(temp.name)
            captures.append((window, temporary))
            try:
                result = subprocess.run(["grim", "-T", window["foreignId"], "-s", "0.25",
                                         "-t", "jpeg", "-q", "72", str(temporary)],
                                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                        timeout=min(CAPTURE_SECONDS, max(.01, deadline - time.monotonic())),
                                        preexec_fn=grim_limits, check=False)
                if result.returncode != 0 or not 0 < temporary.stat().st_size <= MAX_IMAGE_BYTES:
                    temporary.unlink(missing_ok=True)
            except (OSError, subprocess.TimeoutExpired):
                temporary.unlink(missing_ok=True)
        after = state()
        current = {window["id"]: window for card in after["cards"] for window in card["windows"]}
        published = []
        for window, temporary in captures:
            if lock_capture_guard_active() or generation != lock_revision() or not overview_open():
                break
            if excluded(current.get(window["id"], {}), policy()):
                continue
            if not temporary.is_file() or current.get(window["id"], {}).get("foreignId") != window["foreignId"]:
                continue
            path = window_preview_path(window["id"])
            metadata_path = window_preview_metadata_path(window["id"])
            temporary.replace(path)
            metadata = {"version": 1, "conId": window["id"], "foreignId": window["foreignId"],
                        "capturedNs": time.time_ns(), "lockRevision": generation,
                        "imageMtimeNs": path.stat().st_mtime_ns}
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=cache_dir(),
                                             suffix=".json", delete=False) as temp_meta:
                json.dump(metadata, temp_meta, separators=(",", ":"))
                temporary_meta = Path(temp_meta.name)
            try:
                temporary_meta.replace(metadata_path)
            finally:
                temporary_meta.unlink(missing_ok=True)
            published.append(window["id"])
    finally:
        for _, temporary in captures:
            temporary.unlink(missing_ok=True)
    next_cursor = cursor + len(batch) if cursor + len(batch) < len(candidates) else 0
    enforce_quota()
    return {"captured": published, "nextCursor": next_cursor}


def command(action, number=None, con_id=None):
    if number not in range(1, 11):
        raise ValueError("Workspace invalide")
    before = state() if action in ("move", "focus") else None
    if action in ("move", "focus"):
        # CONTRACT: seul un con_id d'une vraie fenêtre de l'arbre courant peut
        # commander Sway. Aucun titre ni texte libre n'entre dans le critère.
        known = {window["id"] for card in before["cards"] for window in card["windows"]}
        if con_id not in known:
            raise ValueError("Fenêtre absente de l'arbre Sway")
    source_number = next((card["number"] for card in before["cards"]
                          if any(window["id"] == con_id for window in card["windows"])), 0) if before else 0
    if action == "move":
        args = [f"[con_id={con_id}]", "move", "container", "to", "workspace", "number", str(number)]
    elif action == "focus":
        args = ["workspace", "number", str(number), ";", f"[con_id={con_id}]", "focus"]
    else:
        args = ["workspace", "number", str(number)]
    result = subprocess.run(["swaymsg", "-r", *args], capture_output=True, text=True,
                            timeout=5, check=True)
    responses = json.loads(result.stdout)
    if not all(item.get("success") for item in responses):
        raise RuntimeError(result.stdout)
    after = state()
    changed = ([card["number"] for old, card in zip(before["cards"], after["cards"])
                if old.get("revision") != card.get("revision")] if before else [])
    return {"ok": True, "state": after, "source": source_number if action == "move" else 0,
            "destination": number if action == "move" else 0, "changedWorkspaces": changed}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("state", "capture", "capture-windows", "move", "focus", "workspace", "purge"))
    parser.add_argument("--output")
    parser.add_argument("--number", type=int)
    parser.add_argument("--con-id", type=int)
    parser.add_argument("--workspace-id", type=int)
    parser.add_argument("--revision")
    parser.add_argument("--settle-ms", type=int, default=0)
    parser.add_argument("--numbers")
    parser.add_argument("--cursor", type=int, default=0)
    args = parser.parse_args()
    if args.action == "purge":
        result = purge()
    elif args.action == "state":
        result = state()
    elif args.action == "capture":
        if not args.output or args.output not in state()["outputs"]:
            raise ValueError("Sortie inactive")
        if args.revision is not None and not re.fullmatch(r"[0-9a-f]{64}", args.revision):
            raise ValueError("Révision de capture invalide")
        result = capture(args.output, args.number, args.workspace_id, args.revision, args.settle_ms)
    elif args.action == "capture-windows":
        if not args.numbers or not re.fullmatch(r"(?:10|[1-9])(?:,(?:10|[1-9]))*", args.numbers):
            raise ValueError("Liste de workspaces invalide")
        result = capture_windows(set(map(int, args.numbers.split(","))), args.cursor)
    else:
        result = command(args.action, args.number, args.con_id)
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))


if __name__ == "__main__":
    # CONTRACT: Quickshell cancels this helper on close/reload. Raising through
    # subprocess.run kills and reaps grim instead of leaving an orphan capture.
    def cancelled(signum, frame):
        raise InterruptedError("Capture annulée")
    signal.signal(signal.SIGTERM, cancelled)
    try:
        main()
    except (ValueError, RuntimeError, subprocess.SubprocessError, OSError, json.JSONDecodeError) as error:
        print(json.dumps({"error": "Opération Overview indisponible"}))
        sys.exit(1)
