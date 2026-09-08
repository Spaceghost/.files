#!/usr/bin/env python3
"""Private reproduction of openresolv PID-file lock namespace semantics."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

SCRIPT = Path(__file__).resolve()
spec = importlib.util.spec_from_file_location('applier_proof', SCRIPT.with_name('verify_network_applier.py'))
proof = importlib.util.module_from_spec(spec)
spec.loader.exec_module(proof)


def worker(host, stock_resolvconf=None):
    expected = proof.prepare_private(host, stock_resolvconf)
    lock = Path('/run/resolvconf/lock')
    holder = subprocess.Popen(['/bin/sleep', '30'])
    try:
        lock.mkdir()
        (lock / 'pid').write_text(str(holder.pid) + '\n')
        proof.guards.guard_private(host, expected)
        completed = subprocess.run(['/usr/bin/timeout', '-k', '1', '2', '/usr/bin/unshare',
            '--mount', '--propagation', 'private', '--pid', '--fork', '--kill-child=KILL',
            '--mount-proc', proof.RESOLVCONF, '-a', 'private0'],
            input='nameserver 192.0.2.53\n', capture_output=True, text=True, timeout=4)
        proof.emit({'phase': 'live_outer_lock', 'holder_alive': holder.poll() is None,
                    'holder_pid': holder.pid, 'returncode': completed.returncode,
                    'stderr': completed.stderr, 'lock_survived': lock.exists(),
                    'provider_written': Path('/run/resolvconf/keys/private0').exists()})
        assert holder.poll() is None and completed.returncode == 0
        assert not lock.exists() and Path('/run/resolvconf/keys/private0').exists()
        if lock.exists():
            (lock / 'pid').unlink()
            lock.rmdir()
        lock.mkdir()
        (lock / 'pid').write_text('1\n')
        proof.guards.guard_private(host, expected)
        completed = subprocess.run(['/usr/bin/timeout', '-k', '1', '2', '/usr/bin/unshare',
            '--mount', '--propagation', 'private', '--pid', '--fork', '--kill-child=KILL',
            '--mount-proc', proof.RESOLVCONF, '-a', 'private1'],
            input='nameserver 192.0.2.54\n', capture_output=True, text=True, timeout=4)
        proof.emit({'phase': 'stale_inner_pid1_lock', 'returncode': completed.returncode,
                    'stderr': completed.stderr, 'lock_survived': lock.exists(),
                    'provider_written': Path('/run/resolvconf/keys/private1').exists()})
        assert completed.returncode == -9 and lock.exists()
        assert not Path('/run/resolvconf/keys/private1').exists()
    finally:
        holder.terminate()
        holder.wait(timeout=2)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--worker')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--resolvconf', type=Path,
                        help='trusted archived stock script for the private negative control')
    args = parser.parse_args()
    if args.worker:
        worker(json.loads(args.worker), args.resolvconf)
        return
    if args.output is None or args.output.exists():
        parser.error('--output must name a new directory')
    before = proof.snapshot_host()
    sources = [SCRIPT, proof.SCRIPT, proof.GUARDS, Path(proof.RESOLVCONF),
               Path('/usr/lib/resolvconf/libc')]
    if args.resolvconf is not None:
        args.resolvconf = args.resolvconf.resolve(strict=True)
        sources.append(args.resolvconf)
    hashes = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in sources}
    privilege = [] if os.geteuid() == 0 else ['doas', '-n']
    command = [*privilege, '/usr/bin/timeout', '-k', '2', '15',
        '/usr/bin/unshare', '--net', '--mount', '--pid', '--fork', '--kill-child=KILL',
        '--propagation', 'unchanged', '/usr/bin/python3', '-I', str(SCRIPT),
        '--worker', json.dumps(before['namespaces'])]
    if args.resolvconf is not None:
        command += ['--resolvconf', str(args.resolvconf)]
    completed = subprocess.run(command, capture_output=True, text=True, timeout=20)
    after = proof.snapshot_host()
    messages = [json.loads(line) for line in completed.stdout.splitlines()]
    ns = next((x['namespaces'] for x in messages if x.get('phase') == 'namespace_ready'), {})
    cleanup = json.loads(proof.guards.checked([*privilege, '/usr/bin/python3', '-I', str(proof.GUARDS),
        '--audit-cleanup', json.dumps(list(ns.values()))]).stdout)
    evidence = {'worker_returncode': completed.returncode, 'messages': messages,
                'worker_stderr': completed.stderr, 'host_state_unchanged': before == after,
                'source_sha256': hashes,
                'source_unchanged': hashes == {str(path): hashlib.sha256(path.read_bytes()).hexdigest()
                                              for path in sources}, 'cleanup': cleanup}
    args.output.mkdir(mode=0o700, parents=True)
    (args.output / 'evidence.json').write_text(json.dumps(evidence, indent=2) + '\n')
    proof.emit(evidence)
    assert before == after and not cleanup['remaining_namespace_members']
    assert evidence['source_unchanged']
    assert completed.returncode == 0


if __name__ == '__main__':
    main()
