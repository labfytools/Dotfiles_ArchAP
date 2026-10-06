#!/usr/bin/env python3
"""Construire, sans l'exécuter, un Restore Plan V1 déterministe."""

from __future__ import annotations

from collections import Counter
import copy
from typing import Any, Mapping, Sequence


PLAN_SCHEMA = "labfy.sway.restore-plan"
PLAN_VERSION = 1
SNAPSHOT_SCHEMA = "labfy.sway.session-snapshot"
SNAPSHOT_VERSION = 1
LAYOUT_ENGINE = "sway-native"

# CONTRACT: cet ordre est l'interface entre le planner STEP19A et le futur
# exécuteur STEP19B. Une phase tardive ne peut jamais précéder sa dépendance.
PHASES = (
    "match-managed",
    "launch",
    "wait-match",
    "workspace",
    "tree-layout",
    "floating",
    "fullscreen",
    "scratchpad",
    "focus",
)
PHASE_INDEX = {name: index for index, name in enumerate(PHASES)}
ACTION_TYPES = {
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
    "manual-required",
}
CONFIDENCE = {"exact", "high", "medium", "ambiguous", "unresolved"}
NON_RESTORABLE_CATEGORIES = {"session-infrastructure", "daemon"}


class RestorePlanError(RuntimeError):
    """Violation du contrat du planner read-only."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RestorePlanError(f"restore plan V1 invalide: {message}")


def _text(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _fold(value: Any) -> str | None:
    text = _text(value)
    return text.casefold() if text else None


def _identity(window: Mapping[str, Any]) -> dict[str, str | None]:
    restore = window.get("restore_identity")
    restore = restore if isinstance(restore, Mapping) else {}
    xwayland = window.get("xwayland")
    xwayland = xwayland if isinstance(xwayland, Mapping) else {}
    return {
        "desktop_entry": _text(restore.get("desktop_entry")),
        "app_id": _text(window.get("app_id")) or _text(restore.get("app_id")),
        "class": _text(xwayland.get("class")) or _text(restore.get("class")),
        "instance": _text(xwayland.get("instance")) or _text(restore.get("instance")),
        "executable_basename": _text(window.get("executable_basename")),
    }


def _stable_window_key(window: Mapping[str, Any]) -> tuple[str, ...]:
    """Départager sans PID ni con_id, qui ne sont jamais des identités."""
    identity = _identity(window)
    return tuple(
        _fold(value) or ""
        for value in (
            identity["desktop_entry"],
            identity["app_id"],
            identity["class"],
            identity["instance"],
            identity["executable_basename"],
            window.get("workspace"),
            window.get("output"),
            window.get("title_hint"),
            window.get("snapshot_identity"),
            window.get("window_id"),
        )
    )


def _candidate(saved: Mapping[str, Any], live: Mapping[str, Any]) -> dict[str, Any] | None:
    """Noter une preuve d'identité ; titre/workspace ne sont que des hints."""
    wanted = _identity(saved)
    current = _identity(live)
    saved_app = _fold(wanted["app_id"])
    live_app = _fold(current["app_id"])
    saved_class = _fold(wanted["class"])
    live_class = _fold(current["class"])
    desktop_equal = bool(
        _fold(wanted["desktop_entry"])
        and _fold(wanted["desktop_entry"]) == _fold(current["desktop_entry"])
    )
    app_equal = bool(saved_app and saved_app == live_app)
    class_equal = bool(saved_class and saved_class == live_class)
    instance_equal = bool(
        _fold(wanted["instance"])
        and _fold(wanted["instance"]) == _fold(current["instance"])
    )
    executable_equal = bool(
        _fold(wanted["executable_basename"])
        and _fold(wanted["executable_basename"]) == _fold(current["executable_basename"])
    )

    # Une contradiction app_id forte interdit qu'un simple basename ou titre
    # fusionne deux applications différentes.
    if saved_app and live_app and saved_app != live_app and not desktop_equal:
        return None
    if not any((desktop_equal, app_equal, class_equal, instance_equal, executable_equal)):
        return None

    matched_by: list[str] = []
    score = 0
    confidence = "medium"
    if desktop_equal:
        score += 500
        matched_by.append("desktop-entry")
    if app_equal:
        score += 400
        matched_by.append("app-id")
    if class_equal:
        score += 350
        matched_by.append("class")
    if instance_equal:
        score += 250
        matched_by.append("instance")
    if executable_equal:
        score += 150
        matched_by.append("executable-basename")

    if desktop_equal and (app_equal or class_equal):
        confidence = "exact"
    elif desktop_equal or app_equal or class_equal:
        confidence = "high"

    # Les hints ne peuvent jamais créer un candidat ; ils départagent
    # seulement plusieurs fenêtres d'une identité application déjà prouvée.
    if saved.get("workspace") == live.get("workspace"):
        score += 20
    if bool(saved.get("floating")) == bool(live.get("floating")):
        score += 10
    if _fold(saved.get("title_hint")) and _fold(saved.get("title_hint")) == _fold(live.get("title_hint")):
        score += 5
        matched_by.append("title-hint-tiebreak")
    return {"score": score, "confidence": confidence, "matched_by": matched_by}


