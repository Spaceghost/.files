"""Struck-water rings over the lower screen, for the moment the strip lands.

The caption flies when it attaches or detaches, and a flight that ends in the
band has an impact. This draws it: a train of rings leaving the strip's own
edge, refracting whatever is actually on the screen rather than drawing light
over it, and gone inside a second.

What it refracts is a still photograph. wlr-screencopy hands over the composited
output through `grim`, the same way the show-desktop animation gets its card, and
that frame is displaced in a fragment shader for the length of the wave. Nothing
underneath is touched: the surface is click-through, sits on the overlay layer,
and destroys itself when the wave has passed.

Only the lower part of the output is covered. A wave that reached the top would
disturb the window being read at the moment the pointer did something at the
bottom, and the smaller surface is proportionally fewer pixels to shade on a
machine whose fans are audible.

The pure geometry and the policy live here as plain functions so they can be
tested without a compositor; the surface below imports GTK only when asked to
draw. How the wave looks is not fixed here: the `ripple` object in
decoration.json can change any of DEFAULTS, and settings() is where a stray
edit to it is caught.
"""
import math
import os
from pathlib import Path
import subprocess
import time

import power_source

# How much of the output the wave is allowed to cross, measured from its edge.
REGION_FRACTION = 1.0 / 3.0
# The effect this asks the power ladder about. Registered as 'mains' already,
# so it does not run on battery without anything here having to know that.
EFFECT = 'shaders'

# How the wave looks: the whole vocabulary of decoration.json's `ripple`
# object, with the value each key takes when it is left out. Lengths are in
# logical pixels, the units the compositor places and sizes the strip in.
DEFAULTS = {
    # Where the rings leave from. 'bar' is the strip's own outline, the way a
    # plank dropped flat sends a straight wave along its length with arcs only
    # at its ends; 'point' drops a stone at the middle of the landed edge.
    'source': 'bar',
    # The whole effect, in seconds. Long enough to read as water, short enough
    # that it is over before it can be waited for.
    'duration': 0.9,
    # How far the front has travelled by the end, as a fraction of the water
    # between the strip and the far edge of the band. Whatever this is, the
    # wave dies out before that edge rather than ending in a hard line.
    'reach': 1.0,
    # From one crest to the next.
    'spacing': 40,
    # How far a crest bends what is under it, at its strongest.
    'strength': 14,
    # How much a crest catches the light and a trough loses it, as a swing in
    # brightness either way. Zero draws only the bend.
    'shade': 0.09,
}
LIMITS = {'duration': (0.2, 3.0), 'reach': (0.2, 1.0), 'spacing': (8, 400),
          'strength': (0, 40), 'shade': (0.0, 0.3)}
SOURCES = ('bar', 'point')

# The shape of the wave itself, shared with the shader below and not settable:
# these are what make it water rather than what make it this water.
#
# The disturbed water is an annulus behind the front. Water past the front has
# not been reached yet and water nearer the strip than this fraction of the
# front's distance has already closed, so at the strike itself the annulus has
# no width and nothing at all is drawn: the wave grows out of the strip's edge
# instead of appearing around it.
TAIL = 0.4
# Crests move slower than the packet they ride in, as the short ripples a small
# impact makes do, so each is born at the front and drifts back through the
# annulus as it widens.
CREST = 0.75
# How the strength dies with age: an exponent on the time left.
DECAY = 1.2
# The last part of the available water over which the wave fades out, so it
# never reaches the edge of the surface it is drawn on at any strength.
MARGIN = 0.25


