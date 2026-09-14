"""What the strip says you are looking at, past whatever the title claims."""
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import time
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


class RepositoryTests(unittest.TestCase):
    """Both systems, both answers: which branch, and how the checkout stands."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        import window_context
        self.context = window_context
        self.context._STATUS.clear()
        self.context._DETAIL.clear()
        self.context._FACTS.clear()
        self.context._CACHE.clear()

    def fossil_checkout(self, branch='trunk', newer=0, unsent=0, remote=True):
        """A Fossil checkout with only the tables this reads, and real values."""
        checkout = self.root / 'ckout'
        checkout.mkdir()
        repository = self.root / 'project.fossil'
        with sqlite3.connect(repository) as db:
            db.execute('CREATE TABLE tag(tagid INTEGER PRIMARY KEY, tagname TEXT)')
            db.execute('CREATE TABLE tagxref(tagid INT, rid INT, value TEXT)')
            db.execute('CREATE TABLE event(type TEXT, mtime REAL, objid INT)')
            db.execute('CREATE TABLE unsent(rid INT)')
            db.execute('CREATE TABLE config(name TEXT, value)')
            db.execute("INSERT INTO tag VALUES (8, 'branch')")
            db.execute('INSERT INTO tagxref VALUES (8, 41, ?)', (branch,))
            db.execute("INSERT INTO event VALUES ('ci', 100.0, 41)")
            for index in range(newer):
                db.execute("INSERT INTO event VALUES ('ci', ?, ?)", (101.0 + index, 50 + index))
                db.execute('INSERT INTO tagxref VALUES (8, ?, ?)', (50 + index, branch))
            for index in range(unsent):
                db.execute("INSERT INTO event VALUES ('ci', ?, ?)", (99.0 - index, 70 + index))
                db.execute('INSERT INTO unsent VALUES (?)', (70 + index,))
            if remote:
                db.execute("INSERT INTO config VALUES ('last-sync-url', 'https://example.invalid')")
        with sqlite3.connect(checkout / '.fslckout') as db:
            db.execute('CREATE TABLE vvar(name TEXT PRIMARY KEY, value)')
            db.execute("INSERT INTO vvar VALUES ('checkout', '41')")
            db.execute('INSERT INTO vvar VALUES (?, ?)', ('repository', str(repository)))
        return checkout

    def test_fossil_answers_from_its_own_sqlite_without_running_fossil(self):
        """The branch used to cost a fork; it is two indexed reads instead."""
        checkout = self.fossil_checkout(branch='alpine-oldbook', newer=2, unsent=3)
        facts = self.context.fossil_facts(str(checkout))
        self.assertEqual(facts['branch'], 'alpine-oldbook')
        self.assertEqual(facts['behind'], 2)
        self.assertEqual(facts['ahead'], 3)
        found = self.context.repository(str(checkout), blocking=True)
        self.assertEqual((found['kind'], found['branch']), ('fossil', 'alpine-oldbook'))
        # Named from cache afterwards, so the drawing thread never reads SQLite.
        self.assertEqual(self.context.repository(str(checkout))['branch'], 'alpine-oldbook')

    def test_unsent_check_ins_only_mean_ahead_where_there_is_a_remote(self):
        checkout = self.fossil_checkout(unsent=4, remote=False)
        self.assertIsNone(self.context.fossil_facts(str(checkout))['ahead'])

    def test_an_unreadable_fossil_database_drops_the_answer_rather_than_raising(self):
        checkout = self.root / 'broken'
        checkout.mkdir()
        (checkout / '.fslckout').write_text('not a database at all')
        self.assertEqual(self.context.fossil_facts(str(checkout)),
                         {'branch': None, 'ahead': None, 'behind': None})

    def test_git_reports_dirt_and_divergence_from_one_porcelain_call(self):
        original = self.context.subprocess.run
        self.addCleanup(setattr, self.context.subprocess, 'run', original)
        recorded = []

        class Result:
            returncode = 0
            stdout = ('# branch.oid abc123\n# branch.head work\n'
                      '# branch.ab +2 -5\n1 .M N... 100644 100644 100644 a b file.py\n')

        def fake(command, **kwargs):
            recorded.append(command)
            return Result()

        self.context.subprocess.run = fake
        self.assertEqual(self.context.git_status('/tmp'),
                         {'dirty': True, 'ahead': 2, 'behind': 5})
        self.assertEqual(recorded[0][:3], ['git', 'status', '--porcelain=v2'])

    def test_a_worktree_still_finds_the_branch_through_its_git_file(self):
        real = self.root / 'main/.git'
        real.mkdir(parents=True)
        (real / 'HEAD').write_text('ref: refs/heads/feature\n')
        tree = self.root / 'tree'
        tree.mkdir()
        (tree / '.git').write_text('gitdir: ' + str(real) + '\n')
        self.assertEqual(self.context.repository(str(tree))['branch'], 'feature')

    def test_the_expensive_half_stays_off_the_drawing_thread(self):
        """A caption asking for status gets the last answer, not a subprocess."""
        calls = []
        original = self.context.schedule
        self.addCleanup(setattr, self.context, 'schedule', original)
        self.context.schedule = lambda key, target, *arguments: calls.append(key)
        found = {'kind': 'git', 'root': str(self.root), 'branch': 'work'}
        self.assertEqual(self.context.status(found), {})
        self.assertEqual(calls, [('status', str(self.root))])
        self.context._STATUS[str(self.root)] = (time.monotonic(), {'dirty': True})
        self.assertEqual(self.context.status(found), {'dirty': True})

    def test_a_flat_battery_sheds_every_answer_that_costs_a_process(self):
        import power_source
        original = power_source.posture
        self.addCleanup(setattr, power_source, 'posture', original)
        power_source.posture = lambda root=None: 'battery-critical'
        found = {'kind': 'fossil', 'root': str(self.root), 'branch': 'trunk'}
        self.assertEqual(self.context.status(found), {})
        self.assertEqual(self.context.detail(1, 2), {})
        checkout = self.fossil_checkout()
        self.assertIsNone(self.context.repository(str(checkout), blocking=True)['branch'])
        # And a repository is asked less often on a battery than on the cord.
        self.assertGreater(self.context.status_interval('battery'),
                           self.context.status_interval('mains'))


class TabTests(unittest.TestCase):
    """Real tab sets only: sway's own containers and tmux's window list."""

    def setUp(self):
        import window_context
        self.context = window_context

    def test_tabs_say_where_you_are_and_name_only_the_others(self):
        text = self.context.tab_text({'source': 'tmux', 'index': 2, 'count': 4,
                                      'names': ['edit', 'shell', 'logs', 'mail']})
        self.assertEqual(text, self.context.GLYPHS['tabs'] + ' 2/4 edit, logs, mail')

    def test_a_window_that_is_alone_is_not_a_tab_set(self):
        self.assertEqual(self.context.tab_text({'index': 1, 'count': 1, 'names': ['only']}), '')
        self.assertEqual(self.context.tab_text(None), '')

    def test_a_long_tab_name_is_shortened_rather_than_left_to_the_ellipsis(self):
        text = self.context.tab_text({'index': 1, 'count': 2,
                                      'names': ['here', 'an extremely long window name']})
        self.assertIn('…', text)
        self.assertLess(len(text), 40)

    def test_sways_tabbed_containers_are_read_from_the_tree(self):
        import decoration_actions
        children = [{'id': 4, 'app_id': 'firefox', 'name': 'Rice Board'},
                    {'id': 5, 'app_id': 'foot', 'name': 'notes'}]
        container = {'id': 3, 'layout': 'tabbed', 'nodes': children, 'focus': [5, 4]}
        tabs = decoration_actions.container_tabs(container, children[1])
        self.assertEqual((tabs['index'], tabs['count'], tabs['names']),
                         (2, 2, ['Rice Board', 'notes']))
        self.assertIsNone(decoration_actions.container_tabs(
            dict(container, layout='splith'), children[1]))

    def test_the_innermost_tabbed_container_is_the_one_the_window_is_in(self):
        import decoration_actions
        leaf = {'id': 9, 'app_id': 'foot', 'name': 'inner', 'rect': {}}
        other = {'id': 10, 'app_id': 'foot', 'name': 'beside', 'rect': {}}
        inner = {'id': 8, 'layout': 'tabbed', 'nodes': [leaf, other], 'focus': [9, 10]}
        outer = {'id': 7, 'type': 'workspace', 'name': '2: Lab', 'layout': 'tabbed',
                 'nodes': [inner], 'focus': [8], 'floating_nodes': []}
        tree = {'nodes': [{'type': 'output', 'name': 'eDP-1', 'nodes': [outer], 'focus': [7]}]}
        context = decoration_actions.output_contexts(tree)['eDP-1']
        self.assertEqual(context['tabs']['names'], ['inner', 'beside'])


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
        glyph = self.context.GLYPHS['branch']
        self.assertEqual(line, f'1 Ghost · foot › tmux › nvim · ~/.files {glyph} alpine-oldbook')

    def test_every_other_window_keeps_the_title_it_chose(self):
        line = self.context.strip_caption({'workspace': '2: Orbit', 'title': 'Pithos',
                                           'provenance': {}})
        self.assertEqual(line, '2 Orbit · Pithos')

    def test_an_empty_workspace_still_says_where_it_is(self):
        self.assertEqual(self.context.strip_caption({'workspace': '4: Signal'}),
                         'Empty workspace · 4 Signal')

    def test_the_repository_says_which_system_which_branch_and_how_it_stands(self):
        glyphs = self.context.GLYPHS
        line = self.context.strip_caption({'workspace': '', 'provenance': {
            'chain': ['ghostty'], 'directory': '~/.files',
            'repository': {'kind': 'fossil', 'branch': 'alpine-oldbook',
                           'dirty': True, 'ahead': 2, 'behind': 0}}})
        self.assertEqual(line, f"ghostty · ~/.files {glyphs['fossil']} "
                               f"{glyphs['branch']} alpine-oldbook {glyphs['dirty']} "
                               f"{glyphs['ahead']}2")
        clean = self.context.strip_caption({'workspace': '', 'provenance': {
            'chain': ['ghostty'], 'directory': '~/src/web',
            'repository': {'kind': 'git', 'branch': 'main', 'dirty': False}}})
        self.assertIn(glyphs['clean'], clean)
        self.assertIn(glyphs['git'], clean)

    def test_the_tab_list_is_the_first_thing_the_strip_gives_up(self):
        """Narrower and narrower: names, then tabs, then standing, then place."""
        record = {'chain': ['ghostty', 'nvim'], 'directory': '~/.files',
                  'repository': {'kind': 'git', 'branch': 'alpine-oldbook', 'dirty': True},
                  'tabs': {'index': 1, 'count': 3, 'names': ['edit', 'shell', 'logs']}}
        roles = lambda budget: [role for role, _ in
                                self.context.segments(record, '10 Strata', budget)]
        self.assertEqual(roles(None), ['workspace', 'chain', 'place', 'tabs'])
        full = self.context.caption(record, '10 Strata')
        wide = self.context.caption(record, '10 Strata', len(full))
        self.assertEqual(wide, full)
        narrower = self.context.caption(record, '10 Strata', len(full) - 6)
        self.assertNotIn('shell', narrower)
        self.assertIn('1/3', narrower)
        # Every narrower line is the start of a wider one: segments leave in a
        # fixed order and never come back in a different arrangement.
        ladder = [roles(budget) for budget in range(len(full), 0, -1)]
        for tighter, wider in zip(ladder[1:], ladder):
            self.assertEqual(tighter, wider[:len(tighter)])
        self.assertIn(['workspace', 'chain', 'place'], ladder)
        self.assertEqual(ladder[-1], ['workspace', 'chain'])
        # Whatever happens, the caption still answers where you are and what
        # you are in.
        self.assertIn('10 Strata', self.context.caption(record, '10 Strata', 1))
        self.assertIn('nvim', self.context.caption(record, '10 Strata', 1))

    def test_sway_tabs_reach_the_strip_for_windows_that_are_not_terminals(self):
        line = self.context.strip_caption({
            'workspace': '2: Lab', 'title': 'Rice Board',
            'tabs': {'source': 'sway', 'index': 1, 'count': 2, 'names': ['Rice Board', 'notes']}})
        self.assertEqual(line, "2 Lab · Rice Board · "
                               + self.context.GLYPHS['tabs'] + ' 1/2 notes')

    def test_powerline_is_one_ground_per_segment_and_an_arrow_between(self):
        palette = {'accent': '#dca7ff', 'background_hard': '#13091f', 'surface': '#261631',
                   'foreground': '#eaddf5', 'muted': '#816b91'}
        found = self.context.strip_markup(
            {'workspace': '1: Ghost', 'title': 'Pithos & friends'}, palette)
        self.assertIn('background="#dca7ff"', found)
        self.assertIn(self.context.POWERLINE, found)
        # It opens with the first ground and closes into nothing, like the
        # prompt's and the status bars' chains.
        self.assertTrue(found.startswith('<span foreground="#dca7ff">' + self.context.POWERLINE))
        self.assertTrue(found.endswith(self.context.POWERLINE + '</span>'))
        # The arrow between two segments leaves one colour and enters the next.
        self.assertIn('<span foreground="#dca7ff" background="#261631">', found)
        # Markup is markup: a title with an ampersand may not break the label.
        self.assertIn('Pithos &amp; friends', found)
        self.assertNotIn('& friends', found)

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
