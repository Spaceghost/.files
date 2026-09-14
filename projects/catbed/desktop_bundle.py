"""Collect the current Wayland guard and its local Python import closure.

Preserve the existing relative layout while removing the installed checkout
dependency. Canonical sources stay in one place until runtime extraction is
complete; both distribution formats carry an identical snapshot.
"""

import ast
from pathlib import Path
import shutil


def bundle_desktop(project, destination):
    project = Path(project)
    destination = Path(destination)
    embedded = project / "src/catbed/runtime"
    if embedded.is_dir():
        shutil.copytree(embedded, destination, dirs_exist_ok=True)
        return

    repository = project.parents[1]
    local = repository / "alpine/desktop/.local"
    library = local / "lib/oldbook"
    pending = [local / "bin/oldbook-watch"]
    included = set()
    while pending:
        source = pending.pop()
        if source in included:
            continue
        included.add(source)
        content = source.read_text(encoding="utf-8")
        target = destination / source.relative_to(repository)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        for node in ast.walk(ast.parse(content, filename=str(source))):
            names = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for name in names:
                dependency = library / (name.split(".", 1)[0] + ".py")
                if dependency.is_file() and dependency not in included:
                    pending.append(dependency)

    # Palette readers retain their source-relative lookup. Theme JSON is
    # lightweight; wallpapers, cursor packs, and unrelated desktop executables
    # are deliberately not copied into the guard distribution.
    for source in (repository / "alpine/themes").rglob("*.json"):
        target = destination / source.relative_to(repository)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
