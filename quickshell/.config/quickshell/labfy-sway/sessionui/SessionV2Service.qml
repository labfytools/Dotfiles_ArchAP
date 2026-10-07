pragma Singleton
import QtQuick
import Quickshell
import Quickshell.Io

QtObject {
    id: service
    readonly property string configHome: Quickshell.env("XDG_CONFIG_HOME") || ((Quickshell.env("HOME") || "") + "/.config")
    readonly property string backend: configHome + "/quickshell/labfy-sway/session-v2.py"
    property string operation: ""
    property var client: null
    property bool startupChooserVisible: false
    readonly property bool busy: operation !== "" || backendProcess.running
    signal completed(var owner, string kind, var value, bool okay)

    // Diagnostic lecture seule ; aucun endpoint IPC ne peut cliquer Restore.
    property IpcHandler diagnostics: IpcHandler {
        target: "sessionV2"
        function status(): string {
            return JSON.stringify({backend: "v2", busy: service.busy,
                operation: service.operation, startupChooserCount: service.startupChooserVisible ? 1 : 0});
        }
    }

    // WHY : toutes les barres, le chooser et le power menu partagent un owner.
    // INVARIANT : un unique Process sérialise les commandes V2 de QuickShell.
    function run(kind, name, extra, owner) {
        if (busy) return false;
        const allowed = ["startup-status", "ack-new", "ack-restored", "apply-last", "apply", "list", "show", "save", "delete", "plan", "restore-status", "checkpoint-last"];
        if (allowed.indexOf(kind) < 0) return false;
        const argv = ["python3", "-B", backend];
        if (kind === "ack-new" || kind === "ack-restored") {
            argv.push("acknowledge-startup", "--execute", "--choice", kind === "ack-new" ? "new" : "restored");
            if (kind === "ack-restored") argv.push("--transaction-id", extra);
        } else {
            argv.push(kind);
            if (["apply", "save", "delete", "show", "plan"].indexOf(kind) >= 0) argv.push(name);
            if (["startup-status", "apply-last", "apply", "save", "delete", "checkpoint-last"].indexOf(kind) >= 0) argv.push("--execute");
            if (kind === "checkpoint-last") argv.push("--reason", extra);
        }
        client = owner;
        operation = kind;
        backendProcess.command = argv;
        backendProcess.running = true;
        return true;
    }

    property Process backendProcess: Process {
        running: false
        stdout: StdioCollector { id: collected; waitForEnd: true }
        stderr: StdioCollector { waitForEnd: true }
        onExited: (exitCode, exitStatus) => {
            let value = null;
            try { value = JSON.parse(collected.text); } catch (_) {}
            const owner = service.client;
            const kind = service.operation;
            service.operation = "";
            service.client = null;
            service.completed(owner, kind, value, exitCode === 0 && exitStatus === 0 && value !== null);
        }
    }
}
