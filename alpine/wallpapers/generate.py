#!/usr/bin/env python3
"""Generate daily or explicitly requested artwork using the existing ChatGPT login."""
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
sys.path.insert(0, str(REPO / 'alpine/wallpapers'))
from theme_catalog import has_symlink, load_theme, safe_theme_id

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
    try:
        parts = image.relative_to(gallery).parts
    except ValueError:
        parts = ()
    allowed = (len(parts) == 1
               or (len(parts) == 2 and parts[0] == 'general')
               or (len(parts) == 3 and parts[0] == 'themes' and safe_theme_id(parts[1])))
    if (not allowed or sidecar != image.with_suffix('.json') or image.suffix != '.png'
            or has_symlink(image, repository) or has_symlink(sidecar, repository)):
        raise RuntimeError('Checkpoint must be one regular PNG/JSON pair in a supported gallery folder')
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
    if entry.get('theme_descriptor_sha256'):
        identity = entry.get('theme')
        if not safe_theme_id(identity) or len(parts) != 3 or parts[:2] != ('themes', identity):
            raise RuntimeError('Theme checkpoint identity differs from artwork collection')
        descriptor = repository / 'alpine/themes' / (identity + '.json')
        if (has_symlink(descriptor, repository) or not descriptor.is_file()
                or hashlib.sha256(descriptor.read_bytes()).hexdigest() != entry['theme_descriptor_sha256']):
            raise RuntimeError('Theme descriptor changed after artwork generation')
        theme_path = str(descriptor.relative_to(repository))
        if (not fossil('ls', theme_path).strip()
                or fossil('changes', '--added', '--no-classify', '--rel-paths', theme_path).strip() == theme_path):
            paths.append(theme_path)
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


