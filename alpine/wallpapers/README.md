# Ghost Gallery

The desktop changes artwork every 20 minutes. The Waybar art icon shows the
current painting and its story: click for the next image, scroll to browse,
right-click for a gallery picker, and middle-click to pause. The same controls
work from a terminal:

```sh
oldbook-wallpaper next
oldbook-wallpaper prev
oldbook-wallpaper pick
oldbook-wallpaper pause
```

Edit `gallery.json` to change the interval or curated pool. Add images with JSON
sidecars under `alpine/assets/gallery/`; each entry has `id`, `title`, `file`,
`description`, and ideally `sha256`. Paths are relative to the checkout and must
remain inside `alpine/assets/`. Generated entries are discovered automatically.
The active link is `~/.local/share/oldbook/current-wallpaper.png`; deployment's
baseline `wallpaper.png` is separate. `oldbook-session` starts the rotation daemon
and refreshes the current artwork after Sway reload. A file lock prevents
multiple daemons, including when no graphical session is available yet.

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

`prompts.json` controls the model, palette and rotating scene bank: American
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

If checkpointing fails, the files remain available and the daily reservation
becomes `checkpoint-pending`. Later hourly checks retry only the local checkpoint,
not image generation; resolve the reported repository condition to complete it.
Reinstallation from the repository restores the exact image bytes. Generating the
same prompt again is intentionally creative and is not deterministic.
