# Gruvbox Dark × Space Ghost

## Complete desktop themes

Every theme includes a desktop design and application profile. Run
`oldbook-theme list` and `oldbook-theme use <id>` to switch. Generated collections
now specify typography, corner geometry, spacing, opacity, bar placement, widget
placement and launcher width as well as colors and artwork. Switching applies
the application files, selects an available matching painting and refreshes the
session. Applications that cannot reload styling pick it up when reopened.

`wallpapers/desktop_theme.py` renders missing profiles from the shared desktop
configuration, preserving functional controls. `oldbook-theme sync` materializes
all profiles; `oldbook-theme use <id> --no-reload` restores one into HOME without
reloading the session. Profiles use the deployment journal's backups and rollback.
Generated profile files are derived locally; the descriptor and renderer are the
rebuild inputs. Existing authored profile files remain editable.

The active desktop uses warm charcoal, aged cream, amber, olive and muted aqua.
Window borders, launcher outlines and panel outlines are disabled. Focus is
shown through surface and text color. Existing shortcuts, controls, tooltips,
notification behavior and gallery features remain available.

## What a descriptor declares

A theme is one JSON file beside this README. Thirteen palette roles and eight
design values are the whole of what has to be authored; everything else is
derived, so dropping in a new theme stays a small job.

```
palette   background  background_hard  surface  border  foreground  muted
          red  green  yellow  blue  purple  aqua  orange
design    font  radius  spacing  opacity  bar_position  widget_edge
          launcher_width  cursors  icons
```

Ten further palette roles may be declared and are otherwise derived from the
thirteen. They exist because real consumers needed values the thirteen could
not express:

| Role | Consumer | Derived as |
| --- | --- | --- |
| `red_dim` … `orange_dim` | ANSI 1–6 in Foot, Ghostty, btop, Neovim, the Linux console and the LUKS prompt | the bright role 32% toward `background` |
| `surface_bright` | selection grounds, divider rules, btop's followed rows | `background` 32% toward `foreground` |
| `subtle` | ANSI 7, and the bar's own dim labels | `background` 66% toward `foreground` |
| `foreground_dim` | inactive titles, sidebars, footers | `background` 78% toward `foreground` |

Before the dim roles existed, a generated theme's terminal had eight distinct
colours rather than sixteen: every dark ANSI slot was snapped onto whichever
single role sat nearest, which put Gruvbox's dark yellow on `green`, its dark
magenta and dark cyan both on `muted`, and `#bdae93` — an inactive window title
— on `purple`. Gruvbox Dark declares its own canonical sixteen; a theme that
declares none gets a readable derived set.

`design.cursors` names the installed Simp1e pointer set the drawn Oldbook-Ghost
waiting shapes inherit every other shape from, and `design.icons` names the
folder set built by `alpine/bin/build-icon-theme`. Both are asset *names*: a
descriptor that omits them inherits the shipped Gruvbox sets rather than being
refused, and `oldbook-theme use` says so when a named pointer set is not
installed instead of leaving it to be noticed by eye.

Off-palette shades in the authored templates are rebuilt as
`blend(base_role, tint_role, amount)` rather than snapped to one role, so a
tinted status ground keeps both the ground it sits on and the colour it is
tinted with: the bar's keep-awake amber is `background_hard` a quarter of the
way toward `yellow_dim` in every theme, not a flat surface grey.

## Adding a theme

```sh
cd ~/.files
$EDITOR alpine/themes/<id>.json          # thirteen colours and eight design values
alpine/bin/build-icon-theme --theme <id> # optional: its own folder icons
oldbook-theme sync                       # render its profile, cursors and deck tiles
oldbook-theme use <id>
```

`oldbook-theme sync` renders every profile's text files, draws that theme's
pointer shapes and power-deck glyph tiles, and derives its Ghostty palette from
its Foot one. Nothing here compiles: the image builders are cairo and Pango.

## What reacts to a theme switch, and what does not

