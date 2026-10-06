#!/usr/bin/env python3
"""Capture en lecture seule un Session Snapshot V1 normalisé de Sway."""

from __future__ import annotations

import argparse
import contextlib
import configparser
import datetime as dt
import errno
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import re
import secrets
import shlex
import stat
import subprocess
import sys
import time
from typing import Any, Callable, Iterator, Mapping, Sequence


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
SESSION_NAME = re.compile(r"\A[A-Za-z0-9_-]{1,64}\Z")
SNAPSHOT_SUFFIX = ".json"
LOCK_FILENAME = ".sessions.lock"
MAX_SNAPSHOT_BYTES = 8 * 1024 * 1024
SAVE_ATTEMPTS = 3
SAVE_RETRY_DELAY_SECONDS = 0.05
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


def utc_now() -> str:
    """Retourner un instant UTC stable et sérialisable à la milliseconde."""
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def normalize_session_name(name: str) -> str:
    """Valider la clé logique V1 sans jamais la transformer en chemin libre."""
    if not isinstance(name, str) or SESSION_NAME.fullmatch(name) is None:
        raise SnapshotError(
            "nom de session invalide: utiliser 1 à 64 caractères parmi A-Z, a-z, 0-9, - et _"
        )
    return name


def _snapshot_filename(name: str) -> str:
    return f"{normalize_session_name(name)}{SNAPSHOT_SUFFIX}"


def _ensure_child_directory(parent_fd: int, name: str) -> int:
    """Créer puis ouvrir un répertoire géré sans suivre de lien symbolique."""
    try:
        os.mkdir(name, mode=0o700, dir_fd=parent_fd)
    except FileExistsError:
        pass
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(name, flags, dir_fd=parent_fd)
    except OSError as exc:
        raise SnapshotError(f"répertoire géré non sûr: {name}: {exc}") from exc
    try:
        info = os.fstat(fd)
        if not stat.S_ISDIR(info.st_mode):
            raise SnapshotError(f"répertoire géré non sûr: {name}")
        # CONTRACT: une umask permissive ou un ancien mode ne doit jamais
        # exposer les titres privés contenus dans les snapshots.
        os.fchmod(fd, 0o700)
        if stat.S_IMODE(os.fstat(fd).st_mode) != 0o700:
            raise SnapshotError(f"permissions répertoire invalides: {name}")
        return fd
    except BaseException:
        os.close(fd)
        raise


def sessions_directory(
    environment: Mapping[str, str] | None = None,
    home: Path | None = None,
) -> Path:
    """Résoudre et créer la cible XDG privée des sessions persistantes."""
    env = os.environ if environment is None else environment
    home_path = Path.home() if home is None else home
    configured = env.get("XDG_STATE_HOME")
    root = Path(configured) if configured else home_path / ".local/state"
    if not root.is_absolute():
        raise SnapshotError("XDG_STATE_HOME doit être un chemin absolu")
    try:
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    except OSError as exc:
        raise SnapshotError(f"impossible d'ouvrir XDG state: {exc}") from exc
    try:
        app_fd = _ensure_child_directory(root_fd, "labfy-sway")
        try:
            sessions_fd = _ensure_child_directory(app_fd, "sessions")
            os.close(sessions_fd)
        finally:
            os.close(app_fd)
    finally:
        os.close(root_fd)
    return root / "labfy-sway/sessions"


def _open_sessions_directory(path: Path) -> int:
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise SnapshotError(f"répertoire sessions non sûr: {exc}") from exc
    if stat.S_IMODE(os.fstat(fd).st_mode) != 0o700:
        os.close(fd)
        raise SnapshotError("permissions du répertoire sessions différentes de 0700")
    return fd


