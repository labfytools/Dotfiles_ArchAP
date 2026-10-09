#!/usr/bin/env python3
"""Source bornée des cartes Sway et des captures de sorties visibles."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time


def lock_capture_guard_active():
    # CONTRACT: capture is denied while the dedicated lock may render an auth
    # surface. A crash leaves the guard active until authenticated recovery.
    runtime = os.environ.get("XDG_RUNTIME_DIR")
    if not runtime:
        return False
    try:
        return (Path(runtime) / "labfy-lock.capture-guard").read_text() == "active\n"
    except OSError:
        return False


def sway(kind):
    result = subprocess.run(["swaymsg", "-t", kind, "-r"], capture_output=True,
                            text=True, timeout=5, check=True)
    return json.loads(result.stdout)


def cache_dir():
    # CONTRACT: cache éphémère et privé ; aucune capture de bureau sur disque durable.
    base = Path(os.environ.get("XDG_RUNTIME_DIR", tempfile.gettempdir()))
    path = base / "labfy-workspace-overview"
    path.mkdir(mode=0o700, exist_ok=True)
    return path


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
        image_stat = path.stat()
        if image_stat.st_size == 0 or metadata_path.stat().st_size > 2048:
            return None
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if (metadata.get("version") != 1 or metadata.get("conId") != con_id
                or metadata.get("foreignId") != foreign_id
                or metadata.get("imageMtimeNs") != image_stat.st_mtime_ns
                or not isinstance(metadata.get("capturedNs"), int)):
            return None
        return path.as_uri(), str(metadata["capturedNs"])
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
            if path.suffix in (".jpg", ".json") and path.stat().st_mtime < cutoff:
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
        image_stat = path.stat()
        if image_stat.st_size == 0 or metadata_path.stat().st_size > 2048:
            return None
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if (metadata.get("version") != 1 or metadata.get("output") != output
                or metadata.get("number") != number
                or metadata.get("workspaceId") != workspace_id
                or metadata.get("revision") != revision
                or metadata.get("imageMtimeNs") != image_stat.st_mtime_ns
                or not isinstance(metadata.get("capturedNs"), int)):
            return None
        return path.as_uri(), str(metadata["capturedNs"])
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
        forget_other_outputs(number, output)
        windows = windows_in(node) if node else []
        for window in windows:
            preview = valid_window_preview(window["id"], window["foreignId"])
            window["preview"] = preview[0] if preview else ""
            window["previewTime"] = preview[1] if preview else ""
        revision = (structure_revision(node, workspace, output_info.get(output, {}).get("rect"))
                    if node and workspace else "")
        snapshot = valid_snapshot(output, number, workspace["id"], revision) if revision else None
        if not windows:
            snapshot = None
            if output:
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
    prune_window_previews({window["id"] for card in cards for window in card["windows"]})
    return {"cards": cards, "outputs": [item["name"] for item in outputs if item.get("active")],
            "focusedOutput": next((item["name"] for item in outputs if item.get("focused")), ""),
            "overlayOutputs": overlay_outputs}


def capture(output, expected_number=None, expected_workspace_id=None,
            expected_revision=None, settle_ms=0):
    if lock_capture_guard_active():
        return {"captured": False}
    if settle_ms < 0 or settle_ms > 1000:
        raise ValueError("Délai de capture invalide")
    if settle_ms:
        time.sleep(settle_ms / 1000)
    before = state()
    current = next((card for card in before["cards"] if card["visible"] and card["output"] == output), None)
    if (output in before["overlayOutputs"] or not current or not current["windows"]
            or (expected_number is not None and current["number"] != expected_number)
            or (expected_workspace_id is not None and current["workspaceId"] != expected_workspace_id)
            or (expected_revision is not None and current["revision"] != expected_revision)):
        return {"captured": False}
    path = snapshot_path(output, current["number"])
    metadata_path = snapshot_metadata_path(output, current["number"])
    # WHY: grim capture uniquement une sortie effectivement affichée. Écriture
    # atomique pour qu'un Image QML ne voie jamais un JPEG partiel.
    with tempfile.NamedTemporaryFile(dir=path.parent, suffix=".jpg", delete=False) as temp:
        temporary = Path(temp.name)
    try:
        if lock_capture_guard_active():
            return {"captured": False}
        subprocess.run(["grim", "-o", output, "-s", "0.25", "-t", "jpeg", "-q", "72",
                        str(temporary)], check=True, timeout=8, capture_output=True)
        if not temporary.is_file() or temporary.stat().st_size == 0:
            raise RuntimeError("Capture vide")
        after = state()
        updated = next((card for card in after["cards"] if card["number"] == current["number"]), None)
        # INVARIANT: un changement pendant grim ou la présence de l'Overview
        # interdit de publier une image associée au mauvais arbre.
        if (lock_capture_guard_active() or output in after["overlayOutputs"] or not updated or not updated["visible"]
                or updated["output"] != output or updated["workspaceId"] != current["workspaceId"]
                or updated["revision"] != current["revision"]):
            return {"captured": False}
        temporary.replace(path)
        metadata = {"version": 1, "output": output, "number": current["number"],
                    "workspaceId": current["workspaceId"], "revision": current["revision"],
                    "capturedNs": time.time_ns(), "imageMtimeNs": path.stat().st_mtime_ns}
        # WHY: le manifeste est publié après le JPEG ; un lecteur concurrent
        # n'associe jamais l'ancienne révision aux nouveaux pixels.
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         suffix=".json", delete=False) as temp_meta:
            json.dump(metadata, temp_meta, separators=(",", ":"))
            temporary_meta = Path(temp_meta.name)
        try:
            temporary_meta.replace(metadata_path)
        finally:
            temporary_meta.unlink(missing_ok=True)
    finally:
        temporary.unlink(missing_ok=True)
    return {"captured": True, "number": current["number"], "path": path.as_uri(),
            "revision": current["revision"]}


def capture_windows(numbers, cursor=0):
    if lock_capture_guard_active():
        return {"captured": [], "nextCursor": 0}
    if cursor < 0:
        raise ValueError("Curseur de capture invalide")
    before = state()
    candidates = [window for card in before["cards"] if card["number"] in numbers
                  for window in card["windows"]
                  if re.fullmatch(r"[0-9a-f]{32}", window["foreignId"])]
    # CONTRACT: une invocation capture au plus 16 fenêtres ; l'interface peut
    # reprendre au curseur suivant sans créer de service ou de pool permanent.
    batch = candidates[cursor:cursor + 16]
    captures = []
    try:
        for window in batch:
            if lock_capture_guard_active():
                break
            with tempfile.NamedTemporaryFile(dir=cache_dir(), suffix=".jpg", delete=False) as temp:
                temporary = Path(temp.name)
            captures.append((window, temporary))
            try:
                result = subprocess.run(["grim", "-T", window["foreignId"], "-s", "0.25",
                                         "-t", "jpeg", "-q", "72", str(temporary)],
                                        capture_output=True, timeout=5, check=False)
                if result.returncode != 0 or temporary.stat().st_size == 0:
                    temporary.unlink(missing_ok=True)
            except (OSError, subprocess.TimeoutExpired):
                temporary.unlink(missing_ok=True)
        after = state()
        current = {window["id"]: window for card in after["cards"] for window in card["windows"]}
        published = []
        for window, temporary in captures:
            if lock_capture_guard_active():
                break
            if not temporary.is_file() or current.get(window["id"], {}).get("foreignId") != window["foreignId"]:
                continue
            path = window_preview_path(window["id"])
            metadata_path = window_preview_metadata_path(window["id"])
            temporary.replace(path)
            metadata = {"version": 1, "conId": window["id"], "foreignId": window["foreignId"],
                        "capturedNs": time.time_ns(), "imageMtimeNs": path.stat().st_mtime_ns}
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
    parser.add_argument("action", choices=("state", "capture", "capture-windows", "move", "focus", "workspace"))
    parser.add_argument("--output")
    parser.add_argument("--number", type=int)
    parser.add_argument("--con-id", type=int)
    parser.add_argument("--workspace-id", type=int)
    parser.add_argument("--revision")
    parser.add_argument("--settle-ms", type=int, default=0)
    parser.add_argument("--numbers")
    parser.add_argument("--cursor", type=int, default=0)
    args = parser.parse_args()
    if args.action == "state":
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
    try:
        main()
    except (ValueError, RuntimeError, subprocess.SubprocessError, OSError, json.JSONDecodeError) as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False))
        sys.exit(1)
