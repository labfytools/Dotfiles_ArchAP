//@ pragma UseQApplication
import QtQuick
import Quickshell
import Quickshell.Io
import Quickshell.I3
import Quickshell.Services.Polkit
import "notifications"
import "idlebridge"
import "theme"
import "polkit"
import "scratchpad"
import "osd"

ShellRoot {
    id: shell
    // WHY: distingue les générations QML du PID lors d'un incident. La
    // valeur est purement technique et n'est pas conservée au rechargement.
    readonly property string keepAwakeGeneration: String(Date.now())
    // CONTRACT: one PolkitAgent owns the native request queue for the entire
    // user session. A dialog is constructed only for its current flow.
    PolkitAgent { id: polkitAgent }
    property var polkitScreen: null
    readonly property bool authenticationActive: polkitAgent.flow !== null
    // CONTRACT: le tiroir est global ; aucune barre n'installe son propre
    // abonnement window ni son propre ordonnanceur de commandes.
    DrawerService { id: shellDrawerService; authenticationActive: shell.authenticationActive }
    OsdService { id: shellOsdService; authenticationActive: shell.authenticationActive }
    signal authenticationOpening()
    function choosePolkitScreen(output) {
        const screens = Quickshell.screens;
        polkitScreen = screens.find(screen => screen.name === output)
            || (screens.length ? screens[0] : null);
    }
    function beginPolkitPresentation() {
        polkitScreen = null;
        if (!polkitAgent.flow) {
            polkitOutput.running = false;
            return;
        }
        authenticationOpening();
        // WHY: the focused Sway workspace identifies the output at request
        // start. Later focus changes do not move the authentication surface.
        if (!polkitOutput.running) polkitOutput.running = true;
        else choosePolkitScreen("");
    }
    Connections {
        target: polkitAgent
        function onFlowChanged() { shell.beginPolkitPresentation(); }
        function onAuthenticationRequestStarted() {
            if (!polkitOutput.running && !shell.polkitScreen)
                shell.beginPolkitPresentation();
        }
    }
    Timer {
        // WHY: a missing or disconnected Sway IPC must not leave an active
        // Polkit request with no visible way to cancel it.
        interval: 500
        running: !!polkitAgent.flow && !shell.polkitScreen
        onTriggered: {
            shell.choosePolkitScreen("");
            polkitOutput.running = false;
        }
    }
    Process {
        id: polkitOutput
        command: ["swaymsg", "-t", "get_workspaces", "-r"]
        stdout: StdioCollector { id: polkitOutputData; waitForEnd: true }
        onExited: (code, status) => {
            if (!polkitAgent.flow || shell.polkitScreen) return;
            let output = "";
            if (code === 0) {
                try {
                    const focused = JSON.parse(polkitOutputData.text).find(item => item.focused);
                    output = focused ? focused.output : "";
                } catch (_) {}
            }
            shell.choosePolkitScreen(output);
        }
    }
    // INVARIANT: a vanished output moves the same flow to a surviving screen;
    // it never creates a second PolkitAgent or another request queue.
    Connections {
        target: Quickshell
        function onScreensChanged() {
            if (polkitAgent.flow && Quickshell.screens.indexOf(shell.polkitScreen) < 0)
                shell.choosePolkitScreen("");
        }
    }
    LazyLoader {
        id: polkitDialog
        active: !!polkitAgent.flow && !!shell.polkitScreen
        PolkitDialog { requestFlow: polkitAgent.flow; hostScreen: shell.polkitScreen }
    }
    IpcHandler {
        target: "polkitUi"
        function state(): string {
            return JSON.stringify({ registered: polkitAgent.isRegistered,
                active: polkitAgent.isActive, dialog: polkitDialog.active,
                screen: shell.polkitScreen ? shell.polkitScreen.name : "",
                queryRunning: polkitOutput.running });
        }
    }
    Component.onCompleted: {
        modeSnapshot.running = true;
        if (polkitAgent.flow) beginPolkitPresentation();
    }
    property bool resizeMode: false
    // CONTRACT: seules la sélection manuelle et son échéance passent d'une
    // génération QML à la suivante. Ni socket ni objet Wayland n'est conservé.
    // Un arrêt du processus ou une nouvelle session repartent désactivés.
    PersistentProperties {
        id: manualKeepAwake
        reloadableId: "manualKeepAwake"
        property bool active: false
        property int minutes: 0
        property real deadlineEpochMs: 0
        onLoaded: shell.refreshKeepAwake("chargement")
    }
    readonly property bool keepAwake: manualKeepAwake.active
    readonly property int keepAwakeMinutes: manualKeepAwake.minutes
    property int keepAwakeRemainingSeconds: 0
    // INVARIANT: the helper's application requests never change the user's
    // manual duration or its monotonic expiry timer.
    IdleBridgeReceiver { id: idleBridge }
    readonly property int applicationRequestCount: idleBridge.applicationRequestCount
    IpcHandler {
        target: "keepAwakeDiagnostics"
        function state(): string {
            // CONTRACT: diagnostic local, sans identité d'application ni
            // contenu de fenêtre. L'état applicatif vient toujours du pont.
            return JSON.stringify({ generation: shell.keepAwakeGeneration,
                manual: shell.keepAwake, minutes: shell.keepAwakeMinutes,
                deadlineEpochMs: manualKeepAwake.deadlineEpochMs,
                remainingSeconds: shell.keepAwakeRemainingSeconds,
                applicationRequests: shell.applicationRequestCount });
        }
    }
    function setKeepAwake(minutes) {
        if (![0, 30, 60, 120].includes(minutes)) return false;
        // INVARIANT: l'échéance est écrite avant l'activation, afin qu'un
        // rechargement ne redémarre jamais une durée entière.
        manualKeepAwake.deadlineEpochMs = minutes ? Date.now() + minutes * 60000 : 0;
        manualKeepAwake.minutes = minutes;
        manualKeepAwake.active = true;
        keepAwakeRemainingSeconds = minutes * 60;
        console.info("Maintien manuel activé", minutes === 0 ? "illimité" : minutes + " min",
                     "échéance", manualKeepAwake.deadlineEpochMs);
        return true;
    }
    function clearKeepAwake(reason) {
        if (manualKeepAwake.active)
            console.info("Maintien manuel désactivé", reason || "action utilisateur");
        manualKeepAwake.active = false;
        manualKeepAwake.minutes = 0;
        manualKeepAwake.deadlineEpochMs = 0;
        keepAwakeRemainingSeconds = 0;
    }
    function refreshKeepAwake(reason) {
        if (!manualKeepAwake.active) return;
        if (manualKeepAwake.minutes === 0) {
            keepAwakeRemainingSeconds = 0;
        } else {
            // WHY: une date absolue survit au rechargement, contrairement à
            // ElapsedTimer. Elle empêche la réactivation d'une durée expirée.
            const remaining = Math.ceil((manualKeepAwake.deadlineEpochMs - Date.now()) / 1000);
            if (remaining <= 0) {
                clearKeepAwake("échéance atteinte pendant " + reason);
                return;
            }
            keepAwakeRemainingSeconds = remaining;
        }
        if (reason === "chargement")
            console.info("Maintien manuel restauré", manualKeepAwake.minutes === 0
                         ? "illimité" : manualKeepAwake.minutes + " min",
                         "échéance", manualKeepAwake.deadlineEpochMs);
    }
    // CONTRACT: un seul tick dans ShellRoot publie le temps restant. Chaque
    // barre lit cet état ; aucune n'avance séparément le compte à rebours.
    Timer {
        interval: 1000
        repeat: true
        running: shell.keepAwake && shell.keepAwakeMinutes > 0
        onTriggered: shell.refreshKeepAwake("minuteur")
    }
    // CONTRACT: one owner across all output bars; opening a menu asks every
    // bar to release its other transient panels before the overlay appears.
    property string applicationsOutput: ""
    signal applicationsOpening(string output)
    function toggleApplications(output) {
        if (authenticationActive) return;
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
            drawerService: shellDrawerService
            osdService: shellOsdService
            applicationCoordinator: shell
            authenticationActive: shell.authenticationActive
            keepAwakeController: shell
            resizeMode: shell.resizeMode
            notificationService: rootNotificationService
            // Une seule barre possède le chooser, même en configuration multi-écran.
            startupHost: Quickshell.screens.length > 0
                && modelData === Quickshell.screens[0]
        }
    }
}
