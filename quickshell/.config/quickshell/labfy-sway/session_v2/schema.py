"""Validation versionnée, exacte et référentielle avant toute mutation.

Les bornes contrôlent le travail local ; aucun ancien identifiant runtime n'est
accepté. Un état non implémenté est refusé, jamais silencieusement oublié.
"""
import re
from .errors import require

SCHEMA = "labfy.sway.session-v2"
LAYOUTS = {"splith", "splitv", "tabbed", "stacked"}
STRATEGIES = {"managed-autostart", "single-window", "multi-instance", "terminal", "browser-self-restore", "unknown"}
PROVIDER = "firefox-session-window-uuid"
UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\Z")
IDENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,95}\Z")
PLACE = re.compile(r"[A-Za-z0-9 _:-]{1,64}\Z")


def fields(value, names):
    require(type(value) is dict and set(value) == set(names.split()), "SCHEMA_FIELDS")


def integer(value, low, high):
    require(type(value) is int and low <= value <= high, "SCHEMA_INTEGER")


def text(value, pattern=IDENT):
    require(type(value) is str and pattern.fullmatch(value), "SCHEMA_STRING")


def array(value, maximum=256):
    require(type(value) is list and len(value) <= maximum, "SCHEMA_ARRAY")


def validate(data):
    fields(data, "schema version metadata outputs applications window_slots workspaces focus")
    require(data["schema"] == SCHEMA and type(data["version"]) is int and data["version"] == 1, "SCHEMA_VERSION")
    fields(data["metadata"], "created_ns sway_session reason")
    integer(data["metadata"]["created_ns"], 0, 2**63 - 1)
    text(data["metadata"]["sway_session"])
    require(data["metadata"]["reason"] in ("manual", "logout", "reboot", "poweroff"), "SCHEMA_REASON")
    for key in ("outputs", "applications", "window_slots", "workspaces"): array(data[key])
    outputs, apps, slots, workspaces = {}, {}, {}, {}
    for o in data["outputs"]:
        fields(o, "name")
        text(o["name"], PLACE)
        require(o["name"] not in outputs, "DUPLICATE_OUTPUT")
        outputs[o["name"]] = o
    for a in data["applications"]:
        fields(a, "application_id desktop_entry strategy expected_windows managed_by identity_provider")
        text(a["application_id"])
        text(a["desktop_entry"])
        require(a["desktop_entry"].endswith(".desktop"), "SCHEMA_DESKTOP_ENTRY")
        require(type(a["strategy"]) is str and a["strategy"] in STRATEGIES, "SCHEMA_STRATEGY")
        integer(a["expected_windows"], 1, 256)
        require(a["managed_by"] in (None, "autostart", "sway-autostart"), "SCHEMA_MANAGED_BY")
        require(a["identity_provider"] in (None, PROVIDER), "SCHEMA_PROVIDER")
        require(a["application_id"] not in apps, "DUPLICATE_APPLICATION")
        apps[a["application_id"]] = a
    for s in data["window_slots"]:
        fields(s, "slot_id application_id workspace tree_path state identity_requirement identity_evidence")
        text(s["slot_id"])
        text(s["application_id"])
        text(s["workspace"], PLACE)
        array(s["tree_path"], 32)
        for i in s["tree_path"]: integer(i, 0, 31)
        require(s["application_id"] in apps and s["slot_id"] not in slots, "SLOT_REFERENCE")
        require(s["identity_requirement"] in ("exact", "best-effort", "interchangeable"), "SCHEMA_IDENTITY")
        state = s["state"]
        fields(state, "floating geometry fullscreen scratchpad")
        require(type(state["floating"]) is bool, "SCHEMA_BOOLEAN")
        require(type(state["fullscreen"]) is bool and state["fullscreen"] is False and state["scratchpad"] is False,
                "CAPABILITY_UNSUPPORTED")
        if state["floating"]:
            fields(state["geometry"], "x y width height")
            for k in ("x", "y"): integer(state["geometry"][k], -100000, 100000)
            for k in ("width", "height"): integer(state["geometry"][k], 1, 32768)
            require(s["tree_path"] == [], "FLOATING_TREE_PATH")
        else: require(state["geometry"] is None, "TILING_GEOMETRY")
        evidence = s["identity_evidence"]
        if s["identity_requirement"] == "exact":
            fields(evidence, "type id")
            if evidence["type"] == PROVIDER:
                require(type(evidence["id"]) is str and UUID.fullmatch(evidence["id"]), "INVALID_UUID")
                require(apps[s["application_id"]]["identity_provider"] == PROVIDER, "PROVIDER_REFERENCE")
            else:
                require(evidence["type"] == "application-singleton" and evidence["id"] == s["application_id"] and
                        apps[s["application_id"]]["expected_windows"] == 1, "EXACT_IDENTITY_UNSUPPORTED")
        else: require(evidence is None, "SCHEMA_IDENTITY")
        slots[s["slot_id"]] = s
    seen = set()
    def tree(node, workspace, path=()):
        require(len(path) <= 32, "TREE_DEPTH")
        if node is None: return
        require(type(node) is dict, "TREE_NODE")
        if "slot_id" in node:
            fields(node, "slot_id")
            text(node["slot_id"])
            require(node["slot_id"] in slots and node["slot_id"] not in seen, "TREE_SLOT_REFERENCE")
            s = slots[node["slot_id"]]
            require(not s["state"]["floating"] and s["workspace"] == workspace and s["tree_path"] == list(path), "TREE_SLOT_POSITION")
            seen.add(node["slot_id"])
        else:
            fields(node, "layout children")
            require(type(node["layout"]) is str and node["layout"] in LAYOUTS, "TREE_LAYOUT")
            array(node["children"], 32)
            require(len(node["children"]) >= 2 and all(c is not None for c in node["children"]), "TREE_ARITY")
            for i, c in enumerate(node["children"]): tree(c, workspace, path + (i,))
    for w in data["workspaces"]:
        fields(w, "workspace output root")
        text(w["workspace"], PLACE)
        text(w["output"], PLACE)
        require(w["workspace"] not in workspaces and w["output"] in outputs, "WORKSPACE_REFERENCE")
        workspaces[w["workspace"]] = w
        tree(w["root"], w["workspace"])
    for s in slots.values():
        require(s["workspace"] in workspaces and (s["state"]["floating"] or s["slot_id"] in seen), "UNPLACED_SLOT")
    for name in workspaces:
        require(any(s["workspace"] == name for s in slots.values()), "EMPTY_WORKSPACE_UNSUPPORTED")
    for a in apps.values():
        members = [s for s in slots.values() if s["application_id"] == a["application_id"]]
        require(len(members) == a["expected_windows"], "APPLICATION_CARDINALITY")
        uuids = [s["identity_evidence"]["id"] for s in members if s["identity_evidence"] and s["identity_evidence"]["type"] == PROVIDER]
        require(len(uuids) == len(set(uuids)), "EXACT_WINDOW_IDENTITY_COLLISION")
    require(data["focus"] is None or type(data["focus"]) is str and data["focus"] in slots, "FOCUS_REFERENCE")
    return data
