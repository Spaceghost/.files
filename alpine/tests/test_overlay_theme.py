import json
import os
from pathlib import Path
import runpy
import tempfile
import unittest

MODULE=Path(__file__).resolve().parents[1]/'desktop/.local/lib/oldbook/overlay_theme.py'


class OverlayThemeTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(MODULE.exists(),'Overlays need a shared active-theme source')
        self.api=runpy.run_path(str(MODULE))
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.themes=Path(self.temp.name)
        (self.themes/'current').write_text('warm')
        (self.themes/'warm.json').write_text(json.dumps({'palette':{'background':'#282828',
            'surface':'#3c3836','foreground':'#ebdbb2','yellow':'#fabd2f'}}))

    def test_theme_switch_updates_surface_and_accent_without_restart(self):
        first=self.api['read_palette'](self.themes)
        self.assertEqual(first['accent'],'#fabd2f')
        (self.themes/'cool.json').write_text(json.dumps({'palette':{'background':'#13091f','foreground':'#eaddf5','accent':'#dca7ff'}}))
        (self.themes/'current').write_text('cool')
        second=self.api['read_palette'](self.themes)
        self.assertEqual(second['background'],'#13091f')
        self.assertEqual(second['accent'],'#dca7ff')
        self.assertNotEqual(first,second)

    def test_invalid_theme_cannot_inject_css(self):
        (self.themes/'warm.json').write_text(json.dumps({'palette':{'background':'red; } * { color: red'}}))
        palette=self.api['read_palette'](self.themes)
        self.assertTrue(all(value.startswith('#') and len(value)==7 for value in palette.values()))
        (self.themes/'current').write_text('../outside')
        self.assertEqual(self.api['read_palette'](self.themes),self.api['FALLBACK'])

    def test_qt_and_gtk_consume_the_same_theme(self):
        os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtGui import QPalette
        self.app=QApplication.instance() or QApplication([])
        palette=self.api['read_palette'](self.themes)
        qt=self.api['qt_palette'](self.app.palette(),palette)
        self.assertEqual(qt.color(QPalette.ColorRole.Window).name(),'#282828')
        self.assertEqual(qt.color(QPalette.ColorRole.Highlight).name(),'#fabd2f')
        css=self.api['gtk_css']('window { color: @theme_foreground; }',palette)
        self.assertIn(b'@define-color theme_foreground #ebdbb2;',css)

    def test_running_qt_overlay_refreshes_after_palette_edit(self):
        os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtGui import QPalette
        app=QApplication.instance() or QApplication([])
        original=app.palette()
        function=self.api['follow_qt_theme']
        globals_=function.__globals__
        reader=globals_['read_palette']
        globals_['read_palette']=lambda: reader(self.themes)
        try:
            function(app)
            self.assertEqual(app.palette().color(QPalette.ColorRole.Window).name(),'#282828')
            (self.themes/'warm.json').write_text(json.dumps({'palette':{'background':'#112233'}}))
            app.oldbook_theme_timer.timeout.emit()
            self.assertEqual(app.palette().color(QPalette.ColorRole.Window).name(),'#112233')
        finally:
            app.oldbook_theme_timer.stop()
            app.setPalette(original)
            globals_['read_palette']=reader
