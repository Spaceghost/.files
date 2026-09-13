"""Presentation rules for one caption at each visible workspace's edge."""
import json
import math
import os
from pathlib import Path
import unicodedata

import ripple

# The `ripple` object is the landing wave's own vocabulary: ripple.DEFAULTS and
# ripple.settings() own its keys and limits, so they are named in one place.
SETTINGS_DEFAULTS = {'position': 'bottom', 'opacity': 0.78, 'corner_radius': 7,
                     'reserve_band': True, 'powerline': False,
                     'ripple': dict(ripple.DEFAULTS)}
OPACITY_FLOOR = 0.2
IGNORED_CAPTION_APPS = frozenset((
    'com.oldbook.dropdown', 'oldbook-dropdown', 'com.oldbook.monitor',
    # The firewall's prompt is a decision, not a window you live in: it appears
    # to be answered and then goes. A caption naming it is chrome on a dialog.
    # It is an Xwayland Qt window, so it carries no app_id at all and is only
    # recognisable by its class -- which is why identity is matched across all
    # three fields rather than app_id alone.
    'opensnitch-ui', 'opensnitch_ui',
    # The shortcut guide is something you read across whatever you were already
    # doing, not a window you are working in. Letting the strip follow it names
    # the guide instead of the thing the guide is describing, and pulls the
    # caption off that window for as long as the guide is up.
    'superhold', 'org.superhold.Settings',
))
# A picture-in-picture window is a video parked on the desktop to keep watching
# while doing something else. It is deliberately small, its title says nothing
# worth reading, and a caption across it covers the one thing it exists to show.
PICTURE_IN_PICTURE_APPS = frozenset(('mpv', 'io.mpv.Mpv', 'oldbook-youtube'))
# Firefox names its picture-in-picture window exactly this, and its main window
# always carries the site and the browser too, so an exact match cannot catch a
# page that merely happens to be about the feature.
PICTURE_IN_PICTURE_TITLES = frozenset(('picture-in-picture', 'picture in picture'))


def picture_in_picture(node):
    if window_identity(node) & {name.casefold() for name in PICTURE_IN_PICTURE_APPS}:
        return True
    return str(node.get('name') or '').strip().casefold() in PICTURE_IN_PICTURE_TITLES


def window_identity(node):
    """Every name a window answers to, folded for comparison.

    A Wayland client has an `app_id`; an Xwayland one has a class and an
    instance instead and no `app_id` whatsoever, so anything matching on
    `app_id` alone silently never matches half the windows on the desktop.
    """
    properties = node.get('window_properties') or {}
    return {str(value).casefold() for value in
            (node.get('app_id'), properties.get('class'), properties.get('instance'))
            if value}


def ignored_caption(node):
    """Windows the strip must not attach itself to."""
    if window_identity(node) & {name.casefold() for name in IGNORED_CAPTION_APPS}:
        return True
    return picture_in_picture(node)


def validate_settings(values):
    if not isinstance(values, dict):
        raise ValueError('Decoration settings must be an object')
    unknown = set(values) - set(SETTINGS_DEFAULTS)
    if unknown:
        raise ValueError('Unknown decoration setting: ' + sorted(unknown)[0])
    result = dict(SETTINGS_DEFAULTS)
    result.update(values)
    if result['position'] not in ('bottom', 'right'):
        raise ValueError('Decoration position must be bottom or right')
    opacity = result['opacity']
    if isinstance(opacity, bool) or not isinstance(opacity, (int, float)):
        raise ValueError('Decoration opacity must be a number')
    opacity = float(opacity)
    if not math.isfinite(opacity) or not OPACITY_FLOOR <= opacity <= 1:
        raise ValueError('Decoration opacity must be between 0.2 and 1')
    radius = result['corner_radius']
    if isinstance(radius, bool) or not isinstance(radius, int) or not 0 <= radius <= 24:
        raise ValueError('Decoration corner radius must be an integer from 0 to 24')
    for name in ('reserve_band', 'powerline'):
        if not isinstance(result[name], bool):
            raise ValueError('Decoration ' + name.replace('_', ' ') + ' must be true or false')
    result['opacity'] = opacity
    result['ripple'] = ripple.settings(result['ripple'])
    return result


