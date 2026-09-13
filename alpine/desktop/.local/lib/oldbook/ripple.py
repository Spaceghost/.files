"""Struck-water rings over the lower screen, for the moment the strip lands.

The caption flies when it attaches or detaches, and a flight that ends in the
band has an impact. This draws it: one ring leaving the point the strip came to
rest at, refracting whatever is actually on the screen rather than drawing
light over it, and gone inside a second.

What it refracts is a still photograph. wlr-screencopy hands over the composited
output through `grim`, the same way the show-desktop animation gets its card, and
that frame is displaced in a fragment shader for the length of the ring. Nothing
underneath is touched: the surface is click-through, sits on the overlay layer,
and destroys itself when the wave has passed.

Only the lower part of the output is covered. A wave that reached the top would
disturb the window being read at the moment the pointer did something at the
bottom, and the smaller surface is proportionally fewer pixels to shade on a
machine whose fans are audible.

The pure geometry and the policy live here as plain functions so they can be
tested without a compositor; the surface below imports GTK only when asked to
draw.
"""
import math
import os
from pathlib import Path
import subprocess
import time

import power_source

# How much of the output the wave is allowed to cross, measured from its edge.
REGION_FRACTION = 1.0 / 3.0
# The whole effect, in seconds. Long enough to read as water, short enough that
# it is over before it can be waited for.
DURATION = 0.72
# Rings per unit of region, and how fast the front travels across it. Together
# these decide how many crests are in the air at once.
FREQUENCY = 26.0
SPEED = 1.25
# The crest's displacement at its strongest, as a fraction of the region.
AMPLITUDE = 0.016
# The inverse width of the ring around the travelling front: the disturbance
# falls away as a bell of about 1/SHARPNESS across. Larger is a thinner, harder
# ring; smaller is a swell rather than a ripple.
SHARPNESS = 5.5
# The effect this asks the power ladder about. Registered as 'mains' already,
# so it does not run on battery without anything here having to know that.
EFFECT = 'shaders'


def region(output_rect, edge='bottom', fraction=REGION_FRACTION):
    """The part of the output the wave is allowed to cross.

    Anchored to the strip's own edge, because that is where the impact is and a
    wave that started at the bottom and covered the top would be crossing the
    screen rather than spreading from something.
    """
    if edge not in ('bottom', 'right'):
        raise ValueError('Decoration edge must be bottom or right')
    fraction = max(0.05, min(1.0, float(fraction)))
    x = int(output_rect.get('x', 0))
    y = int(output_rect.get('y', 0))
    width = max(1, int(output_rect.get('width', 0)))
    height = max(1, int(output_rect.get('height', 0)))
    if edge == 'bottom':
        span = max(1, int(round(height * fraction)))
        return {'x': x, 'y': y + height - span, 'width': width, 'height': span}
    span = max(1, int(round(width * fraction)))
    return {'x': x + width - span, 'y': y, 'width': span, 'height': height}


def origin(rect, area):
    """Where the wave starts, in the region's own 0..1 coordinates.

    The middle of the strip's landed edge: the point it arrived on, not its
    centre of area, so the rings leave the surface of the water rather than the
    inside of the bar.
    """
    width = max(1, int(area.get('width', 1)))
    height = max(1, int(area.get('height', 1)))
    centre_x = rect.get('x', 0) + rect.get('width', 0) / 2.0
    centre_y = rect.get('y', 0)
    return (min(1.0, max(0.0, (centre_x - area.get('x', 0)) / width)),
            min(1.0, max(0.0, (centre_y - area.get('y', 0)) / height)))


def allowed(animations=True, current=None):
    """Whether to draw at all: never on battery, never with animation off.

    The power ladder already lists this effect at mains, so asking it is the
    whole of the battery question; nothing here decides a threshold of its own.
    ``current`` names a posture instead of reading the hardware, which is how a
    test says "on battery" without one.
    """
    if not animations:
        return False
    return bool(power_source.allows(EFFECT, current=current))


def capture(output_name, destination):
    """Photograph one output through wlr-screencopy, as a binary pixmap."""
    subprocess.run(['grim', '-o', str(output_name), '-t', 'ppm', str(destination)],
                   check=True, stdin=subprocess.DEVNULL,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                   timeout=4)
    return Path(destination)


