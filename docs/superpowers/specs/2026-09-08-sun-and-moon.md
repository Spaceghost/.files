# Sun and moon: masthead line, night light, nocturne preference

**Date:** 2026-09-08 · **Scope:** desktop panels, session services, gallery rotation

## Decision

The desktop learns where it is only from a file the user writes:
`~/.config/oldbook/location.json` with `name`, `latitude`, `longitude` and
`timezone`. The overlay ships `location.example.json` (Los Angeles, the city
the clock already announces) and documentation, never the live file. Nothing
is fetched and nothing is inferred; without the file every feature below stays
dormant and the desktop is unchanged. This keeps the SESSION-OWNERSHIP pin's
"no inferred location/night-light policy" intact while satisfying the README's
rule that `wlsunset` may run for an explicitly chosen location.

## Arithmetic

`desktop/.local/lib/oldbook/astro.py` is dependency-free and offline:

- Sun: the NOAA solar calculator equations (Meeus). Solar noon is anchored on
  the UTC day nearest the local noon so far-east and southern locations keep
  the right calendar day; sunrise and sunset are refined once with the terms at
  the event itself. Civil twilight uses the 96° zenith. Polar days and nights
  report `None` for the crossings and `is_night` falls back to the sun's
  declination sign.
- Moon: elongation from the low-precision Astronomical Almanac longitude
  series (six periodic terms, about 0.3° accuracy). Phase names use the eight
  45° bins; the lit fraction is `(1 − cos D) / 2`. Glyphs are the Nerd Font
  Material moon set, mirrored south of the equator because the lit limb is.
- Verified against published values: Los Angeles 2024-06-21 sunrise 05:42 and
  sunset 20:07 (published 20:08), 2024-12-21 06:54/16:47; London, Sydney and
  Auckland within five minutes; Tromsø midnight sun; January 2024 new and full
  moons within 45 minutes; synodic cycle 29.46 days.

## Desktop integration

- Masthead card: one extra line, `${execpi 300 ~/.local/bin/oldbook-astro panel}`,
  in both panels.json copies (card height 80 → 100). The policy guard keeps the
  interval within 60–300 s; the line contains no telemetry. Empty without a
  location.
- Night light: `oldbook-sun-light run` execs `wlsunset -l LAT -L LON -t 3500 -T 6500`;
  `oldbook-session` starts it through `start_service` only when the location
  file exists and no wlsunset is running. `stop`/`toggle` write a `disabled`
  marker under `~/.local/state/oldbook/sun-light/` so a user stop survives
  reloads; the command deck exposes **Night light**.
- Nocturnes: `nocturne.nocturne_preference` is consulted only on the automatic
  global timer tick. Between sunset and sunrise it draws the next painting with
  weights 3 (nocturne) : 1 (other) among every painting except the current one,
  so nothing is excluded and manual browsing is untouched. A sidecar's explicit
  `time_of_day` wins; otherwise whole-word matching on night, moon, nocturne,
  dusk, stars, candle, lantern, midnight, aurora and their plain derivatives
  (never substrings, so "Nighthawks" alone does not qualify). Daylight, no
  location or a gallery with no nocturne defers to the ordinary sequence.

## Checks

`alpine/tests/test_astro.py` covers the published references, ordering and
twilight brackets across a year, equinox symmetry, polar behaviour, phase
names/glyphs/illumination, hemisphere mirroring, location-file validation,
the masthead line, the CLI without and with a location, `oldbook-sun-light
status`, and the 3:1 weighting with a seeded generator (4000 draws). Recorded
gaps: a full night of live rotation and the physical wlsunset ramp were not
observed in this session; the display was off and locked during verification.
