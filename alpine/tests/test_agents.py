"""Agent sessions must be tmux-contained and safe to build from configuration."""
import json
from pathlib import Path
import runpy
import shlex
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

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

    def test_rejects_an_unknown_transport(self):
        document = config()
        document['agents'][1]['transport'] = 'carrier-pigeon'
        with self.assertRaises(ValueError):
            launcher.load_config(self.write(document))

    def test_a_transport_without_a_host_is_refused(self):
        document = config()
        document['agents'][0]['transport'] = 'tailscale-ssh'
        with self.assertRaises(ValueError):
            launcher.load_config(self.write(document))

    def test_the_tailnet_agents_need_no_ssh_keys(self):
        document = launcher.load_config(LIVE)
        remote = [agent for agent in launcher.enabled_agents(document) if agent.get('host')]
        self.assertTrue(remote)
        for agent in remote:
            self.assertEqual(agent.get('transport'), 'tailscale-ssh', agent['id'])

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

    def test_tailscale_ssh_replaces_the_plain_ssh_hop(self):
        document = config()
        document['agents'][1]['transport'] = 'tailscale-ssh'
        command = launcher.new_session_command(
            document, document['agents'][1], 'agent-far', '/srv/data')
        self.assertEqual(command[6:9], ['tailscale', 'ssh', 'alienware'])
        self.assertNotIn('-t', command)
        self.assertIn('cd /srv/data && exec ollama run x', command[-1])

    def test_an_unreachable_host_is_explained_rather_than_retried(self):
        document = config()
        plain = launcher.reachability_hint(document['agents'][1])
        self.assertIn('alienware', plain)
        self.assertIn('port 22', plain)
        document['agents'][1]['transport'] = 'tailscale-ssh'
        tailnet = launcher.reachability_hint(document['agents'][1])
        self.assertIn('tailscale up --ssh', tailnet)

    def test_attach_command_opens_the_terminal_on_the_session(self):
        document = config()
        command = launcher.attach_command(document, 'agent-codex', 'Codex')
        self.assertEqual(command, ['foot', '--title=Codex', '-e',
                                   'tmux', 'attach-session', '-t', 'agent-codex'])


class QuickLaunchTests(unittest.TestCase):
    def test_quick_launch_starts_a_fresh_uncontained_ultra_session(self):
        document = launcher.load_config(LIVE)
        agent = next((a for a in document['agents'] if a['id'] == 'codex-ultra'), None)
        self.assertIsNotNone(agent, 'quick-launch preset is missing')
        name = launcher.session_name(document, agent['id'], {'agent-codex-ultra'})
        command = launcher.new_session_command(document, agent, name, '/tmp/project with spaces')
        self.assertNotEqual(name, 'agent-codex-ultra')
        self.assertEqual(command[:8], ['tmux', 'new-session', '-d', '-s', name,
                                      '-c', '/tmp/project with spaces', '--'])
        self.assertIn('--dangerously-bypass-approvals-and-sandbox', command)
        self.assertEqual(command[command.index('--model') + 1], 'gpt-6-astra')
        self.assertIn('model_reasoning_effort="ultra"', command)

    def test_only_real_keyboards_with_either_super_key_trigger_launch(self):
        def bits(*keys):
            result = bytearray(96)
            for key in keys:
                result[key // 8] |= 1 << (key % 8)
            return result
        for key in (125, 126):
            self.assertTrue(launcher.keyboard_super(bits(28, 30, 57, key), bits(key)))
            self.assertFalse(launcher.keyboard_super(bits(key), bits(key)))
        self.assertFalse(launcher.keyboard_super(bits(28, 30, 57, 125), bits(42)))


class SessionListingTests(unittest.TestCase):
    def test_parses_the_tab_separated_listing(self):
        output = 'agent-codex\t2\t1\t/home/jack\nother\t1\t0\t/tmp\n'
        self.assertEqual(launcher.parse_sessions(output), [
            {'name': 'agent-codex', 'windows': '2', 'attached': True, 'path': '/home/jack'},
            {'name': 'other', 'windows': '1', 'attached': False, 'path': '/tmp'},
        ])

    def test_ignores_malformed_rows(self):
        self.assertEqual(launcher.parse_sessions('broken\nalso broken\t1\n'), [])


class PreflightTests(unittest.TestCase):
    """A remote agent explains itself instead of leaving a session that dies."""

    def module(self):
        return runpy.run_path(str(REPO / 'alpine/desktop/.local/bin/oldbook-agents'))

    def agent(self, **extra):
        return dict({'id': 'far', 'title': 'Far', 'host': 'alienware',
                     'transport': 'tailscale-ssh', 'command': ['ollama']}, **extra)

    def test_an_unreachable_host_reports_before_any_session_is_made(self):
        module = self.module()
        with mock.patch.object(module['socket'], 'create_connection',
                               side_effect=OSError('refused')):
            with self.assertRaisesRegex(RuntimeError, 'tailscale up --ssh'):
                module['preflight'](self.agent())

    def test_a_policy_refusal_is_reported_rather_than_the_open_port(self):
        module = self.module()
        denial = subprocess.CompletedProcess(
            [], 1, '', 'tailscale: tailnet policy does not permit you to SSH to this node')
        # runpy hands back a namespace dict, so the name is replaced in place.
        with mock.patch.dict(module, {'reachable': lambda *a, **k: True}), \
                mock.patch.object(module['subprocess'], 'run', return_value=denial):
            with self.assertRaisesRegex(RuntimeError, 'tailnet policy'):
                module['preflight'](self.agent())

    def test_a_permitted_host_passes_preflight(self):
        module = self.module()
        allowed = subprocess.CompletedProcess([], 0, '', '')
        with mock.patch.dict(module, {'reachable': lambda *a, **k: True}), \
                mock.patch.object(module['subprocess'], 'run', return_value=allowed):
            self.assertIsNone(module['preflight'](self.agent()))

    def test_a_local_agent_needs_no_preflight(self):
        module = self.module()
        self.assertIsNone(module['preflight']({'id': 'codex', 'command': ['codex']}))


if __name__ == '__main__':
    unittest.main()