def parse_ppm(data):
    """Return ``(width, height, offset)`` for a binary P6 portable pixmap.

    grim writes a bare three-field header, but the format allows comments and
    any whitespace between fields, so the header is read rather than assumed.
    """
    fields = []
    index = 0
    while len(fields) < 4:
        while index < len(data) and data[index:index + 1].isspace():
            index += 1
        if data[index:index + 1] == b'#':
            while index < len(data) and data[index] != 0x0a:
                index += 1
            continue
        start = index
        while index < len(data) and not data[index:index + 1].isspace():
            index += 1
        if start == index:
            raise ValueError('truncated portable pixmap header')
        fields.append(data[start:index])
    if fields[0] != b'P6' or fields[3] != b'255':
        raise ValueError('not an eight-bit binary portable pixmap')
    width, height = int(fields[1]), int(fields[2])
    if width <= 0 or height <= 0:
        raise ValueError('portable pixmap has no pixels')
    return width, height, index + 1


def ring_envelope(distance, elapsed, duration=DURATION, speed=SPEED, sharpness=SHARPNESS):
    """How close this point and moment are to the travelling front, and how
    much the whole wave has aged: the bell that keeps the disturbance near the
    front and lets it die out as the strike is left behind.

    The disturbance only exists near the front: ahead of it the water has not
    been reached, behind it the surface has already closed. A bell rather than
    a spike, or the ring is a wire instead of a wave.
    """
    if duration <= 0:
        raise ValueError('duration must be positive')
    if not 0 <= elapsed <= duration:
        return 0.0
    age = elapsed / duration
    front = age * speed
    ring = (distance - front) * sharpness
    envelope = math.exp(-ring * ring)
    fade = (1.0 - age) ** 1.5
    return envelope * fade


def radial_reach(distance):
    """How much a ripple this far from the strike still carries, physically:
    energy spreads outward and weakens, so a crest near the point of impact
    moves further than one already most of the way across the region."""
    return 1.0 / (1.0 + 1.5 * distance * distance)


def visibility(distance, elapsed, duration=DURATION, speed=SPEED, sharpness=SHARPNESS):
    """How much of the frozen photograph should be shown at this point and
    moment, as an alpha in 0..1.

    This is what makes the surface transparent rather than a slab: it is
    non-zero only in the travelling band around the front, close to the
    strike. Everywhere else -- which is almost everywhere, almost all the
    time -- the real, live desktop underneath is what a viewer actually sees,
    because nothing is drawn over it at all.
    """
    return ring_envelope(distance, elapsed, duration, speed, sharpness) * radial_reach(distance)


def crest(distance, elapsed, duration=DURATION, frequency=FREQUENCY,
          speed=SPEED, amplitude=AMPLITUDE, sharpness=SHARPNESS):
    """How far the water is pushed at one distance and one moment.

    The same curve the shader runs, kept here in Python so the shape of the
    wave can be tested without a GPU: a travelling front at ``speed`` with a
    ring of crests behind it, fading with age and with distance from the strike.
    """
    if duration <= 0:
        raise ValueError('duration must be positive')
    if not 0 <= elapsed <= duration:
        return 0.0
    age = elapsed / duration
    front = age * speed
    return amplitude * visibility(distance, elapsed, duration, speed, sharpness) * math.sin(
        distance * frequency - age * speed * frequency)


VERTEX_SHADER = """#version 300 es
in vec2 position;
out vec2 texture_position;
void main() {
    texture_position = position * 0.5 + 0.5;
    gl_Position = vec4(position, 0.0, 1.0);
}
"""

