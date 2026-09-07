#!/usr/bin/env python3
"""Generate at most one daily gallery image using the existing ChatGPT login."""
import argparse
import binascii
import datetime as dt
import fcntl
import hashlib
import json
import os
import re
from pathlib import Path
import shutil
import signal
import struct
import subprocess
import sys
import tempfile
import time

REPO = Path(__file__).resolve().parents[2]
STATE = Path.home() / '.local/state/oldbook/wallpaper-generation'
SCHEMA = {'type': 'object', 'properties': {'image_path': {'type': 'string'}},
          'required': ['image_path'], 'additionalProperties': False}


def atomic_json(path, data):
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(data, indent=2) + '\n')
    temporary.replace(path)


def clean_environment():
    # Deliberate allowlist: never pass API credentials, agent socket overrides,
    # inherited Codex internals, or arbitrary developer settings into cron.
    env = {name: os.environ[name] for name in ('HOME', 'USER', 'LOGNAME', 'LANG', 'TZ')
           if name in os.environ}
    env['HOME'] = str(Path.home())
    env['PATH'] = '/usr/local/bin:/usr/bin:/bin'
    env['CODEX_HOME'] = str(Path.home() / '.codex')
    return env


def choose_scene(config, day):
    # Daily permutation visits every scene before repeating, independent of RNG.
    scenes = config['scenes']
    return scenes[dt.date.fromisoformat(day).toordinal() % len(scenes)]


def validate_image(path, generated_root, started):
    path = Path(path)
    resolved = path.resolve(strict=True)
    if path.is_symlink() or not resolved.is_relative_to(generated_root.resolve()):
        raise RuntimeError('Image must be a new native Codex generated artifact')
    if not resolved.is_file() or resolved.stat().st_mtime < started - 2:
        raise RuntimeError('Image was not produced by this generation run')
    if not 10_000 <= resolved.stat().st_size <= 100_000_000:
        raise RuntimeError('Generated image has an unexpected size')
    data = resolved.read_bytes()
    if data[:8] != b'\x89PNG\r\n\x1a\n' or data[12:16] != b'IHDR':
        raise RuntimeError('Generated artifact is not a PNG image')
    width, height = struct.unpack('>II', data[16:24])
    if width < 1024 or height < 600 or width > 8192 or height > 8192 or not 1.25 <= width / height <= 2.0:
        raise RuntimeError(f'Expected a landscape wallpaper, received {width}x{height}')
    offset, have_data, complete = 8, False, False
    while offset + 12 <= len(data):
        size = struct.unpack('>I', data[offset:offset + 4])[0]
        end = offset + size + 12
        if end > len(data):
            raise RuntimeError('Truncated generated PNG chunk')
        kind = data[offset + 4:offset + 8]
        expected_crc = struct.unpack('>I', data[end - 4:end])[0]
        if binascii.crc32(data[offset + 4:end - 4]) != expected_crc:
            raise RuntimeError('Generated PNG chunk checksum failed')
        have_data = have_data or kind == b'IDAT'
        offset = end
        if kind == b'IEND':
            complete = size == 0 and offset == len(data)
            break
    if not have_data or not complete:
        raise RuntimeError('Generated PNG is incomplete')
    return resolved, width, height


def codex_command(work, model):
    return ['codex', '-a', 'never', 'exec', '--ignore-user-config', '--ephemeral',
            '--skip-git-repo-check', '--sandbox', 'workspace-write', '--cd', str(work),
            '--enable', 'image_generation', '--disable', 'plugins', '--disable', 'apps',
            '--disable', 'multi_agent', '--disable', 'shell_tool', '--disable', 'hooks',
            '-c', 'model_reasoning_effort="low"', '-c', 'web_search="disabled"',
            '-c', 'project_doc_max_bytes=0', '-m', model, '--color', 'never', '--json',
            '--output-schema', str(work / 'schema.json'),
            '--output-last-message', str(work / 'result.json'), '-']



