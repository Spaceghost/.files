# Standalone interactive Superhold

The standalone checkout is independent of the installed MBP Intel overlay. Do not
install it, alter desktop startup, or restart the original service during this
work. The intended remote is a dedicated Spaceghost/superhold repository.

The default guide stays open after Super is released and closes when focus moves
away. A settings window and versioned XDG JSON file also offer release-to-close
and adjustable hold/delivery timing. Capture the original app before the guide
receives focus, then freeze that context while browsing. Search matches shortcut
keys, descriptions, app and section text; Enter activates the selected result.

Rows expose individual native keyboard alternatives. Clicking or Enter hides the
guide, waits for all physical keys to be released, verifies the original window
and active session, then sends bounded native Wayland key events. Never replay
Sway or tmux command strings. Reject unsupported physical/device-specific bindings
and stale targets explicitly. Native focus and input are separate protocols, so
the final focus check cannot provide an atomic cross-protocol guarantee.

Validate lifecycle, cancellation and search with deterministic tests; exercise
focus loss, native delivery and settings in a private headless Sway session.
Package application-menu entries for the guide and settings, plus optional LXQt
and Sway startup files. Publish only to the dedicated repository when available.
