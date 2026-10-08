.pragma library

const categoryRules = [
    { key: "Internet", icon: "󰖟", tags: ["Network", "WebBrowser", "Email", "InstantMessaging"] },
    { key: "Multimédia", icon: "󰎆", tags: ["AudioVideo", "Audio", "Video", "Player", "Recorder"] },
    { key: "Développement", icon: "󰅩", tags: ["Development", "IDE", "GUIDesigner"] },
    { key: "Bureautique", icon: "󰈙", tags: ["Office", "WordProcessor", "Spreadsheet", "Presentation"] },
    { key: "Graphisme", icon: "󰏘", tags: ["Graphics", "Photography", "2DGraphics", "3DGraphics"] },
    { key: "Système", icon: "󰒓", tags: ["System", "Settings", "Monitor"] },
    { key: "Utilitaires", icon: "󰐱", tags: ["Utility", "FileManager", "TextEditor"] },
    { key: "Jeux", icon: "󰊗", tags: ["Game"] }
];

function fold(value) {
    return String(value || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLocaleLowerCase();
}

function classify(entry) {
    const tags = entry.categories || [];
    for (const rule of categoryRules)
        if (rule.tags.some(tag => tags.includes(tag))) return rule.key;
    return "Autres";
}

function catalog(entries) {
    const seen = new Set();
    return entries.filter(entry => entry && entry.id && !entry.noDisplay && !seen.has(entry.id)
            && seen.add(entry.id))
        // QuickShell 0.3.1 exposes the stem; Gio launch and durable favorites
        // use the full desktop ID. Normalize once before crossing that boundary.
        .map(entry => ({ id: entry.id.endsWith(".desktop") ? entry.id : entry.id + ".desktop",
            name: entry.name || entry.id,
            genericName: entry.genericName || "", keywords: entry.keywords || [],
            icon: entry.icon || "", category: classify(entry) }))
        .sort((a, b) => a.name.localeCompare(b.name, "fr", { sensitivity: "base" }) || a.id.localeCompare(b.id));
}

function categories(entries) {
    const present = new Set(entries.map(entry => entry.category));
    return categoryRules.filter(rule => present.has(rule.key))
        .concat(present.has("Autres") ? [{ key: "Autres", icon: "󰌗" }] : []);
}

function results(entries, selected, query, favoriteIds) {
    const needle = fold(query.trim());
    if (needle) return entries.filter(entry =>
        [entry.name, entry.genericName].concat(entry.keywords).some(value => fold(value).includes(needle)));
    if (selected === "Favoris") {
        const byId = new Map(entries.map(entry => [entry.id, entry]));
        return favoriteIds.map(id => byId.get(id)).filter(Boolean);
    }
    if (selected === "Toutes") return entries;
    return entries.filter(entry => entry.category === selected);
}

function initialFavorites(entries) {
    const names = ["firefox", "kitty", "yazi file manager", "neovim"];
    return names.map(name => entries.find(entry => fold(entry.name) === name))
        .filter(Boolean).map(entry => entry.id);
}
