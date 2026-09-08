#!/usr/bin/env python3
"""Bounded storage and native integration evidence for Scripture study."""
from contextlib import redirect_stdout
import hashlib
import importlib.machinery
import io
import json
import os
from pathlib import Path
import shutil
import sqlite3
import struct
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
import zlib


REPO = Path(__file__).resolve().parents[2]
OUTPUT = REPO / 'alpine/verification/scripture-study'
ASSETS = REPO / 'alpine/assets/scripture'
HELPER = REPO / 'alpine/desktop/.local/bin/mbp-intel-scripture'
BAR = REPO / 'alpine/desktop/.local/bin/mbp-intel-scripture-bar'
LIBRARY = REPO / 'alpine/desktop/.local/lib/mbp_intel'
sys.path.insert(0, str(LIBRARY))
import scripture_study as study


def fixture(identifier, kind, title):
    """Return synthetic schema-valid content; no prose is generated here."""
    source_text = f'Verification fixture source for {identifier}.'
    return {
        'schema': 1,
        'id': identifier,
        'kind': kind,
        'figure': 'Integration fixture',
        'title': title,
        'reference': 'John 1:1',
        'trial': 'Synthetic integration fixture.',
        'reflection': 'Synthetic integration fixture.',
        'practice': 'Synthetic integration fixture.',
        'cited_source_ids': [f'source-{identifier[-8:]}'],
        'sources': [{
            'id': f'source-{identifier[-8:]}',
            'title': 'Integration fixture source',
            'url': f'https://example.test/scripture-study/{identifier}',
            'license': 'CC0-1.0',
            'text': source_text,
            'sha256': hashlib.sha256(source_text.encode()).hexdigest(),
        }],
        'provenance': {
            'method': 'local-ollama',
            'model': 'fixture-model',
            'model_digest': 'sha256:' + 'd' * 64,
            'endpoint': 'http://127.0.0.1:11434',
            'created_utc': '2026-09-08T04:00:00Z',
            'prompt_sha256': hashlib.sha256(identifier.encode()).hexdigest(),
        },
    }


def fossil_environment(home):
    config = home / '.config'
    cache = home / '.cache'
    config.mkdir(parents=True, exist_ok=True)
    cache.mkdir(parents=True, exist_ok=True)
    environment = dict(os.environ, HOME=str(home), XDG_CONFIG_HOME=str(config),
                       XDG_CACHE_HOME=str(cache))
    environment.pop('FOSSIL_HOME', None)
    return environment


def run(command, *, cwd, environment, log, timeout=45):
    rendered = ' '.join(map(str, command))
    completed = subprocess.run(command, cwd=cwd, env=environment, capture_output=True,
                               text=True, timeout=timeout)
    log.write(f'$ ({cwd}) {rendered}\n{completed.stdout}{completed.stderr}')
    log.flush()
    if completed.returncode:
        raise RuntimeError(f'command failed ({completed.returncode}): {rendered}\n'
                           f'{completed.stdout}{completed.stderr}')
    return completed.stdout


def commit(checkout, message, environment, log, *paths):
    command = ['fossil', 'commit', '--nosync', '--no-prompt', '--no-warnings',
               '--nosign', '--user-override', 'scripture-verifier', '-m', message]
    command.extend(paths)
    return run(command, cwd=checkout, environment=environment, log=log)


def changed_paths(output):
    return [line.split(None, 1) for line in output.splitlines() if line.strip()]


