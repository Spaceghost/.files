"""Presentation rules for one caption at each visible workspace's edge."""
import json
import math
import os
from pathlib import Path
import unicodedata


SETTINGS_DEFAULTS = {'position': 'bottom', 'opacity': 0.78, 'corner_radius': 7}
IGNORED_CAPTION_APPS = frozenset((
    'com.oldbook.dropdown', 'oldbook-dropdown', 'com.oldbook.monitor',
))


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
    if not math.isfinite(opacity) or not 0.2 <= opacity <= 1:
        raise ValueError('Decoration opacity must be between 0.2 and 1')
    radius = result['corner_radius']
    if isinstance(radius, bool) or not isinstance(radius, int) or not 0 <= radius <= 24:
        raise ValueError('Decoration corner radius must be an integer from 0 to 24')
    result['opacity'] = opacity
    return result


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
            if child.get('app_id') not in IGNORED_CAPTION_APPS:
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
