"""Verify LXQt's native settings reuse Gruvbox and update a running Qt app."""
import configparser
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[2]
DESKTOP = REPO / 'alpine/desktop'
LXQT = DESKTOP / '.config/lxqt/lxqt.conf'
PRESET = DESKTOP / '.local/share/lxqt/palettes/Gruvbox-Dark'
ROLES = {'window_text_color': 0, 'text_color': 6, 'base_color': 9,
         'window_color': 10, 'highlight_color': 12, 'highlighted_text_color': 13,
         'link_color': 14, 'link_visited_color': 15, 'tooltip_base_color': 18,
         'tooltip_text_color': 19}


def settings(path):
    result = configparser.ConfigParser()
    result.optionxform = str
    with path.open() as stream:
        result.read_file(stream)
    return result


class LXQtThemeTests(unittest.TestCase):
    def test_native_palette_and_preset_match_existing_qt6ct_colors(self):
        current = settings(DESKTOP / '.config/qt6ct/colors/gruvbox-dark.conf')
        colors = [value.strip() for value in current['ColorScheme']['active_colors'].split(',')]
        expected = {name: '#' + colors[index][-6:] for name, index in ROLES.items()}
        self.assertEqual(dict(settings(LXQT)['Palette']), expected)
        self.assertEqual(dict(settings(PRESET)['Palette']), expected)

    def test_font_and_icon_preferences_match_existing_desktop(self):
        qt = settings(DESKTOP / '.config/qt6ct/qt6ct.conf')
        lxqt = settings(LXQT)
        self.assertEqual(lxqt['Qt']['font'], qt['Fonts']['general'])
        self.assertEqual(lxqt['Qt']['fixedFont'], qt['Fonts']['fixed'])
        self.assertEqual(lxqt['General']['icon_theme'], qt['Appearance']['icon_theme'])
        self.assertNotIn('styleSheet', lxqt['Qt'])

    def test_actual_lxqt_plugin_reads_and_follows_private_configuration(self):
        try:
            from PyQt6.QtCore import QLibraryInfo
        except ImportError:
            self.skipTest('PyQt6 is not installed')
        plugins = Path(QLibraryInfo.path(QLibraryInfo.LibraryPath.PluginsPath))
        if not (plugins / 'platformthemes/libqtlxqt.so').is_file():
            self.skipTest('LXQt platform theme plugin is not installed')
        with tempfile.TemporaryDirectory(prefix='oldbook-lxqt-theme-') as work:
            root = Path(work)
            config = root / 'config/lxqt/lxqt.conf'
            config.parent.mkdir(parents=True)
            shutil.copyfile(LXQT, config)
            env = dict(os.environ, XDG_CONFIG_HOME=str(root / 'config'),
                       XDG_CONFIG_DIRS=str(root / 'empty'), XDG_DATA_HOME=str(root / 'data'),
                       XDG_RUNTIME_DIR=str(root), QT_QPA_PLATFORM='offscreen',
                       QT_QPA_PLATFORMTHEME='lxqt')
            env.pop('QT_STYLE_OVERRIDE', None)
            code = '''
import json,time
from PyQt6.QtCore import QSettings
from PyQt6.QtGui import QIcon,QPalette
from PyQt6.QtWidgets import QApplication
app=QApplication([])
initial={'window':app.palette().color(QPalette.ColorRole.Window).name(),
         'font':app.font().family(),'size':app.font().pointSizeF(),
         'icon':QIcon.themeName()}
app.processEvents()
settings=QSettings(QSettings.Scope.UserScope,'lxqt','lxqt')
settings.setValue('Palette/window_color','#101010')
settings.setValue('Qt/font','Inter,13,-1,5,50,0,0,0,0,0')
settings.sync()
deadline=time.monotonic()+2
while time.monotonic()<deadline:
 app.processEvents()
 if app.palette().color(QPalette.ColorRole.Window).name()=='#101010' and app.font().pointSizeF()==13:break
 time.sleep(.01)
print(json.dumps({'initial':initial,'updated_window':app.palette().color(QPalette.ColorRole.Window).name(),
                  'updated_font_size':app.font().pointSizeF()}))
'''
            result = subprocess.run([sys.executable, '-c', code], env=env,
                                    capture_output=True, text=True, timeout=8, check=True)
            actual = json.loads(result.stdout)
            self.assertEqual(actual['initial'], {'window': '#282828', 'font': 'Inter',
                                                'size': 11.0, 'icon': 'Oldbook-Gruvbox'})
            self.assertEqual(actual['updated_window'], '#101010')
            self.assertEqual(actual['updated_font_size'], 13)


if __name__ == '__main__':
    unittest.main()
