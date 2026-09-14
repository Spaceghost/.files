# Catbed

One command interface for deliberate input parking, targeting the existing
Sway Wayland session on Linux first. Catbed is a cat guard, not an
authentication lock. It cannot guarantee
that a laptop is physically safe as a bed: vents must remain clear and
hardware thermal protection must remain enabled.

## Development status

The distribution now bundles the existing Sway Wayland guard, its local Python
dependencies, and theme JSON without requiring an installed `oldbook-watch` or
dotfiles checkout. Native GTK/Wayland dependencies remain system requirements.
Builds also include
the existing Linux boot guard, OpenRC service, SysRq helper, thermally guarded
fan helper, and ACPI power handler. Their canonical sources remain in the
checkout rather than being maintained twice. The privileged system installation
workflow has not yet been consolidated, so capability reporting still marks the
overall package as not self-contained. Completing installation and lifecycle
integration remains required, not an optional extension of this deliverable.

Only the current Sway Wayland backend is in implementation scope. There is no
X11 fallback, generic Wayland-compositor integration, Windows backend, or macOS
backend. Those can be added later when there is a concrete platform to support;
no speculative backend implementations are included. Unsupported platforms can
only receive an explicit unsupported response from the command interface.

## Commands

```sh
catbed capabilities
catbed start
catbed status
catbed stop
catbed system status
catbed export-system /tmp/catbed-system-files
```

`start` runs in the foreground and delegates keyboard ownership proof to the
existing guard. Hold Super+Shift+Escape for one second with no other key down
to leave it. `stop` is the terminal recovery route. Locking and unlocking do
not deliberately stop the desktop guard; the authentication locker temporarily
owns the keyboard and the guard waits for it to return.

System mutations require an explicitly privileged invocation:

```sh
catbed system run --user jack
catbed system recover
catbed system shutdown
```

Do not start the system stage in a live desktop merely to try the command: it
grabs internal input devices. `shutdown` inhibits supported kernel input
devices; it does not itself shut down the operating system. `recover` clears
that inhibition. Normal boot integration uses the existing OpenRC service.

`export-system` creates a new private directory containing the bundled system
files and a manifest of intended installation destinations. It refuses an
existing destination and never copies files into `/etc` or `/usr/local`.
The bundled OpenRC service currently targets this machine's `jack` account;
it is not a portable installer for other machines.

## Distribution builds

Build from this directory using a Python build frontend. The build hooks
embed canonical Linux helper sources into both wheels and source archives.
An extracted source archive contains those resources and does not need the
dotfiles checkout to rebuild them. Editable/source-tree execution lacks the
generated resources, and `export-system` reports that explicitly.

The source archive and wheel have been built successfully, including building
the wheel from the extracted source archive. An unpacked-wheel check outside
the checkout verified resource export, matching helper payloads, permissions,
and refusal of invalid requests. The host lacks `pip`, so installer-generated
command wrappers remain untested. These checks are not evidence of successful
hardware boot or shutdown handoff.

## Protection boundaries

- Desktop input requires Sway, Wayland, GTK4, GTK4 layer-shell, and PyGObject.
- The system helper starts after local filesystems, not in firmware or at the
  encrypted disk prompt.
- Boot handoff requires a live desktop guard with proven keyboard ownership.
- Quiet-fan requests remain subordinate to thermal and heartbeat recovery.
- Long-press hardware power overrides cannot be blocked by this software.
- Capability reporting describes implementation, not current input ownership.

## Consolidation still required

- Verify the bundled desktop runtime in an isolated Sway session, including
  its palette and layer-shell dependencies without access to the checkout.
- Complete explicit system installation and recovery for the bundled helpers,
  without privileged side effects during Python installation.
- Keep existing `oldbook-*` entry points as compatibility adapters.
- Exercise the installed package outside the checkout and verify stage
  handoff, lock/unlock persistence, failure recovery, and hardware limits.

No live input grab, service activation, reboot, or fan change is performed by
installing or importing this Python package.
