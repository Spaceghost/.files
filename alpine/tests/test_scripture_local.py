"""Exercise the on-demand backend with a real private listener and fake model."""
import importlib.machinery
import importlib.util
from contextlib import redirect_stderr
import io
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]
loader = importlib.machinery.SourceFileLoader('scripture_local_test',
    str(REPO / 'alpine/desktop/.local/bin/oldbook-scripture-local'))
spec = importlib.util.spec_from_loader(loader.name, loader)
local = importlib.util.module_from_spec(spec)
loader.exec_module(local)


class LocalScriptureTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='scripture-local-test-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        config = self.root / 'config/oldbook/ollama.json'
        config.parent.mkdir(parents=True)
        config.write_text(json.dumps({'local_server_enabled': True, 'inference_host': 'local'}))
        self.data = self.root / 'data/oldbook/ollama'
        self.state = self.root / 'state/oldbook/ollama'
        binary = self.data / 'runtime-0.17.7-r1/usr/bin/ollama'
        binary.parent.mkdir(parents=True)
        (self.data / 'models').mkdir()
        (self.data / 'models/fixture').write_bytes(b'retained model')
        binary.write_text('''#!/usr/bin/python3
import json, os, signal, socket, time
from pathlib import Path
profile = Path(os.environ['HOME'])
keys = ('HOME', 'OLLAMA_HOST', 'OLLAMA_MODELS', 'OLLAMA_NO_CLOUD', 'OLLAMA_KEEP_ALIVE',
        'OLLAMA_CONTEXT_LENGTH', 'LD_LIBRARY_PATH')
(profile/'server.json').write_text(json.dumps({'pid': os.getpid(),
    'env': {key: os.environ[key] for key in keys}}))
signal.signal(signal.SIGTERM, lambda *_: exit(0))
host, port = os.environ['OLLAMA_HOST'].split(':')
server = socket.socket()
server.bind((host, int(port)))
server.listen()
while True:
    time.sleep(.05)
''')
        binary.chmod(0o755)
        self.helper = self.root / 'study.py'
        self.helper.write_text('''import json, os, sys
from pathlib import Path
target=Path(os.environ['XDG_STATE_HOME'])/'invocation.json'
target.write_text(json.dumps(sys.argv[1:]))
''')
        with socket.socket() as reservation:
            reservation.bind(('127.0.0.1', 0))
            port = reservation.getsockname()[1]
        for replacement in (patch.object(local, 'PORT', port), patch.object(local, 'HELPER', self.helper),
                            patch.dict(os.environ, XDG_DATA_HOME=str(self.root / 'data'),
                                       XDG_STATE_HOME=str(self.root / 'state'),
                                       XDG_CONFIG_HOME=str(self.root / 'config'))):
            replacement.start()
            self.addCleanup(replacement.stop)

    def run_command(self, *arguments):
        with patch.object(sys, 'argv', ['oldbook-scripture-local', 'John 1:1', '--kind',
                                       'observation', *arguments]):
            return local.main()

    def assert_backend_stopped(self):
        record = json.loads((self.state / 'profile/server.json').read_text())
        self.assertFalse((Path('/proc') / str(record['pid'])).exists())
        self.assertEqual((self.data / 'models/fixture').read_bytes(), b'retained model')
        return record

    def test_owned_server_is_loopback_only_and_staging_arguments_reach_study_cli(self):
        assets, database = self.root / 'review assets', self.root / 'review cache.sqlite3'
        message = io.StringIO()
        with redirect_stderr(message):
            self.assertEqual(self.run_command('--assets', str(assets), '--database', str(database), '--no-track'), 0)
        self.assertIn('up to 15 minutes', message.getvalue())
        record = self.assert_backend_stopped()
        self.assertEqual(record['env']['OLLAMA_HOST'], f'127.0.0.1:{local.PORT}')
        self.assertEqual(record['env']['OLLAMA_NO_CLOUD'], '1')
        self.assertEqual(record['env']['OLLAMA_KEEP_ALIVE'], '0')
        self.assertEqual(record['env']['HOME'], str(self.state / 'profile'))
        self.assertEqual(record['env']['OLLAMA_MODELS'], str(self.data / 'models'))
        arguments = json.loads((self.root / 'state/invocation.json').read_text())
        self.assertEqual(arguments[:4], ['--assets', str(assets), '--database', str(database)])
        self.assertIn('--no-track', arguments)
        self.assertIn('qwen2.5:1.5b', arguments)
        self.assertEqual(arguments[arguments.index('--timeout') + 1], '900')
        self.assertEqual(arguments[-2:], ['--endpoint', f'http://127.0.0.1:{local.PORT}'])

    def test_explicit_timeout_boundaries_reach_generator(self):
        for value in (1, 900):
            with self.subTest(timeout=value), redirect_stderr(io.StringIO()):
                self.assertEqual(self.run_command('--timeout', str(value)), 0)
                arguments = json.loads((self.root / 'state/invocation.json').read_text())
                self.assertEqual(arguments[arguments.index('--timeout') + 1], str(value))
                self.assert_backend_stopped()

    def test_timeout_outside_bounds_is_rejected_before_starting_server(self):
        for value in (0, 901):
            with self.subTest(timeout=value), redirect_stderr(io.StringIO()), \
                    patch.object(local, 'backend') as backend:
                with self.assertRaises(SystemExit) as raised:
                    self.run_command('--timeout', str(value))
                self.assertEqual(raised.exception.code, 2)
                backend.assert_not_called()

    def test_occupied_port_does_not_reuse_or_stop_existing_listener(self):
        with socket.socket() as existing:
            existing.bind(('127.0.0.1', local.PORT))
            existing.listen()
            with self.assertRaisesRegex(RuntimeError, 'occupied'):
                self.run_command()
            self.assertEqual(existing.getsockname(), ('127.0.0.1', local.PORT))
            self.assertFalse((self.state / 'profile/server.json').exists())
            self.assertFalse(local.owns_listener(os.getpid() + 100000000, local.PORT))

    def test_parallel_invocation_reports_busy_and_preserves_first_owned_server(self):
        with local.backend(self.data, self.state):
            record = json.loads((self.state / 'profile/server.json').read_text())
            with self.assertRaisesRegex(RuntimeError, 'Another local'):
                self.run_command()
            self.assertTrue(local.owns_listener(record['pid'], local.PORT))
        self.assert_backend_stopped()

    def test_failed_generation_propagates_exit_code_and_stops_only_owned_backend(self):
        self.helper.write_text('raise SystemExit(7)\n')
        self.assertEqual(self.run_command(), 7)
        self.assert_backend_stopped()

    def test_exception_during_generation_stops_owned_backend(self):
        with self.assertRaisesRegex(RuntimeError, 'fixture interrupted'):
            with local.backend(self.data, self.state):
                raise RuntimeError('fixture interrupted')
        self.assert_backend_stopped()

    def test_failed_or_interrupted_pidfd_acquisition_reaps_only_new_server(self):
        native_popen = subprocess.Popen
        created = []

        def launch(*arguments, **options):
            process = native_popen(*arguments, **options)
            created.append(process)
            return process

        unrelated = native_popen([sys.executable, '-c', 'import time; time.sleep(60)'])
        try:
            for failure in (OSError('fixture pidfd failure'), SystemExit(129)):
                with self.subTest(failure=type(failure).__name__):
                    with patch.object(local.subprocess, 'Popen', side_effect=launch), \
                            patch.object(local.os, 'pidfd_open', side_effect=failure):
                        try:
                            with self.assertRaises(type(failure)):
                                with local.backend(self.data, self.state):
                                    self.fail('failed pidfd acquisition must not yield a backend')
                            self.assertIsNotNone(created[-1].poll(), 'new server was left running')
                            self.assertIsNone(unrelated.poll(), 'unrelated process was stopped')
                            self.assertEqual((self.data / 'models/fixture').read_bytes(), b'retained model')
                        finally:
                            # Keep the intentionally failing pre-fix fixture bounded.
                            for process in created:
                                if process.poll() is None:
                                    process.terminate()
                                process.wait(timeout=3)
        finally:
            unrelated.terminate()
            unrelated.wait(timeout=3)

    def test_missing_runtime_fails_without_download_or_new_server(self):
        (self.data / 'runtime-0.17.7-r1/usr/bin/ollama').unlink()
        with self.assertRaisesRegex(RuntimeError, 'runtime is missing'):
            self.run_command()
        self.assertFalse(self.state.exists())

    def test_hangup_and_termination_promptly_stop_owned_children_and_preserve_others(self):
        source = REPO / 'alpine/desktop/.local/bin/oldbook-scripture-local'
        wrapper = self.root / 'oldbook-scripture-local'
        content = source.read_text()
        self.assertEqual(content.count('PORT = 11435'), 1)
        # Run the real entrypoint and signal handlers, changing only its port
        # so a live bootstrap server cannot be contacted by this fixture.
        wrapper.write_text(content.replace('PORT = 11435', f'PORT = {local.PORT}'))
        wrapper.with_name('oldbook-scripture-study').write_text('''import os, time
from pathlib import Path
path = Path(os.environ['XDG_STATE_HOME'])/'generator.pid'
path.write_text(str(os.getpid()))
time.sleep(60)
''')
        with socket.socket() as unrelated:
            unrelated.bind(('127.0.0.1', 0))
            unrelated.listen()
            for number in (signal.SIGHUP, signal.SIGTERM):
                with self.subTest(signal=number):
                    marker = self.root / 'state/generator.pid'
                    marker.unlink(missing_ok=True)
                    process = subprocess.Popen([sys.executable, '-B', str(wrapper), 'John 1:1',
                        '--kind', 'observation'], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                        start_new_session=True)
                    owned = []
                    try:
                        # Interpreter startup may be scheduled slowly while a
                        # real CPU inference is running; cleanup is still timed
                        # independently from delivery of the tested signal.
                        deadline = time.monotonic() + 30
                        while not marker.exists() and time.monotonic() < deadline:
                            if process.poll() is not None:
                                self.fail(process.stderr.read().decode())
                            time.sleep(.02)
                        self.assertTrue(marker.exists(), 'delegated generator did not start')
                        generator_pid = int(marker.read_text())
                        server_pid = json.loads((self.state / 'profile/server.json').read_text())['pid']
                        owned = [os.pidfd_open(pid) for pid in (generator_pid, server_pid)]
                        started = time.monotonic()
                        process.send_signal(number)
                        self.assertEqual(process.wait(timeout=3), 128 + number)
                        self.assertLess(time.monotonic() - started, 3)
                        self.assertFalse((Path('/proc') / str(generator_pid)).exists())
                        self.assert_backend_stopped()
                        self.assertEqual(unrelated.getsockopt(socket.SOL_SOCKET, socket.SO_ACCEPTCONN), 1)
                    finally:
                        if process.poll() is None:
                            process.terminate()
                        try:
                            process.wait(timeout=3)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            process.wait(timeout=3)
                        process.stderr.close()
                        for descriptor in owned:
                            try:
                                signal.pidfd_send_signal(descriptor, signal.SIGTERM)
                            except ProcessLookupError:
                                pass
                            os.close(descriptor)


if __name__ == '__main__':
    unittest.main()
