# Accessibility and direct app actions

Superhold currently displays shortcut references. The features below are a
possible next step, not capabilities of the release candidate.

## AT-SPI is the useful app interface

Linux applications can expose accessible controls, their available actions and
some associated key bindings through AT-SPI over D-Bus. A client can invoke an
exposed action directly, without simulating a keyboard shortcut or moving the
pointer. See the upstream [Action interface](https://gnome.pages.gitlab.gnome.org/at-spi2-core/libatspi/iface.Action.html).

On 2026-09-07, a throwaway test on Alpine Linux with headless Sway and a private
D-Bus session verified the installed GTK3 and Qt6 implementations:

| Test control | Action | Reported binding | Invocation |
| --- | --- | --- | --- |
| GTK3 button | click | `<Alt>a` | Callback observed |
| Qt6 button | Press | `Alt+A` | Callback observed |
| Qt6 button | SetFocus | `Alt+A` | Action returned success |

The test used `Atspi.Action.do_action()`, with no synthetic keyboard or pointer
events. This establishes toolkit feasibility, not complete application coverage.
Accessibility must be enabled in the target session, and applications must
publish useful accessible objects. See [Qt accessibility activation](https://doc.qt.io/qt-6/qaccessible.html).

Accessibility settings tests must isolate HOME and all XDG directories as well
as D-Bus and Wayland. Use a memory settings backend and pass its environment
into D-Bus activation; a private bus alone does not isolate dconf persistence.

## A design for less keyboard use

- Provide a panel launcher or mouse-button trigger that opens a persistent
  action palette. Holding Super remains an optional reference gesture.
- Show actions from the focused app first, followed by compositor and other
  contextual controls. Select an action by clicking or touch; voice selection
  could be a separate optional input method.
- Invoke an accessible action by its application/object identity. Refresh and
  validate that identity and the enabled state before acting.
- Use compositor IPC for window/workspace controls and app-specific adapters
  where available. Keep static shortcut profiles explicitly partial.
- Keep activation explicit. Searching, previewing and reading a list must not
  execute an action.

[Shortcat](https://shortcat.app/) is primarily a keyboard-driven interface that
reduces mouse use. The same accessible-action data could serve either that
interaction style or a palette designed to reduce keyboard use.

## Portability limits

AT-SPI is separate from the Wayland display protocol. Wayland does not provide
a universal list of all in-app shortcuts. The [GlobalShortcuts portal](https://flatpak.github.io/xdg-desktop-portal/docs/doc-org.freedesktop.portal.GlobalShortcuts.html)
registers an application's global shortcuts; it is not a desktop-wide app-menu
index. The [wlr portal backend](https://github.com/emersion/xdg-desktop-portal-wlr)
currently implements Screenshot and ScreenCast only.

LXQt supports multiple compositors. Qt's accessibility support is a useful
foundation for LXQt applications, but focused-window discovery, positioning,
global triggers and lock/session handling still need backend-specific support.
The initial Superhold release target is LXQt with Sway. Other LXQt sessions must
be tested independently; see [LXQt Wayland sessions](https://github.com/lxqt/lxqt/wiki/Wayland-Session).

Terminal applications, canvas controls, custom widgets and lazily created menus
can expose incomplete data. An absent accessibility action must remain
unavailable rather than be presented as discovered. Screenshot/coordinate or
synthetic-input fallbacks would need their own design and verification.