def storage_verification(root, environment, log):
    hub = root / 'hub.fossil'
    seed = root / 'seed'
    clone_a_repo = root / 'clone-a.fossil'
    clone_b_repo = root / 'clone-b.fossil'
    checkout_a = root / 'checkout-a'
    checkout_b = root / 'checkout-b'
    run(['fossil', 'init', str(hub)], cwd=root, environment=environment, log=log)
    run(['fossil', 'open', str(hub), '--workdir', str(seed), '--nosync'],
        cwd=root, environment=environment, log=log)
    seed_assets = seed / 'alpine/assets/scripture'
    seed_assets.mkdir(parents=True)
    shutil.copyfile(ASSETS / 'reflections.json', seed_assets / 'reflections.json')
    legacy_bytes = (ASSETS / 'reflections.json').read_bytes()
    assert (seed_assets / 'reflections.json').read_bytes() == legacy_bytes
    run(['fossil', 'add', 'alpine/assets/scripture/reflections.json'], cwd=seed,
        environment=environment, log=log)
    commit(seed, 'seed 33 preserved reflections', environment, log,
           'alpine/assets/scripture/reflections.json')
    initial_entry = fixture('study-11111111111111111111111111111111',
                            'study-note', 'Initial saved fixture')
    initial_path = study.save_entry(seed_assets, initial_entry,
                                    root / 'seed-cache.sqlite3', track=True)
    initial_relative = initial_path.relative_to(seed).as_posix()
    staged = run(['fossil', 'changes', '--no-merge', '--classify'], cwd=seed,
                 environment=environment, log=log)
    staged_lines = changed_paths(staged)
    assert staged_lines == [['ADDED', initial_relative]], staged_lines
    commit(seed, 'add initial Scripture study fixture', environment, log,
           initial_relative)
    seed_catalog = study.load_entries(seed_assets, root / 'seed-cache.sqlite3')
    assert len(seed_catalog) == 34
    assert sum(item.get('kind') == 'reflection' for item in seed_catalog) == 33

    for repository, checkout in ((clone_a_repo, checkout_a),
                                 (clone_b_repo, checkout_b)):
        run(['fossil', 'clone', '--no-open', '--once', str(hub), str(repository)],
            cwd=root, environment=environment, log=log)
        run(['fossil', 'open', str(repository), '--workdir', str(checkout), '--nosync'],
            cwd=root, environment=environment, log=log)
    rebuilt_database = root / 'clone-b-fresh.sqlite3'
    assert not rebuilt_database.exists()
    clone_catalog = study.load_entries(checkout_b / 'alpine/assets/scripture',
                                       rebuilt_database)
    assert rebuilt_database.is_file()
    with sqlite3.connect(rebuilt_database) as database:
        assert database.execute('PRAGMA application_id').fetchone()[0] == study.APPLICATION_ID
    assert clone_catalog == seed_catalog

    entry_a = fixture('study-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
                      'observation', 'Clone A fixture')
    entry_b = fixture('study-bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb',
                      'inspiration', 'Clone B fixture')
    path_a = study.save_entry(checkout_a / 'alpine/assets/scripture', entry_a,
                              root / 'clone-a.sqlite3', track=True)
    relative_a = path_a.relative_to(checkout_a).as_posix()
    staged_a = run(['fossil', 'changes', '--no-merge', '--classify'], cwd=checkout_a,
                   environment=environment, log=log)
    assert changed_paths(staged_a) == [['ADDED', relative_a]]
    commit(checkout_a, 'add clone A fixture', environment, log, relative_a)
    current_info = run(['fossil', 'info', 'current'], cwd=checkout_a,
                       environment=environment, log=log)
    leaf_a = next(line.split()[1] for line in current_info.splitlines()
                  if line.startswith('hash:'))
    run(['fossil', 'push', '--once', str(hub)], cwd=checkout_a,
        environment=environment, log=log)

    path_b = study.save_entry(checkout_b / 'alpine/assets/scripture', entry_b,
                              root / 'clone-b.sqlite3', track=True)
    relative_b = path_b.relative_to(checkout_b).as_posix()
    staged_b = run(['fossil', 'changes', '--no-merge', '--classify'], cwd=checkout_b,
                   environment=environment, log=log)
    assert changed_paths(staged_b) == [['ADDED', relative_b]]
    commit(checkout_b, 'add clone B fixture', environment, log, relative_b)
    run(['fossil', 'pull', '--once', str(hub)], cwd=checkout_b,
        environment=environment, log=log)
    run(['fossil', 'merge', '--nosync', leaf_a], cwd=checkout_b,
        environment=environment, log=log)
    merge_changes = run(['fossil', 'changes', '--no-merge', '--classify'], cwd=checkout_b,
                        environment=environment, log=log)
    assert relative_a in merge_changes
    commit(checkout_b, 'merge independent Scripture fixtures', environment, log)
    run(['fossil', 'push', '--once', str(hub)], cwd=checkout_b,
        environment=environment, log=log)
    run(['fossil', 'pull', '--once', str(hub)], cwd=checkout_a,
        environment=environment, log=log)
    run(['fossil', 'update', '--nosync'], cwd=checkout_a,
        environment=environment, log=log)

    expected_ids = {initial_entry['id'], entry_a['id'], entry_b['id']}
    catalogs = {}
    for name, checkout in (('clone_a', checkout_a), ('clone_b', checkout_b)):
        database = root / f'{name}-after-merge.sqlite3'
        found = study.load_entries(checkout / 'alpine/assets/scripture', database)
        ids = {item['id'] for item in found}
        assert expected_ids <= ids
        assert len(found) == 36
        assert sum(item.get('kind') == 'reflection' for item in found) == 33
        catalogs[name] = {'count': len(found), 'ids': sorted(ids)}
    assert catalogs['clone_a']['ids'] == catalogs['clone_b']['ids']
    assert (checkout_a / relative_b).is_file() and (checkout_b / relative_a).is_file()
    return {
        'legacy_reflections_byte_preserved': True,
        'legacy_reflections': 33,
        'initial_save_staged_exact_path': initial_relative,
        'clone_fresh_sqlite_rebuild_equal': True,
        'fresh_rebuild_entries': len(clone_catalog),
        'fresh_sqlite_application_id': study.APPLICATION_ID,
        'local_transport': str(hub),
        'remote_network_used': False,
        'clone_a_staged_exact_path': relative_a,
        'clone_b_staged_exact_path': relative_b,
        'push_pull_merge_performed': True,
        'merged_entries_each_checkout': 36,
        'independent_ids_retained': sorted(expected_ids - {initial_entry['id']}),
        'catalog_ids_equal_after_merge': True,
        'all_commits_nosync': True,
        'private_fossil_home': str(environment['HOME']),
    }


