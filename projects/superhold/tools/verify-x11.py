#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Exercise actual X11 Qt surfaces in a private Xvfb/Openbox desktop."""
import argparse
import json
import os
from pathlib import Path
import select
import subprocess
import sys
import tempfile
import time


def child(output):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from superhold.qt_overlay import create_application, QtShortcutOverlay
    from PyQt6.QtCore import QPoint
    from PyQt6.QtGui import QColor, QPalette
    from PyQt6.QtWidgets import QLineEdit, QScrollArea
    from Xlib import X, display
    from Xlib.ext import xtest

    app = create_application([])
    connection = display.Display()
    root = connection.screen().root

    def pump(seconds=.3):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            app.processEvents()
            time.sleep(.01)

    control = QLineEdit('Synthetic focus control; no personal application data')
    control.setWindowTitle('Superhold X11 focus control')
    control.resize(600, 60)
    control.move(30, 830)
    control.show()
    pump()
    control_id = int(control.winId())
    connection.set_input_focus(control_id, X.RevertToParent, X.CurrentTime)
    connection.sync()
    pump()
    focus = connection.get_input_focus().focus.id
    assert focus == control_id, (focus, control_id)
    overlay = QtShortcutOverlay()
    snapshot = {'app': 'Space Ghost editor', 'output': '', 'sections': [{
        'title': 'Editor shortcuts', 'coverage': 'Synthetic native verification data',
        'rows': [{'key': f'Ctrl+{i}', 'description': f'Undo Zorak’s contribution {i}'} for i in range(60)]}]}
    overlay.show(snapshot)
    pump()
    native = connection.create_resource_object('window', int(overlay.window.winId()))
    assert native.get_attributes().map_state == X.IsViewable
    assert native.get_wm_hints()['input'] == 0
    assert connection.get_input_focus().focus.id == focus
    scroll = overlay.window.findChild(QScrollArea)
    bar = scroll.verticalScrollBar()
    assert bar.maximum() > 0
    point = scroll.viewport().mapToGlobal(QPoint(100, 100))
    root.warp_pointer(point.x(), point.y())
    connection.sync()
    pump(.15)
    for _ in range(3):
        xtest.fake_input(connection, X.ButtonPress, 5)
        xtest.fake_input(connection, X.ButtonRelease, 5)
    connection.sync()
    pump()
    assert bar.value() > 0, 'actual X11 wheel events did not scroll'
    assert connection.get_input_focus().focus.id == focus
    initial = app.palette().color(QPalette.ColorRole.Window).name()
    font = app.font().toString()
    app.primaryScreen().grabWindow(0).save(str(output / 'desktop-native-theme.png'))
    # A palette event is the cross-plugin contract. This changes only this test
    # process and proves the existing visible window repaints without reopening.
    changed = QPalette(app.palette())
    changed.setColor(QPalette.ColorRole.Window, QColor('#123456'))
    app.setPalette(changed)
    pump()
    pixel = overlay.panel.grab().toImage().pixelColor(20, 20).name()
    assert pixel == '#123456', pixel
    assert connection.get_input_focus().focus.id == focus
    overlay.hide()
    pump()
    assert native.get_attributes().map_state != X.IsViewable
    evidence = {'backend': app.platformName(), 'platform_theme': os.environ.get('QT_QPA_PLATFORMTHEME'),
                'initial_window_color': initial, 'font': font,
                'visible_surface': True, 'wm_hints_input': False,
                'focus_preserved_show_scroll_palette_hide': True,
                'physical_wheel_scrolled': True, 'palette_event_repaint': pixel,
                'hidden_surface_unmapped': True, 'synthetic_context_only': True}
    (output / 'evidence.json').write_text(json.dumps(evidence, indent=2) + '\n')
    overlay.close()
    control.close()
    connection.close()
    print(json.dumps(evidence))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--theme', default='qt6ct', help='Installed Qt platform theme plugin')
    parser.add_argument('--child', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    output = args.output.absolute()
    output.mkdir(parents=True, exist_ok=True)
    if args.child:
        child(output)
        return
    with tempfile.TemporaryDirectory(prefix='superhold-x11-') as directory:
        runtime = Path(directory)
        runtime.chmod(0o700)
        reader, writer = os.pipe()
        xvfb = wm = None
        try:
            with (output / 'xvfb.log').open('w') as log:
                xvfb = subprocess.Popen(['Xvfb', '-displayfd', str(writer), '-screen', '0',
                                         '1280x960x24', '-nolisten', 'tcp'], pass_fds=(writer,),
                                        stdout=log, stderr=subprocess.STDOUT)
            os.close(writer)
            writer = None
            if not select.select([reader], [], [], 10)[0]:
                raise RuntimeError('Xvfb did not allocate a private display')
            number = os.read(reader, 100).decode().strip()
            if not number.isdigit():
                raise RuntimeError('Invalid Xvfb display')
            env = dict(os.environ, DISPLAY=':' + number, XDG_RUNTIME_DIR=str(runtime),
                       QT_QPA_PLATFORM='xcb', QT_QPA_PLATFORMTHEME=args.theme,
                       PYTHONDONTWRITEBYTECODE='1')
            for key in ('WAYLAND_DISPLAY', 'SWAYSOCK', 'XDG_SESSION_ID'):
                env.pop(key, None)
            config = runtime / 'openbox.xml'
            config.write_text('<openbox_config xmlns="http://openbox.org/3.4/rc"/>\n')
            with (output / 'openbox.log').open('w') as log:
                wm = subprocess.Popen(['openbox', '--config', str(config)], env=env,
                                      stdout=log, stderr=subprocess.STDOUT)
            time.sleep(.5)
            result = subprocess.run([sys.executable, __file__, '--child', '--output', str(output)],
                                    env=env, timeout=30, capture_output=True, text=True)
            (output / 'client.log').write_text(result.stdout + result.stderr)
            if result.returncode:
                raise RuntimeError(f'Native X11 check failed; see {output / "client.log"}')
            print(result.stdout.strip())
        finally:
            os.close(reader)
            if writer is not None:
                os.close(writer)
            for process in (wm, xvfb):
                if process is not None and process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()


if __name__ == '__main__':
    main()
