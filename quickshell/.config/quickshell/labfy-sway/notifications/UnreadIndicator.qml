import QtQuick
import "../components"

Item {
    id: indicator
    required property int unreadCount
    required property int criticalUnreadCount
    required property bool inverted

    // CONTRACT: cette zone est réservée même à zéro; Clock gère le fond et l'interaction.
    visible: unreadCount > 0
    width: 36
    height: 26

    Row {
        anchors.centerIn: parent
        spacing: 3
        NerdIcon {
            id: bell
            // Le glyphe fa-bell est présent dans JetBrainsMono Nerd Font Mono.
            text: ""
            color: indicator.inverted ? "#1e1e2e"
                : indicator.criticalUnreadCount > 0 ? "#f38ba8" : "#cba6f7"
            // CONTRACT: la cloche gagne en lisibilité sans agrandir le badge ni déplacer la date.
            font.pixelSize: 16
        }
        Text {
            id: countLabel
            text: indicator.unreadCount > 9 ? "9+" : String(indicator.unreadCount)
            color: indicator.inverted ? "#1e1e2e"
                : indicator.criticalUnreadCount > 0 ? "#f38ba8" : "#cdd6f4"
            font.pixelSize: 10
            font.bold: true
        }
    }
}
