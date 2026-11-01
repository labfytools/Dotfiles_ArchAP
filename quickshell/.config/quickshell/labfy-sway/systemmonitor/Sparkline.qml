import QtQuick
import "../theme"

Canvas {
    id: graph
    property var points: []
    property real ceiling: 100
    property color stroke: Theme.lavender
    property bool gridVisible: false
    property bool fillVisible: false
    implicitWidth: 160; implicitHeight: 30
    onPointsChanged: requestPaint()
    onCeilingChanged: requestPaint()
    onWidthChanged: requestPaint()
    onHeightChanged: requestPaint()
    onPaint: {
        const ctx = getContext("2d");
        ctx.clearRect(0, 0, width, height);
        if (gridVisible) {
            ctx.strokeStyle = Theme.outline; ctx.lineWidth = 1;
            for (let k = 1; k <= 3; ++k) {
                const y = k * height / 4;
                ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(width, y); ctx.stroke();
            }
        }
        if (points.length < 2) return;
        // CONTRACT: a null sample breaks the path after suspend or counter reset.
        // Reuse one canvas and draw the bounded ring snapshot without QML nodes.
        const color = stroke.toString();
        let start = -1;
        function drawSegment(first, end) {
            if (end - first < 2) return;
            if (fillVisible) {
                ctx.beginPath();
                ctx.moveTo(first * width / (points.length - 1), height);
                for (let i = first; i < end; ++i) {
                    const x = i * width / (points.length - 1);
                    const y = height - 2 - Math.max(0, Math.min(1, points[i].value / Math.max(1, ceiling))) * (height - 4);
                    ctx.lineTo(x, y);
                }
                ctx.lineTo((end - 1) * width / (points.length - 1), height);
                ctx.closePath(); ctx.fillStyle = Qt.rgba(stroke.r, stroke.g, stroke.b, 0.12); ctx.fill();
            }
            ctx.beginPath();
            for (let i = first; i < end; ++i) {
                const x = i * width / (points.length - 1);
                const y = height - 2 - Math.max(0, Math.min(1, points[i].value / Math.max(1, ceiling))) * (height - 4);
                if (i === first) ctx.moveTo(x, y); else ctx.lineTo(x, y);
            }
            ctx.strokeStyle = color; ctx.lineWidth = 1.5; ctx.stroke();
        }
        for (let i = 0; i <= points.length; ++i) {
            const value = i < points.length ? points[i].value : null;
            if (value !== null && value !== undefined && isFinite(value)) {
                if (start < 0) start = i;
            } else if (start >= 0) { drawSegment(start, i); start = -1; }
        }
    }
}
