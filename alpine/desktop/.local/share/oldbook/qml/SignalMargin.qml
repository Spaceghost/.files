// SPDX-License-Identifier: GPL-3.0-or-later
// The signal margin: dial graduations in the parts of the output no window and
// no reading card is using. The desktop's identity is a radio station, and this
// is the minor scale of a tuning dial running through the empty space.
//
// It never moves. There is no Behavior, no Transition, no NumberAnimation and
// no Timer in this file, and there must not be one: Qt Quick renders when the
// scene is dirty, so with nothing animating the surface is drawn once per
// change and then costs nothing. An animating BOTTOM-layer surface would also
// invalidate SceneFX's pre-rendered blur every frame, which is unmeasured, and
// measuring it is a later plank's job.
import QtQuick

Item {
    id: root

    // The 72x45 occupancy grid published by oldbook-space: one string per row,
    // '.' free and '#' covered by a window or by desktop chrome.
    property var grid: []
    property int columns: 72
    property int rows: 45
    property bool active: true
    property color tickColor: "#aaaaaa"
    property real tickAlpha: 0.14
    // SCREEN-CORNERS rounds the output by 20 logical pixels after the whole
    // scene, so nothing legible belongs inside that arc.
    property real cornerInset: 20
    property real minorLength: 7
    property real majorLength: 13
    property int majorEvery: 5

    onGridChanged: graduations.requestPaint()
    onActiveChanged: graduations.requestPaint()
    onTickColorChanged: graduations.requestPaint()
    onWidthChanged: graduations.requestPaint()
    onHeightChanged: graduations.requestPaint()

    function inCorner(x, y, length) {
        var near = cornerInset;
        var right = width - near;
        var bottom = height - near;
        var left = x <= near;
        var over = x >= right;
        return (left || over) && (y <= near || y + length >= bottom);
    }

    Canvas {
        id: graduations
        anchors.fill: parent
        renderStrategy: Canvas.Cooperative

        onPaint: {
            var context = getContext("2d");
            context.reset();
            if (!root.active || root.columns < 1 || root.rows < 1)
                return;
            var cellWidth = root.width / root.columns;
            var cellHeight = root.height / root.rows;
            if (cellWidth <= 0 || cellHeight <= 0)
                return;
            context.fillStyle = Qt.rgba(root.tickColor.r, root.tickColor.g,
                                        root.tickColor.b, root.tickAlpha);
            for (var row = 0; row < root.rows && row < root.grid.length; ++row) {
                var line = root.grid[row];
                for (var column = 0; column < root.columns && column < line.length; ++column) {
                    if (line.charAt(column) !== ".")
                        continue;
                    var length = (column % root.majorEvery === 0) ? root.majorLength
                                                                  : root.minorLength;
                    var x = Math.round(column * cellWidth);
                    var y = Math.round(row * cellHeight + (cellHeight - length) / 2);
                    if (root.inCorner(x, y, length))
                        continue;
                    context.fillRect(x, y, 1, length);
                }
            }
        }
    }
}
