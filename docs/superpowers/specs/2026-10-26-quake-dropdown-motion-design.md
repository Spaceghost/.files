# Quake-style dropdown motion

## Goal

Make the persistent Ghostty and Foot consoles behave like an attached Quake or
Guake drawer: full usable output width below Waybar, square top corners, modest
bottom-only rounding, and compositor-native vertical reveal/dismiss motion that
can reverse cleanly when toggled mid-flight.

## Behavior

- A Sway mark identifies both persistent consoles without coupling the feature
  to an application ID in compositor code.
- Showing reveals the existing scratchpad container downward from just above its
  settled position. Hiding moves it upward and parks it only after completion.
- A second toggle during dismissal reverses from the current interpolated
  position. The terminal process and shell survive every toggle.
- The drawer fills the focused workspace's usable width and starts at its usable
  top edge, including non-zero output origins.
- Drop-down top corners are square, bottom corners use a 14 px radius, and the
  drop-down shadow is suppressed. Other windows keep the global decoration.
- Workspace changes crossfade in place. Ordinary window open/close/move motion
  remains short and compositor-native.

## Compatibility and rollout

The launcher probes the installed compositor atomically. The r5 command is used
when available; an already-running r4 or stock Sway session falls back to the
existing scratchpad commands. Install the signed r5 APK without restarting the
active compositor; the native path becomes active at the next graphical login.

## Proof

Unit tests cover configuration, command documentation, patch scope, launcher
probing, and multi-output geometry. A private stock-Sway session proves process
persistence and fallback behavior. A private headless SwayFX session measures
reveal, dismissal, reversal, asymmetric corners, workspace styles, settling,
and idle CPU from captured frames.
