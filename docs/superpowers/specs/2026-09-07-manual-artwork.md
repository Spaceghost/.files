# Manual artwork generation

The user requested Super/Command+left-click on the artwork bar icon to generate
one new painting and switch to it, plus the same command in the gallery. Their
follow-up requires additions to preserve existing commands, help and choices.

## Behavior

Keep normal next/previous, right-click gallery, and middle-click pause behavior.
Preserve painting labels and relative order. Append gallery navigation, help,
the existing desktop command deck, and generation. The command deck retains all
its original actions and adds a help entry.

The UI starts a detached worker. Manual requests use individual private records
and the same exclusive lock as cron, without changing the daily reservation.
Concurrent clicks report busy instead of queuing additional requests. A held
lock drives status, so abandoned state files do not leave a stuck indicator.

The existing Codex ChatGPT/native-image path generates exactly one image with
the configured model and timeout. Validate and save the PNG/provenance, attempt
a scoped local Fossil checkpoint, then select that exact gallery ID. Preserve
rotation pause and reset its deadline. Generation failure retains the wallpaper;
activation failure retains the saved artwork and its successful checkpoint.
Hourly checkpoint retries include manual records and never switch the desktop.

## Bar integration

Waybar's ordinary custom module does not expose click modifier state. Its
documented CFFI extension supplies one native artwork widget. Layer-shell bars
without keyboard focus also lack reliable GDK modifier state, so the widget
checks Linux keyboard state at the click and retains GDK state as a fallback.
Keep this source and a reproducible signed Alpine package in Fossil. It must
not introduce global mouse bindings or steal focus from applications.

## Verification

Exercise daily/manual isolation, lock contention, exact selection, generation
and activation failures, checkpoint recovery and retained menu actions with
focused tests. Verify actual pointer/modifier events in an isolated compositor
against a stub command, without billed generations. Run one real manual image
request and check the resulting artifact, Fossil commit and active desktop ID.
Build the widget twice, compare artifacts, archive the updated APK closure, and
inspect the live gallery and bar after deployment.
