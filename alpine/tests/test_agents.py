"""Agent sessions must be tmux-contained and safe to build from configuration."""
import json
from pathlib import Path
import shlex
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'alpine/desktop/.local/lib/oldbook'))
import agent_launcher as launcher

LIVE = REPO / 'alpine/desktop/.config/oldbook/agents.json'


def config(**extra):
    document = {
        'session_prefix': 'agent',
        'terminal': ['foot', '--title={title}', '-e'],
        'workdirs': ['~'],
        'agents': [
            {'id': 'codex', 'title': 'Codex', 'command': ['codex']},
            {'id': 'far', 'title': 'Far', 'host': 'alienware', 'command': ['ollama', 'run', 'x']},
        ],
    }
    document.update(extra)
    return document


class ConfigTests(unittest.TestCase):
    def write(self, document):
        handle = tempfile.NamedTemporaryFile('w', suffix='.json', delete=False)
        json.dump(document, handle)
        handle.close()
        self.addCleanup(lambda: Path(handle.name).unlink(missing_ok=True))
        return handle.name

    def test_live_configuration_is_valid(self):
        document = launcher.load_config(LIVE)
        identifiers = {agent['id'] for agent in launcher.enabled_agents(document)}
        self.assertIn('codex', identifiers)
        self.assertIn('claude', identifiers)
        self.assertTrue(any(agent.get('host') == 'alienware'
                            for agent in launcher.enabled_agents(document)),
                        'the tailnet box should be reachable from the launcher')

    def test_rejects_duplicate_identifiers(self):
        document = config()
        document['agents'].append(dict(document['agents'][0]))
        with self.assertRaises(ValueError):
            launcher.load_config(self.write(document))

    def test_rejects_a_command_that_is_not_a_list_of_strings(self):
        for command in ('codex', [], [''], ['ok', 3]):
            document = config()
            document['agents'][0]['command'] = command
            with self.assertRaises(ValueError):
                launcher.load_config(self.write(document))

    def test_rejects_an_unusable_host(self):
        document = config()
        document['agents'][1]['host'] = 'alienware; rm -rf /'
        with self.assertRaises(ValueError):
            launcher.load_config(self.write(document))

    def test_disabled_agents_are_hidden(self):
        document = config()
        document['agents'][0]['enabled'] = False
        self.assertEqual([agent['id'] for agent in launcher.enabled_agents(document)], ['far'])


class WorkdirTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='oldbook-agents-test-')
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        (self.home / 'src/one').mkdir(parents=True)
        (self.home / 'src/two').mkdir(parents=True)
        (self.home / 'src/afile').write_text('not a directory')

    def test_globs_expand_to_directories_only(self):
        document = config(workdirs=['~/src/*', '~'])
        found = launcher.expand_workdirs(document, home=self.home)
        names = [path.name for path in found]
        self.assertIn('one', names)
        self.assertIn('two', names)
        self.assertNotIn('afile', names)

    def test_missing_directories_are_skipped_without_error(self):
        document = config(workdirs=['~/nope', '~'])
        self.assertEqual(launcher.expand_workdirs(document, home=self.home),
                         [self.home.resolve()])

    def test_short_path_uses_a_tilde(self):
        self.assertEqual(launcher.short_path(self.home / 'src', home=self.home), '~/src')


class CommandTests(unittest.TestCase):
    def test_session_names_do_not_collide(self):
        document = config()
        self.assertEqual(launcher.session_name(document, 'codex', set()), 'agent-codex')
        self.assertEqual(launcher.session_name(document, 'codex', {'agent-codex'}),
                         'agent-codex-2')

    def test_local_agent_runs_in_tmux_with_its_working_directory(self):
        document = config()
        command = launcher.new_session_command(
            document, document['agents'][0], 'agent-codex', '/tmp/work')
        self.assertEqual(command[:5], ['tmux', 'new-session', '-d', '-s', 'agent-codex'])
        self.assertIn('-c', command)
        self.assertEqual(command[command.index('-c') + 1], '/tmp/work')
        self.assertEqual(command[-1], 'codex')

    def test_remote_agent_keeps_tmux_local_and_ssh_inside_it(self):
        document = config()
        command = launcher.new_session_command(
            document, document['agents'][1], 'agent-far', '/srv/data')
        self.assertEqual(command[:2], ['tmux', 'new-session'])
        self.assertIn('ssh', command)
        self.assertEqual(command[command.index('ssh') + 2], 'alienware')
        self.assertIn("cd /srv/data && exec ollama run x", command[-1])

    def test_a_hostile_directory_cannot_break_out_of_the_remote_command(self):
        script = launcher.remote_script(['codex'], "/tmp/x'; rm -rf ~; echo '")
        self.assertTrue(script.startswith('cd '))
        # Everything before the fixed separator must be a single quoted word.
        directory = script[len('cd '):script.index(' && exec ')]
        self.assertEqual(shlex.split(directory), ["/tmp/x'; rm -rf ~; echo '"])

    def test_a_shell_variable_still_expands_on_the_far_side(self):
        self.assertEqual(launcher.remote_script(['$SHELL', '-l'], None), 'exec $SHELL -l')

    def test_attach_command_opens_the_terminal_on_the_session(self):
        document = config()
        command = launcher.attach_command(document, 'agent-codex', 'Codex')
        self.assertEqual(command, ['foot', '--title=Codex', '-e',
                                   'tmux', 'attach-session', '-t', 'agent-codex'])


class SessionListingTests(unittest.TestCase):
    def test_parses_the_tab_separated_listing(self):
        output = 'agent-codex\t2\t1\t/home/jack\nother\t1\t0\t/tmp\n'
        self.assertEqual(launcher.parse_sessions(output), [
            {'name': 'agent-codex', 'windows': '2', 'attached': True, 'path': '/home/jack'},
            {'name': 'other', 'windows': '1', 'attached': False, 'path': '/tmp'},
        ])

    def test_ignores_malformed_rows(self):
        self.assertEqual(launcher.parse_sessions('broken\nalso broken\t1\n'), [])


if __name__ == '__main__':
    unittest.main()