def checkpoint_generated(image, sidecar, repository=REPO):
    """Commit only this new artwork pair, with sync and external hooks excluded."""
    repository = repository.resolve()
    gallery = repository / 'alpine/assets/gallery'
    image, sidecar = Path(image), Path(sidecar)
    if (image.parent.resolve() != gallery.resolve() or sidecar != image.with_suffix('.json')
            or image.suffix != '.png'):
        raise RuntimeError('Checkpoint must be one PNG/JSON pair in the gallery')
    for path in (image, sidecar):
        if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(repository):
            raise RuntimeError('Checkpoint paths must be regular files inside the checkout')
    entry = json.loads(sidecar.read_text())
    if (entry.get('file') != str(image.relative_to(repository))
            or hashlib.sha256(image.read_bytes()).hexdigest() != entry.get('sha256')):
        raise RuntimeError('Checkpoint image and sidecar identity differ')

    def fossil(*arguments):
        result = subprocess.run(['fossil', *arguments], cwd=repository,
                                stdin=subprocess.DEVNULL, capture_output=True,
                                text=True, timeout=60)
        if result.returncode:
            raise RuntimeError('Fossil checkpoint failed: ' + result.stderr.strip()[:1500])
        return result.stdout

    # --nosync suppresses the pre-commit sync. Require the effective setting
    # off as well, because it also prevents post-commit autosync. No hook is
    # bypassed: repositories with configured hooks stay pending for review.
    if fossil('settings', 'autosync', '--value').strip().lower() != 'off':
        raise RuntimeError('Local artwork checkpoint requires Fossil autosync off')
    if fossil('hook', 'list').strip():
        raise RuntimeError('Fossil hooks are configured; artwork remains pending for manual review')
    if fossil('changes', '--merge', '--no-classify').strip():
        raise RuntimeError('A merge is pending; artwork checkpoint cannot include merge state')
    paths = [str(path.relative_to(repository)) for path in (image, sidecar)]
    for path in paths:
        tracked = fossil('ls', path).strip()
        added = fossil('changes', '--added', '--no-classify', '--rel-paths', path).strip()
        if tracked and added != path:
            raise RuntimeError('Automatic checkpoints only accept newly added artwork')
    fossil('add', '--', *paths)
    # Explicit paths leave every other tracked edit and added file untouched.
    result = fossil('commit', '--nosync', '--nosign', '--no-prompt', '--no-warnings',
                    '--hash', '-m', 'art: preserve generated ' + image.stem, '--', *paths)
    match = re.search(r'New_Version:\s+([0-9a-f]{40,64})', result)
    if not match:
        raise RuntimeError('Fossil did not report a checkpoint identifier; inspect history')
    return match.group(1)


def checkpoint_record(record, metadata, repository=REPO):
    """Preserve the daily reservation and artwork even if a local commit fails."""
    image = repository / metadata['file']
    try:
        checkin = checkpoint_generated(image, image.with_suffix('.json'), repository)
    except (RuntimeError, OSError, ValueError, subprocess.TimeoutExpired) as error:
        metadata.update({'status': 'checkpoint-pending', 'checkpoint_error': str(error)})
        atomic_json(record, metadata)
        print('Artwork saved; local Fossil checkpoint pending: ' + str(error), file=sys.stderr)
        return 1
    metadata.pop('checkpoint_error', None)
    metadata.update({'status': 'complete', 'checkpoint': checkin})
    atomic_json(record, metadata)
    print(f'Artwork preserved in local Fossil checkpoint {checkin[:12]}; nothing published.')
    return 0


