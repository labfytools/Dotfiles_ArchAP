"""Capture minimale, sans nom de fenêtre, chemin de document ou argv."""
import time
from .errors import require
from .schema import validate, PROVIDER
from .ipc import walk


def capture(sway, catalog, provider, reason="manual"):
    tree = sway.tree()
    def topology(node):
        # Les titres, tokens et métadonnées applicatives ne participent pas à
        # cette empreinte éphémère. Détecter aussi déplacement/focus durant capture.
        return (node.get("id"), node.get("layout"), node.get("name") if node.get("type") in ("workspace", "output") else None,
                node.get("focused"), node.get("fullscreen_mode"), node.get("floating"), node.get("rect"),
                tuple(topology(c) for c in node.get("nodes", [])), tuple(topology(c) for c in node.get("floating_nodes", [])))
    nodes = [n for n in walk(tree) if n.get("app_id") or n.get("window")]
    require(len(nodes) <= 256, "WINDOW_LIMIT")
    specs = {}
    for n in nodes:
        require(not n.get("fullscreen_mode") and n.get("scratchpad_state", "none") == "none", "CAPABILITY_UNSUPPORTED")
        specs[n["id"]] = catalog.classify(n)
    apps = {}
    identities = {}
    for s in specs.values():
        if s.application_id in apps: continue
        members = [n for n in nodes if specs[n["id"]].application_id == s.application_id]
        apps[s.application_id] = {"application_id": s.application_id, "desktop_entry": s.desktop_entry,
            "strategy": s.strategy, "expected_windows": len(members),
            "managed_by": (s.managed_by or "autostart") if s.strategy == "managed-autostart" else None, "identity_provider": s.provider}
        if s.provider == PROVIDER:
            require(provider is not None, "FIREFOX_IDENTITY_PROVIDER_UNAVAILABLE")
            identities.update({v: k for k, v in provider.capture(members).items()})
    slots, workspaces = [], []
    focused = None
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
        geometry = {k: n["rect"][k] for k in ("x", "y", "width", "height")} if floating else None
        slots.append({"slot_id": slot_id, "application_id": app.application_id, "workspace": workspace,
                      "tree_path": list(path), "state": {"floating": floating, "geometry": geometry, "fullscreen": False, "scratchpad": False},
                      "identity_requirement": requirement, "identity_evidence": evidence})
        return {"slot_id": slot_id}
    def convert(n, workspace, path=()):
        if n.get("app_id") or n.get("window"): return leaf(n, workspace, path, False)
        children = n.get("nodes", [])
        if not children: return None
        if len(children) == 1:
            require(n["layout"] in ("splith", "splitv", "none"), "SINGLE_CHILD_LAYOUT_UNSUPPORTED")
            return convert(children[0], workspace, path)
        return {"layout": n["layout"], "children": [convert(c, workspace, path + (i,)) for i, c in enumerate(children)]}
    outputs = []
    for output in tree.get("nodes", []):
        for ws in output.get("nodes", []):
            if ws.get("type") != "workspace" or not (ws.get("nodes") or ws.get("floating_nodes")): continue
            require(ws["name"] != "__i3_scratch", "CAPABILITY_UNSUPPORTED")
            root = convert(ws, ws["name"])
            for f in ws.get("floating_nodes", []):
                children = [n for n in walk(f) if n.get("app_id") or n.get("window")]
                require(len(children) == 1, "FLOATING_CONTAINER_UNSUPPORTED")
                leaf(children[0], ws["name"], (), True)
            workspaces.append({"workspace": ws["name"], "output": output["name"], "root": root})
            if output["name"] not in outputs: outputs.append(output["name"])
    # Relecture : aucun checkpoint hybride si une fenêtre apparaît/disparaît.
    require({n["id"] for n in sway.windows()} == set(specs), "SNAPSHOT_CHANGED")
    require(topology(sway.tree()) == topology(tree), "SNAPSHOT_CHANGED")
    data = {"schema": "labfy.sway.session-v2", "version": 1,
            "metadata": {"created_ns": time.time_ns(), "sway_session": sway.session, "reason": reason},
            "outputs": [{"name": n} for n in outputs], "applications": list(apps.values()),
            "window_slots": slots, "workspaces": workspaces, "focus": focused}
    return validate(data)
