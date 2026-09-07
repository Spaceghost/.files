"""Real guardian process lifetimes with private marker files, no host radios."""
import importlib.util
import json
import os
from pathlib import Path
import select
import signal
import subprocess
import sys
import tempfile
import time
import unittest

LIBRARY = Path(__file__).parents[1] / 'root/usr/local/lib'
sys.path.insert(0, str(LIBRARY))
PROGRAM = '''import json,os,sys,time
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from privacyctl_runtime.runner import guarded
root=Path(sys.argv[2])
def log(event):
    with (root/'events').open('a') as f: f.write(json.dumps({'event':event,'pid':os.getpid()})+'\\n')
def child(stop):
    log('ready')
    while not stop(): time.sleep(.01)
    log('stopped')
guarded(child,lambda:log('block'),root)
'''


@unittest.skipUnless(os.geteuid() == 0, 'root-private guardian lock')
class GuardianTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('privacyctl_runtime.runner'),
                             'owner runner not implemented')
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.process = subprocess.Popen([sys.executable,'-I','-S','-c',PROGRAM,
                                         str(LIBRARY),str(self.root)],
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.addCleanup(self.cleanup)
        self.child_fd = None
        self.wait_for('ready')
        self.child = next(x['pid'] for x in self.events() if x['event']=='ready')
        self.child_fd = os.pidfd_open(self.child)

    def events(self):
        try: return [json.loads(x) for x in (self.root/'events').read_text().splitlines()]
        except FileNotFoundError: return []

    def wait_for(self, event):
        deadline = time.monotonic()+3
        while not any(x['event']==event for x in self.events()):
            if time.monotonic()>=deadline:
                self.fail('guardian event missing: '+event)
            if self.process.poll() is not None:
                self.fail(self.process.communicate()[1].decode())
            time.sleep(.01)

    def cleanup(self):
        if self.process.poll() is None:
            self.process.kill()
        self.process.communicate(timeout=3)
        if self.child_fd is not None:
            if not select.select([self.child_fd],[],[],.5)[0]:
                signal.pidfd_send_signal(self.child_fd,signal.SIGKILL)
            os.close(self.child_fd)

    def test_child_death_causes_guardian_block(self):
        signal.pidfd_send_signal(self.child_fd,signal.SIGKILL)
        self.process.wait(timeout=3)
        self.assertEqual(self.events()[-1], {'event':'block','pid':self.process.pid})

    def test_guardian_death_causes_child_shutdown_and_block(self):
        self.process.kill()
        self.process.wait(timeout=3)
        self.assertTrue(select.select([self.child_fd],[],[],3)[0])
        events=self.events()
        self.assertIn({'event':'stopped','pid':self.child},events)
        self.assertEqual(events[-1], {'event':'block','pid':self.child})

    def test_normal_stop_blocks_before_child_cleanup(self):
        self.process.terminate()
        self.process.wait(timeout=3)
        events=self.events()
        ready=next(i for i,x in enumerate(events) if x['event']=='ready')
        block=next(i for i,x in enumerate(events) if i>ready and x=={'event':'block','pid':self.process.pid})
        stopped=next(i for i,x in enumerate(events) if x['event']=='stopped')
        self.assertLess(block,stopped)

    def test_second_guardian_cannot_block_or_replace_first(self):
        before=self.events()
        result=subprocess.run([sys.executable,'-I','-S','-c',PROGRAM,str(LIBRARY),str(self.root)],
                              stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=3)
        self.assertNotEqual(result.returncode,0)
        self.assertEqual(self.events(),before)
        self.assertIsNone(self.process.poll())

    def test_inherited_sigchld_ignore_cannot_autoreap_owner_before_pidfd(self):
        program = '''import os,signal,sys,time
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from privacyctl_runtime.runner import guarded
signal.signal(signal.SIGCHLD,signal.SIG_IGN)
real_pidfd=os.pidfd_open
def delayed_pidfd(pid):
    time.sleep(.1)
    return real_pidfd(pid)
os.pidfd_open=delayed_pidfd
def forbidden_numeric_kill(*args):
    raise RuntimeError('numeric PID fallback after potential auto-reap')
os.kill=forbidden_numeric_kill
assert guarded(lambda stop:None,lambda:None,Path(sys.argv[2]))==0
assert signal.getsignal(signal.SIGCHLD)==signal.SIG_IGN
'''
        result = subprocess.run([sys.executable,'-I','-S','-c',program,str(LIBRARY),str(self.root/'sigchld')],
                                stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=3)
        self.assertEqual(result.returncode,0,result.stderr.decode())


if __name__=='__main__': unittest.main()
