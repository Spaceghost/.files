# Theme switching and gallery activation repair

Gallery generation with activation now applies the saved painting's exact theme
before selecting that painting, including an existing theme. Previously only a
newly generated theme triggered the theme switch. Choosing another theme while
generation is running does not change the completed painting's recorded target.
Unthemed artwork preserves the desktop theme; background or manual generation
without activation changes neither the selected theme nor painting. An activation
failure retains the saved artwork and reports the failure.

The final gallery checks passed **48 tests**:

| Check file | Passed |
| --- | ---: |
| `test_generation_retries.py` | 5 |
| `test_manual_artwork.py` | 12 |
| `test_new_themes.py` | 12 |
| `test_theme_completion_notification.py` | 7 |
| `test_themed_artwork.py` | 12 |

[Final output](generation-final-tests.log) and
[source hashes](generation-final-validation.json) identify this run. The
[initial failing regression](generation-red.log),
[focused passing run](generation-focused-green.log),
[narrow change](generation-change.diff) and
[initial summary](generation-summary.json) preserve the earlier work. The initial
summary records an unrelated stale tooltip assertion; the final 48-test run
includes its corrected expectation and passes. These checks use controlled
generation fixtures, not a paid image request or a live desktop theme change.

Theme switching also failed because the deployer's recovery guard treated
unrelated Scripture database backup manifests as interrupted HOME deployments.
The concurrent guard repair preserves strict checks for actual deployment
journals while allowing unrelated backup manifests to coexist. No Scripture
backup was rolled back, marked restored or deleted to unblock switching.

The [private deployment proof](private-deployment.json) ran the actual
`oldbook-theme use … --no-reload` CLI from a copied checkout into a disposable
HOME containing a byte-for-byte copy of an affected manifest and a synthetic
database payload. Both Waxen Meridian and The Bellows Intercept succeeded; all
25 profile links and the recorded theme changed. Foot background/foreground
changed from `171B1D`/`D9E1D5` to `11191C`/`E9E0C9`, and Waybar styling changed.
The unrelated manifest and payload remained unchanged. This proves deployment
and file selection in isolation; it does not prove running applications reloaded.
The recorded source hashes belong to that historical run and intentionally
differ from the later refresh helper revision.

A separate live diagnosis found `swaymsg reload` timed out after about 3.032
seconds under load even though the compositor could acknowledge a reload later.
The root agent's direct IPC probe received command reply type 0 with
`[{"success": true}]` after **8.19997 seconds**. That result is retained inside
the [Sway reload review evidence](sway-reload-review/evidence.json), together with
the original record's hash and provenance. It establishes the short client
timeout problem; it is not itself an invocation of the repaired theme helper.

The concurrently authored helper sends one reload through an explicitly
identified, owned `SWAYSOCK` and waits up to 20 seconds across the entire exchange.
It validates framing and command results, preserves compositor rejection details
and never resends a command after an ambiguous timeout. Missing session identity
fails visibly rather than choosing another compositor. The intended gallery
activation process inherits its outer desktop session.

The independent review passed **14 isolated tests**: eight IPC checks, two
session ownership checks and four application refresh/reporting checks. They
cover delayed acknowledgement, rejection, malformed and truncated replies,
an absolute deadline despite fragmented input, session isolation, and visible
partial failures. The evidence records exact commands, durations and stable
source hashes. This review retained its structured result, not separate raw
stdout log files. Successful fragmented replies and the oversized-header branch
were reviewed but do not have dedicated assertions in that eight-test IPC suite.

The native helper and deployment guard were already being repaired by another
session; this work reviewed and integrated their evidence without duplicating
those edits. The generation repair, private deployment proof and native IPC
review are separate verification stages.

The root agent subsequently recorded [live activation](activation.json). The
new helper received a successful reload acknowledgement after 8.15957 seconds;
no window IDs disappeared. All 24 theme-controlled configuration links matched
The Bellows Intercept, its exact painting was selected, and the original Ghost
palette was present. `waybar-state.css` is generated runtime state and is
intentionally excluded from profile-link matching. The
[earlier refresh output](live-refresh-before-ipc-fix.log) and
[original slow acknowledgement](slow-reload-acknowledgement.json) retain the
comparison. These checks establish live state and reload acknowledgement, not a
visual audit of every running application.
