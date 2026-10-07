"""Affectation : exact reste exact ; best-effort est toujours signalé."""
from .errors import require
from .schema import PROVIDER


def assign(slots, nodes, identities=None):
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
    # Ordre numérique runtime déterministe, jamais une preuve sémantique.
    for s, target in zip(sorted((s for s in slots if s["slot_id"] not in result), key=lambda x: x["slot_id"]), sorted(remaining)):
        result[s["slot_id"]] = target
    return result
