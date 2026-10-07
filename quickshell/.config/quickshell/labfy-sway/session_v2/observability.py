"""Journal runtime borné, sans texte externe ni contenu de navigation."""
from .storage import atomic
from .errors import require
import math
import re
from .schema import UUID, PROVIDER

FIELDS = "schema version transaction_id phase status reason applications_expected applications_observed slots_expected slots_filled anchors_created anchors_swapped anchors_cleaned helpers_suspended helpers_resumed providers identity_resolutions identity_level final_tree_verified final_focus_verified timings_ms".split()


def validate(value):
    require(type(value) is dict and set(value) == set(FIELDS), "REPORT_SCHEMA")
    require(value["schema"] == "labfy.sway.session-v2-restore-attempt" and type(value["version"]) is int and value["version"] == 1, "REPORT_SCHEMA")
    require(type(value["transaction_id"]) is str and re.fullmatch(r"[a-f0-9]{32}", value["transaction_id"]), "REPORT_SCHEMA")
    require(value["status"] in ("running", "success", "failed", "interrupted"), "REPORT_SCHEMA")
    for key in ("phase", "reason"):
        require(type(value[key]) is str and re.fullmatch(r"[A-Za-z_-]{1,64}", value[key]), "REPORT_SCHEMA")
    for key in ("applications_expected", "applications_observed", "slots_expected", "slots_filled", "anchors_created", "anchors_swapped", "anchors_cleaned", "helpers_suspended", "helpers_resumed"):
        require(type(value[key]) is int and 0 <= value[key] <= 256, "REPORT_SCHEMA")
    require(value["providers"] in ([], [PROVIDER]), "REPORT_SCHEMA")
    require(value["identity_level"] in ("exact", "interchangeable", "best-effort"), "REPORT_SCHEMA")
    for key in ("final_tree_verified", "final_focus_verified"): require(type(value[key]) is bool, "REPORT_SCHEMA")
    require(type(value["identity_resolutions"]) is list and len(value["identity_resolutions"]) <= 256, "REPORT_SCHEMA")
    for r in value["identity_resolutions"]:
        require(type(r) is dict and set(r) == {"uuid", "con_id"} and type(r["uuid"]) is str and UUID.fullmatch(r["uuid"]) and
                type(r["con_id"]) is int and 0 < r["con_id"] < 2**63, "REPORT_SCHEMA")
    require(type(value["timings_ms"]) is dict and set(value["timings_ms"]).issubset({"anchor_build", "swap", "cleanup", "verification", "application_wait"}), "REPORT_SCHEMA")
    for v in value["timings_ms"].values(): require(type(v) in (float, int) and math.isfinite(v) and 0 <= v <= 1e6, "REPORT_SCHEMA")
    return value


class Attempt:
    def __init__(self, path, tx, data):
        self.path = path
        self.data = {"schema": "labfy.sway.session-v2-restore-attempt", "version": 1,
                     "transaction_id": tx, "phase": "validate", "status": "running", "reason": "NONE",
                     "applications_expected": len(data["applications"]), "applications_observed": 0,
                     "slots_expected": len(data["window_slots"]), "slots_filled": 0,
                     "anchors_created": 0, "anchors_swapped": 0, "anchors_cleaned": 0,
                     "helpers_suspended": 0, "helpers_resumed": 0, "providers": [], "identity_resolutions": [],
                     "identity_level": "best-effort" if any(s["identity_requirement"] == "best-effort" for s in data["window_slots"]) else
                                       "interchangeable" if any(s["identity_requirement"] == "interchangeable" for s in data["window_slots"]) else "exact",
                     "final_tree_verified": False, "final_focus_verified": False, "timings_ms": {}}
        self.publish()

    def publish(self): atomic(self.path, self.data, validate)
    def update(self, **values):
        require(set(values).issubset(FIELDS), "REPORT_SCHEMA")
        self.data.update(values)
        self.publish()
