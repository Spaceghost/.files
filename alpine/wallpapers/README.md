# Ghost Gallery

All workspaces share one desktop image and one rotation timer. The desktop
changes artwork every 20 minutes. The Waybar art icon shows the
current painting and its story: click for the gallery picker, scroll to browse,
right-click for the next image, and middle-click to pause. **Super/Command +
left-click** paints an unpainted scene with a fresh mix and switches directly to it when ready.
**Shift + left-click** opens the prompt editor. **Super/Command + Shift +
left-click** creates a random new named theme and switches to its first painting.
**Super/Command + Shift + right-click** asks for a theme description, not a title.
The generator invents the name and creates a complete desktop theme and debut
painting. Empty input or Escape cancels. Themes must include application styling,
typography and layout as well as colors; incomplete designs are rejected.
Left and right Shift and Super keys work. Other right/middle clicks and
scrolling keep their usual actions even when a modifier is held.
The gallery also offers **Generate new artwork & switch to it**. The same controls
work from a terminal:

```sh
mbp-intel-wallpaper next
mbp-intel-wallpaper prev
mbp-intel-wallpaper pick
mbp-intel-wallpaper pause
mbp-intel-wallpaper generate
mbp-intel-wallpaper new-theme
mbp-intel-wallpaper prompt-theme
mbp-intel-wallpaper generate --theme none
mbp-intel-wallpaper generate --theme gruvbox-dark
mbp-intel-wallpaper edit-prompts
```

When a new theme and its painting finish, Ghost Gallery sends a desktop
notification with the theme name and painting preview. It says whether the
desktop switched or the work was saved in the gallery, and reports any pending
local checkpoint. Failed image generation does not announce finished artwork.

The gallery preserves the painting list and appends next/previous, pause/resume,
**Help & gallery controls**, and **Open command deck** alongside generation.
The picker shows up to 28 rows so the current gallery and its controls fit on
the laptop display. Scroll or type part of an action/title to find further entries.
**Edit artwork prompts** is available there too. Its shared guidance and scene
editor offers **Save** and **Cancel**. Saving affects future paintings and new
theme designs; it preserves scene IDs, generation settings and existing artwork.
The previous prompt file is backed up under
`~/.local/state/mbp-intel/prompt-backups/`. An editor opened before another change
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
The active link is `~/.local/share/mbp-intel/current-wallpaper.png`; deployment's
baseline `wallpaper.png` is separate. `mbp-intel-session` starts the rotation daemon
and refreshes the current artwork after Sway reload. A file lock prevents
multiple daemons, including when no graphical session is available yet.
`workspace_rotations: []` keeps selection, pause and the timer global; switching
workspaces does not change the painting. Previous per-workspace selections remain
saved but inactive under `~/.local/state/mbp-intel/wallpaper/workspaces/`.

## Scenes, insertions, mediums and never painting the same thing

`prompts.json` holds three switchable banks. **Scenes** describe the painting;
**insertions** describe how Space Ghost enters it — a tiny cameo, a stained
glass saint, a woven tapestry figure, a cast shadow, a kneeling donor portrait,
marginalia in an illuminated manuscript, or simply interrupting the moment with
the wrong equipment. One of each is combined for every painting, so the two
banks multiply into several hundred distinct requests.

**Mediums** decide how the image is actually made, so the gallery is no longer
all oil paintings: film stills, documentary and large-format photography,
screenprints, risographs, woodcuts, engravings, watercolour, gouache, matte
paintings, 3D renders, cyanotypes, tilt-shift, long exposures, aerials and
stop-motion. A scene that parodies one specific painting carries
`fixed_medium: true` and is never paired with a medium from the bank.

Each entry has an `enabled` switch, so any of them can be taken out of the
rotation without deleting its wording. `scene_selection`, `insertion_selection`
and `medium_selection` choose how the next one is picked:

- `shuffle` (the default) and `random` choose among eligible unused entries.
- `rotate` walks through the eligible entries in order.

Generation excludes every previously painted scene, across all themes. Changing
the insertion, medium, title, palette or variation seed does not make an old
scene eligible. The insertion/medium mix must also be unused. When the enabled
catalog has no fresh scene and mix left, the existing Codex login invents a new
subject, role and treatment in a text-only step before requesting the image.
There is no exhausted-bank reset to old scenes or mixes. Explicit `--scene`
selection also refuses a used scene or mix.

