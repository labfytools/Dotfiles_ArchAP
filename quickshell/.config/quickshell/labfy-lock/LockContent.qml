import QtQuick
import QtQuick.Controls
import Quickshell
import Quickshell.Services.UPower

Item {
    id: content
    required property var controller
    required property var hostSurface
    required property var player
    required property var notificationData
    required property var battery
    property bool preview: false
    property var previewState: ({})
    property alias field: answer

    Appearance { id: appearance }
    SystemClock { id: clock; precision: SystemClock.Minutes }

    readonly property string mediaMode: preview && previewState.mediaMode
        ? previewState.mediaMode : appearance.mediaVisibility
    readonly property bool lightTheme: appearance.state.effectiveFlavor === "latte"
    readonly property bool mediaShown: !!player && mediaMode !== "hidden"
    readonly property bool notificationsShown: !!notificationData && notificationData.total > 0
    readonly property bool compact: height < 680 || width < 900
    readonly property int cardWidth: Math.min(compact ? 340 : 380, width - 32)
    // CONTRACT: artwork remains local-only. Long but bounded file URIs from
    // MPRIS caches must reach Image; Image.status decides whether they work.
    readonly property string coverUri: mediaMode === "metadata" && player
        && typeof player.trackArtUrl === "string"
        && player.trackArtUrl.startsWith("file://") && player.trackArtUrl.length <= 4096
        ? player.trackArtUrl : ""
    readonly property bool coverUsable: coverUri && coverImage.status !== Image.Error
    readonly property string dateText: {
        const value = Qt.locale("fr_FR").toString(clock.date, "dddd d MMMM");
        return value.charAt(0).toUpperCase() + value.slice(1);
    }

    Rectangle { anchors.fill: parent; color: appearance.base }
    // CONTRACT: only the existing effective wallpaper is rendered; a failed
    // load retains an opaque palette background, never a desktop capture.
    Image {
        anchors.fill: parent
        source: content.preview ? "" : appearance.wallpaper
        asynchronous: true
        fillMode: Image.PreserveAspectCrop
        visible: status === Image.Ready
        sourceSize.width: Math.min(content.width * 1.5, 2560)
        sourceSize.height: Math.min(content.height * 1.5, 1600)
    }
    Rectangle { anchors.fill: parent; color: content.lightTheme ? "#b2eff1f5" : "#991e1e2e" }

    // INVARIANT: one bounded central column preserves the requested reading
    // order on every output; optional cards collapse without moving auth into
    // a corner. The reserved feedback area absorbs PAM and Caps Lock changes.
    Column {
        id: stack
        width: content.cardWidth
        anchors.horizontalCenter: parent.horizontalCenter
        y: Math.max(36, (content.height - height) / 2)
        spacing: content.compact ? 4 : 6
        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            text: content.preview && content.previewState.time ? content.previewState.time : Qt.formatTime(clock.date, "HH:mm")
            color: appearance.foreground
            font.family: "JetBrainsMono Nerd Font"
            font.pixelSize: content.compact ? 62 : 76
            font.weight: Font.Light
        }
        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            text: content.preview && content.previewState.date ? content.previewState.date : content.dateText
            color: appearance.foreground
            opacity: 0.82
            font.pixelSize: content.compact ? 15 : 18
        }
        Item { width: 1; height: content.compact ? 5 : 9 }
        Item {
            width: parent.width; height: content.compact ? 46 : 58
            Rectangle {
                anchors.horizontalCenter: parent.horizontalCenter
                width: parent.height; height: parent.height; radius: 4
                color: appearance.surface
                border.color: appearance.accent
                clip: true
                Image {
                    id: avatarImage
                    anchors.fill: parent
                    asynchronous: true
                    source: !content.preview && controller.avatar ? "file://" + controller.avatar : ""
                    fillMode: Image.PreserveAspectCrop
                    sourceSize.width: 128; sourceSize.height: 128
                    visible: status === Image.Ready
                }
                Text {
                    anchors.centerIn: parent
                    text: ""; color: appearance.foreground
                    font.family: "JetBrainsMono Nerd Font"; font.pixelSize: 29
                    visible: !avatarImage.visible
                }
            }
        }
        Text {
            width: parent.width; horizontalAlignment: Text.AlignHCenter
            text: controller.displayName; color: appearance.foreground
            font.pixelSize: content.compact ? 16 : 18; elide: Text.ElideRight
        }
        Text {
            width: parent.width; height: visible ? 15 : 0
            horizontalAlignment: Text.AlignHCenter
            visible: controller.displayName !== controller.loginUser
            text: controller.loginUser; color: appearance.foreground; opacity: 0.72
            font.pixelSize: 11; elide: Text.ElideRight
        }
        Text {
            width: parent.width; height: visible ? 15 : 0
            horizontalAlignment: Text.AlignHCenter
            visible: !!content.battery && content.battery.isPresent
            text: visible ? Math.round(content.battery.percentage * 100) + " % · "
                + (content.battery.state === UPowerDeviceState.Charging ? "En charge"
                : content.battery.state === UPowerDeviceState.Discharging ? "Sur batterie" : "Sur secteur") : ""
            color: appearance.foreground; opacity: 0.68; font.pixelSize: 11
        }
        Item { width: 1; height: content.compact ? 1 : 4 }
        Item {
            id: auth
            width: parent.width; height: 118
            Text {
                width: parent.width; height: 22
                verticalAlignment: Text.AlignVCenter
                horizontalAlignment: Text.AlignHCenter
                text: controller.attempt && controller.activeSurface === hostSurface
                    && hostSurface.secure && controller.pamResponseRequired
                    ? (controller.prompt || "Réponse attendue") : "Déverrouillage"
                color: appearance.foreground; font.pixelSize: 13
                elide: Text.ElideRight
            }
            TextField {
                id: answer
                y: 25; width: parent.width; height: 42
                color: appearance.foreground
                horizontalAlignment: TextInput.AlignHCenter
                background: Rectangle {
                    radius: 4; color: appearance.surface
                    border.color: answer.activeFocus ? appearance.accent : "#777783"
                    border.width: 1
                }
                echoMode: controller.responseVisible ? TextInput.Normal : TextInput.Password
                enabled: !content.preview && controller.activeSurface === hostSurface
                    && hostSurface.secure && !controller.aborting
                placeholderText: content.preview ? "Saisie désactivée dans l’aperçu"
                    : controller.attempt ? "Réponse" : "Appuyer sur Entrée pour commencer"
                onAccepted: controller.submit(text)
                Keys.onEscapePressed: controller.cancel()
                Keys.onPressed: event => {
                    if (event.key === Qt.Key_CapsLock) {
                        controller.capsObserved = true;
                        controller.capsOn = !controller.capsOn;
                    }
                }
                Component.onCompleted: if (!content.preview && controller.activeSurface === hostSurface) forceActiveFocus()
            }
            // CONTRACT: this fixed area contains keyboard, Caps Lock and PAM
            // feedback; their appearance never moves the password field.
            Text {
                y: 70; width: parent.width; height: 17
                text: (controller.keyboardLayout || "Disposition inconnue")
                    + (controller.capsObserved && controller.capsOn ? " · Verr. maj. activé" : "")
                color: appearance.foreground; opacity: 0.76; font.pixelSize: 11
                horizontalAlignment: Text.AlignHCenter; elide: Text.ElideRight
            }
            Text {
                y: 88; width: parent.width; height: 30
                text: controller.feedback
                color: controller.feedbackIsError
                    ? (appearance.palette.red || "#f38ba8") : appearance.foreground
                opacity: controller.feedbackIsError ? 1 : 0.76
                font.pixelSize: 12
                horizontalAlignment: Text.AlignHCenter
                verticalAlignment: Text.AlignTop
                wrapMode: Text.WordWrap; elide: Text.ElideRight
            }
            MouseArea {
                anchors.fill: parent
                enabled: !content.preview && controller.activeSurface !== hostSurface
                onClicked: controller.chooseSurface(hostSurface)
            }
        }
        // CONTRACT: media keeps its established visibility policy. Valid local
        // artwork gets a stable visible slot; failed loads use the small fallback.
        Rectangle {
            id: mediaCard
            width: parent.width; height: visible ? (content.compact ? 82 : 98) : 0
            radius: 4; visible: content.mediaShown
            color: content.lightTheme ? "#dceff1f5" : "#d41e1e2e"
            border.color: appearance.surface; border.width: 1
            Rectangle {
                    x: 10; anchors.verticalCenter: parent.verticalCenter
                    width: content.coverUsable ? 72 : 32
                    height: width; radius: 4
                    color: appearance.surface; clip: true
                    Image {
                        id: coverImage
                        anchors.fill: parent
                        source: content.coverUri
                        asynchronous: true; fillMode: Image.PreserveAspectCrop
                        sourceSize.width: 144; sourceSize.height: 144
                    }
                    Text {
                        visible: !content.coverUsable
                        anchors.centerIn: parent; text: ""
                        font.family: "JetBrainsMono Nerd Font"; font.pixelSize: 20
                        color: appearance.foreground; opacity: 0.55
                    }
                }
                Column {
                    x: content.coverUsable ? 94 : 52
                    y: content.compact ? 8 : 10
                    width: parent.width - x - 10; spacing: content.compact ? 2 : 5
                    Text {
                        width: parent.width; elide: Text.ElideRight
                        text: content.mediaMode === "metadata" && content.player
                            ? content.player.trackTitle : "Lecture média"
                        color: appearance.foreground; font.pixelSize: 13
                    }
                    Text {
                        width: parent.width; elide: Text.ElideRight
                        text: content.mediaMode === "metadata" && content.player
                            ? content.player.trackArtist : ""
                        color: appearance.foreground; opacity: 0.72; font.pixelSize: 12
                    }
                    Row {
                        spacing: 8
                        Repeater {
                            model: [
                                { label: "⏮", ability: "canGoPrevious", action: "previous" },
                                { label: content.player && content.player.isPlaying ? "⏸" : "▶",
                                  ability: "canTogglePlaying", action: "togglePlaying" },
                                { label: "⏭", ability: "canGoNext", action: "next" }
                            ]
                            Rectangle {
                                required property var modelData
                                readonly property bool allowed: content.player
                                    && content.player[modelData.ability] === true
                                visible: allowed
                                width: visible ? 34 : 0; height: 26; radius: 4
                                color: appearance.surface
                                Text { anchors.centerIn: parent; text: parent.modelData.label; color: appearance.foreground }
                                MouseArea {
                                    anchors.fill: parent; enabled: parent.allowed && !content.preview
                                    onClicked: if (content.player && parent.allowed)
                                        content.player[parent.modelData.action]()
                                }
                            }
                        }
                    }
                }
                Rectangle {
                    x: 10; y: parent.height - 5; width: parent.width - 20; height: 2
                    visible: content.mediaMode === "metadata" && content.player
                        && content.player.positionSupported && content.player.length > 0
                    color: "#45475a"
                    Rectangle {
                        height: parent.height
                        width: content.player && content.player.length > 0
                            ? parent.width * Math.max(0, Math.min(1, content.player.position / content.player.length)) : 0
                        color: appearance.accent
                    }
                }
        }
        // INVARIANT: notification projection contains public app counters only;
        // no summary, body or history is introduced by this visual card.
        Rectangle {
            width: parent.width; height: visible ? (content.compact ? 83 : 100) : 0
            radius: 4; visible: content.notificationsShown
            color: content.lightTheme ? "#dceff1f5" : "#d41e1e2e"
            border.color: appearance.surface; border.width: 1
            NotificationCardBody { anchors.fill: parent; projection: content.notificationData; foreground: appearance.foreground }
        }
    }
}
