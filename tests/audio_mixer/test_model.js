const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const path = require("node:path");

const source = fs.readFileSync(path.join(__dirname,
    "../../quickshell/.config/quickshell/labfy-sway/controlcenter/AudioMixerModel.js"), "utf8")
    .replace(/^\.pragma library\s*\n/, "");
const model = vm.createContext({});
vm.runInContext(source, model);

function node(id, media, stream, sink, extra = {}) {
    return { id, ready: true, audio: { volume: 0.4, muted: false },
        isStream: stream, isSink: sink, name: "node-" + id,
        properties: { "media.class": media, ...extra } };
}
const output = node(1, "Audio/Sink", false, true);
const input = node(2, "Audio/Source", false, false);
const playbackA = node(3, "Stream/Output/Audio", true, true,
    { "application.name": "Test", "application.icon-name": "test-icon" });
const playbackB = node(4, "Stream/Output/Audio", true, true,
    { "application.name": "Test" });
const capture = node(5, "Stream/Input/Audio", true, false);
const internal = node(6, "Stream/Input/Audio/Internal", true, true);
const monitor = node(7, "Audio/Source", false, false, { "node.monitor": true });
const grouped = node(8, "Audio/Source", false, false, { "node.group": "loopback" });
const video = node(9, "Video/Source", false, false);
const unready = { ...node(10, "Stream/Output/Audio", true, true), ready: false };
const all = [output, input, playbackA, playbackB, capture, internal, monitor,
    grouped, video, unready];

assert.deepEqual(Array.from(model.outputDevices(all), n => n.id), [1]);
assert.deepEqual(Array.from(model.inputDevices(all), n => n.id), [2]);
assert.deepEqual(Array.from(model.playbackStreams(all), n => n.id), [3, 4]);
assert.deepEqual(Array.from(model.playbackStreams([])), []);
assert.deepEqual(Array.from(model.playbackStreams([playbackB])), [playbackB]);
assert.deepEqual(Array.from(model.playbackStreams(all.filter(n => n !== playbackA)), n => n.id), [4]);
assert.equal(model.streamName(playbackA), "Test");
assert.equal(model.streamDetail(playbackA), "node-3");
assert.equal(model.streamIcon(playbackA), "test-icon");
assert.equal(model.streamIcon(playbackB), "");
assert.equal(model.streamName(node(11, "Stream/Output/Audio", true, true)), "node-11");
assert.equal(model.deviceName(null), "Périphérique indisponible");
assert.equal(model.displayPercent(1.25), 125);
assert.equal(model.requestedVolume(-4), 0);
assert.equal(model.requestedVolume(53.6), 0.54);
assert.equal(model.requestedVolume(120), 1);
console.log("AudioMixerModel: PASS");
