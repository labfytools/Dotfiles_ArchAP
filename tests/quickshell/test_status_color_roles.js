const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const source = fs.readFileSync(path.resolve(__dirname,
    "../../quickshell/.config/quickshell/labfy-sway/status/StatusColorRoles.js"), "utf8");
const roles = {};
vm.createContext(roles);
vm.runInContext(source, roles);

assert.equal(roles.wifi(true, true, true), "sky");
assert.equal(roles.wifi(true, true, false), "secondaryForeground");
assert.equal(roles.wifi(true, false, true), "secondaryForeground");
assert.equal(roles.wifi(false, true, true), "disabledForeground");
assert.equal(roles.bluetooth(true), "blue");
assert.equal(roles.bluetooth(false), "disabledForeground");

assert.equal(roles.battery(false, 60), "disabledForeground");
assert.equal(roles.battery(true, 15), "danger");
assert.equal(roles.battery(true, 16), "urgentForeground");
assert.equal(roles.battery(true, 30), "urgentForeground");
assert.equal(roles.battery(true, 31), "green");
assert.equal(roles.batteryValue(true, 15), "danger");
assert.equal(roles.batteryValue(true, 30), "urgentForeground");
assert.equal(roles.batteryValue(true, 31), "foreground");
assert.equal(roles.batteryValue(false, 0), "disabledForeground");

assert.equal(roles.volume(true, false), "mauve");
assert.equal(roles.volume(true, true), "disabledForeground");
assert.equal(roles.volume(false, false), "disabledForeground");
assert.equal(roles.updates(false, false), "peach");
assert.equal(roles.updates(true, false), "danger");
assert.equal(roles.updates(true, true), "secondaryForeground");
assert.equal(roles.removable(false, false), "teal");
assert.equal(roles.removable(false, true), "warningForeground");
assert.equal(roles.removable(true, true), "danger");

console.log("StatusColorRoles: PASS");
