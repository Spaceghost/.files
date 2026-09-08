# STRATA workspace-zero verification — 2026-09-07

The [native evidence](evidence.json) records seven passing behavior groups, and
the [unit result](unit-tests.json) and [full log](unit-tests.log) record 22 passing
focused tests, for workspace-zero service SHA-256
`8e9cc3daa0607ec52171fa87a78184a46b94be7dcf550d753f2d31ebbf563519`.
These are historical results for that exact source, using the production
launcher and daemon present when the tests ran. Concurrent changes to the
workspace target paused further verification; these results do not validate
later source versions or a launcher retry change. Other production and verifier
hashes are preserved in the JSON records.

The native run verifies:

1. Background startup creates one exact `oldbook-strata` window on workspace 0
   while the ordinary `firefox` control remains focused on workspace 2.
2. A duplicate daemon exits successfully without another browser or server.
3. Moving STRATA to workspace 4 returns it to 0 without changing ordinary
   Firefox's workspace or focus.
4. Two concurrent explicit launchers focus and reuse the existing STRATA window.
5. Closing that window creates one replacement on 0 without stealing focus or
   restarting the healthy Fossil server.
6. Killing the private Sway process with SIGKILL leaves its socket present, yet
   the daemon and its owned browser, server supervisor and Fossil stop.
7. Starting another daemon against that initially stale socket exits without
   launching browser or server children.

The [screenshot](strata-workspace-zero.png) shows only the synthetic STRATA
window after explicit focus. Placement and focus assertions come from bounded
native Sway IPC queries. The fixture uses private HOME, XDG directories, D-Bus,
Sway and an ephemeral loopback port; it never uses the host listener on 8766.
A private HTTP fixture substitutes for Fossil, and Foot substitutes for Firefox
with the exact production app ID. This exercises service and compositor behavior;
it does not establish Firefox rendering, real Fossil content or a logout/login
cycle. Live activation is separate from this private test.

[Runtime](runtime.log) and [service](service.log) logs retain the graphics probe
and unsupported icon-protocol warnings. Broken-pipe and Hangup messages occur
during the intentional browser/compositor termination. The verifier requires
successful service exit and stopped fixture processes despite those messages.
[Fixture traces](fixtures.jsonl) preserve launch counts, PID/parent relationships
and arguments. Their temporary run directory is replaced with `<PRIVATE_RUN>`;
no browser profile, real repository contents or user windows are copied here.

The [prior graceful run](prior-graceful/evidence.json) passed six groups,
including an orderly Sway `exit`, against service SHA-256
`d26d3253c077025daaaf376351af4ce73a2e9161c3e915fe092d7d83b07792fa`.
It predates pidfd supervision. Graceful native shutdown was not rerun on the
`8e9cc3da` candidate. Its verifier hash also predates the abrupt-shutdown option.
The seven-group run at this directory's root covers the later workspace-zero
source version identified above.

The separate [workspace migration](workspace-migration.json) recorded window
253 moving from 6 to 0 intact. The later [activation observation](service-activation.json)
recorded daemon PID 8847 running the `8e9cc3da` service, its lock held, an HTTP
200 response from Fossil, and review window 348 on workspace 0. Replacing the
intermediate supervisor restarted that browser while preserving its existing
profile. These are observations from activation, not a claim about the live
desktop after concurrent configuration changes. Resolving the workspace target
and verifying subsequent source changes remain pending.

To reproduce from the repository root, choose output directories that do not
already exist:

```sh
python3 -m unittest discover -s alpine/tests -p 'test_strata.py' -v
python3 alpine/tests/verify_strata_service.py --abrupt-shutdown \
    --output /tmp/strata-service-abrupt-new
python3 alpine/tests/verify_strata_service.py \
    --output /tmp/strata-service-graceful-new
```

The native verifier requires Linux pidfds, Python 3, `swayfx`, `/usr/bin/foot`,
`grim` and `dbus-run-session`. Run compositor checks sequentially. Each run
records hashes before starting and requires those sources to remain unchanged
before reporting success. Its private processes and directories are cleaned
up while the evidence directory remains available for review.
