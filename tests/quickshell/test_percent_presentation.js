const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const source = fs.readFileSync(path.resolve(__dirname,
    "../../quickshell/.config/quickshell/labfy-sway/status/PercentPresentation.js"), "utf8");
const context = {};
vm.createContext(context);
vm.runInContext(source, context);
for (const value of [9, 10, 99, 100])
    assert.equal(context.label(true, value), `${value} %`);
assert.equal(context.label(false, 0), "—");
console.log("PercentPresentation: PASS");
