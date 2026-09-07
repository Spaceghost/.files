#!/usr/bin/env python3
"""Check bootstrap policy generation without touching host rules or networking."""

import hashlib
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile
import unittest


GENERATOR = Path(__file__).resolve().with_name("bootstrap-rules")


class BootstrapRulesTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="bootstrap-rules-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.marker = self.root / "executable-was-run"
        self.executables = []
        for directory in ("first", "second"):
            parent = self.root / directory
            parent.mkdir()
            executable = parent / "Test-client"
            # Equal basenames and contents must still produce distinct path rules.
            executable.write_text(
                "#!/bin/sh\n: > '" + str(self.marker) + "'\nexit 91\n"
            )
            executable.chmod(0o700)
            self.executables.append(executable)
        self.resolvers = ["198.51.100.53", "2001:db8::53"]

    def command(self, output, uid="1000", executables=None, resolvers=None):
        arguments = [str(GENERATOR), "--uid", str(uid)]
        for executable in self.executables if executables is None else executables:
            arguments.extend(["--executable", str(executable)])
        for resolver in self.resolvers if resolvers is None else resolvers:
            arguments.extend(["--resolver", resolver])
        arguments.extend(["--output", str(output)])
        return arguments

    def invoke(self, arguments):
        return subprocess.run(
            arguments,
            cwd=self.root,
            capture_output=True,
            text=True,
            timeout=10,
            # Generated permissions must remain private even under a loose umask.
            preexec_fn=lambda: os.umask(0),
        )

    def generate(self, output=None, **kwargs):
        output = self.root / "generated" if output is None else output
        result = self.invoke(self.command(output, **kwargs))
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
        self.assertFalse(self.marker.exists(), "generator executed an input file")
        return output

    def snapshot(self, root):
        snapshot = {}
        for path in sorted(root.rglob("*")):
            metadata = path.lstat()
            if path.is_symlink():
                value = ("symlink", os.readlink(path))
            elif path.is_dir():
                value = ("directory",)
            elif stat.S_ISREG(metadata.st_mode):
                value = ("file", path.read_bytes())
            else:
                value = ("special", stat.S_IFMT(metadata.st_mode))
            snapshot[str(path.relative_to(root))] = (
                stat.S_IMODE(metadata.st_mode), value
            )
        return snapshot

    def assert_rejected(self, arguments):
        before = self.snapshot(self.root)
        result = self.invoke(arguments)
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertTrue(result.stderr.strip(), "rejection needs a diagnostic")
        self.assertEqual(self.snapshot(self.root), before, "rejection changed files")

    def read_rules(self, output):
        rule_paths = sorted((output / "rules").glob("*.json"))
        self.assertTrue(rule_paths, "no rule files generated")
        return [json.loads(path.read_text()) for path in rule_paths]

    def test_dates_are_valid_rfc3339_and_represent_the_fixed_policy_revision(self):
        for rule in self.read_rules(self.generate()):
            self.assertEqual(rule['created'], rule['updated'])
            self.assertEqual(datetime.fromisoformat(rule['created']),
                             datetime(2026, 9, 7, tzinfo=timezone.utc))

    def leaves(self, rule):
        operator = rule["operator"]
        self.assertEqual(operator["type"], "list")
        self.assertEqual(operator["operand"], "list")
        leaves = operator["list"]
        self.assertTrue(leaves)
        self.assertEqual(len({leaf["operand"] for leaf in leaves}), len(leaves))
        self.assertTrue(all(leaf["type"] in ("simple", "regexp") for leaf in leaves))
        return {leaf["operand"]: leaf for leaf in leaves}

    def policy_allows(self, rules, connection):
        """Evaluate the emitted AND policy, including regexp anchor behavior.

        This checks the generated policy's boundaries; daemon checksum lookup and
        actual packet enforcement need the separate network namespace tests.
        """
        for rule in rules:
            leaves = self.leaves(rule)
            matches = []
            for operand, leaf in leaves.items():
                actual = connection.get(operand)
                if actual is None:
                    matches.append(False)
                elif leaf["type"] == "simple":
                    matches.append(str(actual) == leaf["data"])
                else:
                    matches.append(re.search(leaf["data"], str(actual)) is not None)
            if rule["enabled"] and rule["action"] == "allow" and all(matches):
                return True
        return False

    def connection(self, executable, protocol="tcp", port="443", address="203.0.113.9"):
        return {
            "process.path": str(executable),
            "user.id": "1000",
            "process.hash.md5": hashlib.md5(executable.read_bytes()).hexdigest(),
            "protocol": protocol,
            "dest.port": str(port),
            "dest.ip": address,
        }

    def test_rules_only_allow_requested_executables_https_and_exact_resolver_dns(self):
        output = self.generate()
        rules = self.read_rules(output)
        self.assertEqual(len(rules), len(self.executables) * (1 + len(self.resolvers)))
        self.assertEqual(len({rule["name"] for rule in rules}), len(rules))
        coverage = set()
        for rule in rules:
            self.assertIs(rule["enabled"], True)
            self.assertIs(rule["precedence"], False)
            self.assertEqual(rule["action"], "allow")
            self.assertEqual(rule["duration"], "always")
            leaves = self.leaves(rule)
            executable = Path(leaves["process.path"]["data"])
            self.assertIn(executable, self.executables)
            self.assertEqual(leaves["process.path"]["type"], "simple")
            self.assertIs(leaves["process.path"]["sensitive"], True)
            self.assertEqual(leaves["user.id"]["type"], "simple")
            self.assertEqual(leaves["user.id"]["data"], "1000")
            self.assertEqual(leaves["process.hash.md5"]["type"], "simple")
            self.assertEqual(
                leaves["process.hash.md5"]["data"],
                hashlib.md5(executable.read_bytes()).hexdigest(),
            )
            self.assertEqual(leaves["protocol"]["type"], "regexp")
            self.assertEqual(leaves["dest.port"]["type"], "simple")
            common = {"process.path", "user.id", "process.hash.md5", "protocol", "dest.port"}
            if leaves["dest.port"]["data"] == "443":
                self.assertEqual(set(leaves), common)
                self.assertEqual(leaves["protocol"]["data"], "^tcp6?$")
                coverage.add((str(executable), "https"))
            else:
                self.assertEqual(set(leaves), common | {"dest.ip"})
                self.assertEqual(leaves["dest.port"]["data"], "53")
                self.assertEqual(leaves["protocol"]["data"], "^(tcp|udp)6?$")
                self.assertEqual(leaves["dest.ip"]["type"], "simple")
                self.assertIn(leaves["dest.ip"]["data"], self.resolvers)
                coverage.add((str(executable), leaves["dest.ip"]["data"]))
        expected = {
            (str(executable), destination)
            for executable in self.executables
            for destination in ["https", *self.resolvers]
        }
        self.assertEqual(coverage, expected)
        self.assertEqual({path.name for path in output.iterdir()}, {"rules", "manifest.json"})
        self.assertEqual(len(list((output / "rules").iterdir())), len(rules))

    def test_policy_accepts_https_and_dns_but_rejects_near_matches(self):
        rules = self.read_rules(self.generate())
        for executable in self.executables:
            allowed = [self.connection(executable, protocol) for protocol in ("tcp", "tcp6")]
            allowed.extend(
                self.connection(executable, protocol, "53", resolver)
                for resolver in self.resolvers
                for protocol in ("tcp", "tcp6", "udp", "udp6")
            )
            for connection in allowed:
                with self.subTest(allowed=connection):
                    self.assertTrue(self.policy_allows(rules, connection))
                for operand, wrong in (
                    ("process.path", str(executable) + "-other"),
                    ("process.path", str(executable).replace("Test-client", "test-client")),
                    ("user.id", "0"),
                    ("user.id", "1001"),
                    ("process.hash.md5", "0" * 32),
                    ("protocol", "not-" + connection["protocol"]),
                    ("protocol", connection["protocol"] + "-other"),
                    ("dest.port", "80"),
                    ("dest.port", "4443"),
                ):
                    changed = dict(connection, **{operand: wrong})
                    with self.subTest(rejected=changed):
                        self.assertFalse(self.policy_allows(rules, changed))
            for protocol in ("udp", "udp6", "icmp", "icmp6"):
                self.assertFalse(self.policy_allows(rules, self.connection(executable, protocol)))
            for address in ("198.51.100.54", "2001:db8::54", "198.51.100.53.evil", "2001:db8::530"):
                for protocol in ("tcp", "tcp6", "udp", "udp6"):
                    self.assertFalse(
                        self.policy_allows(rules, self.connection(executable, protocol, "53", address))
                    )

    def test_manifest_records_audit_hashes_outside_loadable_rule_directory(self):
        output = self.generate()
        manifest = json.loads((output / "manifest.json").read_text())
        self.assertEqual(manifest.get("schema", manifest.get("schema_version")), 1)
        self.assertEqual(manifest["uid"], 1000)
        self.assertEqual(set(manifest["resolvers"]), set(self.resolvers))
        executables = {item["path"]: item for item in manifest["executables"]}
        self.assertEqual(set(executables), {str(path) for path in self.executables})
        for path in self.executables:
            content = path.read_bytes()
            self.assertEqual(executables[str(path)]["md5"], hashlib.md5(content).hexdigest())
            self.assertEqual(executables[str(path)]["sha256"], hashlib.sha256(content).hexdigest())
        self.assertIsInstance(manifest["rules"], dict)
        self.assertEqual(len(manifest["rules"]), len(self.read_rules(output)))
        for filename, digest in manifest["rules"].items():
            path = output / "rules" / filename
            self.assertEqual(path.parent, output / "rules")
            self.assertEqual(digest, hashlib.sha256(path.read_bytes()).hexdigest())
        self.assertFalse((output / "rules" / "manifest.json").exists())

    def test_output_is_private_even_with_permissive_umask(self):
        output = self.generate()
        for path in [output, *output.rglob("*")]:
            with self.subTest(path=path.relative_to(output)):
                self.assertFalse(path.is_symlink())
                expected = 0o700 if path.is_dir() else 0o600
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), expected)

    def test_repeated_generation_is_byte_for_byte_deterministic(self):
        first = self.generate(self.root / "output-one")
        second = self.generate(self.root / "output-two")
        self.assertEqual(self.snapshot(first), self.snapshot(second))

    def test_uid_boundary_values_are_supported(self):
        for uid in (0, 4294967294):
            with self.subTest(uid=uid):
                output = self.generate(self.root / ("uid-" + str(uid)), uid=uid)
                for rule in self.read_rules(output):
                    self.assertEqual(self.leaves(rule)["user.id"]["data"], str(uid))

    def test_invalid_uids_are_rejected_without_writes(self):
        for uid in ("-1", "4294967295", "4294967296", "1.0", "1000x", "", "*", "root"):
            with self.subTest(uid=uid):
                self.assert_rejected(self.command(self.root / "output", uid=uid))

    def test_malformed_and_wildcard_resolvers_are_rejected_without_writes(self):
        for resolver in (
            "*", "any", "", "resolver.example", "198.51.100.*", "0.0.0.0/0", "::/0",
            "198.51.100.53/32", "2001:db8::53/128", "999.1.1.1", "2001:db8:::53",
            "[2001:db8::53]", "198.51.100.53:53",
        ):
            with self.subTest(resolver=resolver):
                self.assert_rejected(
                    self.command(self.root / "output", resolvers=[self.resolvers[0], resolver])
                )

    def test_missing_required_arguments_are_rejected_without_writes(self):
        command = self.command(self.root / "output")
        for option in ("--uid", "--executable", "--resolver", "--output"):
            arguments = [command[0]]
            for index in range(1, len(command), 2):
                if command[index] != option:
                    arguments.extend(command[index:index + 2])
            with self.subTest(option=option):
                self.assert_rejected(arguments)

    def test_invalid_executable_paths_are_rejected_without_writes(self):
        nonexecutable = self.root / "not-executable"
        nonexecutable.write_text("not a program\n")
        nonexecutable.chmod(0o600)
        fifo = self.root / "fifo"
        os.mkfifo(fifo, 0o700)
        for executable in (
            self.executables[0].relative_to(self.root),
            self.root / "missing",
            self.root / "first",
            nonexecutable,
            fifo,
            str(self.root) + "/first/../first/Test-client",
        ):
            with self.subTest(executable=executable):
                self.assert_rejected(
                    self.command(self.root / "output", executables=[self.executables[1], executable])
                )

    def test_symlink_executable_paths_are_rejected_without_writes(self):
        link = self.root / "linked-executable"
        link.symlink_to(self.executables[0])
        ancestor = self.root / "linked-bin"
        ancestor.symlink_to(self.executables[0].parent, target_is_directory=True)
        dangling = self.root / "dangling-executable"
        dangling.symlink_to(self.root / "missing")
        for executable in (link, ancestor / self.executables[0].name, dangling):
            with self.subTest(executable=executable):
                self.assert_rejected(self.command(self.root / "output", executables=[executable]))

    def test_relative_output_is_rejected_without_writes(self):
        self.assert_rejected(self.command("relative-output"))

    def test_existing_output_is_rejected_and_preserved(self):
        directory = self.root / "existing-directory"
        directory.mkdir()
        (directory / "keep").write_bytes(b"existing contents\x00\xff")
        empty = self.root / "empty-directory"
        empty.mkdir()
        regular = self.root / "existing-file"
        regular.write_text("keep this file\n")
        for output in (directory, empty, regular):
            with self.subTest(output=output):
                self.assert_rejected(self.command(output))

    def test_output_symlinks_and_symlink_ancestors_are_rejected_without_writes(self):
        directory = self.root / "real-directory"
        directory.mkdir()
        (directory / "keep").write_text("preserve\n")
        linked = self.root / "linked-output"
        linked.symlink_to(directory, target_is_directory=True)
        dangling = self.root / "dangling-output"
        dangling.symlink_to(self.root / "nonexistent-output")
        for output in (linked, dangling, linked / "new-output", linked / "nested" / "new-output"):
            with self.subTest(output=output):
                self.assert_rejected(self.command(output))


if __name__ == "__main__":
    unittest.main()
