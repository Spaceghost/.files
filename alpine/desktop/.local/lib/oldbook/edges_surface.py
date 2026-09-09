"""One static effect on the BOTTOM layer, drawn only where the desktop is free.

This is the whole of plank 1: a Qt Quick layer surface per output that reads the
region `oldbook-space` publishes and draws the signal margin inside it. It
proves the layer order, the clipping of Conky and the bar, the empty input
region, the zero exclusive zone and the theme wiring -- and nothing else.

Static is the point, not a limitation. Qt Quick renders when the scene is dirty
rather than on a fixed tick, so a surface that never animates costs one paint
per change and nothing at rest. It also leaves SceneFX's pre-rendered
optimized-blur buffer alone, and what an animating BOTTOM surface does to that
buffer is unmeasured; measuring it is the gate on the plank that animates.

Everything that can move this surface is a discrete event: the free region
changing, the palette changing, the power posture changing, an output arriving
or leaving. There is no frame clock and no timer running at rest.
"""
import ctypes
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys

from PyQt6 import sip
from PyQt6.QtCore import (QFileSystemWatcher, QObject, QSocketNotifier, QTimer,
                          QUrl, Qt)
from PyQt6.QtGui import QColor, QGuiApplication, QRegion, QSurfaceFormat
from PyQt6.QtQuick import QQuickView

import desktop_space
import overlay_theme
import power_source

REPO = Path(__file__).resolve().parents[5]
BIN = Path(__file__).resolve().parents[2] / 'bin'
QML = Path(__file__).resolve().parents[2] / 'share/oldbook/qml/SignalMargin.qml'
BUILDER = REPO / 'alpine/bin/build-layer-shell-bridge'

NAMESPACE = desktop_space.EFFECT_NAMESPACE
# LayerShellQt enumerators, mirrored rather than imported: the bridge validates
# every one of them and refuses anything else.
LAYER_BOTTOM = 1
ANCHOR_ALL = 15
KEYBOARD_NONE = 0
EXCLUSIVE_ZONE = 0

# The name this effect asks the power ladder about. It is not in
# `power_source.LADDER` yet, and the ladder answers "yes" for a name it does not
# know on purpose -- registering is what switches an effect off, never
# forgetting to. The moment `'desktop-edges': 'battery-low'` is added there,
# this starts shedding with no change here.
LADDER_EFFECT = 'desktop-edges'

# Every colour is a palette role. `muted` at 0.14 is the graduation ink.
TICK_ROLE = 'muted'
TICK_ALPHA = 0.14

DEFAULTS = {'enabled': False, 'signal-margin': True}


def preferences_path():
    base = os.environ.get('XDG_CONFIG_HOME') or str(Path.home() / '.config')
    return Path(base) / 'oldbook/edges.json'


def preferences(path=None):
    """Off unless the file says otherwise.

    Installing this must change nothing. One key turns the surface on, one key
    per effect turns each drawing off, and deleting the file returns the desktop
    to exactly what it was.
    """
    settings = dict(DEFAULTS)
    try:
        record = json.loads((path or preferences_path()).read_text())
    except (OSError, ValueError, AttributeError):
        return settings
    if isinstance(record, dict):
        for key, value in record.items():
            if key in settings and isinstance(value, bool):
                settings[key] = value
    return settings


def library_path(allow_local=False):
    """The bridge, taken from the cache under the hash of its own source.

    The edge surfaces start with the session, and a session start is the last
    place a C++ compile should appear: it is unasked for, it happens while the
    desktop is coming up, and on this laptop it is heard. So this asks for the
    cache and nothing more. When the source has changed and no cache entry
    matches, the surfaces stay down and say why rather than building, and
    `alpine/bin/build-layer-shell-bridge` is the deliberate act that fixes it.
    """
    override = os.environ.get('OLDBOOK_LAYER_SHELL_LIBRARY')
    if override:
        return Path(override)
    name = 'oldbook_layer_shell_build'
    # The builder is an extensionless script, so it needs its loader named.
    loader = importlib.machinery.SourceFileLoader(name, os.fspath(BUILDER))
    specification = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(specification)
    loader.exec_module(module)
    return module.build(allow_local=allow_local)


