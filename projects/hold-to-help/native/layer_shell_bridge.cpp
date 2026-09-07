// SPDX-License-Identifier: GPL-3.0-or-later
// Small C ABI boundary: Python retains ownership of QWindow and QScreen.
#include <LayerShellQt/Shell>
#include <LayerShellQt/Window>
#include <QCoreApplication>
#include <QMargins>
#include <QScreen>
#include <QSize>
#include <QWindow>

extern "C" Q_DECL_EXPORT int hth_layer_shell_prepare()
{
    if (QCoreApplication::instance()) {
        return -1;
    }
    // Keep this before QApplication, including on Qt versions predating
    // automatic layer integration. It changes no platform theme setting.
    LayerShellQt::Shell::useLayerShell();
    return 0;
}

extern "C" Q_DECL_EXPORT int hth_layer_shell_configure(
    void *window_pointer, void *screen_pointer, int width, int height, int top_margin)
{
    auto *window = static_cast<QWindow *>(window_pointer);
    auto *screen = static_cast<QScreen *>(screen_pointer);
    if (!window || !screen || width < 1 || height < 1 || top_margin < 0) {
        return -1;
    }
    auto *layer = LayerShellQt::Window::get(window);
    if (!layer) {
        return -1;
    }
    layer->setScope(QStringLiteral("hold-to-help"));
    layer->setLayer(LayerShellQt::Window::LayerOverlay);
    layer->setKeyboardInteractivity(LayerShellQt::Window::KeyboardInteractivityNone);
    layer->setActivateOnShow(false);
    layer->setExclusiveZone(0);
    layer->setAnchors(LayerShellQt::Window::AnchorTop);
    layer->setMargins(QMargins(0, top_margin, 0, 0));
    layer->setDesiredSize(QSize(width, height));
    layer->setCloseOnDismissed(false);
    layer->setScreen(screen);
    return 0;
}
