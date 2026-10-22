"""EXPERIMENTAL : journal local borné et reprise d'emplacement, jamais rollback ACID.

WHY : une intention durable précède l'IPC ; sa postcondition seule autorise une
reprise. CONTRACT : identité session/con_id/app_id/PID/starttime et état observé.
INVARIANT : aucun kill client, aucune propriété déduite du nom du workspace.
"""
import copy
import json
import re
import time
from pathlib import Path
from .errors import require
from .ipc import walk, location, workspace, until, canonical
from .storage import atomic, read

JOURNAL = "session-v2-recovery.json"
RECEIPT = "session-v2-recovery-receipt.json"


def process_start(pid):
    # Le comm peut contenir espaces et parenthèses : le champ 22 suit le dernier ).
    return int(Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[19])


def observe(tree, node, start):
    # Commands addressed to a leaf can act on its floating/scratchpad ancestor
    # in Sway. Such a group is outside the single-surface ownership contract.
    parents = {c["id"]: n for n in walk(tree) for c in n.get("nodes", []) + n.get("floating_nodes", [])}
    ancestor = parents.get(node["id"])
    while ancestor and ancestor.get("type") not in ("workspace", "output", "root"):
        require(ancestor.get("scratchpad_state", "none") == "none", "SCRATCHPAD_CONTAINER_UNSUPPORTED")
        ancestor = parents.get(ancestor["id"])
    where = location(tree, node["id"])
    require(where and where[0], "RECOVERY_LOCATION_MISSING")
    output = next((o["name"] for o in tree.get("nodes", [])
                   if any(w.get("type") == "workspace" and w.get("name") == where[0] for w in walk(o))), None)
    require(output is not None, "RECOVERY_OUTPUT_MISSING")
    floating = node.get("type") == "floating_con" or node.get("floating") in ("user_on", "auto_on")
    return {"con_id": node["id"], "app_id": node.get("app_id"), "pid": node.get("pid"),
            "starttime": start(node["pid"]), "workspace": where[0], "output": output,
            "path": list(where[1]), "scratchpad": scratchpad_state(node, where[0]), "floating": floating, "geometry": dict(node["rect"]) if floating else None}


def scratchpad_state(node, workspace_name):
    """CONTRACT : appartenance IPC et visibilité sont deux preuves distinctes."""
    raw = node.get("scratchpad_state", "none")
    require(raw in ("none", "fresh", "changed"), "SCRATCHPAD_STATE_UNSUPPORTED")
    return "none" if raw == "none" else ("hidden" if workspace_name == "__i3_scratch" else "shown")


def placement(state):
    return {k: v for k, v in state.items() if k != "path"} if state is not None else None


def structure(tree):
    """Preuve de topologie, avec feuilles con_id et branches ordonnées.

    CONTRACT : seule la contraction des splits unaires h/v/none déjà utilisée
    par Anchors est équivalente. Tabbed/stacked, branches, ordre et appartenance
    restent significatifs. Les flottants sont comparés par placement exact.
    WHY : un chemin brut ne permet pas de distinguer compaction et réordonnancement.
    """
    identities = {n["id"]: n["id"] for n in walk(tree) if n.get("app_id") or n.get("window")}
    return {n["name"]: canonical(tree, n["name"], identities) for n in walk(tree)
            if n.get("type") == "workspace" and n.get("nodes")}


def command_postcondition(state, target, operation, tree):
    expected = copy.deepcopy(state)
    fields = ["con_id", "app_id", "pid", "starttime", "workspace", "output", "floating", "geometry"]
    if "scratchpad" in expected: fields.append("scratchpad")
    if expected["con_id"] == target:
        if operation == "move scratchpad":
            require(state["floating"], "SCRATCHPAD_FLOATING_REQUIRED")
            expected.update(workspace="__i3_scratch", output="__i3", scratchpad="hidden")
        elif operation == "scratchpad show":
            require(state.get("scratchpad") == "hidden", "SCRATCHPAD_SHOW_UNPROVEN")
            name = focused(tree)["workspace"]
            require(name and name != "__i3_scratch", "RESTORE_FOCUS_UNAVAILABLE")
            expected.update(workspace=name, output=next(o["name"] for o in tree["nodes"]
                if any(w.get("type") == "workspace" and w.get("name") == name for w in walk(o))), scratchpad="shown")
            # Output-coordinate conversion is compositor-owned. The exact saved
            # geometry is set and checked afterwards; identity/focus stay strict.
            fields.remove("geometry")
        elif operation.startswith("move container to workspace "):
            expected["workspace"] = json.loads(operation.removeprefix("move container to workspace "))
            destination = workspace(tree, expected["workspace"])
            if destination:
                expected["output"] = next(o["name"] for o in tree.get("nodes", [])
                                          if any(n.get("id") == destination["id"] for n in walk(o)))
        elif operation.startswith("swap container with con_id "):
            other = int(operation.split()[-1])
            destination = next(n for n in walk(tree) if n["id"] == other)
            expected["workspace"] = location(tree, destination["id"])[0]
            expected["output"] = next(o["name"] for o in tree.get("nodes", [])
                                      if any(n.get("id") == other for n in walk(o)))
        elif operation in ("floating enable", "floating disable"):
            expected["floating"] = operation == "floating enable"
            if expected["floating"]:
                if not state["floating"]: fields.remove("geometry")
            else:
                expected["geometry"] = None
                if "scratchpad" in expected: expected["scratchpad"] = "none"
        elif operation.startswith("resize set "):
            values = [int(v) for v in re.findall(r"-?\d+", operation)]
            g = expected["geometry"]
            # SwayFX resize_set_floating conserve le centre (division C tronquée).
            g["x"] -= int((values[0] - g["width"]) / 2)
            g["y"] -= int((values[1] - g["height"]) / 2)
            g.update(width=values[0], height=values[1])
        elif operation.startswith("move absolute position "):
            values = [int(v) for v in re.findall(r"-?\d+", operation)]
            expected["geometry"].update(x=values[0], y=values[1])
    elif operation.startswith("move workspace to output "):
        # Seul le workspace actuellement focalisé est affecté.
        if expected["workspace"] == focused(tree)["workspace"]:
            expected["output"] = json.loads(operation.removeprefix("move workspace to output "))
    return {k: expected[k] for k in fields}


