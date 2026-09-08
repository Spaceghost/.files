"""Pure logic for the Ghost Planet GRUB theme: PF2 fonts, theme.txt, GRUB keys.

Everything here is side-effect free so it can be unit tested. The generator
(alpine/bin/build-grub-theme) renders the artwork and fonts around these
helpers; the root-only installer (alpine/bin/install-boot-console) copies the
result to /boot and edits /etc/default/grub through `rewrite_grub_keys`.

Why a font compiler lives here: GRUB draws menus with its own bitmap font
format, PF2, and `grub-mkfont` is not packaged for this machine. The stock
`unicode.pf2` is a 16-pixel font, which is unreadable on a 2880x1800 panel,
so `build_pf2` writes the format directly from glyph bitmaps rendered by the
generator. `parse_pf2` reads a file back so the tests can prove the writer
round-trips and the installer can check a font before trusting it.

PF2 layout, from GRUB's font.c and util/grub-mkfont.c:

    "FILE" 00 00 00 04 "PFF2"      magic
    "NAME" <len> <utf8 name> 00    font name, quoted in theme.txt
    "FAMI" ... "WEIG" ... "SLAN"   family, weight, slant
    "PTSZ" 00 02 <u16>             point size
    "MAXW" "MAXH" "ASCE" "DESC"    u16 metrics
    "CHIX" <len> <entries>         9 bytes each: u32 code, u8 flags, u32 offset
    "DATA" FF FF FF FF <glyphs>    the rest of the file

Each glyph at its offset is five big-endian 16-bit fields (width, height,
signed x offset, signed y offset, device width) followed by a one-bit-per-pixel
bitmap, most significant bit first, packed as a continuous stream with no
per-row padding. The y offset is the distance from the baseline up to the
bottom of the bitmap, so descenders carry a negative value.
"""
import re
import struct

PF2_MAGIC = b'PFF2'
CHIX_ENTRY = struct.Struct('>IBI')
GLYPH_HEADER = struct.Struct('>HHhhH')
DATA_SENTINEL = 0xFFFFFFFF
# GRUB reads the theme from the boot partition; keep the name free of spaces so
# the generated `set theme=` path never needs quoting.
THEME_DIRECTORY = 'ghost-planet'
THEME_FILE = 'theme.txt'
# 00_header globs "$themedir"/*.pf2 and "$themedir"/f/*.pf2 for `loadfont`, so
# the fonts have to sit beside theme.txt rather than in a "fonts" subdirectory.
FONT_SUFFIX = '.pf2'
MANAGED_KEYS = ('GRUB_TIMEOUT', 'GRUB_TIMEOUT_STYLE', 'GRUB_THEME', 'GRUB_GFXMODE',
                'GRUB_GFXPAYLOAD_LINUX')
COMPONENT_PATTERN = re.compile(r'^\+\s*([a-z_]+)\s*\{', re.MULTILINE)
REQUIRED_COMPONENTS = ('boot_menu', 'label', 'progress_bar')
REQUIRED_GLOBALS = ('desktop-image', 'desktop-color', 'terminal-font')


def section(name, payload):
    """One PF2 section: four-character name, big-endian length, payload."""
    if len(name) != 4:
        raise ValueError('a PF2 section name is four characters: ' + repr(name))
    return name.encode('ascii') + struct.pack('>I', len(payload)) + payload


def string_section(name, value):
    return section(name, value.encode('utf-8') + b'\0')


def short_section(name, value):
    if not 0 <= value <= 0xFFFF:
        raise ValueError('%s does not fit in sixteen bits: %r' % (name, value))
    return section(name, struct.pack('>H', value))


def pack_bitmap(rows):
    """Pack rows of booleans into GRUB's continuous most-significant-bit stream."""
    bits = bytearray()
    accumulator = 0
    count = 0
    for row in rows:
        for pixel in row:
            accumulator = (accumulator << 1) | (1 if pixel else 0)
            count += 1
            if count == 8:
                bits.append(accumulator)
                accumulator, count = 0, 0
    if count:
        bits.append(accumulator << (8 - count))
    return bytes(bits)


