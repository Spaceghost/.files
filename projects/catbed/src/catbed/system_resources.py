"""Export packaged Linux system files without installing or activating them."""

from importlib.resources import files
import json
from pathlib import Path
import shutil


def export(destination):
    source = files("catbed").joinpath("resources", "linux")
    try:
        manifest_bytes = source.joinpath("manifest.json").read_bytes()
        manifest = json.loads(manifest_bytes)
        entries = manifest["files"]
        payloads = []
        names = set()
        for entry in entries:
            name = entry["name"]
            if (
                not isinstance(name, str) or not name or name in (".", "..", "manifest.json")
                or "/" in name or "\\" in name or name in names
            ):
                raise ValueError("invalid or duplicate resource name")
            names.add(name)
            payloads.append((name, source.joinpath(name).read_bytes()))
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise RuntimeError(
            "packaged system resources are unavailable or malformed; "
            "use a built Catbed distribution rather than an editable source install"
        ) from error

    destination = Path(destination).absolute()
    # Exclusive creation refuses existing directories, files, and symlinks.
    # Read all package data first so missing resources leave no partial export.
    destination.mkdir(mode=0o700)
    try:
        for name, contents in payloads:
            target = destination / name
            target.write_bytes(contents)
            target.chmod(0o755)
        (destination / "manifest.json").write_bytes(manifest_bytes)
    except BaseException:
        shutil.rmtree(destination)
        raise
    return destination
