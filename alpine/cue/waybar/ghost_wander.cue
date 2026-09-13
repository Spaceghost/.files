// Ghost-wander: the idle "float in place and wander" animation on the
// #custom-ghost Waybar module (a @keyframes block plus a #custom-ghost.wander
// rule in style.css) and the matching exec/return-type/interval addition to
// the custom/ghost module in config.jsonc.
//
// Jack: "make the little ghost ... float in place and wander ... like a
// tomagatchi." This was hand-copy-pasted byte-for-byte into three theme
// profiles (gruvbox-dark, catppuccin-mocha, monochrome-test) on 2026-09-13,
// then migrated here as the first real CUE-driven fragment in this repo --
// the "plain files don't suffice alone" case CUE is for.
//
// CUE owns only this fragment, not the surrounding files: alpine/bin/cue-render
// finds the "BEGIN cue-generated: ghost-wander" / "END cue-generated:
// ghost-wander" marker comments already placed in each profile's style.css
// and config.jsonc, and replaces only the text between them. Everything else
// in those files (colors, other modules, the powerline separators) stays
// hand-authored. Run alpine/bin/cue-sync after editing this file -- it
// validates, re-renders and reloads the running Waybar for you; don't hand-
// edit the marked regions.
package waybar

// #GhostWander is deliberately small: all three profiles below render
// byte-identical output today, but a future profile with a different float
// height, cycle length or glyph overrides one field here instead of
// copy-pasting the whole block again.
#GhostWander: {
	// CSS @keyframes name; also referenced by the animation: declaration.
	keyframesName: string | *"oldbook-ghost-wander"

	// Full float cycle length.
	durationSeconds: number & >0 | *11

	// CSS animation-timing-function plus iteration count, e.g.
	// "ease-in-out infinite".
	timingFunction: string | *"ease-in-out infinite"

	// Vertical excursion in pixels from the resting margin. margin-top and
	// margin-bottom trade off around 8 evenly spaced waypoints (0%, 12.5%,
	// ..., 87.5%) so their sum -- and the module's footprint in the bar --
	// never changes: one clean sine-like rise and fall per cycle (Jack:
	// "make the ghost float more fluidly", replacing an earlier 5-waypoint
	// flutter that eased to a full stop at each waypoint).
	amplitudePx: number & >=0 | *3

	// The module's resting margin (the non-animated #custom-ghost rule).
	// margin-right and margin-left hold constant across the whole cycle.
	restMargin: {
		top:    number | *3
		right:  number | *5
		bottom: number | *3
		left:   number | *3
	}

	// The waybar `exec` helper that adds/removes the .wander class on
	// #custom-ghost: on only when Jack has not turned it off (ghost.json's
	// wander key) and the power ladder still allows this small ambient
	// motion (sheds at low battery like everything else in that ladder).
	helperCommand:       string | *"~/.local/bin/oldbook-waybar-ghost-class"
	pollIntervalSeconds: number & >0 | *30
}

// All three current profiles take the defaults untouched -- they were
// byte-identical copy-pastes of each other, so there is nothing to
// parameterize yet. Listed explicitly (rather than derived from the
// filesystem) so adding or dropping a profile here is a one-line, reviewable
// change, and so cue-render's profile list and this file's can never disagree
// silently.
profiles: [string]: #GhostWander
profiles: {
	"gruvbox-dark":     {}
	"catppuccin-mocha": {}
	"monochrome-test":  {}
}
