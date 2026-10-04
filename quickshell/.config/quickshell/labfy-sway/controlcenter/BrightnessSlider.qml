import QtQuick
import QtQuick.Controls
import Quickshell.Io
import "../components"
import "../theme"

Item {
    id: brightnessControl

    // Ce périphérique est celui du panneau interne ; sysfs exige une écriture non atomique.
    readonly property string backlightPath: "/sys/class/backlight/amdgpu_bl1"
    readonly property int maximum: parseInt(maximumFile.text(), 10) || 0
    readonly property real brightness: parseInt(brightnessFile.text(), 10)
    readonly property bool available: maximum > 0 && Number.isFinite(brightness)
    readonly property real fraction: available ? brightness / maximum : 0
    readonly property int percent: Math.round(fraction * 100)

    implicitHeight: content.implicitHeight

    FileView {
        id: maximumFile
        path: brightnessControl.backlightPath + "/max_brightness"
    }

    FileView {
        id: brightnessFile
        path: brightnessControl.backlightPath + "/brightness"
        watchChanges: true
        atomicWrites: false
        onFileChanged: reload()
    }

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
                text: ""
                font.pixelSize: 18
                color: Theme.foreground
            }

            Text {
                anchors.left: icon.right
                anchors.leftMargin: 10
                anchors.verticalCenter: parent.verticalCenter
                text: "Luminosité"
                color: Theme.foreground
                font.pixelSize: 14
            }

            Text {
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                text: brightnessControl.available ? brightnessControl.percent + "%" : "Indisponible"
                color: Theme.secondaryForeground
                font.pixelSize: 14
            }
        }

        Slider {
            id: slider
            width: parent.width
            height: 30
            from: 0.1
            to: 1
            enabled: brightnessControl.available
            value: brightnessControl.available
                ? Math.max(from, Math.min(to, brightnessControl.fraction)) : from

            onMoved: {
                if (brightnessControl.available) {
                    const fraction = Math.max(from, Math.min(to, value));
                    brightnessFile.setText(String(Math.round(brightnessControl.maximum * fraction)));
                }
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
