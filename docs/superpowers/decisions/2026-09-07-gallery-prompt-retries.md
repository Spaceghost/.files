# Prompt-only themes and bounded generation retries

Ghost Gallery now offers **Create theme from prompt** directly beside the
paintings. Users supply creative direction; the model invents the collection
name, palette, art direction, and debut scene. **Paint in an existing theme…**
opens an alphabetical, searchable list of names, with duplicate names numbered.
Four paintings per page keep both navigation controls and all three actions
visible within nine rows. Escape cancels prompt entry without launching a job.

Theme design and image generation each get one initial attempt and up to three
retries, with waits of 2, 4, and 8 seconds. The existing exclusive lock spans all
attempts. A successful theme is reused during image retries. Each attempt has
its own log, and the job record retains attempt counts and errors. Invalid JSON
and missing or invalid native images are retryable. Authentication checks,
artifact writes, local checkpoints, and activation remain outside the retry
loop. A daily reservation covers the entire job; later cron wakes cannot start
another job after its retries are exhausted.

The reported missing desktop bar was absent during the initial process check
and subsequently reappeared while another Waybar maintenance task was active.
A later live check found the regular bar replaced by a diagnostic process using
`probe.jsonc` and `probe.css`. That exact diagnostic process was stopped and
restoration attempted under the existing session lock. A subsequent probe used
`probe2.css` from another Claude session's scratchpad, replacing the normal bar
again. Concurrent reloads also produced a GLib D-Bus assertion in the recovery
log. Stable restoration must wait for that session's live probes to stop; the
original exit cause was not established. Separately, the session regression test reproduced an early exit
when `.config/waybar` did not exist: writing `waybar-state.css` failed. Startup
now creates that directory before writing the stylesheet. The live directory
already existed, so this is not claimed as the cause of the reported exit.

Validation: all 511 desktop/deployment unit tests passed; ShellCheck passed for
`oldbook-session`. Retry tests cover success on the fourth attempt, exhaustion,
theme reuse, malformed native responses, invalid PNGs, retained attempt logs,
and checkpoint failures without repainting. Real Fuzzel renders were captured
under an isolated Sway compositor:

- [Gallery](../../../alpine/verification/gallery-prompts/gallery.png)
- [Existing themes](../../../alpine/verification/gallery-prompts/existing-themes.png)
- [Prompt entry](../../../alpine/verification/gallery-prompts/prompt.png)

Private test logs and the live bar screenshots remain under
`~/.local/state/oldbook/verification/theme-prompt-retries/`. No new model image
request was made for verification; recovery was tested with injected failures.
The installed gallery launcher is a symlink to this checkout, so the UI and
generation changes apply on its next invocation.

Recovery: restore the changed gallery scripts and `oldbook-session` from the
parent of this decision's Fossil check-in. Generated collections, images, and
private attempt records remain usable and need not be removed. Nothing is
published remotely by this change.
