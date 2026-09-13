package rice

// The list. A new feature is a new entry at the top: the loader sorts by
// date, newest first, and keeps file order within a day. Render it with
// `cue export ./alpine/cue/rice -e rice --out json`; see README.md.
rice: {
	version: 1
	entries: [
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
			id:      "cat-bed"
			title:   "Bed mode for the cat"
			date:    "2026-09-09"
			summary: "Locked, it notices a cat on the keyboard and runs warm on purpose for her."
			trigger: "Lock the session and let her settle; oldbook-cat show reports what it sees."
			detail:  "Five keys held for two seconds is necessary but never enough, and three clean keystrokes in ten seconds veto it outright. It never runs unlocked, never on battery, hands the fans back before it cuts load, and takes stricter ceilings with the lid shut."
			run: ["oldbook-cat", "show"]
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
			title:   "The painting breathes with the keyboard"
			date:    "2026-09-08"
			summary: "Keystrokes fill the lungs: the keys breathe deeper and the painting swells as you type."
			trigger: "Alt+Shift+F6, then type"
			detail:  "Continuous motion, so it is a mode you switch on. Alt+Shift+F6 again, or breath.json, switches it off."
		},
		{
			id:      "now-transmitting"
			title:   "Now transmitting"
			date:    "2026-09-08"
			summary: "A card slides in at the bottom right for four seconds when a genuinely new track starts."
			trigger: "Skip a track in Pithos"
			detail:  "Album art, title and artist. A pause and resume of the same track does not bring it back."
		},
	]
}
