import QtQuick
import Quickshell
import "status"

// TEST_ONLY: LABFY_PRINTING_TEST_STATE=empty|jobs|unavailable ; aucune action réelle.
ShellRoot {
    PanelWindow {
        anchors { top: true; left: true }
        aboveWindows: true
        implicitWidth: 70
        implicitHeight: 32
        color: "#1e1e2e"
        PrintingIndicator {
            id: indicator
            anchors.centerIn: parent
            Timer { interval: 700; running: true; onTriggered: indicator.popupOpen = true }
            Timer {
                interval: 1200
                running: indicator.testState.length > 0
                onTriggered: {
                    const mode = indicator.testState;
                    const okay = mode === "jobs"
                        ? indicator.jobCount === 2 && indicator.active
                            && indicator.tooltip === "Impression — 2 travaux en attente"
                            && indicator.defaultPrinter.name === "ENVY_5000"
                        : mode === "empty"
                            ? indicator.jobCount === 0 && indicator.printingData.scheduler
                                && indicator.tooltip === "Impression — Prête"
                            : mode === "unavailable"
                                ? !indicator.printingData.scheduler
                                    && indicator.tooltip === "Impression — indisponible"
                                : false;
                    if (okay) console.info("QML_PRINTING_TEST_PASS", mode);
                    else console.error("QML_PRINTING_TEST_FAIL", mode);
                }
            }
        }
    }
}