def unpack_bitmap(data, width, height):
    """The inverse of pack_bitmap, for the round-trip tests."""
    rows = []
    index = 0
    for _ in range(height):
        row = []
        for _ in range(width):
            byte = data[index // 8] if index // 8 < len(data) else 0
            row.append(bool(byte & (0x80 >> (index % 8))))
            index += 1
        rows.append(row)
    return rows


def glyph_blob(glyph):
    """A glyph's five metrics and its bitmap, as they appear in the DATA section."""
    for key in ('code', 'width', 'height', 'x_ofs', 'y_ofs', 'device_width', 'bitmap'):
        if key not in glyph:
            raise ValueError('glyph is missing ' + key)
    expected = (glyph['width'] * glyph['height'] + 7) // 8
    if len(glyph['bitmap']) != expected:
        raise ValueError('glyph %r bitmap is %d bytes, expected %d'
                         % (glyph['code'], len(glyph['bitmap']), expected))
    header = GLYPH_HEADER.pack(glyph['width'], glyph['height'], glyph['x_ofs'],
                               glyph['y_ofs'], glyph['device_width'])
    return header + glyph['bitmap']


def build_pf2(glyphs, name, family, point_size, ascent, descent,
              weight='normal', slant='normal'):
    """Serialise glyphs into a complete PF2 font file."""
    ordered = sorted(glyphs, key=lambda glyph: glyph['code'])
    codes = [glyph['code'] for glyph in ordered]
    if len(set(codes)) != len(codes):
        raise ValueError('the same code point appears twice in the font')
    if not ordered:
        raise ValueError('a PF2 font needs at least one glyph')
    blobs = [glyph_blob(glyph) for glyph in ordered]
    header = b''.join([
        section('FILE', PF2_MAGIC),
        string_section('NAME', name),
        string_section('FAMI', family),
        string_section('WEIG', weight),
        string_section('SLAN', slant),
        short_section('PTSZ', point_size),
        short_section('MAXW', max(glyph['width'] for glyph in ordered)),
        short_section('MAXH', max(glyph['height'] for glyph in ordered)),
        short_section('ASCE', ascent),
        short_section('DESC', descent),
    ])
    # The character index stores absolute file offsets, so its own size and the
    # eight-byte DATA header have to be counted before the first glyph lands.
    index_length = CHIX_ENTRY.size * len(ordered)
    data_start = len(header) + 8 + index_length + 8
    offsets = []
    cursor = data_start
    for blob in blobs:
        offsets.append(cursor)
        cursor += len(blob)
    index = b''.join(CHIX_ENTRY.pack(code, 0, offset) for code, offset in zip(codes, offsets))
    return (header + section('CHIX', index)
            + b'DATA' + struct.pack('>I', DATA_SENTINEL) + b''.join(blobs))


def parse_pf2(data):
    """Read a PF2 file back into its metadata and glyphs."""
    document = {'glyphs': {}}
    cursor = 0
    index = None
    while cursor + 8 <= len(data):
        name = data[cursor:cursor + 4].decode('ascii', 'replace')
        length = struct.unpack('>I', data[cursor + 4:cursor + 8])[0]
        cursor += 8
        if name == 'DATA':
            if length != DATA_SENTINEL:
                raise ValueError('the DATA section must carry the 0xFFFFFFFF sentinel')
            break
        payload = data[cursor:cursor + length]
        if len(payload) != length:
            raise ValueError('section %s is truncated' % name)
        cursor += length
        if name == 'FILE':
            if payload != PF2_MAGIC:
                raise ValueError('not a PF2 font: ' + repr(payload))
        elif name in ('NAME', 'FAMI', 'WEIG', 'SLAN'):
            document[name.lower()] = payload.rstrip(b'\0').decode('utf-8')
        elif name in ('PTSZ', 'MAXW', 'MAXH', 'ASCE', 'DESC'):
            document[name.lower()] = struct.unpack('>H', payload)[0]
        elif name == 'CHIX':
            if length % CHIX_ENTRY.size:
                raise ValueError('the character index is not a whole number of entries')
            index = [CHIX_ENTRY.unpack_from(payload, offset)
                     for offset in range(0, length, CHIX_ENTRY.size)]
    if index is None:
        raise ValueError('the font has no character index')
    for code, flags, offset in index:
        if flags:
            raise ValueError('compressed glyph storage is not supported')
        width, height, x_ofs, y_ofs, device_width = GLYPH_HEADER.unpack_from(data, offset)
        start = offset + GLYPH_HEADER.size
        size = (width * height + 7) // 8
        bitmap = data[start:start + size]
        if len(bitmap) != size:
            raise ValueError('glyph %d is truncated' % code)
        document['glyphs'][code] = {'code': code, 'width': width, 'height': height,
                                    'x_ofs': x_ofs, 'y_ofs': y_ofs,
                                    'device_width': device_width, 'bitmap': bitmap}
    return document


def font_name(family, size, weight='Regular'):
    """The name GRUB looks a font up by, and the string theme.txt has to quote."""
    return '%s %s %d' % (family, weight, size)


def render_theme(spec):
    """Render the theme.txt document from a specification dictionary."""
    lines = ['# Ghost Planet: the Gruvbox GRUB menu. Generated by alpine/bin/build-grub-theme;',
             '# edit that generator and the palette, not this file.']
    for key in sorted(spec['globals']):
        value = spec['globals'][key]
        lines.append('%s: "%s"' % (key, value))
    for component in spec['components']:
        lines.append('')
        lines.append('+ %s {' % component['type'])
        for key in sorted(properties(component)):
            value = properties(component)[key]
            lines.append('    %s = %s' % (key, quote_value(value)))
        lines.append('}')
    return '\n'.join(lines) + '\n'


def properties(component):
    return {key: value for key, value in component.items() if key != 'type'}


def quote_value(value):
    """GRUB accepts bare numbers and percentages; everything else is quoted."""
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if isinstance(value, (int, float)):
        return str(value)
    if re.fullmatch(r'-?\d+%?([+-]\d+)?', str(value)):
        return str(value)
    return '"%s"' % value


def validate_theme(text, fonts=(), images=()):
    """Raise unless the theme names only fonts and images that were shipped."""
    for key in REQUIRED_GLOBALS:
        if not re.search(r'^%s\s*:' % re.escape(key), text, re.MULTILINE):
            raise ValueError('theme.txt is missing the %s global' % key)
    found = set(COMPONENT_PATTERN.findall(text))
    missing = [name for name in REQUIRED_COMPONENTS if name not in found]
    if missing:
        raise ValueError('theme.txt is missing components: ' + ', '.join(missing))
    if text.count('{') != text.count('}'):
        raise ValueError('theme.txt has unbalanced braces')
    names = set(fonts)
    for match in re.finditer(r'(?:^|\s)(?:terminal-font|title-font|font|item_font)\s*[:=]\s*"([^"]+)"',
                             text, re.MULTILINE):
        if names and match.group(1) not in names:
            raise ValueError('theme.txt names an unshipped font: ' + match.group(1))
    available = set(images)
    for match in re.finditer(r'(?:desktop-image|_pixmap_style|bar_style|highlight_style)\s*[:=]\s*"([^"]+)"',
                             text):
        pattern = match.group(1)
        if not available:
            continue
        if '*' in pattern:
            prefix, suffix = pattern.split('*', 1)
            if not any(name.startswith(prefix) and name.endswith(suffix) for name in available):
                raise ValueError('theme.txt names an unshipped pixmap set: ' + pattern)
        elif pattern not in available:
            raise ValueError('theme.txt names an unshipped image: ' + pattern)
    return True


def rewrite_grub_keys(text, values):
    """Return /etc/default/grub with these keys set, every other line intact.

    A key already present is rewritten in place, so the file keeps its order and
    a second run changes nothing. Keys that are absent are appended under one
    managed comment, which keeps the hand-written part of the file recognisable.
    """
    banner = '# Ghost Planet boot menu (managed by alpine/bin/install-boot-console)'
    result = text
    appended = []
    for key in sorted(values):
        value = values[key]
        if not re.fullmatch(r'[A-Z0-9_]+', key):
            raise ValueError('refusing to write a suspicious GRUB key: ' + repr(key))
        rendered = '%s=%s' % (key, shell_quote(value))
        pattern = re.compile(r'^%s=.*$' % re.escape(key), re.MULTILINE)
        matches = pattern.findall(result)
        if len(matches) > 1:
            raise ValueError('%s appears more than once in /etc/default/grub' % key)
        if matches:
            result = pattern.sub(lambda _match, line=rendered: line, result, count=1)
        else:
            appended.append(rendered)
    if appended:
        if banner not in result:
            result = result.rstrip('\n') + '\n\n' + banner + '\n'
        else:
            result = result.rstrip('\n') + '\n'
        result += '\n'.join(appended) + '\n'
    return result


def shell_quote(value):
    """Quote a GRUB default value the way the file already quotes its own."""
    value = str(value)
    if re.fullmatch(r'[A-Za-z0-9_./=:-]+', value):
        return value
    if any(character in value for character in '"\'\\$`'):
        raise ValueError('refusing to write a GRUB value with shell metacharacters')
    return '"%s"' % value


def grub_key_values(text):
    """The managed keys currently set in /etc/default/grub."""
    found = {}
    for key in MANAGED_KEYS:
        match = re.search(r'^%s=(.*)$' % re.escape(key), text, re.MULTILINE)
        if match:
            found[key] = match.group(1).strip('"\'')
    return found


def validate_menu_cfg(generated, theme_path, timeout):
    """Raise unless the generated grub.cfg really shows the themed menu.

    grub-mkconfig indents the timeout inside its `feature_timeout_style` test
    and repeats it in the fallback branch, so every pattern here tolerates
    leading whitespace rather than anchoring hard at the start of the line.
    """
    relative = theme_path.replace('/boot', '', 1)
    if not re.search(r'^\s*set theme=\(\$root\)%s\s*$' % re.escape(relative), generated, re.MULTILINE):
        raise ValueError('grub.cfg does not select the theme at ' + relative)
    if 'insmod gfxmenu' not in generated:
        raise ValueError('grub.cfg does not load the gfxmenu module')
    if 'insmod png' not in generated:
        raise ValueError('grub.cfg does not load the png module for the background')
    if not re.search(r'^\s*terminal_output gfxterm\s*$', generated, re.MULTILINE):
        raise ValueError('grub.cfg does not select the graphical terminal')
    if not re.search(r'^\s*set timeout=%d\s*$' % timeout, generated, re.MULTILINE):
        raise ValueError('grub.cfg does not carry the requested timeout')
    if not re.search(r'^\s*set timeout_style=menu\s*$', generated, re.MULTILINE):
        raise ValueError('grub.cfg does not show the menu during the timeout')
    fonts = re.findall(r'^\s*loadfont \(\$root\)(\S+)\s*$', generated, re.MULTILINE)
    themed = [path for path in fonts if path.startswith(relative.rsplit('/', 1)[0] + '/')]
    if not themed:
        raise ValueError('grub.cfg loads no font from the theme directory')
    return {'fonts': themed}
