import QtQuick
import Quickshell
import Quickshell.Io

Item {
    id: service
    property string activeOutput: ""
    property string page: "Vue"
    property bool processesVisible: false
    readonly property bool active: activeOutput !== ""
    property var data: ({})
    property var usage: ({})
    property var rates: ({})
    property var processRows: []
    property var histories: ({ cpu: [], gpu: [], ram: [], psi: [], cpuTemp: [], gpuTemp: [], rx: [], tx: [] })
    property var previous: null
    property var processBaseline: null
    property var networkBaseline: null
    property int tick: 0
    readonly property string backend: (Quickshell.env("XDG_CONFIG_HOME") ||
        (Quickshell.env("HOME") + "/.config")) + "/quickshell/labfy-sway/systemmonitor/backend.py"
    // CONTRACT: ShellRoot owns this collector across every output. Closing the
    // panel stops the timer and invalidates all differential baselines.
    function open(output) { activeOutput = output; page = "Vue"; previous = null; processBaseline = null; networkBaseline = null; tick = 0; sample(); }
    function close() { activeOutput = ""; previous = null; processBaseline = null; networkBaseline = null; sampler.running = false; }
    function append(key, value, time, gap) {
        const old = histories[key] || [];
        const next = old.slice(Math.max(0, old.length - 599));
        next.push({ value: gap ? null : value, time: time });
        histories = Object.assign({}, histories, { [key]: next });
    }
    function percent(now, before) {
        if (!now || !before || now.length !== 2 || before.length !== 2) return null;
        const total = now[0] - before[0], idle = now[1] - before[1];
        return total > 0 && idle >= 0 && idle <= total ? 100 * (total - idle) / total : null;
    }
    function sample() {
        if (!active || sampler.running) return;
        const args = ["python3", "-B", backend];
        if (tick % 2 === 0) args.push("gpu");
        if (tick % 30 === 0) args.push("disk");
        if (processesVisible && tick % 4 === 0) args.push("processes");
        sampler.command = args;
        sampler.running = true;
        tick++;
    }
    function accept(d) {
        if (!active || d.error || !d.monotonic) return;
        const prior = previous;
        const gap = !!prior && (d.monotonic <= prior.monotonic || d.monotonic - prior.monotonic > 5);
        const elapsed = prior && !gap ? d.monotonic - prior.monotonic : 0;
        const cpu = elapsed ? percent(d.cpu.cpu, prior.cpu.cpu) : null;
        let threads = {};
        for (const key in d.cpu) if (key !== "cpu")
            threads[key] = elapsed ? percent(d.cpu[key], prior.cpu[key]) : null;
        let rx = null, tx = null;
        if (!d.network || !networkBaseline || d.network.interface !== networkBaseline.interface ||
                d.network.rx < networkBaseline.rx || d.network.tx < networkBaseline.tx)
            networkBaseline = d.network;
        if (elapsed && d.network && prior.network && d.network.interface === prior.network.interface) {
            const dr = d.network.rx - prior.network.rx, dt = d.network.tx - prior.network.tx;
            if (dr >= 0 && dt >= 0) { rx = dr / elapsed; tx = dt / elapsed; }
        }
        let rows = processRows;
        if (d.processes) {
            rows = d.processes.map(p => {
                const old = processBaseline ? processBaseline.rows.find(q => q.pid === p.pid && q.start === p.start) : null;
                const delta = old ? p.ticks - old.ticks : -1;
                const processElapsed = processBaseline && !gap ? d.monotonic - processBaseline.time : 0;
                return Object.assign({}, p, { cpu: processElapsed > 0 && delta >= 0 ?
                    100 * delta / (d.clockTicks * processElapsed) : null });
            });
            rows.sort((a, b) => (b.cpu || 0) - (a.cpu || 0) || b.rss - a.rss);
            processRows = rows.slice(0, 80);
            processBaseline = { rows: d.processes, time: d.monotonic };
        }
        usage = { cpu: cpu, threads: threads };
        rates = { rx: rx, tx: tx,
            totalRx: d.network && networkBaseline ? d.network.rx - networkBaseline.rx : null,
            totalTx: d.network && networkBaseline ? d.network.tx - networkBaseline.tx : null,
            swapIn: elapsed && d.swapPages.pswpin >= (prior.swapPages.pswpin || 0) ?
                (d.swapPages.pswpin - prior.swapPages.pswpin) / elapsed : null,
            swapOut: elapsed && d.swapPages.pswpout >= (prior.swapPages.pswpout || 0) ?
                (d.swapPages.pswpout - prior.swapPages.pswpout) / elapsed : null };
        data = Object.assign({}, data, d);
        const t = d.monotonic;
        append("cpu", cpu, t, gap);
        append("ram", d.memory.total ? 100 * d.memory.used / d.memory.total : null, t, gap);
        append("psi", d.psi.some ? d.psi.some[0] : null, t, gap);
        append("rx", rx, t, gap); append("tx", tx, t, gap);
        if (d.gpu !== undefined) append("gpu", d.gpu ? d.gpu.activity : null, t, gap);
        if (d.temperatures) {
            append("cpuTemp", d.temperatures.cpu, t, gap);
            append("gpuTemp", d.temperatures.gpu, t, gap);
        }
        // INVARIANT: retain the last process reference across non-process ticks;
        // process identity is PID plus start time, never PID alone.
        previous = Object.assign({}, d, { processes: d.processes || (prior ? prior.processes : null),
            network: d.network, gpu: d.gpu || (prior ? prior.gpu : null) });
    }
    Timer { interval: 1000; repeat: true; running: service.active; onTriggered: service.sample() }
    Process {
        id: sampler
        stdout: StdioCollector { id: output; waitForEnd: true }
        onExited: (code, status) => {
            if (code !== 0 || !service.active) return;
            try { service.accept(JSON.parse(output.text)); }
            catch (error) { console.warn("Moniteur matériel : échantillon invalide", error); }
        }
    }
}
