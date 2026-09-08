"""Mission Control: every workspace as a card of real window stills.

The stills come from the window carousel's capture provider, so a workspace on
another output or behind the current one is photographed without being visited
or focused. Cards are captured once per opening. Click or Enter switches, the
arrow keys move, dragging a still onto another card moves that window there, and
the last card creates the next workspace.
"""
from concurrent.futures import ThreadPoolExecutor
import json

from grid_layout import letterbox, move_selection, tile_stills, workspace_grid
from grid_overlay import Overlay
from workspace_model import displayed_views, workspace_name, workspace_nodes

MAX_STILLS = 6
CARD_RADIUS = 16.0


def workspace_cards(tree, limit=MAX_STILLS):
    """One record per real workspace, with the views worth photographing."""
    cards = []
    for node in workspace_nodes(tree):
        if node.get('num', -1) < 0:
            continue
        views = [view for view in displayed_views(node)][:limit]
        cards.append({
            'num': node.get('num'),
            'name': node.get('name') or workspace_name(node.get('num')),
            'focused': bool(node.get('focused')),
            'views': [{'id': view['id'],
                       'name': view.get('name') or '',
                       'app_id': view.get('app_id') or
                                 view.get('window_properties', {}).get('class', ''),
                       'foreign_toplevel_identifier': view.get('foreign_toplevel_identifier')}
                      for view in views],
            'count': len(displayed_views(node)),
        })
    return sorted(cards, key=lambda card: card['num'])


def next_workspace_number(cards):
    used = {card['num'] for card in cards}
    number = 1
    while number in used:
        number += 1
    return number


