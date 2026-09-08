# Bar responsiveness and prompted gallery themes

The workspace tracker and fullscreen dimmer had exited after transient Sway IPC
failures. Recovery loops now reconnect while preserving accepted tracking state.
The dimmer ignores title traffic and limits style reloads to its Wayland session;
its center selector now matches the music controls. A missing or stale tracker
reports unavailable instead of falsely reporting no agents. Existing concurrent
reconnect fixes were preserved and exercised with the focused recovery tests.

Super+Shift+right-click on the gallery opens a description prompt, using the same
complete-theme/debut-painting pipeline as random Super+Shift+left-click. The name
is generated from the description. Empty input and cancellation do nothing.
Existing schema validation rejects responses missing the desktop design; all
current themes render full application profiles. Generation authentication is
unchanged (existing Codex login); verification made no generation requests.

## Evidence

- `native/results.json`: seven real private Sway/Waybar checks: process-based agent
  detection, left cycling, attention state, stale/fresh recovery, fullscreen
  dim/hover/click, right-click picker and closing-session count.
- `media/evidence.json`: existing native playback, rating, selection and
  show/hide behavior checked against a private player and bus.
- `gallery-evidence.json`: 23 native modifier/mouse checks, synthetic keyboard
  excluded from the live compositor; screenshot accompanies it.
- Focused Python suites: tracker 32, dimmer 3, IPC recovery 3, wallpaper 9,
  new-theme/prompt 12, complete themes 3. Logs record actual counts.
- Two network-isolated builds produced byte-identical signed r9 APKs. Both passed
  `apk verify`; the archive was read back from Fossil and matched byte for byte.
  `alpine/packages/waybar-art/manifest.json` identifies the package and payload.
- `activation.json` and `live-bar.png`: installed library mapped by live Waybar,
  fresh tracker and current screenshot. The live desktop changed during restart,
  so window equality could not be asserted; activation issued no window commands.

## Recovery and remaining checks

The exact previous r8 artifact is recorded in `previous-r8-manifest.json`; export
it with `fossil uv export ARTIFACT /tmp/oldbook-waybar-art-1.0.0-r8.apk`, then install
with `doas apk add --no-network --allow-downgrades /tmp/oldbook-waybar-art-1.0.0-r8.apk`
and restart only the live Waybar instance. Keep unrelated checkout edits intact.
The new r9 artifact is in Fossil unversioned storage and the immutable current
package lock matches all 1121 installed package identities.
Physical interaction by the user and a new login are not observed; the actual
native widget was exercised in an isolated compositor. No live artwork was
created solely for testing. Unrelated repository work remains outside this change.