# The same curve as crest() above, run per pixel. The photograph is sampled at
# a displaced coordinate rather than drawn over, so what bends is whatever was
# actually on the screen.
FRAGMENT_SHADER = """#version 300 es
precision highp float;
in vec2 texture_position;
out vec4 fragment;
uniform sampler2D screen;
uniform vec2 origin;
uniform vec2 scale;
uniform float age;
uniform float frequency;
uniform float speed;
uniform float amplitude;
uniform float sharpness;

void main() {
    vec2 offset = (texture_position - origin) * scale;
    float distance = length(offset);
    float front = age * speed;
    float ring = (distance - front) * sharpness;
    float envelope = exp(-ring * ring);
    float fade = pow(1.0 - age, 1.5);
    float reach = 1.0 / (1.0 + 1.5 * distance * distance);
    // Non-zero only in the band around the travelling front: this is the
    // surface's alpha as well as the wave's strength, so almost the entire
    // output stays fully transparent and the real, live desktop underneath is
    // what is actually seen there -- not a second-old photograph pretending
    // to be it. Only the ring itself, for the moment it crosses a pixel, is
    // drawn at all.
    float coverage = envelope * fade * reach;
    float height = amplitude * coverage
                 * sin(distance * frequency - age * speed * frequency);
    vec2 direction = distance > 0.0001 ? offset / distance : vec2(0.0);
    vec2 sampled = texture_position + direction * height / max(scale, vec2(0.0001));
    vec4 colour = texture(screen, clamp(sampled, 0.0, 1.0));
    // A crest catches the light and a trough loses it, which is what makes the
    // bend read as water rather than as a lens.
    colour.rgb += vec3(height * 6.0);
    fragment = vec4(colour.rgb, clamp(coverage * 3.0, 0.0, 1.0));
}
"""


# GTK4 hands out an OpenGL ES context and no Python binding for it. PyOpenGL is
# not packaged for this distribution, and GTK's own shader node was dropped by
# the renderer this version ships, so the calls are made through ctypes against
# the symbols GTK has already loaded. Only the two dozen the effect needs are
# declared.
_GL = {
    'FRAGMENT_SHADER': 0x8B30, 'VERTEX_SHADER': 0x8B31,
    'COMPILE_STATUS': 0x8B81, 'LINK_STATUS': 0x8B82, 'INFO_LOG_LENGTH': 0x8B84,
    'ARRAY_BUFFER': 0x8892, 'STATIC_DRAW': 0x88E4,
    'TEXTURE_2D': 0x0DE1, 'TEXTURE0': 0x84C0, 'RGB': 0x1907,
    'UNSIGNED_BYTE': 0x1401, 'FLOAT': 0x1406, 'TRIANGLE_STRIP': 0x0005,
    'TEXTURE_MIN_FILTER': 0x2801, 'TEXTURE_MAG_FILTER': 0x2800, 'LINEAR': 0x2601,
    'TEXTURE_WRAP_S': 0x2802, 'TEXTURE_WRAP_T': 0x2803, 'CLAMP_TO_EDGE': 0x812F,
    'COLOR_BUFFER_BIT': 0x4000, 'UNPACK_ALIGNMENT': 0x0CF5,
}


def _library():
    """The GL symbols already in this process, whichever library holds them."""
    import ctypes
    library = ctypes.CDLL(None)
    library.glCreateShader.restype = ctypes.c_uint
    library.glCreateShader.argtypes = [ctypes.c_uint]
    library.glCreateProgram.restype = ctypes.c_uint
    library.glCreateProgram.argtypes = []
    library.glGetAttribLocation.restype = ctypes.c_int
    library.glGetAttribLocation.argtypes = [ctypes.c_uint, ctypes.c_char_p]
    library.glGetUniformLocation.restype = ctypes.c_int
    library.glGetUniformLocation.argtypes = [ctypes.c_uint, ctypes.c_char_p]
    library.glUniform1f.argtypes = [ctypes.c_int, ctypes.c_float]
    library.glUniform2f.argtypes = [ctypes.c_int, ctypes.c_float, ctypes.c_float]
    library.glUniform1i.argtypes = [ctypes.c_int, ctypes.c_int]
    library.glClearColor.argtypes = [ctypes.c_float] * 4
    return library


def _compile(library, kind, source):
    import ctypes
    shader = library.glCreateShader(kind)
    text = ctypes.c_char_p(source.encode())
    library.glShaderSource(ctypes.c_uint(shader), 1, ctypes.byref(text), None)
    library.glCompileShader(ctypes.c_uint(shader))
    status = ctypes.c_int(0)
    library.glGetShaderiv(ctypes.c_uint(shader), _GL['COMPILE_STATUS'],
                          ctypes.byref(status))
    if not status.value:
        log = ctypes.create_string_buffer(1024)
        library.glGetShaderInfoLog(ctypes.c_uint(shader), 1024, None, log)
        raise RuntimeError('ripple shader: ' + log.value.decode(errors='replace').strip())
    return shader


