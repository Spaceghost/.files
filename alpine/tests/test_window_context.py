"""What the strip says you are looking at, past whatever the title claims."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[2]
LIBRARY = REPO / 'alpine/desktop/.local/lib/oldbook'
sys.path.insert(0, str(LIBRARY))


def fake_proc(root, processes):
    """A /proc with only the files this reads: comm, task children and cwd."""
    root.mkdir(parents=True, exist_ok=True)
    for pid, (name, kids, cwd) in processes.items():
        entry = root / str(pid)
        (entry / 'task' / str(pid)).mkdir(parents=True)
        (entry / 'comm').write_text(name + '\n')
        (entry / 'task' / str(pid) / 'children').write_text(' '.join(str(k) for k in kids))
        if cwd is not None:
            (entry / 'cwd').symlink_to(cwd)
    return root


class ChainTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        import window_context
        self.context = window_context
        self.context._CACHE.clear()

    def proc(self, processes):
        os.environ['OLDBOOK_PROC_ROOT'] = str(fake_proc(self.root / 'proc', processes))
        self.context.PROC = Path(os.environ['OLDBOOK_PROC_ROOT'])
        self.addCleanup(os.environ.pop, 'OLDBOOK_PROC_ROOT', None)

    def test_a_shell_is_scaffolding_until_it_is_the_only_thing_running(self):
        self.assertEqual(self.context.readable(['foot', 'zsh', 'nvim']), ['foot', 'nvim'])
        self.assertEqual(self.context.readable(['foot', 'zsh']), ['foot'])
        self.assertEqual(self.context.readable(['zsh']), ['zsh'])

    def test_nobody_says_tmux_client_out_loud(self):
        self.assertEqual(self.context.readable(['foot', 'tmux: client', 'nvim']),
                         ['foot', 'tmux', 'nvim'])

    def test_the_walk_follows_the_process_the_user_just_started(self):
        work = self.root / 'work'
        work.mkdir()
        self.proc({10: ('ghostty', [11, 12], str(work)),
                   11: ('some-helper', [], str(work)),
                   12: ('zsh', [13], str(work)),
                   13: ('nvim', [], str(work))})
        self.assertEqual(self.context.readable(
            [self.context.comm(pid) for pid in self.context.descend(10)]),
            ['ghostty', 'nvim'])

    def test_a_directory_inside_the_kernels_own_filesystems_is_no_answer(self):
        """A browser content process answers cwd with /proc, truthfully and uselessly."""
        self.proc({20: ('firefox', [], '/proc/20/fdinfo'), 21: ('gone', [], '/does/not/exist')})
        self.assertEqual(self.context.working_directory(20), '')
        self.assertEqual(self.context.working_directory(21), '')

    def test_only_terminals_are_walked(self):
        self.proc({30: ('python3', [], str(self.root))})
        self.assertEqual(self.context.describe(30, terminal=False), {})
        self.assertTrue(self.context.describe(30, terminal=True))

    def test_a_vanished_process_drops_out_rather_than_raising(self):
        self.proc({})
        self.assertEqual(self.context.comm(9999), '')
        self.assertEqual(self.context.children(9999), [])
        self.assertEqual(self.context.working_directory(9999), '')

    def test_git_head_names_the_branch_without_running_git(self):
        checkout = self.root / 'checkout'
        (checkout / '.git').mkdir(parents=True)
        (checkout / '.git/HEAD').write_text('ref: refs/heads/alpine-oldbook\n')
        self.assertEqual(self.context.branch(str(checkout)), 'alpine-oldbook')
        nested = checkout / 'deep/inside'
        nested.mkdir(parents=True)
        self.assertEqual(self.context.branch(str(nested)), 'alpine-oldbook')
        (checkout / '.git/HEAD').write_text('9f8e7d6c5b4a3928170615243342516070819293\n')
        self.assertEqual(self.context.branch(str(checkout)), '9f8e7d6c5')

    def test_a_directory_in_no_repository_simply_has_no_branch(self):
        plain = self.root / 'plain'
        plain.mkdir()
        self.assertIsNone(self.context.branch(str(plain)))


class CaptionTests(unittest.TestCase):
    def setUp(self):
        import window_context
        self.context = window_context

    def test_the_workspace_identity_drops_the_live_window_hint(self):
        for name, expected in (('10: Strata · ✦ Claude', '10 Strata'), ('3: Lab', '3 Lab'),
                               ('Ghost', 'Ghost'), ('', '')):
            with self.subTest(name=name):
                self.assertEqual(self.context.workspace_label(name), expected)

    def test_a_terminal_says_what_is_running_instead_of_its_own_title(self):
        line = self.context.strip_caption({
            'workspace': '1: Ghost', 'title': '~',
            'provenance': {'chain': ['foot', 'tmux', 'nvim'],
                           'directory': '~/.files', 'branch': 'alpine-oldbook'}})
        self.assertEqual(line, '1 Ghost · foot › tmux › nvim · ~/.files (alpine-oldbook)')

    def test_every_other_window_keeps_the_title_it_chose(self):
        line = self.context.strip_caption({'workspace': '2: Orbit', 'title': 'Pithos',
                                           'provenance': {}})
        self.assertEqual(line, '2 Orbit · Pithos')

    def test_an_empty_workspace_still_says_where_it_is(self):
        self.assertEqual(self.context.strip_caption({'workspace': '4: Signal'}),
                         'Empty workspace · 4 Signal')

    def test_a_branchless_directory_is_shown_without_empty_brackets(self):
        line = self.context.strip_caption({
            'workspace': '', 'provenance': {'chain': ['ghostty'], 'directory': '/tmp',
                                            'branch': None}})
        self.assertEqual(line, 'ghostty · /tmp')


class LadderTests(unittest.TestCase):
    def test_the_costly_half_is_on_the_power_ladder(self):
        """The chain is plain /proc reads; asking tmux and fossil is not."""
        import power_source
        self.assertEqual(power_source.LADDER['window-context-detail'], 'battery-low')
        self.assertTrue(power_source.allows('window-context-detail', 'battery'))
        self.assertFalse(power_source.allows('window-context-detail', 'battery-critical'))


if __name__ == '__main__':
    unittest.main()