def focused(tree):
    # WHY : Sway peut focaliser un split interne sans aucune feuille focalisée.
    # CONTRACT : conserver le vrai con_id, jamais descendre sa pile de focus.
    # INVARIANT : absence ou ambiguïté reste sans preuve, pas une feuille inventée.
    selected = [n for n in walk(tree) if n.get("focused")]
    if len(selected) != 1: return {"con_id": None, "workspace": None}
    node = selected[0]
    if node.get("type") == "workspace":
        return {"con_id": None, "workspace": node["name"]}
    where = location(tree, node["id"])
    if node.get("type") in ("con", "floating_con") and where and where[0]:
        return {"con_id": node["id"], "workspace": where[0]}
    return {"con_id": None, "workspace": None}


def focus_proof(sway):
    """Preuve locale bornée, jamais une sélection implicite de fenêtre.

    WHY : le retrait QML ne prouve pas le retour du focus chez Sway.
    CONTRACT : deux arbres cohérents et la même autorité session avant journal.
    INVARIANT : feuille, split ou workspace explicite ; null/ambigu reste refusé.
    """
    session = sway.session
    def sample():
        tree = sway.tree()
        topology = [(n["id"], n.get("type"), n.get("app_id"), n.get("pid"),
                     n.get("focused", False), n.get("focus", []),
                     [c["id"] for c in n.get("nodes", [])],
                     [c["id"] for c in n.get("floating_nodes", [])]) for n in walk(tree)]
        return focused(tree), topology
    first = sample()
    require(first[0] != {"con_id": None, "workspace": None}, "RESTORE_FOCUS_UNAVAILABLE")
    second = sample()
    require(sway.session == session, "SWAY_SESSION_CHANGED")
    require(first == second, "RESTORE_FOCUS_UNSTABLE")
    return session, first


def command_focus(tree, target, operation):
    """WHY : une lecture post-IPC ne prouve pas la provenance du focus.

    CONTRACT : prédire depuis l'arbre AVANT la commande (Sway move.c,
    container_set_floating et swap_focus). INVARIANT : une divergence observable
    reste un conflit ; elle ne devient jamais une autorisation de refocaliser.
    """
    before = focused(tree)
    nodes = {n["id"]: n for n in walk(tree)}
    def at(identity):
        return {"con_id": identity, "workspace": location(tree, identity)[0]}
    def inactive(node, excluded=None):
        if node["id"] == excluded: return None
        if node.get("app_id") or node.get("window"): return at(node["id"])
        children = node.get("nodes", []) + node.get("floating_nodes", [])
        by_id = {n["id"]: n for n in children}
        # Sans pile IPC, une seule branche restante est déterministe.
        order = node.get("focus", list(by_id) if len(by_id) <= 1 else [])
        for identity in order:
            if identity in by_id:
                result = inactive(by_id[identity], excluded)
                if result: return result
        return None
    # WHY : seat_get_focus_inactive inclut les splits ; les parents du focus
    # sont empilés du plus proche au plus haut avant la feuille (seat.c).
    # CONTRACT : prédiction pré-IPC du retrait d'une branche vide seulement.
    # INVARIANT : conserver l'identité interne, sans élire une feuille voisine.
    if operation.startswith("move container to workspace ") and target in nodes:
        destination = json.loads(operation.removeprefix("move container to workspace "))
        if destination != before["workspace"]:
            parents = {c["id"]: n for n in nodes.values()
                       for c in n.get("nodes", []) + n.get("floating_nodes", [])}
            parent = parents.get(target)
            if before["con_id"] == target and parent and parent.get("type") == "con" and len(parent.get("nodes", [])) == 1:
                ancestors = []
                node = parents.get(parent["id"])
                while node and node.get("type") == "con":
                    ancestors.append(node)
                    node = parents.get(node["id"])
                if ancestors:
                    outer = ancestors[-1]
                    if any(n["id"] != target and (n.get("app_id") or n.get("window")) for n in walk(outer)):
                        return at(outer["id"])
            selected = nodes.get(before["con_id"])
            if selected and not (selected.get("app_id") or selected.get("window")):
                leaves = [n["id"] for n in walk(selected) if n.get("app_id") or n.get("window")]
                ws = workspace(tree, before["workspace"])
                if leaves == [target] and ws and all(n["id"] == target for n in walk(ws) if n.get("app_id") or n.get("window")):
                    return {"con_id": None, "workspace": before["workspace"]}
    if operation == "scratchpad show":
        require(target in nodes and scratchpad_state(nodes[target], location(tree, target)[0]) == "hidden", "SCRATCHPAD_SHOW_UNPROVEN")
        return {"con_id": target, "workspace": before["workspace"]}
    if operation == "move scratchpad":
        require(target in nodes and (nodes[target].get("app_id") or nodes[target].get("window")), "SCRATCHPAD_CONTAINER_UNSUPPORTED")
        source = location(tree, target)[0]
        if source == "__i3_scratch": return before
        if nodes[target].get("scratchpad_state", "none") == "none":
            # root_scratchpad_add_container always selects the inactive node of
            # the source workspace, even when an unrelated workspace had focus.
            # With floating leaf ownership there is no tiled parent fallback.
            require(nodes[target].get("floating") in ("auto_on", "user_on"), "SCRATCHPAD_FLOATING_REQUIRED")
            ws = workspace(tree, source)
            return inactive(ws, target) or {"con_id": None, "workspace": source}
        # Floating leaves only: the removal uses the same inactive focus stack
        # as move-to-workspace. No split ancestor is implicitly admitted.
        return command_focus(tree, target, 'move container to workspace "__i3_scratch"')
    if operation == "focus":
        require(target in nodes and location(tree, target)[0] != "__i3_scratch", "FOCUS_HIDDEN_SCRATCHPAD")
        return at(target)
    if operation.startswith("workspace "):
        name = json.loads(operation.removeprefix("workspace "))
        ws = workspace(tree, name)
        return (inactive(ws) if ws else None) or {"con_id": None, "workspace": name}
    if operation.startswith("swap container with con_id "):
        other = int(operation.split()[-1])
        if before["con_id"] in (target, other):
            if location(tree, target)[0] != location(tree, other)[0]:
                return {"con_id": other if before["con_id"] == target else target, "workspace": before["workspace"]}
    if (operation.startswith("move container to workspace ") or operation == "kill") and before["con_id"] == target:
        if operation != "kill" and json.loads(operation.removeprefix("move container to workspace ")) == before["workspace"]:
            return before
        parents = [n for n in nodes.values() if any(c["id"] == target for c in n.get("nodes", []) + n.get("floating_nodes", []))]
        for parent in parents + [workspace(tree, before["workspace"])]:
            if parent:
                result = inactive(parent, target)
                if result: return result
        return {"con_id": None, "workspace": before["workspace"]}
    return before


