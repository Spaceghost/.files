# Hold to Help Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Deliver and locally install a standalone, theme-aware contextual shortcut overlay with a reproducible Alpine package.

**Architecture:** Preserve the tested input and asynchronous service core. Replace fixed GTK styling with Qt desktop styling and add an X11 backend alongside Sway. Package the Python modules and a small native layer-shell bridge using CMake.

**Tech Stack:** Python 3.11+, PyQt6, Qt6, layer-shell-qt, python-Xlib, CMake, Alpine abuild, Fossil.

**Spec:** `docs/superpowers/specs/2026-09-07-hold-to-help.md`

## Global Constraints

- Version 0.1.0; GPL-3.0-or-later; executable `hold-to-help`.
- No npm, bundled Qt, keyboard grabs, hardcoded palette, remote publication, or live compositor restart.
- Preserve Super by default, Caps-to-Escape locally, custom profiles, scrolling, and current shortcuts.
- Explicitly label incomplete application and desktop coverage.

---

### Task 1: Portable input, context and service

**Files:** `projects/hold-to-help/hold_to_help/{hold,sources,profiles,service,config,x11,cli}.py`, package initializer and core tests.

**Interfaces:** `HoldState` and `ServiceController` retain their tested contracts. Providers return dictionaries containing `app`, `output`, `sections` (title, coverage, key/description rows), and optional `_output_rect`.

- [x] Port existing 62 behavioral tests to package imports; run `PYTHONPATH=projects/hold-to-help python3 -m unittest discover -s projects/hold-to-help/tests -v` before and after extraction.
- [x] Add config tests rejecting unknown trigger/backend and nonfinite or out-of-range hold duration (0.15–3 seconds).
- [x] Implement X11 focus/context and key polling; test namespace-aware Openbox XML and LXQt shortcut config parsing with temporary files.
- [x] Connect Qt timers to the existing asynchronous controller; verify stale context cannot show after release, locks hide, and singleton identity is per display.

### Task 2: Theme-aware nonfocusing Qt overlay

**Files:** `hold_to_help/qt_overlay.py`, `native/{CMakeLists.txt,layer_shell_bridge.cpp}`, `tests/test_qt_overlay.py`.

**Interfaces:** `create_application(argv=None)` and `QtShortcutOverlay(trigger_label='Super')`; methods `show(snapshot)`, `show_loading(context)`, `hide()`, `close()`; `.window` for native validation.

- [x] Add offscreen tests using two `QPalette` values, plain-text hostile labels, scrolling, and nonactivation flags.
- [x] Implement palette/font/style-derived rendering with runtime updates; no forced platform theme or stylesheet colors.
- [x] Build the C bridge against installed layer-shell-qt; set overlay layer, keyboard none, exclusive zone zero, and appropriate output.
- [x] Run tests with `QT_QPA_PLATFORM=offscreen` and native checks in nested Sway and Xvfb/Openbox.

### Task 3: Release, Alpine package and local migration

**Files:** project `CMakeLists.txt`, `bin/hold-to-help`, README, LICENSE, CONTRIBUTING, CHANGELOG, data/manual/examples, release helper; `alpine/packages/hold-to-help/`; legacy launcher and verification evidence.

- [x] Install modules into `share/hold-to-help`, native bridge into `lib/hold-to-help`, and command into `bin`; validate a temporary DESTDIR's `--help` and `--version`.
- [x] Produce a deterministic source tar using sorted paths, owner/group zero and fixed `SOURCE_DATE_EPOCH`; build signed APKs twice under `unshare --net` with `abuild -d` and compare SHA-256.
- [x] Validate desktop metadata, source license, manual, CLI errors, native palette/focus/scroll behavior, and service hold/release lifecycle.
- [x] Install package, preserve source-edit workflow and old command/profile paths, restart only the shortcut service, and verify it stays hidden while locked.
- [x] Archive exact dependencies and artifacts; review scoped Fossil diff, commit, and back up the repository. Record actual evidence and remaining publication prerequisites without claiming an upstream release.
