# STRATA workspace 10 verification — 2026-09-07

The [focused unit result](unit-tests.json) and [full log](unit-tests.log) record
23 passing STRATA tests. The [native evidence](evidence.json) records seven
passing behavior groups against the production source hashes in that file:

1. Background startup opens STRATA on workspace 10 while the ordinary Firefox
   control remains focused on workspace 2.
2. A duplicate daemon creates no additional browser or server.
3. Moving STRATA to workspace 4 returns it to 10 without affecting the control.
4. Concurrent launchers focus and reuse the existing STRATA window.
5. Closing STRATA creates one replacement on 10 without stealing focus or
   restarting the healthy Fossil server.
6. Killing the private compositor leaves a stale socket but stops its service
   and owned browser and server processes.
7. Starting against that stale socket exits without launching children.

The [screenshot](strata-workspace-ten.png) shows the synthetic STRATA window
after explicit focus. Native Sway IPC assertions establish workspace placement
and focus. The fixture uses private HOME, XDG directories, D-Bus, Sway and an
ephemeral loopback port. Foot substitutes for Firefox with the exact
`oldbook-strata` app ID, and a private HTTP fixture substitutes for Fossil.
This verifies service and compositor behavior, not real browser rendering,
Fossil content, or logout/login. The verifier made no live compositor or
service changes.

[Live activation](activation.json) records the existing workspace being renamed
from 0 to 10 while preserving its workspace and browser container IDs and the
user's focused workspace. The old STRATA supervisor was paused, then stopped
without child cleanup so its replacement adopted the existing browser and
Fossil server. Workspace naming restarted and Sway reloaded successfully.
The resulting label is `10: STRATA · Fossil`; workspace 0 is absent.
An additional 38 workspace naming, placement and overview tests passed, along
with ShellCheck for `oldbook-session` and the Sway configuration parser.

[Runtime](runtime.log) and [service](service.log) logs retain the graphics probe
and unsupported icon-protocol warnings. Broken-pipe and Hangup messages occur
during intentional browser/compositor termination. Successful service exit and
stopped fixture processes are required despite those messages.
[Fixture traces](fixtures.jsonl) preserve launch counts and arguments; their
temporary HOME paths refer to the verifier's deleted private directory.
Native output was copied unchanged from `/tmp/oldbook-strata-ten`.

The [initial unit result](unit-tests-before-retry-repair.json) and
[failure log](unit-tests-before-retry-repair.log) preserve an existing launcher
retry test catching unhandled busy Sway IPC. Restoring bounded IPC retries
made all 23 tests pass before the native run. The hashes distinguish the two
source versions.

Reproduce from the repository root with a new output directory:

```sh
python3 -m unittest discover -s alpine/tests -p 'test_strata.py' -v
python3 alpine/tests/verify_strata_service.py --abrupt-shutdown \
    --output /tmp/oldbook-strata-ten-new
```

The native verifier requires Linux pidfds, Python 3, `swayfx`, `/usr/bin/foot`,
`grim` and `dbus-run-session`. It records source hashes before running and
requires them to remain unchanged before reporting success. The current
candidate's native shutdown check uses SIGKILL; a graceful shutdown native
run was not repeated for this workspace mapping change.
