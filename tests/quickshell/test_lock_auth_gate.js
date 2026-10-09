const fs = require('fs');
const vm = require('vm');
const assert = require('assert');
const source = fs.readFileSync('quickshell/.config/quickshell/labfy-lock/AuthGate.js', 'utf8');
const context = vm.createContext({});
vm.runInContext(source, context);
const allowed = context.mayUnlock;
const Success = 0, Failed = 1, Error = 2, MaxTries = 3;
assert.equal(allowed(true, false, true, Success, Success), true);
for (const result of [Failed, Error, MaxTries])
    assert.equal(allowed(true, false, true, result, Success), false);
assert.equal(allowed(true, true, true, Success, Success), false); // late result after abort
assert.equal(allowed(false, false, true, Success, Success), false); // inactive generation
assert.equal(allowed(true, false, false, Success, Success), false); // not secure
