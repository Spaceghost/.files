# Agent selector order

Super+N starts with new Codex Astra ultra and Claude best/max sessions, then
current tmux sessions, then the remaining enabled presets and the close action.
The pinned entries appear only when enabled and are not duplicated below the
current sessions. New-session rows say `New`; the existing Fuzzel `--no-sort`
option preserves this order when the picker opens.

The existing Codex preset uses GPT-6 Astra with ultra reasoning. The new
`claude-max` preset passes `--model best --effort max`. Claude's documented
`best` alias selects the latest Fable available to the account, otherwise Opus;
`max` applies to the launched session. See the official
[model configuration](https://code.claude.com/docs/en/model-config) documentation.
The preset retains the existing local Claude permission configuration.

Validation: all 27 agent tests pass, and the installed Claude CLI accepts the
configured argv with `--help`. No provider request was sent. Native menu
evidence is stored in `alpine/verification/agent-selector/` using synthetic
sessions. The live launcher and configuration symlink into the checkout, so
the next picker invocation uses these changes without restarting sessions.

Recovery: reverse this ordering commit to restore the previous menu and remove
the new Claude preset. Existing tmux sessions remain available for attachment.
