# Ghost Gallery

All workspaces share one desktop image and one rotation timer. The desktop
changes artwork every 20 minutes. The Waybar art icon shows the
current painting and its story: click for the next image, scroll to browse,
right-click for a gallery picker, and middle-click to pause. **Super/Command +
left-click** generates a new painting and switches directly to it when ready.
**Shift + left-click** opens the prompt editor. Both Shift and Super keys work;
holding Shift and Super together opens the editor. Right/middle clicks and
scrolling keep their usual actions even when a modifier is held.
The gallery also offers **Generate new artwork & switch to it**. The same controls
work from a terminal:

```sh
oldbook-wallpaper next
oldbook-wallpaper prev
oldbook-wallpaper pick
oldbook-wallpaper pause
oldbook-wallpaper generate
oldbook-wallpaper generate --theme none
oldbook-wallpaper generate --theme gruvbox-dark
oldbook-wallpaper edit-prompts
```

The gallery preserves the painting list and appends next/previous, pause/resume,
**Help & gallery controls**, and **Open command deck** alongside generation.
The picker shows up to 28 rows so the current gallery and its controls fit on
the laptop display. Scroll or type part of an action/title to find further entries.
**Edit artwork prompts** is available there too. Its shared guidance and scene
editor offers **Save** and **Cancel**. Saving affects future paintings and new
theme designs; it preserves scene IDs, generation settings and existing artwork.
The previous prompt file is backed up under
`~/.local/state/oldbook/prompt-backups/`. An editor opened before another change
asks you to reopen the file instead of overwriting that newer version.

The shared guidance reflects strong Christian faith, admiration for the
historical medieval Crusades and a love of history. All existing Space Ghost
scenes remain, with additional cathedral pilgrimage, Crusader procession and
monastery chronicle scenes. Sacred subjects are treated reverently, with humor
coming from Space Ghost and his companions.

The command deck retains its desktop tools and adds a **Help** entry. Guides
open in a terminal pager; press `q` to close them.

Edit `gallery.json` to change the interval or curated pool. Add images with JSON
sidecars under `alpine/assets/gallery/`; each entry has `id`, `title`, `file`,
`description`, and ideally `sha256`. Paths are relative to the checkout and must
remain inside `alpine/assets/`. Generated entries are discovered recursively;
symlink escapes and changed hashes are rejected.
The active link is `~/.local/share/oldbook/current-wallpaper.png`; deployment's
baseline `wallpaper.png` is separate. `oldbook-session` starts the rotation daemon
and refreshes the current artwork after Sway reload. A file lock prevents
multiple daemons, including when no graphical session is available yet.
`workspace_rotations: []` keeps selection, pause and the timer global; switching
workspaces does not change the painting. Previous per-workspace selections remain
saved but inactive under `~/.local/state/oldbook/wallpaper/workspaces/`.

## Theme collections

New artwork has separate, additive collections:

- `alpine/assets/gallery/general/`: unthemed generations, with natural scene colors.
- `alpine/assets/gallery/themes/gruvbox-dark/`: warm charcoal, amber and cream artwork.
- `alpine/assets/gallery/themes/<theme-id>/`: other named theme generations.

The original flat artwork stays in place. `gallery.json` marks it with
`legacy_theme: "spaceghost"`; no old image is moved or removed. The picker shows
every painting with its collection label, in the original order followed by new
collections. Click, scroll and next/previous commands continue browsing **all**
artwork. Only the automatic timer follows `rotation_themes`: the default
`["active", "none"]` mixes the active theme and unthemed images. Use `["all"]` to
rotate everything. Until a selected collection contains images, the timer uses
the existing gallery so the desktop always has artwork.

`alpine/themes/current` selects the artwork theme; its descriptor is
`alpine/themes/<theme-id>.json`. Theme IDs use lowercase letters, digits and
hyphens. Each descriptor supplies `id`, `name`, `image_style` and an optional
`palette`. The current default is Gruvbox Dark; the Space Ghost Violet descriptor
is also preserved. Changing this artwork selector does not rewrite application
configuration.

**Generate new artwork & switch to it** and Super/Command+click use the active
theme. The gallery also adds **Generate unthemed artwork** and an explicit
generation action for each installed theme. The foreground equivalents are
`generate.py --manual --activate --theme active`, `--theme none`, or
`--theme gruvbox-dark`. Every new sidecar records the selected theme, exact theme
style, palette, full prompt and bitmap hash, keeping each result restorable even
if the theme descriptor is edited later.

