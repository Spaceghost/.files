"""Fold the live oldbook-named fork into the renamed line with the validated identity rules.

Usage, inside a private checkout of the renamed line (OURS):

    fossil merge THEIRS
    python3 alpine/tools/fold_live_fork.py --pivot PIVOT --ours OURS --theirs THEIRS

Every path the live side touched since the pivot is recomputed as a three-way
merge whose pivot and live sides are rewritten with the same identity rules the
rename applied, so only real changes remain to merge. Evidence paths are copied
verbatim, binary files take the live version, and live-added files under old
names are moved to their renamed paths. Remaining conflicts are marked in the
files and listed in the report for resolution by hand.
"""
import argparse, json, subprocess, sys, tempfile, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from identity_rewrite import rewrite, rename_path
ROOT = Path.cwd()

def cat(version, path):
    for attempt in range(6):
        result = subprocess.run(['fossil', 'cat', '-r', version, path], capture_output=True)
        if result.returncode == 0:
            return result.stdout
        if b'cannot resolve name' not in result.stderr and attempt >= 2:
            break
        time.sleep(0.2 * (attempt + 1))
    return None

def text_or_none(data):
    try:
        return data.decode('utf-8')
    except UnicodeDecodeError:
        return None

def merge3(ours, base, theirs, label):
    with tempfile.TemporaryDirectory() as directory:
        paths = []
        for name, content in (('ours', ours), ('base', base), ('theirs', theirs)):
            path = Path(directory) / name
            path.write_text(content)
            paths.append(str(path))
        result = subprocess.run(['git', 'merge-file', '-p', '-L', 'renamed line', '-L', 'pivot', '-L', 'live fork',
                                 *paths], capture_output=True, text=True)
        if result.returncode < 0:
            raise RuntimeError(f'merge-file failed for {label}: {result.stderr}')
        return result.stdout, result.returncode

parser = argparse.ArgumentParser(description=__doc__.split('\n', 1)[0])
parser.add_argument('--pivot', required=True, help='common ancestor of both lines')
parser.add_argument('--ours', required=True, help='renamed line the checkout is on')
parser.add_argument('--theirs', required=True, help='live fork just merged with fossil merge')
parser.add_argument('--report', type=Path, default=Path('fold-live-fork-report.json'))
arguments = parser.parse_args()
PIVOT, OURS, THEIRS = arguments.pivot, arguments.ours, arguments.theirs
entries = []
for line in subprocess.run(['fossil', 'diff', '--from', PIVOT, '--to', THEIRS, '--brief'], capture_output=True, text=True, check=True).stdout.splitlines():
    kind, path = line.split(None, 1)
    entries.append((kind, path))
report = {'changed': [], 'added': [], 'moved': [], 'deleted': [], 'binary': [], 'conflicts': {}, 'skipped': []}
for kind, path in entries:
    target = rename_path(path)
    if kind == 'DELETED':
        # fossil merge already removed or renamed it; a rename's new path arrives as ADDED.
        report['deleted'].append(target)
        continue
    live = cat(THEIRS, path)
    if live is None:
        report['skipped'].append((kind, path, 'unreadable live content'))
        continue
    live_text = text_or_none(live)
    if kind == 'ADDED':
        if target != path:
            moved = subprocess.run(['fossil', 'mv', '--hard', path, target], capture_output=True, text=True)
            if moved.returncode:
                subprocess.run(['fossil', 'rm', '--hard', path], check=True, capture_output=True)
                (ROOT / target).parent.mkdir(parents=True, exist_ok=True)
                (ROOT / target).write_bytes(live)
                subprocess.run(['fossil', 'add', target], check=True, capture_output=True)
            report['moved'].append((path, target, 'mv' if not moved.returncode else 'rm+add'))
        out = ROOT / target
        if live_text is None:
            out.write_bytes(live)
            report['binary'].append(target)
        else:
            out.write_text(rewrite(path, live_text))
        report['added'].append(target)
    elif kind == 'CHANGED':
        ours = cat(OURS, target)
        pivot = cat(PIVOT, path)
        if ours is None or pivot is None:
            report['skipped'].append((kind, path, f'missing ours/pivot for {target}'))
            continue
        ours_text, pivot_text = text_or_none(ours), text_or_none(pivot)
        out = ROOT / target
        if live_text is None or ours_text is None or pivot_text is None:
            out.write_bytes(live)
            report['binary'].append(target)
            continue
        merged, conflicts = merge3(ours_text, rewrite(path, pivot_text), rewrite(path, live_text), target)
        out.write_text(merged)
        report['changed'].append(target)
        if conflicts:
            report['conflicts'][target] = conflicts
    else:
        report['skipped'].append((kind, path, 'unexpected kind'))
# Two slips of the original rename: a renamed service still wanted under its old name, and an
# error message that took the Python identifier form of a helper name.
SLIPS = [('bazzite/desktop/.config/systemd/user/mbp-intel-session.target',
          'Wants=oldbook-desktop-settings.service', 'Wants=mbp-intel-desktop-settings.service'),
         ('bazzite/bin/mbp-intel-bazzite-profile', 'from mbp_intel-wallpaper', 'from mbp-intel-wallpaper')]
report['slips'] = []
for path, old, new in SLIPS:
    file = ROOT / path
    content = file.read_text()
    if old in content:
        file.write_text(content.replace(old, new))
        report['slips'].append(path)
arguments.report.write_text(json.dumps(report, indent=1) + '\n')
print('changed', len(report['changed']), 'added', len(report['added']), 'moved', len(report['moved']),
      'deleted', len(report['deleted']), 'binary', len(report['binary']), 'skipped', report['skipped'])
print('conflicts:', report['conflicts'])
