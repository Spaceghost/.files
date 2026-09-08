# Session test timing diagnosis

The original session script from `/tmp/oldbook-animation-before/oldbook-session`
was copied into a temporary directory, made executable there, and supplied as
the existing test module's `SESSION`. The repository baseline was not changed.
The test retained its four-second wait and all original assertions.

| Script / fixture | Result | Elapsed |
| --- | --- | --- |
| Original baseline / existing Python helpers | Timeout at first four-second wait | 4.087 s |
| Current session / existing Python helpers | Same timeout | 4.199 s |
| Current session / temporary `-S` helper shebangs | Same timeout | 4.210 s |
| Current session / temporary POSIX shell helpers | Pass | 2.135 s |

The one-minute load was approximately 43 on eight CPUs during the baseline
comparison. Separate Python startup samples were noisy, from 0.415 to 1.833
seconds, so they do not establish a consistent benefit from `-S`.

The session priority hook was separately executed with the inherited live
SWAYSOCK, a disposable runtime directory and a recording `doas` stub. The
recording confirms the helper was never invoked: the session socket does not
match the fixture's runtime directory. No live service or scheduling attribute
was changed by this diagnosis.

The smallest demonstrated fixture fix is to generate its fake `pgrep` and six
fake desktop services in POSIX shell instead of starting Python for each one.
The shell `pgrep` checks the same readiness files and recognizes the same
polkit exemption; each shell service still waits 0.2 seconds, appends its PID,
and lives for ten seconds. The successful experiment retained the four-second
deadline, concurrent clients, readiness delay and every original assertion.
Only temporary fixture output was substituted during diagnosis. The follow-up
applies that narrow shell fixture rewrite to `alpine/tests/test_session.py`,
including correctly quoted output for the setup counter. Assertions, timeouts
and delays are unchanged. `final-test.log` records the passing revised test;
`shellcheck.json` records clean checks of every generated shell fixture.
Session production scripts were not changed by this investigation or fixture
rewrite.
