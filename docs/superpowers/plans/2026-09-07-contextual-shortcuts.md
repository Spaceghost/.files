# Contextual Shortcuts Implementation Plan

> **For agentic workers:** Use Superpowers subagent-driven-development for independent components, with test-first implementation and a final code review. Steps use checkboxes for tracking.

**Goal:** Show contextual shortcuts while Super alone remains held for 500 ms.

**Architecture:** A read-only evdev detector drives a non-focusable GTK layer
overlay. An independent provider collects focused-app profiles, effective Sway
bindings and contextual tmux/terminal controls, off the UI thread.

**Tech Stack:** Python 3 standard library, GTK3 GI, GtkLayerShell, Linux evdev,
Sway IPC, tmux, Python unittest, Fossil.

**Spec:** `docs/superpowers/specs/2026-09-07-contextual-shortcuts.md`

## Global Constraints

- Hold threshold is 500 ms; either Super key works, any other key cancels.
- App, Sway, then other contextual layers; incomplete coverage is explicit.
- Never grab input, change input permissions, or persist key events.
- Keep keyboard focus in the app; use existing installed dependencies.
- Preserve unrelated changes and use exact-path Fossil commits on alpine-oldbook.
- Approval for implementation and live enablement is already given.

## Task 1: Hold detector

Files: create `alpine/desktop/.local/lib/mbp_intel/shortcut_hold.py` and
`alpine/tests/test_shortcut_hold.py`.

Interface: `HoldState.update(device, code, value, now)`, `visible(now) -> bool`,
`cancel()`, `remove_device(device)`, and `EvdevMonitor.poll(now) -> bool`,
`EvdevMonitor.close()`, `EvdevMonitor.device_count`.

- [x] Write failing behavior tests with literal Linux codes 125/126 (Super), 30
  (A), 29 (Ctrl). Example: update('kbd',125,1,0); visible(.49) is false;
  visible(.5) is true; update('kbd',30,1,.6); visible(.7) is false; release A
  still leaves visible false until a fresh Super press.
- [x] Run `python3 -m unittest discover -s alpine/tests -p test_shortcut_hold.py -v`.
- [x] Implement the state machine, nonblocking input reads and hotplug/drop
  recovery. Input is consumed transiently; no grab or key logging.
- [x] Run the same tests and review detector safety and error paths.

## Task 2: Shortcut discovery

Files: create `alpine/desktop/.local/lib/mbp_intel/shortcut_sources.py`,
`shortcut_profiles.py` and `alpine/tests/test_shortcut_sources.py`.

Interface: `ShortcutProvider(socket_path, profiles_path=None).snapshot() -> dict`
returns `{app, output, sections}`. Sections have `{title, coverage, rows}`;
rows have `{key, description}`. Snapshot failures are bounded and explicit.

- [x] Write failing tests for Sway variable expansion, modes, repeated bind
  replacement and unbind handling; active tmux pane selection; unknown apps;
  context ordering and malformed custom profiles.
- [x] Run `python3 -m unittest discover -s alpine/tests -p test_shortcut_sources.py -v`.
- [x] Implement bounded IPC/command queries and baseline app profiles. Use
  effective tmux tables and label partial app coverage. Any shared app resolver
  dependency must degrade safely if unavailable in a fresh repository export.
- [x] Run provider tests and inspect one live snapshot without saving private data.

## Task 3: Overlay, service lifecycle and deployment

Files: create `alpine/desktop/.local/lib/mbp_intel/shortcut_overlay.py`,
`alpine/desktop/.local/bin/mbp-intel-shortcuts`,
`alpine/desktop/.config/sway/local.d/shortcuts.conf`,
`alpine/tests/test_shortcut_service.py` and runtime evidence under
`alpine/verification/`. Document operation in a focused shortcut README.

- [x] Write failing lifecycle tests: an owned runtime directory and socket are
  required, same-session lock excludes duplicates, shutdown closes resources.
- [x] Run targeted lifecycle tests before adding the implementation.
- [x] Implement GTK layout with keyboard mode NONE, scrollable app/Sway/context
  sections, nonblocking provider worker and immediate cancellation. Bound the
  window to the focused monitor and add dump/preview CLI commands.
- [x] Add startup snippet `exec_always --no-startup-id ~/.local/bin/mbp-intel-shortcuts daemon`.
- [x] Validate under isolated Sway, capture screenshot and evidence, and review
  the entire feature with an independent reviewer. Fix significant findings.
- [x] Run complete unittest suite, Sway validation and disposable deployment.
- [x] Deploy only feature files into HOME with the existing deployment journal,
  start the service and check live daemon/device state without injecting host keys.
- [x] Record remaining physical/reboot checks in PROGRESS and commit exact paths.

## Execution record

- Design approved in conversation; implementation proceeds without another gate.
- Existing shared checkout has unrelated active desktop edits. New startup and
  documentation files keep this feature separate; no reset or broad commit.
- Main controller owns integration and runtime verification while two independent
  component workers implement detector and providers in parallel.

- Task 1 complete: 21 tests pass; independent review reports spec and quality PASS.
- Runtime checks passed: two real keyboard devices opened read-only and closed;
  GTK preview keeps focus and delivers real key input to the app; real Wayland
  scrolling changes list content; fullscreen and focused second-output placement
  pass at 1440x900 and 1280x720; timed HoldState-to-GTK integration passes all
  seven tap/chord/left/right/release scenarios.
- Daemon runtime checks passed: active graphical session, two keyboards, duplicate
  startup exclusion and SIGTERM cleanup. Host key injection was not used.

- Final pre-fix full repository run: 197 tests passed. A preceding run had one
  concurrent notification-stream failure; its isolated rerun passed.
- Review identified corrections before live enablement: follow Sway includes;
  preserve distinct tmux key case and literal minus; select the correct Emacs
  copy-mode table; place the loading panel on the focused output; handle a
  disappearing Wayland socket during lock checks; avoid stale worker starvation.
- One combined fix wave assigned to the overlay implementer, with covering
  regression tests and a scoped independent re-review required.
- Root reproduced the loading placement failure in real isolated GTK with a
  deliberately delayed provider; verification script and evidence live in the
  temporary runtime check directory until the final evidence is recorded.

- Final independent scoped review: specification PASS and quality PASS. All
  seven original findings plus variable-redefinition and include-once
  regressions are resolved. Final provider suite passes 22 tests.
- The exact reviewed files pass all 191 tests in a fixed export of committed
  base `6d7e6cc6db1d66ca8d8faaac1c9280e3eeab09c9` plus this feature, including
  62 shortcut tests. The concurrent shared checkout run had seven failures
  because another task removed its notification LED helper during development.
- Stock Sway parser validation and disposable deployment pass. Live deployment
  journal: `~/.local/state/mbp-intel/backups/1788782412724579771`; six links only.
  Service is active with two keyboard devices; duplicate startup preserves PID.
- Compositor shutdown exits the daemon. Native GTK may terminate before the
  final status write; kernel resources are released and stale identities are
  rejected. This runtime limit is documented, not reported as graceful cleanup.
- Remaining checks: physical hold observation, actual keyboard hotplug, VT
  switching and reboot persistence. Runtime evidence and screenshot are saved
  in `alpine/verification/contextual-shortcuts.{json,png}`.
