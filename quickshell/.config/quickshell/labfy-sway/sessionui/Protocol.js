.pragma library

// CONTRACT : aucun exit 0 seul ne vaut succès de restauration. L'UI attend
// toutes les postconditions et, au startup, l'ack durable de cette transaction.
function restoreSucceeded(v) {
    return !!v && v.schema === "labfy.sway.session-v2-restore-attempt"
        && v.version === 1 && v.status === "success"
        && v.final_tree_verified === true && v.final_focus_verified === true
        && Number.isInteger(v.slots_expected) && v.slots_expected === v.slots_filled
        && Number.isInteger(v.applications_expected) && v.applications_expected === v.applications_observed
        && Number.isInteger(v.anchors_created) && v.anchors_created === v.anchors_cleaned
        && Number.isInteger(v.helpers_suspended) && v.helpers_suspended === v.helpers_resumed
        && /^[a-f0-9]{32}$/.test(v.transaction_id)
        && ["exact", "interchangeable", "best-effort"].indexOf(v.identity_level) >= 0;
}

function details(v) {
    // Aucun stdout/stderr libre dans le parcours utilisateur ou dans journald.
    function code(x) { return typeof x === "string" && /^[A-Za-z_-]{1,64}$/.test(x) ? x : "UNKNOWN"; }
    return "Phase : " + code(v ? v.phase : null) + "\nRaison : " + code(v ? v.reason : null);
}
