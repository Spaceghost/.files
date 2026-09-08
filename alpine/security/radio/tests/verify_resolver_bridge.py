#!/usr/bin/env python3
"""Exercise opt-in openresolv host-PID locking only in guarded private namespaces."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import select
import signal
import subprocess
import sys
import time
import traceback

SCRIPT = Path(__file__).resolve()
spec = importlib.util.spec_from_file_location('applier_proof', SCRIPT.with_name('verify_network_applier.py'))
proof = importlib.util.module_from_spec(spec)
spec.loader.exec_module(proof)


def worker(host, patched_script):
    expected = proof.prepare_private(host, patched_script)
    sys.path.insert(0, str(proof.LIBRARY))
    from privacyctl_runtime.network import NativeNetwork
    lock = Path('/run/resolvconf/lock')
    keys = Path('/run/resolvconf/keys')
    backend = NativeNetwork()
    cases = []

    def guard():
        proof.guards.guard_private(host, expected)

    def native(key):
        return backend._run([proof.RESOLVCONF, '-a', key], content='nameserver 192.0.2.53\n',
                            deadline=time.monotonic() + 3, check=guard)

    def record(name, **values):
        case = {'name': name, **values}
        cases.append(case)
        proof.emit({'phase': 'case', **case})

    # An ordinary live provider in the containing namespace keeps its native lock.
    holder = subprocess.Popen(['/bin/sleep', '30'])
    try:
        lock.mkdir()
        (lock / 'pid').write_text(str(holder.pid) + '\n')
        started = time.monotonic()
        try:
            native('live-host-lock')
        except RuntimeError as error:
            assert 'timed out' in str(error), str(error)
        else:
            raise AssertionError('nested writer stole a live ordinary lock')
        assert holder.poll() is None
        assert (lock / 'pid').read_text() == str(holder.pid) + '\n'
        assert not (keys / 'live-host-lock').exists()
        record('nested_writer_preserves_live_ordinary_lock', elapsed_seconds=time.monotonic() - started)
    finally:
        holder.terminate()
        holder.wait(timeout=2)
    # The same stale ordinary PID must then be recoverable by a nested writer.
    native('stale-ordinary-lock')
    assert (keys / 'stale-ordinary-lock').exists() and not lock.exists()
    record('nested_writer_recovers_stale_ordinary_lock')

    def controlled_owner(key):
        ready_read, ready_write = os.pipe2(os.O_CLOEXEC)
        release_read, release_write = os.pipe2(os.O_CLOEXEC)
        owner = os.fork()
        if owner == 0:
            os.close(ready_read)
            os.close(release_write)
            try:
                class HoldingNetwork(NativeNetwork):
                    def _capture(self, process, outer_fd, deadline, check, content):
                        while not (lock / 'pid').exists():
                            check()
                            if time.monotonic() >= deadline:
                                raise RuntimeError('fixture did not observe lock acquisition')
                            time.sleep(0.002)
                        inner = int(Path(f'/proc/{process.pid}/task/{process.pid}/children').read_text())
                        value = {'owner_pid': os.getpid(), 'outer_pid': process.pid,
                                 'inner_pid': inner, 'lock_pid': int((lock / 'pid').read_text()),
                                 'pid_namespace': os.readlink(f'/proc/{inner}/ns/pid')}
                        os.write(ready_write, json.dumps(value).encode() + b'\n')
                        if not select.select([release_read], [], [], 1.5)[0]:
                            raise RuntimeError('fixture release deadline exceeded')
                        if os.read(release_read, 1) != b'G':
                            raise RuntimeError('fixture release cancelled')
                        return super()._capture(process, outer_fd, deadline, check, content)
                HoldingNetwork()._run([proof.RESOLVCONF, '-a', key],
                    content='nameserver 192.0.2.54\n', deadline=time.monotonic() + 3, check=guard)
                os._exit(0)
            except BaseException:
                os.write(ready_write, json.dumps({'error': traceback.format_exc()}).encode() + b'\n')
                os._exit(1)
        os.close(ready_write)
        os.close(release_read)
        try:
            assert select.select([ready_read], [], [], 1.5)[0], 'controlled owner never acquired lock'
            message = json.loads(os.read(ready_read, 8192))
            assert 'error' not in message, message
            assert message['lock_pid'] == message['inner_pid'] and message['lock_pid'] != 1
            assert os.readlink(f"/proc/{message['inner_pid']}/ns/pid") != expected['pid']
            return owner, release_write, message
        except BaseException:
            os.kill(owner, signal.SIGKILL)
            os.waitpid(owner, 0)
            os.close(release_write)
            raise
        finally:
            os.close(ready_read)

    owner, release, identity = controlled_owner('nested-live')
    ordinary = None
    try:
        ordinary = subprocess.Popen([proof.RESOLVCONF, '-a', 'ordinary-contender'],
                                     stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                     env={'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'LANG': 'C'})
        ordinary.stdin.write(b'nameserver 192.0.2.55\n')
        ordinary.stdin.close()
        time.sleep(0.15)
        assert ordinary.poll() is None, 'ordinary caller stole nested owner lock'
        assert int((lock / 'pid').read_text()) == identity['inner_pid']
        assert not (keys / 'ordinary-contender').exists()
        ordinary.kill()
        ordinary.wait(timeout=1)
        os.write(release, b'G')
        _pid, status = os.waitpid(owner, 0)
        owner = None
        assert os.waitstatus_to_exitcode(status) == 0
        assert (keys / 'nested-live').exists() and not lock.exists()
        record('ordinary_writer_respects_nested_host_pid_lock', identity=identity)
    finally:
        os.close(release)
        if ordinary is not None:
            if ordinary.poll() is None:
                ordinary.kill()
                ordinary.wait(timeout=1)
            for stream in (ordinary.stdin, ordinary.stdout, ordinary.stderr):
                stream.close()
        if owner is not None:
            os.kill(owner, signal.SIGKILL)
            os.waitpid(owner, 0)

    def killed_owner(key):
        owner, release, identity = controlled_owner(key)
        os.close(release)
        os.kill(owner, signal.SIGKILL)
        os.waitpid(owner, 0)
        deadline = time.monotonic() + 1
        while Path(f"/proc/{identity['inner_pid']}").exists():
            if time.monotonic() >= deadline:
                raise AssertionError('nested init survived owner death')
            try:
                while os.waitpid(-1, os.WNOHANG)[0]:
                    pass
            except ChildProcessError:
                pass
            time.sleep(0.005)
        assert int((lock / 'pid').read_text()) == identity['inner_pid']
        assert not (keys / key).exists()
        return identity

    identity = killed_owner('killed-before-ordinary')
    proof.guards.checked([proof.RESOLVCONF, '-a', 'ordinary-recovery'], input='nameserver 192.0.2.56\n')
    assert (keys / 'ordinary-recovery').exists() and not lock.exists()
    record('ordinary_writer_recovers_killed_nested_host_pid', identity=identity)
    identity = killed_owner('killed-before-nested')
    native('nested-recovery')
    assert (keys / 'nested-recovery').exists() and not lock.exists()
    record('nested_writer_recovers_killed_nested_host_pid', identity=identity)

    original_proc = os.open('/proc', os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    non_proc = os.open('/run', os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    baseline = {path.name: path.read_bytes() for path in keys.iterdir()}
    resolver_before = Path('/etc/resolv.conf').read_bytes()
    invalid = [
        {'OPENRESOLV_HOST_PID': '1'},
        {'OPENRESOLV_HOST_PROC_FD': str(original_proc)},
        {'OPENRESOLV_HOST_PID': '', 'OPENRESOLV_HOST_PROC_FD': ''},
        {'OPENRESOLV_HOST_PID': '01', 'OPENRESOLV_HOST_PROC_FD': str(original_proc)},
        {'OPENRESOLV_HOST_PID': '0', 'OPENRESOLV_HOST_PROC_FD': str(original_proc)},
        {'OPENRESOLV_HOST_PID': '-1', 'OPENRESOLV_HOST_PROC_FD': str(original_proc)},
        {'OPENRESOLV_HOST_PID': '2147483648', 'OPENRESOLV_HOST_PROC_FD': str(original_proc)},
        {'OPENRESOLV_HOST_PID': '1', 'OPENRESOLV_HOST_PROC_FD': '2147483647'},
        {'OPENRESOLV_HOST_PID': '1', 'OPENRESOLV_HOST_PROC_FD': str(non_proc)},
        {'OPENRESOLV_HOST_PID': '1', 'OPENRESOLV_HOST_PROC_FD': str(original_proc)},
    ]
    try:
        for index, extra in enumerate(invalid):
            guard()
            environment = {'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'LANG': 'C', **extra}
            completed = subprocess.run([proof.RESOLVCONF, '-a', f'invalid-{index}'],
                input='nameserver 192.0.2.57\n', capture_output=True, text=True, timeout=1,
                pass_fds=(original_proc, non_proc), env=environment)
            assert completed.returncode != 0, (index, completed.stdout)
            assert not lock.exists()
            assert baseline == {path.name: path.read_bytes() for path in keys.iterdir()}
            assert resolver_before == Path('/etc/resolv.conf').read_bytes()
    finally:
        os.close(original_proc)
        os.close(non_proc)
    record('invalid_bridge_context_refused_before_mutation', invalid_cases=len(invalid))
    proof.emit({'phase': 'complete', 'cases': cases})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--worker')
    parser.add_argument('--resolvconf', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.worker:
        try:
            worker(json.loads(args.worker), args.resolvconf)
        except BaseException:
            proof.emit({'phase': 'failed', 'traceback': traceback.format_exc()})
            raise
        return
    if args.output is None or args.output.exists():
        parser.error('--output must name a new directory')
    args.resolvconf = args.resolvconf.resolve(strict=True)
    sources = [SCRIPT, proof.SCRIPT, proof.GUARDS, args.resolvconf,
               proof.LIBRARY / 'privacyctl_runtime/network.py', Path('/usr/lib/resolvconf/libc')]
    hashes = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in sources}
    private_before, private_after = {}, {}
    before = proof.snapshot_host(private_before)
    privilege = [] if os.geteuid() == 0 else ['doas', '-n']
    started = time.monotonic()
    completed = subprocess.run([*privilege, '/usr/bin/timeout', '-k', '2', '20',
        '/usr/bin/unshare', '--net', '--mount', '--pid', '--fork', '--kill-child=KILL',
        '--propagation', 'unchanged', '/usr/bin/python3', '-I', str(SCRIPT),
        '--worker', json.dumps(before['namespaces']), '--resolvconf', str(args.resolvconf)],
        capture_output=True, text=True, timeout=25)
    after = proof.snapshot_host(private_after)
    messages = [json.loads(line) for line in completed.stdout.splitlines()]
    namespaces = next((x['namespaces'] for x in messages if x.get('phase') == 'namespace_ready'), {})
    cleanup = json.loads(proof.guards.checked([*privilege, '/usr/bin/python3', '-I', str(proof.GUARDS),
        '--audit-cleanup', json.dumps(list(namespaces.values()))]).stdout)
    evidence = {'schema_version': 1, 'worker_returncode': completed.returncode,
                'messages': messages, 'worker_stderr': completed.stderr,
                'host_state_unchanged': before == after,
                'host_checks': {key: before[key] == after[key] for key in before},
                'host_address_changed_fields': proof.changed_fields(private_before, private_after),
                'source_sha256': hashes,
                'source_unchanged': hashes == {str(path): hashlib.sha256(path.read_bytes()).hexdigest()
                                              for path in sources}, 'cleanup': cleanup,
                'elapsed_seconds': time.monotonic() - started}
    evidence['status'] = 'passed' if (completed.returncode == 0 and namespaces
        and any(x.get('phase') == 'complete' for x in messages) and before == after
        and evidence['source_unchanged'] and not cleanup['remaining_namespace_members']) else 'failed'
    args.output.mkdir(mode=0o700, parents=True)
    (args.output / 'evidence.json').write_text(json.dumps(evidence, indent=2) + '\n')
    proof.emit({'status': evidence['status'], 'elapsed_seconds': evidence['elapsed_seconds'],
                'evidence': str(args.output / 'evidence.json')})
    if evidence['status'] != 'passed':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
