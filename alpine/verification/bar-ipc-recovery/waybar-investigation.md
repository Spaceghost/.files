# Waybar responsiveness and title traffic investigation

Read-only host observations and a private headless compositor fixture, 2026-09-07 PDT. Host Waybar PID 26778 was not signalled, restarted, traced or otherwise changed by this investigation. Host screenshots cover only the bar. Terminal titles were counted and SHA-256 hashed, never recorded as text.

## Observations

- Live bar screenshots at 20:50:35 and 20:52:02 show that the clock progressed from 20:50 to 20:52. Workspace labels/focus and the AI indicator also changed; root was recovering the missing helpers during observation.
- A 6.737-second process sample measured 79.58% of one CPU total: main GTK thread 46.17%, a second thread 32.21%. States were running or sleeping, without the earlier ACPI-blocked observation in this sample. The samples cannot establish continuous health.
- An 8.01-second read-only IPC subscription saw 321 events, all window:title (40.07/s), from four terminals.
- A separate 6.072-second title-hash subscription saw 242 events from those terminals and zero identical consecutive titles. Three containers repeated a sequence of ten hashes. Skipping identical adjacent title notifications would not reduce this traffic.
- Official Waybar 0.15.0 source src/modules/sway/workspaces.cpp subscribes to all window events and unconditionally requests IPC_GET_TREE in onEvent. Thus a title-only stream causes complete tree requests and workspaces rebuilds even for format {value}.

## Private native proof

The fixture ran installed Waybar 0.15.0, the installed oldbook-art.so (checksum in evidence), copied production stylesheet, four Foot windows, its own non-activating D-Bus bus, HOME/XDG directories and headless SwayFX compositor. No production service was started. A private LD_PRELOAD probe observed computed GTK color, main-loop heartbeat, clock text and label-attribute calls; it was never injected into the host bar.

- Three successive atomic replacements of imported waybar-state.css changed computed clock color red→green→blue→red at the next 200ms observation without any signal. The log contains only style reloads for these replacements. The initial probe selector was overridden by production CSS; the successful fixture uses a more specific inspection selector and explicitly verifies its starting color. That discarded probe is retained under /tmp/oldbook-waybar-freeze-check/private-probe/initial-overridden-inspection-rule.
- Idle CPU was 0–0.33%; four windows emitting distinct titles ten times/second raised Waybar CPU to 21.17%; stopping title traffic returned it to 0.33%. All phases retained the clock and heartbeat.
- Three explicit SIGUSR2 reloads in this minimal fixture did not freeze the bar. The host log contains reload-related Glib critical errors, but these observations do not prove the reloads alone caused the reported freeze.

## Scoped change and recommendation

With root authorization, removed only the two reload_style() call sites after write_state in alpine/desktop/.local/bin/oldbook-waybar-dim. Its atomic writer, event filtering, reconnect loop and other functions are unchanged. Waybar already watches imported CSS with reload_style_on_change=true, so dim transitions need no full module reconstruction. Root owns test updates. The later scoped dim activation is recorded separately below; this investigation did not restart Waybar.

Keep the parent’s helper reconnection repair. The title stream is a confirmed avoidable workload for the workspace module, with plausible contribution to IPC pressure; avoid treating it as a proven sole cause of the missing watchers or freeze. If another scoped fix is needed, prefer making Waybar skip title-only workspace rebuilds when the configured format does not use titles, with a native regression check, rather than a SwayFX identical-title dedup that cannot address these changing animation frames.

Primary source retrieved for exact installed version: https://github.com/Alexays/Waybar/blob/0.15.0/src/modules/sway/workspaces.cpp and https://github.com/Alexays/Waybar/blob/0.15.0/src/util/css_reload_helper.cpp . Exact downloaded copies are retained under /tmp/oldbook-waybar-freeze-check/source/.

## Final helper activation

A fresh identity check found Waybar 26778 and dim helper 10227 had already been replaced by Waybar 26230 and dim helper 26333 before this subagent performed any host mutation. Workspace helper 10225 was unchanged. The replacement dim helper began seven seconds before the final source edit, so this subagent used pidfd identity checks to terminate only dim 26333 and started dim 29947 with the same session environment. Waybar 26230 and workspace helper 10225 were preserved. No terminal commands, fullscreen changes, workspace changes or Waybar signals were sent. `dim-style-activation.json` records identities, source SHA-256 and five advancing workspace-state samples; the source hash is `296eaf6adcce78d141420b92e42b6475315f878b41064318664a03ecea683d36`.

`native-style-and-title-traffic/` retains the successful private probe source and evidence. `live-title-hash-summary.json` omits actual titles and hashes while retaining event counts and uniqueness counts. `clock-after-dim-*.png` contains only the clock area of the live bar; matching JSON records timestamps and final preserved process identities.
