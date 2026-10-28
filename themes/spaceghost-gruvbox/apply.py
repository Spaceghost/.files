#!/usr/bin/env python3
"""Apply the saved Spaceghost look with per-file backups and an undo manifest."""
import argparse
import datetime
import json
import os
from pathlib import Path
import shutil
import zipfile

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--home', type=Path, default=Path.home(), help='target home (also useful for previewing in a temporary directory)')
parser.add_argument('--desktop', action='store_true', help='install the portable Sway session as well as appearance settings')
parser.add_argument('--restore', type=Path, help='undo an application using its backup directory')
args = parser.parse_args()
if args.restore:
    backup = args.restore.resolve()
    manifest = json.loads((backup/'manifest.json').read_text())
    target = Path(manifest['home'])
    for rel, existed in reversed(manifest['files']):
        dest = target/rel
        if dest.exists() or dest.is_symlink():
            dest.unlink()
        if existed:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(backup/'files'/rel, dest, follow_symlinks=False)
    print('Restored', target)
    raise SystemExit
root = Path(__file__).resolve().parent
target = args.home.expanduser().resolve()
backup = target/'.local/state/spaceghost-look-backups'/datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')
backup.mkdir(parents=True)
manifest = {'home': str(target), 'files': []}

def install(rel, source=None, content=None, binary=None):
    dest = target/rel
    existed = dest.exists() or dest.is_symlink()
    if existed:
        saved = backup/'files'/rel
        saved.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(dest, saved, follow_symlinks=False)
    manifest['files'].append((rel, existed))
    (backup/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    dest.parent.mkdir(parents=True, exist_ok=True)
    if existed:
        dest.unlink()
    if binary is not None:
        dest.write_bytes(binary)
    elif source:
        shutil.copy2(source, dest)
    else:
        dest.write_text(content)

for source in sorted((root/'home').rglob('*')):
    if source.is_file():
        rel = str(source.relative_to(root/'home'))
        if rel == '.config/waybar/style.css':
            content = source.read_text().replace('url("ghost.png")', 'url("'+str(target/'.config/waybar/ghost.png')+'")')
            install(rel, content=content)
        else:
            install(rel, source=source)
with zipfile.ZipFile(root/'gruvbox-dark.zip') as archive:
    for name in archive.namelist():
        path = Path(name)
        if path.is_absolute() or '..' in path.parts:
            raise ValueError('Unsafe theme path')
        install(name, binary=archive.read(name))
sway = target/'.config/sway/config'
if args.desktop or not sway.exists():
    install('.config/sway/config', source=root/'sway.conf')
else:
    content = sway.read_text()
    if 'include ~/.config/sway/theme.conf' not in content:
        install('.config/sway/config', content=content.rstrip()+'\ninclude ~/.config/sway/theme.conf\n')
# Remove the retired timer from existing Sharkdeck shortcuts without replacing local settings.
local = target/'.config/sway/local.d/panel.conf'
if local.exists() and 'spaceghost-battery' in local.read_text():
    install('.config/sway/local.d/panel.conf', content=''.join(line for line in local.read_text().splitlines(keepends=True) if 'spaceghost-battery' not in line))
print('Applied Spaceghost Gruvbox to', target)
print('Backup:', backup)
print('Undo: python3', root/'apply.py', '--restore', backup)
print('Reload Sway and restart Waybar to display changes; reopen terminals and GTK applications.')
