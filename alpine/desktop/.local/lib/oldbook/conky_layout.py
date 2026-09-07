"""Fit transparent Conky panels into the calm parts of the current wallpaper.

The wallpaper is reduced to two coarse grids: how much detail each cell holds
and how bright it is. Panels are then placed greedily into the calmest cells
that still respect their preferred edge, so the painting's subject stays clear.
Colours come from the active theme, adjusted per panel so text keeps contrast
against the region it actually covers.
"""
import colorsys
import json
import math
import re
from conky_policy import quiet_document

DETAIL_WEIGHT = 1.0
CONTRAST_WEIGHT = 0.6
EDGE_BONUS = 0.35
CENTRE_PENALTY = 1.4
MIN_CONTRAST = 4.5

# Every theme supplies at least a background/foreground/accent; the richer
# Gruvbox-style descriptors override these named series colours when present.
SERIES_KEYS = ('red', 'green', 'yellow', 'blue', 'purple', 'aqua', 'orange')
FALLBACK_PALETTE = {
    'background': '#101014', 'foreground': '#e8e4dc', 'muted': '#9a9188',
    'accent': '#d8a657', 'red': '#e06c63', 'green': '#a9b665', 'yellow': '#d8a657',
    'blue': '#7daea3', 'purple': '#d3869b', 'aqua': '#89b482', 'orange': '#e78a4e',
}


def parse_colour(value):
    match = re.fullmatch(r'#?([0-9a-fA-F]{6})', str(value or '').strip())
    if not match:
        raise ValueError(f'Expected a #RRGGBB colour, received {value!r}')
    digits = match.group(1)
    return tuple(int(digits[index:index + 2], 16) for index in (0, 2, 4))


def format_colour(rgb):
    return '#%02x%02x%02x' % tuple(max(0, min(255, int(round(channel)))) for channel in rgb)


