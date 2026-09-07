"""Definitions and command building for tmux-contained agent sessions.

Every agent runs inside its own tmux session, so closing the terminal never
kills the work and the same session can be reattached from anywhere. Remote
agents are the same thing with an ssh hop in front, which is why a tailnet host
needs no special handling here.
"""
import json
import os
from pathlib import Path
import re
import shlex

SAFE_ID = re.compile(r'[a-z0-9][a-z0-9-]{0,63}')
SAFE_HOST = re.compile(r'[A-Za-z0-9][A-Za-z0-9._-]{0,253}')
# Plain ssh needs keys and a listening sshd; Tailscale SSH needs neither and
# authenticates with the tailnet identity instead.
TRANSPORTS = ('ssh', 'tailscale-ssh')


def load_config(path):
    document = json.loads(Path(path).read_text())
    agents = document.get('agents')
    if not isinstance(agents, list) or not agents:
        raise ValueError('Agent file must define a non-empty agents list')
    seen = set()
    for agent in agents:
        if not isinstance(agent, dict) or not SAFE_ID.fullmatch(str(agent.get('id', ''))):
            raise ValueError('Every agent needs a lowercase hyphenated id')
        if agent['id'] in seen:
            raise ValueError('Duplicate agent id: ' + agent['id'])
        seen.add(agent['id'])
        if not isinstance(agent.get('title'), str) or not agent['title'].strip():
            raise ValueError(f'Agent {agent["id"]} needs a title')
        command = agent.get('command')
        if (not isinstance(command, list) or not command
                or not all(isinstance(part, str) and part for part in command)):
            raise ValueError(f'Agent {agent["id"]} needs a non-empty string command list')
        host = agent.get('host')
        if host is not None and not SAFE_HOST.fullmatch(str(host)):
            raise ValueError(f'Agent {agent["id"]} has an unusable host')
        transport = agent.get('transport', 'ssh')
        if transport not in TRANSPORTS:
            raise ValueError(f'Agent {agent["id"]} has an unknown transport: {transport}')
        if transport != 'ssh' and not host:
            raise ValueError(f'Agent {agent["id"]} sets a transport but no host')
        if 'enabled' in agent and not isinstance(agent['enabled'], bool):
            raise ValueError(f'Agent {agent["id"]} enabled must be true or false')
    return document


def enabled_agents(document):
    return [agent for agent in document.get('agents', []) if agent.get('enabled', True)]


def expand_workdirs(document, home=None):
    """Resolve the configured directory patterns to real directories."""
    home = Path(home or Path.home())
    results = []
    for pattern in document.get('workdirs', ['~']):
        text = str(pattern)
        text = str(home) + text[1:] if text.startswith('~') else text
        candidate = Path(text)
        if '*' in text or '?' in text:
            base = Path(text).parent
            try:
                matches = sorted(base.glob(Path(text).name))
            except (OSError, ValueError):
                matches = []
            results.extend(path for path in matches if path.is_dir())
        elif candidate.is_dir():
            results.append(candidate)
    ordered = []
    for path in results:
        resolved = path.resolve()
        if resolved not in ordered:
            ordered.append(resolved)
    return ordered


def session_name(document, agent_id, existing=()):
    """A short, unique, tmux-safe name for a new session."""
    prefix = str(document.get('session_prefix', 'agent'))
    base = f'{prefix}-{agent_id}'
    if base not in existing:
        return base
    for index in range(2, 1000):
        candidate = f'{base}-{index}'
        if candidate not in existing:
            return candidate
    raise RuntimeError('Too many sessions for ' + agent_id)


def remote_script(command, workdir):
    """One shell line for the far side of an ssh hop, quoted as a unit."""
    body = 'exec ' + ' '.join(_quote_preserving_variables(part) for part in command)
    if workdir:
        return 'cd ' + shlex.quote(str(workdir)) + ' && ' + body
    return body


def _quote_preserving_variables(part):
    # A configured "$SHELL" is meant to expand on the far side; anything else
    # is quoted so a directory or model name can never become shell syntax.
    if re.fullmatch(r'\$[A-Za-z_][A-Za-z0-9_]*', part):
        return part
    return shlex.quote(part)


def remote_hop(agent):
    """How to reach the far side, before the command it should run."""
    if agent.get('transport', 'ssh') == 'tailscale-ssh':
        return ['tailscale', 'ssh', agent['host']]
    return ['ssh', '-t', agent['host']]


def new_session_command(document, agent, name, workdir):
    """The tmux invocation that creates the detached session."""
    base = ['tmux', 'new-session', '-d', '-s', name]
    if agent.get('host'):
        # The hop runs locally inside tmux, so the session survives the link.
        return base + ['--'] + remote_hop(agent) + [remote_script(agent['command'], workdir)]
    return base + ['-c', str(workdir)] + ['--'] + list(agent['command'])


def reachability_hint(agent):
    """What to do when a remote agent cannot be reached, in plain terms."""
    host = agent.get('host', 'the host')
    if agent.get('transport', 'ssh') == 'tailscale-ssh':
        return (f'{host} is not accepting Tailscale SSH. On {host} run: '
                'sudo tailscale up --ssh')
    return (f'{host} is not accepting ssh on port 22. Either start sshd there, or '
            f'enable Tailscale SSH on {host} with "sudo tailscale up --ssh" and set '
            f'"transport": "tailscale-ssh" for this agent.')


def attach_command(document, name, title=None):
    terminal = [str(part).format(title=title or name)
                for part in document.get('terminal', ['foot', '-e'])]
    return terminal + ['tmux', 'attach-session', '-t', name]


def parse_sessions(output):
    """Read the tab separated listing produced by list_sessions_command."""
    sessions = []
    for line in (output or '').splitlines():
        fields = line.split('\t')
        if len(fields) < 4:
            continue
        sessions.append({'name': fields[0], 'windows': fields[1],
                         'attached': fields[2] not in ('', '0'), 'path': fields[3]})
    return sessions


def list_sessions_command():
    return ['tmux', 'list-sessions', '-F',
            '#{session_name}\t#{session_windows}\t#{session_attached}\t#{session_path}']


def describe(agent):
    where = f" · {agent['host']}" if agent.get('host') else ''
    subtitle = agent.get('subtitle') or ' '.join(agent['command'])
    return f"{agent['title']}{where} — {subtitle}"


def short_path(path, home=None):
    home = str(home or Path.home())
    text = str(path)
    return '~' + text[len(home):] if text.startswith(home) else text