def load_bridge(path=None):
    try:
        bridge = ctypes.CDLL(os.fspath(path or library_path()))
        bridge.oldbook_layer_shell_configure.argtypes = [
            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int,
            ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int]
        bridge.oldbook_layer_shell_configure.restype = ctypes.c_int
    except (OSError, AttributeError, ValueError, RuntimeError,
            subprocess.CalledProcessError) as error:
        raise RuntimeError(f'the Wayland layer-shell bridge is unavailable: {error}') from error
    return bridge


def create_application(argv=None):
    """Qt, told to make layer surfaces before it makes its first window.

    All `LayerShellQt::Shell::useLayerShell()` ever did was set this variable,
    and Qt has not needed the call since 6.5; setting it here keeps the C side
    down to the one function that has no Python binding.
    """
    existing = QGuiApplication.instance()
    if existing is not None:
        return existing
    # This process only ever makes layer surfaces; an inherited value for
    # another integration would quietly turn the backdrop into a window.
    os.environ['QT_WAYLAND_SHELL_INTEGRATION'] = 'layer-shell'
    surface = QSurfaceFormat.defaultFormat()
    surface.setAlphaBufferSize(8)
    QSurfaceFormat.setDefaultFormat(surface)
    application = QGuiApplication(list(argv if argv is not None else sys.argv) or [NAMESPACE])
    application.setApplicationName(NAMESPACE)
    application.setQuitOnLastWindowClosed(False)
    return application


class EdgeSurface:
    """One BOTTOM-layer surface on one output, above the painting, below windows.

    BOTTOM rather than BACKGROUND for reasons that are not aesthetic. Ordering
    against the background layer is guaranteed by the protocol while ordering
    *within* it is map order, and `background_fade.surface_order()` inspects only
    background-layer surfaces, so a BOTTOM surface can never trip its restack or
    make it restart Conky. The price is that this draws over the reading cards,
    which is why the region excludes them.
    """

    def __init__(self, screen, bridge, source=QML):
        self.screen = screen
        self.bridge = bridge
        self.view = QQuickView()
        self.view.setColor(QColor(0, 0, 0, 0))
        self.view.setFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint
                           | Qt.WindowType.WindowDoesNotAcceptFocus
                           | Qt.WindowType.WindowTransparentForInput)
        self.view.setResizeMode(QQuickView.ResizeMode.SizeRootObjectToView)
        self.view.setScreen(screen)
        geometry = screen.geometry()
        self.view.resize(geometry.size())
        self.view.setSource(QUrl.fromLocalFile(os.fspath(source)))
        if self.view.status() != QQuickView.Status.Ready:
            raise RuntimeError('; '.join(str(error.toString())
                                         for error in self.view.errors()) or 'QML did not load')
        # Every layer property is set while the QWindow still has no platform
        # window, because the namespace is a creation argument: `layer_effects`,
        # the region's exclusion of this surface and `swaymsg` all key on it.
        result = self.bridge.oldbook_layer_shell_configure(
            int(sip.unwrapinstance(self.view)), int(sip.unwrapinstance(screen)),
            NAMESPACE.encode(), LAYER_BOTTOM, ANCHOR_ALL, EXCLUSIVE_ZONE,
            KEYBOARD_NONE, geometry.width(), geometry.height())
        if result != 0:
            raise RuntimeError(f'could not configure the {NAMESPACE} layer surface: {result}')
        self.mapped = False

    def show(self):
        if self.mapped:
            return
        self.view.show()
        self._clear_input_region()
        self.mapped = True

    def hide(self):
        if self.mapped:
            self.view.hide()
            self.mapped = False

    def _clear_input_region(self):
        """Pass every click through to whatever is underneath.

        `QWindow.setMask` is Qt's way to the Wayland input region, but Qt reads
        an *empty* QRegion as "no restriction" and hands the surface the whole
        output. A one-pixel region outside the surface is a real region that the
        compositor clips away to nothing, so a Conky reading card keeps its own
        click actions and the scripture bar keeps its focus.
        """
        self.view.setMask(QRegion(-1, -1, 1, 1))

    def apply(self, region, palette, allowed):
        if not allowed:
            self.hide()
            return
        root = self.view.rootObject()
        colour = QColor(palette.get(TICK_ROLE, overlay_theme.FALLBACK[TICK_ROLE]))
        root.setProperty('columns', region['columns'])
        root.setProperty('rows', region['rows'])
        root.setProperty('tickColor', colour)
        root.setProperty('tickAlpha', TICK_ALPHA)
        # A fullscreen view covers this surface completely; there is nothing to
        # draw and nothing to clip, so the scene simply empties.
        root.setProperty('active', not region.get('fullscreen'))
        root.setProperty('grid', list(region['grid']))
        self.show()

    def close(self):
        self.hide()
        self.view.setSource(QUrl())
        self.view.deleteLater()