class MissionControl(Overlay):
    NAMESPACE = 'oldbook-mission-control'
    TITLE = 'Mission Control'
    CACHE = 'mission-control'

    def __init__(self, ipc, sway, control):
        super().__init__(ipc, sway, control)
        self.cards = workspace_cards(ipc['request'](sway, 4))
        self.new_number = next_workspace_number(self.cards)
        self.selected = next((index for index, card in enumerate(self.cards)
                              if card['focused']), 0)
        self.hovered = None
        self.textures = {}
        self.unavailable = set()
        self._rects = []
        self._still_rects = []
        self._columns = 1
        self._drag = None
        self.executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix='mission-still')
        self._generation = 0
        drag = self.Gtk.GestureDrag.new()
        drag.connect('drag-begin', self._drag_begin)
        drag.connect('drag-update', self._drag_update)
        drag.connect('drag-end', self._drag_end)
        self.stage.add_controller(drag)
        self.request_stills()

    # Stills --------------------------------------------------------------

    def request_stills(self):
        from carousel import capture_preview
        generation = self._generation
        for card in self.cards:
            for view in card['views']:
                if not view['foreign_toplevel_identifier'] or view['id'] in self.textures:
                    continue
                future = self.executor.submit(capture_preview, dict(view))
                future.add_done_callback(
                    lambda done, identity=view['id']: self.GLib.idle_add(
                        self._deliver, generation, identity, done))

    def _deliver(self, generation, identity, done):
        if generation != self._generation or self.closing:
            return False
        try:
            result = done.result()
        except Exception:
            result = None
        if result is None:
            self.unavailable.add(identity)
        else:
            width, height, pixels = result
            if width > 0 and height > 0 and len(pixels) == width * height * 3:
                self.textures[identity] = self.Gdk.MemoryTexture.new(
                    width, height, self.Gdk.MemoryFormat.R8G8B8,
                    self.GLib.Bytes.new(bytes(pixels)), width * 3)
            else:
                self.unavailable.add(identity)
        self.stage.queue_draw()
        return False

    def _finish(self):
        self._generation += 1
        self.executor.shutdown(wait=False, cancel_futures=True)
        self.textures.clear()
        super()._finish()

    # Actions -------------------------------------------------------------

    def activate(self, index):
        if index == len(self.cards):
            name = workspace_name(self.new_number)
            self.command('workspace number ' + json.dumps(name))
            self.request_close()
            return
        if 0 <= index < len(self.cards):
            card = self.cards[index]
            self.command('workspace number ' + json.dumps(card['name']))
            self.request_close()

    def command(self, text):
        try:
            self.ipc['command'](self.sway, text)
        except Exception:
            pass

    def move_window(self, view_id, index):
        if index == len(self.cards):
            name = workspace_name(self.new_number)
        elif 0 <= index < len(self.cards):
            name = self.cards[index]['name']
        else:
            return
        self.command(f'[con_id={int(view_id)}] move container to workspace '
                     + json.dumps(name))
        self.refresh()

    def refresh(self):
        try:
            self.cards = workspace_cards(self.ipc['request'](self.sway, 4))
        except Exception:
            return
        self.new_number = next_workspace_number(self.cards)
        self.selected = max(0, min(len(self.cards), self.selected))
        self.request_stills()
        self.stage.queue_draw()

    # Input ---------------------------------------------------------------

    def key_pressed(self, keyval, state):
        from gi.repository import Gdk
        if keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            self.activate(self.selected)
            return True
        directions = {Gdk.KEY_Left: 'left', Gdk.KEY_Right: 'right', Gdk.KEY_Up: 'up',
                      Gdk.KEY_Down: 'down', Gdk.KEY_Home: 'home', Gdk.KEY_End: 'end',
                      Gdk.KEY_Tab: 'right'}
        if keyval in directions:
            self.selected = move_selection(self.selected, len(self.cards) + 1,
                                           self._columns, directions[keyval])
            self.stage.queue_draw()
            return True
        if Gdk.KEY_1 <= keyval <= Gdk.KEY_9:
            number = keyval - Gdk.KEY_0
            for index, card in enumerate(self.cards):
                if card['num'] == number:
                    self.activate(index)
                    return True
            return True
        return False

    def card_at(self, x, y):
        for rect in self._rects:
            if (rect['x'] <= x < rect['x'] + rect['width']
                    and rect['y'] <= y < rect['y'] + rect['height']):
                return rect['index']
        return None

    def still_at(self, x, y):
        for still in self._still_rects:
            if (still['x'] <= x < still['x'] + still['width']
                    and still['y'] <= y < still['y'] + still['height']):
                return still
        return None

    def moved(self, x, y):
        index = self.card_at(x, y)
        if index != self.hovered:
            self.hovered = index
            return True
        return bool(self._drag)

    def released(self, x, y, presses):
        if self._drag:
            return True
        index = self.card_at(x, y)
        if index is None:
            self.request_close()
            return True
        self.selected = index
        self.activate(index)
        return True

    def _drag_begin(self, gesture, x, y):
        still = self.still_at(x, y)
        self._drag = dict(still, start_x=x, start_y=y, dx=0.0, dy=0.0) if still else None

    def _drag_update(self, gesture, dx, dy):
        if self._drag:
            self._drag['dx'], self._drag['dy'] = dx, dy
            self.stage.queue_draw()

    def _drag_end(self, gesture, dx, dy):
        drag = self._drag
        self._drag = None
        if not drag:
            return
        if abs(dx) < 12 and abs(dy) < 12:
            self.stage.queue_draw()
            return
        target = self.card_at(drag['start_x'] + dx, drag['start_y'] + dy)
        if target is not None and target != drag['card']:
            self.move_window(drag['view_id'], target)
        self.stage.queue_draw()

    # Drawing -------------------------------------------------------------

    def render(self, snapshot, width, height):
        total = len(self.cards) + 1
        aspect = max(0.5, self.width / max(1.0, self.height))
        grid = workspace_grid(width, height, total, aspect)
        self._columns = max(1, grid['columns'])
        self._rects, self._still_rects = [], []
        self.text(snapshot, 'Mission Control', 0, height * 0.055, width, 22.0,
                  self.color('muted'), bold=True)
        for card, rect in zip(range(total), grid['cards']):
            entry = dict(rect, index=card)
            self._rects.append(entry)
            if card == len(self.cards):
                self.render_new_card(snapshot, entry)
            else:
                self.render_card(snapshot, entry, self.cards[card])
        self.render_drag(snapshot)

    def _card_frame(self, snapshot, rect, card=None):
        selected = rect['index'] == self.selected
        hovered = rect['index'] == self.hovered
        focused = bool(card and card['focused'])
        outline = self.rounded(rect['x'], rect['y'], rect['width'],
                               rect['height'] - 30.0, CARD_RADIUS)
        snapshot.push_rounded_clip(outline)
        snapshot.append_color(self.color('background_hard', 0.82 if hovered else 0.66),
                              self.rectangle(rect['x'], rect['y'], rect['width'],
                                             rect['height'] - 30.0))
        snapshot.pop()
        if selected or focused:
            border = self.Gsk.RoundedRect().init_from_rect(
                self.rectangle(rect['x'] - 2, rect['y'] - 2, rect['width'] + 4,
                               rect['height'] - 26.0), CARD_RADIUS + 2)
            color = self.color('accent', 1.0 if selected else 0.55)
            snapshot.append_border(border, [2.0, 2.0, 2.0, 2.0], [color, color, color, color])
        return outline

    def render_card(self, snapshot, rect, card):
        self._card_frame(snapshot, rect, card)
        inner_x, inner_y = rect['x'] + 10, rect['y'] + 10
        inner_w, inner_h = rect['width'] - 20, rect['height'] - 50.0
        views = card['views']
        if not views:
            self.text(snapshot, 'Empty', rect['x'], rect['y'] + (rect['height'] - 30) / 2 - 10,
                      rect['width'], 15.0, self.color('muted', 0.7))
        for slot, view in zip(tile_stills(len(views), inner_w, inner_h), views):
            x, y = inner_x + slot['x'], inner_y + slot['y']
            texture = self.textures.get(view['id'])
            self._still_rects.append({'x': x, 'y': y, 'width': slot['width'],
                                      'height': slot['height'], 'view_id': view['id'],
                                      'card': rect['index']})
            tile = self.rounded(x, y, slot['width'], slot['height'], 8.0)
            snapshot.push_rounded_clip(tile)
            # A window whose content is nearly black still has to read as a
            # window, so every still sits on a surface and keeps a thin edge.
            snapshot.append_color(self.color('surface', 0.55),
                                  self.rectangle(x, y, slot['width'], slot['height']))
            if texture is not None:
                box = letterbox(texture.get_width(), texture.get_height(),
                                slot['width'], slot['height'])
                snapshot.append_texture(texture, self.rectangle(
                    x + box[0], y + box[1], box[2], box[3]))
            else:
                snapshot.append_color(self.color('surface', 0.75),
                                      self.rectangle(x, y, slot['width'], slot['height']))
                label = view['app_id'] or view['name'] or 'Window'
                self.text(snapshot, label, x + 6, y, slot['width'] - 12, 12.0,
                          self.color('muted'), height=slot['height'])
            snapshot.pop()
            edge = self.color('border', 0.75)
            snapshot.append_border(tile, [1.0, 1.0, 1.0, 1.0], [edge, edge, edge, edge])
        caption = card['name']
        if card['count'] > len(views):
            caption += f'  +{card["count"] - len(views)}'
        self.text(snapshot, caption, rect['x'], rect['y'] + rect['height'] - 26.0,
                  rect['width'], 14.0,
                  self.color('foreground' if card['focused'] else 'muted'),
                  bold=card['focused'])

    def render_new_card(self, snapshot, rect):
        self._card_frame(snapshot, rect)
        # Drawn rather than typed: a full-width plus is missing from the desktop
        # font and rendered as a replacement box.
        arm, thickness = 22.0, 3.0
        centre_x = rect['x'] + rect['width'] / 2
        centre_y = rect['y'] + (rect['height'] - 30.0) / 2
        color = self.color('muted', 0.85)
        snapshot.append_color(color, self.rectangle(
            centre_x - arm, centre_y - thickness / 2, arm * 2, thickness))
        snapshot.append_color(color, self.rectangle(
            centre_x - thickness / 2, centre_y - arm, thickness, arm * 2))
        self.text(snapshot, workspace_name(self.new_number),
                  rect['x'], rect['y'] + rect['height'] - 26.0, rect['width'], 14.0,
                  self.color('muted'))

    def render_drag(self, snapshot):
        drag = self._drag
        if not drag:
            return
        texture = self.textures.get(drag['view_id'])
        x = drag['x'] + drag['dx']
        y = drag['y'] + drag['dy']
        outline = self.rounded(x, y, drag['width'], drag['height'], 8.0)
        snapshot.push_opacity(0.85)
        snapshot.push_rounded_clip(outline)
        if texture is not None:
            box = letterbox(texture.get_width(), texture.get_height(),
                            drag['width'], drag['height'])
            snapshot.append_texture(texture, self.rectangle(
                x + box[0], y + box[1], box[2], box[3]))
        else:
            snapshot.append_color(self.color('surface'),
                                  self.rectangle(x, y, drag['width'], drag['height']))
        snapshot.pop()
        snapshot.pop()


def main(action='toggle'):
    from grid_overlay import serve
    serve(MissionControl, action, 'mission-control')
