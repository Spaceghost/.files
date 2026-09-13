"""Whether a painting is made without anyone asking for one by name.

Painting is the one step of this gallery that spends something outside the
machine -- Codex image credits -- and so the one step that stops when that
account runs dry. That is how a new theme came to depend on a painting: the
descriptor was designed as text and saved, and then the whole run waited on a
painter that could not paint before the theme was ever applied. Jack: "I want
to freely generate themes even without the image gen ... temporarily disable
it for theme-gen and elsewhere unless called specifically."

So painting has a policy of its own, read from ~/.config/oldbook/painting.json,
answering two questions: does the hourly schedule paint the day's painting,
and does a newly created theme get a debut painting. Both default to off.
Nothing here touches an explicit request -- "Generate new artwork" in the
gallery, Super+click on the badge, `generate.py --manual` from a terminal --
because a person asking for a painting by name is exactly what "called
specifically" means. A missing or malformed file is the shipped default, not
an error: the policy must never be the reason a painting fails to be reported.
"""
import json
import os
from pathlib import Path

FILE = 'painting.json'
DEFAULTS = {'scheduled': False, 'debut_painting': False}
# What each switch means, for the messages that say why nothing was painted.
MEANING = {
    'scheduled': 'the hourly schedule paints one painting a day',
    'debut_painting': 'a newly created theme is given a first painting',
}


def path():
    """The user's own copy; the shipped default is deployed beside it as a link."""
    root = os.environ.get('XDG_CONFIG_HOME') or str(Path.home() / '.config')
    return Path(root) / 'oldbook' / FILE


def load(source=None):
    """The policy, with anything the file leaves out or gets wrong at its default."""
    source = Path(source) if source is not None else path()
    policy = dict(DEFAULTS)
    try:
        document = json.loads(source.read_text())
    except (OSError, ValueError):
        return policy
    if not isinstance(document, dict):
        return policy
    for key in DEFAULTS:
        if isinstance(document.get(key), bool):
            policy[key] = document[key]
    return policy


def allows(kind, source=None):
    """True when this kind of unasked-for painting is switched on."""
    if kind not in DEFAULTS:
        raise ValueError('Unknown painting policy: ' + str(kind))
    return load(source)[kind]


def refusal(kind, source=None):
    """One sentence saying what was not painted and where to change that."""
    where = Path(source) if source is not None else path()
    return (f'Painting is off: {MEANING[kind]} only when "{kind}" is true in '
            f'{where}. An explicit request still paints.')
