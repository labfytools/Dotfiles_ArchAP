#!/usr/bin/env python3
"""Capture en lecture seule un Session Snapshot V1 normalisé de Sway."""

from __future__ import annotations

import argparse
import configparser
import datetime as dt
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import time
from typing import Any, Mapping, Sequence


SCHEMA = "labfy.sway.session-snapshot"
VERSION = 1
LAYOUT_ENGINE = "sway-native"
# WHY: le snapshot contient seulement une reconstruction Sway native ; STEP20
# pourra ajouter un autre moteur sans redéfinir les coordonnées inexistantes.
# CONTRACT: schema/version/layout_engine sont les discriminants persistants V1.
# INVARIANT: aucune valeur runtime (PID/con_id) n'est une identité durable.
LAYOUTS = {"none", "splith", "splitv", "stacked", "tabbed", "output", "dockarea"}
CONFIDENCE = {"exact", "heuristic", "unresolved"}
RECT_KEYS = ("x", "y", "width", "height")
DAEMON_NAMES = {
    "autotiling",
    "inactive-windows-transparency.py",
    "wlsunset",
}
INFRASTRUCTURE_NAMES = {
    "polkit-gnome-authentication-agent-1",
    "qs",
    "quickshell",
}


class SnapshotError(RuntimeError):
    """Erreur de collecte ou violation du contrat V1."""


