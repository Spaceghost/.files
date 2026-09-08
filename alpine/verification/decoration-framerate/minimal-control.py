#!/usr/bin/env python3
import math, signal
import gi
gi.require_version('Gtk', '3.0')
gi.require_version('GtkLayerShell', '0.1')
from gi.repository import Gtk, GtkLayerShell, GLib
class Caption:
    def __init__(self):
        self.window = Gtk.Window()
        self.window.set_name('private-minimal-control')
        GtkLayerShell.init_for_window(self.window)
        GtkLayerShell.set_namespace(self.window, 'oldbook-decoration')
        GtkLayerShell.set_layer(self.window, GtkLayerShell.Layer.TOP)
        GtkLayerShell.set_keyboard_mode(self.window, GtkLayerShell.KeyboardMode.NONE)
        GtkLayerShell.set_exclusive_zone(self.window, -1)
        for edge in ('TOP','LEFT'):
            GtkLayerShell.set_anchor(self.window, getattr(GtkLayerShell.Edge, edge), True)
        self.window.set_size_request(440, 34)
        self.window.add(Gtk.Label(label='PRIVATE FRAME CLOCK CONTROL'))
        self.motion_rect = {'x': 240, 'y': 420, 'width': 440, 'height': 34}
        self.motion_target = dict(self.motion_rect)
        self.window.show_all()
        self.started = None
        self.window.add_tick_callback(self.frame)
    def frame(self, window, clock):
        now = clock.get_frame_time()/1000000
        if self.started is None:
            self.started = now
        elapsed = now-self.started
        self.motion_rect['x'] = round(240+230*math.sin(elapsed*2.1))
        self.motion_rect['y'] = round(420+100*math.sin(elapsed*1.7))
        self.motion_target = dict(self.motion_rect)
        GtkLayerShell.set_margin(window, GtkLayerShell.Edge.LEFT, self.motion_rect['x'])
        GtkLayerShell.set_margin(window, GtkLayerShell.Edge.TOP, self.motion_rect['y'])
        return True
caption = Caption()
def stop():
    Gtk.main_quit()
    return False
GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGTERM, stop)
Gtk.main()
caption.window.destroy()
