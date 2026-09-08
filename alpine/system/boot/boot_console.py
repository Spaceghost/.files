"""Pure logic for the Gruvbox boot console: kernel parameters, GRUB edits, banners.

Everything here is side-effect free so it can be unit tested. The root-only
installer (alpine/bin/install-boot-console) does the file writes and command
execution around these helpers.

Sources of truth versioned beside this module:

- console-palette.json: the sixteen VT colours, the kernel font and the default
  attribute the console starts with.
- issue.template: the /etc/issue banner printed by the rescue gettys. It uses
  colour tokens so the versioned text stays readable; the rendered file carries
  raw ESC bytes.

The LUKS passphrase prompt is printed by the initramfs init on the kernel
console, so the same vt.default_* palette and fbcon font colour it from the
first frame; nothing in the initramfs has to change for that.
"""
import json
import re
import shlex

MANAGED_PREFIXES = ('vt.default_red=', 'vt.default_grn=', 'vt.default_blu=',
                    'vt.color=', 'fbcon=font:')
CMDLINE_KEY = 'GRUB_CMDLINE_LINUX_DEFAULT'
ISSUE_TOKENS = {
    # Sixteen-colour SGR codes, so the banner uses the kernel palette itself.
    'reset': '\033[0m',
    'amber': '\033[1;93m',
    'cream': '\033[97m',
    'muted': '\033[37m',
    'grey': '\033[90m',
    'aqua': '\033[96m',
    'red': '\033[91m',
}
# BusyBox getty expands these (libbb/login.c); anything else after a backslash
# or a percent sign is printed literally, which would look like a typo.
ISSUE_ESCAPES = set('snhrvmDodtl')
GHOST_TITLE_SUFFIX = ' (Ghost Planet initramfs)'
CUSTOM_BEGIN = '# BEGIN oldbook-boot-console ghost initramfs (managed by alpine/bin/install-boot-console)'
CUSTOM_END = '# END oldbook-boot-console ghost initramfs'


def load_palette(text):
    """Validate the palette document and return it as a dict."""
    document = json.loads(text)
    colors = document.get('colors')
    if not isinstance(colors, list) or len(colors) != 16:
        raise ValueError('console palette needs exactly sixteen colours')
    for value in colors:
        if not re.fullmatch(r'#[0-9a-fA-F]{6}', value):
            raise ValueError('console colour must be #rrggbb: ' + repr(value))
    font = document.get('font', '')
    if not re.fullmatch(r'[A-Za-z0-9x]+', font):
        raise ValueError('console font name must be a kernel built-in font name')
    for key in ('default_foreground', 'default_background'):
        index = document.get(key)
        if not isinstance(index, int) or not 0 <= index <= 15:
            raise ValueError(key + ' must be a palette index from 0 to 15')
    return document


def channel(colors, offset):
    return ','.join(str(int(value[offset:offset + 2], 16)) for value in colors)


def kernel_parameters(palette):
    """Kernel command-line tokens, in the order they are appended."""
    colors = palette['colors']
    attribute = (palette['default_background'] << 4) | palette['default_foreground']
    return [
        'vt.default_red=' + channel(colors, 1),
        'vt.default_grn=' + channel(colors, 3),
        'vt.default_blu=' + channel(colors, 5),
        'vt.color=0x%02X' % attribute,
        'fbcon=font:' + palette['font'],
    ]


def is_managed(token):
    return token.startswith(MANAGED_PREFIXES)


def rewrite_grub_default(text, parameters):
    """Return /etc/default/grub with the managed tokens replaced, others intact."""
    pattern = re.compile(r'^(' + CMDLINE_KEY + r')=(.*)$', re.MULTILINE)
    matches = list(pattern.finditer(text))
    if len(matches) != 1:
        raise ValueError('expected exactly one %s line in /etc/default/grub' % CMDLINE_KEY)
    match = matches[0]
    raw = match.group(2)
    if raw.startswith('"') and raw.endswith('"') and len(raw) >= 2:
        quote, body = '"', raw[1:-1]
    elif raw.startswith("'") and raw.endswith("'") and len(raw) >= 2:
        quote, body = "'", raw[1:-1]
    else:
        quote, body = '"', raw
    if any(character in body for character in '"\'\\$`'):
        raise ValueError('refusing to rewrite a %s value with shell quoting' % CMDLINE_KEY)
    tokens = [token for token in body.split() if not is_managed(token)]
    tokens.extend(parameters)
    replacement = '%s=%s%s%s' % (CMDLINE_KEY, quote, ' '.join(tokens), quote)
    return text[:match.start()] + replacement + text[match.end():]


