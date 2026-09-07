# Accessibility and direct app actions

Superhold `0.2.0.dev0` provides a searchable, clickable shortcut guide. A menu
launcher opens it without a keyboard gesture, and a selected shortcut is sent
to the original application through `wtype`. The guide can stay open until focus
moves away. These interaction features are implemented; live AT-SPI discovery
and direct accessible actions remain a separate future adapter.

## AT-SPI can supply app actions

Linux applications can expose accessible controls, actions, and some associated
key bindings through AT-SPI over D-Bus. An adapter can invoke an exposed action
directly, without simulating a keyboard shortcut or moving the pointer. See the
upstream [Action interface](https://gnome.pages.gitlab.gnome.org/at-spi2-core/libatspi/iface.Action.html).

On 2026-09-07, the earlier feasibility investigation used headless Sway and a
private D-Bus session on Alpine to test GTK3 and Qt6 controls:

| Test control | Action | Reported binding | Invocation |
| --- | --- | --- | --- |
| GTK3 button | click | `<Alt>a` | Callback observed |
| Qt6 button | Press | `Alt+A` | Callback observed |
| Qt6 button | SetFocus | `Alt+A` | Action returned success |

That test used `Atspi.Action.do_action()`, with no synthetic keyboard or pointer
events. It establishes toolkit feasibility, not complete application coverage
or a shipped Superhold adapter. Accessibility must be enabled in the target
session, and applications must publish useful objects. See
[Qt accessibility activation](https://doc.qt.io/qt-6/qaccessible.html).

Accessibility experiments must isolate HOME and all XDG directories as well as
D-Bus and Wayland. Use a memory settings backend and propagate its environment
to D-Bus activation. A private bus alone does not isolate dconf persistence.
Superhold's current settings screen does not enable accessibility or alter the
session's accessibility preferences.

## Extend the current action guide

- Query the original focused app's accessible objects before mapping the guide.
  Show discovered actions first, then compositor and other contextual controls.
- Keep the accessible object identity, action identity, and enabled state with
  each result. Refresh and validate them immediately before activation.
- Invoke an accessible action directly when the application exposes it. Label
  profile-based native keyboard sequences as a different source with partial
  coverage and their existing timing limitations.
- Retain click selection, panel launch, and search. A configurable mouse-button
  trigger, touch interaction, or optional voice selection would need additional
  implementation and testing.
- Keep activation explicit. Opening, searching, previewing, and inspecting the
  list must never execute an action.

[Shortcat](https://shortcat.app/) primarily reduces mouse use through keyboard
selection. The same accessible action data can support a palette intended to
reduce keyboard use, which is the direction of Superhold's clickable guide.

## Portability and coverage

AT-SPI is separate from the Wayland display protocol. Wayland does not expose a
universal index of every app's shortcuts. The
[GlobalShortcuts portal](https://flatpak.github.io/xdg-desktop-portal/docs/doc-org.freedesktop.portal.GlobalShortcuts.html)
registers an application's global shortcuts; it is not an index of all other
applications' menus. Superhold currently uses Sway IPC and local profiles rather
than a portal for contextual shortcut discovery.

LXQt supports multiple compositors. Qt accessibility offers a basis for app
adapters, but focused-window discovery, global triggers, positioning, and
lock/session handling still need a supported compositor backend. The current
target is LXQt with Sway, and full LXQt testing is still outstanding. See
[LXQt Wayland sessions](https://github.com/lxqt/lxqt/wiki/Wayland-Session).

Terminal apps, canvas controls, custom widgets, and lazily created menus can
expose incomplete accessibility information. Missing actions must remain
unavailable. The current keyboard backend already checks original-target and
session identity and waits for held keys, but focus checks and Wayland keyboard
injection are not atomic. An AT-SPI adapter must validate its own object-lifetime
and action-delivery behavior rather than inherit those checks as proof.
