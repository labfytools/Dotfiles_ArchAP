import QtQuick
import QtQuick.Layouts
import Quickshell.Services.Mpris
import "../components"

Rectangle {
    id: card

    // Un proxy MPRIS comme playerctld duplique un lecteur réel ; l'ordre DBus
    // départage les lecteurs de même état sans dépendre de leur arrivée.
    readonly property var player: {
        const candidates = Mpris.players.values.filter(item =>
            item && item.dbusName !== "org.mpris.MediaPlayer2.playerctld"
            && item.trackTitle && item.trackTitle.trim().length > 0);
        candidates.sort((a, b) => a.dbusName.localeCompare(b.dbusName));
        return candidates.find(item => item.playbackState === MprisPlaybackState.Playing)
            || candidates.find(item => item.playbackState === MprisPlaybackState.Paused)
            || null;
    }

    visible: player !== null
    implicitHeight: visible ? 116 : 0
    height: implicitHeight
    radius: 4
    color: "#313244"

    RowLayout {
        anchors.fill: parent
        anchors.margins: 12
        spacing: 12

        Rectangle {
            Layout.preferredWidth: 72
            Layout.preferredHeight: 72
            radius: 4
            color: "#45475a"
            clip: true

            Image {
                id: artwork
                anchors.fill: parent
                source: card.player ? card.player.trackArtUrl : ""
                fillMode: Image.PreserveAspectCrop
                asynchronous: true
                visible: status === Image.Ready
            }
            NerdIcon {
                anchors.centerIn: parent
                visible: !artwork.visible
                text: ""
                color: "#cba6f7"
                font.pixelSize: 27
            }
        }

        ColumnLayout {
            Layout.fillWidth: true
            spacing: 5

            Text {
                Layout.fillWidth: true
                text: card.player ? card.player.trackTitle : ""
                color: "#cdd6f4"
                font.pixelSize: 13
                font.bold: true
                elide: Text.ElideRight
            }
            Text {
                Layout.fillWidth: true
                text: card.player ? card.player.trackArtist : ""
                visible: text.length > 0
                color: "#a6adc8"
                font.pixelSize: 11
                elide: Text.ElideRight
            }

            Row {
                Layout.topMargin: 7
                spacing: 8

                Repeater {
                    model: [
                        { icon: "", capability: "canGoPrevious", action: "previous" },
                        { icon: card.player && card.player.isPlaying ? "" : "",
                            capability: "canTogglePlaying", action: "togglePlaying" },
                        { icon: "", capability: "canGoNext", action: "next" }
                    ]
                    Rectangle {
                        required property var modelData
                        readonly property bool available: card.player
                            && card.player[modelData.capability] === true
                        width: 32
                        height: 27
                        radius: 4
                        color: controlPointer.containsMouse && available ? "#585b70" : "#45475a"

                        NerdIcon {
                            anchors.centerIn: parent
                            text: modelData.icon
                            color: parent.available ? "#cdd6f4" : "#6c7086"
                            font.pixelSize: 14
                        }
                        MouseArea {
                            id: controlPointer
                            anchors.fill: parent
                            hoverEnabled: true
                            enabled: parent.available
                            onClicked: {
                                if (card.player && parent.available)
                                    card.player[modelData.action]();
                            }
                        }
                    }
                }
            }
        }
    }
}