def validate(value):
    require(type(value) is dict and value.get("schema") == "labfy.session-v2-recovery" and type(value.get("version")) is int and value.get("version") in (1, 2),
            "RECOVERY_SCHEMA")
    require(value.get("status") in ("active", "complete", "recovered", "required"), "RECOVERY_SCHEMA")
    require(type(value.get("windows")) is list and len(value["windows"]) <= 256, "RECOVERY_SCHEMA")
    require(type(value.get("foreign")) is list and len(value["foreign"]) <= 256, "RECOVERY_SCHEMA")
    require(type(value.get("operations")) is int and 0 <= value["operations"] <= 4096, "RECOVERY_SCHEMA")
    require(type(value.get("session")) is str and re.fullmatch(r"[a-f0-9]{64}", value["session"]), "RECOVERY_SCHEMA")
    require(type(value.get("transaction_id")) is str and re.fullmatch(r"[a-f0-9]{32}", value["transaction_id"]), "RECOVERY_SCHEMA")
    require(value.get("stage") == "labfy-v2-stage-" + value["transaction_id"], "RECOVERY_SCHEMA")
    def text(v): return type(v) is str and 0 < len(v) <= 256 and not any(ord(c) < 32 for c in v)
    def state(v):
        require(type(v) is dict and set(v) == ({"con_id", "app_id", "pid", "starttime", "workspace", "output", "floating", "geometry", "path"} | ({"scratchpad"} if value["version"] == 2 else set())), "RECOVERY_SCHEMA")
        for k in ("con_id", "pid", "starttime"):
            require(type(v[k]) is int and 0 < v[k] < 2**63, "RECOVERY_SCHEMA")
        require(v["app_id"] is None or text(v["app_id"]), "RECOVERY_SCHEMA")
        require(text(v["workspace"]) and text(v["output"]) and type(v["floating"]) is bool, "RECOVERY_SCHEMA")
        require(type(v["path"]) is list and len(v["path"]) <= 64 and all(type(i) is int and 0 <= i <= 256 for i in v["path"]), "RECOVERY_SCHEMA")
        if value["version"] == 2:
            require(v["scratchpad"] in ("none", "hidden", "shown") and
                    (v["scratchpad"] == "none" or v["floating"]) and
                    ((v["workspace"] == "__i3_scratch") == (v["scratchpad"] == "hidden")), "RECOVERY_SCHEMA")
        g = v["geometry"]
        require((not v["floating"] and g is None) or (type(g) is dict and set(g) == {"x", "y", "width", "height"}
                and all(type(x) is int and abs(x) < 2**31 for x in g.values())), "RECOVERY_SCHEMA")
    seen = set()
    for entry in value["windows"]:
        require(type(entry) is dict and type(entry.get("pending")) is bool and type(entry.get("recovered")) is bool, "RECOVERY_SCHEMA")
        state(entry.get("origin"))
        state(entry.get("expected"))
        require(all(entry["origin"][k] == entry["expected"][k] for k in ("con_id", "app_id", "pid", "starttime")), "RECOVERY_SCHEMA")
        require(entry["origin"]["con_id"] not in seen, "RECOVERY_SCHEMA")
        seen.add(entry["origin"]["con_id"])
    for entry in value["foreign"]: state(entry)
    for key in ("focus_origin", "focus_expected"):
        f = value.get(key)
        require(type(f) is dict and set(f) == {"con_id", "workspace"}, "RECOVERY_SCHEMA")
        require(f["con_id"] is None or (type(f["con_id"]) is int and 0 < f["con_id"] < 2**63), "RECOVERY_SCHEMA")
        require(f["workspace"] is None or text(f["workspace"]), "RECOVERY_SCHEMA")
    if "focus_boundaries" in value:
        rows = value["focus_boundaries"]
        require(type(rows) is list and len(rows) <= 8, "RECOVERY_SCHEMA")
        for row in rows:
            require(type(row) is dict and set(row) == {"boundary", "expected", "observed"} and
                    text(row["boundary"]), "RECOVERY_SCHEMA")
            for key in ("expected", "observed"):
                f = row[key]
                require(type(f) is dict and set(f) == {"con_id", "workspace"}, "RECOVERY_SCHEMA")
                require(f["con_id"] is None or (type(f["con_id"]) is int and 0 < f["con_id"] < 2**63), "RECOVERY_SCHEMA")
                require(f["workspace"] is None or text(f["workspace"]), "RECOVERY_SCHEMA")
    for key in ("focus_pending", "focus_conflict"): require(type(value.get(key)) is bool, "RECOVERY_SCHEMA")
    if "path_reconciliations" in value:
        rows = value["path_reconciliations"]
        require(type(rows) is list and len(rows) <= 4, "RECOVERY_SCHEMA")
        for batch in rows:
            require(type(batch) is list and len(batch) <= 256, "RECOVERY_SCHEMA")
            for row in batch:
                require(type(row) is dict and set(row) == {"con_id", "before", "after"} and
                        type(row["con_id"]) is int and 0 < row["con_id"] < 2**63, "RECOVERY_SCHEMA")
                for key in ("before", "after"):
                    path = row[key]
                    require(type(path) is list and len(path) <= 64 and
                            all(type(i) is int and 0 <= i <= 256 for i in path), "RECOVERY_SCHEMA")
    # CONTRACT : extension facultative V1 ; l'absence dans un ancien journal
    # n'autorise jamais à reconstruire une preuve depuis l'arbre post-incident.
    if "structure_expected" in value:
        shapes = value["structure_expected"]
        require(type(shapes) is dict and len(shapes) <= 256 and all(text(k) for k in shapes), "RECOVERY_SCHEMA")
        budget = [4096]
        def shape(node, depth=0):
            budget[0] -= 1
            require(budget[0] >= 0 and depth <= 64, "RECOVERY_SCHEMA")
            if type(node) is int:
                require(0 < node < 2**63, "RECOVERY_SCHEMA")
                return
            require(type(node) is dict and len(node) == 1, "RECOVERY_SCHEMA")
            layout, children = next(iter(node.items()))
            require(layout in ("splith", "splitv", "none", "tabbed", "stacked") and
                    type(children) is list and len(children) <= 256, "RECOVERY_SCHEMA")
            for child in children: shape(child, depth + 1)
        for node in shapes.values(): shape(node)
    return value


