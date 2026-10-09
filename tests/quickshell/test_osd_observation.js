const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const source = fs.readFileSync(path.resolve(__dirname,
    "../../quickshell/.config/quickshell/labfy-sway/osd/Observation.js"), "utf8")
    .replace(/^\.pragma library\s*/, "");
const model = {};
vm.createContext(model);
vm.runInContext(source, model);

const sink = {};
let result = model.observe(null, sink, true, 0.57, false);
assert.equal(result.changed, false); // Première lecture : référence seulement.
result = model.observe(result.state, sink, true, 0.57, false);
assert.equal(result.changed, false);
result = model.observe(result.state, sink, true, 0.571, false);
assert.equal(result.volumeChanged, true); // Même pourcentage arrondi, autre valeur brute.
result = model.observe(result.state, sink, true, 0.571, true);
assert.equal(result.muteChanged, true);
let microphone = model.observe(null, "source A", true, 0.36, false);
assert.equal(microphone.changed, false); // Page Audio jamais ouverte.
microphone = model.observe(microphone.state, "source A", true, 0.36, true);
assert.equal(microphone.muteChanged, true);
microphone = model.observe(microphone.state, "source B", true, 0.2, false);
assert.equal(microphone.changed, false);
result = model.observe(result.state, {}, true, 0.25, false);
assert.equal(result.changed, false); // Nouveau défaut : état initial ignoré.
result = model.observe(result.state, null, false, NaN, false);
assert.equal(result.state, null);
result = model.observe(result.state, sink, true, 0.57, false);
assert.equal(result.changed, false); // Reconnexion : nouvelle référence.

const screen = { name: "sortie-test" };
let card = model.nextCard(null, "volume", 57, false, screen, 0);
card = model.nextCard(card, "volume", 58, false, screen, 500);
assert.equal(card.deadline, 2000);
assert.equal(model.expire(card, 1, 1500), false);
card = model.nextCard(card, "brightness", 42, false, screen, 800);
assert.equal(card.kind, "brightness");
assert.equal(model.expire(card, 2, 2000), false); // Ancien timer.
assert.equal(model.expire(card, 3, 2299), false);
assert.equal(model.expire(card, 3, 2300), true);
const other = { name: "autre-sortie" };
assert.equal(model.screenForEvent([screen, other], other.name, null, "volume", 0), other);
assert.equal(model.screenForEvent([screen, other], other.name,
    { kind: "volume", screen, until: 100 }, "volume", 50), screen);
assert.equal(model.screenForEvent([screen, other], other.name,
    { kind: "volume", screen, until: 100 }, "volume", 101), other);
assert.equal(model.pageShows("brightness", 0), true);
assert.equal(model.pageShows("microphone", 0), false);
assert.equal(model.pageShows("microphone", 15), true);
console.log("OSD observation et minuteur: PASS");
