import QtQuick
import Quickshell
import Quickshell.Io

Item {
    id: metrics
    property bool active: false
    property real cpuPercent: -1
    property real ramPercent: -1
    property real ramUsedGiB: -1
    property real ramTotalGiB: -1
    property real gpuPercent: -1
    property real cpuTemp: -1
    property real gpuTemp: -1
    property real diskPercent: -1
    property real diskUsedGiB: -1
    property real diskTotalGiB: -1
    property string loadAverage: ""
    property string uptimeText: ""
    property var previousCpu: null
    property string gpuPath: ""
    property string cpuTempPath: ""
    property string gpuTempPath: ""

    function numberFromFile(view, divisor) {
        const raw = view.text().trim();
        if (!/^[0-9]+$/.test(raw)) return -1;
        const value = Number(raw) / divisor;
        return Number.isFinite(value) ? value : -1;
    }

    // CONTRACT: la première lecture CPU constitue seulement la référence ; seul un delta positif produit un pourcentage.
    function updateCpu() {
        const line = cpuFile.text().split("\n")[0].trim().split(/\s+/);
        if (line[0] !== "cpu" || line.length < 6) return;
        const values = line.slice(1).map(Number);
        if (values.some(value => !Number.isFinite(value))) return;
        const total = values.reduce((sum, value) => sum + value, 0);
        const idle = values[3] + values[4]; // idle + iowait
        if (previousCpu) {
            const totalDelta = total - previousCpu.total;
            const idleDelta = idle - previousCpu.idle;
            if (totalDelta > 0 && idleDelta >= 0)
                cpuPercent = Math.max(0, Math.min(100, 100 * (1 - idleDelta / totalDelta)));
        }
        previousCpu = { total: total, idle: idle };
    }

    function updateMemory() {
        const entries = {};
        for (const line of memoryFile.text().split("\n")) {
            const match = line.match(/^(MemTotal|MemAvailable):\s+([0-9]+) kB$/);
            if (match) entries[match[1]] = Number(match[2]);
        }
        if (!(entries.MemTotal > 0) || !(entries.MemAvailable >= 0)) return;
        const used = Math.max(0, entries.MemTotal - entries.MemAvailable);
        ramPercent = Math.min(100, used * 100 / entries.MemTotal);
        ramUsedGiB = used / 1048576;
        ramTotalGiB = entries.MemTotal / 1048576;
    }

    function updateLoad() {
        const fields = loadFile.text().trim().split(/\s+/);
        if (fields.length >= 3 && fields.slice(0, 3).every(value => /^[0-9]+\.[0-9]+$/.test(value)))
            loadAverage = fields.slice(0, 3).join("   ");
    }

    function updateUptime() {
        const seconds = Number(uptimeFile.text().trim().split(/\s+/)[0]);
        if (!Number.isFinite(seconds) || seconds < 0) return;
        const minutes = Math.floor(seconds / 60);
        const days = Math.floor(minutes / 1440);
        const hours = Math.floor((minutes % 1440) / 60);
        uptimeText = days > 0 ? days + " j " + hours + " h" : hours + " h " + minutes % 60 + " min";
    }

    function sample() {
        if (!active) return;
        cpuFile.reload();
        memoryFile.reload();
        gpuFile.reload();
        cpuTempFile.reload();
        gpuTempFile.reload();
        loadFile.reload();
        uptimeFile.reload();
    }

    function refreshDisk() {
        if (active && !diskReader.running) diskReader.running = true;
    }

    onActiveChanged: {
        if (active) {
            previousCpu = null;
            cpuPercent = -1;
            gpuPercent = -1;
            cpuTemp = -1;
            gpuTemp = -1;
            gpuPath = "";
            cpuTempPath = "";
            gpuTempPath = "";
            // WHY: les numéros cardN et hwmonN changent au redémarrage.
            if (!hardwareResolver.running) hardwareResolver.running = true;
            sample();
            refreshDisk();
        } else {
            previousCpu = null;
            diskReader.running = false;
        }
    }

    // INVARIANT: aucun échantillonnage ni Process df périodique quand le panneau est fermé.
    Timer { interval: 1000; repeat: true; running: metrics.active; onTriggered: metrics.sample() }
    Timer { interval: 15000; repeat: true; running: metrics.active; onTriggered: metrics.refreshDisk() }

    FileView { id: cpuFile; path: "/proc/stat"; onLoaded: metrics.updateCpu() }
    FileView { id: memoryFile; path: "/proc/meminfo"; onLoaded: metrics.updateMemory() }
    FileView {
        id: gpuFile
        path: metrics.gpuPath
        printErrors: false
        onLoaded: metrics.gpuPercent = metrics.numberFromFile(gpuFile, 1)
    }
    FileView {
        id: cpuTempFile
        path: metrics.cpuTempPath
        printErrors: false
        onLoaded: metrics.cpuTemp = metrics.numberFromFile(cpuTempFile, 1000)
    }
    FileView {
        id: gpuTempFile
        path: metrics.gpuTempPath
        printErrors: false
        onLoaded: metrics.gpuTemp = metrics.numberFromFile(gpuTempFile, 1000)
    }
    FileView { id: loadFile; path: "/proc/loadavg"; onLoaded: metrics.updateLoad() }
    FileView { id: uptimeFile; path: "/proc/uptime"; onLoaded: metrics.updateUptime() }

    Process {
        id: hardwareResolver
        command: ["/usr/bin/python3", Quickshell.shellPath("bin/resolve-hardware.py")]
        stdout: StdioCollector { id: hardwareOutput; waitForEnd: true }
        onExited: (exitCode, exitStatus) => {
            if (exitCode !== 0 || exitStatus !== 0) return;
            const paths = hardwareOutput.text.trimEnd().split("\n");
            if (paths.length !== 3) return;
            // CONTRACT: seuls les chemins sysfs résolus par le helper sont chargés.
            if (paths[0].startsWith("/sys/class/drm/")) metrics.gpuPath = paths[0];
            if (paths[1].startsWith("/sys/class/hwmon/")) metrics.cpuTempPath = paths[1];
            if (paths[2].startsWith("/sys/class/hwmon/")) metrics.gpuTempPath = paths[2];
            if (metrics.active) {
                gpuFile.reload();
                cpuTempFile.reload();
                gpuTempFile.reload();
            }
        }
    }

    Process {
        id: diskReader
        command: ["df", "-B1", "--output=size,used,pcent,target", "/"]
        stdout: StdioCollector { id: diskOutput; waitForEnd: true }
        onExited: (exitCode, exitStatus) => {
            if (exitCode !== 0 || exitStatus !== 0) return;
            const lines = diskOutput.text.trim().split("\n");
            if (lines.length < 2) return;
            const fields = lines[lines.length - 1].trim().split(/\s+/);
            if (fields.length !== 4 || fields[3] !== "/") return;
            const total = Number(fields[0]);
            const used = Number(fields[1]);
            if (!(total > 0) || !(used >= 0)) return;
            metrics.diskTotalGiB = total / 1073741824;
            metrics.diskUsedGiB = used / 1073741824;
            metrics.diskPercent = Math.min(100, used * 100 / total);
        }
    }
}
