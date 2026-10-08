const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const source = fs.readFileSync(path.resolve(__dirname,
    "../../quickshell/.config/quickshell/labfy-sway/status/ScrollSteps.js"), "utf8");
const context = {};
vm.createContext(context);
vm.runInContext(source, context);
const advance = context.advance;
const empty = () => ({ remainder: 0, source: "" });

let state = empty();
for (const part of [3, 4, 5, 7, 8]) state = advance(state, part, 0, false, 2, false);
assert.equal(state.steps, 0);
state = advance(state, 5, 120, false, 2, false);
assert.equal(state.steps, 1); // pixelDelta a priorité, sans compter angleDelta.
assert.equal(state.remainder, 0);

state = advance(empty(), 0, 120, false, 0, false);
assert.equal(state.steps, 1); // Un cran de souris = un point.
state = advance(empty(), 0, -240, false, 0, false);
assert.equal(state.steps, -2);
state = advance(empty(), -32, 0, false, 2, true);
assert.equal(state.steps, 1); // Deltas ASUS normalisés : geste haut = hausse.
state = advance(empty(), 32, 0, false, 2, true);
assert.equal(state.steps, -1); // Geste bas = baisse.
state = advance(empty(), 32, 0, true, 2, true);
assert.equal(state.steps, 1); // inverted est traité une seule fois.
state = advance(empty(), 0, -120, false, 0, true);
assert.equal(state.steps, 1); // Touchpad à delta angulaire seul.

state = advance({ remainder: 20, source: "pixel" }, -16, 0, false, 2, false);
assert.equal(state.steps, 0);
assert.equal(state.remainder, -16); // Direction inversée : ancien reliquat abandonné.
state = advance({ remainder: 20, source: "pixel" }, 0, 120, false, 0, false);
assert.equal(state.steps, 1); // Changement de source : reliquat incomparable abandonné.
state = advance({ remainder: 20, source: "pixel" }, 0, 0, false, 3, false);
assert.equal(state.remainder, 0); // Fin de geste.

state = empty();
let total = 0;
for (let i = 0; i < 320; i++) {
    state = advance(state, 1, 0, false, 2, false);
    total += state.steps;
}
assert.equal(total, 10);
assert.equal(state.remainder, 0); // Dix points réguliers, sans accélération.
console.log("ScrollSteps: PASS");
