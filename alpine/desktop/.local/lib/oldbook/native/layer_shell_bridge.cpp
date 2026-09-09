// SPDX-License-Identifier: GPL-3.0-or-later
// Small C ABI boundary between Python and LayerShellQt, in the shape
// `projects/superhold/native/layer_shell_bridge.cpp` established: Python keeps
// ownership of the QWindow and the QScreen and this only sets properties on
// them. Superhold's own bridge is not reused because it is fixed to the OVERLAY
// layer anchored to the top edge, which is the opposite end of the layer map
// from a desktop backdrop, and because its installed library belongs to a
// packaged application this desktop must not rebuild to change a helper.
//
// One piece of policy is deliberately baked in rather than left to the caller:
// the exclusive zone can only ever be zero. An exclusive zone is a tiling
// instruction, DECORATION-PLACEMENT gives the caption band the only reservation
// on this desktop, and a second one would resize every window on the output.
// The neighbouring background daemon uses -1, so refusing anything but 0 here
// makes the easy copy-and-paste mistake impossible rather than merely unlikely.
//
// There is no `prepare` here, unlike superhold's bridge. All its
// `LayerShellQt::Shell::useLayerShell()` ever did was export
// QT_WAYLAND_SHELL_INTEGRATION=layer-shell, it is deprecated as unnecessary
// since Qt 6.5, and Python can set an environment variable without a shared
// library. What genuinely needs C++ is `Window::get`, which has no bindings.
#include <LayerShellQt/Window>
#include <QMargins>
#include <QScreen>
#include <QSize>
#include <QString>
#include <QWindow>

extern "C" Q_DECL_EXPORT int oldbook_layer_shell_configure(
    void *window_pointer, void *screen_pointer, const char *scope,
    int layer, int anchors, int exclusive_zone, int keyboard, int width, int height)
{
    // Scalars first, and deliberately: the exclusive-zone refusal is then
    // reachable from a test that has no Qt application and no window at all.
    if (layer < LayerShellQt::Window::LayerBackground
        || layer > LayerShellQt::Window::LayerOverlay) {
        return -2;
    }
    if (anchors < 0 || anchors > 15) {
        return -3;
    }
    if (keyboard < LayerShellQt::Window::KeyboardInteractivityNone
        || keyboard > LayerShellQt::Window::KeyboardInteractivityOnDemand) {
        return -4;
    }
    if (exclusive_zone != 0) {
        return -5;
    }
    if (width < 1 || height < 1) {
        return -7;
    }
    auto *window = static_cast<QWindow *>(window_pointer);
    auto *screen = static_cast<QScreen *>(screen_pointer);
    if (!window || !screen || !scope) {
        return -1;
    }
    auto *surface = LayerShellQt::Window::get(window);
    if (!surface) {
        return -6;
    }
    surface->setScope(QString::fromUtf8(scope));
    surface->setLayer(static_cast<LayerShellQt::Window::Layer>(layer));
    surface->setAnchors(LayerShellQt::Window::Anchors(
        QFlags<LayerShellQt::Window::Anchor>::fromInt(anchors)));
    surface->setExclusiveZone(0);
    surface->setKeyboardInteractivity(
        static_cast<LayerShellQt::Window::KeyboardInteractivity>(keyboard));
    surface->setActivateOnShow(false);
    surface->setCloseOnDismissed(false);
    surface->setMargins(QMargins(0, 0, 0, 0));
    surface->setDesiredSize(QSize(width, height));
    surface->setScreen(screen);
    return 0;
}
