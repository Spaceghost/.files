"""Firewall trials against a file-backed fake service backend; never call OpenRC."""
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest

SOURCE = Path(__file__).with_name('activate')
loader = importlib.machinery.SourceFileLoader('firewall_activation', str(SOURCE))
spec = importlib.util.spec_from_loader(loader.name, loader)
activation = importlib.util.module_from_spec(spec)
loader.exec_module(activation)
CHILDREN = []


class FakeBackend:
    def __init__(self, path):
        self.path = Path(path)
        if not self.path.exists():
            self.write({'table': False, 'active': False, 'queue': False, 'boot': [], 'calls': [],
                        'daemon': activation.identity(os.getpid())})

    def read(self):
        return json.loads(self.path.read_text())

    def write(self, state):
        temp = self.path.with_suffix('.tmp')
        temp.write_text(json.dumps(state))
        os.replace(temp, self.path)

    def change(self, **changes):
        state = self.read()
        state.update(changes)
        self.write(state)

    def table(self):
        return self.read()['table']

    def active(self):
        return self.read()['active']

    def gate_active(self):
        return self.read().get('gate_service', False)

    def queue(self):
        return self.read()['queue']

    def daemon(self):
        return self.read()['daemon']

    def gate(self):
        if not self.table() or self.read().get('bad_gate'):
            raise RuntimeError('invalid gate')

    def boot(self, name):
        return name in self.read()['boot']

    def start(self, name):
        state = self.read()
        state['calls'].append('start ' + name)
        if name == 'oldbook-firewall':
            state['table'] = True
            state['gate_service'] = True
        else:
            state['active'] = state['queue'] = True
        self.write(state)
        if state.get('fail_start') == name:
            raise RuntimeError('simulated partial start failure')

    def stop_daemon(self):
        state = self.read()
        state['active'] = state['queue'] = False
        state['calls'].append('stop opensnitchd')
        self.write(state)

    def delete_gate(self):
        state = self.read()
        state['table'] = False
        state['gate_service'] = False
        state['calls'].append('delete inet oldbook')
        self.write(state)

    def add_boot(self, name):
        state = self.read()
        state['boot'].append(name)
        state['calls'].append('enable ' + name)
        self.write(state)
        if state.get('fail_boot') == name:
            raise RuntimeError('simulated partial boot-link failure')

    def remove_boot(self, name):
        state = self.read()
        if name in state['boot']:
            state['boot'].remove(name)
        state['calls'].append('disable ' + name)
        self.write(state)


def control_for(base):
    base = Path(base)
    def arm(token):
        child = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), '--watch', str(base), token],
                                 stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL, start_new_session=True)
        CHILDREN.append(child)
        return activation.identity(child.pid)
    return activation.Activation(FakeBackend(base / 'backend.json'), base, uid=os.getuid(), arm=arm)


class ActivationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.control = control_for(self.base)
        self.backend = self.control.backend

    def tearDown(self):
        for record in self.base.glob('*/state.json'):
            state = json.loads(record.read_text())
            watchdog = state.get('watchdog')
            if activation.alive(watchdog):
                os.kill(watchdog['pid'], signal.SIGTERM)
        for child in CHILDREN:
            child.wait(timeout=3)
        CHILDREN.clear()
        self.tmp.cleanup()

    def test_timeout_watchdog_survives_starting_process_exit(self):
        result = subprocess.run([sys.executable, str(Path(__file__).resolve()), '--start', str(self.base)],
                                text=True, capture_output=True, check=True)
        token = result.stdout.strip()
        state = self.control.load(token)
        self.assertTrue(activation.alive(state['watchdog']))
        for _ in range(80):
            if self.control.load(token)['status'] == 'rolled-back':
                break
            time.sleep(.05)
        self.assertEqual(self.control.load(token)['status'], 'rolled-back')
        self.assertFalse(self.backend.table())
        self.assertFalse(self.backend.active())
        self.assertEqual(self.backend.read()['calls'][-2:], ['stop opensnitchd', 'delete inet oldbook'])

    def test_partial_start_failure_rolls_back_only_attempted_resources(self):
        for service in activation.SERVICES:
            with self.subTest(service=service):
                self.backend.change(fail_start=service, calls=[])
                with self.assertRaisesRegex(RuntimeError, 'partial start'):
                    self.control.start(10)
                self.assertFalse(self.backend.table())
                self.assertFalse(self.backend.active())
                calls = self.backend.read()['calls']
                self.assertEqual('stop opensnitchd' in calls, service == 'opensnitchd')
                self.assertEqual(calls[-1], 'delete inet oldbook')

    def test_confirm_installs_both_links_and_cancels_rollback(self):
        token = self.control.start(10)
        state = self.control.confirm(token)
        self.assertEqual(state['status'], 'confirmed')
        self.assertEqual(self.backend.read()['boot'], list(activation.SERVICES))
        self.control.rollback(token)
        self.assertTrue(self.backend.active())
        self.assertTrue(self.backend.table())
        self.assertEqual((self.base / token).stat().st_mode & 0o777, 0o700)
        self.assertEqual((self.base / token / 'state.json').stat().st_mode & 0o777, 0o600)

    def test_partial_confirmation_failure_removes_only_new_links(self):
        token = self.control.start(10)
        self.backend.change(fail_boot='opensnitchd')
        with self.assertRaisesRegex(RuntimeError, 'partial boot-link'):
            self.control.confirm(token)
        state = self.backend.read()
        self.assertEqual(state['boot'], [])
        self.assertFalse(state['active'])
        self.assertFalse(state['table'])
        self.assertEqual(self.control.load(token)['status'], 'rolled-back')

    def test_baseline_refuses_existing_resources_without_mutations(self):
        for field, value in [('table', True), ('gate_service', True), ('active', True),
                             ('queue', True), ('boot', ['opensnitchd'])]:
            with self.subTest(field=field):
                original = self.backend.read()
                self.backend.change(**{field: value})
                with self.assertRaisesRegex(RuntimeError, 'existing'):
                    self.control.start(10)
                self.assertEqual(self.backend.read()['calls'], [])
                self.backend.write(original)

    def test_backend_detects_any_runlevel_and_enables_before_networking(self):
        runlevels = self.base / 'runlevels'
        for name in ('boot', 'default', 'custom'):
            (runlevels / name).mkdir(parents=True)
        backend = activation.Backend(runlevels=runlevels)
        for level in ('default', 'custom', 'boot'):
            link = runlevels / level / 'opensnitchd'
            link.symlink_to('/etc/init.d/opensnitchd')
            self.assertTrue(backend.boot('opensnitchd'))
            link.unlink()
        self.assertFalse(backend.boot('opensnitchd'))
        calls = []
        backend.run = lambda command: calls.append(command)
        for name in activation.SERVICES:
            backend.add_boot(name)
            self.assertEqual(calls[-1], ['/sbin/rc-update', 'add', name, 'boot'])
            link = runlevels / 'boot' / name
            link.symlink_to('/etc/init.d/' + name)
            backend.remove_boot(name)
            self.assertEqual(calls[-1], ['/sbin/rc-update', 'del', name, 'boot'])

    def test_dead_watchdog_or_changed_daemon_cannot_confirm(self):
        for damage in ('watchdog', 'daemon'):
            with self.subTest(damage=damage):
                token = self.control.start(10)
                state = self.control.load(token)
                if damage == 'watchdog':
                    os.kill(state['watchdog']['pid'], signal.SIGKILL)
                    for _ in range(20):
                        if not activation.alive(state['watchdog']):
                            break
                        time.sleep(.02)
                else:
                    self.backend.change(daemon={'pid': 1, 'start_ticks': 'wrong', 'boot_id': 'wrong'})
                with self.assertRaises(RuntimeError):
                    self.control.confirm(token)
                self.assertEqual(self.control.load(token)['status'], 'rolled-back')

    def test_tokens_and_symlinks_cannot_select_arbitrary_paths(self):
        for token in ('../outside', '/etc', '', 'a' * 31, 'A' * 32, 'a' * 32 + '/state.json'):
            with self.assertRaises(ValueError):
                self.control.load(token)
        with tempfile.TemporaryDirectory() as outside:
            token = 'a' * 32
            (self.base / token).symlink_to(outside)
            with self.assertRaisesRegex(RuntimeError, 'Unsafe'):
                self.control.load(token)
            (self.base / token).unlink()
        token = self.control.start(10)
        state = self.control.load(token)
        self.control.rollback(token)
        record = self.base / token / 'state.json'
        record.unlink()
        record.symlink_to('/etc/passwd')
        with self.assertRaises(OSError):
            self.control.load(token)
        record.unlink()
        self.control.save(token, state | {'status': 'rolled-back'})


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--watch':
        control_for(sys.argv[2]).watch(sys.argv[3])
    elif len(sys.argv) > 1 and sys.argv[1] == '--start':
        print(control_for(sys.argv[2]).start(1), flush=True)
    else:
        unittest.main()
