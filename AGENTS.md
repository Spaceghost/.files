# Agent instructions

## Theme coverage and inheritance

Every theme must provide a palette. A theme is a required palette plus optional
customizations, not a choice between those two. Shared rules may derive missing
semantic roles from that palette; app overrides, effects, and assets never
substitute for it. Theme import and validation must reject a missing palette.

Treat theme coverage as cumulative. Whenever work reveals another themeable
application, widget, state, or surface, add it to the shared theme coverage
rather than styling only the currently active theme. Existing themes should
gain that coverage without their authors writing another application config.

Use semantic palette roles (background, surface, foreground, muted, accent,
border, selection, success, warning, and error) instead of app-specific colors
or assumptions that an accent is always purple. Reuse and extend the existing
palette renderer rather than creating a competing theme implementation.

Keep the palette as the source of truth. Expose role variables where the
target supports them, using CSS custom properties, GTK named colors, or
generated native configuration as appropriate. Do not assume CSS variables
or Sass syntax are supported by every application.

Resolve styling from shared defaults, then the selected theme's semantic
palette and optional role overrides, then explicit app/surface overrides.
Missing app-specific theme files must inherit usable shared styling. Preserve
authored overrides and user-owned configuration; do not overwrite them while
regenerating shared or generated surfaces.

Keep a central inventory of managed theme surfaces and their templates, output
paths, supported reload mechanism, and coverage status. Register newly found
surfaces there, including hover, focus, selected, disabled, and urgent states
where applicable. Theme switching and palette changes should regenerate
affected managed outputs and reload supported applications without requiring
logout. Report unsupported or failed reloads instead of claiming full coverage.

Keep theme packages self-contained for their explicit overrides, effects, and
assets, while allowing them to inherit shared app templates from the installed
theme engine. Newly supported surfaces must also work with existing minimal
palettes and the monochrome theme; preserve readable contrast and intentional
role distinctions rather than indiscriminately replacing every color literal.

## Catbed media authorization and privacy boundary

The user authorizes local camera processing for tracking their cat while
Catbed is active, cat-only photos/video, and recording the cat's purrs for
later use. This is not authorization to retain, stream, or upload people,
speech, or general room recordings. Keyboard/trackpad presence heuristics
alone are not sufficient evidence to export media.

Process unfiltered camera/audio data locally in bounded volatile buffers.
Crop before encoding or transmission. Full-frame video is permitted only
when the target cat is confirmed and the scene is confirmed free of other
subjects; otherwise export only a verified cat-only crop or discard the frame.
Video streams must not carry raw microphone audio. Retain only trimmed purr
segments, rejecting speech, other sounds, overlaps, and uncertain segments.
Detector accuracy is imperfect; never describe these checks as a guarantee.

Streaming is restricted to the authenticated tailnet, never public ingress or
Tailscale Funnel. GitHub media uploads require an explicitly selected private
repository and a fresh check of its private visibility before publication.
Never place recordings in the dotfiles checkout or its public GitHub mirror.
Keep capture, streaming, and uploads disabled until the filtering pipeline and
its failure handling are implemented and evaluated. Preserve a visible
capture indicator and an immediate stop control independent of Catbed release.