| Surface | How it follows |
| --- | --- |
| Sway, SwayFX | one IPC `reload`, awaited |
| Pointer | `seat * xcursor_theme` after the reload |
| Waybar | `SIGUSR2`, after the accent stylesheet is re-elected |
| SwayNC | `swaync-client --reload-config` and `--reload-css` |
| Conky | restarted by `oldbook-conky restart` |
| Foot | OSC 4/10/11/12/17/19 written into each terminal's pty |
| Ghostty | `SIGUSR2` |
| tmux | `source-file` on every live server socket |
| btop | `SIGUSR2`, guarded by an installed-handler check |
| Neovim | `--remote-expr` re-running only the colour lines of `init.lua` |
| GTK 3/4 | theme, icon theme, font, cursor theme and size pushed to `org.gnome.desktop.interface` |
| Oldbook overlays | the decoration strip, Scripture bar, carousel and Super-hold poll the palette each second; the OSD and lock read it per render |
| LXQt Qt apps | the plugin rereads `lxqt.conf`, which is now part of the profile |
| fuzzel, wlogout, swaynag, satty | spawned per invocation, so they read the new files |
| cava | `SIGTERM`; its supervisor brings it back |
| The boot chain | the console palette is regenerated; `build-grub-theme` and `install-boot-console` publish it |

Three things a running session cannot be made to follow, and are reported
rather than hidden:

- **Third-party Qt windows** read qt6ct at startup. Oldbook's own Qt surfaces
  follow the palette on a one-second timer; other Qt windows keep the previous
  theme until they are restarted.
- **Already-running GTK and Qt clients** load the cursor theme themselves, and
  `XCURSOR_THEME` in the session environment is fixed until the next login.
  Sway's own pointer changes immediately.
- **`gtk.css`** has no reload channel; the keys that travel are the ones
  `settings.ini` publishes through gsettings.

## Edit and apply

The deployed files are symlinks into `alpine/desktop/`; edit either path.
`gruvbox-dark.json` records the shared palette and artwork direction. The
application-native files retain their full settings and can be edited directly.

```sh
cd ~/.files
alpine/bin/deploy-home
swaymsg reload
oldbook-gtk-settings
oldbook-refresh-terminal-theme
tmux source-file ~/.tmux.conf
swaync-client --reload-css
```

Waybar keeps previous, current-track/play-pause, and next media controls in the
middle section between the left and right control groups. They sit directly on
the bar without a separate center capsule and hide when no player is available.
It watches CSS changes. The artwork icon opens the gallery on left-click and
advances to the next image on right-click. Middle-click pauses rotation; scroll
selects previous/next. Command/Super + left-click generates and Shift + left-click
opens the prompt editor. New terminal
windows read all Foot settings; the refresh command recolors existing Foot
sessions without sending input or closing applications. Other applications
that load their theme only at startup use it when next opened.

`oldbook-decoration` provides one caption at each workspace's bottom edge.
The right edge remains available through right-click or the desktop decoration
editor (`oldbook-decoration-settings`, also Shift + right-click on the caption).
The editor shows placement, opacity and corner radius alongside the editable
`~/.config/oldbook/decoration.json`. Changes apply automatically. Both the editor
and caption follow the active palette, including generated themes; the caption
uses a translucent gradient without a pixel outline. Fullscreen tiled captions
are square, while floating and ordinary windows keep the configured rounding.
Left-click opens the window picker; middle-click toggles the focused window's
floating state. The caption uses the active theme's design typeface (Inter Medium
for Gruvbox Dark) one point above the saved terminal size, left-aligned like an
exhibit label; a theme without a design font keeps the terminal font.

`sway/theme.conf` retains themed native captions as a fallback. Space Ghost uses
plum and lilac; Gruvbox uses charcoal and amber, with centered terminal-font text.
The local SwayFX package can place these below individual windows when native
captions are enabled. Its native drag/resize and middle-click behavior has been
verified separately. See the [offline compositor recipe](../packages/swayfx/README.md).

## Ghost Observatory

The [concept preview](concepts/ghost-observatory/README.md) presented windows as
exhibits: rounded charcoal surfaces, captions underneath, and the contextual bar
above. Its visual language is now the production desktop: 22-pixel window
corners with soft, deep shadows, 6/7-pixel gaps, floating pill-shaped bar
islands with rounded tooltips, an 18-pixel launcher, and Inter Medium captions
with roomier padding. Two parts of the concept were deliberately not adopted:
the window title stays out of the bar centre (music lives there, `BAR-LAYOUT`)
and the caption remains the oldbook-decoration strip with the saved
bottom / 0.67 / radius 7 preferences rather than native per-window titlebars
(`DECORATION-STYLE`); the Ghost badge keeps its own colours (`GHOST-BRAND`).

