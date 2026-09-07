# SPDX-License-Identifier: GPL-3.0-or-later
"""Real Qt widget checks; run with QT_QPA_PLATFORM=offscreen."""
import importlib
import os
from pathlib import Path
import sys
import tempfile
import unittest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PyQt6.QtCore import QEvent, QPoint, QPointF, QRect, Qt
from PyQt6.QtGui import QColor, QFont, QPalette, QWheelEvent
from PyQt6.QtWidgets import QApplication, QLabel, QScrollArea, QStyleFactory


class QtOverlayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.module = importlib.import_module('hold_to_help.qt_overlay')
        except ModuleNotFoundError:
            cls.module = None

    def setUp(self):
        self.assertIsNotNone(self.module, 'Qt overlay implementation is missing')
        self.app = self.module.create_application([])
        self.saved_palette = QPalette(self.app.palette())
        self.saved_font = QFont(self.app.font())
        self.saved_style = self.app.style().objectName()
        self.overlay = self.module.QtShortcutOverlay()
        self.snapshot = {
            'app': 'Demo editor',
            'sections': [{'title': 'Editor', 'coverage': 'Partial baseline',
                          'rows': [{'key': 'Ctrl+S', 'description': 'Save'}]}],
        }

    def tearDown(self):
        if not hasattr(self, 'overlay'):
            return
        self.overlay.close()
        self.app.setPalette(self.saved_palette)
        self.app.setFont(self.saved_font)
        self.app.setStyle(self.saved_style)
        self.app.processEvents()

    def test_plaintext_and_all_sections_survive_rendering(self):
        hostile = '<img src="file:///private"> & <a href="https://invalid">Save</a>'
        self.snapshot['app'] = hostile
        self.snapshot['sections'][0]['rows'][0]['description'] = hostile
        self.snapshot['sections'].append({'title': 'Desktop', 'coverage': 'Live',
                                         'rows': [{'key': 'Super+Enter',
                                                   'description': 'Terminal'}]})
        self.overlay.show(self.snapshot)
        self.app.processEvents()
        labels = self.overlay.window.findChildren(QLabel)
        self.assertIn(hostile, [label.text() for label in labels])
        self.assertIn('Desktop', [label.text() for label in labels])
        for label in labels:
            self.assertEqual(label.textFormat(), Qt.TextFormat.PlainText)
            self.assertFalse(label.openExternalLinks())

    def test_palette_changes_repaint_existing_panel_and_keycaps(self):
        self.overlay.show(self.snapshot)
        self.app.processEvents()
        panel = self.overlay.window.findChild(self.module.QWidget, 'help-panel')
        key = self.overlay.window.findChild(QLabel, 'shortcut-key')
        for panel_color, key_color in (('#243b53', '#526d82'), ('#faf0d8', '#dfb79e')):
            palette = QPalette(self.app.palette())
            for group in (QPalette.ColorGroup.Active, QPalette.ColorGroup.Inactive):
                palette.setColor(group, QPalette.ColorRole.Window, QColor(panel_color))
                palette.setColor(group, QPalette.ColorRole.Button, QColor(key_color))
            self.app.setPalette(palette)
            self.app.processEvents()
            self.assertEqual(panel.grab().toImage().pixelColor(20, 3).name(), panel_color)
            self.assertEqual(key.grab().toImage().pixelColor(key.width() // 2, 2).name(),
                             key_color)

    def test_font_and_style_change_preserve_native_inheritance(self):
        self.overlay.show(self.snapshot)
        self.app.processEvents()
        description = self.overlay.window.findChild(QLabel, 'shortcut-description')
        original_height = self.overlay.window.height()
        before = description.font().pointSizeF()
        changed_font = QFont(self.app.font())
        changed_font.setPointSizeF(max(14, before + 3))
        self.app.setFont(changed_font)
        alternate = next((style for style in QStyleFactory.keys()
                          if style.lower() != self.saved_style.lower()), self.saved_style)
        self.app.setStyle(alternate)
        self.app.processEvents()
        self.assertEqual(description.font().pointSizeF(), changed_font.pointSizeF())
        self.assertGreater(self.overlay.window.height(), original_height)
        self.assertEqual(self.overlay.window.style().objectName().lower(), alternate.lower())
        self.assertEqual(self.overlay.window.styleSheet(), '')

    def test_long_overlay_scrolls_without_keyboard_focus(self):
        self.snapshot['sections'][0]['rows'] = [
            {'key': f'Ctrl+{i}', 'description': f'Action {i}'} for i in range(90)]
        self.overlay.show(self.snapshot)
        self.app.processEvents()
        window = self.overlay.window
        self.assertTrue(window.windowFlags() & Qt.WindowType.WindowDoesNotAcceptFocus)
        self.assertTrue(window.testAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating))
        scroll = window.findChild(QScrollArea)
        bar = scroll.verticalScrollBar()
        self.assertGreater(bar.maximum(), 0)
        event = QWheelEvent(QPointF(20, 20), QPointF(20, 20), QPoint(), QPoint(0, -120),
                            Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
                            Qt.ScrollPhase.NoScrollPhase, False)
        self.app.sendEvent(scroll.viewport(), event)
        self.app.processEvents()
        self.assertGreater(bar.value(), 0)
        self.assertIsNone(window.focusWidget())

    def test_small_output_bounds_include_loading_and_long_words(self):
        self.overlay.show_loading({'_output_rect': {'x': 0, 'y': 0, 'width': 320,
                                                  'height': 240}})
        self.app.processEvents()
        self.assertLessEqual(self.overlay.window.width(), 320)
        self.assertLessEqual(self.overlay.window.height(), 240)
        self.snapshot['_output_rect'] = {'x': 0, 'y': 0, 'width': 320, 'height': 240}
        self.snapshot['sections'][0]['rows'][0]['key'] = 'X' * 150
        self.snapshot['sections'][0]['rows'][0]['description'] = 'Y' * 200
        self.overlay.show(self.snapshot)
        self.app.processEvents()
        self.assertLessEqual(self.overlay.window.width(), 320)
        self.assertLessEqual(self.overlay.window.height(), 240)
        self.assertTrue(QRect(0, 0, 320, 240).contains(self.overlay.window.geometry()))

    def test_trigger_hint_loading_and_hide(self):
        self.overlay.close()
        self.overlay = self.module.QtShortcutOverlay(trigger_label='Meta')
        self.overlay.show_loading({})
        self.app.processEvents()
        self.assertTrue(self.overlay.window.isVisible())
        labels = [label.text() for label in self.overlay.window.findChildren(QLabel)]
        self.assertTrue(any('Release Meta' in label and 'Scroll' in label for label in labels))
        self.assertTrue(any('Loading' in label for label in labels))
        self.overlay.hide()
        self.assertFalse(self.overlay.window.isVisible())

    def test_installed_native_library_resolves_under_destdir_prefix(self):
        with tempfile.TemporaryDirectory(prefix='help-install-') as directory:
            prefix = Path(directory) / 'usr/local'
            module = prefix / 'share/hold-to-help/hold_to_help/qt_overlay.py'
            library = prefix / 'lib64/hold-to-help/libhold-to-help-layer-shell.so'
            library.parent.mkdir(parents=True)
            library.touch()
            self.assertEqual(self.module._default_layer_library(module), library)
            # An arbitrary checkout parent is never treated as an install prefix.
            source = prefix / 'projects/hold-to-help/hold_to_help/qt_overlay.py'
            self.assertNotEqual(self.module._default_layer_library(source), library)

    def test_short_snapshot_fits_content_long_snapshot_uses_scrolling(self):
        self.overlay.show(self.snapshot)
        self.app.processEvents()
        short_height = self.overlay.window.height()
        self.snapshot['sections'][0]['rows'] *= 60
        self.overlay.show(self.snapshot)
        self.app.processEvents()
        self.assertLess(short_height * 1.5, self.overlay.window.height())
        self.assertGreater(self.overlay.window.findChild(QScrollArea)
                           .verticalScrollBar().maximum(), 0)


if __name__ == '__main__':
    unittest.main()
