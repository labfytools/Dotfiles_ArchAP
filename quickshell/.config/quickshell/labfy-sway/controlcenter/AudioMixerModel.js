.pragma library

// CONTRACT: classify only ready, tracked PipeWire audio nodes by media.class
// and direction. A capture stream or technical node cannot become playback UI.
function mediaClass(node) {
    return node && node.ready && node.properties
        ? String(node.properties["media.class"] || "") : "";
}

function outputDevices(nodes) {
    return nodes.filter(node => node && node.audio && !node.isStream && node.isSink
        && mediaClass(node) === "Audio/Sink");
}

function inputDevices(nodes) {
    return nodes.filter(node => node && node.audio && !node.isStream && !node.isSink
        && mediaClass(node) === "Audio/Source"
        && !node.properties["node.group"]
        && node.properties["node.virtual"] !== true
        && node.properties["node.virtual"] !== "true"
        && node.properties["node.monitor"] !== true
        && node.properties["node.monitor"] !== "true");
}

function playbackStreams(nodes) {
    // Keep PipeWire's insertion order. New or removed streams do not reshuffle
    // surviving controls while a user is dragging one of their sliders.
    return nodes.filter(node => node && node.audio && node.isStream
        && mediaClass(node) === "Stream/Output/Audio");
}

function deviceName(node) {
    return node ? (node.description || node.nickname || node.name || "Périphérique audio")
        : "Périphérique indisponible";
}

function streamName(node) {
    if (!node) return "Application";
    const props = node.properties || {};
    return props["application.name"] || node.description || node.name || "Application";
}

function streamDetail(node) {
    if (!node) return "";
    const name = streamName(node);
    return node.name && node.name !== name ? node.name : "Flux audio · " + node.id;
}

function streamIcon(node) {
    return node && node.properties ? String(node.properties["application.icon-name"] || "") : "";
}

function displayPercent(volume) {
    return Math.round(Number(volume) * 100);
}

function requestedVolume(percent) {
    return Math.max(0, Math.min(100, Math.round(percent))) / 100;
}
