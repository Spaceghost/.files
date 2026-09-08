"""Cached thumbnails of gallery paintings, rendered with GdkPixbuf and cairo.

Thumbnails live under the user's cache directory, never inside the checkout.
Each file is keyed by the painting's content digest and its rendered geometry,
so one painting is rendered once per size and reused by every picker and bar
that shows it. Files are written atomically; a failed render leaves nothing
behind and the caller simply shows no image.

Fuzzel's dmenu icon protocol resolves names through an icon theme rather than
absolute paths, so the cache doubles as the single directory of a private
"Oldbook-Thumbnails" theme under the user's data directory. The theme inherits
the desktop icon theme, so ordinary icon names keep working beside paintings.
"""
import argparse
import configparser
import hashlib
import os
from pathlib import Path
import stat
import sys

CACHE_NAME = 'oldbook/thumbnails'
THEME = 'Oldbook-Thumbnails'
FALLBACK_THEMES = ('Papirus', 'hicolor')


def cache_directory(base=None):
    """The private, owned directory holding every rendered thumbnail."""
    if base is None:
        base = os.environ.get('XDG_CACHE_HOME') or str(Path.home() / '.cache')
    directory = Path(base) / CACHE_NAME
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    info = directory.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid():
        raise RuntimeError(f'Thumbnail cache must be an owned regular directory: {directory}')
    os.chmod(directory, 0o700)
    return directory


def file_digest(path):
    """SHA-256 of the painting bytes; sidecars usually supply this already."""
    digest = hashlib.sha256()
    with open(path, 'rb') as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


def default_radius(height):
    return max(2, round(height / 8))


def thumbnail_name(digest, height, radius, shape):
    return f'{digest[:32]}-h{int(height)}-r{int(radius)}-{shape}.png'


def rounded_rectangle(context, x, y, width, height, radius):
    radius = max(0, min(radius, width / 2, height / 2))
    context.new_sub_path()
    context.arc(x + width - radius, y + radius, radius, -1.5708, 0)
    context.arc(x + width - radius, y + height - radius, radius, 0, 1.5708)
    context.arc(x + radius, y + height - radius, radius, 1.5708, 3.14159)
    context.arc(x + radius, y + radius, radius, 3.14159, 4.71239)
    context.close_path()


