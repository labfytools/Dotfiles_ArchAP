import QtQuick
import QtQuick.Controls
import Quickshell.Io
import "../components"
import "../theme"
import "PercentMath.js" as PercentMath

Item {
    id: brightnessControl

    // Ce périphérique est celui du panneau interne ; sysfs exige une écriture non atomique.
    readonly property string backlightPath: "/sys/class/backlight/amdgpu_bl1"
    readonly property int maximum: parseInt(maximumFile.text(), 10) || 0
    readonly property real brightness: parseInt(brightnessFile.text(), 10)
    readonly property bool available: maximum > 0 && Number.isFinite(brightness)
    readonly property real fraction: available ? brightness / maximum : 0
    readonly property int percent: Math.round(fraction * 100)

    // INVARIANT: une seule écriture sysfs à la fois ; les gestes rapides
    // mettent à jour la consigne, puis chaque résultat est relu du matériel.
    property int requestedPercent: -1
    property int writtenPercent: -1
    property bool writeInFlight: false
    property bool readbackFailed: false
    function requestPercent(value) {
        if (!available) return;
        requestedPercent = PercentMath.bounded(value, 10);
        if (!writeInFlight) writeRequested();
    }
    function adjustBy(steps) {
        if (!available || !steps) return;
        requestPercent((requestedPercent >= 0 ? requestedPercent : percent) + steps);
    }
    function writeRequested() {
        if (!available || requestedPercent < 0) return;
        const raw = Math.max(1, Math.round(maximum * requestedPercent / 100));
        writtenPercent = requestedPercent;
        writeInFlight = true;
        brightnessFile.setText(String(raw));
    }
    function finishWrite() {
        // Exécuter après le signal saved évite de réentrer dans les callbacks
        // FileView pendant l'attente bornée de lecture des quelques octets sysfs.
        readbackFailed = false;
        brightnessFile.reload();
        brightnessFile.waitForJob();
        const raw = brightnessFile.text().trim();
        const actual = /^[0-9]+$/.test(raw) ? Number(raw) : NaN;
        writeInFlight = false;
        if (readbackFailed || !Number.isSafeInteger(actual) || actual < 0 || actual > maximum) {
            requestedPercent = -1;
            console.warn("Relecture du rétroéclairage impossible après écriture");
            return;
        }
        if (requestedPercent !== writtenPercent) writeRequested();
        else requestedPercent = -1;
    }

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
        onLoadFailed: error => {
            brightnessControl.readbackFailed = true;
            console.warn("Lecture du rétroéclairage impossible", error);
        }
        onSaved: {
            // WHY: FileView peut déjà avoir émis loaded() depuis le watcher
            // avant saved(). Attendre un second loaded() bloquait la file pour
            // toujours. Relire ici les quelques octets de sysfs, puis libérer
            // l'écriture avant de lancer la dernière consigne en attente.
            // Le pilote peut arrondir ; une nouvelle consigne est la seule
            // raison de poursuivre, jamais un écart entre cible et matériel.
            Qt.callLater(brightnessControl.finishWrite);
        }
        onSaveFailed: error => {
            console.warn("Écriture du rétroéclairage impossible", error);
            brightnessControl.writeInFlight = false;
            brightnessControl.requestedPercent = -1;
            reload();
        }
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
                    brightnessControl.requestPercent(fraction * 100);
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
