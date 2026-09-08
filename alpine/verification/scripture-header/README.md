# Scripture header History

History is now a text link on the Scripture heading, in the same font and active
accent as the title. The separate search-bar button is removed. The passage keeps
its click-to-advance action, while History opens the saved reader without changing
the current reading. Theme-generated templates use the same shared renderer.

`test_conky_clicks.py` exercises the real generated configuration and Lua dispatch,
including the header/body boundary. It failed with an incorrect passage-advance
action before the fix and passed afterward. Both existing native GTK search-bar
theme tests passed, including live palette switches and descriptor edits.

`verify_scripture_header.py` provides isolated native Wayland verification at
scales 1 and 2 with different accent colors. It checks visible accent pixels in
the hit rectangle, sends actual virtual-pointer clicks, opens the real reader,
compares saved selection and card PID, and exercises passage advancement.
Its fixtures and databases are disposable; personal history is never committed.
Both scales passed (`native.json`), with purple and gold header screenshots in
`scale-1/` and `scale-2/`. Reader presence was verified through the native Sway
tree; premature reader screenshots were omitted. All private clients were
stopped (`cleanup.json`).

Live activation retained the saved selection/history, card coordinates, font,
palette and refresh interval. Other Conky clients predate activation. The session
owner relaunched the search bar first; the extra launcher exited under its
singleton lock, leaving one actual bar (`activation.json`). The live card was
covered by an application during capture; retained screenshots come from the
isolated compositor.

The initial default Conky suite had 40 passing checks and five existing Scripture
CLI fixture timeouts at 20 seconds. A separate isolated selection completed at
26.67 seconds; stack samples showed time spent reading the bundled compressed
Scripture catalog. Host load was about 40. These failures are recorded as timing
limits, not replaced with a claim that the entire suite passed.

The full mapped feature run completed 171 checks: 164 passed and seven failed.
The five click failures were the existing 20-second catalog-loading/10-second
advance deadlines. A shortcuts runtime-status check exceeded its 3-second
timeout. An existing global-fullscreen desktop-space assertion returned 16
instead of 60; neither that source nor test was changed here. See
`feature-checks.log`. The new header dispatch test, layout/policy suites, GTK
theme checks, Scripture history/selection/study suites and feature index passed.

Recovery: restore the affected source revision and the private pre-activation
`scripture.conf` backup, then refresh only Scripture and restart its search bar.
Keep personal `history.sqlite3` and the saved selection in place. The activation
record identifies the private backup; no personal database is included here.
