# Changelog

## 0.2.0.dev1 — desktop theme integration

- Use the desktop GTK palette and font in the guide and search controls.
- Reload user GTK colors while the guide or settings window is open.
- Follow atomic stylesheet and symlink replacements; retain valid styling during incomplete edits.
- Keep selection text readable with the theme's selected foreground color.
- Remove Superhold's stylesheet and theme watcher when its window closes.

## 0.2.0.dev0 — interactive application preparation

- Add a floating guide that stays open until focus moves away.
- Search shortcut keys, actions and context; use Up/Down and Enter to activate.
- Make native keyboard shortcuts clickable with separate alternatives.
- Wait for physical keys to be released and verify the original target before replay.
- Add a settings screen, versioned JSON configuration and idle reload.
- Provide guide and settings application-menu entries for LXQt with Sway.
- Preserve the installed Oldbook overlay while preparing a dedicated repository.

## 0.1.0.dev0 — release preparation

- Extract the contextual Super hold overlay from the Alpine Sway desktop.
- Package it as `superhold` with separate XDG configuration and runtime paths.
- Include desktop menu and optional LXQt autostart entries for LXQt with Sway.
- Honor logind's lock hint in addition to active-session checks.
- Preserve the existing input, source parsing, and lifecycle regression tests.
- Add source provenance, release notes, build artifacts, and CI preparation.

No release tag or public release has been created. License selection and
physical LXQt session validation remain open.
