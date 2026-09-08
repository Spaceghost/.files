# Theme selection, generation recovery, and running applications

The last five new themes saved their descriptors and paintings but could not
apply the desktop profile. `deploy-home` scanned every backup manifest as though
it were a deployment journal. Scripture database snapshots share that backup
directory and have a different schema, so the deployer refused every subsequent
theme switch and suggested an inappropriate deployment rollback. Those database
backups are valid personal recovery data and must remain untouched.

The deployment guard now recognizes foreign backup metadata, preserves legacy
list journals, and rejects interrupted or malformed deployment journals before
replacing HOME files. Timestamp-named deployment directories remain protected
even if their manifest is empty or a JSON scalar.

The theme picker now reports results through desktop notifications and reapplies
an explicitly selected theme even when its ID is already marked current.
Wallpaper pairing failures no longer prevent running applications from refreshing
after their files were deployed. Refresh failures return a failure status and
appear in the notification instead of silently reporting success.

The switcher now reloads btop through its supported SIGUSR2 handler and Neovim
through its existing RPC socket. Neovim executes only the managed colorscheme
and highlight declarations; it does not source the whole init file or replace
the editor's current options, mappings, buffers, undo history, or mode.
The process identity and handler/socket checks precede those operations.
Process signals and Foot palette writes are restricted to the caller's HOME
and explicitly identified Sway session, preserving concurrent private desktops.

The live Sway reload also exposed a client deadline mismatch: `swaymsg` stopped
waiting after 3.017 seconds, while a single direct IPC request received the
compositor's successful reply after 8.913 seconds. The switcher now consumes
that actual reply with a 20-second total deadline, validates framing and command
success, and never resends a command after submission. Eight fake-socket tests
cover delayed success, rejection, malformed/truncated replies and the deadline.

## Check against the saved preferences

- The selected descriptor still supplies a complete application profile and
  matching artwork. Existing saved generations can be selected without paying
  for another generation. No provider request is needed for this repair.
- Shared Waybar controls currently match the rendered profiles. The persistent
  Conky policy still excludes telemetry and enforces Scripture at 3600 seconds,
  gallery at 120, journal at 240, and witness at 300. Personal databases and the
  reading history are separate from theme configuration.
- The active Qt integration is **qt6ct**, including OpenSnitch, rather than the
  LXQt integration suggested by the older handoff. Its existing directory watcher
  updates the same running application and widget after its three-second debounce.
  A too-short initial probe was corrected; no extra Qt helper was installed.
- Installed Superhold dev1 already contains its replaceable CSS provider and
  one-second theme polling. The earlier pre-install handoff is superseded.
- The owned Scripture history reader now replaces its palette CSS when the
  theme changes. A native test retains the same entry, scroll position, draft,
  source and note type while colors change, with the synthetic history database
  byte-for-byte unchanged. Closing the window removes the timer and provider.
- Third-party GTK applications can retain the user CSS loaded at startup.
  A native isolated widget kept its old color after symlink replacement while
  its font setting updated. A desktop settings refresh alone does not replace
  those application-owned CSS providers. This remains a limitation; user
  applications were not closed to conceal it.
- Firefox has no generated browser-specific profile here. Notifications now
  describe that limitation instead of promising a restart will complete it.
- `ensure_profile()` still fills missing files while preserving existing files.
  Future descriptor or shared-control edits can therefore leave older generated
  files stale. A regeneration policy that preserves authored overrides remains
  a separate design decision; this repair does not overwrite them wholesale.

## Validation and evidence

Evidence lives in `alpine/verification/theme-repair/`. Failing-first deployment,
picker, refresh-result, and real application tests exercise the observed faults.
The application tests verify changed btop output in the same process and changed
Neovim colors with unsaved editing state intact. The native verifier deploys two
profiles into a private HOME containing a foreign backup fixture, then reloads
the same private Waybar process and captures the changed colors and spacing.
It never calls the physical-session refresh path.

The broad desktop run completed 829 tests with six assertion failures and three
timeouts: the Bazzite profile lacks `oldbook-resize`, one fullscreen-space
expectation disagrees with current behavior, and badge tests overlapped another
session's renderer edits. Two Bazzite timeout cases passed when rerun separately.
The broad run is retained as evidence and is not described as a passing suite.
Final focused checks and activation details are recorded with the evidence.
The current feature-contract runner passed all 280 tests across 27 check files.
The badge tests passed on a later rerun after the concurrent renderer update;
the fullscreen-space failure and a Bazzite overlay timeout remained reproducible.

The final physical `oldbook-theme use the-bellows-intercept-b503d18336b4 --notify`
completed with exit zero. Sway, GTK settings, Waybar, Foot, Ghostty, SwayNC,
Conky, tmux and btop reported refresh. The original bar, Ghostty, btop and
Firefox processes remained. All original Foot processes survived the first
activation; one exited before the final observation, for an unobserved reason.
The exact saved Bellows painting is selected.
All inspected foreign Scripture backup manifests retained their hashes.
See `live-final.json` and `live-activation-final.log`; the earlier false timeout
result is retained separately. Nineteen affected tests passed after the final
Sway integration, alongside the eight IPC tests and eighteen reader/history
tests. No shell source changed; Python syntax and the actual SwayFX configuration
were validated. The installed symlinked entry points resolve to these sources.

Native repaint checks use static fixture text instead of personal desktop
content. Earlier unsuccessful probes are retained with their corrections.
The first serif screenshot check was too strict about fully covered text pixels;
the verifier now uses bold fixture glyphs while retaining the selected colors
and font family.

## Recovery

Run `oldbook-theme use <previous-id>` to restore a previous complete theme.
The deployment journal records configuration backups and remains responsible
for actual interrupted deployment recovery. Never pass a Scripture database
snapshot to `deploy-home --rollback`.

Restore the helper/reader source independently of personal history databases.
Saved paintings and descriptors are not deleted or regenerated by recovery.
Only reviewed task files belong in this local Fossil check-in; concurrent
generation, artwork, branding, radio, and publication work remains separate.

## Runtime references

- [btop's reload handler](https://github.com/aristocratos/btop/blob/v1.4.7/src/btop.cpp#L1139-L1148)
- [Neovim RPC command-line interface](https://github.com/neovim/neovim/blob/v0.12.2/runtime/doc/remote.txt#L49-L60)
- [qt6ct's settings watcher](https://github.com/trialuser02/qt6ct/blob/master/src/qt6ct-qtplugin/qt6ctplatformtheme.cpp)
- [GTK's initial user CSS provider](https://github.com/GNOME/gtk/blob/gtk-3-24/gtk/gtksettings.c#L1879-L1895)
