"""Identités persistantes pures. Aucun PID, con_id ni commande exécutable."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Application:
    application_id: str
    desktop_entry: str
    strategy: str
    expected_windows: int
    managed_by: str | None
    identity_provider: str | None


@dataclass(frozen=True)
class WindowSlot:
    slot_id: str
    application_id: str
    workspace: str
    tree_path: tuple
    state: dict
    identity_requirement: str
    identity_evidence: dict | None


@dataclass(frozen=True)
class WindowSlotRef:
    slot_id: str


@dataclass(frozen=True)
class SplitNode:
    layout: str
    children: tuple


@dataclass(frozen=True)
class WorkspaceTree:
    workspace: str
    output: str
    root: object


def decode_tree(value):
    if value is None: return None
    if "slot_id" in value: return WindowSlotRef(value["slot_id"])
    return SplitNode(value["layout"], tuple(decode_tree(c) for c in value["children"]))


def leaves(node):
    if node is None: return []
    if isinstance(node, WindowSlotRef): return [node.slot_id]
    return [s for c in node.children for s in leaves(c)]


def normalized(node):
    if node is None: return None
    if isinstance(node, WindowSlotRef): return node.slot_id
    return {node.layout: [normalized(c) for c in node.children]}
