"""Curated, deliberately partial shortcut profiles for Sway desktops.

Baseline sources, checked 2026-09-07:

* Firefox: https://support.mozilla.org/en-US/kb/keyboard-shortcuts-perform-firefox-tasks-quickly
* Foot: https://codeberg.org/dnkl/foot/src/branch/master/foot.ini
* Neovim: https://neovim.io/doc/user/usr_02.html
* btop: https://github.com/aristocratos/btop/blob/main/src/btop_input.cpp
* mpv: https://mpv.io/manual/master/#keyboard-control
* imv: https://github.com/eXeC64/imv/blob/master/files/imv_config
* Thunar: https://docs.xfce.org/xfce/thunar/4.20/preferences
* zsh: https://zsh.sourceforge.io/Doc/Release/Zsh-Line-Editor.html
* Codex CLI 0.153.4: https://github.com/openai/codex/tree/rust-v0.153.4
  (``codex-rs/tui/src/keymap.rs`` and composer handlers)

Profiles intentionally contain a useful subset. Applications can customize
their bindings, and editor/shell modes can change which entries apply.
"""


PROFILES = {
    'codex': {
        'name': 'Codex',
        'aliases': ('codex', 'codex-cli'),
        'coverage': 'Partial baseline for Codex CLI 0.153.4',
        'rows': (
            ('?', 'Show shortcuts (empty composer)'),
            ('Enter', 'Submit current draft'),
            ('Shift+Enter', 'Insert newline'),
            ('Tab', 'Queue message while a task is running'),
            ('Escape', 'Interrupt active turn'),
            ('Ctrl+T', 'Open transcript'),
            ('/keymap, Enter', 'Browse current Codex keybindings and remappings'),
        ),
    },
    'firefox': {
        'name': 'Firefox',
        'aliases': ('firefox', 'firefox-esr', 'org.mozilla.firefox'),
        'rows': (
            ('Ctrl+L', 'Focus address bar'),
            ('Ctrl+T', 'New tab'),
            ('Ctrl+W', 'Close tab'),
            ('Ctrl+Shift+T', 'Reopen closed tab'),
            ('Ctrl+R', 'Reload page'),
            ('Alt+Left / Alt+Right', 'Back / forward'),
            ('Ctrl+F', 'Find in page'),
            ('Ctrl++ / Ctrl+-', 'Zoom in / out'),
        ),
    },
    'foot': {
        'name': 'Foot',
        'aliases': ('foot', 'footclient'),
        'rows': (
            ('Ctrl+Shift+C', 'Copy'),
            ('Ctrl+Shift+V', 'Paste'),
            ('Ctrl+Shift+R', 'Search scrollback'),
            ('Shift+PageUp / Shift+PageDown', 'Scroll one page'),
            ('Ctrl+Shift+N', 'Open a new terminal'),
        ),
    },
    'nvim': {
        'name': 'Neovim',
        'aliases': ('nvim', 'neovim'),
        'rows': (
            ('i', 'Enter Insert mode'),
            ('Escape', 'Return to Normal mode'),
            ('h / j / k / l', 'Move cursor in Normal mode'),
            (':w, Enter', 'Write file'),
            (':q, Enter', 'Quit'),
            ('/', 'Search forward'),
            ('n / N', 'Next / previous search match'),
            ('u / Ctrl+R', 'Undo / redo'),
        ),
    },
    'btop': {
        'name': 'btop',
        'aliases': ('btop',),
        'rows': (
            ('q', 'Quit'),
            ('Up / Down', 'Select process'),
            ('Enter', 'Show process details'),
            ('f', 'Filter processes'),
            ('k', 'Send a signal to selected process'),
            ('+ / -', 'Change update interval'),
            ('Left / Right', 'Change process sort field'),
        ),
    },
    'mpv': {
        'name': 'mpv',
        'aliases': ('mpv', 'io.mpv.mpv'),
        'rows': (
            ('Space', 'Pause or resume'),
            ('Left / Right', 'Seek 5 seconds'),
            ('Up / Down', 'Seek 1 minute'),
            ('9 / 0', 'Volume down / up'),
            ('m', 'Mute'),
            ('f', 'Toggle fullscreen'),
            ('q', 'Quit'),
        ),
    },
    'imv': {
        'name': 'imv',
        'aliases': ('imv', 'imv-dir'),
        'rows': (
            ('q', 'Quit'),
            ('Left / Right', 'Previous / next image'),
            ('Up / Down', 'Zoom in / out'),
            ('+ / -', 'Zoom in / out'),
            ('f', 'Toggle fullscreen'),
            ('Ctrl+R', 'Rotate clockwise'),
            ('r', 'Reset zoom and pan'),
        ),
    },
    'thunar': {
        'name': 'Thunar',
        'aliases': ('thunar', 'org.xfce.thunar'),
        'rows': (
            ('Ctrl+L', 'Edit location'),
            ('Ctrl+T', 'New tab'),
            ('Ctrl+W', 'Close tab'),
            ('Ctrl+F', 'Search'),
            ('Ctrl+Shift+N', 'Create folder'),
            ('F2', 'Rename selected item'),
            ('Delete', 'Move selected item to trash'),
        ),
    },
    'zsh': {
        'name': 'zsh',
        'aliases': ('zsh',),
        'rows': (
            ('Ctrl+A / Ctrl+E', 'Move to start / end of line'),
            ('Ctrl+B / Ctrl+F', 'Move one character'),
            ('Alt+B / Alt+F', 'Move one word'),
            ('Ctrl+R', 'Search command history'),
            ('Ctrl+L', 'Clear screen'),
            ('Ctrl+U / Ctrl+K', 'Delete whole line / delete to end'),
            ('Tab', 'Complete'),
        ),
    },
}


TERMINAL_ROWS = (
    ('Ctrl+Shift+C', 'Copy'),
    ('Ctrl+Shift+V', 'Paste'),
    ('Ctrl+Shift+R', 'Search scrollback'),
    ('Shift+PageUp / Shift+PageDown', 'Scroll one page'),
)


SYSTEM_ROWS = (
    ('Super (hold)', 'Show this shortcut guide'),
)