def _ipc(message_type: str) -> Any:
    """CONTRACT: interroger Sway sans commande mutatrice ni shell intermédiaire."""
    try:
        completed = subprocess.run(
            ["swaymsg", "-t", message_type, "-r"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
        return json.loads(completed.stdout)
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
        raise SnapshotError(f"échec de swaymsg -t {message_type}: {exc}") from exc


def _rect(value: Any) -> dict[str, int]:
    source = value if isinstance(value, Mapping) else {}
    return {key: int(source.get(key, 0)) for key in RECT_KEYS}


def _nullable_number(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def _basename_from_pid(pid: Any) -> str | None:
    """SECURITY: lire uniquement le lien exe et ne jamais persister son chemin."""
    if not isinstance(pid, int) or pid <= 0:
        return None
    try:
        return Path(os.readlink(f"/proc/{pid}/exe")).name or None
    except (OSError, ValueError):
        return None


def _desktop_paths() -> list[Path]:
    """Ordre déterministe ; les entrées utilisateur précèdent les entrées système."""
    data_home = Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share")))
    data_dirs = [Path(item) for item in os.environ.get("XDG_DATA_DIRS", "/usr/local/share:/usr/share").split(":") if item]
    roots = [data_home / "applications", *(item / "applications" for item in data_dirs)]
    seen: set[str] = set()
    result: list[Path] = []
    for root in roots:
        key = str(root)
        if key not in seen:
            seen.add(key)
            result.append(root)
    return result


def load_desktop_entries(roots: Sequence[Path] | None = None) -> list[dict[str, str | None]]:
    """Indexer les champs publics nécessaires, sans conserver Exec ni chemins locaux."""
    entries: list[dict[str, str | None]] = []
    claimed_ids: set[str] = set()
    for root in roots or _desktop_paths():
        if not root.is_dir():
            continue
        for path in sorted(root.glob("*.desktop"), key=lambda item: item.name.casefold()):
            desktop_id = path.name
            if desktop_id.casefold() in claimed_ids:
                continue
            parser = configparser.ConfigParser(interpolation=None, strict=False)
            try:
                parser.read(path, encoding="utf-8")
                section = parser["Desktop Entry"]
            except (OSError, UnicodeError, configparser.Error, KeyError):
                continue
            if section.get("Hidden", "false").casefold() == "true":
                continue
            claimed_ids.add(desktop_id.casefold())
            entries.append({
                "desktop_entry": desktop_id,
                "stem": path.stem,
                "startup_wm_class": section.get("StartupWMClass"),
                "name": section.get("Name"),
            })
    return entries


def _identity_candidates(app_id: str | None, window_properties: Mapping[str, Any]) -> list[str]:
    values = [app_id, window_properties.get("class"), window_properties.get("instance")]
    return [value for value in values if isinstance(value, str) and value.strip()]


def resolve_desktop_entry(
    app_id: str | None,
    window_properties: Mapping[str, Any],
    executable_basename: str | None,
    entries: Sequence[Mapping[str, str | None]],
) -> dict[str, Any]:
    """Appliquer une chaîne de preuves explicite ; ne jamais inventer une entrée."""
    candidates = _identity_candidates(app_id, window_properties)
    lowered = {candidate.casefold() for candidate in candidates}
    for entry in entries:
        if str(entry.get("stem") or "").casefold() in lowered:
            return {"desktop_entry": entry["desktop_entry"], "confidence": "exact", "matched_by": "desktop-id"}
    for entry in entries:
        startup = entry.get("startup_wm_class")
        if startup and startup.casefold() in lowered:
            return {"desktop_entry": entry["desktop_entry"], "confidence": "exact", "matched_by": "StartupWMClass"}

    # Une heuristique n'est admise que si un basename normalisé désigne une entrée unique.
    if executable_basename:
        normalized = re.sub(r"[^a-z0-9]+", "", executable_basename.casefold())
        matches = [
            entry for entry in entries
            if re.sub(r"[^a-z0-9]+", "", str(entry.get("stem") or "").casefold()) == normalized
        ]
        if len(matches) == 1:
            return {"desktop_entry": matches[0]["desktop_entry"], "confidence": "heuristic", "matched_by": "executable-basename"}
    return {"desktop_entry": None, "confidence": "unresolved", "matched_by": None}


def parse_sway_autostart(path: Path | None) -> set[str]:
    """Extraire seulement le programme direct des directives exec de l'autostart."""
    managed: set[str] = set()
    if path is None or not path.is_file():
        return managed
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError):
        return managed
    for raw in lines:
        line = raw.strip()
        if not line.startswith("exec "):
            continue
        try:
            words = shlex.split(line[5:], comments=True)
        except ValueError:
            continue
        while words and words[0].startswith("--"):
            words.pop(0)
        if not words:
            continue
        program = Path(words[0]).name
        if program in {"env", "sh", "bash", "zsh", "python", "python3"}:
            if program in {"python", "python3"} and len(words) > 1:
                program = Path(words[1]).name
            else:
                continue
        managed.add(program)
    return managed


def _application_classification(
    app_id: str | None,
    executable_basename: str | None,
    managed: set[str],
) -> dict[str, str | None]:
    names = {name for name in (app_id, executable_basename) if name}
    if names & DAEMON_NAMES:
        return {"category": "daemon", "managed_by": None}
    if names & INFRASTRUCTURE_NAMES:
        return {"category": "session-infrastructure", "managed_by": None}
    if names & managed:
        return {"category": "autostart-managed-application", "managed_by": "sway-autostart"}
    if names:
        return {"category": "user-application", "managed_by": None}
    return {"category": "unknown", "managed_by": None}


class Normalizer:
    """Transformer l'arbre runtime en relations V1 stables dans un snapshot."""

    def __init__(self, desktop_entries: Sequence[Mapping[str, str | None]], managed: set[str]):
        self.desktop_entries = desktop_entries
        self.managed = managed
        self.containers: list[dict[str, Any]] = []
        self.windows: list[dict[str, Any]] = []
        self._container_seq = 0
        self._window_seq = 0
        self._app_ordinals: dict[str, int] = {}
        self.focused_container: str | None = None
        self.focused_window: str | None = None

    def _window(
        self,
        node: Mapping[str, Any],
        workspace: str | None,
        output: str | None,
        parent_id: str | None,
        branch: str,
        index: int,
        hidden_scratchpad: bool,
    ) -> dict[str, str]:
        self._window_seq += 1
        window_id = f"w{self._window_seq}"
        app_id = node.get("app_id") if isinstance(node.get("app_id"), str) else None
        props_source = node.get("window_properties")
        props = props_source if isinstance(props_source, Mapping) else {}
        xclass = props.get("class") if isinstance(props.get("class"), str) else None
        instance = props.get("instance") if isinstance(props.get("instance"), str) else None
        pid = node.get("pid") if isinstance(node.get("pid"), int) else None
        executable = _basename_from_pid(pid)
        resolution = resolve_desktop_entry(app_id, props, executable, self.desktop_entries)
        identity_key = app_id or xclass or instance or executable or "unknown"
        ordinal = self._app_ordinals.get(identity_key, 0) + 1
        self._app_ordinals[identity_key] = ordinal
        scratch_state = node.get("scratchpad_state")
        scratch_member = hidden_scratchpad or scratch_state not in (None, "none")
        classification = _application_classification(app_id, executable, self.managed)
        floating_raw = node.get("floating")
        floating = branch == "floating" or floating_raw in {"auto_on", "user_on"}
        window = {
            "window_id": window_id,
            "snapshot_identity": f"{identity_key}#{ordinal}",
            "runtime": {"con_id": node.get("id"), "pid": pid},
            "workspace": workspace,
            "output": output,
            "app_id": app_id,
            "xwayland": {"class": xclass, "instance": instance},
            "executable_basename": executable,
            "title_hint": node.get("name") if isinstance(node.get("name"), str) else None,
            "restore_identity": {
                "app_id": app_id,
                "class": xclass,
                "instance": instance,
                **resolution,
            },
            "restore_adapter": "terminal" if app_id == "kitty" or xclass == "kitty" else "generic-desktop" if resolution["desktop_entry"] else "unknown",
            "classification": classification,
            "focused": bool(node.get("focused", False)),
            "urgent": bool(node.get("urgent", False)),
            "floating": floating,
            "fullscreen_mode": int(node.get("fullscreen_mode") or 0),
            "rect": _rect(node.get("rect")),
            "percent": _nullable_number(node.get("percent")),
            "marks": [mark for mark in node.get("marks", []) if isinstance(mark, str)],
            "scratchpad": {
                "member": scratch_member,
                "visibility": "hidden" if hidden_scratchpad else "visible" if scratch_member else "not-applicable",
                "state": scratch_state if isinstance(scratch_state, str) else None,
            },
            "tree_position": {"parent_container_id": parent_id, "branch": branch, "index": index},
        }
        self.windows.append(window)
        if window["focused"]:
            self.focused_window = window_id
        return {"kind": "window", "id": window_id}

    def visit(
        self,
        node: Mapping[str, Any],
        workspace: str | None,
        output: str | None,
        parent_id: str | None,
        branch: str,
        index: int,
        hidden_scratchpad: bool = False,
    ) -> dict[str, str]:
        # WHY: les branches séparées portent une sémantique que perdrait une
        # liste plate de fenêtres.
        # CONTRACT: l'ordre de nodes et floating_nodes est conservé tel quel.
        # INVARIANT: chaque référence produite cible exactement un objet V1.
        nodes = node.get("nodes") if isinstance(node.get("nodes"), list) else []
        floating_nodes = node.get("floating_nodes") if isinstance(node.get("floating_nodes"), list) else []
        has_window_identity = any(node.get(key) is not None for key in ("app_id", "window", "window_properties", "pid"))
        if not nodes and not floating_nodes and has_window_identity:
            return self._window(node, workspace, output, parent_id, branch, index, hidden_scratchpad)

        self._container_seq += 1
        container_id = f"c{self._container_seq}"
        container: dict[str, Any] = {
            "container_id": container_id,
            "runtime_con_id": node.get("id"),
            "workspace": workspace,
            "output": output,
            "parent_container_id": parent_id,
            "tree_position": {"branch": branch, "index": index},
            "layout": node.get("layout") if node.get("layout") in LAYOUTS else "none",
            "orientation": node.get("orientation") if isinstance(node.get("orientation"), str) else "none",
            "percent": _nullable_number(node.get("percent")),
            "rect": _rect(node.get("rect")),
            "focused": bool(node.get("focused", False)),
            "urgent": bool(node.get("urgent", False)),
            "marks": [mark for mark in node.get("marks", []) if isinstance(mark, str)],
            "children": [],
            "floating_children": [],
        }
        self.containers.append(container)
        if container["focused"]:
            self.focused_container = container_id
        container["children"] = [
            self.visit(child, workspace, output, container_id, "tiling", child_index, hidden_scratchpad)
            for child_index, child in enumerate(nodes)
            if isinstance(child, Mapping)
        ]
        container["floating_children"] = [
            self.visit(child, workspace, output, container_id, "floating", child_index, hidden_scratchpad)
            for child_index, child in enumerate(floating_nodes)
            if isinstance(child, Mapping)
        ]
        return {"kind": "container", "id": container_id}


def _find_tree_output(tree: Mapping[str, Any], name: str) -> Mapping[str, Any] | None:
    for node in tree.get("nodes", []):
        if isinstance(node, Mapping) and node.get("type") == "output" and node.get("name") == name:
            return node
    return None


def _find_workspace(output_node: Mapping[str, Any], name: str) -> Mapping[str, Any] | None:
    for node in output_node.get("nodes", []):
        if isinstance(node, Mapping) and node.get("type") == "workspace" and node.get("name") == name:
            return node
    return None


def _mode(output: Mapping[str, Any]) -> dict[str, int] | None:
    current = output.get("current_mode")
    if not isinstance(current, Mapping):
        return None
    return {"width": int(current.get("width", 0)), "height": int(current.get("height", 0)), "refresh_millihz": int(current.get("refresh", 0))}


def build_snapshot(
    version: Mapping[str, Any],
    outputs_raw: Sequence[Mapping[str, Any]],
    workspaces_raw: Sequence[Mapping[str, Any]],
    tree: Mapping[str, Any],
    *,
    captured_at: str | None = None,
    environment: Mapping[str, str] | None = None,
    desktop_entries: Sequence[Mapping[str, str | None]] = (),
    managed_autostart: set[str] | None = None,
) -> dict[str, Any]:
    normalizer = Normalizer(desktop_entries, managed_autostart or set())
    outputs: list[dict[str, Any]] = []
    workspaces: list[dict[str, Any]] = []
    workspace_roots: dict[str, dict[str, list[dict[str, str]]]] = {}

    for output in outputs_raw:
        outputs.append({
            "name": output.get("name"),
            "active": bool(output.get("active", False)),
            "focused": bool(output.get("focused", False)),
            "rect": _rect(output.get("rect")),
            "scale": float(output.get("scale", 1.0)),
            "transform": output.get("transform") if isinstance(output.get("transform"), str) else "normal",
            "current_mode": _mode(output),
        })

    for order, workspace in enumerate(workspaces_raw):
        name = str(workspace.get("name"))
        output_name = str(workspace.get("output"))
        tree_output = _find_tree_output(tree, output_name)
        tree_workspace = _find_workspace(tree_output, name) if tree_output else None
        tiling: list[dict[str, str]] = []
        floating: list[dict[str, str]] = []
        if tree_workspace:
            for index, node in enumerate(tree_workspace.get("nodes", [])):
                if isinstance(node, Mapping):
                    tiling.append(normalizer.visit(node, name, output_name, None, "tiling", index))
            for index, node in enumerate(tree_workspace.get("floating_nodes", [])):
                if isinstance(node, Mapping):
                    floating.append(normalizer.visit(node, name, output_name, None, "floating", index))
        workspace_roots[name] = {"tiling": tiling, "floating": floating}
        workspaces.append({
            "name": name,
            "num": int(workspace.get("num", -1)),
            "output": output_name,
            "order": order,
            "focused": bool(workspace.get("focused", False)),
            "visible": bool(workspace.get("visible", False)),
            "urgent": bool(workspace.get("urgent", False)),
            "rect": _rect(workspace.get("rect")),
            "layout": tree_workspace.get("layout", workspace.get("layout", "none")) if tree_workspace else workspace.get("layout", "none"),
            "orientation": tree_workspace.get("orientation", workspace.get("orientation", "none")) if tree_workspace else workspace.get("orientation", "none"),
            "roots": workspace_roots[name],
        })

    # WHY: __i3_scratch est une racine technique, pas un workspace restaurable.
    # CONTRACT: ses vues restent représentées et ne reçoivent pas un faux output.
    # INVARIANT: aucune observation ne déplace une vue vers ou depuis le scratchpad.
    scratch_output = _find_tree_output(tree, "__i3")
    scratch_workspace = _find_workspace(scratch_output, "__i3_scratch") if scratch_output else None
    scratch_roots: list[dict[str, str]] = []
    if scratch_workspace:
        scratch_nodes = [*scratch_workspace.get("nodes", []), *scratch_workspace.get("floating_nodes", [])]
        for index, node in enumerate(scratch_nodes):
            if isinstance(node, Mapping):
                scratch_roots.append(normalizer.visit(node, None, None, None, "scratchpad", index, True))

    env = environment or {}
    captured = captured_at or dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    identity_counts = {key: 0 for key in CONFIDENCE}
    for window in normalizer.windows:
        identity_counts[window["restore_identity"]["confidence"]] += 1
    focused_output = next((item["name"] for item in outputs if item["focused"]), None)
    focused_workspace = next((item["name"] for item in workspaces if item["focused"]), None)
    snapshot = {
        "schema": SCHEMA,
        "version": VERSION,
        "metadata": {
            "captured_at": captured,
            "session_type": env.get("XDG_SESSION_TYPE"),
            "desktop": env.get("XDG_CURRENT_DESKTOP") or env.get("DESKTOP_SESSION"),
        },
        "compositor": {
            "variant": version.get("variant"),
            "version": version.get("human_readable"),
            "sway_version": version.get("sway_original_version"),
            "layout_engine": LAYOUT_ENGINE,
        },
        "outputs": outputs,
        "workspaces": workspaces,
        "containers": normalizer.containers,
        "windows": normalizer.windows,
        "focus": {
            "output": focused_output,
            "workspace": focused_workspace,
            "container_id": normalizer.focused_container,
            "window_id": normalizer.focused_window,
        },
        "restore_hints": {
            "output_matching": "connector-name-preferred-with-future-fallback",
            "missing_output_policy": "deferred",
            "scratchpad_roots": scratch_roots,
        },
        "diagnostics": {
            "identity_counts": identity_counts,
            "volatile_fields": [
                "metadata.captured_at",
                "diagnostics.collection_duration_ms",
                "windows[].title_hint",
            ],
            "source": ["get_version", "get_outputs", "get_workspaces", "get_tree"],
        },
    }
    validate_snapshot(snapshot)
    return snapshot


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise SnapshotError(f"snapshot V1 invalide: {message}")


def validate_snapshot(snapshot: Mapping[str, Any]) -> None:
    """Valider types, bornes et toutes les relations entre collections V1."""
    # WHY: STEP18B ne devra jamais publier un graphe partiel ou incohérent.
    # CONTRACT: toutes les références sont internes au document validé.
    # INVARIANT: la validation est pure et n'interroge pas la session.
    _require(snapshot.get("schema") == SCHEMA, "schema")
    _require(snapshot.get("version") == VERSION, "version")
    for key in ("metadata", "compositor", "focus", "restore_hints", "diagnostics"):
        _require(isinstance(snapshot.get(key), Mapping), key)
    for key in ("outputs", "workspaces", "containers", "windows"):
        _require(isinstance(snapshot.get(key), list), key)

    metadata = snapshot["metadata"]
    _require(all(key in metadata for key in ("captured_at", "session_type", "desktop")), "metadata champs")
    _require(isinstance(metadata["captured_at"], str) and bool(metadata["captured_at"]), "metadata.captured_at")
    _require(metadata["session_type"] is None or isinstance(metadata["session_type"], str), "metadata.session_type")
    _require(metadata["desktop"] is None or isinstance(metadata["desktop"], str), "metadata.desktop")
    compositor = snapshot["compositor"]
    _require(all(key in compositor for key in ("variant", "version", "sway_version", "layout_engine")), "compositor champs")
    _require(compositor["layout_engine"] == LAYOUT_ENGINE, "compositor.layout_engine")
    _require(all(compositor[key] is None or isinstance(compositor[key], str) for key in ("variant", "version", "sway_version")), "compositor types")

    output_names = [item.get("name") for item in snapshot["outputs"]]
    workspace_names = [item.get("name") for item in snapshot["workspaces"]]
    container_ids = [item.get("container_id") for item in snapshot["containers"]]
    window_ids = [item.get("window_id") for item in snapshot["windows"]]
    _require(all(isinstance(item, str) and item for item in output_names), "output.name")
    _require(len(output_names) == len(set(output_names)), "output.name dupliqué")
    _require(len(workspace_names) == len(set(workspace_names)), "workspace.name dupliqué")
    _require(len(container_ids) == len(set(container_ids)), "container_id dupliqué")
    _require(len(window_ids) == len(set(window_ids)), "window_id dupliqué")
    _require([item.get("order") for item in snapshot["workspaces"]] == list(range(len(workspace_names))), "workspace.order")
    all_refs = set(container_ids) | set(window_ids)
    container_by_id = {item["container_id"]: item for item in snapshot["containers"]}
    window_by_id = {item["window_id"]: item for item in snapshot["windows"]}
    object_by_id = {**container_by_id, **window_by_id}

    def validate_rect(value: Any, field: str) -> None:
        _require(isinstance(value, Mapping), field)
        _require(set(value) == set(RECT_KEYS), f"{field} clés")
        _require(all(isinstance(value[key], int) and not isinstance(value[key], bool) for key in RECT_KEYS), f"{field} types")

    for output in snapshot["outputs"]:
        _require(all(key in output for key in ("name", "active", "focused", "rect", "scale", "transform", "current_mode")), "output champs")
        _require(isinstance(output["active"], bool) and isinstance(output["focused"], bool), "output booléens")
        validate_rect(output["rect"], "output.rect")
        _require(isinstance(output["scale"], (int, float)) and not isinstance(output["scale"], bool), "output.scale")
        _require(isinstance(output["transform"], str), "output.transform")
        mode = output["current_mode"]
        _require(mode is None or (
            isinstance(mode, Mapping)
            and set(mode) == {"width", "height", "refresh_millihz"}
            and all(isinstance(item, int) and not isinstance(item, bool) for item in mode.values())
        ), "output.current_mode")

    def validate_ref(ref: Any) -> None:
        _require(isinstance(ref, Mapping), "référence arbre")
        _require(ref.get("kind") in {"container", "window"}, "référence kind")
        _require(ref.get("id") in all_refs, "référence absente")
        _require((ref["kind"] == "container") == (ref["id"] in set(container_ids)), "référence kind/id")

    for workspace in snapshot["workspaces"]:
        _require(all(key in workspace for key in ("name", "num", "output", "order", "focused", "visible", "urgent", "rect", "layout", "orientation", "roots")), "workspace champs")
        _require(workspace.get("output") in output_names, "workspace.output")
        _require(workspace.get("layout") in LAYOUTS, "workspace.layout")
        _require(isinstance(workspace.get("num"), int) and isinstance(workspace.get("order"), int), "workspace num/order")
        _require(all(isinstance(workspace.get(key), bool) for key in ("focused", "visible", "urgent")), "workspace booléens")
        validate_rect(workspace.get("rect"), "workspace.rect")
        for branch in ("tiling", "floating"):
            _require(isinstance(workspace.get("roots", {}).get(branch), list), f"workspace.roots.{branch}")
            for ref in workspace["roots"][branch]:
                validate_ref(ref)
    for container in snapshot["containers"]:
        _require(all(key in container for key in ("container_id", "runtime_con_id", "workspace", "output", "parent_container_id", "tree_position", "layout", "orientation", "percent", "rect", "focused", "urgent", "marks", "children", "floating_children")), "container champs")
        _require(container.get("workspace") is None or container.get("workspace") in workspace_names, "container.workspace")
        _require(container.get("output") is None or container.get("output") in output_names, "container.output")
        _require(container.get("parent_container_id") is None or container.get("parent_container_id") in container_ids, "container.parent")
        _require(container.get("layout") in LAYOUTS, "container.layout")
        _require(isinstance(container.get("orientation"), str), "container.orientation")
        _require(container.get("percent") is None or isinstance(container.get("percent"), (int, float)), "container.percent")
        validate_rect(container.get("rect"), "container.rect")
        for branch in ("children", "floating_children"):
            _require(isinstance(container.get(branch), list), f"container.{branch}")
            for ref in container[branch]:
                validate_ref(ref)
    for window in snapshot["windows"]:
        _require(all(key in window for key in ("window_id", "snapshot_identity", "runtime", "workspace", "output", "app_id", "xwayland", "executable_basename", "title_hint", "restore_identity", "restore_adapter", "classification", "focused", "urgent", "floating", "fullscreen_mode", "rect", "percent", "marks", "scratchpad", "tree_position")), "window champs")
        _require(window.get("workspace") is None or window.get("workspace") in workspace_names, "window.workspace")
        _require(window.get("output") is None or window.get("output") in output_names, "window.output")
        identity = window.get("restore_identity")
        _require(isinstance(identity, Mapping) and identity.get("confidence") in CONFIDENCE, "restore_identity")
        _require(all(key in identity for key in ("app_id", "class", "instance", "desktop_entry", "confidence", "matched_by")), "restore_identity champs")
        _require(window.get("restore_adapter") in {"generic-desktop", "terminal", "browser", "custom", "unknown"}, "restore_adapter")
        classification = window.get("classification")
        _require(isinstance(classification, Mapping) and classification.get("category") in {"user-application", "autostart-managed-application", "session-infrastructure", "daemon", "unknown"}, "classification")
        _require(all(isinstance(window.get(key), bool) for key in ("focused", "urgent", "floating")), "window booléens")
        _require(isinstance(window.get("fullscreen_mode"), int) and not isinstance(window.get("fullscreen_mode"), bool), "window.fullscreen_mode")
        validate_rect(window.get("rect"), "window.rect")
        position = window.get("tree_position")
        _require(isinstance(position, Mapping), "tree_position")
        parent = position.get("parent_container_id")
        _require(parent is None or parent in container_ids, "tree_position.parent_container_id")
        _require(isinstance(window.get("runtime"), Mapping), "window.runtime")
        _require(set(window["runtime"]) == {"con_id", "pid"}, "window.runtime champs")
        _require(all(window["runtime"][key] is None or (isinstance(window["runtime"][key], int) and not isinstance(window["runtime"][key], bool)) for key in ("con_id", "pid")), "window.runtime types")
        scratchpad = window.get("scratchpad")
        _require(isinstance(scratchpad, Mapping) and isinstance(scratchpad.get("member"), bool), "window.scratchpad")
        _require(scratchpad.get("visibility") in {"hidden", "visible", "not-applicable"}, "scratchpad.visibility")
    focus = snapshot["focus"]
    _require(set(focus) == {"output", "workspace", "container_id", "window_id"}, "focus champs")
    _require(focus.get("output") is None or focus.get("output") in output_names, "focus.output")
    _require(focus.get("workspace") is None or focus.get("workspace") in workspace_names, "focus.workspace")
    _require(focus.get("container_id") is None or focus.get("container_id") in container_ids, "focus.container_id")
    _require(focus.get("window_id") is None or focus.get("window_id") in window_ids, "focus.window_id")

    # WHY: une référence valide mais dupliquée ferait relancer/replacer deux fois
    # la même vue ; un objet orphelin perdrait une partie de la session.
    # CONTRACT: chaque objet a exactement une entrée depuis une racine ou un parent.
    # INVARIANT: parent, branche et index concordent avec l'arête entrante.
    incoming = {object_id: 0 for object_id in all_refs}

    def register(ref: Mapping[str, Any], parent: str | None, branch: str, index: int) -> None:
        validate_ref(ref)
        object_id = ref["id"]
        incoming[object_id] += 1
        item = object_by_id[object_id]
        expected_parent = item.get("parent_container_id") if ref["kind"] == "container" else item["tree_position"].get("parent_container_id")
        _require(expected_parent == parent, "arête/parent")
        position = item["tree_position"]
        _require(position.get("branch") == branch and position.get("index") == index, "arête position")

    for workspace in snapshot["workspaces"]:
        for branch in ("tiling", "floating"):
            for index, ref in enumerate(workspace["roots"][branch]):
                register(ref, None, branch, index)
    restore_hints = snapshot["restore_hints"]
    _require(all(key in restore_hints for key in ("output_matching", "missing_output_policy", "scratchpad_roots")), "restore_hints champs")
    _require(restore_hints["output_matching"] == "connector-name-preferred-with-future-fallback", "restore_hints.output_matching")
    _require(restore_hints["missing_output_policy"] == "deferred", "restore_hints.missing_output_policy")
    scratch_roots = restore_hints.get("scratchpad_roots")
    _require(isinstance(scratch_roots, list), "restore_hints.scratchpad_roots")
    for index, ref in enumerate(scratch_roots):
        register(ref, None, "scratchpad", index)
    for container in snapshot["containers"]:
        for key, branch in (("children", "tiling"), ("floating_children", "floating")):
            for index, ref in enumerate(container[key]):
                register(ref, container["container_id"], branch, index)
    _require(all(count == 1 for count in incoming.values()), "objet orphelin ou référencé plusieurs fois")

    # Les comptes d'identité servent au gate réel et doivent être dérivables.
    diagnostics = snapshot["diagnostics"]
    _require(diagnostics.get("source") == ["get_version", "get_outputs", "get_workspaces", "get_tree"], "diagnostics.source")
    _require(isinstance(diagnostics.get("volatile_fields"), list) and all(isinstance(item, str) for item in diagnostics["volatile_fields"]), "diagnostics.volatile_fields")
    counts = diagnostics.get("identity_counts")
    _require(isinstance(counts, Mapping) and set(counts) == CONFIDENCE, "diagnostics.identity_counts")
    expected_counts = {key: 0 for key in CONFIDENCE}
    for window in snapshot["windows"]:
        expected_counts[window["restore_identity"]["confidence"]] += 1
    _require(dict(counts) == expected_counts, "diagnostics.identity_counts valeurs")


def structural_projection(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    """Projection déterministe : les indices purement volatils n'y participent pas."""
    projected = json.loads(json.dumps(snapshot))
    projected["metadata"].pop("captured_at", None)
    projected["diagnostics"].pop("collection_duration_ms", None)
    for window in projected["windows"]:
        window.pop("title_hint", None)
    return projected


def collect(autostart_path: Path | None = None) -> dict[str, Any]:
    """Collecter exactement les quatre sources IPC autorisées et l'allowlist env."""
    environment = {
        key: os.environ[key]
        for key in ("XDG_CURRENT_DESKTOP", "XDG_SESSION_TYPE", "DESKTOP_SESSION")
        if key in os.environ
    }
    return build_snapshot(
        _ipc("get_version"),
        _ipc("get_outputs"),
        _ipc("get_workspaces"),
        _ipc("get_tree"),
        environment=environment,
        desktop_entries=load_desktop_entries(),
        managed_autostart=parse_sway_autostart(autostart_path),
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Capture read-only d'un Session Snapshot V1 Sway")
    parser.add_argument("--stdout", action="store_true", help="émettre le JSON validé sur stdout")
    parser.add_argument("--compact", action="store_true", help="JSON compact (avec --stdout)")
    parser.add_argument(
        "--autostart",
        type=Path,
        default=Path.home() / ".config/sway/autostart",
        help="fichier Sway autostart utilisé seulement pour la classification",
    )
    args = parser.parse_args(argv)
    if not args.stdout:
        parser.error("STEP18A autorise uniquement --stdout")
    started = time.monotonic()
    try:
        snapshot = collect(args.autostart)
    except SnapshotError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    snapshot["diagnostics"]["collection_duration_ms"] = round((time.monotonic() - started) * 1000, 3)
    validate_snapshot(snapshot)
    if args.compact:
        json.dump(snapshot, sys.stdout, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    else:
        json.dump(snapshot, sys.stdout, ensure_ascii=False, sort_keys=True, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
