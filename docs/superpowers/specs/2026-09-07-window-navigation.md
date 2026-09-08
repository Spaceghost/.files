# Predictable window navigation

Super+Tab and Alt+Tab select all ordinary windows across every workspace in
actual recent-focus order. The first press selects the previous window; repeats
advance a frozen list, Shift reverses, releasing the initiating modifier
commits, and Escape cancels without focus movement. Agent-only navigation
remains available on Super+i and Super+Shift+i. Ordinary application Tab and
Ctrl+Tab are not intercepted.

A warm per-Sway-session controller tracks real focus events and owns one GTK4
layer overlay. Its selection model checks window ID, PID and app ID before
commit. A new gesture cannot inherit a stale modifier or stale candidates. The
overlay is dismissed before focus is committed; startup, disconnect, cancellation
and mode takeover release its keyboard ownership. MRU history consists of live
window identities and does not record user content.

The all-window carousel uses angled cards, soft shadows and the active theme,
without pixel outlines. GTK frame-clock animation follows the display refresh
rate and stops when settled. The compositor advertises per-toplevel capture,
GET_TREE supplies foreign_toplevel_identifier, and installed grim supports -T.
Previews are captured asynchronously from those exact windows, including hidden
workspaces, without navigating to them. Pending captures cannot hold up modifier
release. At most two captures run at once; runtime previews are never committed.

Four-finger down restores a valid show-desktop session. With no hidden windows,
it opens the carousel in persistent mode; arrows, Tab, scrolling and clicking
select, Enter commits and Escape closes. Leaving an exposed workspace cancels
the old animation and restores/clears its state while preserving the user's
requested destination. Intentional internal show/restore swaps are distinguished
from external navigation. The real windows remain in their original workspace.

Super+Shift+Space exits fullscreen, enables floating, and centers the window in
90 percent of its workspace's usable rectangle, retaining at least 24 logical
pixels of margin. Repeated use reapplies that size. Existing grow/shrink controls
remain unchanged. STRATA stays on numeric 10, last after 1–9, reached by Super+0.

Validation uses pure selection/state tests and private native Sway windows. It
covers global MRU across interleaved workspaces, reverse and quick gestures,
closed/reused windows, modifier-release ordering, exact toplevel previews,
workspace-leave recovery, restore/carousel dispatch and near-full geometry.
Native screenshots use only synthetic windows. Live activation preserves
application windows and restarts only affected desktop helpers.
