import QtQuick
import Quickshell
import Quickshell.Io
import Quickshell.I3
import "../status"
import "../theme"

Row {
    id: workspaces

    required property var screen

    // WHY: le cache I3 peut perdre son inventaire tout en gardant un objet
    // activeWorkspace hors modèle. Un événement focus ne le réinsère pas.
    // CONTRACT: réconcilier avec get_workspaces au chargement, à la connexion
    // et après chaque événement workspace/output ; aucune liste statique d'extras.
    Timer {
        id: refresh
        interval: 0
        onTriggered: I3.refreshWorkspaces()
    }
    Component.onCompleted: refresh.restart()
    Connections {
        target: I3
        function onConnected() { refresh.restart(); }
        function onRawEvent(event) {
            if (event.type === "workspace" || event.type === "output")
                refresh.restart();
        }
    }

    // CONTRACT: diagnostic en lecture seule du modèle réellement affiché.
    IpcHandler {
        target: "workspacesUi-" + (workspaces.screen ? workspaces.screen.name : "")
        function state(): string {
            return JSON.stringify({output: workspaces.screen ? workspaces.screen.name : "",
                width: workspaces.width,
                buttons: workspaceModel.values.map(item => ({
                    number: item.number,
                    name: item.workspace ? item.workspace.name : String(item.number),
                    active: !!item.workspace && (item.workspace.lastIpcObject.focused === true
                        || item.workspace.lastIpcObject.visible === true)
                }))});
        }
    }

    spacing: 4
    height: 26

    Repeater {
        model: ScriptModel {
            id: workspaceModel
            objectProp: "key"
            values: {
                // CONTRACT: les cinq positions graphiques sont indépendantes de la
                // durée de vie des workspaces vides dans Sway. Les extras et les
                // états réels proviennent de l'IPC du moniteur courant.
                const candidates = I3.workspaces.values;
                const output = workspaces.screen ? workspaces.screen.name : "";
                // INVARIANT: l'identité persistante est le nom de sortie IPC,
                // pas l'identité QObject des moniteurs recréés par QuickShell.
                const real = candidates.filter(workspace => output !== ""
                    && workspace.lastIpcObject.output === output);
                const baseline = [1, 2, 3, 4, 5].map(number => ({
                    key: "number:" + number,
                    number: number,
                    workspace: real.find(workspace => workspace.number === number) || null
                }));
                const extras = real
                    .filter(workspace => workspace.number < 1 || workspace.number > 5)
                    .sort((a, b) => a.number - b.number || a.name.localeCompare(b.name))
                    // INVARIANT: les noms sans numéro (number = -1) gardent une clé
                    // distincte ; ScriptModel ne confond pas deux delegates réels.
                    .map(workspace => ({
                        key: workspace.number >= 0 ? "number:" + workspace.number : "name:" + workspace.name,
                        number: workspace.number,
                        workspace: workspace
                    }));
                return baseline.concat(extras);
            }
        }

        delegate: Item {
            id: button
            required property var modelData
            readonly property var workspace: modelData.workspace
            // WHY: les pointeurs activeWorkspace du cache peuvent désigner un
            // autre objet de même nom. Le relevé IPC porte l'état réel de Sway.
            readonly property bool active: workspace && (workspace.lastIpcObject.focused === true
                || workspace.lastIpcObject.visible === true)
            readonly property bool urgent: workspace && workspace.urgent

            width: 24
            height: 26

            Rectangle {
                anchors.centerIn: parent
                width: button.active ? 24 : 16
                height: button.active ? 16 : 11
                radius: 4
                color: button.urgent ? Theme.urgent
                    : button.active ? Theme.accent
                    : pointer.containsMouse ? Theme.disabledForeground : Theme.strongBorder
            }

            MouseArea {
                id: pointer
                anchors.fill: parent
                acceptedButtons: Qt.LeftButton
                hoverEnabled: true
                onClicked: {
                    // CONTRACT: un emplacement baseline absent crée le workspace
                    // par IPC ; les objets existants gardent leur activation native.
                    if (button.workspace) button.workspace.activate();
                    else I3.dispatch("workspace number " + button.modelData.number);
                }
            }

            StatusTooltip {
                target: button
                hovered: pointer.containsMouse
                message: button.workspace && button.modelData.number < 0
                    ? "Espace " + button.workspace.name
                    : button.workspace && button.workspace.name !== String(button.modelData.number)
                    ? "Espace " + button.modelData.number + " — " + button.workspace.name
                    : "Espace " + button.modelData.number
            }
        }
    }
}
