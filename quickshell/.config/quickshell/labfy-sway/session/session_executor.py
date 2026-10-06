#!/usr/bin/env python3
"""Exécuter le sous-ensemble contrôlé STEP19B/STEP19C d'un plan V1 frais."""

from __future__ import annotations

import contextlib
import copy
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import secrets
import stat
import subprocess
import time
from typing import Any, Callable, Iterator, Mapping, Sequence


REPORT_SCHEMA = "labfy.sway.restore-execution"
REPORT_VERSION = 1
RESTORE_LOCK_FILENAME = ".restore.lock"
LAUNCH_BACKEND = "uwsm-app-desktop-entry"
DEFAULT_WINDOW_TIMEOUT_SECONDS = 10.0
POLL_INTERVAL_SECONDS = 0.1
POSTCONDITION_TIMEOUT_SECONDS = 1.0
SUPPORTED_ACTIONS = {
    "reuse-window",
    "launch-application",
    "skip-autostart-managed",
    "move-to-workspace",
    "restore-floating",
    "restore-fullscreen",
    "restore-tree-position",
    "restore-scratchpad-hidden",
    "restore-scratchpad-visible",
    "restore-focus",
}
UNSUPPORTED_ACTIONS = {
    "manual-required",
}
NUMERIC_WORKSPACE = re.compile(r"\A[1-9][0-9]*\Z")
DESKTOP_ENTRY_ID = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9._-]*\.desktop\Z")


class RestoreExecutionError(RuntimeError):
    """Échec contrôlé portant un code stable et un motif auditables."""

    def __init__(self, code: str, reason: str):
        super().__init__(f"{code}: {reason}")
        self.code = code
        self.reason = reason


