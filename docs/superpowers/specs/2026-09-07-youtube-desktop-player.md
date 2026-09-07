# Launcher-controlled YouTube review player

The pinned player uses mpvpaper's bottom layer on the output currently showing
workspace 1. It does not change wallpaper files or terminate wallpaper services.
When that workspace is hidden, the renderer stops and saves its playback position.
PiP mode uses a dedicated native-Wayland mpv window with Sway floating/sticky
rules. Switching modes preserves playback position and pause state. Desktop
mode resumes when workspace 1 becomes visible again; PiP follows workspaces.

## Controls

Open **YouTube · desktop player & PiP** in the ghost command deck, or search
**Oldbook YouTube** in Super+D. The menu can open a video/playlist URL, save
named playlist shortcuts, resume, play/pause, switch desktop/PiP modes, rewatch,
keep and advance, remove from the local queue and advance, or stop playback.

Only one video is loaded at a time. At EOF the player holds the final frame and
sends a desktop notification. It waits for an explicit review decision before
loading the next item. Keep and Remove record different local decisions.
Remove never modifies YouTube. Named playlist URLs and queue/progress live in
private HOME configuration/state files, outside Fossil. Playback resumes only
when requested after a fresh session; the launcher starts one serialized daemon.

The user's oldbook/watchlist URLs were not provided. **Save a named playlist**
lets them add these and other sources directly from the launcher. No account
cookies or credentials were imported. Private playlists requiring sign-in are
not yet configured. The earlier terminal-background proposal is superseded by
this pinned-player design. Ghostty offers static background images and shaders,
but has no built-in YouTube video-background playback.

## Implementation and validation

- yt-dlp expands public playlists, capped at 500 items, into individual video
  entries. Empty playlists are rejected rather than delegated to mpv autoplay.
- mpv is configured for at most 720p when available, with audio and safe automatic
  hardware decoding. Native Wayland is explicit for PiP so its Sway identity is
  stable. The service owns its decoder process group and private IPC sockets.
- Four unit tests cover decisions, empty lists and output selection. Real
  isolated Sway/mpvpaper/mpv checks cover background rendering, hiding outside
  workspace 1, PiP, pause/position retention, EOF hold and explicit advancement.
  Run: python3 alpine/tests/verify_youtube_headless.py
- Evidence and screenshots: alpine/verification/youtube/. A public Blender
  Foundation YouTube video was extracted and one frame plus audio decoded with
  the production format selection at 1280×720. It was not played on the user's
  live desktop. The launcher daemon is ready but has no selected user playlist.
- Sway, SwayFX, desktop-entry and Python syntax checks passed, as did disposable
  HOME deployment. Package snapshot c0a227c1d5c4ea962d29 archives the full 984-APK
  installed closure, including yt-dlp, its JavaScript runtime and FFmpeg.
- Reboot persistence and the user's actual playlists remain unverified.

## Recovery

Use Stop player in the launcher before removing the integration. Terminate only
this helper's serve process to stop its controller; it cleans up its own renderer.
Remove the dedicated Sway app rule and launcher/desktop entries to disable it.
Keep ~/.local/state/oldbook/youtube/queue.json to retain progress and decisions;
keep ~/.config/oldbook/youtube-playlists.json to retain named playlists.
Package artifacts can be recovered through alpine/bin/package-archive using the
saved lock. No remote playlist edits need to be reversed.

The experimental scalloped ghost button was undone at the user's request; the
original font glyph, gradient and click behavior are retained.
