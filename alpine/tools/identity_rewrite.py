"""The oldbook -> mbp-intel identity rewrite, reconstructed from check-in 468f8ebd2a.

`python3 alpine/tools/identity_rewrite.py --validate` replays the rules over
every file that check-in rewrote or renamed and reports the differences. The
expected remainder is four items: the identity row the rename added to
FEATURES.md, the PROGRESS entry it appended, and two slips it made (a Bazzite
service still wanted under its old name and an error message that took the
Python identifier form), which fold_live_fork.py corrects.
"""
import io, re, tokenize

EVIDENCE = ('alpine/verification/', 'alpine/archive/', 'alpine/packages/locks/', 'alpine/packages/world',
            'alpine/packages/current-lock', 'alpine/packages/1password/firewall/rules/')
KEEP = '\x00KEEP%d\x00'
RESTORE = ['alpine-oldbook', 'oldbook-desktop']
PROTECTED = [r'alpine-oldbook', r'oldbook-desktop(?![\w-])']   # branch name; superseded package name
STRING_RULES = [
    (r'conky_oldbook_', 'conky_mbp_intel_'),
    (r'oldbook%-', 'mbp%-intel%-'),
    (r'OLDBOOK', 'MBP_INTEL'),
    (r'Oldbook-Gruvbox', 'MBP-Intel-Gruvbox'),
    (r'oldbook_workspace_', 'mbp_intel_workspace_'),
    (r'com\.oldbook\.scripture\.history', 'com.mbp_intel.scripture.history'),   # GTK application id
    (r'com\.oldbook\.', 'com.mbp-intel.'),
    (r'\.local/lib/oldbook', '.local/lib/mbp_intel'),
    (r'lib/oldbook(?=/|\b)', 'lib/mbp_intel'),
    (r'\boldbook\.([a-z_]+) import', r'mbp_intel.\1 import'),
    (r'from oldbook import', 'from mbp_intel import'),
    (r'import oldbook\b', 'import mbp_intel'),
    (r'oldbook_', 'mbp_intel_'),
    (r'Oldbook', 'MBP Intel'),
    (r'oldbook', 'mbp-intel'),
]

def _protect(text):
    for index, pattern in enumerate(PROTECTED):
        text = re.sub(pattern, KEEP % index, text)
    return text

def _restore(text):
    for index, pattern in enumerate(PROTECTED):
        text = text.replace(KEEP % index, RESTORE[index])
    return text

def rewrite_text(text):
    text = _protect(text)
    for pattern, replacement in STRING_RULES:
        text = re.sub(pattern, replacement, text)
    return _restore(text)

def is_python(path, text):
    return path.endswith('.py') or text.startswith('#!') and 'python' in text.split('\n', 1)[0]

def rewrite_python(text):
    """Bare `oldbook` names become the package identifier; strings and comments follow the path rules."""
    IDENT = '\x00IDENT\x00'
    lines = text.splitlines(keepends=True)
    try:
        names = [(t.start[0], t.start[1]) for t in tokenize.generate_tokens(io.StringIO(text).readline)
                 if t.type == tokenize.NAME and t.string == 'oldbook']
    except (tokenize.TokenError, SyntaxError):
        return rewrite_text(text)
    for row, col in sorted(names, reverse=True):
        line = lines[row - 1]
        assert line[col:col + 7] == 'oldbook', (row, col, line)
        lines[row - 1] = line[:col] + IDENT + line[col + 7:]
    return rewrite_text(''.join(lines)).replace(IDENT, 'mbp_intel')

def rewrite(path, text):
    if any(path.startswith(prefix) for prefix in EVIDENCE):
        return text
    return rewrite_python(text) if is_python(path, text) else rewrite_text(text)

def rename_path(path):
    if any(path.startswith(prefix) for prefix in EVIDENCE):
        return path
    return rewrite_text(path)


def _validate(pivot='1a46ed2933', rename='468f8ebd2a'):
    """Replay the rules over the rename check-in from inside a checkout of this repository."""
    import subprocess, time
    def manifest(version):
        files = {}
        for line in subprocess.run(['fossil', 'artifact', version], capture_output=True, text=True, check=True).stdout.splitlines():
            parts = line.split()
            if parts and parts[0] == 'F':
                files[parts[1]] = (parts[2], parts[4] if len(parts) > 4 else None)
        return files
    def cat(version, path):
        for attempt in range(6):
            result = subprocess.run(['fossil', 'cat', '-r', version, path], capture_output=True)
            if result.returncode == 0:
                return result.stdout
            time.sleep(0.2 * (attempt + 1))
        return None
    old, new = manifest(pivot), manifest(rename)
    renames = {previous: path for path, (_, previous) in new.items() if previous}
    bad_paths = [(path, target) for path, target in renames.items() if rename_path(path) != target]
    mismatches = []
    for path, (hash_, _) in old.items():
        target = renames.get(path, path)
        if target not in new or new[target][0] == hash_:
            continue
        before, after = cat(pivot, path), cat(rename, target)
        if before is None or after is None:
            mismatches.append((path, target, 'unreadable'))
            continue
        try:
            candidate = rewrite(path, before.decode()).encode()
        except UnicodeDecodeError:
            continue
        if candidate != after:
            mismatches.append((path, target, 'differs'))
    return bad_paths, mismatches


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__.split('\n', 1)[0])
    parser.add_argument('--validate', action='store_true', help='replay the rules over the rename check-in')
    parser.add_argument('paths', nargs='*', help='paths to print in renamed form')
    arguments = parser.parse_args()
    if arguments.validate:
        bad_paths, mismatches = _validate()
        print('path mismatches:', len(bad_paths), 'content mismatches:', len(mismatches))
        for item in bad_paths + mismatches:
            print('  ', *item)
    for path in arguments.paths:
        print(rename_path(path))
