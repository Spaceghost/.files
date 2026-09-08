"""Renamed commands and per-file configuration migration preserve behavior."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from superhold.config import Config, default_profiles_path, load_config


class SuperholdMigrationTests(unittest.TestCase):
    def test_new_config_takes_precedence_and_old_file_remains_untouched(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {'XDG_CONFIG_HOME': directory}):
            root = Path(directory)
            old = root / 'hold-to-help/config.toml'
            new = root / 'superhold/config.toml'
            old.parent.mkdir()
            old.write_text("trigger='capslock'\nhold_seconds=0.25\n")
            self.assertEqual(load_config(), Config('capslock', .25))
            new.parent.mkdir()
            new.write_text("trigger='super'\nhold_seconds=0.75\n")
            self.assertEqual(load_config(), Config('super', .75))
            self.assertEqual(old.read_text(), "trigger='capslock'\nhold_seconds=0.25\n")

    def test_invalid_new_config_does_not_fall_back_to_valid_legacy_config(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {'XDG_CONFIG_HOME': directory}):
            root = Path(directory)
            for name in ('hold-to-help', 'superhold'):
                (root / name).mkdir()
            (root / 'hold-to-help/config.toml').write_text("trigger='super'\n")
            (root / 'superhold/config.toml').write_text("[broken")
            with self.assertRaises(ValueError):
                load_config()

    def test_profiles_fallback_is_per_file_and_new_file_wins(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {'XDG_CONFIG_HOME': directory}):
            root = Path(directory)
            old = root / 'hold-to-help/profiles.json'
            new = root / 'superhold/profiles.json'
            self.assertEqual(default_profiles_path(), new)
            old.parent.mkdir()
            old.write_text('{}')
            self.assertEqual(default_profiles_path(), old)
            new.parent.mkdir()
            (new.parent / 'config.toml').write_text("trigger='super'\n")
            self.assertEqual(default_profiles_path(), old)
            new.write_text('{}')
            self.assertEqual(default_profiles_path(), new)

    def test_dangling_primary_config_is_an_error_not_defaults_or_legacy(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {'XDG_CONFIG_HOME': directory}):
            root = Path(directory)
            old = root / 'hold-to-help/config.toml'
            new = root / 'superhold/config.toml'
            old.parent.mkdir()
            old.write_text("trigger='capslock'\n")
            new.parent.mkdir()
            new.symlink_to(root / 'missing.toml')
            with self.assertRaisesRegex(ValueError, 'configuration file not found'):
                load_config()

    def test_primary_and_legacy_cli_report_superhold_without_display(self):
        root = Path(__file__).resolve().parents[1]
        environment = {'PATH': os.environ['PATH'], 'PYTHONDONTWRITEBYTECODE': '1'}
        for command in ('superhold', 'hold-to-help'):
            path = root / 'bin' / command
            self.assertTrue(path.is_file(), f'{command} command is missing')
            result = subprocess.run([sys.executable, str(path), '--version'],
                                    env=environment, capture_output=True, text=True, timeout=3)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), 'Superhold 0.1.0')