def relative_luminance(rgb):
    """WCAG relative luminance, used so panel text keeps a real contrast ratio."""
    channels = []
    for channel in rgb:
        fraction = channel / 255
        channels.append(fraction / 12.92 if fraction <= 0.04045
                        else ((fraction + 0.055) / 1.055) ** 2.4)
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def contrast_ratio(first, second):
    lighter, darker = sorted((relative_luminance(first), relative_luminance(second)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


def adjust_lightness(rgb, amount):
    hue, lightness, saturation = colorsys.rgb_to_hls(*(channel / 255 for channel in rgb))
    lightness = max(0.0, min(1.0, lightness + amount))
    return tuple(channel * 255 for channel in colorsys.hls_to_rgb(hue, lightness, saturation))


def readable(colour, background, minimum=MIN_CONTRAST):
    """Lighten or darken a theme colour until it is legible over the wallpaper."""
    rgb = parse_colour(colour) if isinstance(colour, str) else colour
    if contrast_ratio(rgb, background) >= minimum:
        return rgb
    direction = 0.06 if relative_luminance(background) < 0.5 else -0.06
    candidate = rgb
    for _ in range(16):
        candidate = adjust_lightness(candidate, direction)
        if contrast_ratio(candidate, background) >= minimum:
            return candidate
    return (255, 255, 255) if relative_luminance(background) < 0.5 else (0, 0, 0)


def resolve_palette(theme):
    palette = dict(FALLBACK_PALETTE)
    supplied = (theme or {}).get('palette') or {}
    for key, value in supplied.items():
        try:
            palette[key] = format_colour(parse_colour(value))
        except ValueError:
            continue
    palette.setdefault('muted', palette['foreground'])
    # A three-colour descriptor still needs a full series; derive it from the accent.
    accent = parse_colour(palette['accent'])
    for offset, key in enumerate(SERIES_KEYS):
        if key not in supplied:
            hue, lightness, saturation = colorsys.rgb_to_hls(*(c / 255 for c in accent))
            shifted = colorsys.hls_to_rgb((hue + offset / len(SERIES_KEYS)) % 1.0,
                                          lightness, saturation)
            palette[key] = format_colour(tuple(c * 255 for c in shifted))
    return palette


def analyze_image(path, columns, rows):
    """Reduce a wallpaper to per-cell detail and brightness grids."""
    import gi
    gi.require_version('GdkPixbuf', '2.0')
    from gi.repository import GdkPixbuf
    import numpy

    # Sample well above the cell grid so within-cell detail survives the reduction.
    sample_width, sample_height = columns * 4, rows * 4
    pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(str(path), sample_width, sample_height, False)
    width, height = pixbuf.get_width(), pixbuf.get_height()
    channels, stride = pixbuf.get_n_channels(), pixbuf.get_rowstride()
    raw = numpy.frombuffer(pixbuf.get_pixels(), dtype=numpy.uint8)
    image = raw[:height * stride].reshape(height, stride)[:, :width * channels]
    image = image.reshape(height, width, channels)[:, :, :3].astype(numpy.float32)
    luma = (0.2126 * image[:, :, 0] + 0.7152 * image[:, :, 1] + 0.0722 * image[:, :, 2]) / 255.0

    gradient = numpy.zeros_like(luma)
    gradient[:, :-1] += numpy.abs(numpy.diff(luma, axis=1))
    gradient[:-1, :] += numpy.abs(numpy.diff(luma, axis=0))

    detail = _block_mean(gradient, columns, rows)
    brightness = _block_mean(luma, columns, rows)
    colour = numpy.stack([_block_mean(image[:, :, index], columns, rows) for index in range(3)], axis=-1)
    peak = float(detail.max()) or 1.0
    return {'detail': (detail / peak).tolist(), 'brightness': brightness.tolist(),
            'colour': colour.tolist(), 'columns': columns, 'rows': rows}


def _block_mean(array, columns, rows):
    import numpy

    height, width = array.shape
    row_edges = numpy.linspace(0, height, rows + 1).astype(int)
    column_edges = numpy.linspace(0, width, columns + 1).astype(int)
    result = numpy.zeros((rows, columns), dtype=numpy.float32)
    for row in range(rows):
        top, bottom = row_edges[row], max(row_edges[row] + 1, row_edges[row + 1])
        for column in range(columns):
            left, right = column_edges[column], max(column_edges[column] + 1, column_edges[column + 1])
            result[row, column] = array[top:bottom, left:right].mean()
    return result


def _region(grid, key, left, top, width, height):
    values = [grid[key][row][column]
              for row in range(top, top + height) for column in range(left, left + width)]
    return values or [0.0]


def region_colour(grid, left, top, width, height):
    channels = [grid['colour'][row][column]
                for row in range(top, top + height) for column in range(left, left + width)]
    if not channels:
        return (0, 0, 0)
    return tuple(sum(channel[index] for channel in channels) / len(channels) for index in range(3))


def _score(grid, left, top, width, height, prefer, columns, rows):
    detail = _region(grid, 'detail', left, top, width, height)
    brightness = _region(grid, 'brightness', left, top, width, height)
    mean_detail = sum(detail) / len(detail)
    spread = max(brightness) - min(brightness)
    score = DETAIL_WEIGHT * mean_detail + CONTRAST_WEIGHT * spread

    centre_column = (left + width / 2) / columns
    centre_row = (top + height / 2) / rows
    # The subject of a painting normally sits near the middle; keep panels off it.
    score += CENTRE_PENALTY * max(0.0, 0.5 - abs(centre_column - 0.5)) * \
        max(0.0, 0.5 - abs(centre_row - 0.5)) * 4
    edges = {'left': 1 - centre_column, 'right': centre_column,
             'top': 1 - centre_row, 'bottom': centre_row}
    if prefer in edges:
        score -= EDGE_BONUS * edges[prefer]
    return score


def reserved_cells(rectangles, grid, area):
    """Convert pixel rectangles, such as the search bar, into occupied cells."""
    cell_width = area['width'] / grid['columns']
    cell_height = area['height'] / grid['rows']
    cells = []
    for rectangle in rectangles or ():
        left = int(rectangle['x'] / cell_width)
        top = int(rectangle['y'] / cell_height)
        width = max(1, math.ceil(rectangle['width'] / cell_width))
        height = max(1, math.ceil(rectangle['height'] / cell_height))
        cells.append((left, top, width, height))
    return cells


def place_panels(panels, grid, area, *, gap=1, reserved=()):
    """Greedily seat each panel in the calmest free rectangle it fits.

    ``area`` carries the screen size plus insets for the panel bar and the
    margins that keep text away from the physical edges of the display.
    """
    columns, rows = grid['columns'], grid['rows']
    cell_width = area['width'] / columns
    cell_height = area['height'] / rows
    # Round insets outward so a panel never encroaches on the bar or the bezel.
    first_row = math.ceil(area.get('top', 0) / cell_height)
    last_row = rows - math.ceil(area.get('bottom', 0) / cell_height)
    first_column = math.ceil(area.get('left', 0) / cell_width)
    last_column = columns - math.ceil(area.get('right', 0) / cell_width)
    taken = list(reserved_cells(reserved, grid, area))
    placements = []
    for panel in sorted(panels, key=lambda item: -item.get('priority', 0)):
        width = max(1, min(columns, round(panel['width'] / cell_width)))
        height = max(1, min(rows, round(panel['height'] / cell_height)))
        best = None
        for top in range(first_row, last_row - height + 1):
            for left in range(first_column, last_column - width + 1):
                if any(_overlaps(left, top, width, height, other, gap) for other in taken):
                    continue
                score = _score(grid, left, top, width, height, panel.get('prefer'), columns, rows)
                if best is None or score < best[0]:
                    best = (score, left, top)
        if best is None:
            continue
        _, left, top = best
        taken.append((left, top, width, height))
        placements.append({
            'id': panel['id'], 'x': int(round(left * cell_width)),
            'y': int(round(top * cell_height)),
            'width': int(round(width * cell_width)), 'height': int(round(height * cell_height)),
            'cell': {'left': left, 'top': top, 'columns': width, 'rows': height},
            'score': round(best[0], 4),
            'background': [round(channel) for channel in region_colour(grid, left, top, width, height)],
        })
    return placements


def _overlaps(left, top, width, height, other, gap):
    other_left, other_top, other_width, other_height = other
    return not (left >= other_left + other_width + gap
                or left + width + gap <= other_left
                or top >= other_top + other_height + gap
                or top + height + gap <= other_top)


def panel_colours(placement, palette):
    """Pick text colours that stay legible over this panel's slice of the image."""
    background = tuple(placement['background'])
    shadow = '#000000' if relative_luminance(background) >= 0.35 else '#000000'
    return {
        'default': format_colour(readable(palette['foreground'], background)),
        'accent': format_colour(readable(palette['accent'], background)),
        'muted': format_colour(readable(palette['muted'], background, minimum=3.0)),
        'series': [format_colour(readable(palette[key], background, minimum=3.0))
                   for key in SERIES_KEYS],
        'shadow': shadow,
        'dark_region': relative_luminance(background) < 0.35,
    }


def lua_string(value):
    return "'" + str(value).replace('\\', '\\\\').replace("'", "\\'") + "'"


def render_config(panel, placement, colours, options):
    """Emit one fully transparent Conky instance pinned to its computed rectangle."""
    settings = {
        'out_to_wayland': 'true', 'out_to_x': 'false',
        'own_window': 'true', 'own_window_type': lua_string('desktop'),
        # A zero-alpha window colour is what makes the panel genuinely transparent.
        'own_window_colour': lua_string('#00000000'),
        'own_window_class': lua_string('oldbook-conky'),
        'own_window_title': lua_string('oldbook-conky-' + panel['id']),
        'alignment': lua_string('top_left'),
        'gap_x': placement['x'], 'gap_y': placement['y'],
        'minimum_width': placement['width'], 'maximum_width': placement['width'],
        'minimum_height': placement['height'],
        'update_interval': options.get('update_interval', 60.0),
        'double_buffer': 'true', 'no_buffers': 'true',
        'use_xft': 'true', 'xftalpha': 1,
        'font': lua_string(options.get('font', 'JetBrainsMono Nerd Font:size=9')),
        'default_color': lua_string(colours['default']),
        'color1': lua_string(colours['accent']), 'color2': lua_string(colours['muted']),
        'draw_shades': 'true', 'default_shade_color': lua_string(colours['shadow']),
        'draw_outline': 'false', 'draw_borders': 'false', 'draw_graph_borders': 'true',
        'border_inner_margin': 0, 'border_outer_margin': 0,
        'stippled_borders': 0, 'text_buffer_size': 4096,
        'short_units': 'true', 'pad_percents': 2, 'use_spacer': lua_string('none'),
        'override_utf8_locale': 'true', 'format_human_readable': 'true',
        'cpu_avg_samples': 2, 'net_avg_samples': 2, 'top_name_width': 12,
    }
    for index, colour in enumerate(colours['series'][:6], start=3):
        settings[f'color{index}'] = lua_string(colour)
    lines = ['-- Generated by oldbook-conky; edits are replaced on the next wallpaper change.',
             'conky.config = {']
    for key, value in settings.items():
        lines.append(f'    {key} = {value},')
    lines.append('}')
    lines.append('')
    lines.append('conky.text = [[' + panel['text'].rstrip('\n') + ']]')
    return '\n'.join(lines) + '\n'


def plan(panels, grid, area, palette, options, reserved=()):
    placements = place_panels(panels, grid, area, gap=options.get('gap', 1), reserved=reserved)
    by_id = {panel['id']: panel for panel in panels}
    plans = []
    for placement in placements:
        panel = by_id[placement['id']]
        colours = panel_colours(placement, palette)
        plans.append({'panel': panel, 'placement': placement, 'colours': colours,
                      'config': render_config(panel, placement, colours, options)})
    return plans


def load_panels(path):
    from pathlib import Path

    document = json.loads(Path(path).read_text())
    panels = document.get('panels')
    if not isinstance(panels, list) or not panels:
        raise ValueError('Panel file must define a non-empty panels list')
    seen = set()
    for panel in panels:
        if not isinstance(panel, dict) or not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,31}', str(panel.get('id', ''))):
            raise ValueError('Every panel needs a lowercase hyphenated id')
        if panel['id'] in seen:
            raise ValueError('Duplicate panel id: ' + panel['id'])
        seen.add(panel['id'])
        for key in ('width', 'height'):
            if not isinstance(panel.get(key), int) or panel[key] <= 0:
                raise ValueError(f'Panel {panel["id"]} needs a positive integer {key}')
        if not isinstance(panel.get('text'), str) or not panel['text'].strip():
            raise ValueError(f'Panel {panel["id"]} needs Conky text')
        if 'enabled' in panel and not isinstance(panel['enabled'], bool):
            raise ValueError(f'Panel {panel["id"]} enabled must be true or false')
    return quiet_document(document)
