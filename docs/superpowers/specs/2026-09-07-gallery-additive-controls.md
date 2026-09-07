# Additive gallery controls and editable prompts

The artwork button keeps left-click next, right-click gallery, middle-click
pause/resume, scroll-up previous and scroll-down next. Super/Command+left-click
adds generation; Shift+left-click adds a prompt editor. Both left and right
modifier keys work. Shift takes priority when both modifiers are held, so editing
cannot accidentally request a painting. Modifiers do not change other gestures
or other panel buttons.

The gallery had grown to 18 paintings while the picker displayed 16 rows,
putting every appended control below the initial viewport. Increasing the cap
to 28 keeps the original order and shows the controls on the 1440×900 desktop.
Search and scrolling continue to reach additional paintings and theme actions.

The native CFFI widget reads a current modifier snapshot because an unfocused
layer-shell panel often receives no GDK keyboard state. Only devices advertising
normal keyboard capabilities contribute kernel key state. A held Meta bit from
a non-keyboard input device previously could redirect an ordinary left click
to generation; the isolated test reproduces that condition. This does not claim
that such a device was the cause on the user's physical desktop.

The prompt editor changes shared artwork guidance and existing scene titles and
descriptions. It preserves IDs, unknown fields and generation settings. Cancel
writes nothing. Save makes a private exact-byte backup, preserves file mode and
atomically replaces valid JSON after checking that the source has not changed.
It opens from Shift+click, the gallery menu or `oldbook-wallpaper edit-prompts`.
Opening and saving the editor never request generation.

Shared guidance now explicitly describes strong Christian faith, admiration for
the historical medieval Crusades and a love of history. The eight original
Space Ghost prompts remain, with cathedral pilgrimage, Crusader procession and
monastery chronicle scenes added. The same shared guidance reaches both the
painting prompt and the design prompt for random or phrase-based collections.

Verification uses real pointer and uinput modifier events inside a private Sway
session, with the exact test devices disabled in existing sessions before they
are created. All actions go to a recording stub. GUI verification uses a copy
of the prompt file; it saves no changes to the user's artwork during testing.
The signed native APK is rebuilt twice offline and retained by exact hash.

Recovery: the previous native package is
`oldbook-waybar-art-1.0.0-r0.apk`, retained in the package archive. Reinstalling it
restores the pre-Shift widget. Prompt backups live in
`~/.local/state/oldbook/prompt-backups/`; copy a selected backup to
`alpine/wallpapers/prompts.json` to recover earlier wording. Existing paintings
and their recorded generation prompts are unchanged.