@contextlib.contextmanager
def _sessions_lock(directory_fd: int, *, exclusive: bool) -> Iterator[None]:
    """Sérialiser publications/suppressions et stabiliser lectures multi-fichiers."""
    flags = os.O_RDWR | os.O_CREAT | os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        lock_fd = os.open(LOCK_FILENAME, flags, 0o600, dir_fd=directory_fd)
    except OSError as exc:
        raise SnapshotError(f"verrou sessions non sûr: {exc}") from exc
    try:
        info = os.fstat(lock_fd)
        if not stat.S_ISREG(info.st_mode):
            raise SnapshotError("verrou sessions non régulier")
        os.fchmod(lock_fd, 0o600)
        fcntl.flock(lock_fd, fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
        yield
    finally:
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
        finally:
            os.close(lock_fd)


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
    captured = captured_at or utc_now()
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
    for field in ("captured_at", "created_at", "updated_at"):
        projected["metadata"].pop(field, None)
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


def collect_consistent(
    autostart_path: Path | None = None,
    *,
    attempts: int = SAVE_ATTEMPTS,
    retry_delay: float = SAVE_RETRY_DELAY_SECONDS,
    collector: Callable[[Path | None], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Réessayer uniquement les graphes IPC relationnellement incohérents."""
    if attempts < 1:
        raise ValueError("attempts doit être positif")
    operation = collect if collector is None else collector
    last_error: SnapshotError | None = None
    for attempt in range(attempts):
        try:
            snapshot = operation(autostart_path)
            validate_snapshot(snapshot)
            return snapshot
        except SnapshotError as exc:
            if not str(exc).startswith("snapshot V1 invalide:"):
                raise
            last_error = exc
            if attempt + 1 < attempts and retry_delay > 0:
                time.sleep(retry_delay)
    raise SnapshotError(f"SAVE_FAILED_INCONSISTENT_STATE: {last_error}") from last_error


def _validate_persistent_snapshot(snapshot: Mapping[str, Any], expected_name: str | None = None) -> None:
    """Valider l'extension compatible de métadonnées propre à STEP18B."""
    validate_snapshot(snapshot)
    metadata = snapshot["metadata"]
    for key in ("session_name", "created_at", "updated_at"):
        _require(isinstance(metadata.get(key), str) and bool(metadata[key]), f"metadata.{key}")
    normalized = normalize_session_name(metadata["session_name"])
    _require(normalized == metadata["session_name"], "metadata.session_name")
    parsed: dict[str, dt.datetime] = {}
    for key in ("created_at", "updated_at"):
        try:
            parsed[key] = dt.datetime.fromisoformat(metadata[key].replace("Z", "+00:00"))
        except ValueError as exc:
            raise SnapshotError(f"snapshot V1 invalide: metadata.{key} UTC") from exc
        _require(
            parsed[key].tzinfo is not None and parsed[key].utcoffset() == dt.timedelta(0),
            f"metadata.{key} UTC",
        )
    _require(parsed["updated_at"] >= parsed["created_at"], "metadata.updated_at antérieur à created_at")
    if expected_name is not None:
        _require(normalized == expected_name, "nom fichier/session")


def _read_all_bounded(fd: int, size: int) -> bytes:
    if size > MAX_SNAPSHOT_BYTES:
        raise SnapshotError(f"snapshot trop volumineux (limite {MAX_SNAPSHOT_BYTES} octets)")
    chunks: list[bytes] = []
    remaining = MAX_SNAPSHOT_BYTES + 1
    while remaining > 0:
        chunk = os.read(fd, min(65536, remaining))
        if not chunk:
            break
        chunks.append(chunk)
        remaining -= len(chunk)
    payload = b"".join(chunks)
    if len(payload) > MAX_SNAPSHOT_BYTES:
        raise SnapshotError(f"snapshot trop volumineux (limite {MAX_SNAPSHOT_BYTES} octets)")
    return payload


def _load_snapshot_at(directory_fd: int, filename: str, expected_name: str) -> dict[str, Any]:
    """Lire un fichier régulier borné sans suivre de lien symbolique."""
    flags = os.O_RDONLY | os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(filename, flags, dir_fd=directory_fd)
    except FileNotFoundError:
        raise
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            raise SnapshotError(f"snapshot refusé (lien symbolique): {expected_name}") from exc
        raise SnapshotError(f"lecture snapshot impossible: {expected_name}: {exc}") from exc
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise SnapshotError(f"snapshot refusé (type non régulier): {expected_name}")
        if stat.S_IMODE(info.st_mode) != 0o600:
            raise SnapshotError(f"permissions snapshot différentes de 0600: {expected_name}")
        payload = _read_all_bounded(fd, info.st_size)
    finally:
        os.close(fd)
    try:
        value = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SnapshotError(f"JSON snapshot invalide: {expected_name}: {exc}") from exc
    if not isinstance(value, Mapping):
        raise SnapshotError(f"snapshot invalide: racine JSON non objet: {expected_name}")
    if value.get("schema") != SCHEMA:
        raise SnapshotError(f"unsupported snapshot schema: {value.get('schema')!r}")
    if value.get("version") != VERSION:
        raise SnapshotError(f"unsupported snapshot version: {value.get('version')!r}")
    snapshot = dict(value)
    _validate_persistent_snapshot(snapshot, expected_name)
    return snapshot


def _serialize_snapshot(snapshot: Mapping[str, Any]) -> bytes:
    payload = (json.dumps(snapshot, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
    if len(payload) > MAX_SNAPSHOT_BYTES:
        raise SnapshotError(f"snapshot trop volumineux (limite {MAX_SNAPSHOT_BYTES} octets)")
    return payload


def _write_all(fd: int, payload: bytes) -> None:
    view = memoryview(payload)
    while view:
        written = os.write(fd, view)
        if written <= 0:
            raise SnapshotError("écriture temporaire incomplète")
        view = view[written:]


def _target_is_safe(directory_fd: int, filename: str) -> None:
    try:
        info = os.stat(filename, dir_fd=directory_fd, follow_symlinks=False)
    except FileNotFoundError:
        return
    if stat.S_ISLNK(info.st_mode):
        raise SnapshotError("cible snapshot refusée: lien symbolique")
    if not stat.S_ISREG(info.st_mode):
        raise SnapshotError("cible snapshot refusée: type non régulier")


def _atomic_publish(
    directory_fd: int,
    filename: str,
    snapshot: Mapping[str, Any],
    *,
    before_replace: Callable[[str], None] | None = None,
) -> None:
    """Publier un snapshot complet sans exposer d'état intermédiaire."""
    payload = _serialize_snapshot(snapshot)
    temporary = f".{filename}.{os.getpid()}.{secrets.token_hex(8)}.tmp"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = -1
    try:
        fd = os.open(temporary, flags, 0o600, dir_fd=directory_fd)
        os.fchmod(fd, 0o600)
        _write_all(fd, payload)
        os.fsync(fd)
        os.close(fd)
        fd = -1

        # CONTRACT: relire le fichier réellement écrit avant publication ; une
        # corruption locale ou un test d'interruption ne touche jamais l'ancien.
        check_flags = os.O_RDONLY | os.O_CLOEXEC
        if hasattr(os, "O_NOFOLLOW"):
            check_flags |= os.O_NOFOLLOW
        check_fd = os.open(temporary, check_flags, dir_fd=directory_fd)
        try:
            written = _read_all_bounded(check_fd, os.fstat(check_fd).st_size)
        finally:
            os.close(check_fd)
        if written != payload:
            raise SnapshotError("validation du temporaire échouée")
        decoded = json.loads(written)
        _validate_persistent_snapshot(decoded, snapshot["metadata"]["session_name"])
        _target_is_safe(directory_fd, filename)
        if before_replace is not None:
            before_replace(temporary)
        os.replace(temporary, filename, src_dir_fd=directory_fd, dst_dir_fd=directory_fd)
        os.fsync(directory_fd)
    except (OSError, json.JSONDecodeError) as exc:
        raise SnapshotError(f"publication atomique échouée: {exc}") from exc
    finally:
        if fd >= 0:
            os.close(fd)
        try:
            os.unlink(temporary, dir_fd=directory_fd)
        except FileNotFoundError:
            pass


def _next_updated_at(previous: str | None) -> str:
    current = utc_now()
    if previous is None or current > previous:
        return current
    try:
        parsed = dt.datetime.fromisoformat(previous.replace("Z", "+00:00"))
    except ValueError:
        return current
    return (parsed + dt.timedelta(milliseconds=1)).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def save_session(
    name: str,
    autostart_path: Path | None = None,
    *,
    environment: Mapping[str, str] | None = None,
    home: Path | None = None,
    collector: Callable[[Path | None], dict[str, Any]] | None = None,
    retry_delay: float = SAVE_RETRY_DELAY_SECONDS,
    before_replace: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Collecter, valider et remplacer atomiquement une session nommée."""
    normalized = normalize_session_name(name)
    started = time.monotonic()
    snapshot = collect_consistent(
        autostart_path,
        retry_delay=retry_delay,
        collector=collector,
    )
    snapshot["diagnostics"]["collection_duration_ms"] = round((time.monotonic() - started) * 1000, 3)
    validate_snapshot(snapshot)
    directory = sessions_directory(environment, home)
    directory_fd = _open_sessions_directory(directory)
    filename = _snapshot_filename(normalized)
    try:
        with _sessions_lock(directory_fd, exclusive=True):
            _target_is_safe(directory_fd, filename)
            existing: dict[str, Any] | None = None
            try:
                existing = _load_snapshot_at(directory_fd, filename, normalized)
            except FileNotFoundError:
                pass
            except SnapshotError:
                # CONTRACT: un save explicitement ciblé peut réparer un JSON
                # corrompu, mais jamais contourner un lien ou type de fichier.
                existing = None
            updated_at = _next_updated_at(existing["metadata"]["updated_at"] if existing else None)
            snapshot["metadata"].update({
                "session_name": normalized,
                "created_at": existing["metadata"]["created_at"] if existing else updated_at,
                "updated_at": updated_at,
            })
            _validate_persistent_snapshot(snapshot, normalized)
            _atomic_publish(
                directory_fd,
                filename,
                snapshot,
                before_replace=before_replace,
            )
    finally:
        os.close(directory_fd)
    return snapshot


def show_session(
    name: str,
    *,
    environment: Mapping[str, str] | None = None,
    home: Path | None = None,
) -> dict[str, Any]:
    normalized = normalize_session_name(name)
    directory = sessions_directory(environment, home)
    directory_fd = _open_sessions_directory(directory)
    try:
        with _sessions_lock(directory_fd, exclusive=False):
            try:
                return _load_snapshot_at(directory_fd, _snapshot_filename(normalized), normalized)
            except FileNotFoundError as exc:
                raise SnapshotError(f"session introuvable: {normalized}") from exc
    finally:
        os.close(directory_fd)


def list_sessions(
    *,
    environment: Mapping[str, str] | None = None,
    home: Path | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    directory = sessions_directory(environment, home)
    directory_fd = _open_sessions_directory(directory)
    sessions: list[dict[str, Any]] = []
    warnings: list[str] = []
    try:
        with _sessions_lock(directory_fd, exclusive=False):
            for filename in sorted(os.listdir(directory_fd)):
                if not filename.endswith(SNAPSHOT_SUFFIX):
                    continue
                name = filename[: -len(SNAPSHOT_SUFFIX)]
                try:
                    normalized = normalize_session_name(name)
                    snapshot = _load_snapshot_at(directory_fd, filename, normalized)
                except (SnapshotError, FileNotFoundError) as exc:
                    warnings.append(f"snapshot ignoré {filename}: {exc}")
                    continue
                sessions.append({
                    "name": normalized,
                    "updated_at": snapshot["metadata"]["updated_at"],
                    "windows": len(snapshot["windows"]),
                    "workspaces": len(snapshot["workspaces"]),
                })
    finally:
        os.close(directory_fd)
    return sessions, warnings


def delete_session(
    name: str,
    *,
    environment: Mapping[str, str] | None = None,
    home: Path | None = None,
) -> None:
    normalized = normalize_session_name(name)
    directory = sessions_directory(environment, home)
    directory_fd = _open_sessions_directory(directory)
    filename = _snapshot_filename(normalized)
    try:
        with _sessions_lock(directory_fd, exclusive=True):
            _target_is_safe(directory_fd, filename)
            try:
                os.unlink(filename, dir_fd=directory_fd)
            except FileNotFoundError as exc:
                raise SnapshotError(f"session introuvable: {normalized}") from exc
            os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def _load_restore_planner() -> Callable[[Mapping[str, Any], Mapping[str, Any]], dict[str, Any]]:
    """Charger le planner voisin sans lui donner d'accès implicite au backend."""
    path = Path(__file__).with_name("session_restore.py")
    spec = importlib.util.spec_from_file_location("labfy_session_restore", path)
    if spec is None or spec.loader is None:
        raise SnapshotError("planner de restauration indisponible")
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except (OSError, ImportError, SyntaxError) as exc:
        raise SnapshotError(f"chargement du planner impossible: {exc}") from exc
    planner = getattr(module, "build_restore_plan", None)
    if not callable(planner):
        raise SnapshotError("planner de restauration invalide")
    return planner


def _load_restore_modules() -> tuple[Any, Any]:
    """Charger explicitement planner pur et frontière d'effets STEP19B."""
    planner_path = Path(__file__).with_name("session_restore.py")
    executor_path = Path(__file__).with_name("session_executor.py")

    def load(name: str, path: Path) -> Any:
        spec = importlib.util.spec_from_file_location(name, path)
        if spec is None or spec.loader is None:
            raise SnapshotError(f"module de restauration indisponible: {path.name}")
        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)
        except (OSError, ImportError, SyntaxError) as exc:
            raise SnapshotError(f"chargement de {path.name} impossible: {exc}") from exc
        return module

    return load("labfy_session_restore_apply", planner_path), load("labfy_session_executor", executor_path)


def apply_session(
    name: str,
    autostart_path: Path | None = None,
    *,
    snapshot_loader: Callable[[str], dict[str, Any]] | None = None,
    live_collector: Callable[[Path | None], dict[str, Any]] | None = None,
    sessions_path: Path | None = None,
    planner_module: Any | None = None,
    executor_module: Any | None = None,
    desktop_loader: Callable[[], Sequence[Mapping[str, str | None]]] | None = None,
    runner: Callable[[Sequence[str], float], Any] | None = None,
    timeout: float = 10.0,
) -> dict[str, Any]:
    """Construire puis exécuter un plan frais sous le verrou STEP19B."""
    # WHY: un plan persistant pourrait viser des con_id recyclés. L'API apply
    # n'accepte donc qu'un nom de snapshot et recollecte toujours Sway.
    # CONTRACT: l'exécuteur détient le lock pendant load→plan→execute→rehash.
    # INVARIANT: aucun plan fourni par l'appelant n'est une autorité exécutable.
    normalized = normalize_session_name(name)
    if planner_module is None or executor_module is None:
        loaded_planner, loaded_executor = _load_restore_modules()
        planner_module = loaded_planner if planner_module is None else planner_module
        executor_module = loaded_executor if executor_module is None else executor_module
    kwargs: dict[str, Any] = {
        "sessions_path": sessions_directory() if sessions_path is None else sessions_path,
        "snapshot_loader": show_session if snapshot_loader is None else snapshot_loader,
        "live_collector": collect if live_collector is None else live_collector,
        "planner_module": planner_module,
        "desktop_loader": load_desktop_entries if desktop_loader is None else desktop_loader,
        "resolve_desktop_entry": resolve_desktop_entry,
        "timeout": timeout,
    }
    if runner is not None:
        kwargs["runner"] = runner
    return executor_module.apply_session(normalized, autostart_path, **kwargs)


def plan_session(
    name: str,
    autostart_path: Path | None = None,
    *,
    snapshot_loader: Callable[[str], dict[str, Any]] | None = None,
    live_collector: Callable[[Path | None], dict[str, Any]] | None = None,
    planner: Callable[[Mapping[str, Any], Mapping[str, Any]], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Charger deux états validés et produire un plan sans jamais l'exécuter."""
    # WHY: STEP19A doit réutiliser exactement la validation persistante et la
    # résolution DesktopEntry STEP18, sans ouvrir une seconde voie divergente.
    # CONTRACT: loader et collector sont en lecture seule ; le planner est pur.
    # INVARIANT: aucune commande applicative ou Sway mutatrice n'est accessible ici.
    load = show_session if snapshot_loader is None else snapshot_loader
    observe = collect if live_collector is None else live_collector
    build = _load_restore_planner() if planner is None else planner
    source = load(normalize_session_name(name))
    live = observe(autostart_path)
    validate_snapshot(live)
    try:
        return build(source, live)
    except Exception as exc:
        if exc.__class__.__name__ != "RestorePlanError":
            raise
        raise SnapshotError(str(exc)) from exc


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Snapshots persistants et restauration contrôlée pour Sway")
    parser.add_argument("--stdout", action="store_true", help="émettre le JSON validé sur stdout")
    parser.add_argument("--compact", action="store_true", help="émettre un JSON compact")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="autoriser explicitement les mutations, uniquement avec apply",
    )
    parser.add_argument(
        "--autostart",
        type=Path,
        default=Path.home() / ".config/sway/autostart",
        help="fichier Sway autostart utilisé seulement pour la classification",
    )
    parser.add_argument("command", nargs="?", choices=("save", "list", "show", "delete", "plan", "apply"))
    parser.add_argument("name", nargs="?")
    args = parser.parse_args(argv)
    if args.stdout and args.command is not None:
        parser.error("--stdout ne peut pas être combiné avec une commande persistante")
    if not args.stdout and args.command is None:
        parser.error("utiliser --stdout ou une commande save/list/show/delete/plan/apply")
    if args.command in {"save", "show", "delete", "plan", "apply"} and args.name is None:
        parser.error(f"{args.command} requiert un nom de session")
    if (args.stdout or args.command == "list") and args.name is not None:
        parser.error("nom de session inattendu")
    if args.execute and args.command != "apply":
        parser.error("--execute est réservé à la commande apply")
    if args.command == "apply" and not args.execute:
        print("RESTORE_EXECUTION_REQUIRES_EXPLICIT_EXECUTE: ajouter --execute", file=sys.stderr)
        return 1
    try:
        if args.stdout:
            started = time.monotonic()
            result: Any = collect(args.autostart)
            result["diagnostics"]["collection_duration_ms"] = round((time.monotonic() - started) * 1000, 3)
            validate_snapshot(result)
        elif args.command == "save":
            snapshot = save_session(args.name, args.autostart)
            result = {
                "name": snapshot["metadata"]["session_name"],
                "created_at": snapshot["metadata"]["created_at"],
                "updated_at": snapshot["metadata"]["updated_at"],
                "windows": len(snapshot["windows"]),
                "workspaces": len(snapshot["workspaces"]),
            }
        elif args.command == "list":
            result, warnings = list_sessions()
            for warning in warnings:
                print(warning, file=sys.stderr)
        elif args.command == "show":
            result = show_session(args.name)
        elif args.command == "plan":
            result = plan_session(args.name, args.autostart)
        elif args.command == "apply":
            result = apply_session(args.name, args.autostart)
        else:
            delete_session(args.name)
            result = {"deleted": args.name}
    except SnapshotError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    if args.compact:
        json.dump(result, sys.stdout, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    else:
        json.dump(result, sys.stdout, ensure_ascii=False, sort_keys=True, indent=2)
    sys.stdout.write("\n")
    if args.command == "apply" and result.get("status") != "success":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
