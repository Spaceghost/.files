# Theme bundles and effects

Ripple defaults on. A theme can turn it off in its descriptor:

```json
"effects": {"ripple": {"enabled": false}}
```

Or ship a replacement with its other parts:

```json
"effects": {"ripple": {
  "enabled": true,
  "module": ".local/share/oldbook/themes/my-theme/effects/wave.py"
}}
```

Place the module, sibling Python helpers and textures under
`alpine/themes/profiles/my-theme/.local/share/oldbook/themes/my-theme/`.
Relative Python imports and assets resolved beside `__file__` are supported.
A replacement implements ripple.py's callable interface: allowed, region,
plan, geometry_string, capture, parse_ppm, crop, Ripple, and warm. It can import
shared functions from ripple and replace just its renderer. Theme modules run
as the desktop user; only activate packages whose code you trust.

The profile's `.config/oldbook/theme-effects.json` is the deployed declaration.
Existing authored declarations are preserved; edit that file directly when a
profile already exists. A newly rendered profile gets the descriptor's effects.
An empty ripple object resets to the enabled built-in effect on theme switches.
A disabled effect is neither imported nor warmed and takes no screenshot.
Geometry preferences stay in decoration.json. Numeric ripple tuning still uses
ripple.py's documented vocabulary and limits.

Export and import without executing any theme code:

```sh
alpine/bin/theme-bundle export my-theme /tmp/my-theme.zip
alpine/bin/theme-bundle import /tmp/my-theme.zip
oldbook-theme use my-theme
```

The archive contains the descriptor, full HOME profile, bundled custom effects
and assets, and the theme's shared authored icon set when present. Gallery
artwork explicitly tagged with the theme is included under its wallpaper assets;
the first PNG supplies the profile's fallback wallpaper. A manifest hashes every
payload file. Import rejects traversal, symlinks, duplicate paths, mismatched
hashes and oversized archives, and refuses to overwrite an existing theme.
Import does not activate anything. System application packages, fonts, inherited
icon/cursor sets and the Oldbook runtime remain installation dependencies.