## Paint on demand

Manual requests run in the background and use the next scene from `prompts.json`.
The artwork icon shows an hourglass while painting; notifications announce the
start, completion or failure. Repeated clicks during generation report that it
is busy without queuing more images. The daily job and manual commands share
the same exclusive lock.

Each explicit manual request is additional to the daily schedule and uses your
Codex image allowance/credits. It does not consume or erase the day's scheduled
reservation. Successful artwork switches immediately, even if rotation is paused;
the pause setting is preserved and the rotation countdown resets. A failed
generation leaves the current image in place. If Sway is unavailable when it
finishes, the saved painting remains selectable in the gallery.

Manual records and logs live under `wallpaper-generation/manual/`; launcher
errors go to `wallpaper-generation/manual.log`. `generate.py --manual --activate`
runs the same operation in the foreground. Remove `--activate` to save only.

## Daily painting, without npm

The one-liner is:

```sh
python3 "$HOME/.files/alpine/wallpapers/generate.py"
```

Run `alpine/bin/install-wallpaper-schedule` from the checkout to preserve existing
cron jobs and add an hourly wake check. The generator reserves **one attempt per
local calendar day**, including failures; it never retries a billed daily run.
It uses an exclusive lock and a maximum 15-minute deadline. Alpine's `crond`
service must be enabled. `--remove` removes only this managed cron block; the
previous crontab is backed up in the private state directory.

`prompts.json` controls the model and rotating scene bank; theme descriptors
supply the palette: American
Ghostic, the Declaration, the Delaware, Nighthawks, Yosemite, the Moon landing
and fictional historical spectacles. The default is `gpt-5.6-luna` with low
reasoning and native `gpt-image-2`, using the existing Codex ChatGPT login.
No npm, API key, external image service or copied authentication is required.
The subprocess ignores personal Codex configuration, disables shell commands,
and keeps workspace sandboxing enabled.

[Native image generation](https://learn.chatgpt.com/docs/image-generation?surface=cli)
uses included Codex limits and can draw from available account credits; this
job limits frequency and runtime, **not dollar cost**. It does not buy credits.
See [current model choices](https://developers.openai.com/codex/models) and
[usage limits](https://learn.chatgpt.com/docs/pricing#image-generation-usage-limits).

Logs, daily reservations and crontab backups stay in
`~/.local/state/oldbook/wallpaper-generation/`. New images, exact prompts, hashes
and model metadata land in the gallery and receive a local Fossil checkpoint
containing exactly the new PNG and JSON pair. Other edits and added files remain
pending. These checkpoints never sync or publish: the job requires `autosync off`,
refuses configured Fossil hooks and pending merges, and uses `--nosync --nosign`
without overriding forks, conflicts or locks. Hooks are not silently bypassed.

If checkpointing fails, the files remain available and the generation record
becomes `checkpoint-pending`. Later hourly checks discover both daily and manual
records and retry only the local checkpoint,
not image generation; resolve the reported repository condition to complete it.
Those retries do not change the current desktop. A newly generated manual image
can still become the wallpaper while its local checkpoint is pending.
Reinstallation from the repository restores the exact image bytes. Generating the
same prompt again is intentionally creative and is not deterministic.

## Create a new theme

Right-click the artwork widget to open **Ghost Gallery**, then type `new theme`:

- **Random new theme** invents a named collection, palette, and art direction.
- **New theme from a phrase/title** asks for a short idea, then interprets it as
  a collection and its first scene. Escape cancels without requesting generation.

Both run in the background through the existing Codex ChatGPT login. A busy
indicator and desktop notifications cover theme design and painting. Once ready,
its first wallpaper is selected. The named collection then appears among the
“Generate … artwork” choices for future paintings. These are gallery themes;
application colors and the default rotation theme remain independently configured.

Theme definitions live in `alpine/themes/<unique-id>.json`. The first successful
image checkpoint includes its new descriptor and PNG/JSON pair, with autosync off.
If painting fails, the saved collection remains available: select its named
Generate action to try an image again. If a checkpoint fails, files remain saved
and the existing pending-checkpoint recovery applies. Private request logs are
under `~/.local/state/oldbook/wallpaper-generation/manual/`.

Command-line equivalents:

```sh
python3 ~/.files/alpine/wallpapers/generate.py --manual --activate --new-theme
python3 ~/.files/alpine/wallpapers/generate.py --manual --activate --new-theme 'Moonlit library'
```