def run_once(scene_override=None):
    STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(STATE, 0o700)
    with (STATE / 'generation.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print('A wallpaper generation is already running.')
            return 0
        # Finish older local checkpoints before requesting another billed image.
        for pending in sorted(STATE.glob('????-??-??.json')):
            previous = json.loads(pending.read_text())
            if previous.get('status') == 'checkpoint-pending':
                return checkpoint_record(pending, previous, REPO)
        day = dt.date.today().isoformat()
        record = STATE / f'{day}.json'
        if record.exists():
            print(f'{day}: daily attempt already reserved; no retry.')
            return 0
        config = json.loads((REPO / 'alpine/wallpapers/prompts.json').read_text())
        scene = (next(s for s in config['scenes'] if s['id'] == scene_override)
                 if scene_override else choose_scene(config, day))
        env = clean_environment()
        login = subprocess.run(['codex', 'login', 'status'], env=env, capture_output=True,
                               text=True, timeout=20)
        if login.returncode or 'Logged in using ChatGPT' not in login.stdout + login.stderr:
            raise RuntimeError('This job requires existing Codex ChatGPT login; no API fallback.')
        started = time.time()
        metadata = {'day': day, 'status': 'reserved', 'scene': scene['id'],
                    'model': config['model'], 'started_utc': dt.datetime.now(dt.timezone.utc).isoformat()}
        # Reserve before making a model request. Failures cannot create a retry loop.
        atomic_json(record, metadata)
        log = STATE / f'{day}.jsonl'
        prompt = config['style'] + '\n\nScene: ' + scene['description']
        request = (
            'This is an unattended, already-authorized wallpaper generation. '
            'Use the built-in native image generation tool exactly once for the request below. '
            'Do not use an API key, external image API, web search, shell commands or file editing. '
            'Do not ask questions and do not make additional images or refinements. '
            'After generation, return JSON with image_path set to the actual absolute local PNG '
            'path returned by that tool under ~/.codex/generated_images. If native image generation '
            'is unavailable, return an empty image_path without attempting any substitute.\n\n' + prompt
        )
        try:
            with tempfile.TemporaryDirectory(prefix='oldbook-art-') as directory:
                work = Path(directory)
                (work / 'schema.json').write_text(json.dumps(SCHEMA))
                with log.open('w') as output:
                    process = subprocess.Popen(codex_command(work, config['model']), env=env,
                                               stdin=subprocess.PIPE, stdout=output,
                                               stderr=subprocess.STDOUT, text=True,
                                               start_new_session=True)
                    try:
                        process.communicate(request, timeout=min(900, max(60, int(config.get('timeout_seconds', 900)))))
                    except subprocess.TimeoutExpired:
                        os.killpg(process.pid, signal.SIGTERM)
                        try:
                            process.wait(timeout=10)
                        except subprocess.TimeoutExpired:
                            os.killpg(process.pid, signal.SIGKILL)
                            process.wait()
                        raise RuntimeError('Generation exceeded its 15-minute deadline') from None
                if process.returncode:
                    raise RuntimeError(f'Codex exited with status {process.returncode}; see private daily log')
                answer = json.loads((work / 'result.json').read_text())
                if not answer.get('image_path'):
                    raise RuntimeError('Codex did not produce a native generated image')
                source, width, height = validate_image(answer['image_path'],
                                                       Path(env['CODEX_HOME']) / 'generated_images', started)
                digest = hashlib.sha256(source.read_bytes()).hexdigest()
                gallery = REPO / 'alpine/assets/gallery'
                gallery.mkdir(parents=True, exist_ok=True)
                stem = f'{day}-{scene["id"]}-{digest[:12]}'
                destination = gallery / f'{stem}.png'
                if destination.exists():
                    raise RuntimeError('Refusing to replace an existing gallery artifact')
                temporary = destination.with_suffix('.png.tmp')
                shutil.copyfile(source, temporary)
                temporary.replace(destination)
                entry = {'id': stem, 'title': scene['title'], 'description': scene['description'],
                         'file': str(destination.relative_to(REPO)), 'sha256': digest,
                         'width': width, 'height': height, 'prompt': prompt,
                         'generator': 'Codex CLI native image_generation',
                         'orchestrator_model': config['model'], 'image_model': 'gpt-image-2',
                         'generated_utc': dt.datetime.now(dt.timezone.utc).isoformat(),
                         'rebuild': 'Restore this exact hashed bitmap; new generations are not deterministic.'}
                atomic_json(gallery / f'{stem}.json', entry)
                metadata.update({'status': 'checkpoint-pending', 'file': entry['file'], 'sha256': digest})
                atomic_json(record, metadata)
                return checkpoint_record(record, metadata, REPO)
        except Exception as error:
            if metadata.get('status') != 'checkpoint-pending':
                metadata['status'] = 'failed'
            metadata['error'] = str(error)
            atomic_json(record, metadata)
            raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scene', help='Select a named scene for today; still limited to one attempt.')
    parser.add_argument('--print-command', action='store_true', help='Show the cron-safe command without generating.')
    args = parser.parse_args()
    if args.print_command:
        import shlex
        print(shlex.join(['/usr/bin/python3', str(Path(__file__).resolve())]))
        return
    sys.exit(run_once(args.scene))


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, OSError, ValueError, subprocess.TimeoutExpired) as error:
        print(f'Wallpaper generation: {error}', file=sys.stderr)
        sys.exit(1)
