# forge

A CUE-declared plan for an isolated Incus project on `bak`: a Fossil server
for the `~/.files` mirror, plus ephemeral per-session checkout sandboxes, so
concurrent Claude sessions stop sharing this laptop's live checkout directly.

**Status: planned, not applied.** Nothing in `schema.cue`/`bak.cue` runs an
`incus` command — `plan.applySequence` (see `cue export . -e plan`) is the
exact command sequence that *would* create it, for Jack to review before any
of it touches `bak`. `plan.requires` lists what's still open, including his
explicit go-ahead.

Validate with `cue vet .` and inspect the rendered plan with
`cue export . -e plan` (both need to run where `cue` is installed — it's on
`bak`, not this laptop, at the time this was written).

`schema.cue` documents the reasoning inline: why it reuses bak's existing
shared `sandbox0` bridge and per-service network ACLs (the same pattern
`bak-portal-desktop` already uses) instead of minting a new network, why
exposure is `tailscale serve` on the bak host rather than a raw port or an SSH
tunnel, and how the disk/CPU/RAM sizing in `bak.cue` was derived from this
repo's actual checkout size rather than guessed.
