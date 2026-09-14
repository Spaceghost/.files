"""Bundle canonical system helpers without maintaining duplicate source files.

Both wheel and source builds embed the same resources. Building an extracted
source distribution uses its embedded copies and does not need this checkout.
No installation or service activation happens during a build.
"""

from pathlib import Path
import json
import runpy
import shutil

from setuptools import setup
from setuptools.command.build_py import build_py
from setuptools.command.sdist import sdist

PROJECT = Path(__file__).resolve().parent
bundle_desktop = runpy.run_path(str(PROJECT / "desktop_bundle.py"))["bundle_desktop"]
REPOSITORY = PROJECT.parents[1]
RESOURCE_PATH = Path("catbed/resources/linux")
SOURCES = {
    "oldbook-catmode": ("alpine/security/catmode/oldbook-catmode", "/usr/local/sbin/oldbook-catmode"),
    "oldbook-catmode.openrc": ("alpine/security/catmode/initd", "/etc/init.d/oldbook-catmode"),
    "catbed-sysrq-hold": ("alpine/bin/catbed-sysrq-hold", "/usr/local/sbin/catbed-sysrq-hold"),
    "oldbook-fan-hold": ("alpine/bin/oldbook-fan-hold", "/usr/local/sbin/oldbook-fan-hold"),
    "acpi-power-handler": ("alpine/system/acpi/PWRF/00000080", "/etc/acpi/PWRF/00000080"),
}


def bundle_system(destination):
    embedded = PROJECT / "src" / RESOURCE_PATH
    destination.mkdir(parents=True, exist_ok=True)
    if embedded.is_dir():
        shutil.copytree(embedded, destination, dirs_exist_ok=True)
        return
    manifest = {"version": 1, "platform": "linux", "files": []}
    for name, (source, installed_path) in SOURCES.items():
        path = REPOSITORY / source
        if not path.is_file():
            raise RuntimeError(f"Missing canonical Catbed resource: {path}")
        shutil.copyfile(path, destination / name)
        manifest["files"].append({"name": name, "destination": installed_path, "mode": "0755"})
    (destination / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")


class BuildPackage(build_py):
    def run(self):
        super().run()
        bundle_system(Path(self.build_lib) / RESOURCE_PATH)
        bundle_desktop(PROJECT, Path(self.build_lib) / "catbed/runtime")


class SourcePackage(sdist):
    def make_release_tree(self, base_dir, files):
        super().make_release_tree(base_dir, files)
        bundle_system(Path(base_dir) / "src" / RESOURCE_PATH)
        bundle_desktop(PROJECT, Path(base_dir) / "src/catbed/runtime")


setup(cmdclass={"build_py": BuildPackage, "sdist": SourcePackage})
