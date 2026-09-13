"""Definitions and command building for tmux-contained agent sessions.

Every agent runs inside its own tmux session, so closing the terminal never
kills the work and the same session can be reattached from anywhere. Remote
agents are the same thing with an ssh hop in front, which is why a tailnet host
needs no special handling here.

A preset names its model and effort as fields of their own, and its command
carries {model} and {effort} where they go, so the picker can show exactly
what a session will run before it runs it, and the same words reach the
command line. A preset that names a list of models or efforts instead of one
value asks in the picker, first entry preselected.
"""
import json
import fcntl
import os
from pathlib import Path
import re
import shlex
import stat
import tempfile

SAFE_ID = re.compile(r'[a-z0-9][a-z0-9-]{0,63}')
SAFE_HOST = re.compile(r'[A-Za-z0-9][A-Za-z0-9._-]{0,253}')
# Plain ssh needs keys and a listening sshd; Tailscale SSH needs neither and
# authenticates with the tailnet identity instead.
TRANSPORTS = ('ssh', 'tailscale-ssh')
# The two things a preset can leave open; each is a {field} in its command.
CHOICES = ('model', 'effort')
STATE = Path(os.environ.get('XDG_STATE_HOME') or Path.home() / '.local/state') \
    / 'oldbook/agents/last-workdir.json'


