import QtQuick
import QtQuick.Controls
import Quickshell
import Quickshell.Wayland
import "../theme"

PanelWindow {
    id: window
    required property var requestFlow
    required property var hostScreen
    readonly property var flow: requestFlow
    readonly property Item card: form
    screen: hostScreen
    anchors { top: true; bottom: true; left: true; right: true }
    exclusionMode: ExclusionMode.Ignore
    exclusiveZone: 0
    aboveWindows: true
    WlrLayershell.layer: WlrLayer.Overlay
    WlrLayershell.keyboardFocus: WlrKeyboardFocus.Exclusive
    WlrLayershell.namespace: "labfy-polkit-authentication"
    color: "transparent"

    // WHY: Sway gives keyboard focus to an exclusive layer surface. The
    // surface exists only for this flow and never dismisses on outside click.
    Rectangle {
        id: frame
        anchors.centerIn: parent
        width: Math.max(0, Math.min(480, parent.width - 32))
        height: Math.max(0, Math.min(form.implicitHeight, parent.height - 32))
        radius: 4
        color: Theme.popupBackground
        border.color: Theme.outline
        border.width: 1
        clip: true
        ScrollView {
            anchors.fill: parent
            contentWidth: availableWidth
            PolkitCard {
                id: form
                width: parent.width
                height: implicitHeight
                flow: window.flow
            }
        }
    }
    Timer { interval: 120; running: true; onTriggered: form.focusResponse() }
    Component.onDestruction: form.clearResponse()
}
