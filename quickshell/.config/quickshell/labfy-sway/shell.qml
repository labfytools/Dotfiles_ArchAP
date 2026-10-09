//@ pragma UseQApplication
import QtQuick
import Quickshell
import Quickshell.Io
import Quickshell.I3
import "notifications"
import "idlebridge"
import "theme"

ShellRoot {
    id: shell
    property bool resizeMode: false
    // CONTRACT: une seule sélection pour toutes les barres. L'inhibition est
    // volontairement éphémère : un redémarrage de QuickShell la libère.
    property bool keepAwake: false
    property int keepAwakeMinutes: 0
    property int keepAwakeRemainingSeconds: 0
    // INVARIANT: the helper's application requests never change the user's
    // manual duration or its monotonic expiry timer.
    IdleBridgeReceiver { id: idleBridge }
    readonly property int applicationRequestCount: idleBridge.applicationRequestCount
    function setKeepAwake(minutes) {
        if (![0, 30, 60, 120].includes(minutes)) return false;
        keepAwake = true;
        keepAwakeMinutes = minutes;
        keepAwakeRemainingSeconds = minutes * 60;
        if (minutes > 0) keepAwakeElapsed.restartMs();
        return true;
    }
    function clearKeepAwake() {
        keepAwake = false;
        keepAwakeMinutes = 0;
        keepAwakeRemainingSeconds = 0;
    }
    // WHY: l'horloge monotone évite qu'un changement d'heure allonge ou
    // raccourcisse une durée choisie. Le tick ne sert qu'à publier l'affichage.
    ElapsedTimer { id: keepAwakeElapsed }
    Timer {
        interval: 1000
        repeat: true
        running: shell.keepAwake && shell.keepAwakeMinutes > 0
        onTriggered: {
            const remaining = shell.keepAwakeMinutes * 60
                - Math.floor(keepAwakeElapsed.elapsedMs() / 1000);
            if (remaining <= 0) shell.clearKeepAwake();
            else shell.keepAwakeRemainingSeconds = remaining;
        }
    }
    // CONTRACT: one owner across all output bars; opening a menu asks every
    // bar to release its other transient panels before the overlay appears.
    property string applicationsOutput: ""
    signal applicationsOpening(string output)
    function toggleApplications(output) {
        if (applicationsOutput === output) { applicationsOutput = ""; return; }
        applicationsOpening(output);
        applicationsOutput = output;
    }
    IpcHandler {
        target: "barMode"
        function active(): bool { return shell.resizeMode; }
    }
    // CONTRACT: un seul abonnement mode pour toutes les barres ; les événements
    // IPC reflètent aussi les changements déclenchés hors du clavier.
    I3IpcListener {
        subscriptions: ["mode"]
        onIpcEvent: event => {
            if (event.type !== "mode") return;
            try { shell.resizeMode = JSON.parse(event.data).change === "resize"; }
            catch (error) { console.warn("Événement mode Sway invalide", error); }
        }
    }
    // WHY: l'abonnement ne rejoue pas le mode courant après un redémarrage.
    // Une requête ponctuelle au démarrage et à la reconnexion réconcilie l'état.
    Process {
        id: modeSnapshot
        command: ["swaymsg", "-t", "get_binding_state"]
        stdout: StdioCollector { id: modeSnapshotOutput; waitForEnd: true }
        onExited: (code, status) => {
            if (code !== 0) return;
            try { shell.resizeMode = JSON.parse(modeSnapshotOutput.text).name === "resize"; }
            catch (error) { console.warn("État mode Sway invalide", error); }
        }
    }
    Component.onCompleted: modeSnapshot.running = true
    Connections {
        target: I3
        function onConnected() { if (!modeSnapshot.running) modeSnapshot.running = true; }
    }
    // CONTRACT: seul ce point d'entrée reçoit les changements live du backend.
    // Aucun état de thème n'est écrit par Theme.qml.
    IpcHandler {
        target: "appearance"
        function setTheme(flavor: string, accent: string): bool {
            return AppearanceController.applyTheme(flavor, accent);
        }
        function currentTheme(): string {
            return AppearanceController.effectiveFlavor + "/" + AppearanceController.effectiveAccent;
        }
        function effectiveState(): string {
            return AppearanceController.effectiveState();
        }
        function publishState(payload: string): bool {
            return AppearanceController.acceptPublished(payload);
        }
        function publishNightLight(payload: string): bool {
            return AppearanceController.acceptPublishedNightLight(payload);
        }
    }
    // Une barre par écran, y compris si les sorties changent pendant la session.
    // CONTRACT: un seul serveur D-Bus pour toutes les sorties.
    NotificationService { id: rootNotificationService }

    Variants {
        model: Quickshell.screens

        Bar {
            applicationCoordinator: shell
            keepAwakeController: shell
            resizeMode: shell.resizeMode
            notificationService: rootNotificationService
            // Une seule barre possède le chooser, même en configuration multi-écran.
            startupHost: Quickshell.screens.length > 0
                && modelData === Quickshell.screens[0]
        }
    }
}
