import QtQuick
import Quickshell
import Quickshell.Io

Item {
    id: bridge
    // CONTRACT: only the live, acknowledged helper connection contributes
    // application requests. A reload or disconnect drops its contribution;
    // the manual keep-awake selection is owned elsewhere in ShellRoot.
    property int applicationRequestCount: 0
    property var currentSocket: null
    property string generation: ""
    property int lastSequence: 0
    property bool socketReady: false

    // WHY: QuickShell construit la nouvelle configuration avant de détruire
    // l'ancienne. Deux SocketServer sur le même chemin peuvent alors se
    // croiser : l'ancien supprime le fichier de socket que le nouveau vient
    // de créer. Le premier tick après le rechargement laisse finir la
    // destruction précédente avant de publier le nouveau chemin. Le helper
    // reconnecte alors ses demandes encore valides depuis son état en mémoire.
    Timer {
        interval: 250
        running: true
        repeat: false
        onTriggered: bridge.socketReady = true
    }

    function receive(socket, line) {
        if (socket !== currentSocket || line.length > 512) {
            socket.connected = false;
            return;
        }
        let frame;
        try { frame = JSON.parse(line); }
        catch (_) { socket.connected = false; return; }
        if (!frame || frame.type !== "snapshot" || frame.version !== 1
                || typeof frame.generation !== "string"
                || !/^[0-9a-f]{32}$/.test(frame.generation)
                || !Number.isSafeInteger(frame.sequence) || frame.sequence <= lastSequence
                || !Number.isInteger(frame.count) || frame.count < 0 || frame.count > 256
                || (generation && frame.generation !== generation)) {
            socket.connected = false;
            return;
        }
        generation = frame.generation;
        lastSequence = frame.sequence;
        if (applicationRequestCount !== frame.count)
            console.info("Demandes applicatives", frame.count, "ms", Date.now());
        applicationRequestCount = frame.count;
        // CONTRACT: this acknowledges assignment of the QuickShell state,
        // not a compositor confirmation (idle-inhibit-v1 has no such ack).
        socket.write(JSON.stringify({ type: "ack", generation: generation,
                                      sequence: lastSequence, applied: true }) + "\n");
        socket.flush();
    }

    SocketServer {
        active: bridge.socketReady
        path: Quickshell.env("LABFY_IDLE_BRIDGE_SOCKET")
              || (Quickshell.env("XDG_RUNTIME_DIR") + "/labfy-idle-bridge.sock")
        handler: Socket {
            id: peer
            onConnectedChanged: {
                if (connected) {
                    // CONTRACT: journaliser seulement les transitions du
                    // pont, jamais les libellés privés reçus par le helper.
                    console.info("Pont d'inhibition connecté", "ms", Date.now());
                    if (bridge.currentSocket && bridge.currentSocket !== peer)
                        bridge.currentSocket.connected = false;
                    bridge.currentSocket = peer;
                    if (bridge.applicationRequestCount !== 0)
                        console.info("Demandes applicatives", 0, "raison reconnexion", "ms", Date.now());
                    bridge.applicationRequestCount = 0;
                    bridge.generation = "";
                    bridge.lastSequence = 0;
                } else if (bridge.currentSocket === peer) {
                    console.info("Pont d'inhibition déconnecté", "ms", Date.now());
                    bridge.currentSocket = null;
                    if (bridge.applicationRequestCount !== 0)
                        console.info("Demandes applicatives", 0, "raison déconnexion", "ms", Date.now());
                    bridge.applicationRequestCount = 0;
                    bridge.generation = "";
                    bridge.lastSequence = 0;
                }
            }
            parser: SplitParser { onRead: line => bridge.receive(peer, line) }
        }
    }
}
