import QtQuick
import "../components"
import "../theme"

Item {
    id: indicator
    required property bool manualActive
    required property bool automaticActive
    required property bool unlimited
    required property int remainingSeconds
    signal activated()
    // CONTRACT: la tasse occupe toujours sa place ; sa couleur décrit l'état
    // combiné sans modifier les deux propriétaires de l'inhibition Wayland.
    readonly property bool active: manualActive || automaticActive
    readonly property string detail: manualActive
        ? "Maintien manuel · " + (unlimited ? "jusqu’à désactivation"
            : Math.ceil(remainingSeconds / 60) + " min restantes")
            + (automaticActive ? "\nMaintien automatique demandé par une application" : "")
        : automaticActive ? "Maintien automatique demandé par une application"
            : "Maintenir éveillé · désactivé"
    width: 26
    height: 26

    NerdIcon {
        anchors.centerIn: parent
        text: "󰅶"
        font.pixelSize: 22
        color: indicator.active ? Theme.red : Theme.foreground
    }
    MouseArea {
        id: pointer
        anchors.fill: parent
        hoverEnabled: true
        onClicked: indicator.activated()
    }
    StatusTooltip {
        target: indicator
        hovered: pointer.containsMouse
        message: indicator.detail
    }
}