def notify(title, message):
    env = os.environ.copy()
    runtime = Path('/run/user') / str(os.getuid())
    if 'DBUS_SESSION_BUS_ADDRESS' not in env and (runtime / 'bus').exists():
        env['DBUS_SESSION_BUS_ADDRESS'] = 'unix:path=' + str(runtime / 'bus')
    try:
        subprocess.run(['notify-send', '--app-name=Ghost Gallery', '--icon=image-x-generic',
                        title, message], env=env, capture_output=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        pass


def records():
    return sorted([*STATE.glob('????-??-??.json'), *(STATE / 'manual').glob('*.json')])


def manual_scene(config, day):
    previous = []
    for record in records():
        try:
            previous.append(json.loads(record.read_text()))
        except (OSError, ValueError):
            continue
    scenes = config['scenes']
    for entry in sorted(previous, key=lambda e: e.get('started_utc', ''), reverse=True):
        for index, scene in enumerate(scenes):
            if scene['id'] == entry.get('scene'):
                return scenes[(index + 1) % len(scenes)]
    return choose_scene(config, day)


def generate_native(config, prompt, env, log):
    request = (
        'This is an unattended, already-authorized wallpaper generation. '
        'Use the built-in native image generation tool exactly once for the request below. '
        'Do not use an API key, external image API, web search, shell commands or file editing. '
        'Do not ask questions and do not make additional images or refinements. '
        'After generation, return JSON with image_path set to the actual absolute local PNG '
        'path returned by that tool under ~/.codex/generated_images. If native image generation '
        'is unavailable, return an empty image_path without attempting any substitute.\n\n' + prompt
    )
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
            raise RuntimeError(f'Codex exited with status {process.returncode}; see private generation log')
        answer = json.loads((work / 'result.json').read_text())
        if not answer.get('image_path'):
            raise RuntimeError('Codex did not produce a native generated image')
        return answer['image_path']


def activate_artwork(record, metadata, entry):
    try:
        response = subprocess.run(['/usr/bin/python3',
                                   str(REPO / 'alpine/desktop/.local/bin/oldbook-wallpaper'),
                                   'select', entry['id']], capture_output=True, text=True, timeout=20)
        if response.returncode:
            raise RuntimeError(response.stderr.strip()[:1500] or 'Sway could not select the new artwork')
    except (OSError, RuntimeError, subprocess.TimeoutExpired) as error:
        metadata.update({'activated': False, 'activation_error': str(error)})
        atomic_json(record, metadata)
        notify('Artwork saved to the gallery', 'Could not switch the desktop. Select ' + entry['title'] + ' from the gallery when Sway is available.')
        return 1
    metadata.update({'activated': True})
    metadata.pop('activation_error', None)
    atomic_json(record, metadata)
    message = entry['title'] + ' is now on your desktop.'
    if metadata['status'] == 'checkpoint-pending':
        message += ' The image is saved; its local Fossil checkpoint is pending.'
    notify('Space Ghost has finished painting', message)
    return 0


def run_once(scene_override=None, *, manual=False, activate=False, theme='active', new_theme=None):
    STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(STATE, 0o700)
    with (STATE / 'generation.lock').open('a+') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print('A wallpaper generation is already running.')
            if manual:
                notify('Space Ghost is already painting', 'The current request will finish first. No extra image was requested.')
            return 0
        # Cron repairs pending local commits, including manual ones, without
        # generating or unexpectedly changing the desktop during that retry.
        if not manual:
            for pending in records():
                previous = json.loads(pending.read_text())
                if previous.get('status') == 'checkpoint-pending':
                    return checkpoint_record(pending, previous, REPO)
        day = dt.date.today().isoformat()
        if manual:
            (STATE / 'manual').mkdir(exist_ok=True, mode=0o700)
            record = STATE / 'manual' / f'{time.time_ns()}-{os.getpid()}.json'
        else:
            record = STATE / f'{day}.json'
            if record.exists():
                print(f'{day}: daily attempt already reserved; no retry.')
                return 0
        config = json.loads((REPO / 'alpine/wallpapers/prompts.json').read_text())
        if new_theme is not None:
            from new_themes import design_theme
            lock.seek(0)
            lock.truncate()
            json.dump({'title': 'Designing ' + (new_theme or 'a random new theme')}, lock)
            lock.flush()
            notify('Space Ghost is designing a theme…', new_theme or 'A surprise collection and its first painting.')
            try:
                env = clean_environment()
                login = subprocess.run(['codex', 'login', 'status'], env=env, capture_output=True,
                                       text=True, timeout=20)
                if login.returncode or 'Logged in using ChatGPT' not in login.stdout + login.stderr:
                    raise RuntimeError('Theme generation requires existing Codex ChatGPT login.')
                selected_theme = design_theme(REPO, config, env, record.with_suffix('.theme.jsonl'),
                                              new_theme, codex_command)
            except (RuntimeError, OSError, ValueError, subprocess.TimeoutExpired) as error:
                atomic_json(record, {'status': 'failed', 'phase': 'theme', 'error': str(error)})
                notify('Theme design hit a snag', str(error)[:300])
                raise
        else:
            selected_theme = load_theme(REPO, theme)
        gallery = REPO / 'alpine/assets/gallery'
        gallery /= 'general' if selected_theme['id'] == 'none' else 'themes/' + selected_theme['id']
        if has_symlink(gallery, REPO):
            raise RuntimeError('Artwork destination must be a regular directory in the gallery')
        if scene_override:
            scene = next((s for s in config['scenes'] if s['id'] == scene_override), None)
            if scene is None:
                raise RuntimeError('Unknown scene: ' + scene_override)
        elif new_theme is not None:
            scene = {'id': 'debut', 'title': selected_theme['name'], 'description': selected_theme['scene']}
        else:
            scene = manual_scene(config, day) if manual else choose_scene(config, day)
        started = time.time()
        metadata = {'day': day, 'status': 'reserved', 'scene': scene['id'], 'manual': manual,
                    'model': config['model'], 'theme': selected_theme['id'], 'theme_name': selected_theme['name'],
                    'started_utc': dt.datetime.now(dt.timezone.utc).isoformat()}
        # Reserve before making a model request. Daily failures cannot retry.
        atomic_json(record, metadata)
        lock.seek(0)
        lock.truncate()
        json.dump({'title': scene['title'], 'started_utc': metadata['started_utc']}, lock)
        lock.flush()
        try:
            env = clean_environment()
            login = subprocess.run(['codex', 'login', 'status'], env=env, capture_output=True,
                                   text=True, timeout=20)
            if login.returncode or 'Logged in using ChatGPT' not in login.stdout + login.stderr:
                raise RuntimeError('This job requires existing Codex ChatGPT login; no API fallback.')
            if manual:
                destination_notice = 'appear on your desktop' if activate else 'be saved in the gallery'
                notify('Space Ghost is painting…', scene['title'] + '. Your new artwork will ' + destination_notice + ' when ready.')
            prompt = config['style']
            if selected_theme['image_style']:
                prompt += '\n\nTheme: ' + selected_theme['name'] + '. ' + selected_theme['image_style']
            prompt += '\n\nScene: ' + scene['description']
            source_path = generate_native(config, prompt, env, record.with_suffix('.jsonl'))
            source, width, height = validate_image(source_path,
                                                   Path(env['CODEX_HOME']) / 'generated_images', started)
            digest = hashlib.sha256(source.read_bytes()).hexdigest()
            if has_symlink(gallery, REPO):
                raise RuntimeError('Artwork destination must remain a regular directory in the gallery')
            gallery.mkdir(parents=True, exist_ok=True)
            stem = f'{day}-{selected_theme["id"]}-{scene["id"]}-{digest[:12]}'
            destination = gallery / f'{stem}.png'
            if destination.exists():
                raise RuntimeError('Refusing to replace an existing gallery artifact')
            temporary = destination.with_suffix('.png.tmp')
            shutil.copyfile(source, temporary)
            temporary.replace(destination)
            entry = {'id': stem, 'title': scene['title'], 'description': scene['description'],
                     'file': str(destination.relative_to(REPO)), 'sha256': digest,
                     'width': width, 'height': height, 'prompt': prompt,
                     'theme': selected_theme['id'], 'theme_name': selected_theme['name'],
                     'theme_style': selected_theme['image_style'],
                     'theme_palette': selected_theme.get('palette', {}),
                     'generator': 'Codex CLI native image_generation',
                     'orchestrator_model': config['model'], 'image_model': 'gpt-image-2',
                     'generated_utc': dt.datetime.now(dt.timezone.utc).isoformat(),
                     'rebuild': 'Restore this exact hashed bitmap; new generations are not deterministic.'}
            if selected_theme.get('generated_by') == 'ghost-gallery':
                descriptor = REPO / 'alpine/themes' / (selected_theme['id'] + '.json')
                entry['theme_descriptor_sha256'] = hashlib.sha256(descriptor.read_bytes()).hexdigest()
            atomic_json(gallery / f'{stem}.json', entry)
            metadata.update({'status': 'checkpoint-pending', 'file': entry['file'], 'sha256': digest})
            atomic_json(record, metadata)
            checkpoint_result = checkpoint_record(record, metadata, REPO)
            activation_result = activate_artwork(record, metadata, entry) if activate else 0
            return max(checkpoint_result, activation_result)
        except Exception as error:
            if metadata.get('status') not in ('checkpoint-pending', 'complete'):
                metadata['status'] = 'failed'
            metadata['error'] = str(error)
            atomic_json(record, metadata)
            if manual:
                notify('Space Ghost hit a snag', 'Your current wallpaper is unchanged. ' + str(error)[:300])
            raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scene', help='Select a named scene from prompts.json.')
    parser.add_argument('--theme', default='active', help='active (default), none, or a theme ID from alpine/themes/.')
    parser.add_argument('--new-theme', nargs='?', const='', help='Create a collection from a phrase, or random if empty.')
    parser.add_argument('--manual', action='store_true', help='One explicit request, independent of the daily schedule.')
    parser.add_argument('--activate', action='store_true', help='Switch to the newly saved artwork when ready.')
    parser.add_argument('--print-command', action='store_true', help='Show the cron-safe command without generating.')
    args = parser.parse_args()
    if args.new_theme is not None and (not args.manual or args.scene or args.theme != 'active'):
        parser.error('--new-theme requires --manual and cannot combine with --scene or --theme')
    if args.print_command:
        import shlex
        print(shlex.join(['/usr/bin/python3', str(Path(__file__).resolve())]))
        return
    sys.exit(run_once(args.scene, manual=args.manual, activate=args.activate, theme=args.theme, new_theme=args.new_theme))


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, OSError, ValueError, subprocess.TimeoutExpired) as error:
        print(f'Wallpaper generation: {error}', file=sys.stderr)
        sys.exit(1)
