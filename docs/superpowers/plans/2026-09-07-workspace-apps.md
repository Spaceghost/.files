# Workspace application integration implementation plan

Follow the accepted direction in `../specs/2026-09-07-workspace-apps.md`.
The user authorized implementation in the current Sway desktop. Use the existing
Fossil branch and exact-path local check-ins; preserve concurrent artwork work.

1. Add pure workspace geometry and naming rules. Cover focus-vs-area, inactive
   workspaces, active tabs, fullscreen, floating windows and manual rename
   preservation with meaningful regression tests.
2. Resolve regular applications, terminal foreground programs, displayed tmux
   panes and exposed Codex/ChatGPT identities using local metadata. Implement
   independently from geometry; keep conversation contents out of runtime state.
3. Add supported Codex lifecycle callbacks and an installer with exact private
   backups and rollback. Preserve existing handlers/configuration; respect Codex
   hook trust. Test routing, ignored events, malformed payloads and recovery.
4. Connect the Sway IPC service, Waybar labels/star menu and session startup.
   Preserve numeric bindings; test lifecycle, malformed cache and command quoting.
5. Run isolated real-Sway integration, the full Alpine test suite, Sway parser,
   ShellCheck and disposable deployment. Apply to the active session and verify
   actual labels, singleton behavior, notification routing and a panel screenshot.
6. Record evidence and remaining checks in PROGRESS, review the exact changed
   paths, and check in locally with Fossil. No remote publishing.

Identity resolution, notification callbacks and independent review/headless
verification run as bounded parallel tasks. The main agent owns desktop wiring,
integration, deployment and the final check-in.
