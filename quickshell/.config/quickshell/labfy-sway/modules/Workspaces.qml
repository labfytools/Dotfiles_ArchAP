import QtQuick
import Quickshell
import Quickshell.I3
import "../status"

Row {
    id: workspaces

    required property var screen

    spacing: 4
    height: 26

    Repeater {
        model: ScriptModel {
            objectProp: "key"
            values: {
                // CONTRACT: les cinq positions graphiques sont indépendantes de la
                // durée de vie des workspaces vides dans Sway. Les extras et les
                // états réels proviennent de l'IPC du moniteur courant.
                const monitors = I3.monitors.values;
                const candidates = I3.workspaces.values;
                const monitor = I3.monitorFor(workspaces.screen);
                if (monitors.length === 0 || !monitor) return [];

                const real = candidates.filter(workspace => workspace.monitor === monitor);
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
            readonly property bool active: workspace && (workspace.focused || workspace.active)
            readonly property bool urgent: workspace && workspace.urgent

            width: 24
            height: 26

            Rectangle {
                anchors.centerIn: parent
                width: button.active ? 24 : 16
                height: button.active ? 16 : 11
                radius: 4
                color: button.urgent ? "#fab387"
                    : button.active ? "#cba6f7"
                    : pointer.containsMouse ? "#6c7086" : "#585b70"
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
