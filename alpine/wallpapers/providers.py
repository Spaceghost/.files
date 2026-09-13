"""Who is asked to design and to paint, and in what order they are asked.

One account being out of credit should not mean no wallpaper. The generator
therefore has a chain rather than a provider: Codex first because it is the one
that can both design and paint, then Claude, then the Alienware, which is this
household's own hardware and answers when nobody's billing does.

The two kinds of work are not interchangeable and the chains differ because of
it. *Designing* is text: a theme or a scene as JSON against a schema, which any
capable model can do, so all three appear. *Painting* is diffusion, which
neither Claude nor an Ollama server does at all, so the image chain skips
straight from Codex to whatever the Alienware is running for images. Listing a
provider that cannot do the work would only spend a minute proving it.

A refusal is not the same as a failure. When a provider says it is out of
credit or not logged in, trying it three more times is a waste of four minutes
and tells the user nothing new, so those reasons end that provider's turn
immediately and the chain moves on. Anything else -- a timeout, a malformed
answer, a network blip -- is worth another attempt.
"""
import json
import os
from pathlib import Path
import ssl
import subprocess
import urllib.error
import urllib.request

DESIGN_ORDER = ('codex', 'claude', 'alienware')
IMAGE_ORDER = ('codex', 'alienware')
# What a provider says when asking it again is pointless. Matched against the
# reason the runner itself gave, folded to lower case.
EXHAUSTED = ('usage limit', 'rate limit', 'quota', 'out of credit', 'insufficient credit',
             'not logged in', 'unauthorized', 'authentication', 'invalid api key',
             'expired', 'forbidden', 'payment')
DEFAULTS = {
    'design': list(DESIGN_ORDER),
    'image': list(IMAGE_ORDER),
    'claude': {'model': 'claude-sonnet-5', 'timeout_seconds': 300},
    'alienware': {
        'design_endpoint': 'https://alienware.bishop-bearded.ts.net:11434',
        'design_model': 'qwen3.5:27b-text',
        'timeout_seconds': 600,
        # Ollama does not paint. This is where a diffusion server would answer,
        # and until one does the image rung reports what is missing rather than
        # pretending the Alienware has nothing to offer.
        'image_endpoint': '',
        'image_model': '',
    },
}


def settings(config, name=None):
    """The providers block, with anything the config leaves out filled in."""
    block = dict(DEFAULTS)
    configured = (config or {}).get('providers')
    if isinstance(configured, dict):
        for key, value in configured.items():
            if isinstance(value, dict) and isinstance(block.get(key), dict):
                block[key] = {**block[key], **value}
            else:
                block[key] = value
    return block if name is None else block.get(name, {})


def chain(config, kind):
    """The providers to try for this kind of work, in order, without repeats."""
    order = settings(config).get(kind) or list(DEFAULTS[kind])
    known = DESIGN_ORDER if kind == 'design' else IMAGE_ORDER
    return [name for index, name in enumerate(order)
            if name in known and name not in order[:index]]


def exhausted(reason):
    """Is this a reason to stop asking this provider rather than to retry it?"""
    if not reason:
        return False
    folded = str(reason).casefold()
    return any(phrase in folded for phrase in EXHAUSTED)


# ---- designing -------------------------------------------------------------


def claude_design(config, env, log, prompt, schema, _command_builder=None):
    """Ask the Claude CLI for the same JSON, through the login already here."""
    options = settings(config, 'claude')
    instruction = (prompt + '\n\nReply with one JSON object and nothing else: no prose, '
                   'no explanation and no code fence. It must validate against this '
                   'JSON Schema:\n' + json.dumps(schema))
    command = ['claude', '-p', instruction, '--output-format', 'json',
               '--model', options.get('model', 'claude-sonnet-5')]
    with Path(log).open('w') as output:
        process = subprocess.run(command, env=env, stdin=subprocess.DEVNULL,
                                 stdout=subprocess.PIPE, stderr=output, text=True,
                                 timeout=options.get('timeout_seconds', 300))
        output.write(process.stdout or '')
    if process.returncode:
        raise RuntimeError(f'Claude exited with status {process.returncode}')
    try:
        envelope = json.loads(process.stdout)
    except ValueError as error:
        raise RuntimeError(f'Claude returned no JSON envelope: {error}') from error
    if envelope.get('is_error'):
        raise RuntimeError(str(envelope.get('result') or 'Claude reported an error'))
    return json.loads(strip_fence(envelope.get('result') or ''))


def strip_fence(text):
    """Take the JSON out of a reply that arrived wearing a code fence."""
    text = (text or '').strip()
    if text.startswith('```'):
        text = text.split('\n', 1)[-1]
        text = text.rsplit('```', 1)[0]
    return text.strip()


def alienware_design(config, _env, log, prompt, schema, _command_builder=None):
    """Ask the household's own GPUs, which owe nobody a subscription."""
    options = settings(config, 'alienware')
    endpoint = (options.get('design_endpoint') or '').rstrip('/')
    if not endpoint:
        raise RuntimeError('No Alienware design endpoint is configured')
    body = json.dumps({
        'model': options.get('design_model', 'qwen3.5:27b-text'),
        'prompt': prompt,
        'stream': False,
        # Ollama constrains the answer to the schema itself, so there is no
        # fence to strip and no prose to apologise for.
        'format': schema,
        'options': {'temperature': 0.8},
    }).encode()
    request = urllib.request.Request(endpoint + '/api/generate', data=body,
                                     headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(
                request, timeout=options.get('timeout_seconds', 600)) as response:
            envelope = json.load(response)
    except urllib.error.HTTPError as error:
        detail = error.read(400).decode('utf-8', 'replace').strip()
        raise RuntimeError(f'The Alienware answered {error.code}: {detail}') from error
    except (urllib.error.URLError, OSError, ssl.SSLError) as error:
        raise RuntimeError(f'The Alienware could not be reached: {error}') from error
    except ValueError as error:
        raise RuntimeError(f'The Alienware returned no JSON: {error}') from error
    Path(log).write_text(json.dumps(envelope, indent=2) + '\n')
    return json.loads(strip_fence(envelope.get('response') or ''))


# ---- painting --------------------------------------------------------------


def alienware_image(config, _prompt, _env, _log):
    """Paint on the Alienware, once something there can paint.

    Ollama runs language models and cannot run a diffusion pipeline, so this
    rung stays honest about being unfinished rather than failing obscurely: it
    names what has to exist on the far side and what stands in the way of
    putting it there.
    """
    options = settings(config, 'alienware')
    endpoint = (options.get('image_endpoint') or '').strip()
    if not endpoint:
        raise RuntimeError(
            'The Alienware has no image endpoint yet: its Ollama server runs language '
            'models only and cannot paint. Installing a diffusion server there needs '
            'SSH, which the tailnet policy currently refuses for this laptop. See '
            'docs/GENERATION-FALLBACK.md for the model this is sized for.')
    raise RuntimeError(f'The Alienware image endpoint {endpoint} is configured but '
                       'this build has no client for it yet')


DESIGNERS = {'claude': claude_design, 'alienware': alienware_design}
PAINTERS = {'alienware': alienware_image}
