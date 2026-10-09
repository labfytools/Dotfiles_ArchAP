import QtQuick
import Quickshell
import Quickshell.I3
import Quickshell.Services.Pipewire
import "Observation.js" as Observation

Item {
    id: service
    required property bool authenticationActive
    property var sinkState: null
    property var brightnessState: null
    property var sourceState: null
    property var card: null
    property var panels: ({})
    property var origin: null
    readonly property var source: Pipewire.defaultAudioSource
    readonly property var sourceAudio: source && source.ready && source.audio ? source.audio : null

    // WHY: AudioMixerPage ne suit les nœuds que pendant son ouverture. Ce
    // tracker léger permet de lire la sourdine du défaut sans ouvrir de flux.
    PwObjectTracker { objects: [service.source] }
    onSourceAudioChanged: sampleSource()
    Connections {
        target: service.sourceAudio
        function onMutedChanged() { service.sampleSource(); }
    }
    function sampleSource() {
        const audio = sourceAudio;
        const result = Observation.observe(sourceState, source, !!audio,
            audio ? audio.volume : NaN, audio ? audio.muted : false);
        sourceState = result.state;
        if (result.muteChanged) publish("microphone", 0, audio.muted);
    }
    function sampleSink(identity, available, raw, percent, muted) {
        const result = Observation.observe(sinkState, identity, available, raw, muted);
        sinkState = result.state;
        if (result.muteChanged || result.volumeChanged)
            publish("volume", percent, muted);
    }
    function sampleBrightness(identity, available, raw, percent) {
        const result = Observation.observe(brightnessState, identity, available, raw, false);
        brightnessState = result.state;
        if (result.changed) publish("brightness", percent, false);
    }
    function barAction(kind, screen) {
        // L'indice de provenance n'est consommé que par une valeur confirmée ;
        // il expire afin qu'une modification externe ultérieure suive le focus.
        origin = { kind: kind, screen: screen, until: Date.now() + 700 };
    }
    function setPanel(screen, visible, page) {
        const next = Object.assign({}, panels);
        if (screen) next[screen.name] = visible ? page : -1;
        panels = next;
    }
    function panelShows(kind) {
        // Tous les Control Centers montrent les mêmes réglages globaux ; une
        // page visible sur une autre sortie suffit donc à rendre l'OSD redondant.
        return Object.keys(panels).some(name => Observation.pageShows(kind, panels[name]));
    }
    function focusedScreen() {
        const monitor = I3.focusedMonitor;
        const screens = Quickshell.screens;
        return Observation.screenForEvent(screens, monitor ? monitor.name : "",
            null, "", Date.now());
    }
    function publish(kind, percent, muted) {
        if (authenticationActive) return;
        const now = Date.now();
        const monitor = I3.focusedMonitor;
        const screen = Observation.screenForEvent(Quickshell.screens,
            monitor ? monitor.name : "", origin, kind, now);
        if (origin && (origin.kind === kind || origin.until < now)) origin = null;
        if (!screen || panelShows(kind)) return;
        // INVARIANT: une seule carte et une seule échéance courante ; un ancien
        // callback ne peut fermer une génération plus récente.
        card = Observation.nextCard(card, kind, percent, muted, screen, now);
        expiry.restart();
    }
    onAuthenticationActiveChanged: if (authenticationActive) {
        card = null;
        origin = null;
        expiry.stop();
    }
    Timer {
        id: expiry
        interval: 1500
        repeat: false
        property int generation: 0
        onTriggered: {
            if (Observation.expire(service.card, generation, Date.now())) service.card = null;
        }
        function restart() {
            generation = service.card.generation;
            stop();
            start();
        }
    }
    LazyLoader {
        active: !!service.card && !service.authenticationActive
        OsdWindow {
            // LazyLoader peut garder l'objet pendant une frame de destruction.
            hostScreen: service.card ? service.card.screen : service.focusedScreen()
            kind: service.card ? service.card.kind : "volume"
            percent: service.card ? service.card.value : 0
            muted: service.card ? service.card.muted : false
        }
    }
}
