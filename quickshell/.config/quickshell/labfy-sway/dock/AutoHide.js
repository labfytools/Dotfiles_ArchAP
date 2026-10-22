.pragma library

// CONTRACT: the sole deadline belongs to arming (edge dwell) or waiting
// (exit grace). Holding any interaction cancels it. No animation sends IPC.
function next(state, event, input) {
    if (input.suppressed) return "hidden";
    if (input.held) return "held";
    if (input.body) return "shown";
    if (input.edge) {
        if (state === "hidden") return "arming";
        if (state === "arming") return event === "deadline" ? "shown" : "arming";
        return "shown";
    }
    if (state === "hidden" || state === "arming") return "hidden";
    if (state === "waiting") return event === "deadline" ? "hidden" : "waiting";
    return "waiting";
}

function influence(distance) {
    return Math.max(0, 1 - Math.abs(distance) / 115);
}
