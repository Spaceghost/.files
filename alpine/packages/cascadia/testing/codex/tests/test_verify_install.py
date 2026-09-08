#!/usr/bin/env python3
"""Behavior tests for the staged Codex package verifier."""

import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


RECIPE = Path(__file__).resolve().parents[1]
VERIFY = RECIPE / "verify-install"


class VerifyInstallTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = Path(tempfile.mkdtemp(prefix="codex-apk-test-"))
        self.root = self.tempdir / "root"
        self.runtime = self.root / "usr/lib/codex/0.153.4"
        for part in ("cli", "app-server"):
            (self.runtime / part / "bin").mkdir(parents=True)
            (self.runtime / part / "codex-path").mkdir()
            (self.runtime / part / "codex-resources/zsh/bin").mkdir(parents=True)
        (self.runtime / "proxy").mkdir()

        self._metadata("cli", "codex", "bin/codex")
        self._metadata("app-server", "codex-app-server", "bin/codex-app-server")
        self._program("cli/bin/codex", "codex-cli 0.153.4")
        self.protocol_log = self.tempdir / "protocol.log"
        self._helper("cli/bin/codex-code-mode-host")
        self._program("app-server/bin/codex-app-server", "Usage: codex-app-server")
        self._helper("app-server/bin/codex-code-mode-host")
        self._program("cli/codex-path/rg", "ripgrep 15.2.0")
        self._program("app-server/codex-path/rg", "ripgrep 15.2.0")
        self._program("cli/codex-resources/bwrap", "bubblewrap 0.12.0")
        self._program("app-server/codex-resources/bwrap", "bubblewrap 0.12.0")
        self._program("proxy/codex-responses-api-proxy", "Usage: codex-responses-api-proxy")
        for part in ("cli", "app-server"):
            shell = self.runtime / part / "codex-resources/zsh/bin/zsh"
            shell.symlink_to("/bin/zsh")
            original = shell.parent / "zsh.upstream-gnu"
            original.write_bytes(b"preserved upstream zsh\n")
            original.chmod(0o755)
        (self.runtime / "alpine-adaptations.json").write_text(json.dumps({
            "private_zsh": "/bin/zsh",
            "reason": "upstream musl archive private zsh requires GNU loader",
            "preserved_original": "codex-resources/zsh/bin/zsh.upstream-gnu",
        }))
        links = {
            "codex": "../lib/codex/0.153.4/cli/bin/codex",
            "codex-code-mode-host": "../lib/codex/0.153.4/cli/bin/codex-code-mode-host",
            "codex-app-server": "../lib/codex/0.153.4/app-server/bin/codex-app-server",
            "codex-responses-api-proxy": "../lib/codex/0.153.4/proxy/codex-responses-api-proxy",
        }
        bindir = self.root / "usr/bin"
        bindir.mkdir(parents=True)
        for name, target in links.items():
            (bindir / name).symlink_to(target)

    def tearDown(self):
        shutil.rmtree(self.tempdir)

    def _metadata(self, part, variant, entrypoint):
        data = {
            "layoutVersion": 1,
            "version": "0.153.4",
            "target": "x86_64-unknown-linux-musl",
            "variant": variant,
            "entrypoint": entrypoint,
            "resourcesDir": "codex-resources",
            "pathDir": "codex-path",
        }
        (self.runtime / part / "codex-package.json").write_text(json.dumps(data))

    def _program(self, relative, output):
        path = self.runtime / relative
        path.write_text("#!/bin/sh\nprintf '%s\\n' " + repr(output) + "\n")
        path.chmod(0o755)

    def _helper(self, relative):
        path = self.runtime / relative
        path.write_text(
            "#!/bin/sh\n"
            "case \"$*\" in\n"
            "    --help) printf '%s\\n' 'Usage: codex-code-mode-host' ;;\n"
            "    '--listen stdio') printf '%s\\n' protocol >> "
            + repr(str(self.protocol_log))
            + " ;;\n"
            "    *) exit 23 ;;\n"
            "esac\n"
        )
        path.chmod(0o755)

    def verify(self):
        if not VERIFY.exists():
            return subprocess.CompletedProcess(
                [str(VERIFY), str(self.root)], 127, "", "verifier missing"
            )
        return subprocess.run(
            [str(VERIFY), str(self.root)], text=True, capture_output=True, check=False
        )

    def test_complete_native_bundle_is_accepted(self):
        result = self.verify()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("verified Codex 0.153.4", result.stdout)
        self.assertTrue(self.protocol_log.exists(), "helper protocol was not started")
        self.assertEqual(self.protocol_log.read_text().splitlines(), ["protocol", "protocol"])

    def test_missing_app_server_is_rejected(self):
        (self.runtime / "app-server/bin/codex-app-server").unlink()
        result = self.verify()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("codex-app-server", result.stderr)

    def test_wrong_package_metadata_is_rejected(self):
        metadata = self.runtime / "cli/codex-package.json"
        data = json.loads(metadata.read_text())
        data["version"] = "0.0.0"
        metadata.write_text(json.dumps(data))
        result = self.verify()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("metadata", result.stderr)

    def test_non_native_private_zsh_is_rejected(self):
        shell = self.runtime / "cli/codex-resources/zsh/bin/zsh"
        shell.unlink()
        shell.write_text("#!/bin/sh\nexit 0\n")
        shell.chmod(0o755)
        result = self.verify()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("/bin/zsh", result.stderr)

    def test_node_payload_is_rejected(self):
        node_modules = self.runtime / "cli/node_modules"
        node_modules.mkdir()
        (node_modules / "index.js").write_text("// forbidden package payload\n")
        result = self.verify()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("npm/node", result.stderr)


if __name__ == "__main__":
    unittest.main()