def settings(values=None):
    """The ripple's settings with defaults filled in and each value checked.

    Anything that is not a key of DEFAULTS, or is outside the range LIMITS
    holds it to, raises ValueError so that a mistake in decoration.json is
    reported rather than drawn.
    """
    if values is None:
        values = {}
    if not isinstance(values, dict):
        raise ValueError('Decoration ripple settings must be an object')
    unknown = set(values) - set(DEFAULTS)
    if unknown:
        raise ValueError('Unknown decoration ripple setting: ' + sorted(unknown)[0])
    result = dict(DEFAULTS)
    result.update(values)
    if result['source'] not in SOURCES:
        raise ValueError('Decoration ripple source must be bar or point')
    for key, (low, high) in LIMITS.items():
        value = result[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError('Decoration ripple ' + key + ' must be a number')
        value = float(value)
        if not math.isfinite(value) or not low <= value <= high:
            raise ValueError('Decoration ripple {} must be between {} and {}'.format(
                key, low, high))
        result[key] = value
    return result


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


def thickness(area, edge='bottom'):
    """The band's depth: the length of water the wave has to cross, and the
    unit every distance the shader works in is measured in, so the wave looks
    the same whichever edge the strip lives on."""
    return max(1, int(area.get('height' if edge == 'bottom' else 'width', 1)))


def origin(rect, area, edge='bottom'):
    """Where a stone would drop, in the region's own 0..1 coordinates, y down.

    The middle of the strip's landed edge -- the edge facing the water, not the
    strip's centre of area -- so the rings leave the surface of the water rather
    than the inside of the bar.
    """
    width = max(1, int(area.get('width', 1)))
    height = max(1, int(area.get('height', 1)))
    if edge == 'bottom':
        centre_x = rect.get('x', 0) + rect.get('width', 0) / 2.0
        centre_y = rect.get('y', 0)
    else:
        centre_x = rect.get('x', 0)
        centre_y = rect.get('y', 0) + rect.get('height', 0) / 2.0
    return (min(1.0, max(0.0, (centre_x - area.get('x', 0)) / width)),
            min(1.0, max(0.0, (centre_y - area.get('y', 0)) / height)))


def source(rect, area, edge='bottom', shape='bar', corner_radius=0):
    """The struck outline the rings leave, as a rounded box: its centre, the
    half extents of the box inside the rounding, and the corner radius, all in
    units of the band's thickness with y down, measured from the region's
    top-left corner.

    'bar' is the strip itself, so a strip the width of the screen sends a
    straight front up the band with arcs only at its ends. 'point' collapses
    the box to the middle of the landed edge: a stone dropped there.
    """
    unit = float(thickness(area, edge))
    if shape == 'point':
        x, y = origin(rect, area, edge)
        return {'centre': (x * area.get('width', 1) / unit, y * area.get('height', 1) / unit),
                'half': (0.0, 0.0), 'radius': 0.0}
    centre = ((rect.get('x', 0) + rect.get('width', 0) / 2.0 - area.get('x', 0)) / unit,
              (rect.get('y', 0) + rect.get('height', 0) / 2.0 - area.get('y', 0)) / unit)
    half = (max(0.0, rect.get('width', 0) / 2.0 / unit),
            max(0.0, rect.get('height', 0) / 2.0 / unit))
    radius = min(max(0.0, float(corner_radius)) / unit, min(half))
    return {'centre': centre, 'half': (half[0] - radius, half[1] - radius), 'radius': radius}


def travel(rect, area, edge='bottom'):
    """How much water lies between the strip's landed edge and the far edge of
    the band, in units of the band's thickness: the furthest a wave could go
    before it met the edge of the surface it is drawn on."""
    unit = float(thickness(area, edge))
    if edge == 'bottom':
        available = (rect.get('y', 0) - area.get('y', 0)) / unit
    else:
        available = (rect.get('x', 0) - area.get('x', 0)) / unit
    return min(1.0, max(0.15, available))


def smoothstep(lower, upper, value):
    if upper <= lower:
        return 1.0 if value >= upper else 0.0
    step = min(1.0, max(0.0, (value - lower) / (upper - lower)))
    return step * step * (3.0 - 2.0 * step)


def envelope(distance, age, travel=1.0, reach=1.0):
    """How disturbed the water is, 0..1, at one distance from the strip's edge
    and one moment of the wave's life (``age`` runs 0..1).

    An annulus behind the travelling front, widening as it goes, fading with
    age and dying out before the far edge of the band. It is exactly zero at
    the strike itself, inside the strip, ahead of the front and once the wave
    is spent, which is what keeps the surface transparent -- and the screen
    untouched -- everywhere the water is still.
    """
    if not 0.0 <= age <= 1.0 or distance <= 0.0:
        return 0.0
    front = age * reach * travel
    tail = front * TAIL
    if distance <= tail or distance >= front:
        return 0.0
    position = (distance - tail) / (front - tail)
    bump = 6.75 * position * position * (1.0 - position)
    fade = (1.0 - age) ** DECAY
    edge = 1.0 - smoothstep(travel * (1.0 - MARGIN), travel, distance)
    return bump * fade * edge


def slope(distance, age, travel=1.0, reach=1.0, spacing=0.15):
    """How the water is tilted, -1..1: the crests and troughs riding in the
    envelope, ``spacing`` apart in the band's units.

    The tilt is what bends the picture under it and what catches the light,
    so this one curve is both the displacement and the shading. Over a
    wavelength it averages to nothing, which is why the wave never brightens
    the screen as a whole: only its crests do, and each has a trough.
    """
    strength = envelope(distance, age, travel, reach)
    if strength == 0.0:
        return 0.0
    front = age * reach * travel
    phase = 2.0 * math.pi * (distance - CREST * front) / spacing
    return strength * math.cos(phase)


def plan(rect, area, edge='bottom', values=None, corner_radius=0):
    """Everything one strike tells the shader, worked out from the strip's
    landed rectangle, the region and the settings: the struck outline, the
    water available, and the wave's own numbers in the band's units."""
    values = settings(values)
    unit = float(thickness(area, edge))
    width = max(1, int(area.get('width', 1)))
    height = max(1, int(area.get('height', 1)))
    box = source(rect, area, edge, values['source'], corner_radius)
    return {
        'centre': box['centre'], 'half': box['half'], 'radius': box['radius'],
        'travel': travel(rect, area, edge), 'reach': values['reach'],
        # Texture coordinates run 0..1 across the region either way. `scale`
        # turns them into the band's units and `texel` is one logical pixel
        # back in texture terms, so a bend of so many pixels stays so many
        # pixels however the region is shaped.
        'scale': (width / unit, height / unit),
        'texel': (1.0 / width, 1.0 / height),
        'spacing': values['spacing'] / unit,
        'strength': values['strength'],
        'shade': values['shade'],
        'duration': values['duration'],
    }


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


def geometry_string(x, y, width, height):
    """grim's -g syntax: the same "X,Y WxH" slurp already speaks."""
    return f'{x},{y} {width}x{height}'


def capture(destination, geometry=None, output_name=None):
    """Photograph the screen through wlr-screencopy, as a binary pixmap.

    A geometry crops at the source rather than after: grim resolves it
    against the output's own scale itself, so the capture, its encode and the
    disk round-trip only ever pay for the pixels the ripple actually needs.
    Measured live, capturing the whole panel just to throw two-thirds of it
    away a moment later in crop() was the largest single cost in the whole
    strike -- about 150ms of a roughly 165ms gap between landing and the
    first visible frame, dwarfing everything else in the chain.
    """
    if geometry is None and output_name is None:
        raise ValueError('capture needs a geometry or an output name')
    command = ['grim']
    command += ['-g', geometry] if geometry is not None else ['-o', str(output_name)]
    command += ['-t', 'ppm', str(destination)]
    subprocess.run(command, check=True, stdin=subprocess.DEVNULL,
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


VERTEX_SHADER = """#version 300 es
in vec2 position;
out vec2 texture_position;
void main() {
    texture_position = position * 0.5 + 0.5;
    gl_Position = vec4(position, 0.0, 1.0);
}
"""

# The same curves as envelope() and slope() above, run per pixel. The
# photograph is sampled at a displaced coordinate rather than drawn over, so
# what bends is whatever was actually on the screen.
FRAGMENT_SHADER = """#version 300 es
precision highp float;
in vec2 texture_position;
out vec4 fragment;
uniform sampler2D screen;
// Texture coordinates to the band's units, and one logical pixel back.
uniform vec2 scale;
uniform vec2 texel;
// The struck outline: a rounded box in the band's units, y down.
uniform vec2 centre;
uniform vec2 half_size;
uniform float radius;
// The water available past the outline, and the wave's own numbers.
uniform float travel;
uniform float reach;
uniform float spacing;
uniform float strength;
uniform float shade;
uniform float age;

const float TAIL = %(tail)s;
const float CREST = %(crest)s;
const float DECAY = %(decay)s;
const float MARGIN = %(margin)s;

void main() {
    // The photograph's first row is the bottom of the screen, so the texture
    // runs upward; the strip was placed with y running down, and the geometry
    // is worked out the way it was placed.
    vec2 point = vec2(texture_position.x, 1.0 - texture_position.y) * scale;
    vec2 relative = point - centre;
    // Distance to the box inside the rounding, and the way out of it: the
    // rings leave the outline along its normal, straight off a side and
    // fanning out around a corner.
    vec2 away = relative - clamp(relative, -half_size, half_size);
    float apart = length(away);
    float water = apart - radius;
    vec2 normal = apart > 0.00001 ? away / apart : vec2(0.0);

    float front = age * reach * travel;
    float tail = front * TAIL;
    float position = clamp((water - tail) / max(front - tail, 0.00001), 0.0, 1.0);
    float bump = 6.75 * position * position * (1.0 - position);
    float fade = pow(max(1.0 - age, 0.0), DECAY);
    float edge = 1.0 - smoothstep(travel * (1.0 - MARGIN), travel, water);
    float envelope = (water > tail && water < front) ? bump * fade * edge : 0.0;
    float phase = 6.28318530718 * (water - CREST * front) / spacing;
    float slope = envelope * cos(phase);

    // Bend the picture along the normal by the tilt, in logical pixels; the
    // normal's y is flipped back into the texture's upward direction.
    vec2 bend = vec2(normal.x, -normal.y) * slope * strength * texel;
    vec4 colour = texture(screen, clamp(texture_position + bend, 0.0, 1.0));
    // A crest catches the light and a trough loses it, which is what makes the
    // bend read as water rather than as a lens. Together they add nothing.
    colour.rgb = clamp(colour.rgb + vec3(shade * slope), 0.0, 1.0);
    // The surface exists only where the water is disturbed, blended by how
    // disturbed it is; everywhere else the live desktop underneath is what is
    // seen, not a moment-old photograph of it. GTK composites this canvas as
    // premultiplied alpha, so the colour is scaled by its own coverage --
    // written straight, every half-covered pixel would come out brighter
    // than the desktop it was meant to match.
    float alpha = clamp(envelope * 2.0, 0.0, 1.0);
    fragment = vec4(colour.rgb * alpha, alpha);
}
""" % {'tail': repr(float(TAIL)), 'crest': repr(float(CREST)),
       'decay': repr(float(DECAY)), 'margin': repr(float(MARGIN))}


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
    strike rather than a blank overlay waiting for one. ``plan`` is what
    plan() returned for this strike: the outline, the water and the settings.
    """

    def __init__(self, monitor, area, plan, pixels, size, on_done=None):
        import ctypes
        import gi
        gi.require_version('Gtk', '4.0')
        gi.require_version('Gdk', '4.0')
        gi.require_version('Gtk4LayerShell', '1.0')
        from gi.repository import GLib, Gtk, Gtk4LayerShell
        self._ctypes, self._Gtk, self._shell = ctypes, Gtk, Gtk4LayerShell
        self._GLib = GLib
        self.area, self.plan, self.pixels, self.size = area, plan, pixels, size
        self.duration = max(0.05, float(plan['duration']))
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
        if self.started is not None and time.monotonic() - self.started >= self.duration:
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
        ctypes, library, plan = self._ctypes, self.library, self.plan
        age = min(1.0, (time.monotonic() - self.started) / self.duration)
        library.glClearColor(0.0, 0.0, 0.0, 0.0)
        library.glClear(_GL['COLOR_BUFFER_BIT'])
        library.glUseProgram(ctypes.c_uint(self.program))
        library.glBindVertexArray(ctypes.c_uint(self.vertices))
        library.glActiveTexture(_GL['TEXTURE0'])
        library.glBindTexture(_GL['TEXTURE_2D'], ctypes.c_uint(self.texture))
        for name, value in (('screen', 0),):
            place = library.glGetUniformLocation(ctypes.c_uint(self.program), name.encode())
            if place >= 0:
                library.glUniform1i(place, value)
        for name, value in (('age', age), ('travel', plan['travel']), ('reach', plan['reach']),
                            ('spacing', plan['spacing']), ('strength', plan['strength']),
                            ('shade', plan['shade']), ('radius', plan['radius'])):
            place = library.glGetUniformLocation(ctypes.c_uint(self.program), name.encode())
            if place >= 0:
                library.glUniform1f(place, float(value))
        for name, pair in (('scale', plan['scale']), ('texel', plan['texel']),
                           ('centre', plan['centre']), ('half_size', plan['half'])):
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
