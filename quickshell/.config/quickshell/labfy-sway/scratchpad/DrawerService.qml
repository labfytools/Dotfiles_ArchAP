import QtQuick
import Quickshell
import Quickshell.I3
import Quickshell.I3._Ipc
import Quickshell.Io

Item {
    id: service
    property var entries: []
    property int focusedId: 0
    property string error: ""
    property bool authenticationActive: false
    property bool reading: false
    property bool pending: false
    property bool busy: actionProcess.running
    readonly property string backend: (Quickshell.env("XDG_CONFIG_HOME") ||
        (Quickshell.env("HOME") + "/.config")) + "/quickshell/labfy-sway/scratchpad/backend.py"

    // CONTRACT: une seule file d'opérations dans le ShellRoot sérialise même
    // deux clics arrivés depuis des barres différentes. Le backend relit Sway.
    function act(action, id, output) {
        if (authenticationActive || actionProcess.running || !Number.isSafeInteger(id) || id <= 0)
            return false;
        error = "";
        actionProcess.command = ["python3", "-B", backend, action, String(id), output || ""];
        actionProcess.running = true;
        return true;
    }
    // WHY: un titre animé ne doit pas repousser indéfiniment le relevé ; la
    // première notification ouvre une fenêtre de coalescence fixe.
    function refresh() { if (!refreshDelay.running) refreshDelay.start(); }
    Timer {
        id: refreshDelay
        interval: 90
        onTriggered: {
            if (service.reading) service.pending = true;
            else {
                service.reading = true;
                listProcess.running = true;
            }
        }
    }
    Process {
        id: listProcess
        command: ["python3", "-B", service.backend, "list"]
        stdout: StdioCollector { id: listOutput; waitForEnd: true }
        onExited: (code, status) => {
            if (code === 0) {
                try {
                    const state = JSON.parse(listOutput.text);
                    service.entries = state.entries;
                    service.focusedId = state.focused;
                }
                catch (error) { console.warn("Tiroir Sway illisible :", error); }
            }
            service.reading = false;
            if (service.pending) {
                service.pending = false;
                service.refresh();
            }
        }
    }
    Process {
        id: actionProcess
        stdout: StdioCollector { id: actionOutput; waitForEnd: true }
        onExited: (code, status) => {
            if (code !== 0) {
                try { service.error = JSON.parse(actionOutput.text).error; }
                catch (_) { service.error = "Action sur le tiroir impossible"; }
            }
            service.refresh();
        }
    }
    I3IpcListener {
        subscriptions: ["window"]
        onIpcEvent: event => service.refresh()
    }
    Connections {
        target: I3
        function onConnected() { service.refresh(); }
        function onRawEvent(event) {
            if (event.type === "workspace" || event.type === "output") service.refresh();
        }
    }
    Component.onCompleted: refresh()
}
