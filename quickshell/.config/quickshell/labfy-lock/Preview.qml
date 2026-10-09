import QtQuick
import Quickshell
import Quickshell.Wayland

// TEST_ONLY: this file cannot acquire a session lock and never creates PAM.
// All preview content is synthetic; the production wrapper selects shell.qml.
ShellRoot {
    PanelWindow {
        id: preview
        screen: Quickshell.screens[0]
        anchors { left: true; right: true; top: true; bottom: true }
        exclusionMode: ExclusionMode.Ignore
        WlrLayershell.layer: WlrLayer.Overlay
        WlrLayershell.namespace: "labfy-lock-preview-non-locked"
        color: "#1e1e2e"

        readonly property string scenario: Quickshell.env("LABFY_LOCK_PREVIEW_SCENARIO") || "both"
        readonly property bool mediaPresent: ["both", "media", "long", "noart"].includes(scenario)
        // TEST_ONLY: the override lets the fixture exercise long/invalid URIs
        // using a copy of its own synthetic cover; production ignores it.
        readonly property string artUri: Quickshell.env("LABFY_LOCK_PREVIEW_ART_URI")
            || Qt.resolvedUrl("preview-cover.png").toString()
        readonly property bool notificationsPresent: ["both", "notifications", "long"].includes(scenario)
        readonly property bool batteryPresent: Quickshell.env("LABFY_LOCK_PREVIEW_BATTERY") !== "absent"
        readonly property string feedback: Quickshell.env("LABFY_LOCK_PREVIEW_FEEDBACK") === "error"
            ? "Authentification refusée. Appuyez sur Entrée pour réessayer."
            : Quickshell.env("LABFY_LOCK_PREVIEW_FEEDBACK") === "pam"
                ? "Message PAM de démonstration." : ""
        readonly property bool feedbackIsError: Quickshell.env("LABFY_LOCK_PREVIEW_FEEDBACK") === "error"
        readonly property bool capsOn: Quickshell.env("LABFY_LOCK_PREVIEW_CAPS") === "on"
        readonly property bool promptMode: Quickshell.env("LABFY_LOCK_PREVIEW_FEEDBACK") === "prompt"
        readonly property var dummySurface: ({ secure: preview.promptMode })
        readonly property var dummyController: ({
            displayName: "Compte de démonstration", loginUser: "demo", avatar: "",
            attempt: preview.promptMode,
            activeSurface: preview.promptMode ? preview.dummySurface : null,
            secure: preview.promptMode,
            pamResponseRequired: preview.promptMode, prompt: preview.promptMode ? "Mot de passe" : "",
            responseVisible: false, aborting: false, keyboardLayout: "Français",
            capsObserved: preview.capsOn, capsOn: preview.capsOn,
            feedback: preview.feedback, feedbackIsError: preview.feedbackIsError,
            submit: function() {}, cancel: function() {}, chooseSurface: function() {}
        })
        readonly property var dummyPlayer: mediaPresent ? ({
            trackTitle: scenario === "long" ? "Un titre synthétique très long pour vérifier que le texte reste dans la carte sans déplacer les commandes" : "Morceau de démonstration",
            trackArtist: "Artiste fictif",
            trackArtUrl: scenario === "noart" ? "" : preview.artUri,
            isPlaying: true,
            canGoPrevious: true, canTogglePlaying: true, canGoNext: true,
            positionSupported: false, length: 0
        }) : null
        readonly property var dummyNotifications: notificationsPresent ? ({
            total: 3, apps: [
                { name: scenario === "long" ? "Application de démonstration au nom volontairement très long" : "Messagerie fictive", count: 2, icon: "mail-unread" },
                { name: "Agenda fictif", count: 1, icon: "x-office-calendar" }
            ]
        }) : null
        readonly property var dummyBattery: batteryPresent ? ({ isPresent: true, percentage: 0.73, state: -1 }) : null

        LockContent {
            anchors.fill: parent
            preview: true
            previewState: ({ time: "18:42", date: "Vendredi 9 octobre", mediaMode: "metadata" })
            controller: preview.dummyController
            hostSurface: preview.dummySurface
            player: preview.dummyPlayer
            notificationData: preview.dummyNotifications
            battery: preview.dummyBattery
        }
        Rectangle {
            anchors.top: parent.top
            anchors.horizontalCenter: parent.horizontalCenter
            width: warning.implicitWidth + 24; height: 30
            color: "#1e1e2e"; border.color: "#f38ba8"; radius: 4
            Text {
                id: warning
                anchors.centerIn: parent
                text: "APERÇU — NON VERROUILLÉ"
                color: "#f38ba8"; font.pixelSize: 14; font.bold: true
            }
        }
    }
}
