#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Create a deterministic standalone source release, without a VCS dependency."""
import argparse
import gzip
import hashlib
import os
from pathlib import Path
import tarfile
import tempfile

VERSION = "0.1.0"
EPOCH = 1788739200
REQUIRED = ("CMakeLists.txt", "LICENSE", "README.md", "CONTRIBUTING.md", "CHANGELOG.md", "SOURCE_MANIFEST")


def source_files(source):
    for name in REQUIRED:
        path = source / name
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"Missing regular source file: {name}")
    result = []
    names = (source / "SOURCE_MANIFEST").read_text().splitlines()
    if len(names) != len(set(names)) or not set(REQUIRED).issubset(names):
        raise ValueError("SOURCE_MANIFEST must include required files exactly once")
    for name in names:
        relative = Path(name)
        if not name or relative.is_absolute() or any(part.startswith(".") or part == "__pycache__" for part in relative.parts):
            raise ValueError(f"Invalid source manifest path: {name}")
        path = source / relative
        if any(part.is_symlink() for part in (path, *path.parents) if part != source and source in part.parents):
            raise ValueError(f"Source symlink must be reviewed before release: {path}")
        if not path.is_file():
            raise ValueError(f"Missing source manifest file: {name}")
        result.append(path)
    return sorted(result, key=lambda path: path.relative_to(source).as_posix())


def make_release(source, destination, epoch=EPOCH):
    if not 0 <= epoch <= 0xFFFFFFFF:
        raise ValueError("SOURCE_DATE_EPOCH must fit an unsigned 32-bit gzip timestamp")
    source = Path(source).resolve(strict=True)
    destination = Path(destination).absolute()
    paths = source_files(source)
    if destination.resolve() in paths:
        raise ValueError("Release output must not replace a source file")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=destination.parent, prefix=".release-", delete=False) as stream:
            temporary = Path(stream.name)
            with gzip.GzipFile(filename="", mode="wb", fileobj=stream, mtime=epoch) as zipped:
                with tarfile.open(fileobj=zipped, mode="w", format=tarfile.USTAR_FORMAT) as archive:
                    for path in paths:
                        relative = path.relative_to(source).as_posix()
                        entry = tarfile.TarInfo(f"superhold-{VERSION}/{relative}")
                        entry.size = path.stat().st_size
                        entry.mtime = epoch
                        entry.mode = 0o755 if relative.startswith(("bin/", "tools/")) and path.stat().st_mode & 0o111 else 0o644
                        entry.uid = entry.gid = 0
                        entry.uname = entry.gname = "root"
                        with path.open("rb") as content:
                            archive.addfile(entry, content)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.chmod(0o644)
        os.replace(temporary, destination)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return hashlib.sha256(destination.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--epoch", type=int, default=int(os.environ.get("SOURCE_DATE_EPOCH", EPOCH)))
    args = parser.parse_args()
    try:
        digest = make_release(Path(__file__).resolve().parent.parent, args.output, args.epoch)
    except (OSError, ValueError, tarfile.TarError) as error:
        parser.exit(1, f"Release failed: {error}\n")
    print(f"{digest}  {args.output}")


if __name__ == "__main__":
    main()