def window_opacity(node, terminal=False, theme=None, saved=SETTINGS_DEFAULTS['opacity']):
    """Match the window the strip is decorating, so it reads as part of it.

    Sway only reports a container opacity where something explicitly set one, so
    that answer wins wherever it exists and is actually transparent; a window
    sway calls fully opaque tells us nothing the application has not already.
    Otherwise a terminal is as transparent as the active theme says terminals
    are -- the same value the terminal's own configuration is generated from, so
    the two move together when the theme changes -- and an ordinary application
    is opaque, which makes its caption opaque with it rather than a translucent
    slab floating over a solid window. An empty workspace decorates the desktop
    itself and keeps the saved preference.
    """
    fallback = saved if isinstance(saved, (int, float)) and not isinstance(saved, bool) else \
        SETTINGS_DEFAULTS['opacity']
    if not node or not (node.get('app_id') or node.get('window')):
        return float(fallback)
    explicit = node.get('opacity')
    if isinstance(explicit, (int, float)) and not isinstance(explicit, bool):
        explicit = float(explicit)
        if math.isfinite(explicit) and 0 < explicit < 1:
            return max(OPACITY_FLOOR, explicit)
    if terminal and isinstance(theme, (int, float)) and not isinstance(theme, bool):
        theme = float(theme)
        if math.isfinite(theme) and 0 < theme <= 1:
            return max(OPACITY_FLOOR, theme)
    return 1.0 if not terminal else float(fallback)


# SwayFX accepts a window corner radius of 0 to 99 and nothing else.
CORNER_LIMIT = 99


