"""Compilation pure, top-down, arité conservée ; aucune opération de lancement."""
from dataclasses import dataclass
from .model import SplitNode, leaves, WorkspaceTree, decode_tree


@dataclass(frozen=True)
class Operation:
    kind: str
    transaction_id: str
    workspace: str
    slot_id: str = ""
    layout: str = ""
    parent: tuple = ()
    child_order: int = 0
    root: bool = False


def trees(data): return [WorkspaceTree(w["workspace"], w["output"], decode_tree(w["root"])) for w in data["workspaces"]]


def compile_plan(data, tx):
    from .schema import validate
    import re
    from .errors import require
    validate(data)
    require(re.fullmatch(r"[0-9a-f]{32}", tx), "TRANSACTION_ID_INVALID")
    plan = []
    for t in trees(data):
        def emit(kind, slot="", layout="", parent=(), order=0, root=False):
            plan.append(Operation(kind, tx, t.workspace, slot, layout, parent, order, root))
        def build(node, path=(), root=False):
            if not isinstance(node, SplitNode): return
            first = leaves(node.children[0])[0]
            emit("layout", first, node.layout, path, root=root)
            previous = first
            for i, child in enumerate(node.children[1:], 1):
                emit("focus", previous)
                seed = leaves(child)[0]
                emit("create", seed, parent=path, order=i)
                previous = seed
            for i, child in enumerate(node.children): build(child, path + (i,))
        if t.root is not None:
            emit("workspace")
            emit("create", leaves(t.root)[0])
            build(t.root, root=True)
    return tuple(plan)


def compile_placements(data):
    """Deterministic placement phase after tiling anchors, including scratchpad.

    CONTRACT : this is descriptive data, not executable launch authority. Hidden
    leaves have no workspace destination. V1 false means only ordinary floating;
    the historical document itself is never rewritten or silently downgraded.
    """
    from .schema import validate
    validate(data)
    return tuple({"slot_id": s["slot_id"], "workspace": s["workspace"],
                  "scratchpad": s["state"]["scratchpad"] or "none",
                  "geometry": dict(s["state"]["geometry"])}
                 for s in data["window_slots"] if s["state"]["floating"])
