# Gruvbox Dark × Space Ghost

## Complete desktop themes

Every theme includes a desktop design and application profile. Run
`mbp-intel-theme list` and `mbp-intel-theme use <id>` to switch. Generated collections
now specify typography, corner geometry, spacing, opacity, bar placement, widget
placement and launcher width as well as colors and artwork. Switching applies
the application files, selects an available matching painting and refreshes the
session. Applications that cannot reload styling pick it up when reopened.

`wallpapers/desktop_theme.py` renders missing profiles from the shared desktop
configuration, preserving functional controls. `mbp-intel-theme sync` materializes
all profiles; `mbp-intel-theme use <id> --no-reload` restores one into HOME without
reloading the session. Profiles use the deployment journal's backups and rollback.
Generated profile files are derived locally; the descriptor and renderer are the
rebuild inputs. Existing authored profile files remain editable.

The active desktop uses warm charcoal, aged cream, amber, olive and muted aqua.
Window borders, launcher outlines and panel outlines are disabled. Focus is
shown through surface and text color. Existing shortcuts, controls, tooltips,
notification behavior and gallery features remain available.

## Edit and apply

The deployed files are symlinks into `alpine/desktop/`; edit either path.
`gruvbox-dark.json` records the shared palette and artwork direction. The
application-native files retain their full settings and can be edited directly.

```sh
cd ~/.files
alpine/bin/deploy-home
swaymsg reload
mbp-intel-gtk-settings
mbp-intel-refresh-terminal-theme
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

`mbp-intel-decoration` provides one caption at each workspace's bottom edge.
The right edge remains available through right-click or the desktop decoration
editor (`mbp-intel-decoration-settings`, also Shift + right-click on the caption).
The editor shows placement, opacity and corner radius alongside the editable
`~/.config/mbp-intel/decoration.json`. Changes apply automatically. Both the editor
and caption follow the active palette, including generated themes; the caption
uses a translucent gradient without a pixel outline. Fullscreen tiled captions
are square, while floating and ordinary windows keep the configured rounding.
Left-click opens the window picker; middle-click toggles the focused window's
floating state. The caption follows the saved terminal font.

`sway/theme.conf` retains themed native captions as a fallback. Space Ghost uses
plum and lilac; Gruvbox uses charcoal and amber, with centered terminal-font text.
The local SwayFX package can place these below individual windows when native
captions are enabled. Its native drag/resize and middle-click behavior has been
verified separately. See the [offline compositor recipe](../packages/swayfx/README.md).

## Ghost Observatory concept

The [native concept preview](concepts/ghost-observatory/README.md) presents windows
as exhibits: rounded charcoal surfaces, captions underneath, and the contextual
bar above. Its larger corners and spacing are a visual proposal; the preview
script renders the real patched compositor without changing the active theme.

## Artwork collections

`current` selects the default generation/rotation theme. Each `<id>.json`
descriptor has a safe ID, display name, palette and `image_style`. New artwork
lives under `alpine/assets/gallery/themes/<id>/`; unrestricted palettes go under
`alpine/assets/gallery/general/`. Old flat artwork remains available.

The timer mixes the active theme with general images. Manual scrolling,
previous/next and the gallery still reach every collection. The gallery offers
active-theme, unthemed and named-theme generation. See the
[gallery guide](../wallpapers/README.md).

## Preserve and rebuild

`profiles/spaceghost/` preserves the original application theme configurations;
`profiles/gruvbox-dark/` records this theme's starting configuration. These are
authored profiles used by the switcher. Missing application files are supplied
from the shared desktop configuration. The active overlay and Fossil history
remain the source for the installed setup.

The exact cursor and Papirus inputs are in the APK lock. The Qt system palette
link is installed by `alpine/bin/install-desktop-system`. The native artwork
widget has its own offline build recipe and verified identical package builds.
`alpine/bin/build-icon-theme` rebuilds the warm gold folder icons from the locked
Papirus SVGs; the generated overlay, licenses and hashes are versioned too.
Copy a complete Fossil database backup, including its unversioned artifacts,
using [the restore instructions](../packages/RESTORE.md).

## Expo and Super-hold palettes

Ghost Expo and the MBP Intel Super-hold launcher read the palette selected by
`alpine/themes/current`. The Fuzzel workspace/window picker reads colors when it
opens; Super-hold refreshes while running, within about one second. Gruvbox Dark
supplies charcoal surfaces, cream text, muted brown labels, and amber highlights.
Other descriptors use the same semantic roles.

The shared adapter is `desktop/.local/lib/mbp_intel/overlay_theme.py`. The picker
passes palette colors to Fuzzel while retaining its configured fonts and shape;
the MBP Intel launcher applies Qt palette roles locally to Hold to Help. The
standalone Hold to Help project retains native platform theming.
