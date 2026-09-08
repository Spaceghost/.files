# Fresh gallery scenes and mixes

The user reported repetitive generation with Super+click and requested new
scenes and mixes instead of more images of old scenes.

The native Waybar gesture already reaches `mbp-intel-wallpaper generate`;
Super+Shift+click reaches `new-theme`. The repetition came from generation:
the selector only excluded identical scene/insertion/medium triples, so another
medium or insertion made a previously painted scene eligible. Once those triples
were exhausted it deliberately returned the oldest. Local history also stopped
after 2,000 records and did not merge saved artwork when a history file existed.

Automatic generation now requires both an unpainted scene and an unused
insertion/medium mix, across theme collections. If either bank is exhausted, it
uses the existing Codex ChatGPT login for a bounded text-only proposal of a new
scene and mix. The image tool is disabled during this design step. Repeated
proposals are rejected before any image request; the existing three retries
apply and failures preserve the current wallpaper. Explicit scene selection
also refuses old scenes or mixes.

New-theme design receives previous subjects and collection art directions and
rejects reused scenes or styles before saving the descriptor. The complete
desktop design schema remains required. Theme debuts receive unique scene IDs
derived from their descriptions instead of every debut sharing `debut`.

History retains all records and merges gallery sidecars, curated entries and
local reservations, preserving paint order. Old sidecars can recover scene IDs
from their saved descriptions, titles or catalog IDs. New sidecars and
reservations include scene and mix descriptions and the theme art direction.
Deleted artwork remains remembered; failed image requests retain their proposed
subjects because an image could have completed remotely. Failed text-only
designs do not reserve subjects. Existing gallery browsing and rotation do not
request images and keep their previous behavior.

Validation: 89 focused tests passed across fresh scenes, themes, prompt catalog,
themed artwork, retries, prompt editing, wallpaper controls and Fossil artwork
checkpoints. The 17 new regression tests cover used scenes with unused mixes,
exhaustion, renamed subjects and mixes, history restoration/retention/order,
deleted-theme styles, explicit old-scene refusal, failed-image mix recovery, and
duplicate proposals never reaching image generation. Modified Python sources
compile. No real text design or image generation was requested during testing.

The read-only live audit in `alpine/verification/fresh-scenes.json` recovered 74
historical records, excluded 24 of 39 catalog scenes and found 15 unpainted
scenes. Its sampled next scene and mix were both unused. The live helper already
resolves into this checkout, so these changes apply to the next click without a
Waybar rebuild or restart.

Limits: exclusion checks compare IDs plus exact and lightly rewritten text.
The designer receives previous subjects and mixes, but semantic or visual
uniqueness of a generative model's output cannot be guaranteed. Actual image
generation remains an outstanding live check; tests deliberately used fixtures
without spending image allowance.

Recovery: restore the previous generator, prompt catalog, theme designer and
tooltip helper together. Keep the expanded local history and saved sidecars;
their additional fields are backward compatible. No artwork, current wallpaper,
theme choice or credentials were changed by this fix.
