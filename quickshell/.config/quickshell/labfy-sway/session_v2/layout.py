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
