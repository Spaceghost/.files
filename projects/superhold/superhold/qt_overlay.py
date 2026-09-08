# SPDX-License-Identifier: GPL-3.0-or-later
"""Theme-native, mouse-scrollable shortcut cards without keyboard focus.

Only the Wayland surface adapter needs native code. The source collector and
hold state machine do not depend on Qt. No process-wide Qt theme is selected:
LXQt, qt6ct, or the desktop's other platform plugin supplies fonts and colors.
"""
import ctypes
import os
from pathlib import Path
import sys

from PyQt6 import sip
from PyQt6.QtCore import QEvent, QMargins, QRect, QRectF, Qt, QTimer
from PyQt6.QtGui import QFont, QPainter, QPalette
from PyQt6.QtWidgets import (QApplication, QFrame, QHBoxLayout, QLabel,
                             QLayout, QScrollArea, QSizePolicy, QStyle, QVBoxLayout,
                             QWidget)


_application = None
_layer_bridge = None


def _default_layer_library(module_file=None):
    """Resolve an installed share/superhold tree, including DESTDIR staging."""
    module = Path(module_file or __file__).resolve()
    candidates = []
    if (module.parent.name == 'superhold'
            and module.parent.parent.name == 'superhold'
            and module.parent.parent.parent.name == 'share'):
        prefix = module.parents[3]
        candidates.extend(prefix / directory / 'superhold/libsuperhold-layer-shell.so'
                          for directory in ('lib', 'lib64'))
    candidates.append(Path('/usr/lib/superhold/libsuperhold-layer-shell.so'))
    return next((path for path in candidates if path.is_file()), candidates[-1])


def _load_layer_bridge():
    global _layer_bridge
    if _layer_bridge is not None:
        return _layer_bridge
    path = (os.environ.get('SUPERHOLD_LAYER_SHELL_LIBRARY')
            or os.environ.get('HOLD_TO_HELP_LAYER_SHELL_LIBRARY')
            or _default_layer_library())
    try:
        bridge = ctypes.CDLL(os.fspath(Path(path)))
        # An explicit old override can still point at the previous installed ABI.
        for name in ('prepare', 'configure'):
            current = 'superhold_layer_shell_' + name
            if not hasattr(bridge, current):
                setattr(bridge, current, getattr(bridge, 'hth_layer_shell_' + name))
        bridge.superhold_layer_shell_prepare.argtypes = []
        bridge.superhold_layer_shell_prepare.restype = ctypes.c_int
        bridge.superhold_layer_shell_configure.argtypes = [
            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int]
        bridge.superhold_layer_shell_configure.restype = ctypes.c_int
    except (OSError, AttributeError) as error:
        raise RuntimeError(f'Wayland layer-shell bridge is unavailable: {path}') from error
    _layer_bridge = bridge
    return bridge


def create_application(argv=None):
    """Create Qt once, preparing layer-shell before any Wayland windows exist."""
    global _application
    existing = QApplication.instance()
    if existing is not None:
        _application = existing
        return existing
    arguments = list(sys.argv if argv is None else argv)
    if not arguments:
        arguments = ['superhold']
    platform = os.environ.get('QT_QPA_PLATFORM', '').split(';', 1)[0].split(':', 1)[0]
    for index, argument in enumerate(arguments[:-1]):
        if argument in ('-platform', '--platform'):
            platform = arguments[index + 1].split(':', 1)[0]
    wayland = platform.startswith('wayland') or (
        not platform and bool(os.environ.get('WAYLAND_DISPLAY')))
    if wayland and _load_layer_bridge().superhold_layer_shell_prepare() != 0:
        raise RuntimeError('could not prepare the Wayland layer-shell integration')
    _application = QApplication(arguments)
    _application.setApplicationName('superhold')
    _application.setDesktopFileName('io.github.spaceghost.Superhold')
    _application.setQuitOnLastWindowClosed(False)
    return _application


class _Card(QWidget):
    """A quiet rounded surface whose colors remain native palette roles."""

    def __init__(self, role=QPalette.ColorRole.Window, parent=None):
        super().__init__(parent)
        self.color_role = role
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self.palette().brush(self.color_role))
        radius = self.fontMetrics().height() * .5
        painter.drawRoundedRect(QRectF(self.rect()), radius, radius)


class _SurfaceWindow(QWidget):
    def changeEvent(self, event):
        super().changeEvent(event)
        callback = getattr(self, 'theme_changed', None)
        if callback and event.type() in (QEvent.Type.ApplicationFontChange,
                                         QEvent.Type.FontChange, QEvent.Type.StyleChange):
            callback()