class Session(QObject):
    """One owner per compositor session; every redraw has a named cause."""

    def __init__(self, application, bridge, source=QML, parent=None):
        super().__init__(parent)
        self.application = application
        self.bridge = bridge
        self.source = source
        self.surfaces = {}
        self.settings = preferences()
        self.pending = QTimer(self)
        self.pending.setSingleShot(True)
        self.pending.setInterval(60)
        self.pending.timeout.connect(self.refresh)
        self.watcher = None
        application.screenAdded.connect(lambda _screen: self.schedule())
        application.screenRemoved.connect(self._forget)

    def watch(self):
        """Wake on the files that can change what is drawn, and on no timer."""
        self.watcher = QFileSystemWatcher(self)
        self.watcher.fileChanged.connect(lambda _path: self.schedule())
        self.watcher.directoryChanged.connect(lambda _path: self.schedule())
        paths = [desktop_space.runtime_directory(), desktop_space.state_path(),
                 power_source.state_path(), overlay_theme.THEMES,
                 overlay_theme.THEMES / 'current', overlay_theme.override_path(),
                 overlay_theme.override_path().parent, preferences_path().parent,
                 preferences_path()]
        for path in paths:
            if path.exists():
                self.watcher.addPath(os.fspath(path))
        return self.watcher

    def schedule(self):
        # Collapse the burst a replaced file produces into one repaint. The
        # timer exists only between the event and the repaint; at rest nothing
        # is running.
        self.pending.start()

    def _forget(self, screen):
        surface = self.surfaces.pop(screen.name(), None)
        if surface is not None:
            surface.close()

    def refresh(self):
        self.settings = preferences()
        record = desktop_space.published()
        palette = overlay_theme.read_palette()
        allowed = (self.settings['enabled'] and self.settings['signal-margin']
                   and power_source.allows(LADDER_EFFECT))
        regions = {region['output']: region for region in record.get('regions', [])}
        screens = {screen.name(): screen for screen in self.application.screens()}
        for name in list(self.surfaces):
            if name not in regions or name not in screens:
                self.surfaces.pop(name).close()
        for name, region in regions.items():
            screen = screens.get(name)
            if screen is None:
                continue
            surface = self.surfaces.get(name)
            if surface is None:
                if not allowed:
                    continue
                surface = self.surfaces[name] = EdgeSurface(screen, self.bridge, self.source)
            surface.apply(region, palette, allowed)
        if self.watcher is not None:
            # A watched file replaced by rename is no longer the watched inode.
            for path in (desktop_space.state_path(), power_source.state_path(),
                         overlay_theme.override_path(), preferences_path()):
                if path.exists() and os.fspath(path) not in self.watcher.files():
                    self.watcher.addPath(os.fspath(path))

    def close(self):
        for surface in self.surfaces.values():
            surface.close()
        self.surfaces.clear()


def start_space_service():
    """Bring up the publisher behind our own claim; a second start is a no-op."""
    service = BIN / 'oldbook-space'
    subprocess.Popen([sys.executable, os.fspath(service), 'run'],
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, start_new_session=True)


def install_quit_handler(application):
    """Leave on a signal without a polling timer to notice it."""
    reader, writer = socket.socketpair()
    for connection in (reader, writer):
        connection.setblocking(False)
    signal.set_wakeup_fd(writer.fileno())
    for number in (signal.SIGTERM, signal.SIGINT):
        signal.signal(number, lambda *_: None)
    def leave(*_):
        try:
            reader.recv(4096)
        except OSError:
            pass
        application.quit()

    notifier = QSocketNotifier(reader.fileno(), QSocketNotifier.Type.Read, application)
    notifier.activated.connect(leave)
    application.oldbook_quit_channel = (reader, writer, notifier)


def run(source=QML):
    """Map the surface and stay until told to go."""
    application = create_application()
    bridge = load_bridge()
    install_quit_handler(application)
    with desktop_space.Subscription(NAMESPACE):
        start_space_service()
        session = Session(application, bridge, source)
        session.watch()
        session.refresh()
        try:
            return application.exec()
        finally:
            session.close()