`alpine/themes/preview --output DIR [--power-deck]` renders the deployed
profile, bar, caption daemon and three Foot cards in a private headless SwayFX
session over the pinned Yosemite painting, without touching the live desktop.
The adopted look is recorded in
[verification/ghost-observatory](../verification/ghost-observatory/README.md).

## Artwork collections

`current` selects the default generation/rotation theme. Each `<id>.json`
descriptor has a safe ID, display name, palette and `image_style`. New artwork
lives under `alpine/assets/gallery/themes/<id>/`; unrestricted palettes go under
`alpine/assets/gallery/general/`. Old flat artwork remains available.

The timer mixes the active theme with general images. Manual scrolling,
previous/next and the gallery still reach every collection. The gallery offers
active-theme, unthemed and named-theme generation. See the
[gallery guide](../wallpapers/README.md).

## The accent follows the painting

The theme's colours stay put, but its accent moves with the artwork. After every
image change `oldbook-palette` reduces the new painting to a weighted hue
signature in OKLab and elects whichever of the theme's *own* accent candidates
holds the largest share of its colour, plus a companion. Nothing is sampled out
of the canvas: for Gruvbox Dark the choice is between the declared yellow,
orange, aqua, green, blue and purple, and red stays reserved for urgency. A grey
painting, or one where no colour holds a third of the frame, keeps the declared
accent.

The election lands in `~/.local/state/oldbook/palette-override.json`, which
`overlay_theme.read_palette` honours for the theme that produced it and only for
colours that theme declares, so the feedback pill, launcher, Expo, lock screen,
caption strip and shortcut guide all retint on their next render. The bar reads
`~/.config/waybar/waybar-accent.css`, imported last by `style.css` so it wins
over the hardcoded amber. The Ghost badge is branding and never changes.

```sh
oldbook-palette          # re-elect for the painting on screen
oldbook-palette show     # the current record, with its scores
oldbook-palette clear    # back to the theme's declared accent
```

A descriptor turns the whole thing off with `"reactive_accent": false`; an
absent key means enabled. Details and evidence:
[the design note](../../docs/superpowers/specs/2026-09-08-reactive-palette.md)
and [verification/reactive-palette](../verification/reactive-palette/README.md).

## Preserve and rebuild

`profiles/spaceghost/` preserves the original application theme configurations;
`profiles/gruvbox-dark/` records this theme's starting configuration. These are
authored profiles used by the switcher. Missing application files are supplied
from the shared desktop configuration. The active overlay and Fossil history
remain the source for the installed setup.

`profiles/catppuccin-mocha/` is authored the same way, and deliberately. Its
surfaces were generated by recolouring templates designed for Gruvbox, which is
high-contrast, warm and earthy; Mocha is low-contrast and cool and gets its
depth from a ladder of surfaces (crust, mantle, base, surface0-2, overlay0-1)
rather than from strong colour, so a straight recolour arrives flat. The bar,
the notification centre, both GTK palettes, the launcher, the LXQt palette and
the Qt colour scheme are written for that ladder instead. `ensure_profile` only
ever *adds* files a profile is missing and never rewrites one that is present,
so these survive a theme switch, a regeneration and any later template change.
The one file no profile may author is `.config/ghostty/config`: `oldbook-theme`
regenerates it from that profile's `foot.ini` on every switch.

The exact cursor and Papirus inputs are in the APK lock. The Qt system palette
link is installed by `alpine/bin/install-desktop-system`. The native artwork
widget has its own offline build recipe and verified identical package builds.
`alpine/bin/build-icon-theme` rebuilds the warm gold folder icons from the locked
Papirus SVGs; the generated overlay, licenses and hashes are versioned too.
Copy a complete Fossil database backup, including its unversioned artifacts,
using [the restore instructions](../packages/RESTORE.md).

## Expo and Super-hold palettes

Ghost Expo and the Oldbook Super-hold launcher read the palette selected by
`alpine/themes/current`. The Fuzzel workspace/window picker reads colors when it
opens; Super-hold refreshes while running, within about one second. Gruvbox Dark
supplies charcoal surfaces, cream text, muted brown labels, and amber highlights.
Other descriptors use the same semantic roles.

The shared adapter is `desktop/.local/lib/oldbook/overlay_theme.py`. The picker
passes palette colors to Fuzzel while retaining its configured fonts and shape;
the Oldbook launcher applies Qt palette roles locally to Hold to Help. The
standalone Hold to Help project retains native platform theming.
