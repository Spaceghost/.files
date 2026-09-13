# A theme is not a painting

**The ask.** "The theme selector in my super+shift+d when I generate is
requiring wallpapers to generate to make the theme, that shouldn't be. I want
to select the option to make a new theme and just type there, not go to the
wallpaper section. It should fully cover literally everything themeable … The
ones we can't see can be asynchronously applied to their theme but the visible
should theme right away upon selection. I want to freely generate themes even
without the image gen. In fact, if you can't switch the bg generator to use a
different freeer api or set up my alienware to generate images for you, then
temporarily disable it for theme-gen and elsewhere unless called specifically."

**What was coupled.** `oldbook-control` → *Paint a new one* → `oldbook-wallpaper
pick` → *Create theme from prompt* → `generate.py --new-theme`, which designed
the theme as text, saved the descriptor, then painted through Codex and only
switched the desktop from `activate_artwork` after the painting landed. Codex
is out of credit until 2026-09-14 18:21, so no theme could be made; and the
design chain's Claude rung was never found because the generator's clean PATH
omitted `~/.local/bin`.

**The split.** Three things that were one:

1. *Designing and applying* is `oldbook-theme create PHRASE | --random`. Text
   only, through the existing chain (Codex, Claude, the Alienware). The model
   returns three colours and the design block; the pointer set and the folder
   icons are chosen here -- the nearest installed Simp1e set to the palette,
   and a set named after the theme, built into its profile by
   `build-icon-theme` on first use. Then `use`, unchanged in what it covers.
2. *The boot chain* is published after the visible switch, detached:
   `use --boot-chain background` (the default) writes the console palette in
   the switch and starts `oldbook-theme boot-chain ID`, which takes a lock,
   renders GRUB, runs the doas install, records the outcome and notifies --
   low urgency on success, critical with the log on failure. `now` keeps it in
   the process; `skip` is for a files-only switch.
3. *Painting* is a policy, `~/.config/oldbook/painting.json`: `scheduled` and
   `debut_painting`, both shipped off. Explicit requests always paint.

**Why not a free painter.** The keyless Pollinations API answers, but
anonymously it serves one model, caps output near 968x608 and watermarks the
image despite `nologo=true`; a wallpaper for a 2880x1800 panel cannot come out
of that. SSH to the Alienware is refused by the tailnet policy, so nothing can
be installed there from this laptop. A registered Pollinations token (free)
would lift both limits and would live in 1Password.

**What the deck offers.** Under *Theme*: the catalogue, then *New theme ·
describe it here* (a Fuzzel prompt with no rows; the text reaches `create` as
one argument), *New theme · surprise me*, and *Artwork gallery · paintings and
prompts*. The gallery's *Create theme from prompt*, *Random new theme* and the
badge's Super+Shift clicks run the same command.

**Verification.** Hermetic tests throughout (`test_theme_workshop.py`,
`test_painting_policy.py`, the deck, designer and boundary suites). One real
design through the Alienware rung alone, in a scratch copy of the checkout:
*Scriptorium Shadows*, 544 s, profile rendered complete. Nothing was exercised
on the live desktop; the deck prompt, a live `create` and the background boot
publish are first sightings.
