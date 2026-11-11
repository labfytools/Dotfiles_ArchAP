.pragma library

// The favorites file remains a pure ordered list of desktop IDs. User separators
// belong to their own document and live at *gaps* between pinned applications.
function entries(applications, separators) {
    const pinned = applications.filter(entry => entry.pinned);
    const running = applications.filter(entry => !entry.pinned);
    const result = [];
    const at = new Map();
    for (const separator of (separators || [])) {
        if (!separator || !/^sep-[0-9a-f]{12}$/.test(separator.id)
                || !Number.isInteger(separator.position) || separator.position < 0)
            continue;
        const index = Math.min(pinned.length, separator.position);
        if (!at.has(index)) at.set(index, []);
        at.get(index).push({id: separator.id, kind: "separator",
                            position: separator.position,
                            name: "Séparateur", windows: [], pinned: false});
    }
    for (let i = 0; i <= pinned.length; ++i) {
        for (const sep of (at.get(i) || [])) result.push(sep);
        if (i < pinned.length) result.push(pinned[i]);
    }
    if (pinned.length && running.length)
        result.push({id: "dock-running-boundary", kind: "automatic-separator",
                     name: "Applications ouvertes", windows: [], pinned: false});
    return result.concat(running);
}

function hasSeparator(separators, position) {
    return (separators || []).some(sep => sep.position === position);
}

// A pinned icon can move relative to other pinned icons, never into an
// unpinned process or an arbitrary desktop ID.
function moveTarget(ids, id, direction) {
    const index = ids.indexOf(id);
    if (direction === -1 && index > 0) return {id: id, before: ids[index - 1]};
    if (direction === 1 && index >= 0 && index < ids.length - 1)
        return {id: id, before: ids[index + 2] || ""};
    return null;
}
