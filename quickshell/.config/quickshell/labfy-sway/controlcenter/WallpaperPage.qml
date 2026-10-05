import QtQuick
import QtQuick.Dialogs
import Quickshell
import Quickshell.Io
import "../theme"

Item {
    id: page
    required property bool activePage
    signal backRequested()
    property var items: []
    property var selected: null
    property bool selectionValid: false
    property var currentMeta: null
    property string directory: ""
    property string feedback: ""
    property bool hasMore: false
    property bool scanning: false
    property int nextPage: 0
    readonly property string backend: AppearanceController.wallpaperBackend
    readonly property var flavorNames: ({ latte: "Latte", frappe: "Frappé", macchiato: "Macchiato", mocha: "Mocha" })
    readonly property var previewMeta: selected || currentMeta
    onSelectedChanged: {
        selectionValid = false;
        if (validationProcess.running) validationProcess.running = false;
        if (selected) {
            validationProcess.command = ["python", backend, "validate", selected.path];
            validationProcess.running = true;
        }
    }

    function start() {
        currentProcess.command = ["python", backend, "current"];
        currentProcess.running = true;
        refreshCurrent();
    }
    function refreshCurrent() {
        currentImage.command = ["python", backend, "thumbnail", AppearanceController.effectiveWallpaper];
        currentImage.running = true;
    }
    function scan(reset) {
        if (!directory) return;
        if (reset) { items = []; selected = null; nextPage = 0; hasMore = false; }
        if (scanProcess.running) scanProcess.running = false;
        scanning = true;
        scanProcess.command = ["python", backend, "scan", directory, "--page", String(nextPage)];
        scanProcess.running = true;
    }
    function changeDirectory(url) {
        // CONTRACT: le picker ne sélectionne ni n'applique de wallpaper.
        if (scanProcess.running) scanProcess.running = false;
        directoryProcess.command = ["python", backend, "set-directory", url.toString()];
        directoryProcess.running = true;
    }
    function move(step) {
        const index = items.findIndex(item => selected && item.path === selected.path);
        const next = index + step;
        if (next >= 0 && next < items.length) selected = items[next];
        else if (index < 0 && items.length) selected = items[step > 0 ? 0 : items.length - 1];
    }
    onActivePageChanged: {
        if (activePage) start();
        else {
            if (scanProcess.running) scanProcess.running = false;
            if (validationProcess.running) validationProcess.running = false;
            if (currentImage.running) currentImage.running = false;
            if (currentProcess.running) currentProcess.running = false;
        }
    }
    Connections {
        target: AppearanceController
        function onWallpaperApplied() { page.feedback = "Fond d'écran appliqué"; page.refreshCurrent(); }
    }

    Process {
        id: validationProcess
        stdout: StdioCollector { id: validationOutput; waitForEnd: true }
        onExited: (code, status) => {
            if (!page.activePage || !page.selected || code !== 0 || status !== 0) return;
            try {
                const result = JSON.parse(validationOutput.text);
                page.selectionValid = result.path === page.selected.path;
            } catch (_) { page.selectionValid = false; }
        }
    }
    Process {
        id: currentProcess
        stdout: StdioCollector { id: currentOutput; waitForEnd: true }
        stderr: StdioCollector { waitForEnd: true }
        onExited: (code, status) => {
            if (!page.activePage || code !== 0 || status !== 0) return;
            try {
                const data = JSON.parse(currentOutput.text);
                AppearanceController.effectiveWallpaper = data.effectiveWallpaper;
                page.directory = data.wallpaperDirectory;
                AppearanceController.wallpaperDirectory = data.wallpaperDirectory;
                page.feedback = data.wallpaperMissing ? "Fond actuel introuvable : le prochain choix utilisera le repli." : "";
                page.scan(true);
            } catch (_) { page.feedback = "État des fonds d'écran indisponible"; }
        }
    }
    Process {
        id: currentImage
        stdout: StdioCollector { id: imageOutput; waitForEnd: true }
        onExited: (code, status) => {
            if (!page.activePage || code !== 0 || status !== 0) return;
            try { page.currentMeta = JSON.parse(imageOutput.text); }
            catch (_) { page.currentMeta = null; }
        }
    }
    Process {
        id: scanProcess
        stdout: StdioCollector { id: scanOutput; waitForEnd: true }
        stderr: StdioCollector { id: scanError; waitForEnd: true }
        onExited: (code, status) => {
            if (!page.activePage) return;
            page.scanning = false;
            if (code !== 0 || status !== 0) { page.feedback = scanError.text.trim() || "Lecture du dossier impossible"; return; }
            try {
                const data = JSON.parse(scanOutput.text);
                if (data.directory !== page.directory && data.directory !== page.directory.replace(/\/$/, "")) return;
                page.items = page.items.concat(data.items);
                page.nextPage = data.page + 1;
                page.hasMore = data.hasMore;
            } catch (_) { page.feedback = "Galerie invalide"; }
        }
    }
    Process {
        id: directoryProcess
        stdout: StdioCollector { id: directoryOutput; waitForEnd: true }
        stderr: StdioCollector { id: directoryError; waitForEnd: true }
        onExited: (code, status) => {
            if (!page.activePage) return;
            if (code !== 0 || status !== 0) { page.feedback = directoryError.text.trim() || "Dossier invalide"; return; }
            try {
                const data = JSON.parse(directoryOutput.text);
                page.directory = data.wallpaperDirectory;
                AppearanceController.wallpaperDirectory = page.directory;
                page.feedback = "";
                page.scan(true);
            } catch (_) { page.feedback = "Dossier invalide"; }
        }
    }
    FolderDialog {
        id: folderPicker
        title: "Choisir un dossier de fonds d'écran"
        onAccepted: page.changeDirectory(selectedFolder)
    }

    Column {
        anchors.fill: parent
        spacing: 8
        Row {
            spacing: 7; height: 30
            ActionButton { label: ""; onClicked: page.backRequested() }
            Text { text: "Fond d'écran"; height: 30; verticalAlignment: Text.AlignVCenter; color: Theme.foreground; font.pixelSize: 16; font.bold: true }
        }
        Text { text: page.selected ? "APERÇU DE LA SÉLECTION" : "APERÇU ACTUEL"; color: Theme.accentForeground; font.bold: true; font.pixelSize: 11 }
        Text {
            visible: AppearanceController.themeMode === "wallpaper"
            text: "Thème selon le fond : " + page.flavorNames[AppearanceController.effectiveFlavor]
            color: Theme.secondaryForeground; font.pixelSize: 10
        }
        Rectangle {
            width: parent.width; height: 110; radius: 4; color: Theme.buttonBackground
            Image {
                anchors.fill: parent; anchors.margins: 3
                source: page.previewMeta ? page.previewMeta.thumbnail : ""
                fillMode: Image.PreserveAspectFit; asynchronous: true; sourceSize.width: 320; sourceSize.height: 320
            }
        }
        Text {
            width: parent.width; text: page.previewMeta
                ? page.previewMeta.filename + "  •  " + page.previewMeta.width + " × " + page.previewMeta.height + "  •  " + page.previewMeta.format
                : AppearanceController.effectiveWallpaper
            elide: Text.ElideMiddle; color: Theme.secondaryForeground; font.pixelSize: 10
        }
        Row {
            width: parent.width; spacing: 6; height: 30
            Text { text: "GALERIE"; width: parent.width - 100; height: 30; verticalAlignment: Text.AlignVCenter; color: Theme.accentForeground; font.bold: true; font.pixelSize: 11 }
            ActionButton { label: "Dossier…"; onClicked: folderPicker.open() }
        }
        Text { width: parent.width; text: page.directory; elide: Text.ElideMiddle; color: Theme.secondaryForeground; font.pixelSize: 10 }
        GridView {
            id: gallery
            width: parent.width; height: 158; clip: true
            cellWidth: Math.floor(width / 3); cellHeight: 78
            model: page.items
            delegate: Rectangle {
                required property var modelData
                readonly property bool chosen: page.selected && page.selected.path === modelData.path
                readonly property bool active: AppearanceController.effectiveWallpaper === modelData.path
                width: gallery.cellWidth - 5; height: gallery.cellHeight - 5; radius: 4
                color: Theme.buttonBackground
                border.width: chosen ? 2 : 1; border.color: chosen ? Theme.accent : Theme.border
                Image {
                    anchors.fill: parent; anchors.margins: 3
                    source: modelData.thumbnail; fillMode: Image.PreserveAspectFit
                    asynchronous: true; sourceSize.width: 160; sourceSize.height: 160
                }
                Rectangle {
                    visible: parent.active; anchors.right: parent.right; anchors.top: parent.top
                    width: 20; height: 20; radius: 4; color: Theme.accent
                    Text { anchors.centerIn: parent; text: "✓"; color: Theme.onAccent; font.pixelSize: 13; font.bold: true }
                }
                MouseArea { anchors.fill: parent; onClicked: page.selected = modelData }
            }
            Text {
                anchors.centerIn: parent
                visible: !page.scanning && page.items.length === 0
                text: "Aucun fond d'écran trouvé"; color: Theme.secondaryForeground; font.pixelSize: 11
            }
        }
        ActionButton { visible: page.hasMore; label: page.scanning ? "Chargement…" : "Voir plus"; enabled: !page.scanning; onClicked: page.scan(false) }
        Text {
            width: parent.width; text: page.selected
                ? page.selected.filename + "  •  " + page.selected.width + " × " + page.selected.height + "  •  " + page.selected.format
                : "Choisir une miniature pour l'aperçu"
            elide: Text.ElideMiddle; color: Theme.foreground; font.pixelSize: 11
        }
        Row {
            spacing: 7
            ActionButton { label: "Précédent"; enabled: page.items.length > 0; onClicked: page.move(-1) }
            ActionButton { label: "Suivant"; enabled: page.items.length > 0; onClicked: page.move(1) }
            ActionButton {
                label: AppearanceController.wallpaperApplying ? "Application…" : "Appliquer"
                enabled: !!page.selected && page.selectionValid && !AppearanceController.appearanceBusy && !AppearanceController.nightLightBusy
                    && page.selected.path !== AppearanceController.effectiveWallpaper
                onClicked: { page.feedback = ""; AppearanceController.applyWallpaper(page.selected.path); }
            }
        }
        Text {
            width: parent.width; visible: !!page.feedback || !!AppearanceController.wallpaperError || !!AppearanceController.appearanceError
            text: AppearanceController.wallpaperError || AppearanceController.appearanceError || page.feedback
            color: AppearanceController.wallpaperError || AppearanceController.appearanceError ? Theme.warningForeground : Theme.successForeground
            wrapMode: Text.Wrap; font.pixelSize: 11
        }
    }
}