def render(source, destination, height, radius, shape):
    """Scale the painting to the requested height and clip its corners."""
    import gi
    gi.require_version('GdkPixbuf', '2.0')
    gi.require_version('Gdk', '3.0')
    from gi.repository import Gdk, GdkPixbuf
    import cairo
    if shape == 'square':
        pixbuf = GdkPixbuf.Pixbuf.new_from_file(str(source))
        side = min(pixbuf.get_width(), pixbuf.get_height())
        pixbuf = pixbuf.new_subpixbuf((pixbuf.get_width() - side) // 2,
                                      (pixbuf.get_height() - side) // 2, side, side)
        pixbuf = pixbuf.scale_simple(height, height, GdkPixbuf.InterpType.BILINEAR)
    else:
        pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(str(source), -1, height, True)
    if pixbuf is None:
        raise RuntimeError('Painting could not be decoded')
    width, height = pixbuf.get_width(), pixbuf.get_height()
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
    context = cairo.Context(surface)
    rounded_rectangle(context, 0, 0, width, height, radius)
    context.clip()
    Gdk.cairo_set_source_pixbuf(context, pixbuf, 0, 0)
    context.paint()
    surface.flush()
    temporary = destination.with_name(destination.name + f'.{os.getpid()}.tmp')
    try:
        surface.write_to_png(str(temporary))
        os.chmod(temporary, 0o600)
        os.replace(temporary, destination)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def thumbnail(source, height=48, radius=None, digest=None, shape='fit', cache=None):
    """Return the cached thumbnail path for one painting, rendering it if needed.

    `digest` is the painting's SHA-256 when the caller already knows it; the
    file is hashed otherwise. Returns None when the painting cannot be read or
    rendered, so callers fall back to text-only rows.
    """
    try:
        source = Path(source)
        if not source.is_file():
            return None
        if radius is None:
            radius = default_radius(height)
        if not digest:
            digest = file_digest(source)
        directory = cache_directory(cache)
        destination = directory / thumbnail_name(digest, height, radius, shape)
        if destination.is_file() and destination.stat().st_size > 0:
            return destination
        render(source, destination, int(height), int(radius), shape)
        return destination
    except Exception:  # noqa: BLE001 - any decode or filesystem failure means "no image"
        return None


def cached(source, height=48, radius=None, digest=None, shape='fit', cache=None):
    """The thumbnail path only if it already exists; never renders."""
    try:
        if radius is None:
            radius = default_radius(height)
        if not digest:
            digest = file_digest(source)
        destination = cache_directory(cache) / thumbnail_name(digest, height, radius, shape)
        return destination if destination.is_file() and destination.stat().st_size > 0 else None
    except Exception:  # noqa: BLE001
        return None


def warm(sources, height=48, radius=None, shape='fit', cache=None):
    """Render thumbnails for many paintings; returns the number rendered."""
    rendered = 0
    for source in sources:
        path = Path(source)
        if thumbnail(path, height=height, radius=radius, shape=shape, cache=cache) is not None:
            rendered += 1
    return rendered


def icon_name(path):
    """The icon-theme name Fuzzel resolves back to this thumbnail file."""
    return Path(path).stem


def desktop_icon_theme(config=None):
    """The GTK icon theme the desktop selected, so the private theme inherits it."""
    if config is None:
        base = os.environ.get('XDG_CONFIG_HOME') or str(Path.home() / '.config')
        config = Path(base) / 'gtk-3.0' / 'settings.ini'
    parser = configparser.ConfigParser(interpolation=None)
    try:
        parser.read(config)
        name = parser.get('Settings', 'gtk-icon-theme-name', fallback='').strip()
    except (configparser.Error, OSError):
        name = ''
    return name or None


def icon_theme(cache=None, data=None, inherits=None):
    """Ensure the private icon theme exposes the cache; returns the theme name.

    The theme is one `index.theme` plus a `thumbnails` link to the cache
    directory, so Fuzzel resolves `icon_name(path)` for any cached thumbnail.
    """
    directory = cache_directory(cache)
    if data is None:
        data = os.environ.get('XDG_DATA_HOME') or str(Path.home() / '.local/share')
    theme = Path(data) / 'icons' / THEME
    theme.mkdir(parents=True, exist_ok=True)
    link = theme / 'thumbnails'
    if link.is_symlink():
        if link.resolve() != directory.resolve():
            link.unlink()
    elif link.exists():
        raise RuntimeError(f'{link} exists and is not the thumbnail cache link')
    if not link.is_symlink():
        temporary = theme / f'.thumbnails.{os.getpid()}'
        temporary.symlink_to(directory)
        os.replace(temporary, link)
    parents = []
    for name in list(inherits or [desktop_icon_theme()]) + list(FALLBACK_THEMES):
        if name and name != THEME and name not in parents:
            parents.append(name)
    index = (f'[Icon Theme]\nName={THEME}\nComment=Cached Ghost Gallery painting thumbnails\n'
             f'Inherits={",".join(parents)}\nDirectories=thumbnails\n\n'
             '[thumbnails]\nSize=96\nType=Scalable\nMinSize=16\nMaxSize=512\nContext=Applications\n')
    index_path = theme / 'index.theme'
    try:
        current = index_path.read_text()
    except OSError:
        current = None
    if current != index:
        temporary = theme / f'.index.{os.getpid()}.tmp'
        temporary.write_text(index)
        os.replace(temporary, index_path)
    return THEME


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sources', nargs='+', type=Path)
    parser.add_argument('--height', type=int, default=48)
    parser.add_argument('--radius', type=int)
    parser.add_argument('--shape', choices=['fit', 'square'], default='fit')
    parser.add_argument('--quiet', action='store_true', help='render without printing paths')
    parser.add_argument('--icon-theme', action='store_true',
                        help='also ensure the private icon theme exposes the cache')
    args = parser.parse_args(argv)
    if args.icon_theme:
        icon_theme()
    missing = 0
    for source in args.sources:
        path = thumbnail(source, height=args.height, radius=args.radius, shape=args.shape)
        if path is None:
            missing += 1
        elif not args.quiet:
            print(path)
    return 1 if missing and missing == len(args.sources) else 0


if __name__ == '__main__':
    sys.exit(main())
