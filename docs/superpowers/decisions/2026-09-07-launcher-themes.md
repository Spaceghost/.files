# Theme-aware desktop launchers

Every MBP Intel Fuzzel entry point uses `mbp-intel-fuzzel`, which reads
`alpine/themes/current` and its descriptor each time a menu opens. Generating an
artwork collection does not itself change the active desktop theme.

The shared Fuzzel configuration controls typography and geometry: existing
JetBrains Mono at 13pt, comfortable row spacing, 12px outer corners, and a fine
accent border. Selected rows use 6px corners and a tint derived from the theme.
The wrapper supplies all color roles, including prompts, placeholders, matches,
and selected text. Opaque menu surfaces keep wallpaper colors from compromising
readability. Plain system `fuzzel` still uses the fallback configuration; desktop
integrations should invoke `~/.local/bin/mbp-intel-fuzzel`.

Minimal generated palettes need only background, foreground, and accent. The
adapter preserves readable colors, blends secondary colors from the theme, and
adjusts insufficient-contrast text toward black or white. Tests require text
contrast of at least 4.5:1, and selection/background separation of at least 1.3:1.
Malformed descriptors use the existing safe fallback reader.

Validation: new palette tests cover dark, light, identical gray, all-black, and
all-white inputs. Fuzzel's installed parser accepts the config and arguments;
ShellCheck accepts mbp-intel-menu. Actual isolated Sway renders are in
`alpine/verification/launcher-themes/`; `verify_launcher_themes.py` reproduces
them without changing the live palette. The real app launcher opens. The Expo
integration verifies searching/focusing windows, workspace selection, Escape,
close, toggle, and repeated show. Deployment to a disposable HOME passed.

The full Alpine test run had 343 tests, with three failures in the simultaneous
Superhold migration (configuration alias deployment and two legacy status
checks). No launcher/theme tests failed. The gallery integration shares
mbp-intel-wallpaper with ongoing desktop-panel work; its two wrapper substitutions
are applied but that shared file is excluded from this task's focused commit.

Recovery: restore this change's launcher/config paths from its parent revision
and remove the new mbp-intel-fuzzel HOME symlink. Reopen menus; no compositor restart
or persistent background service is required by this change.
