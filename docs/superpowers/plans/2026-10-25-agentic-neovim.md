# Agentic Neovim Implementation Plan

**Goal:** Make Agentic the native Codex interface in the Spaceghost Neovim shell, locally and on bak, and push the configuration.

**Architecture:** Load a pinned Agentic optional Neovim package on demand. Install the maintained Codex ACP adapter with a locked npm dependency tree in user data, using the existing ChatGPT login. Keep shell navigation and unrelated bak edits intact.

**Tech Stack:** Neovim Lua, shell, Agentic, @agentclientprotocol/codex-acp.

**Authorization:** User requested full installation here, in .files, pushed, and on bak. Existing recommendation specifies Agentic; routine integration choices are implementation details.

## Constraints and review focus

- No credential copies or new API keys; reuse each machine's existing Codex ChatGPT login.
- Preserve Ctrl-backslash as the cockpit prefix; use prefix i for Agentic and F4 i for its menu.
- New sessions use the originating file's directory or shell's OSC 7 directory, even after the UI changes focus.
- No startup network access; missing dependencies give an actionable install command.
- Preserve unrelated working-tree changes on bak and all running shell jobs.

## Steps

1. [x] Add pinned dependency manifests, repeatable installer, native UI module, theme, commands, keybindings, command deck entry, and user guide.
2. [x] Install locally; check actual native buffers, ACP initialization, ChatGPT authentication, response streaming, project directory, and existing navigation regressions.
3. [x] Review, commit and push only task files; fast-forward bak without disturbing its edits, install there, verify, and reload both running cockpits without restarting jobs.

## Progress

- Recon complete: live configurations are symlinked to .files on both machines; bak has unrelated FFXIV/tmux edits. Both use Codex ChatGPT login. New maintained adapter is @agentclientprotocol/codex-acp 2.2.2.
- Local installation and real Codex streamed-response smoke test passed. Existing navigation and nested remote UI tests passed (15 checks).
- Independent review found stale workspace after config reload and terminal-mode launch failing to enter insert mode. Both reproduced with regression tests, fixed, and verified passing. No other important issues reported.
- bak's /tmp is full; home has space. Installer and adapter use user-cache temporary directories, without deleting existing files.
- Rollout verified on both machines: real Codex streamed response, native buffers, workspace after reload, hide/reopen, keyboard launch from terminal input, and all 15 navigation checks passed. Running cockpits reloaded without service restarts; bak's preexisting tracked diff and working-tree status remained unchanged.
