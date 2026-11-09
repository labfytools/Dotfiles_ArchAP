pragma Singleton
import QtQuick
import QtCore
import Quickshell
import Quickshell.Io

Singleton {
    id: service
    readonly property string executable: (Quickshell.env("HOME") || "") + "/.local/bin/labfy-rgb"
    property string operation: ""
    readonly property bool busy: operation !== "" || runner.running
    property bool available: false
    property string device: ""
    // CONTRACT: these are command history, never an optical measurement or
    // hardware mode readback. Missing/failed status discards stale UI history.
    property string commandedMode: "unknown"
    property string lastColor: ""
    property int lastPercent: -1
    property string message: "État non vérifié"
    property string pendingColor: ""
    property int pendingPercent: 100
    property bool refreshPending: false
    property bool startupPending: false
    readonly property bool restoreEnabled: preferences.restoreEnabled
    readonly property var palette: [
        {name: "Violet", color: "#8000FF"}, {name: "Bleu", color: "#0040FF"},
        {name: "Cyan", color: "#00FFFF"}, {name: "Vert", color: "#00FF40"},
        {name: "Rose", color: "#FF0080"}, {name: "Rouge", color: "#FF0000"},
        {name: "Orange", color: "#FF6000"}, {name: "Jaune", color: "#FFFF00"}
    ]
    Settings {
        id: preferences
        // WHY: Settings.location is a URL; an explicit local-file URL avoids
        // falling back to unset global application/organization identifiers.
        location: "file://" + (Quickshell.env("XDG_CONFIG_HOME") || ((Quickshell.env("HOME") || "") + "/.config")) + "/labfy-rgb/quickshell.ini"
        property bool restoreEnabled: false
        property string savedColor: ""
        property int savedPercent: 100
        property string savedMode: "unknown"
    }
    function validColor(color) { return typeof color === "string" && /^#[0-9a-fA-F]{6}$/.test(color); }
    function validPercent(percent) { return Number.isInteger(percent) && percent >= 0 && percent <= 100; }
    function setRestoreEnabled(enabled) {
        preferences.restoreEnabled = enabled;
        // Only validated successful history can become a startup preference.
        if (enabled && validColor(lastColor) && validPercent(lastPercent) && commandedMode === "software") {
            preferences.savedColor = lastColor;
            preferences.savedPercent = lastPercent;
            preferences.savedMode = "software";
        }
        if (enabled && commandedMode === "firmware") preferences.savedMode = "firmware";
        preferences.sync();
    }
    function launch(kind, args) {
        if (busy) return false;
        operation = kind;
        runner.command = [executable].concat(args);
        runner.running = true;
        return true;
    }
    function refresh() { return launch("status", ["status", "--json"]); }
    // CONTRACT: a preset click immediately sends exactly set + validated color.
    // The CLI's default is 100%; subsequent intensity uses brightness explicitly.
    // Share the same admission as custom colors, never start concurrent writes.
    function preset(color) {
        if (!validColor(color) || busy) return false;
        pendingColor = color.toUpperCase(); pendingPercent = 100;
        return launch("set", ["set", pendingColor]);
    }
    function applyColor(color, percent) {
        if (!validColor(color) || !validPercent(percent) || busy) return false;
        pendingColor = color.toUpperCase(); pendingPercent = percent;
        return launch("set", ["set", pendingColor, String(percent)]);
    }
    function intensity(percent) {
        if (!validPercent(percent) || !validColor(lastColor) || busy) return false;
        pendingColor = lastColor; pendingPercent = percent;
        return launch("brightness", ["brightness", String(percent)]);
    }
    function firmware() { return launch("auto", ["auto"]); }
    function off() { return launch("off", ["off"]); }
    function finish(code, status) {
        if (!operation) return;
        const kind = operation;
        operation = "";
        const okay = code === 0 && status === 0;
        if (kind === "status") {
            let value = null;
            try { value = JSON.parse(output.text); } catch (_) {}
            const valid = okay && value && value.schema === 1 && value.available === true
                && typeof value.device === "string" && /^\/dev\/hidraw[0-9]+$/.test(value.device)
                && ["unknown", "software", "firmware"].indexOf(value.commanded_mode) >= 0;
            available = !!valid;
            device = valid ? value.device : "";
            commandedMode = valid ? value.commanded_mode : "unknown";
            lastColor = valid && validColor(value.last_color) ? value.last_color : "";
            lastPercent = valid && validPercent(value.last_percent) ? value.last_percent : -1;
            if (!valid) message = "Contrôleur indisponible ou inaccessible (code " + code + ").";
            else if (!message || message === "État non vérifié") message = "Contrôleur accessible";
            // One-shot opt-in only. No permanent polling/retry and firmware
            // preference wins over saved colors; invalid config never writes HID.
            if (valid && commandedMode === "firmware") { preferences.savedMode = "firmware"; preferences.sync(); }
            if (startupPending) {
                startupPending = false;
                if (valid && commandedMode !== "firmware" && preferences.restoreEnabled && preferences.savedMode === "software"
                    && validColor(preferences.savedColor) && validPercent(preferences.savedPercent)) {
                    pendingColor = preferences.savedColor; pendingPercent = preferences.savedPercent;
                    startupRestore.start();
                }
            }
        } else {
            message = okay ? (kind === "auto" ? "Mode ASUS demandé ; couleur physique non mesurée." : "Consigne appliquée ; résultat visuel à vérifier.")
                : "Commande refusée/échouée (code " + code + ") : " + errors.text.trim().slice(0, 240);
            if (okay) {
                if (kind === "auto") preferences.savedMode = "firmware";
                else if (kind === "set" || kind === "brightness") {
                    preferences.savedColor = pendingColor; preferences.savedPercent = pendingPercent;
                    preferences.savedMode = "software";
                } else if (kind === "off") { preferences.savedPercent = 0; }
                preferences.sync();
            } else {
                // Do not replay a formerly successful preference after an
                // uncertain hardware failure, including a recovery failure.
                preferences.savedMode = "unknown"; preferences.sync();
            }
            refreshPending = true; followup.start();
        }
    }
    Component.onCompleted: {
        startupPending = preferences.restoreEnabled;
        // The singleton is loaded by ControlCenter at session startup. A single
        // delayed check never blocks startup and never writes while opted out.
        initialCheck.start();
    }
    Timer { id: initialCheck; interval: 1500; onTriggered: service.refresh() }
    Timer { id: startupRestore; interval: 0; onTriggered: service.applyColor(service.pendingColor, service.pendingPercent) }
    Timer { id: followup; interval: 0; onTriggered: { if (service.refreshPending && !service.busy) { service.refreshPending = false; service.refresh(); } } }
    Timer { id: failedStart; interval: 0; onTriggered: { if (service.operation && !runner.running) service.finish(-1, 1); } }
    Process {
        id: runner
        stdout: StdioCollector { id: output; waitForEnd: true }
        stderr: StdioCollector { id: errors; waitForEnd: true }
        onExited: (code, status) => service.finish(code, status)
        onRunningChanged: if (!running && service.operation) failedStart.start()
    }
    // Read-only diagnostics: no IPC action can trigger color or opt-in.
    IpcHandler {
        target: "rgbKeyboard"
        function state(): string {
            return JSON.stringify({busy: service.busy, available: service.available,
                commandedMode: service.commandedMode, lastColor: service.lastColor,
                lastPercent: service.lastPercent, restoreEnabled: service.restoreEnabled,
                message: service.message});
        }
    }
}
