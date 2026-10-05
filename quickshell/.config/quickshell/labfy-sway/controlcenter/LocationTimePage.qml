import QtQuick
import QtQuick.Controls
import "../components"
import "../theme"

Item {
    id: page
    signal backRequested()
    property string view: "home"
    property var selected: null
    property string query: ""
    property string latitudeDraft: ""
    property string longitudeDraft: ""
    property string nameDraft: ""
    property string validationError: ""
    readonly property bool busy: AppearanceController.locationBusy
    readonly property var filtered: AppearanceController.locationPresets.filter(item =>
        (item.timezone + " " + item.city + " " + item.comment + " " + item.countries.join(" ")).toLowerCase().includes(query.toLowerCase()))

    function choose(item) { selected = item; view = "detail"; validationError = ""; }
    function validNumber(value, bound) {
        if (!/^[+-]?(?:\d+(?:\.\d*)?|\.\d+)$/.test(value.trim())) return false;
        let n = Number(value);
        return Number.isFinite(n) && n >= -bound && n <= bound;
    }
    function manualItem() {
        if (!validNumber(latitudeDraft, 90) || !validNumber(longitudeDraft, 180)) {
            validationError = "Latitude ou longitude invalide";
            return null;
        }
        validationError = "";
        return {name: nameDraft.trim(), timezone: AppearanceController.effectiveTimezone,
            latitude: Number(latitudeDraft), longitude: Number(longitudeDraft)};
    }
    function run(kind) {
        if (!selected) return;
        if (AppearanceController.applyLocation(kind, selected)) view = "home";
    }
    Column {
        anchors.fill: parent
        spacing: 10
        Row {
            spacing: 8; height: 30
            ActionButton { label: ""; onClicked: page.view === "home" ? page.backRequested() : page.view = "home" }
            Text { text: "Localisation & heure"; color: Theme.foreground; font.pixelSize: 16; font.bold: true; height: 30; verticalAlignment: Text.AlignVCenter }
        }
        Text { visible: page.view === "home"; text: "FUSEAU HORAIRE ACTUEL"; color: Theme.accentForeground; font.pixelSize: 11; font.bold: true }
        Text { visible: page.view === "home"; text: AppearanceController.effectiveTimezone || "Lecture…"; color: Theme.foreground; font.pixelSize: 15 }
        Text { visible: page.view === "home"; text: "POSITION SOLAIRE"; color: Theme.accentForeground; font.pixelSize: 11; font.bold: true }
        Text {
            visible: page.view === "home"
            text: AppearanceController.solarScheduleConfigured
                ? (AppearanceController.activeLocationName || "Position configurée") : "Non configurée"
            color: Theme.foreground; font.pixelSize: 13
        }
        Text {
            visible: page.view === "home"; width: parent.width; wrapMode: Text.Wrap
            text: "Le fuseau système et la position solaire sont indépendants."
            color: Theme.secondaryForeground; font.pixelSize: 11
        }
        ActionButton { visible: page.view === "home"; label: "󰖉  Choisir un lieu local"; onClicked: page.view = "search" }
        ActionButton { visible: page.view === "home"; label: "󰐀  Position manuelle"; onClicked: page.view = "manual" }
        ActionButton { visible: page.view === "home"; label: "󰃭  Lieux enregistrés"; onClicked: page.view = "saved" }

        TextField {
            visible: page.view === "search"; width: parent.width
            placeholderText: "Rechercher Paris, Madrid, Europe/Paris…"
            onTextChanged: page.query = text
        }
        Text {
            visible: page.view === "search"; width: parent.width; wrapMode: Text.Wrap
            text: "Points représentatifs de zone1970.tab ; une position manuelle peut être plus précise."
            color: Theme.secondaryForeground; font.pixelSize: 11
        }
        ScrollView {
            visible: page.view === "search"; width: parent.width; height: 470
            clip: true
            Column {
                width: page.width - 14; spacing: 3
                Repeater {
                    model: page.filtered
                    delegate: Rectangle {
                        required property var modelData
                        width: parent.width; height: 38; radius: 4
                        color: pointer.containsMouse ? Theme.buttonHover : Theme.buttonBackground
                        Text { anchors.left: parent.left; anchors.leftMargin: 8; anchors.verticalCenter: parent.verticalCenter
                            text: modelData.city + " · " + modelData.timezone; color: Theme.foreground
                            width: parent.width - 16; elide: Text.ElideRight; font.pixelSize: 12 }
                        MouseArea { id: pointer; anchors.fill: parent; hoverEnabled: true; onClicked: page.choose(modelData) }
                    }
                }
            }
        }
        Text { visible: page.view === "detail"; text: page.selected ? (page.selected.name || page.selected.city || page.selected.timezone) : ""; color: Theme.foreground; font.pixelSize: 15; font.bold: true }
        Text { visible: page.view === "detail"; text: "Fuseau système : " + (page.selected ? page.selected.timezone : ""); color: Theme.foreground; font.pixelSize: 12 }
        Text { visible: page.view === "detail"; text: "Position solaire : coordonnées représentatives disponibles"; color: Theme.secondaryForeground; font.pixelSize: 11 }
        Text { visible: page.view === "detail"; width: parent.width; wrapMode: Text.Wrap
            text: "Cette position associée au fuseau n'est pas nécessairement votre position exacte."
            color: Theme.secondaryForeground; font.pixelSize: 11 }
        ActionButton { visible: page.view === "detail"; enabled: !page.busy; label: "Appliquer les deux"; onClicked: page.run("both") }
        ActionButton { visible: page.view === "detail"; enabled: !page.busy; label: "Fuseau uniquement"; onClicked: page.run("timezone") }
        ActionButton { visible: page.view === "detail"; enabled: !page.busy; label: "Position solaire uniquement"; onClicked: page.run("solar") }
        ActionButton { visible: page.view === "detail"; enabled: !page.busy; label: "Enregistrer ce lieu"; onClicked: {
            AppearanceController.saveLocation({name: page.selected.city || page.selected.name, timezone: page.selected.timezone,
                latitude: page.selected.latitude, longitude: page.selected.longitude});
        } }

        Text { visible: page.view === "manual"; text: "Position solaire manuelle"; color: Theme.foreground; font.pixelSize: 14; font.bold: true }
        TextField { visible: page.view === "manual"; width: parent.width; placeholderText: "Latitude (−90 à 90)"; text: page.latitudeDraft; onTextEdited: page.latitudeDraft = text }
        TextField { visible: page.view === "manual"; width: parent.width; placeholderText: "Longitude (−180 à 180)"; text: page.longitudeDraft; onTextEdited: page.longitudeDraft = text }
        TextField { visible: page.view === "manual"; width: parent.width; placeholderText: "Nom facultatif pour enregistrer"; text: page.nameDraft; onTextEdited: page.nameDraft = text }
        Text { visible: page.view === "manual"; text: page.validationError; color: Theme.warningForeground; font.pixelSize: 11 }
        ActionButton { visible: page.view === "manual"; enabled: !page.busy; label: "Appliquer la position"; onClicked: {
            let item = page.manualItem();
            if (item && AppearanceController.applyLocation("solar", item)) page.view = "home";
        } }
        ActionButton { visible: page.view === "manual"; enabled: !page.busy; label: "Enregistrer ce lieu"; onClicked: {
            let item = page.manualItem();
            if (item && item.name) AppearanceController.saveLocation(item);
            else if (item) page.validationError = "Saisir un nom pour enregistrer";
        } }
        Text { visible: page.view === "saved"; text: "Lieux enregistrés"; color: Theme.foreground; font.pixelSize: 14; font.bold: true }
        ScrollView {
            visible: page.view === "saved"; width: parent.width; height: 470; clip: true
            Column {
                width: page.width - 14; spacing: 4
                Repeater {
                    model: AppearanceController.savedLocations
                    delegate: Rectangle {
                        required property var modelData
                        width: parent.width; height: 46; radius: 4
                        color: savedPointer.containsMouse ? Theme.buttonHover : Theme.buttonBackground
                        Column { anchors.left: parent.left; anchors.leftMargin: 8; anchors.verticalCenter: parent.verticalCenter
                            Text { text: modelData.name; color: Theme.foreground; font.pixelSize: 12; font.bold: true }
                            Text { text: modelData.timezone; color: Theme.secondaryForeground; font.pixelSize: 11 } }
                        MouseArea { id: savedPointer; anchors.fill: parent; hoverEnabled: true; onClicked: page.choose(modelData) }
                    }
                }
            }
        }
        Text { visible: !!AppearanceController.locationError; text: AppearanceController.locationError;
            width: parent.width; wrapMode: Text.Wrap; color: Theme.warningForeground; font.pixelSize: 11 }
    }
}