def wait_for_wayland(runtime):
    for _ in range(100):
        displays = [path for path in runtime.glob('wayland-*') if path.is_socket()]
        sockets = list(runtime.glob('sway-ipc*.sock'))
        if displays and sockets:
            return displays[0].name, str(sockets[0])
        time.sleep(.1)
    raise RuntimeError('private Sway did not expose Wayland and IPC sockets')


def wait_for_fuzzel(parent_pid):
    for _ in range(150):
        pending = [str(parent_pid)]
        seen = set()
        while pending:
            pid = pending.pop()
            if pid in seen:
                continue
            seen.add(pid)
            try:
                children = Path(f'/proc/{pid}/task/{pid}/children').read_text().split()
            except OSError:
                continue
            for child in children:
                try:
                    if Path(f'/proc/{child}/comm').read_text().strip() == 'fuzzel':
                        return int(child)
                except OSError:
                    pass
                pending.append(child)
        time.sleep(.1)
    raise RuntimeError('real Fuzzel process did not appear')


def png_pixels(path):
    """Decode a non-interlaced 8-bit RGB/RGBA PNG into unfiltered scanlines."""
    content = Path(path).read_bytes()
    assert content[:8] == b'\x89PNG\r\n\x1a\n'
    offset = 8
    chunks = []
    header = None
    while offset < len(content):
        length = struct.unpack('>I', content[offset:offset + 4])[0]
        kind = content[offset + 4:offset + 8]
        data = content[offset + 8:offset + 8 + length]
        if kind == b'IHDR':
            header = struct.unpack('>IIBBBBB', data)
        if kind == b'IDAT':
            chunks.append(data)
        offset += 12 + length
    width, height, depth, color_type, compression, filtering, interlace = header
    assert (depth, compression, filtering, interlace) == (8, 0, 0, 0)
    channels = {2: 3, 6: 4}[color_type]
    packed = zlib.decompress(b''.join(chunks))
    stride = width * channels
    rows = []
    previous = bytearray(stride)

    def paeth(left, above, upper_left):
        estimate = left + above - upper_left
        distances = (abs(estimate - left), abs(estimate - above),
                     abs(estimate - upper_left))
        return (left, above, upper_left)[distances.index(min(distances))]

    cursor = 0
    for _ in range(height):
        method = packed[cursor]
        encoded = packed[cursor + 1:cursor + 1 + stride]
        cursor += stride + 1
        row = bytearray(stride)
        for index, byte in enumerate(encoded):
            left = row[index - channels] if index >= channels else 0
            above = previous[index]
            upper_left = previous[index - channels] if index >= channels else 0
            predictor = {
                0: 0,
                1: left,
                2: above,
                3: (left + above) // 2,
                4: paeth(left, above, upper_left),
            }[method]
            row[index] = (byte + predictor) & 0xff
        rows.append(bytes(row))
        previous = row
    assert cursor == len(packed)
    return width, height, channels, rows