def program(library):
    """Link the two shaders into the one program the wave is drawn with."""
    import ctypes
    vertex = _compile(library, _GL['VERTEX_SHADER'], VERTEX_SHADER)
    fragment = _compile(library, _GL['FRAGMENT_SHADER'], FRAGMENT_SHADER)
    linked = library.glCreateProgram()
    library.glAttachShader(ctypes.c_uint(linked), ctypes.c_uint(vertex))
    library.glAttachShader(ctypes.c_uint(linked), ctypes.c_uint(fragment))
    library.glLinkProgram(ctypes.c_uint(linked))
    status = ctypes.c_int(0)
    library.glGetProgramiv(ctypes.c_uint(linked), _GL['LINK_STATUS'],
                           ctypes.byref(status))
    library.glDeleteShader(ctypes.c_uint(vertex))
    library.glDeleteShader(ctypes.c_uint(fragment))
    if not status.value:
        log = ctypes.create_string_buffer(1024)
        library.glGetProgramInfoLog(ctypes.c_uint(linked), 1024, None, log)
        raise RuntimeError('ripple program: ' + log.value.decode(errors='replace').strip())
    return linked


def crop(data, offset, width, height, area, scale=1.0):
    """The region's own pixels, bottom row first, ready to upload.

    A texture's first row is its bottom one and a portable pixmap's is its top,
    so the crop is taken upside down rather than flipping the sampler and
    making every coordinate in the shader read backwards.

    ``area`` is in the compositor's own logical units -- the same ones Sway
    reports outputs in and layer-shell margins are placed with -- but grim
    hands over the photograph at the output's real, physical resolution. On
    any output where those differ, ``scale`` is what converts one to the
    other; left at 1 it is a no-op for an unscaled output. Skipping this once
    cropped a thin, wrongly-placed sliver of the screen on a HiDPI panel
    instead of the intended band.
    """
    import numpy
    frame = numpy.frombuffer(data, dtype=numpy.uint8, count=width * height * 3,
                             offset=offset).reshape(height, width, 3)
    left = max(0, min(width - 1, round(area['x'] * scale)))
    top = max(0, min(height - 1, round(area['y'] * scale)))
    right = max(left + 1, min(width, left + round(area['width'] * scale)))
    bottom = max(top + 1, min(height, top + round(area['height'] * scale)))
    return numpy.ascontiguousarray(frame[top:bottom, left:right][::-1]), \
        right - left, bottom - top


