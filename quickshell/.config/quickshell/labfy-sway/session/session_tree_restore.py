#!/usr/bin/env python3
"""Compiler un sous-ensemble prouvé d'arbres Sway en opérations typées."""

from __future__ import annotations

import copy
import re
from typing import Any, Mapping, NamedTuple, Sequence


SUPPORTED_LAYOUTS = {"splith", "splitv", "tabbed", "stacked"}
SPLIT_LAYOUTS = {"splith", "splitv"}
SAFE_SOURCE_ID = re.compile(r"\Aw[1-9][0-9]*\Z")
SAFE_WORKSPACE = re.compile(r"\A[1-9][0-9]*\Z")


class TreeRestoreError(RuntimeError):
    """Topologie invalide ou extérieure au sous-ensemble STEP19C."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


class TreeNode(NamedTuple):
    """Nœud indépendant des identifiants de containers Sway runtime."""

    kind: str
    key: str | None
    layout: str | None
    percent: float | None
    children: tuple["TreeNode", ...] = ()


def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise TreeRestoreError(reason)


def _number(value: Any) -> float | None:
    if value is None:
        return None
    _require(isinstance(value, (int, float)) and not isinstance(value, bool), "invalid-percent")
    result = float(value)
    _require(0.0 <= result <= 1.0, "invalid-percent")
    return result


def _collections(snapshot: Mapping[str, Any]) -> tuple[dict[str, Mapping[str, Any]], dict[str, Mapping[str, Any]]]:
    containers = {
        str(item.get("container_id")): item
        for item in snapshot.get("containers", [])
        if isinstance(item, Mapping) and isinstance(item.get("container_id"), str)
    }
    windows = {
        str(item.get("window_id")): item
        for item in snapshot.get("windows", [])
        if isinstance(item, Mapping) and isinstance(item.get("window_id"), str)
    }
    return containers, windows


def _node_from_ref(
    ref: Mapping[str, Any],
    containers: Mapping[str, Mapping[str, Any]],
    windows: Mapping[str, Mapping[str, Any]],
    window_keys: Mapping[str, str],
    seen: set[str],
) -> TreeNode:
    kind = ref.get("kind")
    object_id = ref.get("id")
    _require(kind in {"container", "window"} and isinstance(object_id, str), "invalid-tree-reference")
    _require(object_id not in seen, "duplicate-tree-reference")
    seen.add(object_id)
    if kind == "window":
        _require(object_id in windows and object_id in window_keys, "missing-target-window")
        window = windows[object_id]
        _require(window.get("floating") is False, "floating-window-in-tiling-branch")
        return TreeNode("window", window_keys[object_id], None, _number(window.get("percent")))
    _require(object_id in containers, "missing-target-container")
    container = containers[object_id]
    layout = container.get("layout")
    _require(layout in SUPPORTED_LAYOUTS, "unsupported-layout")
    floating_children = container.get("floating_children")
    _require(isinstance(floating_children, list) and not floating_children, "floating-child-in-tiling-container")
    children = container.get("children")
    _require(isinstance(children, list) and children, "empty-or-invalid-container")
    return TreeNode(
        "container",
        None,
        str(layout),
        _number(container.get("percent")),
        tuple(
            _node_from_ref(child, containers, windows, window_keys, seen)
            for child in children
            if isinstance(child, Mapping)
        ),
    )


def normalized_workspace_tree(
    snapshot: Mapping[str, Any],
    workspace_name: str,
    window_keys: Mapping[str, str],
) -> tuple[TreeNode, ...]:
    """Projeter uniquement la branche tiling en identités persistantes/matchées."""
    _require(SAFE_WORKSPACE.fullmatch(workspace_name) is not None, "unsupported-non-numeric-workspace")
    workspace = next(
        (
            item for item in snapshot.get("workspaces", [])
            if isinstance(item, Mapping) and item.get("name") == workspace_name
        ),
        None,
    )
    _require(workspace is not None, "missing-workspace")
    roots = workspace.get("roots")
    roots = roots if isinstance(roots, Mapping) else {}
    tiling = roots.get("tiling")
    _require(isinstance(tiling, list), "invalid-workspace-roots")
    containers, windows = _collections(snapshot)
    seen: set[str] = set()
    return tuple(
        _node_from_ref(ref, containers, windows, window_keys, seen)
        for ref in tiling
        if isinstance(ref, Mapping)
    )


def _leaves(nodes: Sequence[TreeNode]) -> list[str]:
    result: list[str] = []
    for node in nodes:
        if node.kind == "window":
            assert node.key is not None
            result.append(node.key)
        else:
            result.extend(_leaves(node.children))
    return result


def _shape(nodes: Sequence[TreeNode]) -> Any:
    return [
        ("window", node.key)
        if node.kind == "window"
        else ("container", node.layout, _shape(node.children))
        for node in nodes
    ]


def _workspace_layout(snapshot: Mapping[str, Any], workspace_name: str) -> str:
    workspace = next(
        (
            item for item in snapshot.get("workspaces", [])
            if isinstance(item, Mapping) and item.get("name") == workspace_name
        ),
        None,
    )
    _require(workspace is not None and workspace.get("layout") in SUPPORTED_LAYOUTS, "unsupported-workspace-layout")
    return str(workspace["layout"])


def _flat_parent(nodes: Sequence[TreeNode], workspace_layout: str) -> tuple[str, list[str], str]:
    """Retourner layout, ordre et style de racine pour une fratrie sans nesting."""
    if nodes and all(node.kind == "window" for node in nodes):
        return workspace_layout, _leaves(nodes), "workspace-direct"
    if len(nodes) == 1 and nodes[0].kind == "container" and all(
        child.kind == "window" for child in nodes[0].children
    ):
        container = nodes[0]
        assert container.layout is not None
        return container.layout, _leaves(container.children), "container-root"
    raise TreeRestoreError("unsupported-nested-tree")


def _target_shape(nodes: Sequence[TreeNode], workspace_layout: str) -> dict[str, Any]:
    try:
        layout, order, style = _flat_parent(nodes, workspace_layout)
        return {"kind": "flat", "layout": layout, "order": order, "style": style}
    except TreeRestoreError:
        pass

    outer: TreeNode | None = None
    style = "workspace-direct"
    children: Sequence[TreeNode] = nodes
    if len(nodes) == 1 and nodes[0].kind == "container":
        outer = nodes[0]
        children = outer.children
        style = "container-root"
    nested_indexes = [index for index, child in enumerate(children) if child.kind == "container"]
    _require(len(nested_indexes) == 1, "unsupported-nested-tree")
    nested_index = nested_indexes[0]
    nested = children[nested_index]
    _require(all(child.kind == "window" for child in children if child is not nested), "unsupported-nested-tree")
    _require(len(nested.children) == 2 and all(child.kind == "window" for child in nested.children), "unsupported-nested-tree")
    outer_layout = outer.layout if outer is not None else workspace_layout
    _require(outer_layout in SPLIT_LAYOUTS and nested.layout in SPLIT_LAYOUTS, "unsupported-nested-layout")
    _require(outer_layout != nested.layout, "redundant-nested-split")
    _require(nested_index > 0, "unsupported-leading-nested-container")
    return {
        "kind": "two-level",
        "layout": outer_layout,
        "nested_layout": nested.layout,
        "nested_index": nested_index,
        "order": _leaves(children),
        "nested_order": _leaves(nested.children),
        "style": style,
    }


def _operation(kind: str, workspace: str, **values: Any) -> dict[str, Any]:
    # CONTRACT: ces dictionnaires sont une somme fermée ; aucune chaîne Sway
    # provenant d'un snapshot n'est transportée jusqu'à l'exécuteur.
    return {"operation": kind, "workspace": workspace, **values}


def _bubble_order(workspace: str, current: list[str], target: Sequence[str]) -> list[dict[str, Any]]:
    operations: list[dict[str, Any]] = []
    # WHY: move left/right peut extraire une vue d'un container tabbed/stacked.
    # CONTRACT: move-to-mark insère la source après une référence exacte ; le
    # premier enfant cible sert donc d'ancre et chaque suivant est réinséré.
    for wanted_index in range(1, len(target)):
        wanted = target[wanted_index]
        reference = target[wanted_index - 1]
        current_index = current.index(wanted)
        reference_index = current.index(reference)
        if current_index == reference_index + 1:
            continue
        operations.append(_operation(
            "move-relative",
            workspace,
            source_window=wanted,
            relation="after",
            reference_window=reference,
        ))
        current.pop(current_index)
        reference_index = current.index(reference)
        current.insert(reference_index + 1, wanted)
    return operations


def _workspace_names_for_tree_actions(
    source: Mapping[str, Any],
    plan: Mapping[str, Any],
) -> list[str]:
    source_windows = {
        str(item.get("window_id")): item
        for item in source.get("windows", [])
        if isinstance(item, Mapping)
    }
    result: set[str] = set()
    for action in plan.get("actions", []):
        if not isinstance(action, Mapping) or action.get("action") != "restore-tree-position":
            continue
        window = source_windows.get(str(action.get("source_window")))
        workspace = window.get("workspace") if window else None
        _require(isinstance(workspace, str), "tree-action-without-workspace")
        result.add(workspace)
    return sorted(result, key=lambda value: int(value))


def compile_tree_restore(
    source: Mapping[str, Any],
    live: Mapping[str, Any],
    plan: Mapping[str, Any],
) -> dict[str, Any]:
    """Compiler sans effet externe le sous-ensemble localement démontré.

    WHY: les containers et PID sauvegardés sont volatils ; seules les fenêtres
    rematchées relient les deux arbres. CONTRACT: toute fenêtre tiling du
    workspace doit appartenir au target, sinon le preflight bloque. INVARIANT:
    la sortie est déterministe et ne contient aucune commande libre.
    """
    mappings: dict[str, int] = {}
    live_id_by_con: dict[int, str] = {}
    for action in plan.get("actions", []):
        if not isinstance(action, Mapping) or action.get("action") != "reuse-window":
            continue
        source_id = action.get("source_window")
        live_window = action.get("live_window")
        runtime = live_window.get("runtime") if isinstance(live_window, Mapping) else None
        con_id = runtime.get("con_id") if isinstance(runtime, Mapping) else None
        _require(
            isinstance(source_id, str)
            and SAFE_SOURCE_ID.fullmatch(source_id) is not None
            and isinstance(con_id, int)
            and not isinstance(con_id, bool)
            and con_id > 0,
            "invalid-runtime-mapping",
        )
        _require(con_id not in live_id_by_con, "duplicate-runtime-window")
        mappings[source_id] = con_id
        live_id_by_con[con_id] = source_id

    source_windows = {
        str(item.get("window_id")): item
        for item in source.get("windows", [])
        if isinstance(item, Mapping)
    }
    live_windows = {
        str(item.get("window_id")): item
        for item in live.get("windows", [])
        if isinstance(item, Mapping)
    }
    source_keys = {window_id: window_id for window_id in source_windows}
    live_keys: dict[str, str] = {}
    for live_id, window in live_windows.items():
        runtime = window.get("runtime")
        con_id = runtime.get("con_id") if isinstance(runtime, Mapping) else None
        if isinstance(con_id, int) and con_id in live_id_by_con:
            live_keys[live_id] = live_id_by_con[con_id]

    all_operations: list[dict[str, Any]] = []
    workspaces: list[dict[str, Any]] = []
    for workspace in _workspace_names_for_tree_actions(source, plan):
        target_nodes = normalized_workspace_tree(source, workspace, source_keys)
        live_nodes = normalized_workspace_tree(live, workspace, live_keys)
        target_workspace_layout = _workspace_layout(source, workspace)
        live_workspace_layout = _workspace_layout(live, workspace)
        target_leaves = _leaves(target_nodes)
        live_leaves = _leaves(live_nodes)
        _require(target_leaves, "empty-target-tree")
        _require(set(target_leaves) <= set(mappings), "missing-target-window")
        _require(set(live_leaves) == set(target_leaves), "unexpected-live-window")
        _require(len(live_leaves) == len(set(live_leaves)), "duplicate-live-window")
        target = _target_shape(target_nodes, target_workspace_layout)
        identical = (
            _shape(target_nodes) == _shape(live_nodes)
            and (target["style"] != "workspace-direct" or target_workspace_layout == live_workspace_layout)
        )
        operations: list[dict[str, Any]] = []
        if not identical:
            try:
                live_layout, live_order, live_style = _flat_parent(live_nodes, live_workspace_layout)
            except TreeRestoreError as exc:
                raise TreeRestoreError("unsupported-live-nested-tree") from exc
            _require(target["style"] == live_style, "unsupported-root-style-transition")
            operations.extend(_bubble_order(workspace, list(live_order), target["order"]))
            anchor = target["order"][0]
            if live_layout != target["layout"]:
                operations.append(_operation(
                    "set-container-layout",
                    workspace,
                    source_window=anchor,
                    layout=target["layout"],
                ))
            if target["kind"] == "two-level":
                nested_first, nested_second = target["nested_order"]
                operations.append(_operation(
                    "set-split-orientation",
                    workspace,
                    source_window=nested_first,
                    layout=target["nested_layout"],
                ))
                operations.append(_operation(
                    "move-relative",
                    workspace,
                    source_window=nested_second,
                    relation="after",
                    reference_window=nested_first,
                ))
        workspaces.append({
            "workspace": workspace,
            "capability": "supported-subset",
            "target_shape": copy.deepcopy(target),
            "target_tree": _shape(target_nodes),
            "live_tree": _shape(live_nodes),
            "runtime_con_ids": {key: mappings[key] for key in target_leaves},
            "percent_capability": "unsupported",
            "operations": copy.deepcopy(operations),
        })
        all_operations.extend(operations)
    return {
        "capability": "supported-subset",
        "percent_capability": "unsupported",
        "workspaces": workspaces,
        "operations": all_operations,
    }


def validate_operation(operation: Mapping[str, Any]) -> None:
    """Refuser toute valeur hors de la somme typée avant construction argv."""
    kind = operation.get("operation")
    _require(kind in {"set-container-layout", "set-split-orientation", "move-relative"}, "invalid-operation")
    workspace = operation.get("workspace")
    source = operation.get("source_window")
    _require(isinstance(workspace, str) and SAFE_WORKSPACE.fullmatch(workspace) is not None, "invalid-operation-workspace")
    _require(isinstance(source, str) and SAFE_SOURCE_ID.fullmatch(source) is not None, "invalid-operation-window")
    if kind in {"set-container-layout", "set-split-orientation"}:
        layout = operation.get("layout")
        allowed = SUPPORTED_LAYOUTS if kind == "set-container-layout" else SPLIT_LAYOUTS
        _require(layout in allowed, "invalid-operation-layout")
    else:
        _require(operation.get("relation") == "after", "invalid-operation-relation")
        reference = operation.get("reference_window")
        _require(isinstance(reference, str) and SAFE_SOURCE_ID.fullmatch(reference) is not None, "invalid-operation-reference")


def validate_compilation(compilation: Mapping[str, Any]) -> None:
    _require(compilation.get("capability") == "supported-subset", "invalid-capability")
    operations = compilation.get("operations")
    _require(isinstance(operations, list), "invalid-operations")
    for operation in operations:
        _require(isinstance(operation, Mapping), "invalid-operation")
        validate_operation(operation)


def tree_fingerprint(
    live: Mapping[str, Any],
    workspace: str,
    runtime_by_source: Mapping[str, int],
) -> Any:
    """Empreinte structurelle pour détecter une dérive entre deux mutations."""
    live_keys: dict[str, str] = {}
    source_by_con = {con_id: source_id for source_id, con_id in runtime_by_source.items()}
    for item in live.get("windows", []):
        if not isinstance(item, Mapping):
            continue
        runtime = item.get("runtime")
        con_id = runtime.get("con_id") if isinstance(runtime, Mapping) else None
        window_id = item.get("window_id")
        if isinstance(con_id, int) and con_id in source_by_con and isinstance(window_id, str):
            live_keys[window_id] = source_by_con[con_id]
    nodes = normalized_workspace_tree(live, workspace, live_keys)
    return (_workspace_layout(live, workspace), _shape(nodes))
