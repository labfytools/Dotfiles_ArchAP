import QtQuick
import Quickshell
import Quickshell.Io
import Quickshell.Wayland
import Quickshell.Services.Pam
import "AuthGate.js" as AuthGate

ShellRoot {
    id: root
    // CONTRACT: this process never reloads its code while it owns a session lock.
    Component.onCompleted: Quickshell.watchFiles = false
    readonly property string generation: String(Quickshell.env("LABFY_LOCK_GENERATION") || "")
    readonly property string loginUser: String(Quickshell.env("LABFY_LOCK_USER") || Quickshell.env("USER") || "")
    readonly property string displayName: String(Quickshell.env("LABFY_LOCK_DISPLAY") || loginUser)
    readonly property string avatar: String(Quickshell.env("LABFY_LOCK_AVATAR") || "")
    property FileView captureGuard: FileView {
        path: (Quickshell.env("XDG_RUNTIME_DIR") || "") + "/labfy-lock.capture-guard"
        blockWrites: true
        atomicWrites: true
    }
    property var surfaces: []
    property var activeSurface: null
    property bool attempt: false
    property bool aborting: false
    property bool responding: false
    property bool authorized: false
    property string feedback: ""
    property bool feedbackIsError: false
    property string keyboardLayout: ""
    property bool capsObserved: false
    property bool capsOn: false
    readonly property bool pamResponseRequired: pam.responseRequired
    readonly property bool responseVisible: pam.responseVisible
    readonly property string prompt: pam.message

    function addSurface(surface) {
        surfaces = surfaces.concat([surface]);
        if (!activeSurface) chooseSurface(surface);
    }
    function removeSurface(surface) {
        surfaces = surfaces.filter(item => item !== surface);
        if (activeSurface === surface) {
            activeSurface = null;
            if (surfaces.length) chooseSurface(surfaces[0]);
        }
    }
    function chooseSurface(surface) {
        if (activeSurface && activeSurface.field) activeSurface.field.text = "";
        activeSurface = surface;
        if (surface && surface.field) Qt.callLater(() => surface.field.forceActiveFocus());
    }
    function cancel() {
        if (activeSurface && activeSurface.field) activeSurface.field.text = "";
        if (attempt && pam.active) {
            aborting = true;
            pam.abort();
        }
        feedback = "Saisie effacée.";
        feedbackIsError = false;
    }
    function startAuthentication() {
        if (!lock.secure || attempt || authorized || aborting) return;
        attempt = true;
        feedback = "";
        feedbackIsError = false;
        if (!pam.start()) {
            attempt = false;
            feedback = "Authentification indisponible.";
            feedbackIsError = true;
        }
    }
    function submit(value) {
        if (!lock.secure || authorized || aborting || responding) return;
        if (!attempt) startAuthentication();
        // INVARIANT: an early Enter cannot discard a secret before PAM asks for it.
        if (!attempt || !pam.responseRequired) return;
        // CONTRACT: an empty submission leaves the current PAM prompt pending.
        if (value.length === 0) return;
        responding = true;
        pam.respond(value);
        if (activeSurface && activeSurface.field) activeSurface.field.text = "";
        responding = false;
    }

    // INVARIANT: no IPC method mutates the lock. A caller only observes this
    // exact process generation and compositor confirmation.
    IpcHandler {
        target: "lock"
        function state(): string {
            return root.generation + ":" + (lock.secure && lock.locked ? "secure" : "pending");
        }
    }
    Process {
        // WHY: Sway exposes the active layout, but not a reliable initial
        // CapsLock state in get_inputs. We report the latter only after a key event.
        command: ["swaymsg", "-t", "get_inputs", "-r"]
        running: true
        stdout: StdioCollector { id: inputData; waitForEnd: true }
        onExited: (code, status) => {
            if (code !== 0 || inputData.text.length > 65536) return;
            try {
                const inputs = JSON.parse(inputData.text);
                const keyboard = inputs.find(item => item.type === "keyboard"
                    && item.identifier && item.identifier.includes("AT_Translated"))
                    || inputs.find(item => item.type === "keyboard" && item.xkb_active_layout_name);
                if (keyboard && typeof keyboard.xkb_active_layout_name === "string")
                    root.keyboardLayout = keyboard.xkb_active_layout_name.slice(0, 48);
            } catch (_) {}
        }
    }

    PamContext {
        id: pam
        // CONTRACT: la politique auth dédiée reprend « auth include login » ;
        // le fichier appartient à root sous /etc/pam.d/labfy-lock.
        config: "labfy-lock"
        user: root.loginUser
        onPamMessage: {
            // CONTRACT: a PAM response prompt is already shown above the field;
            // only informational messages and actual errors use the lower line.
            root.feedback = pam.responseRequired && !pam.messageIsError ? "" : pam.message;
            root.feedbackIsError = pam.messageIsError;
            root.responding = false;
            if (root.activeSurface && root.activeSurface.field)
                Qt.callLater(() => root.activeSurface.field.forceActiveFocus());
        }
        onError: error => {
            root.feedback = "Erreur d’authentification.";
            root.feedbackIsError = true;
        }
        onCompleted: result => {
            const valid = AuthGate.mayUnlock(root.attempt, root.aborting,
                lock.secure, result, PamResult.Success);
            root.attempt = false;
            root.responding = false;
            root.aborting = false;
            if (root.activeSurface && root.activeSurface.field) root.activeSurface.field.text = "";
            if (valid) {
                root.authorized = true;
                // CONTRACT: QuickShell releases this Wayland session lock by
                // changing its locked property after PAM succeeds.
                lock.locked = false;
            } else {
                root.feedback = result === PamResult.MaxTries
                    ? "Nombre maximal de tentatives atteint."
                    : "Authentification refusée. Appuyez sur Entrée pour réessayer.";
                root.feedbackIsError = true;
            }
        }
    }

    // WHY: the surface component is instantiated by QuickShell for every
    // compositor output, including outputs plugged in after acquisition.
    WlSessionLock {
        id: lock
        locked: true
        onLockStateChanged: {
            // CONTRACT: an acquisition refusal cannot leave an inert second
            // locker occupying the wrapper's singleton record.
            if (!locked && !root.authorized) Qt.quit();
        }
        onSecureStateChanged: {
            if (!secure && root.authorized) {
                // CONTRACT: exit only after the authenticated unlock has
                // removed compositor protection, so the next request is fresh.
                root.captureGuard.setText("released\n");
                Qt.quit();
                return;
            }
            if (secure) {
                // WHY: PAM is ready before the user types the first password.
                root.startAuthentication();
                if (root.activeSurface && root.activeSurface.field)
                    Qt.callLater(() => root.activeSurface.field.forceActiveFocus());
            }
        }
        LockSurface { controller: root; secure: lock.secure }
    }
}