class Ripple:
    """One wave, on its own surface, for as long as it takes to cross.

    Built already holding its photograph, so the first frame it draws is the
    strike rather than a blank overlay waiting for one.
    """

    def __init__(self, monitor, area, point, pixels, size, on_done=None):
        import ctypes
        import gi
        gi.require_version('Gtk', '4.0')
        gi.require_version('Gdk', '4.0')
        gi.require_version('Gtk4LayerShell', '1.0')
        from gi.repository import GLib, Gtk, Gtk4LayerShell
        self._ctypes, self._Gtk, self._shell = ctypes, Gtk, Gtk4LayerShell
        self._GLib = GLib
        self.area, self.point, self.pixels, self.size = area, point, pixels, size
        self.on_done = on_done
        self.started = None
        self.library = None
        self.program = self.texture = self.buffer = self.vertices = None
        self.window = Gtk.Window()
        self.window.set_decorated(False)
        self.window.set_name('oldbook-ripple')
        self.window.set_can_focus(False)
        # Without this, GTK's own window background -- opaque on this theme --
        # sits behind the GL canvas and defeats every alpha the shader draws.
        self.provider = Gtk.CssProvider()
        self.provider.load_from_string('#oldbook-ripple { background: transparent; }')
        Gtk4LayerShell.init_for_window(self.window)
        Gtk4LayerShell.set_namespace(self.window, 'oldbook-ripple')
        Gtk4LayerShell.set_monitor(self.window, monitor)
        Gtk4LayerShell.set_layer(self.window, Gtk4LayerShell.Layer.OVERLAY)
        Gtk4LayerShell.set_keyboard_mode(self.window, Gtk4LayerShell.KeyboardMode.NONE)
        # Held by one corner and given its extent outright, exactly as the
        # caption is: an anchored size the compositor has to guess at is a
        # two-hundred pixel square.
        for name in ('TOP', 'LEFT'):
            Gtk4LayerShell.set_anchor(self.window, getattr(Gtk4LayerShell.Edge, name), True)
        Gtk4LayerShell.set_margin(self.window, Gtk4LayerShell.Edge.LEFT, area['x'])
        Gtk4LayerShell.set_margin(self.window, Gtk4LayerShell.Edge.TOP, area['y'])
        Gtk4LayerShell.set_exclusive_zone(self.window, -1)
        # Layer-shell surfaces are placed and sized in the compositor's own
        # logical units, same as the margins just above -- unlike ``size``,
        # which is the cropped photograph's physical pixel dimensions and is
        # only what the GL texture itself is uploaded at.
        self.window.set_size_request(round(area['width']), round(area['height']))
        self.window.set_default_size(round(area['width']), round(area['height']))
        self.canvas = Gtk.GLArea()
        self.canvas.set_has_depth_buffer(False)
        self.canvas.set_has_stencil_buffer(False)
        self.canvas.connect('realize', self.prepare)
        self.canvas.connect('render', self.draw)
        self.canvas.connect('unrealize', self.dispose)
        self.window.set_child(self.canvas)
        self.window.connect('realize', self.untouchable)
        Gtk.StyleContext.add_provider_for_display(
            self.window.get_display(), self.provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    def untouchable(self, _widget):
        """The wave is a picture, not a control; clicks belong underneath it."""
        surface = self.window.get_surface()
        if surface is None:
            return
        try:
            import cairo
            surface.set_input_region(cairo.Region())
        except (ImportError, AttributeError, TypeError, ValueError):
            pass

    def start(self):
        self.window.present()
        self.started = time.monotonic()
        self.canvas.add_tick_callback(self.frame)

    def frame(self, widget, _clock):
        if self.started is not None and time.monotonic() - self.started >= DURATION:
            self.finish()
            return False
        widget.queue_draw()
        return True

    def prepare(self, canvas):
        ctypes = self._ctypes
        canvas.make_current()
        if canvas.get_error() is not None:
            self.finish()
            return
        try:
            self.library = _library()
            self.program = program(self.library)
        except (OSError, AttributeError, RuntimeError) as error:
            print('ripple: ' + str(error), file=__import__('sys').stderr)
            self.finish()
            return
        library = self.library
        # One quad, and the photograph on it.
        import array
        corners = array.array('f', (-1, -1, 1, -1, -1, 1, 1, 1))
        handle = ctypes.c_uint(0)
        library.glGenVertexArrays(1, ctypes.byref(handle))
        self.vertices = handle.value
        library.glBindVertexArray(ctypes.c_uint(self.vertices))
        buffer_id = ctypes.c_uint(0)
        library.glGenBuffers(1, ctypes.byref(buffer_id))
        self.buffer = buffer_id.value
        library.glBindBuffer(_GL['ARRAY_BUFFER'], ctypes.c_uint(self.buffer))
        raw = corners.tobytes()
        library.glBufferData(_GL['ARRAY_BUFFER'], len(raw), raw, _GL['STATIC_DRAW'])
        location = library.glGetAttribLocation(ctypes.c_uint(self.program), b'position')
        if location >= 0:
            library.glEnableVertexAttribArray(ctypes.c_uint(location))
            library.glVertexAttribPointer(ctypes.c_uint(location), 2, _GL['FLOAT'],
                                          0, 0, None)
        texture_id = ctypes.c_uint(0)
        library.glGenTextures(1, ctypes.byref(texture_id))
        self.texture = texture_id.value
        library.glBindTexture(_GL['TEXTURE_2D'], ctypes.c_uint(self.texture))
        library.glPixelStorei(_GL['UNPACK_ALIGNMENT'], 1)
        pixels = self.pixels.ctypes.data_as(ctypes.c_void_p)
        library.glTexImage2D(_GL['TEXTURE_2D'], 0, _GL['RGB'], self.size[0],
                             self.size[1], 0, _GL['RGB'], _GL['UNSIGNED_BYTE'], pixels)
        for name, value in (('TEXTURE_MIN_FILTER', 'LINEAR'), ('TEXTURE_MAG_FILTER', 'LINEAR'),
                            ('TEXTURE_WRAP_S', 'CLAMP_TO_EDGE'), ('TEXTURE_WRAP_T', 'CLAMP_TO_EDGE')):
            library.glTexParameteri(_GL['TEXTURE_2D'], _GL[name], _GL[value])

    def draw(self, canvas, _context):
        if self.program is None or self.started is None:
            return False
        ctypes, library = self._ctypes, self.library
        age = min(1.0, (time.monotonic() - self.started) / DURATION)
        library.glClearColor(0.0, 0.0, 0.0, 0.0)
        library.glClear(_GL['COLOR_BUFFER_BIT'])
        library.glUseProgram(ctypes.c_uint(self.program))
        library.glBindVertexArray(ctypes.c_uint(self.vertices))
        library.glActiveTexture(_GL['TEXTURE0'])
        library.glBindTexture(_GL['TEXTURE_2D'], ctypes.c_uint(self.texture))
        # Distance has to mean the same in both directions or the rings are
        # ellipses: the shorter side is scaled to the longer one.
        width, height = float(self.size[0]), float(self.size[1])
        longest = max(width, height)
        for name, value in (('screen', 0),):
            place = library.glGetUniformLocation(ctypes.c_uint(self.program), name.encode())
            if place >= 0:
                library.glUniform1i(place, value)
        for name, value in (('age', age), ('frequency', FREQUENCY), ('speed', SPEED),
                            ('amplitude', AMPLITUDE), ('sharpness', SHARPNESS)):
            place = library.glGetUniformLocation(ctypes.c_uint(self.program), name.encode())
            if place >= 0:
                library.glUniform1f(place, float(value))
        for name, pair in (('origin', self.point),
                           ('scale', (width / longest, height / longest))):
            place = library.glGetUniformLocation(ctypes.c_uint(self.program), name.encode())
            if place >= 0:
                library.glUniform2f(place, float(pair[0]), float(pair[1]))
        library.glDrawArrays(_GL['TRIANGLE_STRIP'], 0, 4)
        return True

    def dispose(self, _canvas=None):
        ctypes, library = self._ctypes, self.library
        if library is None:
            return
        for name, value in (('glDeleteTextures', self.texture), ('glDeleteBuffers', self.buffer),
                            ('glDeleteVertexArrays', self.vertices)):
            if value:
                handle = ctypes.c_uint(value)
                getattr(library, name)(1, ctypes.byref(handle))
        if self.program:
            library.glDeleteProgram(ctypes.c_uint(self.program))
        self.program = self.texture = self.buffer = self.vertices = None

    def finish(self):
        if self.window is None:
            return
        window, self.window = self.window, None
        display = window.get_display()
        if not display.is_closed():
            self._Gtk.StyleContext.remove_provider_for_display(display, self.provider)
        window.destroy()
        self.pixels = None
        if self.on_done is not None:
            self.on_done()


class Warmth:
    """Holds the GL context open so the first landing does not pay for it."""

    def __init__(self, window):
        self.window = window

    def close(self):
        window, self.window = self.window, None
        if window is not None:
            window.destroy()


def warm():
    """Create the GL context and compile the wave before anything needs them.

    The first GLArea in a process pays for the whole graphics context -- four
    tenths of a second on this hardware -- and the first strike is exactly the
    wrong moment to find that out, because it lands on the frame after the
    strip has come to rest. Realizing one offscreen at start-up pays it while
    nothing is watching, and holding the window open keeps the context alive
    for the surfaces that follow, which then cost nothing measurable.

    Nothing is mapped, no layer-shell role is taken and no photograph is read;
    the area is one pixel and is never presented.
    """
    import gi
    gi.require_version('Gtk', '4.0')
    from gi.repository import Gtk
    window = Gtk.Window()
    window.set_default_size(1, 1)
    canvas = Gtk.GLArea()
    canvas.set_has_depth_buffer(False)
    canvas.set_has_stencil_buffer(False)
    compiled = {}

    def prepare(area):
        area.make_current()
        if area.get_error() is not None:
            return
        try:
            library = _library()
            compiled['program'] = program(library)
            library.glDeleteProgram(__import__('ctypes').c_uint(compiled['program']))
        except (OSError, AttributeError, RuntimeError):
            return

    canvas.connect('realize', prepare)
    window.set_child(canvas)
    try:
        window.realize()
    except Exception:
        window.destroy()
        raise
    if window.get_mapped():
        window.destroy()
        raise RuntimeError('ripple warmup must remain unmapped')
    return Warmth(window)
