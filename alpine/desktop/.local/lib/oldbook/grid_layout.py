"""Grid geometry and keyboard navigation for the Launchpad and Mission Control overlays.

Pure logic: every function takes plain numbers and returns plain dictionaries, so
the layout can be tested without a compositor. Both grids share the same idea —
a centred block of equal cells inside a padded viewport — but Launchpad pages its
cells and Mission Control sizes its cards to the output's aspect ratio.
"""
import math

ICON_CELL = 168.0
ICON_MIN_COLUMNS = 4
ICON_MAX_COLUMNS = 9
ICON_MAX_ROWS = 5
MARGIN_X = 0.10
MARGIN_TOP = 0.16
MARGIN_BOTTOM = 0.12


def launchpad_grid(width, height, count, cell=ICON_CELL):
    """Columns, rows and the page size for an icon grid inside the viewport."""
    if width <= 0 or height <= 0:
        return {'columns': 0, 'rows': 0, 'page_size': 0, 'pages': 0,
                'cell_width': 0.0, 'cell_height': 0.0, 'origin_x': 0.0, 'origin_y': 0.0}
    usable_width = width * (1.0 - 2 * MARGIN_X)
    usable_height = height * (1.0 - MARGIN_TOP - MARGIN_BOTTOM)
    columns = max(ICON_MIN_COLUMNS, min(ICON_MAX_COLUMNS, int(usable_width // cell)))
    rows = max(1, min(ICON_MAX_ROWS, int(usable_height // cell)))
    page_size = columns * rows
    pages = max(1, math.ceil(max(0, count) / page_size)) if page_size else 0
    cell_width = usable_width / columns
    cell_height = usable_height / rows
    block_width = cell_width * columns
    block_height = cell_height * rows
    return {
        'columns': columns, 'rows': rows, 'page_size': page_size, 'pages': pages,
        'cell_width': cell_width, 'cell_height': cell_height,
        'origin_x': (width - block_width) / 2,
        'origin_y': height * MARGIN_TOP + (usable_height - block_height) / 2,
    }


def launchpad_cells(grid, count, page):
    """Rectangles for the entries on one page, with their absolute indices."""
    cells = []
    page_size = grid['page_size']
    if page_size <= 0:
        return cells
    start = page * page_size
    for slot in range(page_size):
        index = start + slot
        if index >= count:
            break
        row, column = divmod(slot, grid['columns'])
        cells.append({
            'index': index, 'slot': slot, 'row': row, 'column': column,
            'x': grid['origin_x'] + column * grid['cell_width'],
            'y': grid['origin_y'] + row * grid['cell_height'],
            'width': grid['cell_width'], 'height': grid['cell_height'],
        })
    return cells


def hit_cell(cells, x, y):
    """Index of the cell containing the point, or None."""
    for cell in cells:
        if (cell['x'] <= x < cell['x'] + cell['width']
                and cell['y'] <= y < cell['y'] + cell['height']):
            return cell['index']
    return None


def move_selection(index, count, columns, direction):
    """Arrow-key movement across a wrapped grid; the selection never escapes."""
    if count <= 0 or columns <= 0:
        return None
    index = max(0, min(count - 1, 0 if index is None else index))
    if direction == 'left':
        return (index - 1) % count
    if direction == 'right':
        return (index + 1) % count
    if direction == 'up':
        candidate = index - columns
        return candidate if candidate >= 0 else index
    if direction == 'down':
        candidate = index + columns
        return candidate if candidate < count else index
    if direction == 'home':
        return 0
    if direction == 'end':
        return count - 1
    return index


def page_of(index, page_size):
    return 0 if page_size <= 0 else max(0, index) // page_size


def workspace_grid(width, height, count, aspect=16 / 10):
    """Card rectangles for every workspace, as large as the viewport allows.

    Cards keep the output's aspect ratio so a still is never distorted; the
    column count is the one that makes the cards biggest.
    """
    if width <= 0 or height <= 0 or count <= 0:
        return {'columns': 0, 'rows': 0, 'cards': [], 'card_width': 0.0, 'card_height': 0.0}
    usable_width = width * (1.0 - 2 * MARGIN_X)
    usable_height = height * (1.0 - MARGIN_TOP - MARGIN_BOTTOM)
    gap = min(28.0, usable_width * 0.02)
    best = None
    for columns in range(1, count + 1):
        rows = math.ceil(count / columns)
        card_width = (usable_width - gap * (columns - 1)) / columns
        card_height = (usable_height - gap * (rows - 1)) / rows
        # A card holds a still plus a caption strip below it.
        fitted_height = min(card_height, card_width / aspect + 34.0)
        fitted_width = min(card_width, (fitted_height - 34.0) * aspect)
        if fitted_width <= 0 or fitted_height <= 0:
            continue
        area = fitted_width * fitted_height
        if best is None or area > best[0]:
            best = (area, columns, rows, fitted_width, fitted_height)
    if best is None:
        return {'columns': 0, 'rows': 0, 'cards': [], 'card_width': 0.0, 'card_height': 0.0}
    _, columns, rows, card_width, card_height = best
    block_width = card_width * columns + gap * (columns - 1)
    block_height = card_height * rows + gap * (rows - 1)
    origin_x = (width - block_width) / 2
    origin_y = height * MARGIN_TOP + (usable_height - block_height) / 2
    cards = []
    for index in range(count):
        row, column = divmod(index, columns)
        in_row = min(columns, count - row * columns)
        row_width = card_width * in_row + gap * (in_row - 1)
        row_origin = (width - row_width) / 2 if row == rows - 1 else origin_x
        cards.append({
            'index': index, 'row': row, 'column': column,
            'x': row_origin + column * (card_width + gap),
            'y': origin_y + row * (card_height + gap),
            'width': card_width, 'height': card_height,
        })
    return {'columns': columns, 'rows': rows, 'cards': cards,
            'card_width': card_width, 'card_height': card_height}


def letterbox(pixel_width, pixel_height, width, height):
    """Centre a still inside a card without distorting it."""
    if pixel_width <= 0 or pixel_height <= 0:
        return (0.0, 0.0, float(width), float(height))
    scale = min(width / pixel_width, height / pixel_height)
    fitted_width, fitted_height = pixel_width * scale, pixel_height * scale
    return ((width - fitted_width) / 2, (height - fitted_height) / 2, fitted_width, fitted_height)


def tile_stills(count, width, height):
    """Slots for the stills inside one workspace card, newest windows first."""
    if count <= 0 or width <= 0 or height <= 0:
        return []
    columns = 1 if count == 1 else (2 if count <= 4 else 3)
    rows = math.ceil(count / columns)
    gap = min(8.0, width * 0.03)
    tile_width = (width - gap * (columns - 1)) / columns
    tile_height = (height - gap * (rows - 1)) / rows
    slots = []
    for index in range(count):
        row, column = divmod(index, columns)
        slots.append({'index': index,
                      'x': column * (tile_width + gap), 'y': row * (tile_height + gap),
                      'width': tile_width, 'height': tile_height})
    return slots
