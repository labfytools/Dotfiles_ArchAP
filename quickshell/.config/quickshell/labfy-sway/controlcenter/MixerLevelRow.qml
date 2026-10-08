import QtQuick
import QtQuick.Controls
import Quickshell
import "../theme"
import "AudioMixerModel.js" as MixerModel

Item {
    id: row
    required property string title
    property string detail: ""
    property string iconName: ""
    property string fallbackGlyph: ""
    property bool microphone: false
    property var audio: null
    readonly property int percent: audio ? MixerModel.displayPercent(audio.volume) : 0
    implicitHeight: detail ? 74 : 61

    Image {
        id: icon
        anchors.left: parent.left
        anchors.top: parent.top
        width: 22; height: 22
        source: row.iconName ? Quickshell.iconPath(row.iconName) : ""
        sourceSize.width: 22; sourceSize.height: 22
        visible: status === Image.Ready
        fillMode: Image.PreserveAspectFit
    }
    Text {
        anchors.centerIn: icon
        visible: !icon.visible
        text: row.fallbackGlyph
        font.family: "JetBrainsMono Nerd Font"
        font.pixelSize: 17
        color: Theme.lavender
    }
    Text {
        id: titleText
        anchors.left: icon.right; anchors.leftMargin: 8
        anchors.right: valueText.left; anchors.rightMargin: 5
        anchors.top: parent.top
        text: row.title
        color: Theme.foreground
        font.pixelSize: 12
        elide: Text.ElideRight
    }
    Text {
        visible: row.detail !== ""
        anchors.left: titleText.left; anchors.right: titleText.right
        anchors.top: titleText.bottom; anchors.topMargin: 1
        text: row.detail
        color: Theme.secondaryForeground
        font.pixelSize: 10
        elide: Text.ElideRight
    }
    Text {
        id: valueText
        anchors.right: muteButton.left; anchors.rightMargin: 5
        anchors.top: parent.top
        width: 43
        horizontalAlignment: Text.AlignRight
        text: row.audio ? row.percent + " %" : "—"
        color: Theme.secondaryForeground
        font.pixelSize: 11
    }
    Button {
        id: muteButton
        anchors.right: parent.right; anchors.top: parent.top
        width: 27; height: 25
        enabled: row.audio !== null
        Accessible.name: row.audio && row.audio.muted
            ? "Réactiver " + row.title : "Couper " + row.title
        onClicked: if (row.audio) row.audio.muted = !row.audio.muted
        background: Rectangle {
            radius: 4
            color: row.audio && row.audio.muted ? Theme.buttonPressed
                : muteButton.hovered ? Theme.buttonHover : Theme.buttonBackground
            border.color: muteButton.activeFocus ? Theme.lavender : "transparent"
        }
        contentItem: Text {
            text: row.microphone ? (row.audio && row.audio.muted ? "" : "")
                : row.audio && row.audio.muted ? "󰝟" : "󰕾"
            font.family: "JetBrainsMono Nerd Font"
            font.pixelSize: 15
            color: row.audio && row.audio.muted ? Theme.danger : Theme.foreground
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
        }
    }
    Slider {
        id: level
        anchors.left: parent.left; anchors.right: parent.right
        anchors.bottom: parent.bottom
        height: 29
        from: 0; to: 100; stepSize: 1
        enabled: row.audio !== null
        // WHY: an external value above 100 % remains visible in the label;
        // clamping the slider's display must never write back on its own.
        value: row.audio ? Math.max(0, Math.min(100, row.percent)) : 0
        Accessible.name: "Volume de " + row.title
        onMoved: if (row.audio) row.audio.volume = MixerModel.requestedVolume(value)
        background: Rectangle {
            x: level.leftPadding
            y: level.topPadding + level.availableHeight / 2 - height / 2
            width: level.availableWidth; height: 8; radius: 4
            color: Theme.buttonBackground
            Rectangle {
                width: level.visualPosition * parent.width
                height: parent.height; radius: 4; color: Theme.accent
            }
        }
        handle: Rectangle {
            x: level.leftPadding + level.visualPosition * (level.availableWidth - width)
            y: level.topPadding + level.availableHeight / 2 - height / 2
            width: 16; height: 16; radius: 4
            color: level.activeFocus ? Theme.lavender : Theme.foreground
        }
    }
}