def changed_pixels(image, baseline, rectangle):
    """Count decompressed RGB pixels changed inside x/y/width/height."""
    width, height, channels, rows = png_pixels(image)
    base_width, base_height, base_channels, base_rows = png_pixels(baseline)
    assert (width, height, channels) == (base_width, base_height, base_channels)
    x, y, region_width, region_height = rectangle
    assert x + region_width <= width and y + region_height <= height
    changed = 0
    for row_index in range(y, y + region_height):
        row = rows[row_index]
        base_row = base_rows[row_index]
        for column in range(x, x + region_width):
            start = column * channels
            if row[start:start + 3] != base_row[start:start + 3]:
                changed += 1
    return changed


def bright_pixels(image, rectangle, threshold=80):
    """Count visibly light RGB pixels in a dark-background rectangle."""
    width, height, channels, rows = png_pixels(image)
    x, y, region_width, region_height = rectangle
    assert x + region_width <= width and y + region_height <= height
    count = 0
    for row_index in range(y, y + region_height):
        row = rows[row_index]
        for column in range(x, x + region_width):
            start = column * channels
            if max(row[start:start + 3]) > threshold:
                count += 1
    return count


def terminate_pid(pid):
    try:
        os.kill(int(pid), 15)
    except (OSError, ValueError):
        return
    for _ in range(20):
        if not Path(f'/proc/{pid}').exists():
            return
        time.sleep(.05)
    try:
        os.kill(int(pid), 9)
    except OSError:
        pass