class _Label(QLabel):
    def __init__(self, text, name, role='body', parent=None):
        super().__init__(str(text), parent)
        self.semantic_role = role
        self._syncing_font = False
        self.setObjectName(name)
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setOpenExternalLinks(False)
        self.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setWordWrap(True)
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self._sync_font()

    def _sync_font(self):
        if self._syncing_font:
            return
        self._syncing_font = True
        try:
            font = QFont(QApplication.font('QLabel'))
            if self.semantic_role in ('title', 'section', 'key'):
                font.setWeight(QFont.Weight.DemiBold)
            if self.semantic_role == 'title':
                if font.pointSizeF() > 0:
                    font.setPointSizeF(font.pointSizeF() * 1.4)
                elif font.pixelSize() > 0:
                    font.setPixelSize(round(font.pixelSize() * 1.4))
            self.setFont(font)
        finally:
            self._syncing_font = False

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() in (QEvent.Type.ApplicationFontChange, QEvent.Type.FontChange,
                            QEvent.Type.StyleChange):
            self._sync_font()


class _Keycap(_Label):
    def __init__(self, text, parent=None):
        super().__init__(text, 'shortcut-key', 'key', parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setForegroundRole(QPalette.ColorRole.ButtonText)
        self.setMargin(max(3, self.fontMetrics().height() // 4))

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self.palette().brush(QPalette.ColorRole.Button))
        radius = self.fontMetrics().height() * .25
        painter.drawRoundedRect(QRectF(self.rect()), radius, radius)
        painter.end()
        super().paintEvent(event)


def _context_rect(context):
    values = context.get('_output_rect')
    if not isinstance(values, dict):
        return None
    try:
        components = [values[name] for name in ('x', 'y', 'width', 'height')]
        if any(type(value) is not int for value in components):
            return None
        rect = QRect(*components)
        return rect if rect.width() > 0 and rect.height() > 0 else None
    except (KeyError, OverflowError):
        return None


class QtShortcutOverlay:
    """One reusable surface; the service owns hold/release and session guards."""

    def __init__(self, trigger_label='Super'):
        self.app = create_application([])
        self.trigger_label = str(trigger_label)
        self.wayland = self.app.platformName().startswith('wayland')
        self.bridge = _load_layer_bridge() if self.wayland else None
        self.window = _SurfaceWindow(flags=(Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint
                                            | Qt.WindowType.WindowStaysOnTopHint
                                            | Qt.WindowType.WindowDoesNotAcceptFocus))
        self.window.setObjectName('superhold')
        self.window.setWindowTitle('Keyboard shortcuts')
        self.window.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.window.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.window.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.layout = QVBoxLayout(self.window)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
        self.panel = _Card(parent=self.window)
        self.panel.setObjectName('help-panel')
        self.layout.addWidget(self.panel)
        self.panel_layout = QVBoxLayout(self.panel)
        self._context = {}
        self._loading = False
        self._closed = False
        self._screen = None
        self._remeasure_pending = False
        self.window.theme_changed = self._queue_remeasure

    def _queue_remeasure(self):
        if not self._closed and not self._remeasure_pending:
            self._remeasure_pending = True
            # Let Qt propagate the new font/style through all child widgets
            # before measuring their wrapped text and native scroll gutter.
            QTimer.singleShot(0, self._remeasure)

    def _remeasure(self):
        self._remeasure_pending = False
        if not self._closed and self.window.isVisible():
            self._place(self._context, loading=self._loading)

    def _clear(self):
        while self.panel_layout.count():
            item = self.panel_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()

    def _header(self, title):
        self.panel_layout.addWidget(_Label(title, 'help-title', 'title', self.panel))
        hint = _Label(f'Release {self.trigger_label} to close  ·  Scroll for more',
                      'help-hint', parent=self.panel)
        hint.setForegroundRole(QPalette.ColorRole.PlaceholderText)
        self.panel_layout.addWidget(hint)

    def _select_screen(self, context):
        screens = self.app.screens()
        rect = _context_rect(context)
        name = context.get('output')
        screen = next((item for item in screens if item.name() == name), None)
        if screen is None and rect is not None:
            screen = next((item for item in screens if item.geometry() == rect), None)
            if screen is None:
                screen = next((item for item in screens
                               if item.geometry().contains(rect.center())), None)
        return screen or self.app.primaryScreen()

    def _place(self, context, loading=False):
        screen = self._select_screen(context)
        bounds = screen.availableGeometry()
        requested = _context_rect(context)
        if requested is not None and requested.intersects(bounds):
            bounds = bounds.intersected(requested)
        gap = min(16, bounds.width() // 20, bounds.height() // 20)
        inner = bounds.marginsRemoved(QMargins(gap, gap, gap, gap))
        line = self.window.fontMetrics().height()
        width = min(inner.width(), max(420, line * (30 if loading else 46)))
        width = max(1, width)
        padding = min(max(10, line), max(2, width // 20))
        self.panel_layout.setContentsMargins(padding, padding, padding, padding)
        self.panel_layout.setSpacing(max(6, line // 2))
        height = max(1, min(inner.height(), line * (9 if loading else 35),
                            self._natural_height(width)))
        self.window.setFixedSize(width, height)
        if screen != self._screen:
            if self.wayland and self._screen is not None:
                # A layer surface's output is fixed at creation. Changing only
                # QScreen cannot move a mapped wl_surface to another output.
                self.window.hide()
                handle = self.window.windowHandle()
                if handle is not None:
                    handle.destroy()
            self.window.setScreen(screen)
            self._screen = screen
        if self.wayland:
            # QWidget creates its QWindow lazily. The layer configuration is
            # attached while hidden, before any show/activation request.
            self.window.winId()
            handle = self.window.windowHandle()
            margin = inner.top() - screen.geometry().top()
            result = self.bridge.superhold_layer_shell_configure(
                int(sip.unwrapinstance(handle)), int(sip.unwrapinstance(screen)),
                width, height, margin)
            if result != 0:
                raise RuntimeError('could not configure the non-focusable layer surface')
        else:
            self.window.move(inner.x() + (inner.width() - width) // 2, inner.y())

    def _natural_height(self, width):
        margins = self.panel_layout.contentsMargins()
        available = max(1, width - margins.left() - margins.right())
        height = margins.top() + margins.bottom()
        count = 0
        for index in range(self.panel_layout.count()):
            widget = self.panel_layout.itemAt(index).widget()
            if widget is None:
                continue
            count += 1
            if isinstance(widget, QScrollArea):
                content = widget.widget()
                # Reserve the native scroll gutter when measuring wrapping;
                # it can appear as soon as this content reaches the height cap.
                gutter = widget.style().pixelMetric(QStyle.PixelMetric.PM_ScrollBarExtent)
                content_width = max(1, available - gutter)
                content_layout = content.layout()
                measured = content_layout.totalHeightForWidth(content_width)
                height += max(content_layout.minimumSize().height(), measured)
            else:
                measured = widget.heightForWidth(available)
                height += measured if measured >= 0 else widget.sizeHint().height()
        return height + max(0, count - 1) * self.panel_layout.spacing()

    def show_loading(self, context=None):
        self._context = context if isinstance(context, dict) else {}
        self._loading = True
        self._clear()
        self._header('Keyboard shortcuts')
        self.panel_layout.addWidget(_Label('Loading the focused context…', 'help-loading',
                                           parent=self.panel))
        self.panel_layout.addStretch()
        self._place(self._context, loading=True)
        self.window.show()

    def show(self, snapshot):
        self._context = snapshot
        self._loading = False
        self._clear()
        self._header(f"{snapshot.get('app') or 'Current context'} shortcuts")
        scroll = QScrollArea(self.panel)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidgetResizable(True)
        scroll.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setAutoFillBackground(False)
        scroll.viewport().setAutoFillBackground(False)
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(max(8, self.window.fontMetrics().height() // 2))
        for section in snapshot.get('sections', []):
            card = _Card(QPalette.ColorRole.AlternateBase, content)
            card_layout = QVBoxLayout(card)
            heading = _Label(section.get('title', 'Shortcuts'), 'shortcut-section',
                             'section', card)
            card_layout.addWidget(heading)
            coverage = _Label(section.get('coverage', 'Unknown coverage'),
                              'shortcut-coverage', parent=card)
            coverage.setForegroundRole(QPalette.ColorRole.PlaceholderText)
            card_layout.addWidget(coverage)
            for row in section.get('rows', []):
                line = QHBoxLayout()
                line.setSpacing(max(8, card.fontMetrics().height() // 2))
                key = _Keycap(row.get('key', '—'), card)
                description = _Label(row.get('description', ''), 'shortcut-description',
                                     parent=card)
                line.addWidget(key, 2)
                line.addWidget(description, 5)
                card_layout.addLayout(line)
            content_layout.addWidget(card)
        content_layout.addStretch()
        scroll.setWidget(content)
        content.setAutoFillBackground(False)
        self.panel_layout.addWidget(scroll, 1)
        self._place(snapshot)
        self.window.show()

    def hide(self):
        self.window.hide()

    def close(self):
        if self._closed:
            return
        self._closed = True
        self.window.theme_changed = None
        self.window.close()
        self.window.deleteLater()