class Recovery:
    def __init__(self, sway, runtime, tx=None, stage=None, start=process_start, proof=None):
        self.sway, self.runtime, self.start = sway, Path(runtime), start
        self.path = self.runtime / JOURNAL
        self.anchor_owned = lambda n: False
        if tx is None:
            self.data = read(self.path, validate)
        else:
            if proof is not None:
                require(focus_proof(sway) == proof, "RESTORE_FOCUS_UNSTABLE")
            tree = sway.tree()
            if proof is not None:
                require(sway.session == proof[0] and focused(tree) == proof[1][0], "RESTORE_FOCUS_UNSTABLE")
            self.data = {"schema": "labfy.session-v2-recovery", "version": 2,
                         "session": sway.session, "transaction_id": tx, "stage": stage,
                         "status": "active", "windows": [], "foreign": [], "operations": 0,
                         "focus_origin": focused(tree), "focus_expected": focused(tree),
                         "focus_pending": False, "focus_conflict": False, "intention": None}
            self.publish()
            # Un ancien succès ne décrit jamais la nouvelle transaction active.
            self.receipt("active", [], ["RECOVERY_IN_PROGRESS"])

    def receipt(self, status, windows, issues):
        value = {"status": status, "transaction_id": self.data["transaction_id"],
                 "session": self.data["session"], "stage": self.data["stage"],
                 "windows": windows, "issues": issues}
        atomic(self.runtime / RECEIPT, value)
        return value

    def publish(self): atomic(self.path, self.data, validate)

    def snapshot(self, identity, tree=None):
        tree = self.sway.tree() if tree is None else tree
        node = next((n for n in walk(tree) if n["id"] == identity and (n.get("app_id") or n.get("window"))), None)
        state = observe(tree, node, self.start) if node else None
        if state and self.data["version"] == 1:
            # Historical journals never proved scratchpad membership. Refuse an
            # observed scratchpad rather than synthesizing absent evidence.
            require(state.pop("scratchpad") == "none", "LEGACY_SCRATCHPAD_UNPROVEN")
        return state

    def pin(self, node):
        """Observation runtime avant une attente externe, sans autorité de focus.

        WHY : PID/app_id relus après un provider ne prouvent pas le starttime
        ni l'emplacement observés avant son appel. CONTRACT : session vérifiée
        autour de la lecture ; cette observation n'autorise aucun IPC et ne
        prouve pas que le processus vient de notre lancement.
        """
        require(self.sway.session == self.data["session"], "SWAY_SESSION_CHANGED")
        state = self.snapshot(node["id"])
        require(self.sway.session == self.data["session"], "SWAY_SESSION_CHANGED")
        require(state and state["pid"] == node.get("pid") and state["app_id"] == node.get("app_id"), "TARGET_IDENTITY_CHANGED")
        return state

    def admit(self, node, observed=None):
        state = self.pin(node)
        # INVARIANT : une attente provider ne peut pas remplacer la première
        # observation. L'égalité inclut identité, placement et chemin ; elle
        # est un contrôle avant admission, jamais un CAS avec la commande IPC.
        if observed is not None:
            require(state == observed, "TARGET_OBSERVATION_CHANGED")
        previous = next((e for e in self.data["windows"] if e["origin"]["con_id"] == node["id"]), None)
        if previous is not None:
            # WHY : un con_id déjà vu ne constitue pas une nouvelle admission.
            # CONTRACT : conserver l'identité runtime épinglée, y compris après
            # relecture/provider ; aucun PID/starttime remplacé n'est autorisé.
            # INVARIANT : l'origine durable n'est jamais réécrite par app_id.
            require(all(state[k] == previous["origin"][k] for k in ("con_id", "app_id", "pid", "starttime")),
                    "TARGET_IDENTITY_CHANGED")
            require(not previous["pending"] and state == previous["expected"], "RECOVERY_STATE_CHANGED")
            return
        require(len(self.data["windows"]) < 256, "RECOVERY_WINDOW_LIMIT")
        self.data["windows"].append({"origin": state, "expected": state, "pending": False, "recovered": False})
        self.publish()

    def baseline(self, allowed):
        tree = self.sway.tree()
        nodes = [n for n in walk(tree) if (n.get("app_id") or n.get("window")) and n.get("app_id") not in allowed]
        require(len(nodes) <= 256, "RECOVERY_WINDOW_LIMIT")
        self.data["foreign"] = [observe(tree, n, self.start) for n in nodes]
        self.publish()

    def record_focus_conflict(self, observation):
        # WHY : un cleanup tardif peut lui-même changer le focus et masquer
        # l'écart initial. CONTRACT : première observation durable immuable,
        # pas une preuve de causalité ; une ancienne trace reste telle quelle.
        # INVARIANT : ce diagnostic n'accorde aucune permission de mutation.
        self.data["focus_conflict"] = True
        self.data.setdefault("focus_conflict_observation", copy.deepcopy(observation))
        self.publish()

    def command(self, command):
        # Toute commande peut affecter focus/geometry (y compris un swap anchor).
        # Une observation concurrente divergente bloque avant la mutation suivante.
        require(self.data["operations"] < 4096 and len(command) <= 2048, "RECOVERY_OPERATION_LIMIT")
        tree = self.sway.tree()
        if focused(tree) != self.data["focus_expected"]:
            focus_node = next((n for n in walk(tree) if n.get("focused") and n.get("app_id")), None)
            if not focus_node or not self.anchor_owned(focus_node):
                self.record_focus_conflict({"phase": "before-command", "command": command,
                                            "before": self.data["focus_expected"], "observed": focused(tree)})
        match = re.match(r'\[con_id=(\d+)\] (.*)', command)
        target, operation = (int(match[1]), match[2]) if match else (None, command)
        expected_focus = command_focus(tree, target, operation)
        self.check_focus_preservation(tree, expected_focus, command)
        # Toutes les vérifications et prédictions précèdent l'intention durable.
        # Un refus local n'est pas un mouvement lancé ; un crash après publish
        # reste volontairement ambigu, même si l'IPC n'a pas encore répondu.
        before_tree = tree
        expected_after = {}
        for entry in self.data["windows"]:
            current = self.snapshot(entry["origin"]["con_id"], tree)
            if entry["pending"] or current != entry["expected"]:
                self.data["state_conflict_observation"] = {"command": command, "expected": entry["expected"], "observed": current}
                self.publish()
                require(False, "RECOVERY_STATE_CHANGED")
            expected_after[str(current["con_id"])] = command_postcondition(current, target, operation, tree)
        if operation == "kill" and target is not None:
            old = next((n for n in walk(tree) if n["id"] == target), None)
            require(old is not None and self.anchor_owned(old), "ANCHOR_OWNERSHIP_INVALID")
        for entry in self.data["windows"]:
            entry.update(pending=True, before=copy.deepcopy(entry["expected"]))
        self.data.update(focus_pending=True, intention={"command": command,
                         "focus_before": focused(tree), "expected_focus": expected_focus,
                         "expected_after": expected_after})
        self.data["operations"] += 1
        self.publish()
        answer = self.sway.command(command)
        if operation in ("floating enable", "scratchpad show"):
            # WHY : IPC reports pending rect before Wayland configure/commit;
            # a late initial configure can otherwise undo the next resize.
            # CONTRACT : bounded drain only where geometry is explicitly
            # compositor-owned; all predicted fields and focus are still checked
            # below, before publishing the confirmed observation. No retries of
            # a divergent command and no relaxation of final geometry equality.
            time.sleep(.3)
        if operation == "kill" and target is not None:
            # Une réponse à kill n'est pas le retrait Wayland. Attendre l'anchor
            # possédée évite de journaliser un chemin encore transitoire.
            old = next((n for n in walk(before_tree) if n["id"] == target), None)
            require(old is not None and self.anchor_owned(old), "ANCHOR_OWNERSHIP_INVALID")
            until(lambda: not any(n["id"] == target for n in self.sway.windows()))
        tree = self.sway.tree()
        before_states = [e["before"] for e in self.data["windows"] if e["origin"]["con_id"] != target]
        after_states = [self.snapshot(e["origin"]["con_id"], tree) for e in self.data["windows"] if e["origin"]["con_id"] != target]
        def order(states):
            return sorted((n["workspace"], n["path"], n["con_id"]) for n in states if n and not n["floating"])
        require([n[2] for n in order(before_states)] == [n[2] for n in order(after_states)], "RECOVERY_ORDER_CHANGED")
        for entry in self.data["windows"]:
            after = self.snapshot(entry["origin"]["con_id"], tree)
            require(after is not None and all(after[k] == entry["origin"][k] for k in ("con_id", "app_id", "pid", "starttime")), "TARGET_IDENTITY_CHANGED")
            require(all(after[k] == v for k, v in expected_after[str(after["con_id"])].items()), "RECOVERY_POSTCONDITION_FAILED")
            entry.update(expected=after, pending=False)
        self.check_command_focus(tree, expected_focus, command)
        # CONTRACT : cette preuve est post-réponse RUN_COMMAND ; elle décrit
        # l'observation, pas une exclusion de l'input concurrent.
        self.data["intention"]["focus_after"] = focused(tree)
        self.data.update(focus_expected=focused(tree), focus_pending=False, structure_expected=structure(tree))
        self.publish()
        return answer

    def boundary(self, name):
        """Observation durable bornée aux transitions du watchdog.

        WHY : SIGCONT acquitté ne prouve pas le drainage des événements d'un
        client IPC. CONTRACT : comparer avant toute nouvelle mutation ; aucune
        attribution helper/utilisateur ni nouvelle autorité de focus.
        """
        tree = self.sway.tree()
        rows = self.data.setdefault("focus_boundaries", [])
        require(len(rows) < 8, "RECOVERY_OPERATION_LIMIT")
        rows.append({"boundary": name, "expected": copy.deepcopy(self.data["focus_expected"]),
                     "observed": focused(tree)})
        self.publish()
        self.check_command_focus(tree, self.data["focus_expected"], name)

    def verify(self):
        tree = self.sway.tree()
        ws = workspace(tree, self.data["stage"])
        require(not ws or not any(n.get("app_id") or n.get("window") for n in walk(ws)), "STAGE_NOT_EMPTY")
        for old in self.data["foreign"]:
            require(placement(self.snapshot(old["con_id"], tree)) == placement(old), "FOREIGN_WINDOW_CHANGED")

    def validate_final(self, tree):
        """CONTRACT : aucune intention ambiguë ni réadmission à la clôture.

        WHY : un con_id stable ne prouve ni PID/starttime ni placement.
        INVARIANT : toutes les fenêtres gérées gardent leur identité d'origine
        et leur dernier état confirmé ; le focus attendu n'est jamais réécrit.
        """
        require(self.sway.session == self.data["session"], "SWAY_SESSION_CHANGED")
        require(not self.data["focus_pending"] and not self.data["focus_conflict"] and
                not any(e["pending"] for e in self.data["windows"]), "RECOVERY_STATE_CHANGED")
        # Le focus sur split exige une seconde lecture : celle-ci devient
        # l'observation utilisée aussi pour identités et structure finales.
        tree = self.check_command_focus(tree, self.data["focus_expected"], "final-observation")
        states = {}
        for entry in self.data["windows"]:
            current = self.snapshot(entry["origin"]["con_id"], tree)
            states[entry["origin"]["con_id"]] = current
            require(current and all(current[k] == entry["origin"][k] for k in ("con_id", "pid", "starttime", "app_id")),
                    "TARGET_IDENTITY_CHANGED")
            # WHY : Sway peut normaliser tardivement un parent unaire après
            # retrait d'ancre. CONTRACT : placement exact et ordre relatif,
            # layout canonique contrôlé par Executor, jamais chemin brut seul.
            require(placement(current) == placement(entry["expected"]), "RECOVERY_STATE_CHANGED")
        def order(states):
            return [state["con_id"] for state in sorted(states, key=lambda state: (state["workspace"], state["path"], state["con_id"]))
                    if not state["floating"]]
        require(order(e["expected"] for e in self.data["windows"]) ==
                order(states.values()), "RECOVERY_ORDER_CHANGED")
        for old in self.data["foreign"]:
            require(placement(self.snapshot(old["con_id"], tree)) == placement(old), "FOREIGN_WINDOW_CHANGED")
        return tree

    def complete(self, verify_tree=None):
        self.verify()
        # WHY : l'acquittement du guard peut encore attendre après la dernière
        # vérification Executor. CONTRACT : relire le vrai arbre avant success.
        # INVARIANT : ni un stage vide focalisé ni un changement tiers tardif
        # ne peuvent devenir final_focus_verified par simple égalité ancienne.
        tree = self.sway.tree()
        tree = self.validate_final(tree)
        # CONTRACT : Executor fournit son contrôle layout/output/slots sur cette
        # dernière observation après Guard ; aucun appel provider ensuite.
        # Ce protocole reste observationnel, jamais un CAS avec le compositeur.
        if verify_tree is not None: tree = verify_tree(tree)
        require(focused(tree)["workspace"] != self.data["stage"], "FINAL_FOCUS_IN_STAGE")
        expected = {e["origin"]["con_id"] for e in self.data["windows"]} | {e["con_id"] for e in self.data["foreign"]}
        require({n["id"] for n in walk(tree) if n.get("app_id") or n.get("window")} == expected,
                "APPLICATION_MEMBERSHIP_CHANGED")
        self.data["status"] = "complete"
        self.publish()
        self.receipt("complete", [], [])

    def recovery_command(self, text):
        tree = self.sway.tree()
        before = focused(tree)
        if before != self.data["focus_expected"]:
            self.record_focus_conflict({"phase": "before-recovery-command", "command": text,
                                        "before": self.data["focus_expected"], "observed": before})
        observed = getattr(self, "recovering_observed", None)
        if observed is not None:
            require(self.snapshot(observed["con_id"], tree) == observed, "RECOVERY_STATE_CHANGED")
        match = re.match(r'\[con_id=(\d+)\] (.*)', text)
        target, operation = (int(match[1]), match[2]) if match else (None, text)
        expected = command_postcondition(observed, target, operation, tree) if observed else None
        expected_focus = command_focus(tree, target, operation)
        self.check_focus_preservation(tree, expected_focus, text)
        require("structure_expected" not in self.data or structure(tree) == self.data["structure_expected"],
                "RECOVERY_STRUCTURE_CHANGED")
        require(self.data["operations"] < 4096 and len(text) <= 2048, "RECOVERY_OPERATION_LIMIT")
        entry = next((e for e in self.data["windows"] if observed and e["origin"]["con_id"] == observed["con_id"]), None)
        if entry is not None:
            entry.update(before=copy.deepcopy(observed), expected=copy.deepcopy(observed), pending=True)
        # Chaque sous-commande a sa propre intention durable exacte. pending
        # reste vrai jusqu'à la fin du retour : aucune relance forcée après crash.
        self.data.update(focus_pending=True, intention={"command": text,
                         "recovery_con_id": observed["con_id"] if observed else None,
                         "before": copy.deepcopy(observed), "focus_before": before,
                         "observations": [self.snapshot(e["origin"]["con_id"], tree) for e in self.data["windows"]],
                         "expected_after": expected if observed else {"focus": expected_focus},
                         "expected_focus": expected_focus})
        self.data["operations"] += 1
        self.publish()
        self.sway.command(text)
        tree = self.sway.tree()
        if observed is not None:
            after = self.snapshot(observed["con_id"], tree)
            require(after and all(after[k] == observed[k] for k in ("con_id", "app_id", "pid", "starttime")), "TARGET_IDENTITY_CHANGED")
            require(all(after[k] == v for k, v in expected.items()), "RECOVERY_POSTCONDITION_FAILED")
            self.recovering_observed = after
            entry["expected"] = after
            self.data["intention"]["observed_after"] = after
        self.check_command_focus(tree, expected_focus, text)
        self.data["intention"]["focus_after"] = focused(tree)
        self.data.update(focus_expected=focused(tree), focus_pending=False, structure_expected=structure(tree))
        self.publish()

    def check_focus_preservation(self, tree, expected, command):
        # WHY : une identité correcte ne prouve pas la conservation du focus user.
        # CONTRACT : après conflit, aucune nouvelle mutation IPC du journal,
        # même prédite neutre pour le focus ; sa provenance reste ambiguë.
        # INVARIANT : ni admission ni app_id ne lèvent un conflit durable.
        before = focused(tree)
        if before == {"con_id": None, "workspace": None} or self.data["focus_conflict"]:
            self.record_focus_conflict({"phase": "preservation", "command": command,
                                        "before": before, "predicted": expected})
            require(False, "FOCUS_RECOVERY_NOT_PROVEN")

    def check_command_focus(self, tree, expected, command):
        observed = focused(tree)
        stable = True
        # WHY : accepter un split exige que sa preuve structurale ne change
        # pas pendant la lecture. CONTRACT : deux observations bornées exactes.
        # INVARIANT : un changement d'input/parents/piles reste un conflit.
        node = next((n for n in walk(tree) if n["id"] == observed["con_id"]), None)
        if observed == expected and node and not (node.get("app_id") or node.get("window")):
            def topology(root):
                return [(n["id"], n.get("type"), n.get("focused", False), n.get("focus", []),
                         [c["id"] for c in n.get("nodes", [])],
                         [c["id"] for c in n.get("floating_nodes", [])]) for n in walk(root)]
            second = self.sway.tree()
            if focused(second) != expected or topology(second) != topology(tree):
                observed = focused(second)
                stable = False
        if not stable or observed != expected or observed == {"con_id": None, "workspace": None}:
            self.record_focus_conflict({"phase": "after-command", "command": command,
                                        "before": expected, "observed": observed})
            require(False, "RECOVERY_FOCUS_MISMATCH")
        # CONTRACT : transmettre la dernière observation au contrôle structurel,
        # plutôt que réutiliser silencieusement l'arbre antérieur au focus.
        return second if node and not (node.get("app_id") or node.get("window")) else tree

    def adjust_paths(self, previous, excluded):
        """Compaction observée due à notre retrait, sans bénir un réordonnancement.

        Les autres identités/emplacements doivent être identiques AVANT et APRÈS,
        et leur ordre relatif reste inchangé. Le chemin final d'origine n'est
        jamais une promesse de reconstruction exacte de l'arbre.
        """
        current = {identity: self.snapshot(identity) for identity in previous if identity != excluded}
        old = {identity: state for identity, state in previous.items() if identity != excluded}
        def order(states):
            groups = {}
            for identity, state in states.items():
                if state is not None and not state["floating"]:
                    groups.setdefault(state["workspace"], []).append((state["path"], identity))
            return {ws: [identity for _, identity in sorted(group)] for ws, group in groups.items()}
        if order(old) != order(current): return
        for entry in self.data["windows"]:
            identity = entry["origin"]["con_id"]
            if identity == excluded: continue
            before, after = old.get(identity), current.get(identity)
            if before == entry["expected"] and after is not None and placement(before) == placement(after):
                entry["expected"] = after

    def recover(self):
        try:
            return self._recover()
        except Exception:
            # IPC indisponible : reçu nominatif dérivé du journal validé, sans
            # IPC supplémentaire ni mouvement. Une erreur storage reste visible.
            durable = read(self.path, validate)
            require(durable["session"] == self.data["session"] and
                    durable["transaction_id"] == self.data["transaction_id"], "RECOVERY_JOURNAL_CHANGED")
            self.data = durable
            self.data["status"] = "required"
            self.publish()
            windows = [{"con_id": e["origin"]["con_id"], "app_id": e["origin"]["app_id"],
                        "workspace": e["origin"]["workspace"], "output": e["origin"]["output"],
                        "reason": "RECOVERY_OBSERVATION_UNAVAILABLE"} for e in durable["windows"] if not e["recovered"]]
            return self.receipt("RECOVERY_REQUIRED", windows, ["RECOVERY_OBSERVATION_UNAVAILABLE"])

    def equivalent_paths(self, tree):
        """Réconcilier seulement une équivalence structurelle déjà prouvée.

        INVARIANT : lot entier, identités, placement et branches doivent rester
        exacts ; aucune intention pending n'est réinterprétée. L'origine et les
        preuves d'incident restent immuables, même pour une reprise sans IPC.
        """
        if (self.data["focus_pending"] or any(e["pending"] for e in self.data["windows"]) or
                "structure_expected" not in self.data or structure(tree) != self.data["structure_expected"]):
            return
        expected = [e["expected"] for e in self.data["windows"]] + self.data["foreign"]
        nodes = [n for n in walk(tree) if n.get("app_id") or n.get("window")]
        if {n["id"] for n in nodes} != {s["con_id"] for s in expected}: return
        current = {n["id"]: observe(tree, n, self.start) for n in nodes}
        if any(placement(current[s["con_id"]]) != placement(s) for s in expected): return
        changed = [{"con_id": e["origin"]["con_id"], "before": list(e["expected"]["path"]),
                    "after": list(current[e["origin"]["con_id"]]["path"])} for e in self.data["windows"]
                   if e["expected"]["path"] != current[e["origin"]["con_id"]]["path"]]
        if not changed: return
        # WHY : réconcilier expected ne doit pas effacer la preuve exacte de la
        # commande confirmée. CONTRACT : historique avant/après durable et borné ;
        # à saturation refuser la normalisation, jamais écraser un ancien lot.
        history = self.data.setdefault("path_reconciliations", [])
        if len(history) >= 4: return
        history.append(changed)
        for entry in self.data["windows"]:
            entry["expected"] = current[entry["origin"]["con_id"]]
        self.publish()

    def _recover(self):
        if self.data["status"] in ("complete", "recovered"):
            return {"status": self.data["status"], "windows": [], "issues": []}
        issues, windows = [], []
        def issue(entry, reason):
            origin = entry["origin"]
            windows.append({"con_id": origin["con_id"], "app_id": origin["app_id"],
                            "workspace": origin["workspace"], "output": origin["output"], "reason": reason,
                            "inspect": "swaymsg -t get_tree -r", "stage": self.data["stage"],
                            "instruction": "Vérifier identité et emplacement avec get_tree ; après autorisation humaine seulement, "
                            + ("Scratchpad : examiner le journal avant toute commande." if origin.get("scratchpad", "none") != "none" else
                               f'[con_id={origin["con_id"]}] move container to workspace ' + json.dumps(origin["workspace"]))})
        if self.sway.session != self.data["session"]:
            for e in self.data["windows"]: issue(e, "SESSION_CHANGED")
            issues.append("SESSION_CHANGED")
        else:
            tree = self.sway.tree()
            recovery_focus = focused(tree)
            if recovery_focus != self.data["focus_expected"]:
                self.record_focus_conflict({"phase": "recovery-entry", "command": None,
                                            "before": self.data["focus_expected"], "observed": recovery_focus})
            # WHY : un changement de layout peut garder tous les chemins bruts
            # identiques. CONTRACT : la preuve canonique, lorsqu'elle existe,
            # doit aussi précéder une reprise, même sans normalisation de chemin.
            structure_changed = ("structure_expected" in self.data and
                                 structure(tree) != self.data["structure_expected"])
            self.equivalent_paths(tree)
            for e in self.data["windows"]:
                if e["recovered"]: continue
                try:
                    current = self.snapshot(e["origin"]["con_id"])
                    if current is None:
                        e["recovered"] = True  # Client fermé : jamais recréé ou tué.
                        self.publish()
                        continue
                    if e["pending"]: issue(e, "AMBIGUOUS_INTENTION"); continue
                    if structure_changed: issue(e, "STRUCTURE_OR_ORDER_CHANGED"); continue
                    if current != e["expected"]:
                        issue(e, "PATH_EQUIVALENCE_NOT_PROVEN" if placement(current) == placement(e["expected"])
                              else "IDENTITY_OR_MEMBERSHIP_CHANGED")
                        continue
                    origin = e["origin"]
                    if origin.get("scratchpad", "none") != "none" or current.get("scratchpad", "none") != "none":
                        if placement(current) == placement(origin):
                            e.update(recovered=True, pending=False)
                            self.publish()
                        else:
                            # WHY : no original output transform is persisted for
                            # a hidden leaf. CONTRACT : keep the client and exact
                            # journal; never show it as a speculative rollback.
                            issue(e, "SCRATCHPAD_RECOVERY_REQUIRES_REVIEW")
                        continue
                    active = {o["name"] for o in self.sway.outputs() if o.get("active")}
                    if origin["output"] not in active: issue(e, "OUTPUT_UNAVAILABLE"); continue
                    existing = workspace(self.sway.tree(), origin["workspace"])
                    if existing:
                        output = next((o["name"] for o in self.sway.tree().get("nodes", []) if any(w.get("id") == existing["id"] for w in walk(o))), None)
                        if output != origin["output"]: issue(e, "ORIGIN_OUTPUT_CHANGED"); continue
                    if self.data["focus_conflict"] and (origin["floating"] or not existing):
                        issue(e, "FOCUS_RECOVERY_NOT_PROVEN"); continue
                    # Journal de reprise avant IPC également : un crash pendant le
                    # retour devient ambigu, pas une autorisation de forcer au reboot.
                    self.recovering_observed = current
                    previous = {other["origin"]["con_id"]: self.snapshot(other["origin"]["con_id"]) for other in self.data["windows"]}
                    # Déjà à l'origine : rien à commander ni à journaliser.
                    if placement(current) == placement(origin):
                        e.update(recovered=True, pending=False)
                        self.recovering_observed = None
                        self.publish()
                        continue
                    if not existing:
                        self.recovery_command("workspace " + json.dumps(origin["workspace"]))
                        self.recovery_command("move workspace to output " + json.dumps(origin["output"]))
                    prefix = f'[con_id={origin["con_id"]}] '
                    self.recovery_command(prefix + "move container to workspace " + json.dumps(origin["workspace"]))
                    self.recovery_command(prefix + ("floating enable" if origin["floating"] else "floating disable"))
                    if origin["floating"]:
                        self.recovery_command("workspace " + json.dumps(origin["workspace"]))
                        g = origin["geometry"]
                        self.recovery_command(prefix + f'resize set width {g["width"]} px height {g["height"]} px')
                        self.recovery_command(prefix + f'move absolute position {g["x"]} px {g["y"]} px')
                    require(placement(self.snapshot(origin["con_id"])) == placement(origin), "RECOVERY_POSTCONDITION_FAILED")
                    e.update(expected=self.snapshot(origin["con_id"]), pending=False, recovered=True)
                    self.adjust_paths(previous, origin["con_id"])
                    self.recovering_observed = None
                    self.publish()
                except Exception:
                    self.recovering_observed = None
                    issue(e, "RECOVERY_IPC_OR_IDENTITY_FAILED")
            # Ne pas voler un focus déplacé pendant l'attente ; si la reprise a
            # changé le focus, sa responsabilité est connue et bornée à ce lot.
            try:
                origin_focus = self.data["focus_origin"]
                if not self.data["focus_pending"] and not self.data["focus_conflict"] and not windows:
                    target = origin_focus["con_id"]
                    if target is not None:
                        entry = next((e for e in self.data["windows"] if e["origin"]["con_id"] == target), None)
                        old = entry["origin"] if entry else next((o for o in self.data["foreign"] if o["con_id"] == target), None)
                        require(old and placement(self.snapshot(target)) == placement(old), "RECOVERY_FOCUS_IDENTITY_CHANGED")
                        self.recovery_command(f'[con_id={target}] focus')
                    elif origin_focus["workspace"]:
                        self.recovery_command("workspace " + json.dumps(origin_focus["workspace"]))
                    require(focused(self.sway.tree()) == origin_focus, "RECOVERY_FOCUS_MISMATCH")
                else: issues.append("FOCUS_RECOVERY_NOT_PROVEN")
            except Exception: issues.append("FOCUS_RECOVERY_FAILED")
            try: self.verify()
            except Exception: issues.append("STAGE_OR_FOREIGN_NOT_VERIFIED")
        self.data["status"] = "required" if windows or issues else "recovered"
        self.publish()
        receipt = {"status": "RECOVERY_REQUIRED" if windows or issues else "recovered",
                   "transaction_id": self.data["transaction_id"], "stage": self.data["stage"], "windows": windows, "issues": issues,
                   "doctor": ["Lire get_tree et get_outputs sur le socket explicitement vérifié.",
                              "Accéder au stage par son nom après accord ; ne jamais tuer le client ni relancer restore pour lire le reçu."]}
        receipt["session"] = self.data["session"]
        atomic(self.runtime / RECEIPT, receipt)
        return receipt


