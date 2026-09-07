# Agent sessions and the offline library

## Launching agents

**Super+N** opens the agent picker; it also appears in the AI menu
(**Super+Shift+I**) as *Launch a new agent…*. Type to filter, choose an agent,
then choose a working directory. Running sessions are listed first so the same
picker reattaches as well as launches.

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

That still requires the far side to accept it. Run this once **on alienware**:

```sh
sudo tailscale up --ssh
```

Until then the launcher refuses immediately with that instruction rather than
hanging, because alienware currently answers nothing on port 22. Plain ssh
remains available for hosts that run sshd: set `"transport": "ssh"` on the
agent, and put a key in `~/.ssh` (this machine has none).

Adjust the Ollama model name in the config to whatever that box actually
serves; `llama3.3` is a placeholder.

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
