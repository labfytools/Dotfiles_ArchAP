import QtQuick
import Quickshell
import Quickshell.Io

Scope {
    id: service
    property string state: "error"
    property string problem: "Vérification de Hyprwhspr"
    property string phase: ""
    property bool commandBusy: false
    property bool refreshPending: false
    property string commandError: ""
    readonly property string tooltip: problem || (state === "recording"
        ? "Dictée en cours" : state === "processing" ? "Transcription en cours" : "Dictée inactive")
    readonly property int pollInterval: state === "recording" || state === "processing" ? 400 : 1000

    // WHY: status returns Idle/0 even with no daemon. Service availability is
    // checked first; only exact installed CLI responses can confirm recording.
    // INVARIANT: one child at a time, no queued polls and no optimistic toggle.
    function launch(kind, argv) {
        phase = kind;
        runner.command = ["timeout", "--signal=TERM", "--kill-after=1s", "3s"].concat(argv);
        runner.running = true;
    }
    function refresh() {
        if (runner.running) { refreshPending = true; return; }
        poll.stop();
        refreshPending = false;
        launch("availability", ["systemctl", "--user", "is-active", "hyprwhspr.service"]);
    }
    function toggle() {
        if (commandBusy) return;
        commandBusy = true;
        commandError = "";
        poll.stop();
        // CONTRACT: defer a click until an in-flight read exits; never overlap
        // commands, and retain the click lock until the confirming read ends.
        if (!runner.running) launch("toggle", ["hyprwhspr", "record", "toggle"]);
    }
    function finish() {
        phase = "";
        commandBusy = false;
        if (commandError) { state = "error"; problem = commandError; commandError = ""; }
        if (refreshPending) refresh();
        else poll.restart();
    }
    function completed(code, output) {
        if (commandBusy && phase !== "toggle" && phase !== "confirm" && phase !== "confirmStatus") {
            launch("toggle", ["hyprwhspr", "record", "toggle"]);
            return;
        }
        if (phase === "toggle") {
            // WHY: installed CLI reports send_control failures as [ERROR] but
            // can exit 0. Never equate exit success with daemon confirmation.
            if (code !== 0 || output.indexOf("[ERROR]") >= 0
                    || !/^\[SUCCESS\] Recording (started|stopped)$/.test(output))
                commandError = "Échec de la commande Hyprwhspr";
            launch("confirm", ["systemctl", "--user", "is-active", "hyprwhspr.service"]);
        } else if (phase === "availability" || phase === "confirm") {
            if (code !== 0 || output !== "active") {
                state = "error";
                problem = "Service Hyprwhspr indisponible";
                finish();
            } else {
                launch("status", ["hyprwhspr", "record", "status"]);
                // Distinguish confirmation from an interrupted background read.
                if (commandBusy) phase = "confirmStatus";
            }
        } else {
            if (code === 0 && output === "[INFO] Status: Recording in progress") {
                state = "recording"; problem = "";
            } else if (code === 0 && output === "[INFO] Status: Idle") {
                // CONTRACT: only the native OSD marker proves processing; an
                // absent marker means no observable transcription state.
                const visual = visualizer.text().trim();
                state = visual === "processing" ? "processing" : visual === "error" ? "error" : "idle";
                problem = visual === "error" ? "Erreur de transcription Hyprwhspr" : "";
            } else {
                state = "error"; problem = "État Hyprwhspr illisible ou délai dépassé";
            }
            finish();
        }
    }
    Process {
        id: runner
        // CONTRACT: capture control/status text only; never log stdout/stderr,
        // audio or transcription. timeout bounds each invocation's lifetime.
        stdout: StdioCollector { id: output; waitForEnd: true }
        stderr: StdioCollector { }
        onExited: (code, status) => service.completed(code, output.text.trim())
    }
    FileView {
        // Native change notification accelerates keyboard/automatic stops.
        // Polling is still required for missing/recreated files and service loss.
        path: Quickshell.env("XDG_RUNTIME_DIR") ? Quickshell.env("XDG_RUNTIME_DIR")
            + "/hyprwhspr/recording_status" : ""
        watchChanges: true
        printErrors: false
        onFileChanged: { reload(); service.refresh(); }
    }
    FileView {
        id: visualizer
        path: Quickshell.env("XDG_RUNTIME_DIR") ? Quickshell.env("XDG_RUNTIME_DIR")
            + "/hyprwhspr/visualizer_state" : ""
        watchChanges: true
        printErrors: false
        // WHY: this file contains state labels only. Never read transcript_preview.
        onFileChanged: { reload(); service.refresh(); }
        onLoaded: service.refresh()
    }
    Timer { id: poll; interval: service.pollInterval; onTriggered: service.refresh() }
    Component.onCompleted: refresh()
    IpcHandler {
        target: "dictationStatus"
        // Read-only diagnosis: no IPC entry point can start a recording.
        function state(): string {
            return JSON.stringify({state: service.state, tooltip: service.tooltip,
                busy: service.commandBusy, running: runner.running,
                interval: service.pollInterval});
        }
    }
}
