"""Affectation : exact reste exact ; best-effort est toujours signalé."""
from .errors import require
from .schema import PROVIDER


def assign(slots, nodes, identities=None, states=None):
    require(len(nodes) >= len(slots), "APPLICATION_WINDOWS_INCOMPLETE")
    require(len(nodes) <= len(slots), "UNEXPECTED_EXTRA_WINDOW")
    result, remaining = {}, {n["id"] for n in nodes}
    identities = identities or {}
    require(len(set(identities.values())) == len(identities), "EXACT_WINDOW_IDENTITY_COLLISION")
    for s in slots:
        if s["identity_requirement"] != "exact": continue
        evidence = s["identity_evidence"]
        if evidence["type"] == PROVIDER:
            require(evidence["id"] in identities, "EXACT_WINDOW_IDENTITY_MISSING")
            target = identities[evidence["id"]]
        else:
            require(len(nodes) == 1, "EXACT_IDENTITY_UNSUPPORTED")
            target = nodes[0]["id"]
        require(target in remaining, "EXACT_WINDOW_IDENTITY_COLLISION")
        result[s["slot_id"]] = target
        remaining.remove(target)
    # WHY : interchangeable is an explicit loss of semantic identity, never a
    # permission to expose an arbitrary hidden peer of the same application.
    # CONTRACT : preserve matching visibility first, deterministic runtime tie
    # break; exact UUID/singleton assignments above remain authoritative.
    states = states or {}
    pending = sorted((s for s in slots if s["slot_id"] not in result),
                     key=lambda s: (s.get("state", {}).get("scratchpad", "none") != "hidden", s["slot_id"]))
    for s in pending:
        desired = s.get("state", {}).get("scratchpad", "none") or "none"
        matching = [i for i in remaining if states.get(i, {}).get("scratchpad", "none") == desired]
        candidates = matching or [i for i in remaining if states.get(i, {}).get("scratchpad", "none") == "none"]
        require(candidates, "SCRATCHPAD_ASSIGNMENT_UNPROVEN")
        target = min(candidates)
        result[s["slot_id"]] = target
        remaining.remove(target)
    return result
