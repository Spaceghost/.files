"""Theme descriptors shared by the wallpaper generator and gallery."""
import json
from pathlib import Path
import re


def safe_theme_id(value):
    return isinstance(value, str) and re.fullmatch(r'[a-z0-9][a-z0-9-]{0,63}', value) is not None


def has_symlink(path, root):
    """Reject links at every component, including an otherwise in-root target."""
    try:
        relative = path.relative_to(root)
    except ValueError:
        return True
    current = root
    for component in relative.parts:
        if component in ('.', '..'):
            return True
        current /= component
        if current.is_symlink():
            return True
    return False


def load_theme(repo, selection='active'):
    directory = repo / 'alpine/themes'
    if selection == 'active':
        current = directory / 'current'
        if has_symlink(current, repo):
            raise RuntimeError('The active theme must be a regular file in the checkout')
        selection = current.read_text().strip() if current.exists() else 'none'
    if selection == 'none':
        return {'id': 'none', 'name': 'Unthemed', 'image_style': ''}
    if not safe_theme_id(selection):
        raise RuntimeError('Invalid theme ID: ' + str(selection))
    source = directory / (selection + '.json')
    if has_symlink(source, repo) or not source.is_file():
        raise RuntimeError('Unknown or unsafe theme: ' + selection)
    theme = json.loads(source.read_text())
    if (not isinstance(theme, dict) or theme.get('id') != selection
            or not isinstance(theme.get('name'), str) or not theme['name'].strip()
            or not isinstance(theme.get('image_style'), str)):
        raise RuntimeError('Invalid theme descriptor: ' + selection)
    return theme


def available_themes(repo):
    themes = []
    for source in sorted((repo / 'alpine/themes').glob('*.json')):
        try:
            themes.append(load_theme(repo, source.stem))
        except (OSError, ValueError, RuntimeError):
            continue
    return themes
