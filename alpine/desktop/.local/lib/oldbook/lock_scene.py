"""Compose the Oldbook lock scene: a blurred painting, a caption card and locker arguments.

The scene is rendered once per painting and screen geometry into a private
cache; the caption card is rendered for every lock because the Scripture
selection changes hourly. Both are plain PNG files that swaylock-effects
composes over its screenshot, so the desktop dissolves into the scene.
"""
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys

SCENE_VERSION = 1
DEFAULT_GEOMETRY = (2880, 1800, 2)
CAPTION_WIDTH = 560          # logical pixels
CAPTION_MARGIN = 44          # logical pixels from the lower-left corner
INDICATOR_RADIUS = 172       # logical pixels
INDICATOR_THICKNESS = 8
FALLBACK_DATE = '%A · %-d %B'
CLOCK_FONT = 'Inter Display SemiBold'
CAPTION_FONT = 'Inter'
MONO_FONT = 'JetBrainsMono Nerd Font'
GHOST_GLYPH = '\U000f02a0'
SCRIPTURE_GLYPH = '\U000f00ba'


def _smoothstep(edge0, edge1, value):
    import numpy as np
    t = np.clip((value - edge0) / (edge1 - edge0), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def _box_blur(image, radius, passes=3):
    """Separable box blur repeated three times: a close, fast gaussian."""
    import numpy as np
    width = 2 * radius + 1
    for _ in range(passes):
        for axis in (1, 0):
            pad = [(0, 0), (0, 0), (0, 0)]
            pad[axis] = (radius + 1, radius)
            padded = np.pad(image, pad, mode='edge')
            summed = np.cumsum(padded, axis=axis, dtype=np.float32)
            if axis == 1:
                image = (summed[:, width:, :] - summed[:, :-width, :]) / width
            else:
                image = (summed[width:, :, :] - summed[:-width, :, :]) / width
    return image


def _hex_rgb(color):
    color = color.lstrip('#')
    return tuple(int(color[index:index + 2], 16) / 255.0 for index in (0, 2, 4))


def private_directory(path):
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise RuntimeError(f'Lock scene directory must be an owned private directory: {path}')
    return path


def cache_directory():
    override = os.environ.get('OLDBOOK_LOCK_CACHE')
    base = Path(override) if override else Path(os.environ.get('XDG_CACHE_HOME', Path.home() / '.cache')) / 'oldbook/lock'
    return private_directory(base)


def output_geometry(environment=None):
    """Physical width, height and integer scale of the first powered output."""
    try:
        result = subprocess.run(['swaymsg', '-r', '-t', 'get_outputs'], capture_output=True,
                                text=True, timeout=2, check=True, env=environment)
        outputs = json.loads(result.stdout)
    except (OSError, ValueError, subprocess.SubprocessError):
        return DEFAULT_GEOMETRY
    candidates = [output for output in outputs if output.get('active')] or outputs
    for output in sorted(candidates, key=lambda item: not item.get('focused')):
        mode = output.get('current_mode') or {}
        width, height = mode.get('width'), mode.get('height')
        scale = output.get('scale') or 1
        if width and height:
            return int(width), int(height), max(1, int(round(scale)))
    return DEFAULT_GEOMETRY


def current_painting(home=None):
    home = home or Path.home()
    for name in ('current-wallpaper.png', 'wallpaper.png'):
        candidate = home / '.local/share/oldbook' / name
        if candidate.is_file():
            return candidate.resolve()
    return None


def painting_story(painting, home=None):
    """Title and one line of story for the current painting, if they are known."""
    home = home or Path.home()
    sources = [home / '.local/state/oldbook/wallpaper/state.json']
    if painting is not None:
        sources.append(painting.with_suffix('.json'))
    for source in sources:
        try:
            entry = json.loads(source.read_text())
        except (OSError, ValueError):
            continue
        if not isinstance(entry, dict) or not entry.get('title'):
            continue
        recorded = entry.get('file')
        if painting is not None and source.name == 'state.json' and recorded:
            if Path(recorded).name != painting.name:
                continue
        return {'title': str(entry['title']), 'description': str(entry.get('description') or '')}
    return None


def scripture_line():
    """The hour's Scripture, read from the durable history without advancing it."""
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import scripture_history
        record = scripture_history.current()
    except Exception:  # noqa: BLE001 - the lock must never depend on the reading library
        return None
    if not record:
        return None
    document = record.get('document') or {}
    reference = document.get('reference')
    text = document.get('text')
    if not reference or not isinstance(text, str):
        return None
    return {'reference': str(reference), 'text': text.strip(), 'edition': document.get('edition') or ''}


def first_sentence(text, limit=150):
    text = ' '.join(str(text).split())
    for stop in ('. ', '; ', ': '):
        index = text.find(stop)
        if 0 < index < limit:
            return text[:index + 1].strip()
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(' ', 1)[0]
    return cut.rstrip('.,;: ') + '…'


def painting_key(painting):
    digest = hashlib.sha256()
    with painting.open('rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()[:20]


def render_background(painting, geometry, palette, cache=None):
    """Blur, darken and vignette the painting for the output; cached per painting."""
    width, height, scale = geometry
    cache = cache or cache_directory()
    target = cache / f'{painting_key(painting)}-{width}x{height}-v{SCENE_VERSION}.png'
    if target.is_file():
        return target
    # Imported only on a cache miss: numpy and GdkPixbuf cost more to load than
    # the whole warm lock path.
    import numpy as np
    import gi
    gi.require_version('GdkPixbuf', '2.0')
    from gi.repository import GdkPixbuf, GLib

    work_w, work_h = max(320, width // 2), max(200, height // 2)
    source = GdkPixbuf.Pixbuf.new_from_file(str(painting))
    ratio = max(work_w / source.get_width(), work_h / source.get_height())
    covered = source.scale_simple(max(work_w, int(source.get_width() * ratio + 0.5)),
                                  max(work_h, int(source.get_height() * ratio + 0.5)),
                                  GdkPixbuf.InterpType.BILINEAR)
    crop = covered.new_subpixbuf((covered.get_width() - work_w) // 2,
                                 (covered.get_height() - work_h) // 2, work_w, work_h)
    channels = crop.get_n_channels()
    rows = np.frombuffer(crop.get_pixels(), dtype=np.uint8)
    stride = crop.get_rowstride()
    image = np.lib.stride_tricks.as_strided(rows, shape=(work_h, work_w, channels),
                                            strides=(stride, channels, 1))[:, :, :3]
    image = image.astype(np.float32) / 255.0
    image = _box_blur(image, max(6, round(work_w / 110)))
    luminance = image @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
    image = image * 0.86 + luminance[:, :, None] * 0.14
    tint = np.array(_hex_rgb(palette.get('background', '#282828')), dtype=np.float32)
    image = image * 0.88 + tint * 0.12
    ys = (np.arange(work_h, dtype=np.float32) / max(1, work_h - 1))
    xs = (np.arange(work_w, dtype=np.float32) / max(1, work_w - 1))
    distance = np.sqrt(((xs * 2 - 1)[None, :]) ** 2 + ((ys * 2 - 1)[:, None]) ** 2)
    vignette = (1.0 - 0.52 * _smoothstep(0.42, 1.38, distance))[:, :, None]
    scrim = (1.0 - 0.30 * _smoothstep(0.52, 1.0, ys))[:, None, None]
    image = np.clip(image * 0.68 * vignette * scrim, 0.0, 1.0)
    data = (image * 255.0 + 0.5).astype(np.uint8).tobytes()
    small = GdkPixbuf.Pixbuf.new_from_bytes(GLib.Bytes.new(data), GdkPixbuf.Colorspace.RGB,
                                            False, 8, work_w, work_h, work_w * 3)
    # Half resolution is invisible under this much blur; the locker scales it
    # bilinearly, and the file loads in a fraction of the time.
    temporary = target.with_name(target.name + f'.{os.getpid()}.tmp')
    small.savev(str(temporary), 'png', ['compression'], ['1'])
    os.chmod(temporary, 0o600)
    temporary.replace(target)
    for stale in sorted(cache.glob('*.png'), key=lambda item: item.stat().st_mtime)[:-6]:
        stale.unlink(missing_ok=True)
    return target


def caption_key(story, scripture, palette, scale, width):
    content = json.dumps([story, scripture, palette, scale, width, SCENE_VERSION], sort_keys=True)
    return hashlib.sha256(content.encode()).hexdigest()[:20]


def render_caption(story, scripture, palette, scale, target, width=CAPTION_WIDTH):
    """Render the lower-left caption card as an ARGB PNG at the output scale.

    The card is cached beside its target by content, so an unchanged hour and
    painting skip Pango entirely on the next lock.
    """
    target = Path(target)
    stamp = target.with_suffix('.key')
    try:
        if target.is_file() and stamp.read_text().split('\n')[0] == caption_key(story, scripture, palette, scale, width):
            return target, width, int(stamp.read_text().split('\n')[1])
    except (OSError, ValueError, IndexError):
        pass
    import cairo
    import gi
    gi.require_version('Pango', '1.0')
    gi.require_version('PangoCairo', '1.0')
    from gi.repository import Pango, PangoCairo

    def escape(text):
        return (str(text).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;'))

    def color(name):
        return palette.get(name, '#ebdbb2')

    padding, gap, radius = 26, 9, 16
    inner = width - 2 * padding
    blocks = []
    if story:
        blocks.append(('eyebrow', f'<span foreground="{color("accent")}" letter_spacing="2200" '
                                  f'font_family="{MONO_FONT}" size="8500" weight="600">NOW SHOWING · GHOST GALLERY</span>'))
        blocks.append(('title', f'<span foreground="{color("foreground")}" font_family="{CAPTION_FONT}" '
                                f'size="17500" weight="600">{escape(story["title"])}</span>'))
        if story.get('description'):
            blocks.append(('story', f'<span foreground="{color("muted")}" font_family="{CAPTION_FONT}" '
                                    f'size="11000">{escape(first_sentence(story["description"]))}</span>'))
    if scripture:
        if blocks:
            blocks.append(('rule', None))
        edition = f' · {escape(scripture["edition"])}' if scripture.get('edition') else ''
        blocks.append(('reference', f'<span foreground="{color("accent")}" font_family="{MONO_FONT}" '
                                    f'size="10500" weight="600">{SCRIPTURE_GLYPH}  {escape(scripture["reference"])}'
                                    f'</span><span foreground="{color("muted")}" font_family="{MONO_FONT}" '
                                    f'size="9500">{edition}</span>'))
        blocks.append(('verse', f'<span foreground="{color("foreground")}" font_family="{CAPTION_FONT}" '
                                f'size="11000" style="italic">{escape(first_sentence(scripture["text"], 190))}</span>'))
    if blocks:
        blocks.append(('rule', None))
    blocks.append(('footer', f'<span foreground="{color("accent")}" font_family="{MONO_FONT}" size="9500">'
                             f'{GHOST_GLYPH}</span><span foreground="{color("muted")}" font_family="{MONO_FONT}" '
                             f'letter_spacing="2000" size="8500">  GHOST PLANET · COAST TO COAST</span>'))

    def layouts(context):
        result = []
        for kind, markup in blocks:
            if kind == 'rule':
                result.append((kind, None, 1))
                continue
            layout = PangoCairo.create_layout(context)
            layout.set_width(inner * Pango.SCALE)
            layout.set_wrap(Pango.WrapMode.WORD_CHAR)
            layout.set_ellipsize(Pango.EllipsizeMode.END)
            layout.set_height(-(3 if kind in ('story', 'verse') else 2) * Pango.SCALE)
            layout.set_markup(markup, -1)
            _, logical = layout.get_pixel_extents()
            result.append((kind, layout, logical.height))
        return result

    probe = cairo.ImageSurface(cairo.FORMAT_ARGB32, 4, 4)
    measured = layouts(cairo.Context(probe))
    height = 2 * padding + sum(item[2] for item in measured) + gap * (len(measured) - 1)
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, int(width * scale), int(height * scale))
    context = cairo.Context(surface)
    context.scale(scale, scale)
    # Card: a translucent charcoal slab with a soft edge, no outline pixel.
    context.new_sub_path()
    context.arc(width - radius, radius, radius, -1.5708, 0)
    context.arc(width - radius, height - radius, radius, 0, 1.5708)
    context.arc(radius, height - radius, radius, 1.5708, 3.14159)
    context.arc(radius, radius, radius, 3.14159, 4.71239)
    context.close_path()
    red, green, blue = _hex_rgb(palette.get('background_hard', '#1d2021'))
    context.set_source_rgba(red, green, blue, 0.70)
    context.fill()
    y = padding
    for kind, layout, block_height in layouts(context):
        if kind == 'rule':
            red, green, blue = _hex_rgb(color('accent'))
            context.set_source_rgba(red, green, blue, 0.55)
            context.rectangle(padding, y, 56, 1)
            context.fill()
        else:
            context.move_to(padding, y)
            PangoCairo.show_layout(context, layout)
        y += block_height + gap
    surface.flush()
    temporary = Path(str(target) + f'.{os.getpid()}.tmp')
    surface.write_to_png(str(temporary))
    os.chmod(temporary, 0o600)
    temporary.replace(target)
    stamp.write_text(f'{caption_key(story, scripture, palette, scale, width)}\n{height}\n')
    os.chmod(stamp, 0o600)
    return target, width, height


def indicator_arguments(palette, geometry):
    """Clock inside an idle-invisible ring; the amber ring returns while typing."""
    width, height, scale = geometry
    logical_w, logical_h = width // scale, height // scale

    def color(name, alpha='ff'):
        return palette[name].lstrip('#') + alpha

    clear = '00000000'
    return ['--clock', '--indicator', '--timestr', '%H:%M', '--datestr', FALLBACK_DATE,
            '--indicator-radius', str(INDICATOR_RADIUS), '--indicator-thickness', str(INDICATOR_THICKNESS),
            '--indicator-x-position', str(logical_w // 2),
            '--indicator-y-position', str(int(logical_h * 0.40)),
            '--font', CLOCK_FONT, '--font-size', str(int(INDICATOR_RADIUS * scale * 0.37)),
            '--ring-idle-color', clear, '--inside-idle-color', clear, '--line-idle-color', clear,
            '--text-idle-color', color('foreground'),
            '--ring-color', color('accent'), '--inside-color', color('background_hard', 'b8'),
            '--line-color', clear, '--text-color', color('foreground'),
            '--ring-clear-color', color('border'), '--inside-clear-color', color('surface', 'b8'),
            '--line-clear-color', clear, '--text-clear-color', color('foreground'),
            '--ring-caps-lock-color', color('accent'), '--inside-caps-lock-color', color('surface', 'b8'),
            '--line-caps-lock-color', clear, '--text-caps-lock-color', color('accent'),
            '--ring-ver-color', color('muted'), '--inside-ver-color', color('surface', 'b8'),
            '--line-ver-color', clear, '--text-ver-color', color('muted'),
            '--ring-wrong-color', color('foreground'), '--inside-wrong-color', color('surface', 'b8'),
            '--line-wrong-color', clear, '--text-wrong-color', color('foreground'),
            '--key-hl-color', color('accent'), '--bs-hl-color', color('foreground'),
            '--caps-lock-key-hl-color', color('accent'), '--caps-lock-bs-hl-color', color('muted'),
            '--separator-color', clear, '--layout-bg-color', color('background', 'ee'),
            '--layout-border-color', color('accent'), '--layout-text-color', color('foreground'),
            '--text-clear', 'Cleared', '--text-ver', 'Checking…', '--text-wrong', 'Not tonight',
            '--text-caps-lock', 'Caps Lock', '--ignore-empty-password', '--hide-keyboard-layout']


def scene_arguments(ready_fd, palette, geometry, runtime, home=None, cache=None):
    """Complete swaylock-effects arguments for the current painting and hour."""
    width, height, scale = geometry
    painting = current_painting(home)
    # The desktop screenshot is the fade source; effects run on it at buffer
    # resolution, so compose geometry below is percentages or physical pixels.
    args = ['--fade-in', '0.4', '--screenshots', '-c', palette['background'].lstrip('#')]
    if ready_fd is not None:
        args = ['-R', str(ready_fd)] + args
    if painting is not None:
        background = render_background(painting, geometry, palette, cache)
        args += ['--effect-compose', f'0,0;100%x100%;northwest;{background}']
    story = painting_story(painting, home)
    scripture = scripture_line()
    caption_dir = private_directory(Path(runtime) / 'oldbook-screen-lock')
    caption, caption_w, _ = render_caption(story, scripture, palette, scale, caption_dir / 'caption.png')
    margin = CAPTION_MARGIN * scale
    args += ['--effect-compose', f'{margin},-{margin};{caption_w * scale}x-1;southwest;{caption}']
    return args + indicator_arguments(palette, geometry)
