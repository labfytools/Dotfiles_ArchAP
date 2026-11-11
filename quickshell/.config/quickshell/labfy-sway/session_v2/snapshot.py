"""Capture minimale, sans nom de fenêtre, chemin de document ou argv."""
import time
from .errors import require
from .schema import validate, PROVIDER
from .ipc import walk, location, surface_identity


def capture(sway, catalog, provider, reason="manual"):
    tree = sway.tree()
    def topology(node):
        # Les titres, tokens et métadonnées applicatives ne participent pas à
        # cette empreinte éphémère. Détecter aussi déplacement/focus durant capture.
        return (node.get("id"), node.get("layout"), node.get("name") if node.get("type") in ("workspace", "output") else None,
                surface_identity(node), node.get("window"), node.get("pid"), node.get("scratchpad_state", "none"), node.get("focused"), node.get("fullscreen_mode"), node.get("floating"), node.get("rect"),
                tuple(topology(c) for c in node.get("nodes", [])), tuple(topology(c) for c in node.get("floating_nodes", [])))
    nodes = [n for n in walk(tree) if n.get("app_id") or n.get("window")]
    require(len(nodes) <= 256, "WINDOW_LIMIT")
    specs = {}
    for n in nodes:
        require(not n.get("fullscreen_mode"), "CAPABILITY_UNSUPPORTED")
        require(n.get("scratchpad_state", "none") in ("none", "fresh", "changed"), "SCRATCHPAD_STATE_UNSUPPORTED")
        specs[n["id"]] = catalog.classify(n)
    apps = {}
    identities = {}
    for s in specs.values():
        if s.application_id in apps: continue
        members = [n for n in nodes if specs[n["id"]].application_id == s.application_id]
        require(s.strategy != "single-window" or len(members) == 1, "APPLICATION_POLICY_MISMATCH")
        apps[s.application_id] = {"application_id": s.application_id, "desktop_entry": s.desktop_entry,
            "strategy": s.strategy, "expected_windows": len(members),
            "managed_by": (s.managed_by or "autostart") if s.strategy == "managed-autostart" else None, "identity_provider": s.provider}
        if s.provider == PROVIDER:
            require(provider is not None, "FIREFOX_IDENTITY_PROVIDER_UNAVAILABLE")
            identities.update({v: k for k, v in provider.capture(members).items()})
    slots, workspaces = [], []
    focused = None
    selected = [n for n in walk(tree) if n.get("focused")]
    # Une layer-shell (notamment le dialogue de logout) peut prendre le focus
    # et ne laisser aucune feuille/workspace marqué focused dans GET_TREE.
    # Capturer explicitement l'inconnu, jamais déduire une cible d'une pile IPC.
    require(len(selected) <= 1, "SNAPSHOT_FOCUS_AMBIGUOUS")
    focus_workspace = None
    if selected:
        focus_location = location(tree, selected[0]["id"])
        require(focus_location and focus_location[0] and focus_location[0] != "__i3_scratch", "SNAPSHOT_FOCUS_AMBIGUOUS")
        focus_workspace = focus_location[0]
    def leaf(n, workspace, path, floating):
        nonlocal focused
        app = specs[n["id"]]
        slot_id = "slot-" + str(len(slots) + 1)
        if app.provider == PROVIDER:
            require(n["id"] in identities, "EXACT_WINDOW_IDENTITY_MISSING")
            requirement, evidence = "exact", {"type": PROVIDER, "id": identities[n["id"]]}
        elif apps[app.application_id]["expected_windows"] == 1:
            requirement, evidence = "exact", {"type": "application-singleton", "id": app.application_id}
        else: requirement, evidence = "interchangeable", None
        if n.get("focused"): focused = slot_id
        scratchpad = "none" if n.get("scratchpad_state", "none") == "none" else ("hidden" if workspace is None else "shown")
        require(workspace is not None or scratchpad == "hidden", "SCRATCHPAD_STATE_UNSUPPORTED")
        require(scratchpad == "none" or floating, "SCRATCHPAD_FLOATING_REQUIRED")
        if floating:
            require(type(n.get("rect")) is dict and all(k in n["rect"] for k in ("x", "y", "width", "height")), "SNAPSHOT_GEOMETRY_MISSING")
        geometry = {k: n["rect"][k] for k in ("x", "y", "width", "height")} if floating else None
        slots.append({"slot_id": slot_id, "application_id": app.application_id, "workspace": workspace,
                      "tree_path": list(path), "state": {"floating": floating, "geometry": geometry, "fullscreen": False, "scratchpad": scratchpad},
                      "identity_requirement": requirement, "identity_evidence": evidence})
        return {"slot_id": slot_id}
    def convert(n, workspace, path=()):
        if n.get("app_id") or n.get("window"): return leaf(n, workspace, path, False)
        children = n.get("nodes", [])
        if not children: return None
        # Sway peut conserver un onglet ou une pile avec une seule fenêtre.
        # Ne normaliser que les parents splith/splitv/none : les conteneurs
        # tabbed/stacked unaires portent un choix de présentation à restaurer.
        if len(children) == 1 and n["layout"] in ("splith", "splitv", "none"):
            return convert(children[0], workspace, path)
        require(n["layout"] in ("splith", "splitv", "tabbed", "stacked"), "TREE_LAYOUT")
        return {"layout": n["layout"], "children": [convert(c, workspace, path + (i,)) for i, c in enumerate(children)]}
    outputs = []
    for output in tree.get("nodes", []):
        for ws in output.get("nodes", []):
            if ws.get("type") != "workspace" or not (ws.get("nodes") or ws.get("floating_nodes") or ws.get("name") == focus_workspace): continue
            if ws["name"] == "__i3_scratch":
                require(not ws.get("nodes"), "SCRATCHPAD_CONTAINER_UNSUPPORTED")
                for f in ws.get("floating_nodes", []):
                    require(f.get("app_id") or f.get("window"), "SCRATCHPAD_CONTAINER_UNSUPPORTED")
                    leaf(f, None, (), True)
                continue
            root = convert(ws, ws["name"])
            for f in ws.get("floating_nodes", []):
                children = [n for n in walk(f) if n.get("app_id") or n.get("window")]
                require(len(children) == 1, "FLOATING_CONTAINER_UNSUPPORTED")
                require(children[0] is f, "FLOATING_CONTAINER_UNSUPPORTED")
                leaf(children[0], ws["name"], (), True)
            workspaces.append({"workspace": ws["name"], "output": output["name"], "root": root})
            if output["name"] not in outputs: outputs.append(output["name"])
    require(len(slots) == len(nodes), "SNAPSHOT_UNPLACED_WINDOW")
    # Relecture : aucun checkpoint hybride si une fenêtre apparaît/disparaît.
    require({n["id"] for n in sway.windows()} == set(specs), "SNAPSHOT_CHANGED")
    require(topology(sway.tree()) == topology(tree), "SNAPSHOT_CHANGED")
    data = {"schema": "labfy.sway.session-v2", "version": 2,
            "metadata": {"created_ns": time.time_ns(), "sway_session": sway.session, "reason": reason},
            "outputs": [{"name": n} for n in outputs], "applications": list(apps.values()),
            "window_slots": slots, "workspaces": workspaces, "focus": focused, "focus_workspace": focus_workspace}
    return validate(data)