def window_radius(value):
    """The compositor's own window corner radius, as a number the strip can use.

    SwayFX 0.6 has no per-window corner radius to ask for. `cmd_corner_radius`
    writes the single global `config->corner_radius` whatever criteria precede
    it -- setting one container is an unimplemented TODO in that function -- and
    it widens the titlebar padding on the way past, so squaring one window
    would square every window opened afterwards. The strip therefore never asks
    the compositor to change a window. It reads the same theme number the
    compositor's own `corner_radius` line is generated from, so the two move
    together on a theme switch exactly as the terminal opacity does, and closes
    the seam itself.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0
    try:
        value = int(value)
    except (ValueError, OverflowError):
        return 0
    return max(0, min(CORNER_LIMIT, value))


def seam_overlap(mode, edge, radius):
    """How far an attached strip climbs over its window to close the seam.

    Exactly the height of the arc the compositor clipped out of the window's
    bottom corners. The strip fills those two clipped corners and squares its
    own top, so the pair reads as one shape, and it covers no row of window
    content that the compositor was drawing: the only pixels it adds are the
    ones the rounding took away. Nothing else merges -- a right-edge strip
    meets a vertical side, and a workspace strip belongs to no window at all.
    """
    return window_radius(radius) if mode == 'window' and edge == 'bottom' else 0


def corner_radii(corner_radius, square, merged, window_radius=None):
    """(top, bottom) corner radius for the strip itself.

    A fullscreen tiled caption is square all round, as it has always been.

    Merged into the window above it, the strip is no longer its own object: the
    two are one shape, square where they meet and rounded only where the pair
    ends. So the bottom takes the *window's* radius rather than the strip's own
    saved one. Keeping the saved value there rounded the top of the assembly at
    the compositor's radius and the bottom at the strip's -- 22 against 7 on
    this desktop -- which reads as a card that has been cut off square rather
    than one shape. Unmerged, the strip is its own object again and keeps its
    own rounding.
    """
    radius = 0 if square else max(0, int(corner_radius))
    if square or not merged:
        return (0 if merged else radius), radius
    outer = radius if window_radius is None else max(0, int(window_radius))
    return 0, outer


def save_settings(path, values, legacy_position=None):
    settings = validate_settings(values)
    path = Path(path)
    target = path.resolve(strict=False) if path.is_symlink() else path
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f'{target.name}.{os.getpid()}.tmp')
    try:
        with temporary.open('x') as stream:
            json.dump(settings, stream, indent=2)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)
    if legacy_position is not None:
        legacy = Path(legacy_position)
        legacy.parent.mkdir(parents=True, exist_ok=True)
        state_temporary = legacy.with_name(f'{legacy.name}.{os.getpid()}.tmp')
        try:
            with state_temporary.open('x') as stream:
                stream.write(settings['position'] + '\n')
                stream.flush()
                os.fsync(stream.fileno())
            state_temporary.replace(legacy)
        finally:
            state_temporary.unlink(missing_ok=True)
    return settings


def load_settings(path, legacy_position=None):
    path = Path(path)
    try:
        return validate_settings(json.loads(path.read_text()))
    except FileNotFoundError:
        pass
    except (OSError, ValueError, TypeError):
        return dict(SETTINGS_DEFAULTS)
    if legacy_position is not None:
        try:
            position = Path(legacy_position).read_text().strip()
        except OSError:
            position = ''
        if position in ('bottom', 'right'):
            return save_settings(path, {'position': position})
    return dict(SETTINGS_DEFAULTS)


def focused_child(node):
    children = node.get('nodes', []) + node.get('floating_nodes', [])
    by_id = {child.get('id'): child for child in children}
    return next((by_id[identifier] for identifier in node.get('focus', [])
                 if identifier in by_id), children[0] if children else None)


def caption_child(node):
    """Follow focus history past desktop drop-downs to an ordinary window.

    Sway retains the previous child after a scratchpad takes focus. Filtering
    each branch keeps caption geometry and actions on that live window without
    retaining stale containers across closes or workspace changes.
    """
    children = node.get('nodes', []) + node.get('floating_nodes', [])
    by_id = {child.get('id'): child for child in children}
    ordered = [by_id[identifier] for identifier in node.get('focus', [])
               if identifier in by_id]
    ordered.extend(child for child in children if child not in ordered)
    for child in ordered:
        if child.get('app_id') or child.get('window'):
            if not ignored_caption(child):
                return child
        elif caption_child(child) is not None:
            return child
    return None


def focused_title(node):
    while node:
        if node.get('app_id') or node.get('window'):
            return ' '.join(str(node.get('name') or node.get('app_id') or 'Window').split())
        node = focused_child(node)
    return ''


def output_titles(tree):
    titles = {}
    for output in tree.get('nodes', []):
        if output.get('type') != 'output' or output.get('name', '').startswith('__'):
            continue
        workspace = focused_child(output)
        if workspace:
            titles[output['name']] = focused_title(workspace) or workspace.get('name', '')
    return titles


def action_command(button, home=Path.home(), shifted=False):
    """Map caption pointer buttons to fixed argument vectors; right-click is local."""
    if button == 1:
        return [str(home / '.local/bin/oldbook-control'), 'windows']
    if button == 2:
        return ['swaymsg', 'floating', 'toggle']
    if button == 3 and shifted:
        return [str(home / '.local/bin/oldbook-decoration-settings')]
    return None


def square_outputs(tree):
    """Fullscreen tiled views get square chrome; floating views keep corners."""
    result = set()
    for output in tree.get('nodes', []):
        if output.get('type') != 'output' or output.get('name', '').startswith('__'):
            continue
        node = focused_child(output)
        fullscreen = bool(tree.get('fullscreen_mode') or output.get('fullscreen_mode'))
        floating = False
        while node:
            fullscreen = fullscreen or bool(node.get('fullscreen_mode'))
            child = focused_child(node)
            floating_ids = {candidate.get('id') for candidate in node.get('floating_nodes', [])}
            floating = floating or bool(child and child.get('id') in floating_ids)
            node = child
        if fullscreen and not floating:
            result.add(output['name'])
    return result


def vertical_title(title, limit):
    clusters = []
    for char in ' '.join(title.replace('|', '—').split()):
        if clusters and (unicodedata.combining(char) or char in ('\ufe0f', '\u200d')
                         or clusters[-1].endswith('\u200d')):
            clusters[-1] += char
        else:
            clusters.append(char)
    limit = max(1, limit)
    if len(clusters) > limit:
        clusters = clusters[:limit - 1] + ['…']
    return '\n'.join(clusters)
