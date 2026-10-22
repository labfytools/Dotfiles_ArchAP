pragma Singleton
import QtQuick
import Quickshell
import Quickshell.Io
import "ApplicationsModel.js" as Model
import "WindowModel.js" as Windows

Singleton {
    id: service
    // CONTRACT: both interfaces bind these backend-authoritative properties.
    // No UI writes ids; a failed command never leaves an optimistic favorite.
    property var ids: []
    property var apps: []
    property var windows: []
    property bool ready: false
    property bool available: false
    property string error: ""
    property string iconTheme: ""
    readonly property string backend: decodeURIComponent(Qt.resolvedUrl("backend.py").toString().replace(/^file:\/\//, ""))
    readonly property var dockEntries: Windows.entries(apps, ids, windows)
    function mutate(action, values) {
        if (!available) { error = "Service de favoris indisponible"; return; }
        bridge.write(JSON.stringify({action: action, ids: values}) + "\n");
    }
    function toggle(id) { mutate("toggle", [id]); }
    function move(id, before) { mutate("move", [id, before]); }
    function launch(id) { act("launch", id); }
    function focusWindow(id) { act("focus", id); }
    function act(kind, id) {
        // INVARIANT: callers are user-click handlers only. Neither snapshots,
        // state transitions nor animations may call this action boundary.
        if (action.running) { error = "Action en cours"; return; }
        action.command = ["python3", "-B", backend, kind, id];
        action.running = true;
    }
    Process {
        id: bridge
        command: ["python3", "-B", service.backend, "serve"]
        stdinEnabled: true
        running: true
        stdout: SplitParser {
            onRead: data => {
                try {
                    const state = JSON.parse(data);
                    service.error = state.error || "";
                    if (!state.ids) return;
                    service.ids = state.ids;
                    service.apps = Model.catalog(state.apps);
                    service.iconTheme = state.theme;
                    service.ready = true;
                    service.available = true;
                    // WHY: an existing empty file means intentionally empty.
                    // Seed only an absent file; backend repeats that check under lock.
                    if (!state.exists) service.mutate("seed", Model.initialFavorites(service.apps));
                } catch (_) { service.error = "Réponse des favoris invalide"; }
            }
        }
        onExited: { service.available = false; reconnect.start(); }
    }
    Timer { id: reconnect; interval: 1500; onTriggered: bridge.running = true }
    Process {
        id: action
        stdout: StdioCollector { id: actionReply; waitForEnd: true }
        onExited: (code, status) => {
            if (code !== 0) {
                try { service.error = JSON.parse(actionReply.text).error || "Action refusée"; }
                catch (_) { service.error = "Action refusée"; }
            }
        }
    }
    // CONTRACT: one native event subscription for all outputs. Reconcile on
    // connect and after bursts; dirty preserves events received during a query.
    property bool dirty: false
    function refreshWindows() { dirty = true; if (!snapshot.running) settle.restart(); }
    Process {
        id: subscription
        command: ["swaymsg", "-m", "-t", "subscribe", '["window","workspace","output"]']
        running: true
        stdout: SplitParser { onRead: data => service.refreshWindows() }
        onStarted: service.refreshWindows()
        onExited: { service.windows = []; reconnectEvents.restart(); }
    }
    // WHY: the native I3 listener in 0.3.2 did not resubscribe after a forced
    // socket loss in the private-compositor test. This one owned process has
    // a single restart deadline; there is no steady-state window polling.
    Timer { id: reconnectEvents; interval: 1500; onTriggered: subscription.running = true }
    Timer { id: settle; interval: 60; onTriggered: { service.dirty = false; snapshot.running = true; } }
    Timer { id: retrySnapshot; interval: 1500; onTriggered: service.refreshWindows() }
    Process {
        id: snapshot
        command: ["python3", "-B", service.backend, "windows"]
        stdout: StdioCollector { id: snapshotReply; waitForEnd: true }
        onExited: (code, status) => {
            if (code === 0) {
                try { service.windows = JSON.parse(snapshotReply.text).windows; }
                catch (_) { service.windows = []; }
            } else { service.windows = []; retrySnapshot.restart(); }
            if (service.dirty) settle.restart();
        }
    }
    Component.onCompleted: refreshWindows()
}
