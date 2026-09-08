# Near-full floating window shortcut

Super+Shift+Space invokes `oldbook-resize near-full`. It exits fullscreen,
enables floating, and centers the focused window in its containing workspace's
usable rectangle. Each edge keeps five percent of the available dimension,
with a minimum 24 logical pixels of breathing room. A second press reapplies
the same size and position.

Sway supplies the usable rectangle, so the helper respects reserved bars,
output offsets and logical scaling. It checks the resulting window dimensions
and corrects the center if application or compositor size constraints changed
the request. An application minimum larger than the available area can prevent
the requested margins; the helper still centers the actual size.

The existing grow/shrink actions retain their 40-pixel step and original window
center. Caption middle-click and directional resize controls keep their current
behavior. The shortcut does not toggle back to tiled mode.

Verification combines focused unit cases with the existing private Sway resize
probe. The native probe retains all earlier resize checks and covers repeated
near-full application from floating, tiled and fullscreen modes, an exclusive
top bar, and a scaled output with a nonzero origin. It never resizes a host
window.