def cmdline_tokens(text):
    """Tokens of the single GRUB_CMDLINE_LINUX_DEFAULT line."""
    pattern = re.compile(r'^' + CMDLINE_KEY + r'=(.*)$', re.MULTILINE)
    matches = pattern.findall(text)
    if len(matches) != 1:
        raise ValueError('expected exactly one %s line' % CMDLINE_KEY)
    words = shlex.split(matches[0])
    return ' '.join(words).split()


def render_issue(template, tokens=ISSUE_TOKENS):
    """Render the getty banner; returns bytes with raw escape sequences."""
    if '%' in template:
        raise ValueError('/etc/issue must not contain a percent sign: getty treats it as an escape')
    for escape in re.findall(r'\\(.)', template):
        if escape not in ISSUE_ESCAPES:
            raise ValueError('unsupported getty escape: \\' + escape)
    rendered = template
    for name in re.findall(r'\{([a-z]+)\}', template):
        if name not in tokens:
            raise ValueError('unknown banner colour token: ' + name)
    for name, sequence in tokens.items():
        rendered = rendered.replace('{' + name + '}', sequence)
    if '{' in rendered or '}' in rendered:
        raise ValueError('banner still contains braces after rendering')
    return rendered.encode('ascii')


def sections(cfg):
    """Map the grub.cfg generator sections to their text."""
    found = {}
    for match in re.finditer(r'^### BEGIN (\S+) ###\n(.*?)^### END \1 ###$', cfg, re.MULTILINE | re.DOTALL):
        found[match.group(1)] = match.group(2)
    return found


def menuentries(text):
    """List (title, block) for each top-level menuentry in the text."""
    entries = []
    for match in re.finditer(r"^menuentry '((?:[^'\\]|\\.)*)'[^\n]*\{\n(.*?)^\}$", text,
                             re.MULTILINE | re.DOTALL):
        entries.append((match.group(1), match.group(0)))
    return entries


def entry_lines(block):
    """The linux and initrd lines of a menuentry, as (path, tokens) and path."""
    linux = re.search(r'^\s*linux\s+(\S+)\s*(.*)$', block, re.MULTILINE)
    initrd = re.search(r'^\s*initrd\s+(\S+)\s*$', block, re.MULTILINE)
    if not linux or not initrd:
        raise ValueError('menuentry lacks a linux or initrd line')
    return linux.group(1), linux.group(2).split(), initrd.group(1)


def stock_entry(cfg):
    """The first entry generated by 10_linux: the entry the machine boots today."""
    section = sections(cfg).get('/etc/grub.d/10_linux')
    if section is None:
        raise ValueError('grub.cfg has no 10_linux section')
    entries = menuentries(section)
    if not entries:
        raise ValueError('grub.cfg 10_linux section has no menuentry')
    return entries[0]


def ghost_menuentry(cfg, stock_initrd='/initramfs-lts', ghost_initrd='/initramfs-lts-ghost',
                    suffix=GHOST_TITLE_SUFFIX):
    """Derive the non-default banner entry from the stock entry text."""
    title, block = stock_entry(cfg)
    _kernel, _tokens, initrd = entry_lines(block)
    if initrd != stock_initrd:
        raise ValueError('stock entry boots %s, not %s' % (initrd, stock_initrd))
    if title.endswith(suffix):
        raise ValueError('stock entry already carries the ghost suffix')
    head, rest = block.split('{\n', 1)
    head = head.replace("menuentry '%s'" % title, "menuentry '%s%s'" % (title, suffix), 1)
    head = re.sub(r"'(gnulinux-[^']*)'", lambda m: "'%s-ghost'" % m.group(1), head, count=1)
    rest = re.sub(r'^(\s*initrd\s+)' + re.escape(stock_initrd) + r'\s*$',
                  lambda m: m.group(1) + ghost_initrd, rest, count=1, flags=re.MULTILINE)
    return head + '{\n' + rest


def render_custom_fragment(existing, entry):
    """Replace or append the managed block in /etc/grub.d/40_custom."""
    if not existing.startswith('#!/bin/sh\nexec tail -n +3 $0\n'):
        raise ValueError('40_custom does not start with the stock exec tail header')
    block = CUSTOM_BEGIN + '\n' + entry.rstrip('\n') + '\n' + CUSTOM_END + '\n'
    pattern = re.compile(re.escape(CUSTOM_BEGIN) + r'\n.*?' + re.escape(CUSTOM_END) + r'\n', re.DOTALL)
    if pattern.search(existing):
        return pattern.sub(lambda _m: block, existing, count=1)
    return existing.rstrip('\n') + '\n' + block