def native_verification(root, log):
    home = root / 'native-home'
    runtime = root / 'native-run'
    home.mkdir()
    runtime.mkdir(mode=0o700)
    environment = dict(os.environ, HOME=str(home), XDG_RUNTIME_DIR=str(runtime),
                       XDG_CONFIG_HOME=str(home / '.config'),
                       XDG_DATA_HOME=str(home / '.local/share'),
                       WLR_BACKENDS='headless', WLR_RENDERER='pixman',
                       WLR_LIBINPUT_NO_DEVICES='1')
    for name in ('SWAYSOCK', 'WAYLAND_DISPLAY', 'DISPLAY'):
        environment.pop(name, None)
    config = root / 'sway.conf'
    config.write_text('output HEADLESS-1 mode 1440x900\n'
                      'output * bg #282828 solid_color\n'
                      'seat seat0 fallback true\n')
    children = []
    sway = subprocess.Popen(['sway', '-c', str(config)], env=environment,
                            stdout=log, stderr=log)
    children.append(sway)
    replacement_scripture = None
    try:
        display, socket = wait_for_wayland(runtime)
        environment.update(WAYLAND_DISPLAY=display, SWAYSOCK=socket)
        baseline = root / 'headless-background.png'
        card_geometry = '20,20 440x240'
        subprocess.run(['grim', '-g', card_geometry, str(baseline)], env=environment,
                       check=True, timeout=10)
        daily = subprocess.run([str(HELPER), 'daily'], env=environment,
                               capture_output=True, text=True, timeout=30)
        log.write(daily.stdout + daily.stderr)
        assert daily.returncode == 0
        selection_path = home / '.local/state/mbp-intel/scripture/selection.json'
        daily_selection = json.loads(selection_path.read_text())
        assert daily_selection['kind'] == 'reflection'
        legacy = json.loads((ASSETS / 'reflections.json').read_text())['reflections']
        assert len(legacy) == 33
        assert daily_selection['id'] in {item['id'] for item in legacy}

        state = home / '.local/state/mbp-intel/conky'
        state.mkdir(parents=True)
        scripture_config = state / 'scripture.conf'
        scripture_config.write_text(
            "conky.config={out_to_wayland=true,out_to_x=false,own_window=true,"
            "own_window_type='desktop',own_window_colour='#00000000',"
            "own_window_class='mbp-intel-conky',own_window_title='mbp-intel-conky-scripture',"
            "alignment='top_left',gap_x=30,gap_y=30,minimum_width=420,"
            "maximum_width=420,minimum_height=204,update_interval=60,"
            "font='JetBrainsMono Nerd Font:size=9',use_xft=true,default_color='#ebdbb2',"
            "color1='#d8a657',color2='#a89984',text_buffer_size=4096,"
            "double_buffer=true,no_buffers=true}\n"
            f"conky.text=[[${{color1}}SCRIPTURE${{color2}} ${{hr 1}}\n"
            f"${{execpi 60 \"{HELPER} panel --width 52\"}}]]\n")
        witness_config = state / 'witness.conf'
        witness_config.write_text(
            "conky.config={out_to_wayland=true,out_to_x=false,own_window=true,"
            "own_window_type='desktop',own_window_colour='#00000000',"
            "alignment='bottom_right',gap_x=30,gap_y=30,minimum_width=300,"
            "minimum_height=80,update_interval=60,font='monospace:size=14',"
            "use_xft=true,default_color='#a89984'}\n"
            "conky.text=[[WITNESS CONTROL]]\n")
        scripture_process = subprocess.Popen(['conky', '-c', str(scripture_config)],
                                             env=environment, stdout=log, stderr=log)
        children.append(scripture_process)
        rendered = False
        scripture_changed_pixels = 0
        scripture_bright_pixels = 0
        for _ in range(20):
            time.sleep(.5)
            subprocess.run(['grim', '-g', card_geometry,
                            str(OUTPUT / 'restored-card.png')], env=environment,
                           check=True, timeout=10)
            scripture_changed_pixels = changed_pixels(
                OUTPUT / 'restored-card.png', baseline, (0, 0, 440, 240))
            scripture_bright_pixels = bright_pixels(
                OUTPUT / 'restored-card.png', (0, 0, 440, 240))
            if scripture_changed_pixels > 100 and scripture_bright_pixels > 100:
                rendered = True
                break
        assert rendered, 'Scripture Conky did not render visible pixels'
        witness_process = subprocess.Popen(['conky', '-c', str(witness_config)],
                                           env=environment, stdout=log, stderr=log)
        children.append(witness_process)
        (state / 'pids.json').write_text(json.dumps({
            'scripture': scripture_process.pid,
            'witness': witness_process.pid,
        }))
        time.sleep(1)

        finder = subprocess.Popen([str(HELPER), 'reflections'], env=environment,
                                  stdout=log, stderr=log)
        children.append(finder)
        fuzzel_pid = wait_for_fuzzel(finder.pid)
        time.sleep(1)
        subprocess.run(['grim', str(OUTPUT / 'reflections-picker.png')], env=environment,
                       check=True, timeout=10)
        chosen = legacy[0]
        subprocess.run(['wtype', '-d', '10', chosen['title'], '-k', 'Return'],
                       env=environment, check=True, timeout=10)
        finder.wait(timeout=30)
        assert finder.returncode == 0
        selected = json.loads(selection_path.read_text())
        assert selected['id'] == chosen['id'], selected
        assert selected['kind'] == 'reflection'
        for _ in range(60):
            updated_pids = json.loads((state / 'pids.json').read_text())
            replacement_scripture = int(updated_pids['scripture'])
            if replacement_scripture != scripture_process.pid:
                break
            time.sleep(.1)
        assert replacement_scripture != scripture_process.pid
        assert int(updated_pids['witness']) == witness_process.pid
        assert Path(f'/proc/{replacement_scripture}').exists()
        assert Path(f'/proc/{witness_process.pid}').exists()
        return {
            'isolated_headless_sway': True,
            'private_home': str(home),
            'legacy_daily_restored': daily_selection['id'],
            'restored_card_screenshot': 'restored-card.png',
            'restored_card_crop': card_geometry,
            'actual_conky_card': True,
            'card_visible_pixels_verified': True,
            'scripture_rectangle_changed_pixels': scripture_changed_pixels,
            'scripture_rectangle_bright_pixels': scripture_bright_pixels,
            'actual_fuzzel_picker': True,
            'actual_wtype_enter': True,
            'picker_preserved_entries': len(legacy),
            'picker_screenshot': 'reflections-picker.png',
            'entered_selection': selected['id'],
            'scripture_pid_replaced': True,
            'witness_control_pid_unchanged': True,
            'only_scripture_refreshed': True,
            'fuzzel_pid_observed': fuzzel_pid,
        }
    finally:
        if replacement_scripture:
            terminate_pid(replacement_scripture)
        try:
            pids = json.loads((home / '.local/state/mbp-intel/conky/pids.json').read_text())
        except (OSError, ValueError):
            pids = {}
        for pid in pids.values():
            terminate_pid(pid)
        for process in reversed(children):
            if process.poll() is None:
                process.terminate()
        for process in reversed(children):
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


