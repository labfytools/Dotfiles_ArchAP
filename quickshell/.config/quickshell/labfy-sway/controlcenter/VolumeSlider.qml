import QtQuick
import QtQuick.Controls
import Quickshell.Services.Pipewire
import "../components"
import "../theme"

Item {
    id: volumeControl

    readonly property var sink: Pipewire.defaultAudioSink
    // Le tracker suit le sink par défaut ; attendre ready avant toute lecture ou écriture.
    readonly property var sinkAudio: sink && sink.ready && sink.audio ? sink.audio : null
    readonly property bool muted: sinkAudio ? sinkAudio.muted : false
    readonly property int percent: sinkAudio ? Math.round(sinkAudio.volume * 100) : 0

    PwObjectTracker {
        objects: [volumeControl.sink]
    }

    implicitHeight: content.implicitHeight

    Column {
        id: content
        width: parent.width
        spacing: 12

        Item {
            width: parent.width
            height: 28

            NerdIcon {
                id: icon
                anchors.left: parent.left
                anchors.verticalCenter: parent.verticalCenter
                text: volumeControl.sinkAudio ? (volumeControl.muted ? "" : "") : ""
                font.pixelSize: 18
                color: volumeControl.muted ? Theme.danger : Theme.foreground

                MouseArea {
                    anchors.fill: parent
                    enabled: volumeControl.sinkAudio !== null
                    acceptedButtons: Qt.LeftButton
                    onClicked: volumeControl.sinkAudio.muted = !volumeControl.sinkAudio.muted
                }
            }

            Text {
                anchors.left: icon.right
                anchors.leftMargin: 10
                anchors.verticalCenter: parent.verticalCenter
                text: "Volume"
                color: Theme.foreground
                font.pixelSize: 14
            }

            Text {
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                text: volumeControl.sinkAudio ? volumeControl.percent + "%" : "Indisponible"
                color: volumeControl.muted ? Theme.danger : Theme.secondaryForeground
                font.pixelSize: 14
            }
        }

        Slider {
            id: slider
            width: parent.width
            height: 30
            from: 0
            to: 1
            enabled: volumeControl.sinkAudio !== null
            value: volumeControl.sinkAudio
                ? Math.max(0, Math.min(1, volumeControl.sinkAudio.volume)) : 0

            onMoved: {
                if (volumeControl.sinkAudio)
                    volumeControl.sinkAudio.volume = Math.max(0, Math.min(1, value));
            }

            background: Rectangle {
                x: slider.leftPadding
                y: slider.topPadding + slider.availableHeight / 2 - height / 2
                width: slider.availableWidth
                height: 8
                radius: 4
                color: Theme.buttonBackground

                Rectangle {
                    width: slider.visualPosition * parent.width
                    height: parent.height
                    radius: parent.radius
                    color: Theme.accent
                }
            }

            handle: Rectangle {
                x: slider.leftPadding + slider.visualPosition * (slider.availableWidth - width)
                y: slider.topPadding + slider.availableHeight / 2 - height / 2
                width: 16
                height: 16
                radius: 8
                color: Theme.foreground
            }
        }
    }
}
