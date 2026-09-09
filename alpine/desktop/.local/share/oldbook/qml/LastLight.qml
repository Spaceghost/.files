// The dying-battery vignette: darkness closing in from the edges.
//
// Built from four edge gradients rather than a shader. Qt 6 wants shaders
// precompiled with `qsb`, which would put a build step on a laptop this
// project deliberately does not compile on, and the effect does not need one:
// four linear gradients in `black` with alpha, overlapping at the corners,
// give a vignette whose corners are darker than its sides for free. Where two
// edges cross, the composite is 1-(1-a)^2, which is the corner emphasis a
// radial falloff would have cost a render pass to produce.
//
// Everything is driven from two properties the surface sets. `reach` is a
// fraction of the shorter screen axis, so the band scales with the display
// rather than being a pixel count that means something different on each one.
//
// The pulse is the one animation here, and it is the point rather than an
// indulgence: this exists to be noticed. It runs only while `depth` is above
// zero, so on mains and above the warning band there is no frame clock at all
// and the surface costs nothing.
import QtQuick

Item {
    id: root
    anchors.fill: parent

    // Set by lastlight_surface.py from the published state.
    property real depth: 0.0        // outer alpha, 0..1
    property real reach: 0.9        // band size as a fraction of the short axis
    property real pulsePeriod: 6.0  // seconds, matched to the keyboard breath
    property real pulseDepth: 0.18  // how much of `depth` the pulse swings

    // The pulse multiplies rather than adds, so it vanishes with the effect.
    property real pulse: 1.0
    readonly property real shortAxis: Math.min(width, height)
    readonly property real band: Math.max(1, shortAxis * reach * 0.5)
    readonly property real alpha: Math.max(0, Math.min(1, depth * pulse))

    Behavior on depth { NumberAnimation { duration: 900; easing.type: Easing.InOutQuad } }
    Behavior on reach { NumberAnimation { duration: 900; easing.type: Easing.InOutQuad } }

    SequentialAnimation on pulse {
        running: root.depth > 0.001
        loops: Animation.Infinite
        alwaysRunToEnd: false
        NumberAnimation {
            to: 1.0 - root.pulseDepth
            duration: Math.max(200, root.pulsePeriod * 500)
            easing.type: Easing.InOutSine
        }
        NumberAnimation {
            to: 1.0
            duration: Math.max(200, root.pulsePeriod * 500)
            easing.type: Easing.InOutSine
        }
        onStopped: root.pulse = 1.0
    }

    // --- the four edges -----------------------------------------------------

    Rectangle {
        anchors { top: parent.top; left: parent.left; right: parent.right }
        height: root.band
        gradient: Gradient {
            orientation: Gradient.Vertical
            GradientStop { position: 0.0; color: Qt.rgba(0, 0, 0, root.alpha) }
            GradientStop { position: 1.0; color: "transparent" }
        }
    }

    Rectangle {
        anchors { bottom: parent.bottom; left: parent.left; right: parent.right }
        height: root.band
        gradient: Gradient {
            orientation: Gradient.Vertical
            GradientStop { position: 0.0; color: "transparent" }
            GradientStop { position: 1.0; color: Qt.rgba(0, 0, 0, root.alpha) }
        }
    }

    Rectangle {
        anchors { left: parent.left; top: parent.top; bottom: parent.bottom }
        width: root.band
        gradient: Gradient {
            orientation: Gradient.Horizontal
            GradientStop { position: 0.0; color: Qt.rgba(0, 0, 0, root.alpha) }
            GradientStop { position: 1.0; color: "transparent" }
        }
    }

    Rectangle {
        anchors { right: parent.right; top: parent.top; bottom: parent.bottom }
        width: root.band
        gradient: Gradient {
            orientation: Gradient.Horizontal
            GradientStop { position: 0.0; color: "transparent" }
            GradientStop { position: 1.0; color: Qt.rgba(0, 0, 0, root.alpha) }
        }
    }
}
