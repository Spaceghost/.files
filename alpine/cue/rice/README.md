# The rice list, in CUE

`alpine/desktop/.config/oldbook/rice.json` -- the list the desktop's reading
card draws and `oldbook-rice` sets off -- is rendered from this package.
`catalogue.cue` is the list; `schema.cue` is what an entry has to be, the same
rules `rice_tour.check()` applies at load time, so `cue vet` catches a bad
entry before it is rendered.

Add a feature at the top of `catalogue.cue`, then:

    cue vet ./alpine/cue/rice
    cue export ./alpine/cue/rice -e rice --out json \
        > alpine/desktop/.config/oldbook/rice.json

Commit both files together. `test_rice_tour.py` fails if the shipped JSON is
not exactly what the source renders, so the two cannot drift apart; it skips
that check where `cue` is not installed (it is on this laptop, from `cue-cli`).

The desktop reads the rendered file, not the source: `deploy-home` links
`~/.config/oldbook/rice.json` to it, the Bazzite profile copies it, and the
card refreshes on its own slow cadence, so a re-rendered list appears without
restarting anything. The wider CUE pipeline for this repository
(`alpine/bin/cue-render`, `cue-sync`, and a watcher that pulls and applies on
every commit) is being built alongside; this package needs only `cue export`,
so it can be wired in as a whole-file target when that lands.