class RecordedSway:
    """Même IPC, autorité unique ; interception locale du journal executor."""
    def __init__(self, sway, recovery): self.raw, self.recovery = sway, recovery
    def __getattr__(self, name): return getattr(self.raw, name)
    def command(self, command): return self.recovery.command(command)


def resume_pending(sway, runtime, start=process_start):
    if not (Path(runtime) / JOURNAL).exists(): return None
    return Recovery(sway, runtime, start=start).recover()


def recovery_status(runtime):
    """Diagnostic sans IPC ni écriture ; deux fichiers ne forment pas un CAS."""
    runtime = Path(runtime)
    def unavailable(reason): return {"status": "RECOVERY_REQUIRED", "reason": reason}
    try:
        journal = read(runtime / JOURNAL, validate)
    except FileNotFoundError:
        return unavailable("RECOVERY_JOURNAL_MISSING") if (runtime / RECEIPT).exists() else {"status": "idle", "reason": "NO_RECOVERY_JOURNAL"}
    except Exception: return unavailable("RECOVERY_JOURNAL_INVALID")
    try: receipt = read(runtime / RECEIPT)
    except FileNotFoundError: return unavailable("RECOVERY_RECEIPT_MISSING")
    except Exception: return unavailable("RECOVERY_RECEIPT_INVALID")
    if not isinstance(receipt, dict): return unavailable("RECOVERY_RECEIPT_INVALID")
    if any(receipt.get(k) != journal[k] for k in ("transaction_id", "session", "stage")):
        return unavailable("RECOVERY_RECEIPT_STALE")
    expected = {"active": "active", "required": "RECOVERY_REQUIRED", "complete": "complete", "recovered": "recovered"}
    if (receipt.get("status") != expected[journal["status"]] or
            type(receipt.get("windows")) is not list or len(receipt["windows"]) > 256 or
            type(receipt.get("issues")) is not list or len(receipt["issues"]) > 256 or
            not all(type(w) is dict and type(w.get("con_id")) is int for w in receipt["windows"]) or
            not all(type(i) is str and len(i) <= 256 for i in receipt["issues"])):
        return unavailable("RECOVERY_RECEIPT_INVALID")
    # Relire le journal : un remplacement concurrent ne valide pas un reçu ancien.
    try:
        if read(runtime / JOURNAL, validate) != journal: return unavailable("RECOVERY_JOURNAL_CHANGED")
    except Exception: return unavailable("RECOVERY_JOURNAL_INVALID")
    return receipt
