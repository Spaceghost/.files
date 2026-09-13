package rice

// The list. A new feature is a new entry at the top: the loader sorts by
// date, newest first, and keeps file order within a day. Render it with
// `cue export ./alpine/cue/rice -e rice --out json`; see README.md.
rice: {
	version: 1
	entries: [
		{
			id:      "theme-workshop-on-the-deck"
			title:   "New themes are typed into the deck"
			date:    "2026-09-13"
			summary: "Super+Shift+D, Theme, New theme: a few words become a whole theme, applied at once, unpainted."
			trigger: "Super+Shift+D, Theme, New theme · describe it here, then type a description and press Enter."
			detail:  "oldbook-theme create designs the theme as text (Codex, then Claude, then the Alienware), chooses the nearest installed pointer set, builds its own folder icons and applies it like any theme: the visible desktop at once, GRUB and the boot console in the background with a notice either way. No painting is asked for unless debut_painting is true in ~/.config/oldbook/painting.json; the same file's scheduled key switches the daily painting back on. New theme · surprise me needs no description."
		},
		{
			id:      "catbed-mode-is-yours"
			title:   "Catbed mode is yours alone to end"
			date:    "2026-09-13"
			summary: "Super+Shift+Escape parks every key and the pointer. Only that chord, held a second, lets go."
			trigger: "Super+Shift+Escape; then hold Super+Shift+Escape for a second with no other key down to return."
			detail:  "A cat guard, not a lock: the desktop stays visible and running while a transparent overlay takes the keyboard and pointer and a Sway mode that binds nothing takes the compositor's own keys. Nothing ends it for you -- not the cat getting up, not a lock and unlock, not a reload. While it is up the power, suspend and hibernate keys and SysRq are held as the lock holds them, from ~/.config/oldbook/catbed.json. A wedged guard is ended with 'oldbook-watch stop' from a terminal or over SSH."
			run: ["oldbook-watch", "start"]
		},
		{
			id:       "agent-picker-names-the-model"
			title:    "The agent picker says what it will run"
			date:     "2026-09-13"
			summary:  "Super+N leads with the best Codex and Claude, model and effort named, and opens on the prompt."
			trigger:  "Super+N, Enter, Enter: the best Codex opens where you used it last, straight on its prompt."
			detail:   "Each preset's model and effort are fields the line prints and the command carries; lead, quick and remember_workdir in ~/.config/oldbook/agents.json say which presets lead, which one Super+Ctrl+N starts and whether the directory list opens on last time's. A preset marked trust has its directory accepted with Claude Code or Codex before the session exists, so neither stops on its trust screen; set trust to false on a preset to be asked again."
			run: ["oldbook-agents", "show"]
			terminal: true
		},
		{
			id:      "animation-first"
			title:   "Animation takes the machine first"
			date:    "2026-09-13"
			summary: "The compositor draws in realtime and the desktop's own sessions outweigh any agent or build."
			trigger: "Start several agents at once, then fly the caption strip between a floating and a tiled window."
			detail:  "oldbook-ui-priority, asked through doas when the session and each drawing daemon start, runs the render thread at the lowest realtime priority with children reset, the desktop's threads at nice -15 and its session groups at nice -20. doas oldbook-ui-priority --check --session $SWAYSOCK prints every thread's policy; removing the helper from /usr/local/sbin stops it being asked."
		},
		{
			id:      "caption-names-the-agent"
			title:   "The strip names what your agent is doing"
			date:    "2026-09-13"
			summary: "A Claude or Codex window's caption carries its title plus one still glyph for its state."
			trigger: "Focus a Claude Code or Codex terminal that is mid-permission-prompt, then read the bottom strip."
			detail:  "The glyph is loading.py's own alphabet -- a blocked mark when a routing record says the agent is waiting on you, a single still spinner frame when Codex reports its own run state and nothing is waiting, nothing otherwise. It changes only when that real state changes, never on a clock: Claude embeds no run-state string of its own, so a Claude window shows the waiting mark or nothing, not a guess dressed as a fact. Toggle with the agent_status key in ~/.config/oldbook/decoration.json."
		},
		{
			id:      "theme-reaches-the-boot-chain"
			title:   "Themes reach GRUB and the boot console now"
			date:    "2026-09-13"
			summary: "Switching themes now reaches GRUB and the boot console automatically, not just the desktop."
			trigger: "oldbook-theme use catppuccin-mocha, then check /boot/grub/themes/ghost-planet/theme.txt: desktop-color now reads that theme's own background."
			detail:  "Before this, only the console palette file regenerated automatically; build-grub-theme and doas install-boot-console needed a human to remember them by hand afterward, so every theme but the one that got that manual treatment once left GRUB and the boot console on gruvbox regardless of what was active everywhere else. A theme now is not allowed to count as complete while any boot-time surface still needs an unenforced follow-up command."
		},
		{
			id:      "landing-ripple"
			title:   "The strip strikes the water"
			date:    "2026-09-13"
			summary: "The caption strip landing in its band sends rings up the lower screen for under a second."
			trigger: "Focus a floating window, then a tiled one"
			detail:  "The rings refract a photograph of the screen; nothing is drawn where the water is still. Tune or switch off the ripple object in ~/.config/oldbook/decoration.json. Sheds at battery-low."
		},
		{
			id:      "ghost-wander"
			title:   "The Ghost badge floats in place"
			date:    "2026-09-13"
			summary: "The Space Ghost badge in the bar bobs gently in its own cell, and holds still at low battery."
			trigger: "Look at the Space Ghost badge in the bar."
			detail:  "A CSS float cycle that oldbook-waybar-ghost-class switches on and off; the glyph itself never changes, and it sheds at battery-low. Off: \"wander\": false in ~/.config/oldbook/ghost.json."
		},
		{
			id:      "powerline-chains"
			title:   "Powerline chains in prompt, tmux and bar"
			date:    "2026-09-13"
			summary: "The prompt, the tmux status line and the bar draw their segments as rounded powerline chips."
			trigger: "Open a terminal in a checkout and read the prompt, then the tmux status line and the bar."
			detail:  "Rounded Nerd Font separators in every theme profile's starship.toml, .tmux.conf and Waybar config. The caption strip's own separators are a separate setting, off by default."
		},
		{
			id:      "claude-alert-lands-on-session"
			title:   "Claude's alerts lead to its session"
			date:    "2026-09-13"
			summary: "Clicking a Claude waiting-on-you alert lands on its tmux pane, and visiting clears the alert."
			trigger: "When a Claude Code session asks for your attention, click its notification."
			detail:  "oldbook-claude-notify-focus finds the window already showing that pane, or selects the pane in tmux and opens a terminal attached to the session. A Stop or a fresh prompt closes the alert as well; a session nothing can locate leaves it alone."
		},
		{
			id:      "wifi-deck"
			title:   "A Wi-Fi deck for away from home"
			date:    "2026-09-09"
			summary: "The network module lists nearby networks, saved and loudest first, and joins one from the menu."
			trigger: "Left-click the network module in the bar."
			detail:  "Right-click opens Transmission Status and middle-click an Air Survey. Open networks draw a different glyph from encrypted ones. It drives wpa_supplicant through its control socket rather than restarting it, and a password that failed is removed rather than saved."
		},
		{
			id:       "lastlight"
			title:    "The last light of a dying battery"
			date:     "2026-09-09"
			summary:  "Below 25 percent unplugged the keys breathe faster, the edges close in and the screen labours."
			trigger:  "Unplug and let the charge fall below 25 percent; plugging back in runs it backwards."
			detail:   "The warning deepens at 10 percent and again at 4. It is the one effect the power ladder never sheds. Each channel switches off alone in ~/.config/oldbook/lastlight.json: enabled, keys, edges and backlight."
			run: ["oldbook-lastlight", "table"]
			terminal: true
		},
		{
			id:      "claude-code-theme"
			title:   "Claude Code wears the theme"
			date:    "2026-09-09"
			summary: "Every theme carries a Claude Code palette, and an open session repaints when the theme changes."
			trigger: "With Claude Code's theme set to oldbook, switch desktop themes with oldbook-theme use."
			detail:  "All seventy of Claude Code's colour keys come from the same recolouring path as the terminals and the bar. oldbook-theme reports whether the file is deployed and whether Claude's settings select it."
		},
		{
			id:       "signal-margin"
			title:    "Dial ticks in the empty desktop"
			date:     "2026-09-09"
			summary:  "An opt-in backdrop draws still tuning-dial ticks in the space no window or reading card uses."
			trigger:  "oldbook-edges on"
			detail:   "It never animates and takes no input. oldbook-edges status reports it; oldbook-edges off stops it and puts the preference back."
			run: ["oldbook-edges", "status"]
			terminal: true
		},
		{
			id:      "notification-finds-its-window"
			title:   "A notification leads to its window"
			date:    "2026-09-09"
			summary: "Clicking a notification focuses the window that sent it, workspace and all, or does nothing."
			trigger: "Click a notification from an application that has a window open."
			detail:  "It matches by desktop entry, then display name, then a long enough window title, and a click with no confident match does nothing rather than focus the wrong window."
		},
		{
			id:      "catppuccin-mocha"
			title:   "Catppuccin Mocha, a second full theme"
			date:    "2026-09-09"
			summary: "A complete pastel theme with a design of its own, reaching every surface Gruvbox does."
			trigger: "oldbook-theme use catppuccin-mocha"
			detail:  "oldbook-theme use gruvbox-dark switches back. The profile is alpine/themes/profiles/catppuccin-mocha."
		},
		{
			id:      "strip-merges-into-its-window"
			title:   "The strip merges into its window"
			date:    "2026-09-09"
			summary: "Attached along the bottom, the caption strip and its window read as one shape rather than two."
			trigger: "Focus a floating window and look where its bottom edge meets the strip."
			detail:  "The strip climbs exactly the theme's corner radius and fills the two corners the compositor clipped, and clicks there still reach the window. A floating window left sitting in the band is moved just clear of it."
		},
		{
			id:      "cat-bed"
			title:   "Bed mode for the cat"
			date:    "2026-09-09"
			summary: "Locked, it notices a cat on the keyboard and runs warm on purpose for her."
			trigger: "Lock the session and let her settle; oldbook-cat show reports what it sees."
			detail:  "Five keys held for two seconds is necessary but never enough, and three clean keystrokes in ten seconds veto it outright. It never runs unlocked, never on battery, hands the fans back before it cuts load, and takes stricter ceilings with the lid shut."
			run: ["oldbook-cat", "show"]
		},
		{
			id:      "strip-names-the-repository"
			title:   "The strip names the repository and tabs"
			date:    "2026-09-09"
			summary: "In a checkout the caption shows the branch and how it stands, plus the tabs tmux or Sway holds."
			trigger: "Focus a terminal inside a Fossil or git checkout that has several tmux windows."
			detail:  "A dot marks uncommitted work, a check a clean tree, arrows what has not moved. As the strip narrows it gives up whole ideas in a fixed order rather than cutting the text."
		},
		{
			id:       "rice-card"
			title:    "The rice card lists what landed"
			date:     "2026-09-08"
			summary:  "A reading card names the newest desktop features, and its Try link sets each one off."
			trigger:  "Click the rice card: left steps forward, right steps back, the middle button ticks it tried."
			detail:   "The list is ~/.config/oldbook/rice.json, rendered from alpine/cue/rice; oldbook-rice list prints it. Off: delete the rice card from the Conky panels.json."
			run: ["oldbook-rice", "list"]
			terminal: true
		},
		{
			id:      "terminal-progress"
			title:   "One way for the terminal to wait"
			date:    "2026-09-08"
			summary: "Long helpers draw segmented bars, stepped spinners and step lists that move only on real work."
			trigger: "Run a long helper such as alpine/bin/remote-build or alpine/bin/package-archive."
			detail:  "There is no timer: a repaint happens only when the caller reports work. A pipe, NO_COLOR, a plain console, a battery or OLDBOOK_LOADING=plain all get plain stepped lines instead."
		},
		{
			id:      "notification-cards"
			title:   "Notification cards"
			date:    "2026-09-08"
			summary: "A notification is a card and nothing around it paints; a three-pixel rail carries the urgency."
			trigger: "notify-send 'Ghost Planet' 'Received'"
			detail:  "Send one at each urgency to watch the rail change, then Super+Shift+N for the styled history."
			run: ["notify-send", "Ghost Planet", "Received"]
		},
		{
			id:      "strip-process-chain"
			title:   "The strip names the process chain"
			date:    "2026-09-08"
			summary: "The caption strip says foot > tmux > claude and the directory's branch, not the window's title."
			trigger: "Focus a terminal and read the bottom strip"
			detail:  "Only terminals are walked. Hover the caption for the raw window title; Super+Ctrl+B moves the strip."
		},
		{
			id:      "power-posture"
			title:   "One power posture for the desktop"
			date:    "2026-09-08"
			summary: "Mains, battery, low, critical: one posture the session agrees on, and a ladder to shed by."
			trigger: "oldbook-power-mode show"
			detail:  "'ladder' prints what survives at each posture; 'override battery-low' holds one by hand, 'auto' releases it."
			run: ["oldbook-power-mode", "show"]
			terminal: true
		},
		{
			id:      "lock-power-key"
			title:   "The power key is inert behind the lock"
			date:    "2026-09-08"
			summary: "While the lock screen is up an inhibitor holds the power key, so a press powers nothing off."
			trigger: "Super+Escape, then press the power key"
			detail:  "A sat-on key repeating for an hour is refused too. An unlocked session still powers off on a press."
		},
		{
			id:      "ambient-display"
			title:   "The panel follows the room"
			date:    "2026-09-08"
			summary: "The panel eases to the room's light, and learns any level you set by hand as a lasting offset."
			trigger: "oldbook-ambient-display on"
			detail:  "Opt-in and reversible with 'off'. Cover the sensor beside the camera to watch the panel answer."
		},
		{
			id:      "grub-menu"
			title:   "Ghost Planet GRUB menu"
			date:    "2026-09-08"
			summary: "The boot menu shows the painting blurred behind an amber selection bar and the Ghost wordmark."
			trigger: "Reboot and watch the three-second boot menu."
			detail:  "Its fonts are written straight to GRUB's PF2 format from Pango glyphs. Rebuild with alpine/bin/build-grub-theme, install with doas alpine/bin/install-boot-console, and remove with --remove-theme."
		},
		{
			id:      "mission-control"
			title:   "Mission Control"
			date:    "2026-09-08"
			summary: "Every workspace as a card of real window stills, the focused one outlined in amber."
			trigger: "F3"
			detail:  "Drag a still onto another card to move that window. F3 again, or Escape, puts it away."
			run: ["oldbook-mission-control", "toggle"]
		},
		{
			id:      "launchpad"
			title:   "Launchpad"
			date:    "2026-09-08"
			summary: "Every application as a large icon over the blurred painting, filtering from the first keystroke."
			trigger: "F4"
			detail:  "Page dots underneath; type to filter, Enter to launch, Escape to close."
			run: ["oldbook-launchpad", "toggle"]
		},
		{
			id:      "workspace-peek"
			title:   "Peek at a workspace from the bar"
			date:    "2026-09-08"
			summary: "Resting on a workspace button opens a peek of that workspace's windows, one still and title each."
			trigger: "Rest the pointer on a Waybar workspace button"
			detail:  "It takes about a third of a second, so a pointer merely crossing the bar never opens it."
		},
		{
			id:      "artwork-reveal"
			title:   "The next painting grows from your click"
			date:    "2026-09-08"
			summary: "The crossfade to the next painting expands out of the exact point you clicked on the artwork badge."
			trigger: "Right-click the artwork badge in the bar"
			detail:  "Left-click picks a painting, middle-click pauses rotation, and the wheel browses the collection."
		},
		{
			id:      "reactive-palette"
			title:   "The painting elects the accent"
			date:    "2026-09-08"
			summary: "Each painting's hue elects one of the theme's own accents for pill, launcher, lock and strip."
			trigger: "oldbook-palette show"
			detail:  "It runs on every painting change; 'show' says which accent won and why, 'clear' returns to the theme."
			run: ["oldbook-palette", "show"]
			terminal: true
		},
		{
			id:      "sound-cues"
			title:   "Ghost Planet sound cues"
			date:    "2026-09-08"
			summary: "Six synthesized cues under a second each: lock, unlock, low battery, a new painting and more."
			trigger: "oldbook-sound unlock"
			detail:  "'oldbook-sound list' names all six. They are quiet on purpose and follow the desktop's mute."
			run: ["oldbook-sound", "unlock"]
		},
		{
			id:      "idle-gallery"
			title:   "The idle gallery"
			date:    "2026-09-08"
			summary: "Four minutes idle and the paintings take over, drifting slowly across each before crossfading."
			trigger: "Leave the desk for four minutes"
			detail:  "It restores exactly on return. 'oldbook-screensaver stop' ends a drift you would rather not watch."
		},
		{
			id:      "desktop-breath"
			title:   "The keys breathe with your typing"
			date:    "2026-09-08"
			summary: "In breathe-on-air mode each keystroke deepens the keyboard's breath, and idle lungs slowly empty."
			trigger: "Alt+Shift+F6, then type"
			detail:  "The breath starts shallow at about seven seconds a cycle and quickens towards three as you type. The caption strip's accent wash glows with it; the painting never moves. Shift+F5 returns the keys to steady, and breath.json switches the caption glow off."
		},
		{
			id:      "animated-cursors"
			title:   "The Ghost waiting cursor"
			date:    "2026-09-08"
			summary: "The waiting pointer is an amber ring that turns and breathes, and the busy one keeps its arrow."
			trigger: "Launch an application and watch the pointer while it starts."
			detail:  "The cursor theme is Oldbook-Ghost, drawn by alpine/bin/build-cursor-theme. Off: name simp1e-cursors-gruvbox-dark again in sway/theme.conf and both GTK settings.ini files."
		},
		{
			id:      "now-transmitting"
			title:   "Now transmitting"
			date:    "2026-09-08"
			summary: "A card slides in at the bottom right for four seconds when a genuinely new track starts."
			trigger: "Skip a track in Pithos"
			detail:  "Album art, title and artist. A pause and resume of the same track does not bring it back."
		},
		{
			id:      "painting-crossfade"
			title:   "Paintings crossfade"
			date:    "2026-09-08"
			summary: "The wallpaper eases from one painting to the next instead of cutting, even at login and reload."
			trigger: "Super+Ctrl+Right for the next painting."
			detail:  "1.6 seconds for the timer, 0.8 for a deliberate change. oldbook-background quit returns plain cuts until the next login."
		},
		{
			id:      "lock-screen"
			title:   "The lock dissolves into the painting"
			date:    "2026-09-08"
			summary: "The lock fades into the blurred painting with a clock, a caption card and the hour's Scripture."
			trigger: "Super+Escape"
			detail:  "The ring stays invisible until you type. The locker is oldbook-swaylock-effects beside stock swaylock; OLDBOOK_LOCK_BACKEND=stock returns the plain one."
		},
		{
			id:      "keys-follow-the-room"
			title:   "The keys follow the room's light"
			date:    "2026-09-08"
			summary: "Ambient mode lights the keyboard in a dark room and turns it off in daylight, fading smoothly."
			trigger: "Alt+F6, then cover the light sensor beside the camera."
			detail:  "It reads the Apple SMC light sensor on a log-scale curve with a hysteresis band, and F5 and F6 still set the peak. Shift+F5 returns to steady light."
		},
		{
			id:      "last-breath"
			title:   "The keyboard's last breath before lock"
			date:    "2026-09-08"
			summary: "Idle four and a half minutes, the screen dims and the keys rise once, then fade to dark."
			trigger: "Leave the desk for four and a half minutes."
			detail:  "The lock follows at five minutes. Any activity restores the display and the keys exactly. Off: drop the timeout 270 pair from the swayidle line in oldbook-session."
		},
		{
			id:      "neovim-statusline"
			title:   "Neovim's hand-rolled statusline"
			date:    "2026-09-08"
			summary: "Neovim shows a mode-coloured statusline with branch and diagnostics, a winbar and thin splits."
			trigger: "Open a file in nvim inside a checkout."
			detail:  "No plugin manager; it lives in the theme profile's init.lua."
		},
		{
			id:      "cava-meter"
			title:   "A signal meter beside the music"
			date:    "2026-09-08"
			summary: "A ten-bar spectrum follows the media controls while something plays, and stops in silence."
			trigger: "Play a track in Pithos and watch the centre of the bar."
			detail:  "cava stops entirely when nothing plays. Off: delete custom/cava from modules-center in the bar's config.jsonc."
		},
		{
			id:       "sun-and-moon"
			title:    "Sun, moon and a night light"
			date:     "2026-09-08"
			summary:  "With a location file the masthead shows sunrise, sunset and moon, and the screen warms at dusk."
			trigger:  "Copy location.example.json to ~/.config/oldbook/location.json and fill it in."
			detail:   "Everything is computed offline; nothing is inferred or fetched. After dark the gallery timer prefers nocturnes. Night light in the command deck, or oldbook-sun-light toggle, stops the warming, and deleting the file switches all of it off."
			run: ["oldbook-astro", "status"]
			terminal: true
		},
		{
			id:      "painting-thumbnails"
			title:   "The badge and picker show the painting"
			date:    "2026-09-08"
			summary: "The bar badge is a thumbnail of the painting on screen, and Super+G shows one on every row."
			trigger: "Super+G"
			detail:  "A paused rotation dims the badge and a running generation swaps in an hourglass. Thumbnails are cached under ~/.cache/oldbook/thumbnails/."
		},
		{
			id:      "ghostty-shaders"
			title:   "Warm bloom and a smeared cursor"
			date:    "2026-09-08"
			summary: "Ghostty lifts bright amber text with a soft bloom and smears the cursor from cell to cell."
			trigger: "Super+Enter for Ghostty, then move the cursor."
			detail:  "Both shaders animate only while the window is focused. Off: delete the custom-shader lines from the Ghostty config."
		},
		{
			id:      "terminal-splash"
			title:   "The Space Ghost terminal splash"
			date:    "2026-09-08"
			summary: "A new terminal opens on fastfetch beside the Space Ghost painting, the hour's Scripture and track."
			trigger: "Open a new terminal outside tmux."
			detail:  "Drawn with Ghostty's kitty images or libsixel in Foot. OLDBOOK_SPLASH_LOGO=none silences it; oldbook-splash shows it again."
		},
		{
			id:      "ghost-observatory"
			title:   "The Ghost Observatory look"
			date:    "2026-09-08"
			summary: "Glass blur, rounded window corners, soft deep shadows and a floating bar over the painting."
			trigger: "Look at any window over the painting."
			detail:  "Tweak alpine/desktop/.config/swayfx/effects.conf. Starting Sway with OLDBOOK_STOCK_SWAY=1 leaves it out."
		},
		{
			id:      "power-deck"
			title:   "The power deck"
			date:    "2026-09-08"
			summary: "Five charcoal tiles over the blurred desktop: lock, suspend, log out, reboot and shut down."
			trigger: "Super+Shift+E, or left-click the battery."
			detail:  "The keys l, u, e, r and s choose a tile and Escape closes. Log out, reboot and shut down ask on a themed bar first."
		},
		{
			id:      "ghost-planet-boot-entry"
			title:   "A Ghost Planet boot entry"
			date:    "2026-09-08"
			summary: "A second GRUB entry prints a Ghost Planet masthead above the disk passphrase prompt."
			trigger: "Pick the Ghost Planet entry in the GRUB menu at boot."
			detail:  "The default entry and its initramfs are untouched. install-boot-console --remove-ghost withdraws it; rerun the installer after a kernel upgrade."
		},
		{
			id:      "screenshot-shutter"
			title:   "A shutter for every screenshot"
			date:    "2026-09-08"
			summary: "After a capture the screen flashes cream, the shutter clicks and Satty opens to annotate."
			trigger: "Print, Shift+Print for an area, or Ctrl+Print for a window."
			detail:  "In Satty, Enter copies and closes and Ctrl+S overwrites. Uninstall sound-theme-freedesktop to silence the click."
		},
		{
			id:      "feedback-pill"
			title:   "The feedback pill"
			date:    "2026-09-08"
			summary: "Volume, brightness and keyboard-light changes show a small themed pill at the bottom centre."
			trigger: "Tap a volume or brightness key."
			detail:  "It takes no focus and passes clicks through, holding about a second before it fades. Off: remove its block from oldbook-session."
			run: ["oldbook-osd", "show", "--kind", "volume", "--value", "40"]
		},
		{
			id:      "control-centre"
			title:   "Incoming Transmissions"
			date:    "2026-09-08"
			summary: "The notification centre holds the playing track, volume and brightness sliders and quick actions."
			trigger: "Super+Shift+N, or click the bell."
			detail:  "The quick actions are Lock, Deck, Next art, Hold art, Mic off and Cards. Remove any widget from swaync's config.json and run swaync-client -R."
		},
		{
			id:      "boot-console-colours"
			title:   "The boot console wears the theme"
			date:    "2026-09-08"
			summary: "The passphrase prompt, kernel messages and rescue consoles share the theme's colours and font."
			trigger: "Reboot, or Ctrl+Alt+F2 for a rescue console under the Ghost Planet banner."
			detail:  "Sixteen console colours and the kernel's Terminus 16x32 font ride on the GRUB command line. alpine/bin/install-boot-console keeps a backup that --rollback restores."
		},
		{
			id:      "scripture-steps-back"
			title:   "Right-click steps back a passage"
			date:    "2026-09-08"
			summary: "Right-clicking the Scripture card returns to the passage before, along your own reading path."
			trigger: "Right-click the Scripture card."
			detail:  "Each return is saved to history as a new hour-long selection; nothing saved is edited or removed."
		},
		{
			id:      "keyboard-moods"
			title:   "The keyboard light has moods"
			date:    "2026-09-08"
			summary: "Beyond F5 and F6 the keys can breathe, brighten with each keypress, or dim while you type."
			trigger: "Shift+F6 to breathe, Ctrl+F6 to glow with each keypress, Shift+F5 for steady light."
			detail:  "Ctrl+F5 starts bright and darkens as you type, and the Ctrl+Shift variants react only above about 22 words per minute. The level and mode survive logins, and the command deck's Keyboard glow menu has every mode."
		},
		{
			id:      "screen-corners"
			title:   "The screen has rounded corners"
			date:    "2026-09-07"
			summary: "The whole display is masked with rounded black corners over everything, the lock included."
			trigger: "Look at the corners of the screen."
			detail:  "A SwayFX patch draws the mask after the whole scene. SPACEGHOST_SCREEN_CORNER_RADIUS=0 before starting Sway disables it."
		},
		{
			id:      "scripture-history"
			title:   "Reading history behind History"
			date:    "2026-09-07"
			summary: "A chosen passage holds for an hour, and History on the card opens every saved reading."
			trigger: "Click History on the Scripture card's header."
			detail:  "History is its own durable SQLite database: notes, research and drafts are appended and never replaced. Clicking the passage itself advances it."
		},
		{
			id:      "window-carousel"
			title:   "The window carousel"
			date:    "2026-09-07"
			summary: "Super+Tab or Alt+Tab shows every window as an angled card, in true recent order."
			trigger: "Hold Super and press Tab."
			detail:  "Shift reverses, releasing selects and Escape returns home; a quick tap swaps the last two windows. A four-finger swipe down opens it when nothing is hidden."
		},
		{
			id:      "scripture-study"
			title:   "A study library beside Scripture"
			date:    "2026-09-07"
			summary: "Reflections and study notes, kept in a Fossil-backed library, are searchable from the bar."
			trigger: "Right-click the Scripture search bar, then type."
			detail:  "oldbook-scripture-study list names every curated and generated entry."
		},
		{
			id:      "window-sizing"
			title:   "Grow, shrink and centre in place"
			date:    "2026-09-07"
			summary: "Super+= and Super+- resize a window around its centre, and Super+C centres and raises it."
			trigger: "Super+= on a floating window."
			detail:  "Super+Shift+Space floats a window at 90 percent with room to breathe."
		},
		{
			id:      "clipboard-history"
			title:   "Clipboard history"
			date:    "2026-09-07"
			summary: "Copied text and images are kept, and a picker puts any of them back on the clipboard."
			trigger: "Super+Shift+V"
			detail:  "Super+Ctrl+Shift+V deletes an entry. The history stays out of the repository and survives theme changes."
		},
		{
			id:      "strip-follows-floats"
			title:   "The strip follows a floating window"
			date:    "2026-09-07"
			summary: "Focus a floating window and the caption strip attaches beneath it and travels with it."
			trigger: "Focus a floating window, then drag it."
			detail:  "Focusing a tiled window sends the strip flying home to its band at the bottom of the workspace."
		},
		{
			id:      "strip-buttons"
			title:   "The caption strip answers the pointer"
			date:    "2026-09-07"
			summary: "Left-click the strip for the window picker, middle-click to float, or use its buttons."
			trigger: "Middle-click the caption strip to float the focused window."
			detail:  "Its buttons float, fullscreen or pick a window, and an empty workspace's strip offers launchers instead. Shift+right-click opens the settings editor for position, opacity, corners, powerline and more, saved to ~/.config/oldbook/decoration.json."
		},
		{
			id:      "music-on-the-bar"
			title:   "Music in the middle of the bar"
			date:    "2026-09-07"
			summary: "Previous, play and next sit on the bar with the track, which takes clicks, scrolls and seeks."
			trigger: "Play something in Pithos and use the controls at the centre of the bar."
			detail:  "For Pithos, double-click opens it, right-click shows or hides it, middle-click marks a song tired and Super+middle-click bans it."
		},
		{
			id:      "bar-tooltips"
			title:   "Every bar module says what it does"
			date:    "2026-09-07"
			summary: "Each module in the bar has a Space Ghost tooltip naming its clicks, and groups slide out on hover."
			trigger: "Rest the pointer on the CPU, network, sound or battery module."
			detail:  "The drawers hold memory, thermals and storage; radio and firewall state; the microphone; brightness and keep-awake."
		},
		{
			id:      "caption-strip"
			title:   "Window titles live in a caption strip"
			date:    "2026-09-07"
			summary: "Captions sit in one translucent strip along the workspace's bottom edge instead of titlebars."
			trigger: "Look at the bottom edge of any workspace."
			detail:  "Super+Ctrl+B returns the strip to the bottom. Settings live in ~/.config/oldbook/decoration.json."
		},
		{
			id:       "theme-switching"
			title:    "Switch the whole desktop's theme"
			date:     "2026-09-07"
			summary:  "oldbook-theme swaps a complete theme into every surface and every running application at once."
			trigger:  "oldbook-theme use catppuccin-mocha, then oldbook-theme use gruvbox-dark"
			detail:   "A theme must be complete; palette-only themes are refused. Foot recolours open windows without closing them."
			run: ["oldbook-theme", "list"]
			terminal: true
		},
		{
			id:      "fullscreen-bar-fade"
			title:   "The bar steps back for fullscreen"
			date:    "2026-09-07"
			summary: "While a window is fullscreen the bar fades to thirty percent, and returns under the pointer."
			trigger: "Super+F on any window."
			detail:  "oldbook-waybar-dim rewrites one stylesheet only when the state changes. Off: remove its block from oldbook-session."
		},
		{
			id:      "show-desktop"
			title:   "Four fingers clear the desktop"
			date:    "2026-09-07"
			summary: "Swipe four fingers up to clear every window away, and down to put each one back."
			trigger: "Four-finger swipe up on the trackpad, then down."
			detail:  "With nothing hidden, four fingers down opens the window carousel instead."
		},
		{
			id:      "agent-launcher"
			title:   "Agents in tmux, one key away"
			date:    "2026-09-07"
			summary: "Super+N starts Codex and Claude sessions in tmux and lists the running ones to reattach."
			trigger: "Super+N"
			detail:  "Super+Ctrl+N starts the quick preset straight away. Presets live in ~/.config/oldbook/agents.json."
		},
		{
			id:      "witness-card"
			title:   "Witnesses from outside"
			date:    "2026-09-07"
			summary: "A reading card carries quotations from outside witnesses, and a click brings the next one."
			trigger: "Click the Witness card on the desktop."
		},
		{
			id:      "torah-and-talmud"
			title:   "Torah and Talmud, offline"
			date:    "2026-09-07"
			summary: "The five books of Torah and 37 Talmud tractates ship offline, searched before Bible verses."
			trigger: "Super+Shift+/ and type a word."
			detail:  "References such as Torah Genesis 1:1 and Talmud Berakhot 2a work, and the curated reflections are searched too."
		},
		{
			id:      "coast-to-coast-notebook"
			title:   "The Coast to Coast notebook"
			date:    "2026-09-07"
			summary: "A card rotates Coast to Coast quips with dated journal notes from a private SQLite notebook."
			trigger: "Click the Coast to Coast card to advance it."
			detail:  "Three quips to each note, one entry every four minutes. oldbook-journal add --text writes a note and oldbook-journal backup copies the database."
		},
		{
			id:       "scripture-on-the-desktop"
			title:    "Scripture on the desktop"
			date:     "2026-09-07"
			summary:  "The whole King James Bible ships offline, and Super+/ searches it right in the desktop bar."
			trigger:  "Super+/ and type a reference or a word."
			detail:   "Enter shows the passage on the Scripture card and holds it for an hour, and Escape closes the search. Clicking the passage advances it."
			run: ["oldbook-scripture", "show", "Psalm 23"]
			terminal: true
		},
		{
			id:      "reading-cards"
			title:   "Reading cards seated on the painting"
			date:    "2026-09-07"
			summary: "Transparent cards settle on the calm parts of each painting, tinted until their text is legible."
			trigger: "Super+Shift+G hides them and shows them again."
			detail:  "The placement is cached per painting, and the gallery picker can refit them. The cards are defined in the Conky panels.json."
		},
		{
			id:      "dropdown-terminals"
			title:   "A drop-down console and monitor"
			date:    "2026-09-07"
			summary: "Super+` drops a persistent Ghostty console below the bar, and Super+~ a btop monitor."
			trigger: "Super+` to summon it, and again to hide it."
			detail:  "Each keeps its process through hide and show, and follows you across workspaces while it is shown."
		},
		{
			id:      "expo"
			title:   "Expo: every workspace in one picker"
			date:    "2026-09-07"
			summary: "Super+E or a three-finger swipe up opens a picker of every workspace and window."
			trigger: "Super+E"
			detail:  "A three-finger swipe down closes it."
		},
		{
			id:      "trackpad-gestures"
			title:   "Trackpad gestures for workspaces"
			date:    "2026-09-07"
			summary: "Three or four fingers sideways change workspace, and a four-finger pinch opens the launcher."
			trigger: "Swipe three fingers left or right on the trackpad."
			detail:  "Two fingers stay with the application. The full table is alpine/desktop/GESTURES.md."
		},
		{
			id:      "theme-invention"
			title:   "Invent a theme from the badge"
			date:    "2026-09-07"
			summary: "Super+Shift+click the artwork badge to invent a whole theme with a debut painting of its own."
			trigger: "Super+Shift+click the artwork badge, or Super+Shift+right-click to describe one."
			detail:  "The finished theme is announced with a preview of its painting and applied with it."
		},
		{
			id:      "next-ai-window"
			title:   "Jump to the next AI window"
			date:    "2026-09-07"
			summary: "Super+I jumps to the next Codex or Claude window, and workspaces holding one carry a star."
			trigger: "Super+I, or Super+Shift+I for a menu of them."
		},
		{
			id:      "youtube-player"
			title:   "YouTube on the desktop"
			date:    "2026-09-07"
			summary: "Search YouTube, your history and playlists, and play as floating picture-in-picture."
			trigger: "Open the command deck and choose YouTube."
			detail:  "It plays through yt-dlp and mpv, floating or pinned behind the desktop."
		},
		{
			id:      "hold-to-help"
			title:   "Hold Super for help"
			date:    "2026-09-07"
			summary: "Hold Super alone for half a second to see the shortcuts for the focused application and more."
			trigger: "Hold Super on its own for half a second."
			detail:  "It never takes focus, and releasing or pressing a key dismisses it. Sections read outward from the focused window and can be arranged in ~/.config/superhold/config.json."
		},
		{
			id:      "video-background"
			title:   "Video backgrounds"
			date:    "2026-09-07"
			summary: "A muted video can loop beneath the windows in place of the painting, started only by hand."
			trigger: "Open the command deck and choose a video background."
			detail:  "oldbook-video-background FILE plays one and oldbook-video-background stop ends it."
		},
		{
			id:      "focus-follows-pointer"
			title:   "Focus follows the pointer"
			date:    "2026-09-07"
			summary: "Windows and tmux panes take focus under the pointer; a resting float rises after a second."
			trigger: "Move the pointer across two windows."
			detail:  "The raise delay is mouse_raise_delay 1000 in sway/local.d/hover-raise.conf."
		},
		{
			id:      "strata-workspace"
			title:   "Strata on workspace ten"
			date:    "2026-09-07"
			summary: "Super+0 opens Strata, the local Fossil review browser, on its own tenth workspace."
			trigger: "Super+0"
		},
		{
			id:      "workspace-names"
			title:   "Workspaces named for what's on them"
			date:    "2026-09-07"
			summary: "Workspace buttons carry a name, Ghost to Lounge, and the largest application showing on each."
			trigger: "Open an application on an empty workspace and read its button in the bar."
		},
		{
			id:      "attention-light"
			title:   "Caps Lock lights when an agent waits"
			date:    "2026-09-07"
			summary: "Codex and Claude completions or approvals light the Caps Lock LED until you visit that window."
			trigger: "Let a Codex or Claude session finish while you work in another window."
			detail:  "Ordinary notifications never light it, and the Caps Lock key itself is Escape."
		},
		{
			id:      "command-deck"
			title:   "The command deck"
			date:    "2026-09-07"
			summary: "One menu for the desktop's switches and places, each row saying how it is set before you pick."
			trigger: "Super+Shift+D, or left-click the Ghost badge."
			detail:  "Applications, the gallery, keyboard glow, night light, the firewall, notifications, the Fossil checkout and the session menu."
		},
		{
			id:      "space-ghost-gallery"
			title:   "The Space Ghost gallery"
			date:    "2026-09-07"
			summary: "Space Ghost and Zorak dropped into paintings, rotating every twenty minutes on every workspace."
			trigger: "Super+G to pick a painting, Super+Shift+P to pause the rotation."
			detail:  "On the artwork badge, left-click opens the gallery, right-click moves on, middle-click pauses and the wheel browses; Super+click generates a painting and Shift+click edits the prompts."
		},
		{
			id:      "space-ghost-desktop"
			title:   "The Space Ghost desktop"
			date:    "2026-09-07"
			summary: "SwayFX with a floating control-deck bar and the Space Ghost badge, reproducible on Alpine."
			trigger: "Log in."
			detail:  "The Ghost badge's white, purple and pink are the one thing no theme may recolour."
		},
	]
}
