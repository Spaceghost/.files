# Gruvbox Dark × Space Ghost

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
oldbook-gtk-settings
oldbook-refresh-terminal-theme
tmux source-file ~/.tmux.conf
swaync-client --reload-css
```

Waybar places the focused-app title and media controls immediately before the
right-hand status group; its center module list is empty.
It watches CSS changes. Its artwork widget preserves left/right/middle
click and scroll, and adds Command/Super+left-click generation. New terminal
windows read all Foot settings; the refresh command recolors existing Foot
sessions without sending input or closing applications. Other applications
that load their theme only at startup use it when next opened.

`sway/theme.conf` contains decorations separately from keybindings. Foot has
a matching fallback decoration for other compositors. The local SwayFX package
puts normal window captions below their content; grouped tab and stack headers
retain their controls. Its soft shadows, rounded corners and bottom captions
take effect at the next normal desktop login when stock Sway is still running.
See the [offline compositor recipe](../packages/swayfx/README.md).

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
reference/restore copies, not a switcher that overwrites later feature edits.
The active overlay and Fossil history remain the source for the installed setup.

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