def snapshot_digest(snapshot: Mapping[str, Any]) -> str:
    """Hasher le document chargé, indépendamment de son formatage JSON sur disque."""
    payload = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _default_runner(argv: Sequence[str], timeout: float) -> Any:
    """CONTRACT: exécuter un argv construit localement, sans interpréteur shell."""
    if argv and argv[0] == "uwsm":
        # WHY: uwsm app peut rester attaché pendant toute la vie de
        # l'application. Attendre son exit bloquerait avant même le polling
        # Sway ; son PID n'est en outre jamais l'identité de la future vue.
        # CONTRACT: l'enfant direct reçoit uniquement l'argv allowlisté, sans
        # shell et sans capture bornée à gérer. Le CLI STEP19B est éphémère.
        # INVARIANT: seul le matching d'une nouvelle fenêtre prouve le succès.
        return subprocess.Popen(  # type: ignore[return-value]
            list(argv),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
            start_new_session=True,
        )
    return subprocess.run(
        list(argv),
        check=True,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _direct_uwsm_command(desktop_entry: str) -> list[str]:
    """Reconstruire l'unique backend autorisé sans consulter launch.argv."""
    return ["uwsm", "app", "--", desktop_entry]


def _direct_sway_command(con_id: int, operation: str) -> list[str]:
    """Cibler une observation runtime validée ; operation est toujours une constante locale."""
    return ["swaymsg", "-r", f"[con_id={con_id}] {operation}"]


def _load_tree_compiler() -> Any:
    """Charger le compilateur pur voisin sans lui donner d'effet externe."""
    path = Path(__file__).with_name("session_tree_restore.py")
    spec = importlib.util.spec_from_file_location("labfy_session_tree_restore", path)
    if spec is None or spec.loader is None:
        raise RestoreExecutionError("RESTORE_TREE_COMPILER_UNAVAILABLE", path.name)
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except (OSError, ImportError, SyntaxError) as exc:
        raise RestoreExecutionError("RESTORE_TREE_COMPILER_UNAVAILABLE", str(exc)) from exc
    return module


def _source_windows(source: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    return {
        str(window.get("window_id")): window
        for window in source.get("windows", [])
        if isinstance(window, Mapping)
    }


def _runtime_con_id(window: Mapping[str, Any]) -> int | None:
    runtime = window.get("runtime")
    runtime = runtime if isinstance(runtime, Mapping) else {}
    value = runtime.get("con_id")
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else None


def _find_con_id(live: Mapping[str, Any], con_id: int) -> Mapping[str, Any] | None:
    return next(
        (
            window
            for window in live.get("windows", [])
            if isinstance(window, Mapping) and _runtime_con_id(window) == con_id
        ),
        None,
    )


def _compatible_match(
    planner_module: Any,
    saved: Mapping[str, Any],
    candidate: Mapping[str, Any],
) -> bool:
    matches, unmatched = planner_module.match_windows([saved], [candidate])
    saved_id = str(saved.get("window_id"))
    evidence = matches.get(saved_id)
    return not unmatched and evidence is not None and evidence.get("confidence") != "ambiguous"


def _revalidate_runtime(
    source_window: Mapping[str, Any],
    con_id: int,
    *,
    collector: Callable[[], dict[str, Any]],
    planner_module: Any,
    allow_scratchpad: bool = False,
) -> tuple[Mapping[str, Any], dict[str, Any]]:
    """Refuser disparition, recyclage d'id, identité divergente ou workspace inconnu."""
    live = collector()
    candidate = _find_con_id(live, con_id)
    if candidate is None:
        raise RestoreExecutionError("RESTORE_RUNTIME_DIVERGED", f"con_id disparu: {con_id}")
    if not _compatible_match(planner_module, source_window, candidate):
        raise RestoreExecutionError("RESTORE_RUNTIME_DIVERGED", f"identité modifiée pour con_id={con_id}")
    scratchpad = candidate.get("scratchpad")
    scratch_member = isinstance(scratchpad, Mapping) and scratchpad.get("member") is True
    if (
        (not isinstance(candidate.get("workspace"), str) or not candidate.get("workspace"))
        and not (allow_scratchpad and scratch_member)
    ):
        raise RestoreExecutionError("RESTORE_RUNTIME_DIVERGED", f"workspace inconnu pour con_id={con_id}")
    return candidate, live


def _validate_desktop_entry(
    saved: Mapping[str, Any],
    action: Mapping[str, Any],
    *,
    desktop_entries: Sequence[Mapping[str, str | None]],
    resolve_desktop_entry: Callable[..., dict[str, Any]],
) -> str:
    """Recalculer l'identité exacte contre les sources XDG actuelles."""
    desktop_entry = action.get("desktop_entry")
    launch = action.get("launch")
    launch = launch if isinstance(launch, Mapping) else {}
    classification = saved.get("classification")
    classification = classification if isinstance(classification, Mapping) else {}
    identity = saved.get("restore_identity")
    identity = identity if isinstance(identity, Mapping) else {}
    if (
        not isinstance(desktop_entry, str)
        or DESKTOP_ENTRY_ID.fullmatch(desktop_entry) is None
        or launch.get("backend") != LAUNCH_BACKEND
        or classification.get("category") != "user-application"
        or identity.get("confidence") != "exact"
        or identity.get("desktop_entry") != desktop_entry
    ):
        raise RestoreExecutionError(
            "RESTORE_DESKTOP_ENTRY_REJECTED",
            f"identité de lancement non exacte: {action.get('source_window')}",
        )
    xwayland = saved.get("xwayland")
    xwayland = xwayland if isinstance(xwayland, Mapping) else {}
    current = resolve_desktop_entry(
        saved.get("app_id"),
        xwayland,
        saved.get("executable_basename"),
        desktop_entries,
    )
    if current.get("confidence") != "exact" or current.get("desktop_entry") != desktop_entry:
        raise RestoreExecutionError(
            "RESTORE_DESKTOP_ENTRY_REJECTED",
            f"DesktopEntry absente, ambiguë ou devenue incompatible: {desktop_entry}",
        )
    return desktop_entry


def _blocking_finding(action: Mapping[str, Any]) -> dict[str, Any] | None:
    action_type = action.get("action")
    action_id = action.get("action_id")
    if action_type not in SUPPORTED_ACTIONS:
        return {
            "action_id": action_id,
            "action": action_type,
            "reason": action.get("reason") or "unsupported-action-step19b",
        }
    if action_type == "reuse-window" and action.get("confidence") == "ambiguous":
        return {
            "action_id": action_id,
            "action": action_type,
            "reason": "ambiguous-runtime-match",
        }
    if action_type == "move-to-workspace":
        workspace = action.get("desired_workspace")
        if not isinstance(workspace, str) or NUMERIC_WORKSPACE.fullmatch(workspace) is None:
            return {
                "action_id": action_id,
                "action": action_type,
                "reason": "unsupported-non-numeric-workspace",
                "desired_workspace": workspace,
            }
    if action_type == "restore-fullscreen" and action.get("desired_fullscreen_mode") not in {0, 1}:
        return {
            "action_id": action_id,
            "action": action_type,
            "reason": "unsupported-fullscreen-mode",
            "desired_fullscreen_mode": action.get("desired_fullscreen_mode"),
        }
    if action_type in {"restore-scratchpad-hidden", "restore-scratchpad-visible"}:
        desired = action.get("desired")
        visibility = desired.get("visibility") if isinstance(desired, Mapping) else None
        expected = "hidden" if action_type.endswith("hidden") else "visible"
        if not isinstance(desired, Mapping) or desired.get("member") is not True or visibility != expected:
            return {
                "action_id": action_id,
                "action": action_type,
                "reason": "invalid-scratchpad-target",
            }
    return None


def capability_gate(
    source: Mapping[str, Any],
    plan: Mapping[str, Any],
    live: Mapping[str, Any],
    *,
    planner_module: Any,
    tree_module: Any,
    desktop_entries: Sequence[Mapping[str, str | None]],
    resolve_desktop_entry: Callable[..., dict[str, Any]],
) -> Mapping[str, Any]:
    """Examiner tout le plan avant la première mutation, sans exception partielle."""
    windows = _source_windows(source)
    findings: list[dict[str, Any]] = []
    for action in plan.get("actions", []):
        if not isinstance(action, Mapping):
            findings.append({"action_id": None, "action": None, "reason": "invalid-action"})
            continue
        finding = _blocking_finding(action)
        if finding is not None:
            findings.append(finding)
            continue
        saved = windows.get(str(action.get("source_window")))
        if saved is None:
            findings.append({
                "action_id": action.get("action_id"),
                "action": action.get("action"),
                "reason": "source-window-missing",
            })
            continue
        if action.get("action") == "launch-application":
            try:
                _validate_desktop_entry(
                    saved,
                    action,
                    desktop_entries=desktop_entries,
                    resolve_desktop_entry=resolve_desktop_entry,
                )
            except RestoreExecutionError as exc:
                findings.append({
                    "action_id": action.get("action_id"),
                    "action": action.get("action"),
                    "reason": exc.reason,
                })
        if action.get("action") == "reuse-window":
            live_window = action.get("live_window")
            if not isinstance(live_window, Mapping) or _runtime_con_id(live_window) is None:
                findings.append({
                    "action_id": action.get("action_id"),
                    "action": action.get("action"),
                    "reason": "missing-runtime-con-id",
                })
        if action.get("action") == "restore-scratchpad-visible":
            desired_workspace = saved.get("workspace")
            live_focus = live.get("focus")
            focused_workspace = live_focus.get("workspace") if isinstance(live_focus, Mapping) else None
            if (
                not isinstance(desired_workspace, str)
                or NUMERIC_WORKSPACE.fullmatch(desired_workspace) is None
                or focused_workspace != desired_workspace
            ):
                findings.append({
                    "action_id": action.get("action_id"),
                    "action": action.get("action"),
                    "reason": "scratchpad-visible-requires-focused-target-workspace",
                })
    try:
        planner_module.validate_restore_plan(plan)
    except Exception as exc:
        findings.append({"action_id": None, "action": None, "reason": f"invalid-plan: {exc}"})
    if any(
        isinstance(action, Mapping) and action.get("action") == "restore-tree-position"
        for action in plan.get("actions", [])
    ):
        try:
            tree_compilation = tree_module.compile_tree_restore(source, live, plan)
            tree_module.validate_compilation(tree_compilation)
        except Exception as exc:
            findings.append({
                "action_id": None,
                "action": "restore-tree-position",
                "reason": f"tree-preflight: {exc}",
            })
            tree_compilation = {"capability": "unsupported", "operations": [], "workspaces": []}
    else:
        tree_compilation = {
            "capability": "supported-subset",
            "percent_capability": "unsupported",
            "operations": [],
            "workspaces": [],
        }
    if findings:
        raise RestoreExecutionError(
            "RESTORE_BLOCKED_UNSUPPORTED_ACTION",
            json.dumps(findings, ensure_ascii=False, sort_keys=True),
        )
    return tree_compilation


@contextlib.contextmanager
def restore_lock(directory: Path) -> Iterator[None]:
    """Détenir un flock exclusif non bloquant sur un fichier privé persistant."""
    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        directory_flags |= os.O_NOFOLLOW
    try:
        directory_fd = os.open(directory, directory_flags)
    except OSError as exc:
        raise RestoreExecutionError("RESTORE_LOCK_UNSAFE", f"répertoire sessions non sûr: {exc}") from exc
    if stat.S_IMODE(os.fstat(directory_fd).st_mode) != 0o700:
        os.close(directory_fd)
        raise RestoreExecutionError("RESTORE_LOCK_UNSAFE", "répertoire sessions non privé")
    flags = os.O_RDWR | os.O_CREAT | os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    lock_fd = -1
    try:
        try:
            lock_fd = os.open(RESTORE_LOCK_FILENAME, flags, 0o600, dir_fd=directory_fd)
        except OSError as exc:
            raise RestoreExecutionError("RESTORE_LOCK_UNSAFE", f"restore lock non sûr: {exc}") from exc
        info = os.fstat(lock_fd)
        if not stat.S_ISREG(info.st_mode):
            raise RestoreExecutionError("RESTORE_LOCK_UNSAFE", "restore lock non régulier")
        os.fchmod(lock_fd, 0o600)
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RestoreExecutionError("RESTORE_ALREADY_RUNNING", "une restauration est déjà active") from exc
        yield
    finally:
        if lock_fd >= 0:
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
            finally:
                os.close(lock_fd)
        os.close(directory_fd)


def _parse_sway_success(completed: Any) -> None:
    try:
        payload = json.loads(completed.stdout)
    except (AttributeError, TypeError, json.JSONDecodeError) as exc:
        raise RestoreExecutionError("RESTORE_SWAY_COMMAND_FAILED", "réponse swaymsg JSON invalide") from exc
    if not isinstance(payload, list) or not payload or not all(
        isinstance(item, Mapping) and item.get("success") is True for item in payload
    ):
        raise RestoreExecutionError("RESTORE_SWAY_COMMAND_FAILED", f"commande refusée: {payload!r}")


def _wait_for_launched_window(
    saved: Mapping[str, Any],
    before_ids: set[int],
    *,
    collector: Callable[[], dict[str, Any]],
    planner_module: Any,
    timeout: float,
    monotonic: Callable[[], float],
    sleeper: Callable[[float], None],
) -> tuple[int, Mapping[str, Any]]:
    deadline = monotonic() + timeout
    while True:
        live = collector()
        candidates = [
            window
            for window in live.get("windows", [])
            if isinstance(window, Mapping)
            and _runtime_con_id(window) is not None
            and _runtime_con_id(window) not in before_ids
            and _compatible_match(planner_module, saved, window)
        ]
        if candidates:
            matches, _unmatched = planner_module.match_windows([saved], candidates)
            match = matches.get(str(saved.get("window_id")))
            if match is None:
                pass
            elif match.get("confidence") == "ambiguous":
                raise RestoreExecutionError(
                    "RESTORE_LAUNCH_AMBIGUOUS",
                    f"plusieurs nouvelles fenêtres indiscernables: {saved.get('window_id')}",
                )
            else:
                chosen = candidates[int(match["live_index"])]
                con_id = _runtime_con_id(chosen)
                if con_id is not None:
                    return con_id, chosen
        if monotonic() >= deadline:
            raise RestoreExecutionError(
                "RESTORE_LAUNCH_TIMEOUT",
                f"aucune nouvelle fenêtre compatible: {saved.get('window_id')}",
            )
        sleeper(POLL_INTERVAL_SECONDS)


def _action_status(action: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "action_id": action.get("action_id"),
        "action": action.get("action"),
        "source_window": action.get("source_window"),
        "status": "pending",
        "reason": None,
    }


def _wait_for_postcondition(
    saved: Mapping[str, Any],
    con_id: int,
    predicate: Callable[[Mapping[str, Any]], bool],
    failure_reason: str,
    *,
    collector: Callable[[], dict[str, Any]],
    planner_module: Any,
    monotonic: Callable[[], float],
    sleeper: Callable[[float], None],
    allow_scratchpad: bool = False,
) -> Mapping[str, Any]:
    """Attendre brièvement la visibilité IPC d'une mutation déjà acceptée."""
    deadline = monotonic() + POSTCONDITION_TIMEOUT_SECONDS
    while True:
        candidate, _live = _revalidate_runtime(
            saved,
            con_id,
            collector=collector,
            planner_module=planner_module,
            allow_scratchpad=allow_scratchpad,
        )
        if predicate(candidate):
            return candidate
        if monotonic() >= deadline:
            raise RestoreExecutionError("RESTORE_POSTCONDITION_FAILED", failure_reason)
        sleeper(POLL_INTERVAL_SECONDS)


def _tree_argv(
    operation: Mapping[str, Any],
    runtime_by_source: Mapping[str, int],
    tree_module: Any,
) -> list[str]:
    """Construire une commande fermée depuis une opération prévalidée."""
    tree_module.validate_operation(operation)
    source_id = str(operation["source_window"])
    con_id = runtime_by_source.get(source_id)
    if con_id is None:
        raise RestoreExecutionError("RESTORE_RUNTIME_DIVERGED", f"fenêtre arbre absente: {source_id}")
    kind = operation["operation"]
    if kind == "set-container-layout":
        command_layout = "stacking" if operation["layout"] == "stacked" else operation["layout"]
        sway_operation = f"layout {command_layout}"
    elif kind == "set-split-orientation":
        sway_operation = "split horizontal" if operation["layout"] == "splith" else "split vertical"
    else:
        raise RestoreExecutionError("RESTORE_TREE_OPERATION_INVALID", "move-relative requiert un mark temporaire")
    return _direct_sway_command(con_id, sway_operation)


def _all_live_marks(live: Mapping[str, Any]) -> set[str]:
    result: set[str] = set()
    for collection in (live.get("containers", []), live.get("windows", [])):
        for item in collection if isinstance(collection, list) else []:
            if isinstance(item, Mapping):
                result.update(mark for mark in item.get("marks", []) if isinstance(mark, str))
    return result


def _move_relative_with_mark(
    operation: Mapping[str, Any],
    runtime_by_source: Mapping[str, int],
    *,
    collector: Callable[[], dict[str, Any]],
    runner: Callable[[Sequence[str], float], Any],
    monotonic: Callable[[], float],
    sleeper: Callable[[float], None],
) -> int:
    """Insérer une vue après une référence exacte sans direction géométrique."""
    source_con = runtime_by_source.get(str(operation["source_window"]))
    reference_con = runtime_by_source.get(str(operation["reference_window"]))
    if source_con is None or reference_con is None or source_con == reference_con:
        raise RestoreExecutionError("RESTORE_RUNTIME_DIVERGED", "référence move-relative invalide")
    before = collector()
    existing = _all_live_marks(before)
    mark = ""
    for _attempt in range(8):
        candidate = f"__labfy_restore_{secrets.token_hex(8)}"
        if candidate not in existing:
            mark = candidate
            break
    if not mark:
        raise RestoreExecutionError("RESTORE_TEMPORARY_MARK_COLLISION", "aucun mark unique disponible")

    mark_created = False
    commands = 0
    try:
        completed = runner(_direct_sway_command(reference_con, f"mark --add {mark}"), 5.0)
        _parse_sway_success(completed)
        commands += 1
        mark_created = True
        marked = collector()
        reference = _find_con_id(marked, reference_con)
        if reference is None or mark not in reference.get("marks", []):
            raise RestoreExecutionError("RESTORE_POSTCONDITION_FAILED", "mark temporaire absent")
        completed = runner(_direct_sway_command(source_con, f"move container to mark {mark}"), 5.0)
        _parse_sway_success(completed)
        commands += 1
    finally:
        if mark_created:
            try:
                completed = runner(_direct_sway_command(reference_con, f"unmark {mark}"), 5.0)
                _parse_sway_success(completed)
                commands += 1
            except (OSError, subprocess.SubprocessError, RestoreExecutionError):
                # Le caller vérifiera l'absence du mark ; l'erreur originale
                # reste prioritaire si le move lui-même a échoué.
                pass
    deadline = monotonic() + POSTCONDITION_TIMEOUT_SECONDS
    while True:
        after = collector()
        if mark not in _all_live_marks(after):
            return commands
        if monotonic() >= deadline:
            raise RestoreExecutionError("RESTORE_TEMPORARY_MARK_LEAK", mark)
        sleeper(POLL_INTERVAL_SECONDS)


def _execute_tree_compilation(
    source: Mapping[str, Any],
    plan: Mapping[str, Any],
    compilation: Mapping[str, Any],
    runtime_by_source: Mapping[str, int],
    *,
    collector: Callable[[], dict[str, Any]],
    planner_module: Any,
    tree_module: Any,
    runner: Callable[[Sequence[str], float], Any],
    monotonic: Callable[[], float],
    sleeper: Callable[[float], None],
) -> int:
    """Exécuter le bytecode typé avec détection de dérive entre mutations."""
    source_windows = _source_windows(source)
    last_fingerprint: dict[str, Any] = {}
    commands = 0
    for operation in compilation.get("operations", []):
        workspace = str(operation["workspace"])
        before = collector()
        for source_id, con_id in runtime_by_source.items():
            saved = source_windows.get(source_id)
            if saved is not None and saved.get("workspace") == workspace:
                candidate = _find_con_id(before, con_id)
                if candidate is None or not _compatible_match(planner_module, saved, candidate):
                    raise RestoreExecutionError(
                        "RESTORE_RUNTIME_DIVERGED",
                        f"inventaire arbre modifié: {source_id}",
                    )
        fingerprint = tree_module.tree_fingerprint(before, workspace, runtime_by_source)
        if workspace in last_fingerprint and fingerprint != last_fingerprint[workspace]:
            raise RestoreExecutionError(
                "RESTORE_TREE_DRIFTED",
                f"arbre modifié entre deux opérations: workspace {workspace}",
            )
        if operation["operation"] == "move-relative":
            commands += _move_relative_with_mark(
                operation,
                runtime_by_source,
                collector=collector,
                runner=runner,
                monotonic=monotonic,
                sleeper=sleeper,
            )
        else:
            completed = runner(_tree_argv(operation, runtime_by_source, tree_module), 5.0)
            _parse_sway_success(completed)
            commands += 1
        deadline = monotonic() + POSTCONDITION_TIMEOUT_SECONDS
        while True:
            after = collector()
            changed = tree_module.tree_fingerprint(after, workspace, runtime_by_source)
            if changed != fingerprint:
                last_fingerprint[workspace] = changed
                break
            if monotonic() >= deadline:
                raise RestoreExecutionError(
                    "RESTORE_POSTCONDITION_FAILED",
                    f"opération arbre sans effet observable: {operation['operation']}",
                )
            sleeper(POLL_INTERVAL_SECONDS)

    final_live = collector()
    try:
        remaining = tree_module.compile_tree_restore(source, final_live, plan)
        tree_module.validate_compilation(remaining)
    except Exception as exc:
        raise RestoreExecutionError("RESTORE_POSTCONDITION_FAILED", f"arbre final invalide: {exc}") from exc
    if remaining.get("operations"):
        raise RestoreExecutionError("RESTORE_POSTCONDITION_FAILED", "arbre cible non atteint")
    for workspace in remaining.get("workspaces", []):
        if workspace.get("target_tree") != workspace.get("live_tree"):
            raise RestoreExecutionError("RESTORE_POSTCONDITION_FAILED", "topologie finale différente")
    return commands


def execute_fresh_plan(
    source: Mapping[str, Any],
    plan: Mapping[str, Any],
    *,
    collector: Callable[[], dict[str, Any]],
    planner_module: Any,
    desktop_entries: Sequence[Mapping[str, str | None]],
    resolve_desktop_entry: Callable[..., dict[str, Any]],
    runner: Callable[[Sequence[str], float], Any] = _default_runner,
    timeout: float = DEFAULT_WINDOW_TIMEOUT_SECONDS,
    monotonic: Callable[[], float] = time.monotonic,
    sleeper: Callable[[float], None] = time.sleep,
    tree_module: Any | None = None,
) -> dict[str, Any]:
    """Appliquer séquentiellement un plan déjà préflighté et arrêter au premier écart."""
    tree_module = _load_tree_compiler() if tree_module is None else tree_module
    preflight_live = collector()
    tree_compilation = capability_gate(
        source,
        plan,
        preflight_live,
        planner_module=planner_module,
        tree_module=tree_module,
        desktop_entries=desktop_entries,
        resolve_desktop_entry=resolve_desktop_entry,
    )
    windows = _source_windows(source)
    statuses = [_action_status(action) for action in plan["actions"]]
    runtime_by_source: dict[str, int] = {}
    initial_ids = {
        con_id
        for window in plan.get("live", {}).get("windows", [])
        if isinstance(window, Mapping)
        for con_id in [_runtime_con_id(window)]
        if con_id is not None
    }
    applications_launched = 0
    mutating_commands = 0
    stopped_reason: str | None = None
    tree_executed = False

    for action, status in zip(plan["actions"], statuses):
        action_type = action["action"]
        source_id = str(action["source_window"])
        saved = windows[source_id]
        try:
            if action_type == "reuse-window":
                con_id = _runtime_con_id(action["live_window"])
                assert con_id is not None
                saved_scratchpad = saved.get("scratchpad")
                _revalidate_runtime(
                    saved,
                    con_id,
                    collector=collector,
                    planner_module=planner_module,
                    allow_scratchpad=(
                        isinstance(saved_scratchpad, Mapping)
                        and saved_scratchpad.get("member") is True
                    ),
                )
                runtime_by_source[source_id] = con_id
                status.update(status="success", reason="fenêtre live réutilisée et revalidée")
            elif action_type == "skip-autostart-managed":
                status.update(status="skipped", reason="lancement possédé par sway-autostart")
            elif action_type == "launch-application":
                desktop_entry = _validate_desktop_entry(
                    saved,
                    action,
                    desktop_entries=desktop_entries,
                    resolve_desktop_entry=resolve_desktop_entry,
                )
                # CONTRACT: l'inventaire de référence est pris immédiatement
                # avant le lancement, et non réutilisé depuis le plan. Toute
                # apparition/disparition imprévue depuis le plan force l'arrêt.
                before_launch = collector()
                before_launch_ids = {
                    con_id
                    for window in before_launch.get("windows", [])
                    if isinstance(window, Mapping)
                    for con_id in [_runtime_con_id(window)]
                    if con_id is not None
                }
                expected_ids = initial_ids | set(runtime_by_source.values())
                if before_launch_ids != expected_ids:
                    raise RestoreExecutionError(
                        "RESTORE_RUNTIME_DIVERGED",
                        "inventaire con_id modifié avant lancement",
                    )
                completed = runner(_direct_uwsm_command(desktop_entry), timeout)
                if getattr(completed, "returncode", 0) not in {None, 0}:
                    raise RestoreExecutionError("RESTORE_LAUNCH_FAILED", f"uwsm a retourné {completed.returncode}")
                applications_launched += 1
                con_id, _window = _wait_for_launched_window(
                    saved,
                    before_launch_ids,
                    collector=collector,
                    planner_module=planner_module,
                    timeout=timeout,
                    monotonic=monotonic,
                    sleeper=sleeper,
                )
                runtime_by_source[source_id] = con_id
                status.update(status="success", reason=f"nouvelle fenêtre compatible con_id={con_id}")
            else:
                con_id = runtime_by_source.get(source_id)
                if con_id is None:
                    raise RestoreExecutionError(
                        "RESTORE_RUNTIME_DIVERGED",
                        f"aucun con_id validé pour {source_id}",
                    )
                saved_scratchpad = saved.get("scratchpad")
                _revalidate_runtime(
                    saved,
                    con_id,
                    collector=collector,
                    planner_module=planner_module,
                    allow_scratchpad=(
                        isinstance(saved_scratchpad, Mapping)
                        and saved_scratchpad.get("member") is True
                    ),
                )
                if action_type == "restore-tree-position":
                    if not tree_executed:
                        mutating_commands += _execute_tree_compilation(
                            source,
                            plan,
                            tree_compilation,
                            runtime_by_source,
                            collector=collector,
                            planner_module=planner_module,
                            tree_module=tree_module,
                            runner=runner,
                            monotonic=monotonic,
                            sleeper=sleeper,
                        )
                        tree_executed = True
                    status.update(status="success", reason="topologie Sway cible confirmée")
                    continue
                if action_type == "move-to-workspace":
                    workspace = str(int(action["desired_workspace"]))
                    operation = f"move container to workspace number {workspace}"
                elif action_type == "restore-floating":
                    operation = "floating enable" if action["desired_floating"] else "floating disable"
                elif action_type == "restore-fullscreen":
                    operation = "fullscreen enable" if action["desired_fullscreen_mode"] == 1 else "fullscreen disable"
                elif action_type in {"restore-scratchpad-hidden", "restore-scratchpad-visible"}:
                    current = collector()
                    candidate = _find_con_id(current, con_id)
                    if candidate is None or not _compatible_match(planner_module, saved, candidate):
                        raise RestoreExecutionError("RESTORE_RUNTIME_DIVERGED", f"scratchpad cible absente: {con_id}")
                    scratch = candidate.get("scratchpad")
                    scratch = scratch if isinstance(scratch, Mapping) else {}
                    must_hide = (
                        action_type == "restore-scratchpad-hidden"
                        and scratch.get("visibility") != "hidden"
                    )
                    must_admit = (
                        action_type == "restore-scratchpad-visible"
                        and scratch.get("member") is not True
                    )
                    if must_hide or must_admit:
                        completed = runner(_direct_sway_command(con_id, "move scratchpad"), 5.0)
                        _parse_sway_success(completed)
                        mutating_commands += 1
                        _wait_for_postcondition(
                            saved,
                            con_id,
                            lambda item: isinstance(item.get("scratchpad"), Mapping)
                            and item["scratchpad"].get("member") is True
                            and item["scratchpad"].get("visibility") == "hidden",
                            "fenêtre non déplacée vers le scratchpad caché",
                            collector=collector,
                            planner_module=planner_module,
                            monotonic=monotonic,
                            sleeper=sleeper,
                            allow_scratchpad=True,
                        )
                        scratch = {"member": True, "visibility": "hidden"}
                    if (
                        action_type == "restore-scratchpad-visible"
                        and scratch.get("visibility") != "visible"
                    ):
                        completed = runner(_direct_sway_command(con_id, "scratchpad show"), 5.0)
                        _parse_sway_success(completed)
                        mutating_commands += 1
                        _wait_for_postcondition(
                            saved,
                            con_id,
                            lambda item: isinstance(item.get("scratchpad"), Mapping)
                            and item["scratchpad"].get("member") is True
                            and item["scratchpad"].get("visibility") == "visible",
                            "fenêtre scratchpad ciblée non visible",
                            collector=collector,
                            planner_module=planner_module,
                            monotonic=monotonic,
                            sleeper=sleeper,
                            allow_scratchpad=True,
                        )
                    status.update(status="success", reason="scratchpad ciblé confirmé")
                    continue
                else:
                    operation = "focus"
                completed = runner(_direct_sway_command(con_id, operation), 5.0)
                _parse_sway_success(completed)
                mutating_commands += 1
                if action_type == "move-to-workspace":
                    predicate = lambda item: item.get("workspace") == workspace
                    failure_reason = "workspace cible non atteint"
                elif action_type == "restore-floating":
                    predicate = lambda item: bool(item.get("floating")) == bool(action["desired_floating"])
                    failure_reason = "état floating non atteint"
                elif action_type == "restore-fullscreen":
                    predicate = lambda item: int(item.get("fullscreen_mode") or 0) == action["desired_fullscreen_mode"]
                    failure_reason = "état fullscreen non atteint"
                else:
                    predicate = lambda item: bool(item.get("focused"))
                    failure_reason = "focus cible non atteint"
                _wait_for_postcondition(
                    saved,
                    con_id,
                    predicate,
                    failure_reason,
                    collector=collector,
                    planner_module=planner_module,
                    monotonic=monotonic,
                    sleeper=sleeper,
                )
                status.update(status="success", reason="postcondition Sway confirmée")
        except (OSError, subprocess.SubprocessError, RestoreExecutionError, AssertionError) as exc:
            if isinstance(exc, RestoreExecutionError):
                stopped_reason = str(exc)
            else:
                stopped_reason = f"RESTORE_EXTERNAL_COMMAND_FAILED: {exc}"
            status.update(status="failed", reason=stopped_reason)
            break

    return {
        "actions": statuses,
        "applications_launched": applications_launched,
        "mutating_commands_executed": mutating_commands,
        "status": "failed" if stopped_reason else "success",
        "reason": stopped_reason,
        "runtime_windows": dict(sorted(runtime_by_source.items())),
    }


def apply_session(
    name: str,
    autostart_path: Path | None,
    *,
    sessions_path: Path,
    snapshot_loader: Callable[[str], dict[str, Any]],
    live_collector: Callable[[Path | None], dict[str, Any]],
    planner_module: Any,
    desktop_loader: Callable[[], Sequence[Mapping[str, str | None]]],
    resolve_desktop_entry: Callable[..., dict[str, Any]],
    runner: Callable[[Sequence[str], float], Any] = _default_runner,
    timeout: float = DEFAULT_WINDOW_TIMEOUT_SECONDS,
    monotonic: Callable[[], float] = time.monotonic,
    sleeper: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    """Lock, snapshot frais, live frais, plan frais, gate puis exécution contrôlée."""
    report: dict[str, Any] = {
        "schema": REPORT_SCHEMA,
        "version": REPORT_VERSION,
        "source_session": name,
        "status": "blocked",
        "reason": None,
        "snapshot_hash_before": None,
        "snapshot_hash_after": None,
        "snapshot_unchanged": False,
        "plan": None,
        "actions": [],
        "applications_launched": 0,
        "mutating_commands_executed": 0,
        "rollback": "not-transactional-stop-on-first-critical-divergence",
    }
    try:
        with restore_lock(sessions_path):
            source = snapshot_loader(name)
            report["snapshot_hash_before"] = snapshot_digest(source)
            live = live_collector(autostart_path)
            plan = planner_module.build_restore_plan(source, live)
            report["plan"] = copy.deepcopy(plan)
            result = execute_fresh_plan(
                source,
                plan,
                collector=lambda: live_collector(autostart_path),
                planner_module=planner_module,
                desktop_entries=desktop_loader(),
                resolve_desktop_entry=resolve_desktop_entry,
                runner=runner,
                timeout=timeout,
                monotonic=monotonic,
                sleeper=sleeper,
            )
            report.update(result)
            after = snapshot_loader(name)
            report["snapshot_hash_after"] = snapshot_digest(after)
            report["snapshot_unchanged"] = report["snapshot_hash_after"] == report["snapshot_hash_before"]
            if not report["snapshot_unchanged"]:
                report["status"] = "failed"
                report["reason"] = "RESTORE_SNAPSHOT_CHANGED: snapshot source modifié pendant apply"
    except RestoreExecutionError as exc:
        report["status"] = "blocked"
        report["reason"] = str(exc)
        if isinstance(report.get("plan"), Mapping):
            report["actions"] = []
            for action in report["plan"].get("actions", []):
                status = _action_status(action)
                finding = _blocking_finding(action)
                if finding is not None:
                    status.update(status="blocked", reason=finding["reason"])
                report["actions"].append(status)
        if report["snapshot_hash_before"] is not None:
            after = snapshot_loader(name)
            report["snapshot_hash_after"] = snapshot_digest(after)
            report["snapshot_unchanged"] = report["snapshot_hash_after"] == report["snapshot_hash_before"]
    return report
