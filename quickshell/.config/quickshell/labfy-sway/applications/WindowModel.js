.pragma library

function match(apps, window) {
    // CONTRACT: declared identities only, never titles. Exact desktop stem
    // wins; an ambiguous executable/WM_CLASS alias must remain unknown.
    const keys = [window.appId, window.wmClass, window.instance]
        .filter(Boolean).map(value => value.toLowerCase());
    for (const key of keys) {
        const exact = apps.filter(app => app.id.slice(0, -8).toLowerCase() === key);
        if (exact.length === 1) return exact[0];
        const aliases = apps.filter(app => (app.aliases || []).includes(key));
        if (aliases.length === 1) return aliases[0];
    }
    return null;
}

function entries(apps, ids, windows) {
    const byId = new Map(apps.map(app => [app.id, app]));
    const result = ids.map(id => Object.assign({}, byId.get(id) || {
        id: id, name: id.replace(/\.desktop$/, "") + " (indisponible)",
        iconSource: "", newInstance: false, missing: true
    }, {pinned: true, windows: []}));
    const groups = new Map(result.map(entry => [entry.id, entry]));
    for (const window of windows) {
        const app = match(apps, window);
        const id = app ? app.id : "window:" + (window.appId || window.wmClass || window.id);
        if (!groups.has(id)) {
            const entry = Object.assign({}, app || {id: id, name: window.appId || window.wmClass || "Application",
                iconSource: "", missing: true, newInstance: false}, {pinned: false, windows: []});
            groups.set(id, entry); result.push(entry);
        }
        groups.get(id).windows.push(window);
    }
    return result;
}