def match_windows(
    saved_windows: Sequence[Mapping[str, Any]],
    live_windows: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """Produire un matching un-à-un stable ; une vue live n'est jamais réutilisée deux fois."""
    # WHY: une boucle source gloutonne ferait prendre Firefox-B par Firefox-A
    # avant que son titre puisse départager les deux vues.
    # CONTRACT: les meilleures preuves globales gagnent ; l'ordre snapshot ne
    # sert qu'après identité, workspace, floating et title_hint.
    edges: list[tuple[int, int, tuple[str, ...], int, dict[str, Any]]] = []
    for saved_index, saved in enumerate(saved_windows):
        for live_index, live in enumerate(live_windows):
            evidence = _candidate(saved, live)
            if evidence is not None:
                edges.append(
                    (-evidence["score"], saved_index, _stable_window_key(live), live_index, evidence)
                )
    edges.sort()
    used_saved: set[int] = set()
    used_live: set[int] = set()
    matches: dict[str, dict[str, Any]] = {}
    for chosen in edges:
        score, saved_index, _stable, live_index, evidence = chosen
        if saved_index in used_saved or live_index in used_live:
            continue
        used_saved.add(saved_index)
        used_live.add(live_index)
        saved_id = str(saved_windows[saved_index].get("window_id"))
        equal_competitors = sum(
            1 for item in edges
            if item[0] == score and (item[1] == saved_index or item[3] == live_index)
        )
        confidence = "ambiguous" if equal_competitors > 1 else evidence["confidence"]
        matches[saved_id] = {
            "saved_index": saved_index,
            "live_index": live_index,
            "confidence": confidence,
            "matched_by": evidence["matched_by"],
            "score": -score,
        }
    unmatched = [
        str(saved.get("window_id"))
        for index, saved in enumerate(saved_windows)
        if index not in used_saved
    ]
    return matches, unmatched


def _container_path(snapshot: Mapping[str, Any], window: Mapping[str, Any]) -> list[dict[str, Any]]:
    containers = {
        item.get("container_id"): item
        for item in snapshot.get("containers", [])
        if isinstance(item, Mapping)
    }
    position = window.get("tree_position")
    position = position if isinstance(position, Mapping) else {}
    parent = position.get("parent_container_id")
    path: list[dict[str, Any]] = []
    seen: set[str] = set()
    while isinstance(parent, str) and parent in containers and parent not in seen:
        seen.add(parent)
        item = containers[parent]
        item_position = item.get("tree_position")
        item_position = item_position if isinstance(item_position, Mapping) else {}
        path.append({
            "layout": item.get("layout"),
            "orientation": item.get("orientation"),
            "branch": item_position.get("branch"),
            "index": item_position.get("index"),
            "percent": item.get("percent"),
        })
        parent = item.get("parent_container_id")
    path.reverse()
    return path


def _placement(snapshot: Mapping[str, Any], window: Mapping[str, Any]) -> dict[str, Any]:
    workspaces = {
        item.get("name"): item
        for item in snapshot.get("workspaces", [])
        if isinstance(item, Mapping)
    }
    workspace = workspaces.get(window.get("workspace"), {})
    position = window.get("tree_position")
    position = position if isinstance(position, Mapping) else {}
    return {
        "workspace_layout": workspace.get("layout"),
        "workspace_orientation": workspace.get("orientation"),
        "container_path": _container_path(snapshot, window),
        "branch": position.get("branch"),
        "index": position.get("index"),
        "percent": window.get("percent"),
    }


def _window_inventory(window: Mapping[str, Any]) -> dict[str, Any]:
    runtime = window.get("runtime")
    runtime = runtime if isinstance(runtime, Mapping) else {}
    classification = window.get("classification")
    classification = classification if isinstance(classification, Mapping) else {}
    return {
        "window_id": window.get("window_id"),
        "snapshot_identity": window.get("snapshot_identity"),
        "runtime": {"con_id": runtime.get("con_id"), "pid": runtime.get("pid")},
        "workspace": window.get("workspace"),
        "output": window.get("output"),
        **_identity(window),
        "classification": {
            "category": classification.get("category"),
            "managed_by": classification.get("managed_by"),
        },
        "floating": bool(window.get("floating")),
        "fullscreen_mode": window.get("fullscreen_mode"),
        "scratchpad": copy.deepcopy(window.get("scratchpad")),
        "focused": bool(window.get("focused")),
        "title_hint": window.get("title_hint"),
    }


def _validate_input(snapshot: Mapping[str, Any], label: str, *, persistent: bool) -> None:
    _require(snapshot.get("schema") == SNAPSHOT_SCHEMA, f"{label}.schema")
    _require(snapshot.get("version") == SNAPSHOT_VERSION, f"{label}.version")
    compositor = snapshot.get("compositor")
    _require(isinstance(compositor, Mapping), f"{label}.compositor")
    _require(compositor.get("layout_engine") == LAYOUT_ENGINE, f"{label}.layout_engine")
    _require(isinstance(snapshot.get("windows"), list), f"{label}.windows")
    _require(isinstance(snapshot.get("outputs"), list), f"{label}.outputs")
    _require(isinstance(snapshot.get("workspaces"), list), f"{label}.workspaces")
    metadata = snapshot.get("metadata")
    _require(isinstance(metadata, Mapping), f"{label}.metadata")
    if persistent:
        _require(bool(_text(metadata.get("session_name"))), f"{label}.metadata.session_name")


def _draft(
    key: str,
    action: str,
    phase: str,
    saved: Mapping[str, Any] | None,
    *,
    depends: Sequence[str] = (),
    **payload: Any,
) -> dict[str, Any]:
    result = {
        "_key": key,
        "_depends": list(depends),
        "action": action,
        "phase": phase,
        "source_window": saved.get("window_id") if saved else None,
        "snapshot_identity": saved.get("snapshot_identity") if saved else None,
        **payload,
    }
    return result


def _finalize_actions(drafts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    drafts.sort(key=lambda item: (PHASE_INDEX[item["phase"]], item.pop("_order"), item["action"], item["_key"]))
    key_to_id = {item["_key"]: f"a{index:03d}" for index, item in enumerate(drafts, 1)}
    actions: list[dict[str, Any]] = []
    for item in drafts:
        result = {key: value for key, value in item.items() if not key.startswith("_")}
        result["action_id"] = key_to_id[item["_key"]]
        result["depends_on"] = [key_to_id[key] for key in item["_depends"] if key in key_to_id]
        actions.append(result)
    return actions


def validate_restore_plan(plan: Mapping[str, Any]) -> None:
    """Valider l'ordre et les dépendances sans aucun effet externe."""
    _require(plan.get("schema") == PLAN_SCHEMA, "schema")
    _require(plan.get("version") == PLAN_VERSION, "version")
    _require(plan.get("read_only") is True, "read_only")
    _require(plan.get("execution_supported") is False, "execution_supported")
    actions = plan.get("actions")
    _require(isinstance(actions, list), "actions")
    known: set[str] = set()
    last_phase = -1
    focus_seen = False
    for index, action in enumerate(actions):
        _require(isinstance(action, Mapping), f"actions[{index}]")
        action_id = action.get("action_id")
        _require(isinstance(action_id, str) and action_id not in known, "action_id")
        _require(action.get("action") in ACTION_TYPES, "action type")
        phase = action.get("phase")
        _require(phase in PHASE_INDEX and PHASE_INDEX[phase] >= last_phase, "ordre phases")
        last_phase = PHASE_INDEX[phase]
        dependencies = action.get("depends_on")
        _require(isinstance(dependencies, list) and all(item in known for item in dependencies), "depends_on")
        if focus_seen:
            _require(action.get("action") == "restore-focus", "focus doit rester dernier")
        if action.get("action") == "restore-focus":
            focus_seen = True
        confidence = action.get("confidence")
        if confidence is not None:
            _require(confidence in CONFIDENCE, "confidence")
        known.add(action_id)


def build_restore_plan(source: Mapping[str, Any], live: Mapping[str, Any]) -> dict[str, Any]:
    """Comparer deux snapshots validés et retourner uniquement des intentions."""
    _validate_input(source, "source", persistent=True)
    _validate_input(live, "live", persistent=False)
    source_windows = [item for item in source["windows"] if isinstance(item, Mapping)]
    live_windows = [item for item in live["windows"] if isinstance(item, Mapping)]
    matches, unmatched = match_windows(source_windows, live_windows)
    live_outputs = {
        item.get("name")
        for item in live["outputs"]
        if isinstance(item, Mapping) and item.get("active") is True
    }
    live_workspaces = {
        item.get("name")
        for item in live["workspaces"]
        if isinstance(item, Mapping)
    }
    live_focused = live.get("focus", {}).get("window_id") if isinstance(live.get("focus"), Mapping) else None
    drafts: list[dict[str, Any]] = []
    base_keys: dict[str, str] = {}
    matched_live_by_saved: dict[str, Mapping[str, Any]] = {}

    def add(item: dict[str, Any], order: int) -> str:
        item["_order"] = order
        drafts.append(item)
        return item["_key"]

    for order, saved in enumerate(source_windows):
        saved_id = str(saved.get("window_id"))
        desired_output = saved.get("output")
        desired_workspace = saved.get("workspace")
        category = saved.get("classification", {}).get("category") if isinstance(saved.get("classification"), Mapping) else "unknown"
        resolution = saved.get("restore_identity")
        resolution = resolution if isinstance(resolution, Mapping) else {}
        match = matches.get(saved_id)
        live_window: Mapping[str, Any] | None = None

        if match is not None:
            live_window = live_windows[match["live_index"]]
            matched_live_by_saved[saved_id] = live_window
            key = f"reuse:{saved_id}"
            base_keys[saved_id] = add(_draft(
                key,
                "reuse-window",
                "match-managed",
                saved,
                confidence=match["confidence"],
                matched_by=match["matched_by"],
                live_window=_window_inventory(live_window),
            ), order)
        elif desired_output is not None and desired_output not in live_outputs:
            key = f"manual-output:{saved_id}"
            base_keys[saved_id] = add(_draft(
                key,
                "manual-required",
                "match-managed",
                saved,
                confidence="unresolved",
                reason="missing-output",
                desired_output=desired_output,
                policy="deferred-no-fallback",
            ), order)
            continue
        elif category == "autostart-managed-application":
            key = f"managed:{saved_id}"
            base_keys[saved_id] = add(_draft(
                key,
                "skip-autostart-managed",
                "match-managed",
                saved,
                confidence="unresolved",
                reason="launch-owned-by-sway-autostart",
                managed_by=saved.get("classification", {}).get("managed_by"),
            ), order)
            continue
        elif category in NON_RESTORABLE_CATEGORIES:
            key = f"manual-category:{saved_id}"
            base_keys[saved_id] = add(_draft(
                key,
                "manual-required",
                "match-managed",
                saved,
                confidence="unresolved",
                reason="non-restorable-category",
                category=category,
            ), order)
            continue
        elif category == "user-application" and resolution.get("confidence") == "exact" and _text(resolution.get("desktop_entry")):
            key = f"launch:{saved_id}"
            desktop_entry = resolution["desktop_entry"]
            base_keys[saved_id] = add(_draft(
                key,
                "launch-application",
                "launch",
                saved,
                confidence="exact",
                desktop_entry=desktop_entry,
                launch={
                    "backend": "uwsm-app-desktop-entry",
                    "argv": ["uwsm", "app", "--", desktop_entry],
                    "execute_in_step19a": False,
                },
                limitations=["application-internal-state-not-restored"],
            ), order)
        else:
            key = f"manual-identity:{saved_id}"
            base_keys[saved_id] = add(_draft(
                key,
                "manual-required",
                "match-managed",
                saved,
                confidence="unresolved",
                reason="no-exact-launch-identity",
                restore_identity=copy.deepcopy(resolution),
            ), order)
            continue

        base = base_keys[saved_id]
        current_workspace = live_window.get("workspace") if live_window else None
        current_output = live_window.get("output") if live_window else None
        if desired_output is not None and desired_output not in live_outputs:
            add(_draft(
                f"manual-output:{saved_id}", "manual-required", "workspace", saved,
                depends=(base,), confidence="unresolved", reason="missing-output",
                desired_output=desired_output, policy="deferred-no-fallback",
            ), order)
            continue
        if live_window is None or current_workspace != desired_workspace or current_output != desired_output:
            add(_draft(
                f"workspace:{saved_id}", "move-to-workspace", "workspace", saved,
                depends=(base,), desired_workspace=desired_workspace, desired_output=desired_output,
                workspace_exists=desired_workspace in live_workspaces,
                current_workspace=current_workspace, current_output=current_output,
            ), order)

        desired_placement = _placement(source, saved)
        current_placement = _placement(live, live_window) if live_window else None
        # WHY: une fenêtre absente n'a aucune position live à comparer. Émettre
        # immédiatement restore-tree-position bloquerait tout lancement STEP19B,
        # même pour une simple racine de workspace. STEP19C pourra replanifier
        # la topologie une fois la nouvelle fenêtre réellement observable.
        # CONTRACT: le planner ne demande une reconstruction d'arbre que pour
        # une fenêtre déjà matchée dont la structure diffère effectivement.
        # INVARIANT: l'absence n'est jamais assimilée à une structure divergente.
        if live_window is not None and current_placement != desired_placement:
            add(_draft(
                f"tree:{saved_id}", "restore-tree-position", "tree-layout", saved,
                depends=(base,), capability="partially-supported",
                desired=desired_placement, current=current_placement,
                reason="sway-native-tree-diff",
            ), order)

        if live_window is None:
            current_floating = False
            current_fullscreen = 0
            current_scratchpad: Mapping[str, Any] = {}
        else:
            current_floating = bool(live_window.get("floating"))
            current_fullscreen = int(live_window.get("fullscreen_mode") or 0)
            raw_scratchpad = live_window.get("scratchpad")
            current_scratchpad = raw_scratchpad if isinstance(raw_scratchpad, Mapping) else {}
        if current_floating != bool(saved.get("floating")):
            add(_draft(
                f"floating:{saved_id}", "restore-floating", "floating", saved,
                depends=(base,), desired_floating=bool(saved.get("floating")),
                current_floating=current_floating,
            ), order)
        desired_fullscreen = int(saved.get("fullscreen_mode") or 0)
        if current_fullscreen != desired_fullscreen:
            add(_draft(
                f"fullscreen:{saved_id}", "restore-fullscreen", "fullscreen", saved,
                depends=(base,), desired_fullscreen_mode=desired_fullscreen,
                current_fullscreen_mode=current_fullscreen,
            ), order)
        desired_scratchpad = saved.get("scratchpad")
        desired_scratchpad = desired_scratchpad if isinstance(desired_scratchpad, Mapping) else {}
        if desired_scratchpad.get("member") is True and dict(current_scratchpad) != dict(desired_scratchpad):
            visibility = desired_scratchpad.get("visibility")
            action = "restore-scratchpad-hidden" if visibility == "hidden" else "restore-scratchpad-visible"
            add(_draft(
                f"scratch:{saved_id}", action, "scratchpad", saved,
                depends=(base,), desired=copy.deepcopy(desired_scratchpad),
                current=copy.deepcopy(current_scratchpad),
            ), order)
        elif desired_scratchpad.get("member") is not True and current_scratchpad.get("member") is True:
            add(_draft(
                f"manual-scratch:{saved_id}", "manual-required", "scratchpad", saved,
                depends=(base,), confidence="unresolved", reason="live-window-unexpected-scratchpad",
            ), order)

    source_focus = source.get("focus")
    source_focus = source_focus if isinstance(source_focus, Mapping) else {}
    focus_saved_id = source_focus.get("window_id")
    if isinstance(focus_saved_id, str) and focus_saved_id in base_keys:
        focus_live = matched_live_by_saved.get(focus_saved_id)
        focus_live_id = focus_live.get("window_id") if focus_live else None
        mutations = [
            item["_key"] for item in drafts
            if item["action"] not in {"reuse-window", "skip-autostart-managed", "manual-required"}
        ]
        if focus_live_id != live_focused or mutations:
            dependencies = tuple(
                item["_key"] for item in drafts
                if item["action"] != "manual-required"
            )
            add(_draft(
                f"focus:{focus_saved_id}", "restore-focus", "focus",
                next((item for item in source_windows if item.get("window_id") == focus_saved_id), None),
                depends=dependencies, desired_focus_window=focus_saved_id,
                current_live_focus=live_focused,
            ), len(source_windows))

    actions = _finalize_actions(drafts)
    plan = {
        "schema": PLAN_SCHEMA,
        "version": PLAN_VERSION,
        "read_only": True,
        "execution_supported": False,
        "source_session": source["metadata"]["session_name"],
        "source": {
            "schema": source["schema"],
            "version": source["version"],
            "captured_at": source["metadata"].get("captured_at"),
            "layout_engine": source["compositor"]["layout_engine"],
        },
        "live": {
            "captured_at": live["metadata"].get("captured_at"),
            "outputs": [item.get("name") for item in live["outputs"] if isinstance(item, Mapping) and item.get("active")],
            "workspaces": [item.get("name") for item in live["workspaces"] if isinstance(item, Mapping)],
            "windows": [_window_inventory(item) for item in live_windows],
        },
        "policy": {
            "runtime_identity_fields": [],
            "runtime_observation_fields": ["runtime.pid", "runtime.con_id"],
            "missing_output": "deferred-no-fallback",
            "autostart_owner": "sway-autostart",
            "launch_backend_step19b": "uwsm-app-desktop-entry",
            "phase_order": list(PHASES),
            "spatial_canvas": "out-of-scope-step20",
        },
        "matches": [
            {
                "source_window": saved_id,
                "live_window": live_windows[data["live_index"]].get("window_id"),
                "confidence": data["confidence"],
                "matched_by": data["matched_by"],
            }
            for saved_id, data in sorted(matches.items(), key=lambda item: item[1]["saved_index"])
        ],
        "unmatched_source_windows": unmatched,
        "actions": actions,
        "diagnostics": {
            "action_counts": dict(sorted(Counter(item["action"] for item in actions).items())),
            "match_confidence_counts": dict(sorted(Counter(item["confidence"] for item in plan_matches(matches)).items())),
            "mutating_commands_executed": 0,
            "applications_launched": 0,
            "snapshots_written": 0,
        },
    }
    validate_restore_plan(plan)
    return plan


def plan_matches(matches: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Projection minuscule utilisée pour les diagnostics déterministes."""
    return [{"confidence": item["confidence"]} for item in matches.values()]