def keyboard_super(capabilities, pressed):
    def bit(bits, key):
        return bool(bits[key // 8] & (1 << (key % 8)))
    return (all(bit(capabilities, key) for key in (30, 28, 57))
            and any(bit(pressed, key) for key in (125, 126)))


def super_pressed():
    # Waybar has no keyboard focus: inspect a current key snapshot, like the
    # artwork control. Never read an event stream or retain keyboard history.
    for device in Path('/dev/input').glob('event*'):
        try:
            fd = os.open(device, os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC | os.O_NOFOLLOW)
            try:
                if not stat.S_ISCHR(os.fstat(fd).st_mode):
                    continue
                capabilities, pressed = bytearray(96), bytearray(96)
                fcntl.ioctl(fd, 0x80604521, capabilities)  # EVIOCGBIT(EV_KEY, 96)
                fcntl.ioctl(fd, 0x80604518, pressed)  # EVIOCGKEY(96)
                if keyboard_super(capabilities, pressed):
                    return True
            finally:
                os.close(fd)
        except OSError:
            continue
    return False


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
        for key in ('enabled', 'trust'):
            if key in agent and not isinstance(agent[key], bool):
                raise ValueError(f'Agent {agent["id"]} {key} must be true or false')
        for field in CHOICES:
            _check_choice(agent, field)
    for key in ('lead', 'quick'):
        named = document.get(key)
        wanted = named if isinstance(named, list) else [named] if named is not None else []
        if not all(isinstance(item, str) for item in wanted) or (
                key == 'quick' and isinstance(named, list)):
            raise ValueError(f'{key} must name agent ids')
        unknown = [item for item in wanted if item not in seen]
        if unknown:
            raise ValueError(f'{key} names agents that do not exist: ' + ', '.join(unknown))
    if 'remember_workdir' in document and not isinstance(document['remember_workdir'], bool):
        raise ValueError('remember_workdir must be true or false')
    return document


def _check_choice(agent, field):
    identity = agent['id']
    value = agent.get(field)
    if value is not None and (not isinstance(value, str) or not value.strip()):
        raise ValueError(f'Agent {identity} {field} must be a non-empty string')
    listed = agent.get(field + 's')
    if listed is not None and (not isinstance(listed, list) or not listed or not all(
            isinstance(item, str) and item.strip() for item in listed)):
        raise ValueError(f'Agent {identity} {field}s must be a non-empty list of names')
    token = '{' + field + '}'
    used = any(token in part for part in agent['command'])
    if used and value is None and listed is None:
        raise ValueError(f'Agent {identity} uses {token} but names neither a {field} '
                         f'nor a {field}s list')
    if not used and (value is not None or listed is not None):
        raise ValueError(f'Agent {identity} names a {field} its command never uses; '
                         f'put {token} in the command')


def enabled_agents(document):
    return [agent for agent in document.get('agents', []) if agent.get('enabled', True)]


def lead_agents(document):
    """The presets that head the picker, in the order the file lists them."""
    wanted = document.get('lead', [])
    agents = {agent['id']: agent for agent in enabled_agents(document)}
    return [agents[identity] for identity in wanted if identity in agents]


def quick_agent(document):
    identity = document.get('quick')
    if identity is None:
        return None
    return next((agent for agent in document['agents'] if agent['id'] == identity), None)


def uses(agent, field):
    token = '{' + field + '}'
    return any(token in part for part in agent['command'])


def open_choices(agent):
    """The fields a preset leaves for the picker to ask about."""
    return [field for field in CHOICES if uses(agent, field) and agent.get(field) is None]


def options(agent, field):
    """What to offer for a field: the preset value first, then the listed rest."""
    preset = agent.get(field)
    listed = agent.get(field + 's') or []
    return ([preset] if preset else []) + [item for item in listed if item != preset]


def selection(agent, field, choices=None):
    return (choices or {}).get(field) or agent.get(field)


def render_command(agent, choices=None):
    """The command with every {model} and {effort} filled in."""
    values = {}
    for field in CHOICES:
        if not uses(agent, field):
            continue
        value = selection(agent, field, choices)
        if not value:
            raise ValueError(f'{agent["title"]} needs a {field}')
        values['{' + field + '}'] = value
    rendered = []
    for part in agent['command']:
        # A plain replacement, not str.format: a command may carry literal
        # braces of its own, such as a JSON settings argument.
        for token, value in values.items():
            part = part.replace(token, value)
        rendered.append(part)
    return rendered


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


def remembered_workdir(agent_id, state=STATE):
    """Where this preset last started, if that is still a directory."""
    try:
        record = json.loads(Path(state).read_text())
    except (OSError, ValueError):
        return None
    path = record.get(agent_id) if isinstance(record, dict) else None
    if isinstance(path, str) and Path(path).is_dir():
        return Path(path).resolve()
    return None


def remember_workdir(agent_id, path, state=STATE):
    state = Path(state)
    try:
        record = json.loads(state.read_text())
    except (OSError, ValueError):
        record = {}
    if not isinstance(record, dict):
        record = {}
    record[agent_id] = str(Path(path).resolve())
    state.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=str(state.parent), prefix='.' + state.name + '.')
    with os.fdopen(handle, 'w') as stream:
        json.dump(record, stream, indent=2)
    os.replace(temporary, state)


def workdir_options(document, agent_id, home=None, state=STATE):
    """The directories to offer: last time's first, then the configured list."""
    listed = expand_workdirs(document, home=home)
    if not document.get('remember_workdir', True):
        return listed, None
    last = remembered_workdir(agent_id, state=state)
    if last is None:
        return listed, None
    return [last] + [path for path in listed if path != last], last


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


def new_session_command(document, agent, name, workdir, choices=None):
    """The tmux invocation that creates the detached session."""
    base = ['tmux', 'new-session', '-d', '-s', name]
    command = render_command(agent, choices)
    if agent.get('host'):
        # The hop runs locally inside tmux, so the session survives the link.
        return base + ['--'] + remote_hop(agent) + [remote_script(command, workdir)]
    return base + ['-c', str(workdir)] + ['--'] + command


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


def title(agent, choices=None):
    """The short name a window carries: title, model and effort."""
    facts = [selection(agent, field, choices) for field in CHOICES if uses(agent, field)]
    return ' · '.join([agent['title'], *[fact for fact in facts if fact]])


def describe(agent, choices=None):
    """One picker line: what it is, what it runs as, and what it may do."""
    host = agent.get('host')
    # A title that already says "on alienware" need not say it twice.
    where = f' · {host}' if host and host.lower() not in agent['title'].lower() else ''
    facts = []
    pending = [field for field in open_choices(agent) if not (choices or {}).get(field)]
    for field in CHOICES:
        if uses(agent, field) and field not in pending:
            facts.append(selection(agent, field, choices))
    if pending:
        facts.append('choose ' + ' and '.join(pending) + '…')
    if agent.get('trust'):
        facts.append('trusts all')
    head = ' · '.join([agent['title'] + where, *facts])
    subtitle = agent.get('subtitle')
    return head + (f' — {subtitle}' if subtitle else '')


def short_path(path, home=None):
    home = str(home or Path.home())
    text = str(path)
    return '~' + text[len(home):] if text.startswith(home) else text
