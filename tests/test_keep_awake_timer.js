// Run with node tests/test_keep_awake_timer.js.
// CONTRACT: execute production function bodies with a controlled clock;
// only PersistentProperties are shared between simulated ShellRoot generations.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const path = require("node:path");
const root = path.resolve(__dirname, "..");
const source = fs.readFileSync(path.join(root, "quickshell/.config/quickshell/labfy-sway/shell.qml"), "utf8");
const bar = fs.readFileSync(path.join(root, "quickshell/.config/quickshell/labfy-sway/Bar.qml"), "utf8");
const page = fs.readFileSync(path.join(root, "quickshell/.config/quickshell/labfy-sway/controlcenter/KeepAwakePage.qml"), "utf8");
const indicator = fs.readFileSync(path.join(root, "quickshell/.config/quickshell/labfy-sway/status/KeepAwakeIndicator.qml"), "utf8");

function body(signature) {
    const marker = `function ${signature}`;
    const start = source.indexOf(marker);
    assert.notEqual(start, -1);
    const open = source.indexOf("{", start + marker.length);
    let depth = 0;
    for (let i = open; i < source.length; i++) {
        if (source[i] === "{") depth++;
        else if (source[i] === "}" && --depth === 0) return source.slice(open + 1, i);
    }
    throw new Error(`unclosed ${signature}`);
}
const set = body("setKeepAwake(minutes)");
const clear = body("clearKeepAwake(reason)");
const refresh = body("refreshKeepAwake(reason)");

function fixture() {
    let now = 0;
    const saved = { active: false, minutes: 0, deadlineEpochMs: 0 };
    function generation(requestCount = 0) {
        const state = { manualKeepAwake: saved, keepAwakeRemainingSeconds: 0,
            applicationRequestCount: requestCount, Date: { now: () => now },
            console: { info() {} } };
        Object.defineProperties(state, {
            keepAwake: { get: () => saved.active },
            keepAwakeMinutes: { get: () => saved.minutes }
        });
        state.shell = state;
        vm.createContext(state);
        vm.runInContext(`function setKeepAwake(minutes) {${set}}
            function clearKeepAwake(reason) {${clear}}
            function refreshKeepAwake(reason) {${refresh}}`, state);
        state.refreshKeepAwake("chargement");
        return state;
    }
    return { generation, advance(ms) { now = ms; } };
}

for (const seconds of [60, 130, 300, 360, 600]) {
    const clock = fixture();
    let state = clock.generation();
    assert.equal(state.setKeepAwake(0), true);
    clock.advance(seconds * 1000);
    state = clock.generation();
    assert.equal(state.keepAwake, true, `unlimited at ${seconds}s`);
}

for (const minutes of [30, 60, 120]) {
    const clock = fixture();
    let state = clock.generation();
    state.setKeepAwake(minutes);
    const deadline = state.manualKeepAwake.deadlineEpochMs;
    clock.advance(minutes * 30000);
    state = clock.generation();
    assert.equal(state.keepAwake, true);
    assert.equal(state.manualKeepAwake.deadlineEpochMs, deadline);
    assert.equal(state.keepAwakeRemainingSeconds, minutes * 30);
    clock.advance(deadline - 1);
    state.refreshKeepAwake("minuteur");
    assert.equal(state.keepAwake, true);
    assert.equal(state.keepAwakeRemainingSeconds, 1);
    clock.advance(deadline);
    state.refreshKeepAwake("minuteur");
    assert.equal(state.keepAwake, false);
    assert.equal(state.keepAwakeRemainingSeconds, 0);
}

{
    const clock = fixture();
    let state = clock.generation();
    state.setKeepAwake(0);
    for (let i = 1; i <= 3; i++) {
        clock.advance(i * 130000);
        state = clock.generation();
        assert.equal(state.keepAwake, true);
    }
    state.applicationRequestCount = 1;
    state.clearKeepAwake();
    assert.equal(state.keepAwake, false);
    assert.equal(state.applicationRequestCount, 1);
}

{
    const clock = fixture();
    let state = clock.generation(1);
    state.setKeepAwake(30);
    clock.advance(1800000);
    state = clock.generation(1);
    assert.equal(state.keepAwake, false, "expired during reload");
    assert.equal(state.applicationRequestCount, 1);
}

assert.match(source, /PersistentProperties\s*\{[\s\S]*?reloadableId:\s*"manualKeepAwake"/);
assert.match(source, /running:\s*shell\.keepAwake\s*&&\s*shell\.keepAwakeMinutes\s*>\s*0/);
assert.equal((source.match(/function refreshKeepAwake\(reason\)/g) || []).length, 1);
assert.doesNotMatch(page, /Component\.onCompleted|Timer\s*\{|ElapsedTimer/);
assert.match(bar, /enabled:\s*bar\.startupHost\s*&&\s*\(bar\.keepAwakeController\.keepAwake\s*\|\|\s*bar\.keepAwakeController\.applicationRequestCount\s*>\s*0\)/);
assert.match(indicator, /readonly property bool active: manualActive \|\| automaticActive/);
assert.match(indicator, /width: 26/);
console.log("keep-awake timer: controlled-clock and reload checks passed");
