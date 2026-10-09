import QtQuick
import Quickshell
import Quickshell.Wayland
import "../components"
import "../theme"

PanelWindow {
    id: window
    required property var hostScreen
    required property string kind
    required property int percent
    required property bool muted
    screen: hostScreen
    anchors { left: true; bottom: true }
    margins.left: Math.max(0, Math.round((hostScreen.width - implicitWidth) / 2))
    margins.bottom: Math.min(40, Math.max(8, Math.round(hostScreen.height / 20)))
    implicitWidth: Math.min(320, Math.max(1, hostScreen.width - 16))
    implicitHeight: 80
    exclusionMode: ExclusionMode.Ignore
    exclusiveZone: 0
    aboveWindows: true
    WlrLayershell.layer: WlrLayer.Overlay
    WlrLayershell.keyboardFocus: WlrKeyboardFocus.None
    WlrLayershell.namespace: "labfy-setting-osd"
    color: "transparent"
    // CONTRACT: Region vide au niveau de la fenêtre Wayland : ni clic, ni
    // défilement, ni glisser-déposer ne sont dirigés vers la carte.
    mask: Region { width: 0; height: 0 }

    readonly property color emphasis: kind === "brightness" ? Theme.yellow
        : muted ? Theme.danger : Theme.mauve
    readonly property string label: kind === "brightness" ? "Luminosité"
        : kind === "microphone" ? "Microphone" : "Volume"
    readonly property string glyph: kind === "brightness" ? "󰖨"
        : kind === "microphone" ? (muted ? "󰍭" : "󰍬")
        : (muted ? "󰝟" : "󰕾")

    Rectangle {
        anchors.fill: parent
        radius: 4
        // WHY: un léger aperçu du contenu reste visible sans changer de palette.
        color: Qt.rgba(Theme.popupBackground.r, Theme.popupBackground.g,
            Theme.popupBackground.b, 0.92)
        border.color: Theme.outline
        border.width: 1
        NerdIcon {
            id: icon
            anchors.left: parent.left
            anchors.leftMargin: 16
            anchors.top: parent.top
            anchors.topMargin: 13
            text: window.glyph
            color: window.emphasis
            font.pixelSize: 26
        }
        Text {
            anchors.left: icon.right
            anchors.leftMargin: 12
            anchors.verticalCenter: icon.verticalCenter
            text: window.label
            color: Theme.foreground
            font.pixelSize: 15
            font.bold: true
        }
        Text {
            anchors.right: parent.right
            anchors.rightMargin: 16
            anchors.verticalCenter: icon.verticalCenter
            text: window.kind === "microphone" ? (window.muted ? "Muet" : "Non muet")
                : window.muted ? "Muet · " + window.percent + "%" : window.percent + "%"
            color: window.muted ? Theme.danger : Theme.foreground
            font.pixelSize: 14
        }
        Rectangle {
            visible: window.kind !== "microphone"
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.leftMargin: 16
            anchors.rightMargin: 16
            anchors.bottom: parent.bottom
            anchors.bottomMargin: 15
            height: 7
            radius: 3
            color: Theme.buttonBackground
            Rectangle {
                width: Math.max(0, Math.min(1, window.percent / 100)) * parent.width
                height: parent.height
                radius: parent.radius
                color: window.emphasis
            }
        }
    }
}
