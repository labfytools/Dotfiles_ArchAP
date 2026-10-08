import QtQuick
import QtQuick.Controls
import Quickshell
import Quickshell.Services.Pipewire
import "../theme"
import "AudioMixerModel.js" as MixerModel

Item {
    id: page
    required property bool activePage
    required property var volumeControl
    signal backRequested()
    property var pendingSink: null
    property var pendingSource: null

    readonly property var audioNodes: Pipewire.nodes.values.filter(node => node && node.audio)
    readonly property var outputDevices: MixerModel.outputDevices(audioNodes)
    readonly property var inputDevices: MixerModel.inputDevices(audioNodes)
    readonly property var playbackStreams: MixerModel.playbackStreams(audioNodes)
    readonly property var effectiveSink: Pipewire.defaultAudioSink
    readonly property var effectiveSource: Pipewire.defaultAudioSource


    // CONTRACT: bind audio nodes only while the mixer is visible. The always
    // active VolumeSlider continues to own tracking of the shared default sink.
    PwObjectTracker { objects: page.activePage ? page.audioNodes : [] }

    onEffectiveSinkChanged: if (pendingSink === effectiveSink) pendingSink = null
    onEffectiveSourceChanged: if (pendingSource === effectiveSource) pendingSource = null
    onOutputDevicesChanged: if (pendingSink && !outputDevices.includes(pendingSink)) pendingSink = null
    onInputDevicesChanged: if (pendingSource && !inputDevices.includes(pendingSource)) pendingSource = null
    onActivePageChanged: {
        if (!activePage) { pendingSink = null; pendingSource = null; }
        else resetScroll.start();
    }
    Timer {
        id: resetScroll
        interval: 0; repeat: false
        onTriggered: if (scroll.contentItem) scroll.contentItem.contentY = 0
    }

    Column {
        anchors.fill: parent
        spacing: 9
        Row {
            width: parent.width; height: 30; spacing: 8
            Button {
                width: 40; height: 30
                Accessible.name: "Retour aux réglages rapides"
                onClicked: page.backRequested()
                background: Rectangle {
                    radius: 4
                    color: parent.hovered ? Theme.buttonHover : Theme.buttonBackground
                    border.color: parent.activeFocus ? Theme.lavender : "transparent"
                }
                contentItem: Text {
                    text: ""; color: Theme.foreground
                    font.family: "JetBrainsMono Nerd Font"; font.pixelSize: 14
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                }
            }
            Text {
                height: 30; verticalAlignment: Text.AlignVCenter
                text: "Audio"
                color: Theme.foreground; font.pixelSize: 16; font.bold: true
            }
        }
        ScrollView {
            id: scroll
            width: parent.width
            height: Math.max(0, parent.height - y)
            clip: true
            ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
            Column {
                width: scroll.availableWidth
                spacing: 8

                Text { text: "SORTIE AUDIO"; color: Theme.lavender; font.pixelSize: 11; font.bold: true }
                Text {
                    width: parent.width
                    text: !Pipewire.ready ? "Connexion audio en cours…"
                        : page.effectiveSink ? "Utilisée : " + MixerModel.deviceName(page.effectiveSink)
                            : "Aucune sortie active"
                    color: Theme.secondaryForeground; font.pixelSize: 11
                    elide: Text.ElideRight
                }
                Repeater {
                    model: page.outputDevices
                    delegate: Button {
                        required property var modelData
                        width: scroll.availableWidth; height: 31
                        enabled: page.activePage && modelData.ready
                        Accessible.name: "Choisir la sortie " + MixerModel.deviceName(modelData)
                        onClicked: {
                            if (page.effectiveSink === modelData) return;
                            page.pendingSink = modelData;
                            Pipewire.preferredDefaultAudioSink = modelData;
                        }
                        background: Rectangle {
                            radius: 4
                            color: page.effectiveSink === modelData ? Theme.buttonPressed
                                : parent.hovered ? Theme.buttonHover : Theme.buttonBackground
                            border.color: parent.activeFocus ? Theme.lavender : "transparent"
                        }
                        contentItem: Row {
                            spacing: 7
                            Text {
                                width: 18; height: 18; anchors.verticalCenter: parent.verticalCenter
                                text: "󰕾"; color: Theme.lavender
                                font.family: "JetBrainsMono Nerd Font"; font.pixelSize: 15
                            }
                            Text {
                                width: scroll.availableWidth - 54
                                anchors.verticalCenter: parent.verticalCenter
                                text: MixerModel.deviceName(modelData)
                                color: Theme.foreground; font.pixelSize: 11; elide: Text.ElideRight
                            }
                            Text {
                                anchors.verticalCenter: parent.verticalCenter
                                text: page.effectiveSink === modelData ? "✓" : ""
                                color: Theme.lavender; font.pixelSize: 12
                            }
                        }
                    }
                }
                Text {
                    visible: page.outputDevices.length === 0 && Pipewire.ready
                    text: "Aucune sortie disponible"
                    color: Theme.secondaryForeground; font.pixelSize: 11
                }
                Text {
                    visible: page.pendingSink !== null && page.pendingSink !== page.effectiveSink
                    text: "Changement de sortie demandé…"
                    color: Theme.secondaryForeground; font.pixelSize: 10
                }
                MixerLevelRow {
                    width: scroll.availableWidth
                    title: "Volume général"
                    fallbackGlyph: "󰕾"
                    audio: page.volumeControl.sinkAudio
                }

                Rectangle { width: scroll.availableWidth; height: 1; color: Theme.separator }
                Text { text: "APPLICATIONS"; color: Theme.lavender; font.pixelSize: 11; font.bold: true }
                Text {
                    visible: page.playbackStreams.length === 0
                    text: Pipewire.ready ? "Aucun flux de lecture" : "Recherche des flux…"
                    color: Theme.secondaryForeground; font.pixelSize: 11
                }
                Repeater {
                    model: page.playbackStreams
                    delegate: MixerLevelRow {
                        required property var modelData
                        width: scroll.availableWidth
                        title: MixerModel.streamName(modelData)
                        detail: MixerModel.streamDetail(modelData)
                        iconName: MixerModel.streamIcon(modelData)
                        fallbackGlyph: "󰀻"
                        audio: modelData && modelData.ready ? modelData.audio : null
                    }
                }

                Rectangle { width: scroll.availableWidth; height: 1; color: Theme.separator }
                Text { text: "MICROPHONE"; color: Theme.lavender; font.pixelSize: 11; font.bold: true }
                Text {
                    width: parent.width
                    text: !Pipewire.ready ? "Connexion audio en cours…"
                        : page.effectiveSource ? "Utilisé : " + MixerModel.deviceName(page.effectiveSource)
                            : "Aucun microphone actif"
                    color: Theme.secondaryForeground; font.pixelSize: 11
                    elide: Text.ElideRight
                }
                Repeater {
                    model: page.inputDevices
                    delegate: Button {
                        required property var modelData
                        width: scroll.availableWidth; height: 31
                        enabled: page.activePage && modelData.ready
                        Accessible.name: "Choisir le microphone " + MixerModel.deviceName(modelData)
                        onClicked: {
                            if (page.effectiveSource === modelData) return;
                            page.pendingSource = modelData;
                            Pipewire.preferredDefaultAudioSource = modelData;
                        }
                        background: Rectangle {
                            radius: 4
                            color: page.effectiveSource === modelData ? Theme.buttonPressed
                                : parent.hovered ? Theme.buttonHover : Theme.buttonBackground
                            border.color: parent.activeFocus ? Theme.lavender : "transparent"
                        }
                        contentItem: Row {
                            spacing: 7
                            Text {
                                width: 18; height: 18; anchors.verticalCenter: parent.verticalCenter
                                text: ""; color: Theme.lavender
                                font.family: "JetBrainsMono Nerd Font"; font.pixelSize: 15
                            }
                            Text {
                                width: scroll.availableWidth - 54
                                anchors.verticalCenter: parent.verticalCenter
                                text: MixerModel.deviceName(modelData)
                                color: Theme.foreground; font.pixelSize: 11; elide: Text.ElideRight
                            }
                            Text {
                                anchors.verticalCenter: parent.verticalCenter
                                text: page.effectiveSource === modelData ? "✓" : ""
                                color: Theme.lavender; font.pixelSize: 12
                            }
                        }
                    }
                }
                Text {
                    visible: page.inputDevices.length === 0 && Pipewire.ready
                    text: "Aucun microphone disponible"
                    color: Theme.secondaryForeground; font.pixelSize: 11
                }
                Text {
                    visible: page.pendingSource !== null && page.pendingSource !== page.effectiveSource
                    text: "Changement de microphone demandé…"
                    color: Theme.secondaryForeground; font.pixelSize: 10
                }
                MixerLevelRow {
                    width: scroll.availableWidth
                    title: "Niveau du microphone"
                    fallbackGlyph: ""
                    microphone: true
                    audio: page.effectiveSource && page.effectiveSource.ready
                        ? page.effectiveSource.audio : null
                }
                Item { width: 1; height: 5 }
            }
        }
    }
}
