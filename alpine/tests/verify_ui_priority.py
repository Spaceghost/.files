#!/usr/bin/python3 -I
"""Private process verification: doas python3 -I alpine/tests/verify_ui_priority.py.

Only this short-lived verifier changes priority. No desktop PID is targeted.
"""
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys


def snapshot(helper):
    return {'nice': os.getpriority(os.PRIO_PROCESS, 0), 'policy': helper['scheduler_policy'](0)}


def main():
    if os.geteuid() != 0:
        sys.exit('Run this private scheduling verifier through doas.')
    helper_path = str(Path(__file__).resolve().parents[1] / 'bin/oldbook-ui-priority')
    helper = runpy.run_path(helper_path)
    before = snapshot(helper)
    assert helper['boost_thread'](os.getpid(), -5)
    parent = snapshot(helper)
    read_end, write_end = os.pipe()
    child = os.fork()
    if child == 0:
        os.close(read_end)
        os.write(write_end, json.dumps(snapshot(helper)).encode())
        os.close(write_end)
        os._exit(0)
    os.close(write_end)
    with os.fdopen(read_end) as stream:
        forked = json.load(stream)
    _, status = os.waitpid(child, 0)
    assert status == 0
    launched = json.loads(subprocess.check_output([
        sys.executable, '-I', '-c',
        'import json,os,runpy,sys; h=runpy.run_path(sys.argv[1]); '
        'print(json.dumps({"nice":os.getpriority(os.PRIO_PROCESS,0),'
        '"policy":h["scheduler_policy"](0)}))', helper_path], text=True, timeout=10))
    assert parent == {'nice': -5, 'policy': os.SCHED_OTHER | os.SCHED_RESET_ON_FORK}, parent
    assert forked == {'nice': 0, 'policy': os.SCHED_OTHER}, forked
    assert launched == {'nice': 0, 'policy': os.SCHED_OTHER}, launched
    print(json.dumps({'before': before, 'parent': parent, 'fork_child': forked,
                      'exec_child': launched, 'passed': True}, indent=2))


if __name__ == '__main__':
    main()
