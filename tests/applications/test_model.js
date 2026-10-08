const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const path = require("node:path");

const source = fs.readFileSync(path.join(__dirname,
    "../../quickshell/.config/quickshell/labfy-sway/applications/ApplicationsModel.js"), "utf8")
    .replace(/^\.pragma library\s*\n/, "");
const context = vm.createContext({});
vm.runInContext(source, context);
const entries = context.catalog([
    { id: "firefox.desktop", name: "Firefox", genericName: "Navigateur Web", keywords: ["Internet"], categories: ["Network"], icon: "firefox" },
    { id: "nvim.desktop", name: "Éditeur", genericName: "Texte", keywords: ["Code"], categories: ["Development"] },
    { id: "hidden.desktop", name: "Hidden", noDisplay: true, categories: ["Game"] },
    { id: "firefox.desktop", name: "Duplicate", categories: ["Utility"] },
    { id: "other.desktop", name: "Mystère", categories: [] }
]);
assert.equal(entries.length, 3);
assert.equal(context.catalog([{ id: "fixture", name: "Fixture" }])[0].id,
    "fixture.desktop");
assert.equal(context.categories(entries).length, 3);
assert.equal(context.results(entries, "Développement", "", []).length, 1);
assert.equal(context.results(entries, "Développement", "navigateur", []).length, 1);
assert.equal(context.results(entries, "Toutes", "editeur", []).length, 1);
assert.equal(context.results(entries, "Toutes", "absent", []).length, 0);
assert.equal(context.results(entries, "Favoris", "", ["removed.desktop", "firefox.desktop"])[0].id,
    "firefox.desktop");
assert.equal(context.initialFavorites([{ id: "kitty.desktop", name: "kitty" }])[0],
    "kitty.desktop");
console.log("ApplicationsModel: PASS");