def callback_verification(root):
    """Exercise the GTK callback through its actual spawned Python process."""
    loader = importlib.machinery.SourceFileLoader('scripture_bar_verification', str(BAR))
    bar_module = loader.load_module()
    record = root / 'callback-action'
    finder = root / 'record-finder.py'
    finder.write_text(
        'from pathlib import Path\n'
        'import sys\n'
        f'Path({str(record)!r}).write_text(sys.argv[1])\n')
    bar = bar_module.SearchBar.__new__(bar_module.SearchBar)
    original_finder = bar_module.FINDER
    bar_module.FINDER = finder
    observed = {}
    try:
        for name, event in (('left', SimpleNamespace(button=1)),
                            ('right', SimpleNamespace(button=3)), ('signal', None)):
            record.unlink(missing_ok=True)
            bar.open_finder(None, event)
            for _ in range(100):
                if record.is_file():
                    break
                time.sleep(.02)
            observed[name] = record.read_text()
    finally:
        bar_module.FINDER = original_finder
    assert observed == {'left': 'find', 'right': 'reflections', 'signal': 'find'}
    return {
        'callback_subprocess_observed': observed,
        'right_click_routes_reflections': True,
        'left_click_routes_find': True,
        'signal_routes_find': True,
        'native_physical_mouse_simulated': False,
    }


