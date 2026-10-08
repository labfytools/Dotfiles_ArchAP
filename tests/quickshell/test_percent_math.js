const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const source = fs.readFileSync(path.resolve(__dirname,
    "../../quickshell/.config/quickshell/labfy-sway/controlcenter/PercentMath.js"), "utf8");
const context = {};
vm.createContext(context);
vm.runInContext(source, context);
const bounded = context.bounded;
assert.equal(bounded(-1, 0), 0);
assert.equal(bounded(35 + 1, 0), 36);
assert.equal(bounded(101, 0), 100);
assert.equal(bounded(9, 10), 10);
assert.equal(bounded(93 + 1, 10), 94);
assert.equal(bounded(101, 10), 100);
console.log("PercentMath: PASS");
