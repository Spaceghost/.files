# YouTube in the launcher

Open **Oldbook YouTube** from Super+D, or choose **YouTube · desktop player &
PiP** in the command deck.

- **Search YouTube…** searches public videos. Type again in the results popup
  to filter the current page; next/previous controls browse more results.
- **My Watch Later / watchlist**, **My YouTube history**, and **My YouTube
  playlists** read the selected browser account. Choose a playlist to browse
  its videos, select a video to play it, or play the current page as a queue.
- **Account / sign in** selects a browser profile, opens YouTube for sign-in or
  account switching, offers browser fallbacks for the lists, or disconnects
  the player from the account. Sign-in stays in the browser.
- **PiP** floats the video across desktops; **Pin behind apps on desktop 1**
  returns it beneath windows. The existing pause, rewatch, keep/next, and remove
  from local queue controls remain available. EOF waits for a review decision.

The player reads the selected browser's current cookies through yt-dlp.
`~/.config/oldbook/youtube-account.json` stores only the browser/profile reference,
with mode 0600. No cookie export, password, or OAuth client is needed. Public
search does not use the browser session. Account cookies are used only for
YouTube URLs, including video playback. Firefox profiles with an existing cookie
database are offered by name; Chromium, Chrome, and Brave defaults are also
selectable. Multiple YouTube identities follow the browser's active/default
session; switch them in that browser.

Lists load on demand in pages of 50 with one lookahead item. Nothing polls the
account in the background or caches its complete history. Cancelling a list
leaves playback alone; selecting a video or page replaces the active queue.
An empty history can mean it is paused, cleared, or unavailable to the extractor.
If YouTube rejects a session, sign in again or use the browser fallback. Network
errors offer retry without changing the queue.

These are read-only account lists: local keep/remove decisions do not modify
Watch Later or other remote playlists, and player viewing is not uploaded to
YouTube watch history. Private URLs and selected titles stay in local state.

Verification and recovery:

```sh
cd ~/.files
python3 -m unittest discover -s alpine/tests -p 'test_youtube*.py' -v
python3 alpine/tests/verify_youtube_headless.py
```

To disconnect, select **Use without an account**. To revert the feature, restore
`oldbook-youtube` from its parent check-in and restart its service after stopping
playback. Saved local queues and named playlist links remain intact. See
`alpine/verification/youtube/library.json` for the current live-check limits.