def live_activation_observation():
    """Record the already-authorized live activation without changing it."""
    live_database = Path('/home/jack/.local/share/mbp-intel/scripture/study.sqlite3')
    archived_database = Path(
        '/home/jack/.local/share/mbp-intel/scripture/'
        'study-before-application-id-1788838969347774079.sqlite3')
    selection_backup = Path(
        '/home/jack/.local/state/mbp-intel/scripture/'
        'selection-before-study-1788838996144792109.json')
    preview_journal = Path(
        '/tmp/mbp-intel-scripture-study-preview/.local/state/mbp-intel/backups/'
        '1788838969793306374')
    live_journal = Path(
        '/home/jack/.local/state/mbp-intel/backups/1788838970027102079')
    selection = json.loads(Path(
        '/home/jack/.local/state/mbp-intel/scripture/selection.json').read_text())
    selection_identity = {key: selection.get(key) for key in
                          ('kind', 'id', 'reference', 'chosen_utc')}
    with sqlite3.connect(live_database) as database:
        application_id = database.execute('PRAGMA application_id').fetchone()[0]
        row_count = database.execute('SELECT count(*) FROM entries').fetchone()[0]
    with sqlite3.connect(archived_database) as database:
        archived_application_id = database.execute('PRAGMA application_id').fetchone()[0]
        archived_row_count = database.execute('SELECT count(*) FROM entries').fetchone()[0]
    bar_pid = int(Path('/home/jack/.local/state/mbp-intel/scripture/bar.pid').read_text())
    bar_command = Path(f'/proc/{bar_pid}/cmdline').read_bytes().rstrip(b'\0').replace(
        b'\0', b' ').decode()
    assert application_id == study.APPLICATION_ID and row_count == 33
    assert archived_application_id == 0 and archived_row_count == 33
    activated_selection = {'kind': 'reflection', 'id': 'isaiah-call',
                           'reference': 'Isaiah 6:5',
                           'chosen_utc': '2026-09-08T03:43:16Z'}
    assert selection_backup.is_file()
    assert preview_journal.is_dir() and live_journal.is_dir()
    assert bar_command.endswith('/home/jack/.local/bin/mbp-intel-scripture-bar')
    return {
        'scope': 'read-only observation of root live activation; screenshots are headless only',
        'preview_deployment_journal': str(preview_journal),
        'live_deployment_journal': str(live_journal),
        'archived_application_id_zero_cache': str(archived_database),
        'archived_cache_entries': archived_row_count,
        'rebuilt_application_id': application_id,
        'rebuilt_cache_entries': row_count,
        'prior_selection_backup': str(selection_backup),
        'activated_daily_selection': activated_selection,
        'current_selection_observed': selection_identity,
        'same_daily_identity_current': all(
            selection_identity[key] == activated_selection[key]
            for key in ('kind', 'id', 'reference')),
        'verified_owned_bar_old_pid': 10394,
        'verified_owned_bar_new_pid': bar_pid,
        'verified_owned_bar_command': bar_command,
        'only_bar_restarted_by_root_activation': True,
    }


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for name in ('summary.json', 'fossil.log', 'native.log', 'restored-card.png',
                 'reflections-picker.png'):
        (OUTPUT / name).unlink(missing_ok=True)
    summary = {'schema': 1, 'status': 'running'}
    started = time.monotonic()
    try:
        with tempfile.TemporaryDirectory(prefix='scripture-study-integration-') as directory:
            root = Path(directory)
            private_home = root / 'fossil-home'
            private_home.mkdir()
            environment = fossil_environment(private_home)
            with (OUTPUT / 'fossil.log').open('w') as fossil_log:
                summary['storage'] = storage_verification(root, environment, fossil_log)
            with (OUTPUT / 'native.log').open('w') as native_log:
                summary['native'] = native_verification(root, native_log)
            summary['search_bar_dispatch'] = callback_verification(root)
            summary['live_activation'] = live_activation_observation()
        summary['status'] = 'passed'
    except BaseException as error:
        summary['status'] = 'failed'
        summary['error'] = f'{type(error).__name__}: {error}'
        raise
    finally:
        summary['elapsed_seconds'] = round(time.monotonic() - started, 3)
        summary['temporary_repositories_removed'] = True
        (OUTPUT / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
        print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
