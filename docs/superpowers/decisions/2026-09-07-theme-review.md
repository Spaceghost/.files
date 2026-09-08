# Theme review

The user loves Gruvbox and wants to review the other themes visually, with
decisions recorded as the review proceeds. **Keep Gruvbox Dark.** All other
themes remain unreviewed; uncertainty is not a dislike or permission to remove
them. Ask for a decision after showing a small comparison batch. Record the
user's words and decision here before acting on a requested change.

The animation responsiveness request took priority before the first comparison
was reviewed. [The first comparison](../../../alpine/verification/theme-review/index.html)
preserves native previews of Gruvbox Dark, Space Ghost Violet and the current
Waxen Meridian. These isolated screenshots show wallpaper, Foot and a simplified
Waybar. They do not verify every application's appearance or responsiveness.

| Theme | Decision | Evidence / next step |
| --- | --- | --- |
| Gruvbox Dark | Keep — user confirmed | User says they love Gruvbox; comparison baseline. |
| Space Ghost Violet | Unreviewed | First comparison ready. |
| Waxen Meridian | Unreviewed | First comparison ready; active theme at audit time. |
| Spectral Wave | Unreviewed | Compare with Tidepool Astronautics for rounded, translucent styling. |
| Tidepool Astronautics | Unreviewed | Compare with Spectral Wave; bottom bar. |
| Sewer Starwatch | Unreviewed | Compare with The Watch at Dusk for compact, bottom-bar styling. |
| The Watch at Dusk | Unreviewed | Compare with Sewer Starwatch. |
| The Astronomer’s Vigil | Unreviewed | Compare with The Lanterns of Acre and The Falconer’s Comet. |
| The Lanterns of Acre | Unreviewed | Manuscript-inspired serif group. |
| The Falconer’s Comet | Unreviewed | Manuscript-inspired serif group. |
| Comet at the Caravanserai | Unreviewed | Compare with The Ivory Joust for warmer serif styling. |
| The Ivory Joust | Unreviewed | Compare with Comet at the Caravanserai. |
| Vespersteel Archive | Unreviewed | Compare with The Minted Eclipse and The Centurion’s Vigil. |
| The Minted Eclipse | Unreviewed | Similar geometry to Vespersteel Archive; different artwork. |
| The Centurion’s Vigil | Unreviewed | Serif group with 10-pixel spacing and left widgets. |
| The Bellows Intercept | Unreviewed | Compare with The Luminous Sounding and The Saffron Undertow. |
| The Luminous Sounding | Unreviewed | Design differs from Bellows Intercept only in launcher width. |
| The Saffron Undertow | Unreviewed | Design differs from Waxen Meridian only in launcher width. |
| The Brass Meridian | Unreviewed | Matching artwork is missing; completion issue, not a taste decision. |

## Audit findings

All 19 descriptors validate against the complete design schema and have all 25
currently required profile files. No exact duplicate palettes, designs or
artwork directions were found. Several generated designs are close enough to
compare together, but their artwork directions differ. The Brass Meridian has
no matching entry accepted by the gallery loader. Every other theme has at
least one accepted painting. File/schema checks alone do not prove a complete
live desktop.

The catalog has no saved theme ratings, favorites or hide list. It loads every
`alpine/themes/*.json` descriptor. `alpine/themes/current` saves only the active
selection, and `alpine/wallpapers/gallery.json` controls artwork rotation.
Neither records review decisions. Keep this document as the decision record;
do not infer taste from the active theme or generation history.

No theme descriptor, application profile, artwork or active selection was
changed for this review. Preserve the originals while deciding what to keep,
adjust or archive.

## 2026-09-08 — archived pending review

The 18 unreviewed themes (descriptors, application profiles and paintings)
were moved on disk into `alpine/archive/` while Gruvbox Dark stayed the only
active theme. The user directed that the move be recorded in Fossil as it
stands ("fossil mv them"), so the originals are preserved there, unchanged,
rather than deleted. Their review decisions above are still open; restoring a
theme means moving its files back out of `alpine/archive/`.

