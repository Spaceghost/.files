# Skip the system-monitor drop-down in caption selection

The user wants the system-monitor drop-down to be skipped by window decoration
just like the console. The launcher gives it the exact application ID
`com.mbp-intel.monitor`, separate from `com.mbp-intel.dropdown` and the historical
`mbp-intel-dropdown` console. Add the monitor to their shared caption exclusion.

Opening either drop-down keeps caption geometry, title and actions on the
previous ordinary window from Sway's current focus history. Normal Ghostty
windows and similarly named applications still receive captions. Fullscreen
monitor containers also leave the ordinary caption selection alone.

The existing placement and action-context tests now cover the monitor alongside
both console identities. Before the source change, three monitor subtests failed
as expected; all 47 decoration tests passed afterward. Native and activation
evidence is recorded in `alpine/verification/decoration-monitor/`.

Six isolated native checks passed. All 150 samples during monitor show/hide
retained the ordinary caption's target and geometry, with exactly one caption.
An actual normal Ghostty window still received its caption. The live helper was
restarted with matching tested source hashes and preserved appearance settings.

This updates the earlier console-only exclusion policy: the paired system
monitor is now excluded as well. The console/monitor launchers and bindings need
no changes. Recovery is to remove only `com.mbp-intel.monitor` from
`IGNORED_CAPTION_APPS` in `decoration.py` and restart the decoration daemon.
