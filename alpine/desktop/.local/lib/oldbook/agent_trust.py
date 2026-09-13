"""Pre-accept the workspace trust an agent CLI would otherwise stop to ask for.

Claude Code and Codex both open on a "do you trust this directory?" screen the
first time they see a directory, whatever permission flags they were started
with: Claude's defaults to "No, exit", Codex's to "Yes, continue". Either one is
a keystroke between the launcher's last Enter and the first typed word, which
is exactly the gap the launcher exists to close. Both tools keep the answer in
their own configuration, keyed by the git root when the directory is inside a
git work tree and by the directory itself otherwise, and each names setting it
there by hand as the supported way to pre-accept, so that is what this does --
for a local agent whose preset says "trust": true, just before its session is
created.

Nothing here reaches a remote host: the far side of an ssh hop keeps its own
answers, and nothing here changes what the tools are allowed to do once they
are running; the permission flags on each preset's command do that.
"""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time
import tomllib

CLAUDE_CONFIG = Path.home() / '.claude.json'
CODEX_CONFIG = Path.home() / '.codex/config.toml'
# Claude Code holds a lock directory beside its file while it writes; a
# launch should wait that out rather than race it, but never for long.
LOCK_WAIT = 2.0


def tool_name(command):
    """The program a preset runs, without its directory."""
    return Path(command[0]).name if command else ''


def trust_key(workdir):
    """The path a CLI files its answer under: the git root, else the directory."""
    directory = Path(workdir).expanduser().resolve()
    git = shutil.which('git')
    if git:
        try:
            result = subprocess.run([git, '-C', str(directory), 'rev-parse', '--show-toplevel'],
                                    capture_output=True, text=True, timeout=5)
        except (OSError, subprocess.SubprocessError):
            result = None
        if result is not None and result.returncode == 0 and result.stdout.strip():
            return str(Path(result.stdout.strip()).resolve())
    return str(directory)


def grant(command, workdir, claude_config=CLAUDE_CONFIG, codex_config=CODEX_CONFIG):
    """Record trust for workdir with whichever tool the command runs.

    Returns the path that was written, or None when the tool keeps no such
    answer or already had this one.
    """
    tool = tool_name(command)
    if tool == 'claude':
        return grant_claude(trust_key(workdir), claude_config)
    if tool == 'codex':
        return grant_codex(trust_key(workdir), codex_config)
    return None


def grant_claude(key, config=CLAUDE_CONFIG):
    """Set projects[key].hasTrustDialogAccepted in Claude Code's own file."""
    config = Path(config)
    _wait_for_lock(config.with_name(config.name + '.lock'))
    document = {}
    if config.exists():
        text = config.read_text()
        document = json.loads(text) if text.strip() else {}
    if not isinstance(document, dict):
        raise ValueError(f'{config} is not a JSON object')
    projects = document.setdefault('projects', {})
    if not isinstance(projects, dict):
        raise ValueError(f'{config} has a projects entry that is not an object')
    entry = projects.setdefault(key, {})
    if not isinstance(entry, dict):
        raise ValueError(f'{config} has a project entry for {key} that is not an object')
    if entry.get('hasTrustDialogAccepted') is True:
        return None
    entry['hasTrustDialogAccepted'] = True
    _replace(config, json.dumps(document, indent=2) + '\n')
    return config


def grant_codex(key, config=CODEX_CONFIG):
    """Set trust_level = "trusted" under [projects."key"] in Codex's config.toml."""
    config = Path(config)
    text = config.read_text() if config.exists() else ''
    document = tomllib.loads(text)
    projects = document.get('projects', {})
    if not isinstance(projects, dict):
        raise ValueError(f'{config} has a projects entry that is not a table')
    if projects.get(key, {}).get('trust_level') == 'trusted':
        return None
    header = f'[projects."{_toml_escape(key)}"]'
    if key in projects:
        text = _set_in_table(text, header, 'trust_level = "trusted"')
    else:
        text = text.rstrip('\n') + ('\n\n' if text.strip() else '') + header + '\ntrust_level = "trusted"\n'
    if tomllib.loads(text).get('projects', {}).get(key, {}).get('trust_level') != 'trusted':
        raise ValueError(f'could not record trust for {key} in {config}')
    _replace(config, text)
    return config


def _toml_escape(value):
    return value.replace('\\', '\\\\').replace('"', '\\"')


def _set_in_table(text, header, assignment):
    """Replace or add one key inside the table that starts at header."""
    lines = text.split('\n')
    try:
        start = next(index for index, line in enumerate(lines) if line.strip() == header)
    except StopIteration:
        raise ValueError(f'{header} exists but is written in a form this cannot edit; '
                         f'set {assignment} there by hand') from None
    end = next((index for index in range(start + 1, len(lines))
                if lines[index].lstrip().startswith('[')), len(lines))
    key = assignment.split('=', 1)[0].strip()
    pattern = re.compile(r'^\s*' + re.escape(key) + r'\s*=')
    for index in range(start + 1, end):
        if pattern.match(lines[index]):
            lines[index] = assignment
            break
    else:
        lines.insert(start + 1, assignment)
    return '\n'.join(lines)


def _wait_for_lock(lock, limit=LOCK_WAIT):
    deadline = time.monotonic() + limit
    while lock.exists() and time.monotonic() < deadline:
        time.sleep(0.05)


def _replace(path, text):
    """Write the whole file through a rename, keeping its mode, so a reader
    never sees a half-written configuration."""
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = path.stat().st_mode & 0o777 if path.exists() else 0o600
    handle, temporary = tempfile.mkstemp(dir=str(path.parent), prefix='.' + path.name + '.')
    try:
        with os.fdopen(handle, 'w') as stream:
            stream.write(text)
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise
