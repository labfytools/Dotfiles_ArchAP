import QtQuick
import Quickshell
import Quickshell.Io
import "../components"

Item {
    id: indicator
    readonly property string statePath: Quickshell.env("XDG_RUNTIME_DIR") + "/labfy-quickshell-updates.json"
    readonly property var state: {
        const raw = snapshot.text();
        if (!raw) return { repoUpdates: 0, aurUpdates: 0, totalUpdates: 0, lastCheck: "", error: "Vérification en attente" };
        try {
            const value = JSON.parse(raw);
            if (!Number.isSafeInteger(value.repoUpdates) || value.repoUpdates < 0
                    || !Number.isSafeInteger(value.aurUpdates) || value.aurUpdates < 0
                    || value.totalUpdates !== value.repoUpdates + value.aurUpdates)
                throw new Error("État invalide");
            return value;
        } catch (error) {
            return { repoUpdates: 0, aurUpdates: 0, totalUpdates: 0, lastCheck: "", error: "État illisible" };
        }
    }
    readonly property bool hasError: Boolean(state.error)
    visible: hasError || state.totalUpdates > 0
    width: visible ? icon.width + (hasError ? 0 : count.implicitWidth + 3) + 6 : 0
    height: 26
    readonly property string detail: hasError
        ? "Impossible de vérifier les mises à jour\n" + state.error
        : state.totalUpdates + (state.totalUpdates === 1 ? " mise à jour" : " mises à jour")
            + "\n" + state.repoUpdates + " Arch\n" + state.aurUpdates + " AUR"
            + (state.lastCheck ? "\nDernière vérification : " + Qt.formatTime(new Date(state.lastCheck), "HH:mm") : "")

    // Le timer systemd publie un fichier atomique ; le renderer ne lance jamais de gestionnaire de paquets.
    FileView {
        id: snapshot
        path: indicator.statePath
        watchChanges: true
        printErrors: false
        onFileChanged: reload()
    }
    // Après un redémarrage, /run/user ne contient pas encore le fichier :
    // QFileSystemWatcher ne voit pas sa création. Réessayer seulement jusqu'au premier chargement.
    Timer {
        interval: 10000
        repeat: true
        running: !snapshot.loaded
        onTriggered: snapshot.reload()
    }
    Rectangle { anchors.fill: parent; radius: 4; color: pointer.containsMouse ? "#45475a" : "transparent" }
    NerdIcon {
        id: icon
        width: 18
        // WHY: le trait circulaire paraît plus petit que le glyphe batterie à 18 px.
        font.pixelSize: 22
        anchors.left: parent.left
        anchors.leftMargin: 3
        anchors.verticalCenter: parent.verticalCenter
        text: indicator.hasError ? "" : "󰚰"
        color: indicator.hasError ? "#fab387" : "#cba6f7"
    }
    Text {
        id: count
        anchors.left: icon.right
        anchors.leftMargin: 3
        anchors.verticalCenter: parent.verticalCenter
        visible: !indicator.hasError
        text: indicator.state.totalUpdates
        color: "#cba6f7"
        font.family: "JetBrainsMono Nerd Font Mono"
        font.pixelSize: 12
    }
    MouseArea { id: pointer; anchors.fill: parent; hoverEnabled: true; acceptedButtons: Qt.NoButton }
    StatusTooltip { target: indicator; hovered: pointer.containsMouse; message: indicator.detail }
}
