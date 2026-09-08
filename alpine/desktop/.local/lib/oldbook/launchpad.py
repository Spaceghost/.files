"""Launchpad: every application as a large icon over the blurred painting.

Typing filters from the first keystroke, the arrow keys and the pointer move the
selection, Enter or a click launches, and Escape or a click on empty space puts
the overlay away. The grid pages when there are more applications than fit, with
dots underneath and the scroll wheel or the Page keys to move between pages.
"""
import subprocess

from app_index import scan, search
from grid_layout import (ICON_CELL, hit_cell, launchpad_cells, launchpad_grid,
                         move_selection, page_of)
from grid_overlay import Overlay

TERMINAL = ('foot', '-e')
ICON_FRACTION = 0.56
PROMPT = 'Type to find an application'


def launch_arguments(entry, terminal=TERMINAL):
    """The argument list that starts one entry, honouring Terminal=true."""
    arguments = list(entry.get('arguments') or ())
    if not arguments:
        return []
    return list(terminal) + arguments if entry.get('terminal') else arguments


class Launchpad(Overlay):
    NAMESPACE = 'oldbook-launchpad'
    TITLE = 'Launchpad'
    CACHE = 'launchpad'

    def __init__(self, ipc, sway, control):
        super().__init__(ipc, sway, control)
        self.entries = scan()
        self.query = ''
        self.matches = list(self.entries)
        self.selected = 0 if self.matches else None
        self.page = 0
        self.hovered = None
        self._pressed_index = None
        self._icons = {}
        self._grid = None
        self._cells = []

    # Model ---------------------------------------------------------------

    def refilter(self):
        self.matches = search(self.entries, self.query)
        self.selected = 0 if self.matches else None
        self.page = 0
        self.stage.queue_draw()

    def launch(self, index):
        if not (0 <= index < len(self.matches)):
            return
        arguments = launch_arguments(self.matches[index])
        if not arguments:
            return
        try:
            subprocess.Popen(arguments, start_new_session=True,
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
        except OSError:
            return
        self.request_close()

    # Input ---------------------------------------------------------------

    def key_pressed(self, keyval, state):
        from gi.repository import Gdk
        control = bool(state & Gdk.ModifierType.CONTROL_MASK)
        if keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            if self.selected is not None:
                self.launch(self.selected)
            return True
        if keyval == Gdk.KEY_BackSpace:
            if self.query:
                self.query = self.query[:-1]
                self.refilter()
            return True
        directions = {Gdk.KEY_Left: 'left', Gdk.KEY_Right: 'right', Gdk.KEY_Up: 'up',
                      Gdk.KEY_Down: 'down', Gdk.KEY_Home: 'home', Gdk.KEY_End: 'end'}
        if keyval in directions and self._grid:
            self.selected = move_selection(self.selected, len(self.matches),
                                           self._grid['columns'], directions[keyval])
            if self.selected is not None:
                self.page = page_of(self.selected, self._grid['page_size'])
            self.stage.queue_draw()
            return True
        if keyval == Gdk.KEY_Tab:
            self.selected = move_selection(self.selected, len(self.matches),
                                           self._grid['columns'] if self._grid else 1, 'right')
            if self.selected is not None and self._grid:
                self.page = page_of(self.selected, self._grid['page_size'])
            self.stage.queue_draw()
            return True
        if keyval in (Gdk.KEY_Page_Down, Gdk.KEY_Page_Up):
            self.turn_page(1 if keyval == Gdk.KEY_Page_Down else -1)
            return True
        if control:
            return True
        character = Gdk.keyval_to_unicode(keyval)
        if character and chr(character).isprintable():
            self.query += chr(character)
            self.refilter()
            return True
        return False

    def turn_page(self, step):
        if not self._grid or self._grid['pages'] <= 1:
            return
        pages = max(1, -(-len(self.matches) // self._grid['page_size']))
        self.page = max(0, min(pages - 1, self.page + step))
        self.stage.queue_draw()

    def scrolled(self, dx, dy):
        self.turn_page(1 if dy > 0 or dx > 0 else -1)
        return True

    def moved(self, x, y):
        index = hit_cell(self._cells, x, y)
        if index != self.hovered:
            self.hovered = index
            return True
        return False

    def pressed(self, x, y, presses):
        self._pressed_index = hit_cell(self._cells, x, y)
        return True

    def released(self, x, y, presses):
        index = hit_cell(self._cells, x, y)
        if index is None or index != self._pressed_index:
            # A click on the empty space around the grid dismisses the overlay,
            # the way clicking the desktop does.
            if index is None and self._pressed_index is None:
                self.request_close()
            self._pressed_index = None
            return True
        self._pressed_index = None
        self.selected = index
        self.launch(index)
        return True

    # Drawing -------------------------------------------------------------

    def icon_paintable(self, entry, size, scale):
        key = (entry['icon'], size, scale)
        if key in self._icons:
            return self._icons[key]
        from gi.repository import Gdk, Gtk
        name = entry.get('icon') or 'application-x-executable'
        paintable = None
        try:
            if name.startswith('/'):
                paintable = Gdk.Texture.new_from_filename(name)
            else:
                theme = Gtk.IconTheme.get_for_display(self.window.get_display())
                paintable = theme.lookup_icon(name, ['application-x-executable'], size, scale,
                                              Gtk.TextDirection.NONE, Gtk.IconLookupFlags.PRELOAD)
        except Exception:
            paintable = None
        if len(self._icons) > 400:
            self._icons.clear()
        self._icons[key] = paintable
        return paintable

    def render(self, snapshot, width, height):
        grid = launchpad_grid(width, height, len(self.matches), ICON_CELL)
        self._grid = grid
        pages = max(1, -(-len(self.matches) // grid['page_size'])) if grid['page_size'] else 1
        self.page = max(0, min(pages - 1, self.page))
        self._cells = launchpad_cells(grid, len(self.matches), self.page)
        self.render_search(snapshot, width, height)
        if not self.matches:
            self.text(snapshot, 'Nothing here answers to that name',
                      width * 0.2, height * 0.45, width * 0.6, 20.0,
                      self.color('muted'), centered=True)
            return
        scale = max(1, round(self.window.get_scale_factor() or 1))
        for cell in self._cells:
            self.render_cell(snapshot, cell, scale)
        self.render_pages(snapshot, width, height, pages)

    def render_search(self, snapshot, width, height):
        bar_width = min(760.0, width * 0.5)
        x = (width - bar_width) / 2
        y = height * 0.055
        outline = self.rounded(x, y, bar_width, 46.0, 14.0)
        snapshot.push_rounded_clip(outline)
        snapshot.append_color(self.color('background_hard', 0.72),
                              self.rectangle(x, y, bar_width, 46.0))
        snapshot.pop()
        if self.query:
            self.text(snapshot, self.query + '▏', x + 18, y, bar_width - 36, 19.0,
                      self.color('foreground'), bold=True, centered=False, height=46.0)
        else:
            self.text(snapshot, PROMPT, x + 18, y, bar_width - 36, 17.0,
                      self.color('muted'), centered=False, height=46.0)

    def render_cell(self, snapshot, cell, scale):
        entry = self.matches[cell['index']]
        selected = cell['index'] == self.selected
        hovered = cell['index'] == self.hovered
        if selected or hovered:
            pad = 10.0
            outline = self.rounded(cell['x'] + pad, cell['y'] + pad / 2,
                                   cell['width'] - 2 * pad, cell['height'] - pad, 18.0)
            snapshot.push_rounded_clip(outline)
            snapshot.append_color(self.color('accent' if selected else 'surface',
                                             0.20 if selected else 0.30),
                                  self.rectangle(cell['x'] + pad, cell['y'] + pad / 2,
                                                 cell['width'] - 2 * pad, cell['height'] - pad))
            snapshot.pop()
        icon_size = min(cell['width'], cell['height']) * ICON_FRACTION
        icon_x = cell['x'] + (cell['width'] - icon_size) / 2
        icon_y = cell['y'] + cell['height'] * 0.10
        paintable = self.icon_paintable(entry, max(16, int(icon_size)), scale)
        if paintable is not None:
            snapshot.save()
            snapshot.translate(self.Graphene.Point().init(icon_x, icon_y))
            try:
                paintable.snapshot(snapshot, icon_size, icon_size)
            except Exception:
                pass
            snapshot.restore()
        label_y = icon_y + icon_size + 12.0
        self.text(snapshot, entry['name'], cell['x'] + 6, label_y, cell['width'] - 12, 14.5,
                  self.color('foreground' if selected else 'muted'), bold=selected)

    def render_pages(self, snapshot, width, height, pages):
        if pages <= 1:
            return
        radius, gap = 4.0, 18.0
        total = pages * radius * 2 + (pages - 1) * (gap - radius * 2)
        x = (width - total) / 2
        y = height * (1.0 - 0.07)
        for page in range(pages):
            color = self.color('accent' if page == self.page else 'muted',
                               1.0 if page == self.page else 0.45)
            snapshot.push_rounded_clip(self.rounded(x, y, radius * 2, radius * 2, radius))
            snapshot.append_color(color, self.rectangle(x, y, radius * 2, radius * 2))
            snapshot.pop()
            x += gap


def main(action='toggle'):
    from grid_overlay import serve
    serve(Launchpad, action, 'launchpad')