The designer receives previous subjects and mixes. Exact and lightly rewritten
duplicates are rejected before painting, including new themes that repeat a
previous scene or art direction. A rejected proposal gets up to three text-only
retries; failure leaves the current wallpaper in place. This checks prompt
novelty; visual resemblance in model-generated images cannot be guaranteed.

History lives in `~/.local/state/mbp-intel/wallpaper-generation/history.json` without
the former 2,000-record cutoff. Each request merges saved gallery sidecars,
curated artwork and local generation records, so restoring an older history
does not make saved scenes new again. Deleting a painting does not erase its
history. Failed image attempts remain excluded because an image may have been
produced remotely; a failed text-only design does not reserve a subject.

Every sidecar records the scene ID, scene and mix descriptions, and variation seed
alongside the full prompt. The prompt editor (**Shift+click** on the artwork
icon) edits both banks and their selection modes on separate tabs.

```sh
python3 alpine/wallpapers/generate.py --manual --activate
python3 alpine/wallpapers/generate.py --manual --scene observatory-night --medium cyanotype
```

## Reverence

The shared guidance carries hard limits that override everything else in a
request. Space Ghost and his companions are never depicted as Christ, God, the
Holy Spirit, an angel, a saint or any holy person; they never receive a halo,
nimbus or devotional attribute, are never the object of veneration or worship,
and are never shown as clergy performing a sacrament. Scripture, the
crucifixion, the Mass, the Eucharist, baptism and prayer are never parodied, and
altars, crucifixes, icons and relics are never props. Where a church or sacred
art appears it is rendered straight and reverently, and the humour comes only
from Space Ghost being somewhere he plainly does not belong.

The insertion bank follows the same rule: the stained-glass and commemorative
styles are explicitly civic rather than ecclesiastical, and the statue and
marginalia styles state where they may not appear. `test_prompt_catalog.py`
guards these limits against reappearing.

## Deleting a painting

**Delete this painting permanently** in the gallery actions removes the image
and its sidecar after asking for confirmation, moving the desktop on to the next
artwork first so it never points at a missing file. Only generated artwork under
`alpine/assets/gallery/` can be deleted; curated entries listed in
`gallery.json` are refused. The removal is staged in Fossil and stays pending
for review. The same operation without a prompt is `mbp-intel-wallpaper delete`.

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

Manual requests run in the background and use an unpainted scene from
`prompts.json`, or invent a fresh scene and mix when the catalog is exhausted.
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
cron jobs and add an hourly wake check. The generator reserves **one job per
local calendar day**, including failures. Each job retries failed generation up to
three times after the initial attempt, waiting 2, 4, then 8 seconds. Later cron
wakes cannot restart an exhausted job. It uses an exclusive lock across retries
and a maximum 15-minute deadline per image attempt. Alpine's `crond`
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
`~/.local/state/mbp-intel/wallpaper-generation/`. New images, exact prompts, hashes
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

Right-click the artwork widget to open **Ghost Gallery**:

- **Create theme from prompt** is on the first screen. Describe what you want;
  the generator invents the name, palette, art direction, and first scene.
  Escape cancels without requesting generation.
- **Paint in an existing theme…** opens a separate alphabetical picker; type to
  filter the theme names, then select one for another painting.
- **Random new theme**, under **Gallery actions…**, invents a collection without a prompt.

Both run in the background through the existing Codex ChatGPT login. A busy
indicator and desktop notifications cover theme design and painting. Once ready,
its first wallpaper is selected. The named collection then appears in the
existing-theme picker for future paintings. These are gallery themes;
application colors and the default rotation theme remain independently configured.

Theme definitions live in `alpine/themes/<unique-id>.json`. The first successful
image checkpoint includes its new descriptor and PNG/JSON pair, with autosync off.
Theme design and painting each retry up to three times after the initial attempt.
Notifications show retry progress and each attempt keeps a separate private log.
A successful theme design is reused for all image retries. If painting still
fails, the saved collection remains available in the existing-theme picker.
If a checkpoint fails, files remain saved
and the existing pending-checkpoint recovery applies. Private request logs are
under `~/.local/state/mbp-intel/wallpaper-generation/manual/`.

Command-line equivalents:

```sh
python3 ~/.files/alpine/wallpapers/generate.py --manual --activate --new-theme
python3 ~/.files/alpine/wallpapers/generate.py --manual --activate --new-theme 'Moonlit library'
```
