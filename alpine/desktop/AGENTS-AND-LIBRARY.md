# Agent sessions and the offline library

## Launching agents

**Super+N** opens the agent picker; it also appears in the AI menu
(**Super+Shift+I**) as *Launch a new agent…*. Type to filter, choose an agent,
then choose a working directory. Home (`~`) is first and selected by default.
New Codex Astra ultra and Claude best/max entries lead the picker, followed by
running sessions for reattachment and the remaining agent presets.

Every agent runs inside its own **tmux** session, so closing the terminal never
kills the work and the same session can be picked up again later. A remote
agent is the same thing with an ssh hop inside the tmux session, which means the
session survives a dropped link rather than dying with it.

```sh
oldbook-agents            # the picker
oldbook-agents agents     # what can be launched
oldbook-agents list       # running sessions
oldbook-agents new codex --cwd ~/.files
oldbook-agents attach agent-codex
oldbook-agents kill agent-codex
```

Agents are defined in `alpine/desktop/.config/oldbook/agents.json`: an `id`, a
`title`, a `command` array, an optional `host`, and an `enabled` switch. Local
agents cover Codex, Claude Code and a plain shell. The `alienware` agents reach
the tailnet box over ssh for Codex, Claude Code, Ollama and a login shell.

Directories and model names are shell-quoted before they cross the ssh hop, so
a path containing quotes cannot become remote shell syntax; `$SHELL` is the one
value deliberately left to expand on the far side.

### Reaching the tailnet box

Tailscale is installed, enabled at boot and authenticated; this machine is
`oldbook`. The `alienware` agents use **Tailscale SSH** rather than plain ssh,
because it needs no key on either side and authenticates with the tailnet
identity instead.

That still requires two things. On the far side, `sudo tailscale up --ssh`,
which alienware now has. And in the tailnet policy, an `ssh` rule permitting
it: both machines are **tagged** rather than user-owned, so the rule must be
tag to tag, and it must be `accept` rather than `check`, because a tagged
source has no user identity to re-authenticate.

```json
"ssh": [
  {
    "action": "accept",
    "src":    ["tag:apple"],
    "dst":    ["tag:desktop"],
    "users":  ["autogroup:nonroot", "root"]
  }
]
```

The launcher checks both before creating a session: an unreachable host and a
policy refusal produce different messages, because a listening port is not the
same as permission to use it. Plain ssh
remains available for hosts that run sshd: set `"transport": "ssh"` on the
agent, and put a key in `~/.ssh` (this machine has none).

Verified end to end: the session opens on alienware, and closing the terminal
leaves it running there to be reattached. The Ollama agents use the models that
box actually serves, `qwen3.5:27b-text` and `qwen3.5:9b`.

### What this laptop accepts

Nothing that is not asked for. There is no sshd, Tailscale SSH is off here, and
`table inet oldbook` drops unsolicited inbound on every interface including
`tailscale0`, permitting only loopback, established or related traffic, DHCP
replies and the ICMP and NDP types IPv6 needs. Tailscale still reaches peers
directly because it initiates outbound and conntrack lets the replies home.
`--shields-up` would add nothing over that rule and would break Taildrop, and
extra nftables rules risk the NAT traversal that keeps the path direct rather
than relayed, so neither is used. Subnet routes are deliberately not accepted,
so no peer can quietly become a route for this machine's traffic.

## The offline library

The complete King James text ships in the checkout. Everything else installs
into `~/.local/share/oldbook/scripture/`, and the first desktop login after an
install fetches it automatically in the background.

```sh
oldbook-scripture-library list       # what exists, and what is installed
oldbook-scripture-library install --core   # public-domain Bibles and the Tanakh
oldbook-scripture-library install --all    # adds the Talmud
oldbook-scripture-library install ylt
oldbook-scripture-library installed
```

Christian Bibles, all public domain: the King James Version, the same with the
Apocrypha, the American Standard Version, the World English Bible, Young's
Literal, Douay-Rheims with the Deuterocanon, Webster, Tyndale, Wycliffe, the
Bible in Basic English and the American King James Version.

Jewish texts from Sefaria: the Tanakh in Hebrew with cantillation and in the
JPS 1917 English translation, both public domain; the Mishnah; and the
thirty-seven tractates of the Talmud Bavli in the William Davidson translation.

**On what is missing.** The ESV, NIV, NASB, NKJV, NLT, CSB and the 1985 JPS are
under copyright and cannot be redistributed, so they are deliberately absent
rather than quietly broken. Every text records its licence when it installs.
The Davidson Talmud is CC-BY-NC: fine for personal study, not for anything
commercial.

Read any of them with `oldbook-scripture --translation <id> show 'Isaiah 53'`,
or switch the desktop and the picker with `oldbook-scripture use <id>`. The
scripture picker (**Super+/**) lists the other installed texts at the top, so
one keystroke and a word of typing moves between translations.

## Witnesses from outside

`alpine/assets/scripture/witnesses.json` holds remarks about Christ, the Church
and Christian ethics from people who did not share the faith: Pliny, Tacitus,
Julian the Apostate, Josephus, Rousseau, Franklin, Jefferson, Nietzsche,
Einstein, Freud, Camus, Habermas, Dawkins, Tom Holland and others. Each entry
records the speaker's stance and the actual source, and where an attribution is
disputed it says so, because a quotation that will not survive checking is no
encouragement at all. The desktop shows one a day on the **WITNESS** panel.