def remove_custom_fragment(existing):
    pattern = re.compile(re.escape(CUSTOM_BEGIN) + r'\n.*?' + re.escape(CUSTOM_END) + r'\n', re.DOTALL)
    return pattern.sub('', existing, count=1)


def validate_generated_cfg(previous, generated, parameters, ghost_initrd=None,
                           stock_initrd='/initramfs-lts', suffix=GHOST_TITLE_SUFFIX):
    """Raise unless the new grub.cfg boots exactly what the old one booted, plus the palette."""
    old_title, old_block = stock_entry(previous)
    new_title, new_block = stock_entry(generated)
    if old_title != new_title:
        raise ValueError('stock entry title changed: %r -> %r' % (old_title, new_title))
    old_kernel, old_tokens, old_initrd = entry_lines(old_block)
    new_kernel, new_tokens, new_initrd = entry_lines(new_block)
    if old_kernel != new_kernel:
        raise ValueError('kernel path changed: %s -> %s' % (old_kernel, new_kernel))
    if old_initrd != new_initrd or new_initrd != stock_initrd:
        raise ValueError('initramfs path changed: %s -> %s' % (old_initrd, new_initrd))
    kept = [token for token in old_tokens if not is_managed(token)]
    expected = kept + list(parameters)
    if new_tokens != expected:
        raise ValueError('kernel command line differs from the expected %r: %r' % (expected, new_tokens))
    for name in ('search', 'set root'):
        old_lines = [line for line in old_block.splitlines() if line.strip().startswith(name)]
        new_lines = [line for line in new_block.splitlines() if line.strip().startswith(name)]
        if old_lines != new_lines:
            raise ValueError('boot device lookup changed for ' + name)
    old_default = re.findall(r'^\s*set default=.*$', previous, re.MULTILINE)
    new_default = re.findall(r'^\s*set default=.*$', generated, re.MULTILINE)
    if old_default != new_default:
        raise ValueError('default entry selection changed: %r -> %r' % (old_default, new_default))
    ghosts = [(title, block) for title, block in menuentries(generated) if title.endswith(suffix)]
    if ghost_initrd is None:
        if ghosts:
            raise ValueError('unexpected ghost entry present')
        return
    if len(ghosts) != 1:
        raise ValueError('expected exactly one ghost entry, found %d' % len(ghosts))
    ghost_title, ghost_block = ghosts[0]
    if ghost_title != new_title + suffix:
        raise ValueError('ghost entry title is not derived from the stock entry')
    ghost_kernel, ghost_tokens, ghost_initrd_found = entry_lines(ghost_block)
    if ghost_kernel != new_kernel or ghost_tokens != new_tokens:
        raise ValueError('ghost entry must boot the same kernel and command line')
    if ghost_initrd_found != ghost_initrd:
        raise ValueError('ghost entry boots %s, not %s' % (ghost_initrd_found, ghost_initrd))
    if menuentries(generated)[0][0] != new_title:
        raise ValueError('the stock entry must stay first')


INIT_ANCHOR = '\tebegin "Mounting root"\n'
INIT_BANNER = '''\t# Oldbook: a Gruvbox masthead on the console before the encrypted-root
\t# passphrase prompt that nlplug-findfs/cryptsetup print below. Sixteen-colour
\t# escapes only, so the vt.default_* kernel palette supplies the actual tones.
\tif [ -n "$KOPT_cryptroot" ]; then
\t\tprintf '\\n  \\033[1;93mGHOST PLANET\\033[0m  \\033[37mOldbook - Alpine Linux\\033[0m\\n'
\t\tprintf '  \\033[97mEncrypted root.\\033[0m \\033[37mEnter the passphrase to continue.\\033[0m\\n\\n'
\tfi
'''


def patch_init(stock):
    """Insert the banner exactly once, immediately before the root mount step."""
    if INIT_BANNER in stock:
        raise ValueError('init script already carries the banner')
    if stock.count(INIT_ANCHOR) != 1:
        raise ValueError('expected exactly one "Mounting root" step in the init script')
    return stock.replace(INIT_ANCHOR, INIT_BANNER + INIT_ANCHOR, 1)


def parse_listing(text):
    """Normalise a cpio -t listing to a set of archive-relative names."""
    names = set()
    for line in text.splitlines():
        name = line.strip()
        if name.startswith('./'):
            name = name[2:]
        if name and name != '.':
            names.add(name)
    return names


def compare_listings(stock, ghost):
    """Files the ghost initramfs lacks or adds relative to the stock one."""
    stock, ghost = parse_listing(stock), parse_listing(ghost)
    return {'missing': sorted(stock - ghost), 'extra': sorted(ghost - stock)}
