// CONTRACT: ces fonctions choisissent des rôles de Theme, jamais des couleurs
// fixes ; les états matériels priment toujours sur l'accent décoratif.
function wifi(hardwareEnabled, enabled, connected) {
    if (!hardwareEnabled) return "disabledForeground";
    return enabled && connected ? "sky" : "secondaryForeground";
}

function bluetooth(active) {
    return active ? "blue" : "disabledForeground";
}

function battery(available, percent) {
    if (!available) return "disabledForeground";
    if (percent <= 15) return "danger";
    if (percent <= 30) return "urgentForeground";
    return "green";
}

function batteryValue(available, percent) {
    return available && percent > 30 ? "foreground" : battery(available, percent);
}

function volume(available, muted) {
    return !available || muted ? "disabledForeground" : "mauve";
}

function updates(hasError, pending) {
    return pending ? "secondaryForeground" : hasError ? "danger" : "peach";
}

function removable(hasError, busy) {
    return hasError ? "danger" : busy ? "warningForeground" : "teal";
}
