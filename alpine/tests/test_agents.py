"""Agent sessions must be tmux-contained and safe to build from configuration."""
import json
from pathlib import Path
import runpy
import shlex
import shutil
import subprocess
import sys
import tempfile
import tomllib
import unittest
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'alpine/desktop/.local/lib/oldbook'))
import agent_launcher as launcher
import agent_trust as trust

LIVE = REPO / 'alpine/desktop/.config/oldbook/agents.json'
SCRIPT = REPO / 'alpine/desktop/.local/bin/oldbook-agents'


def script():
    """The launcher's own namespace, disarmed.

    runpy hands back a copy of the globals, so a patch on that copy never
    reaches the functions; a function's __globals__ is the dict they read.
    The menu and the notifier are replaced at load so a test that reaches
    either fails loudly instead of opening Fuzzel or a card on the desktop.
    """
    namespace = runpy.run_path(str(SCRIPT))['main'].__globals__
    namespace['FUZZEL'] = Path('/nonexistent/oldbook-fuzzel')
    namespace['notify'] = lambda *args, **kwargs: None
    return namespace


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
        agent = launcher.quick_agent(document)
        self.assertIsNotNone(agent, 'quick-launch preset is missing')
        self.assertEqual(agent['id'], 'codex-best')
        name = launcher.session_name(document, agent['id'], {'agent-codex-best'})
        command = launcher.new_session_command(document, agent, name, '/tmp/project with spaces')
        self.assertNotEqual(name, 'agent-codex-best')
        self.assertEqual(command[:8], ['tmux', 'new-session', '-d', '-s', name,
                                      '-c', '/tmp/project with spaces', '--'])
        self.assertIn('--dangerously-bypass-approvals-and-sandbox', command)
        self.assertEqual(command[command.index('--model') + 1], 'gpt-6-astra')
        self.assertIn('model_reasoning_effort="ultra"', command)
        self.assertTrue(agent.get('trust'), 'the quick launch must not stop at a trust screen')

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
        return script()

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


def preset(**extra):
    agent = {'id': 'claude', 'title': 'Claude', 'model': 'claude-fable-5-1', 'effort': 'max',
             'trust': True,
             'command': ['claude', '--model', '{model}', '--effort', '{effort}',
                         '--settings', '{"sandbox":{"enabled":false}}']}
    agent.update(extra)
    return agent


def open_preset():
    agent = preset(models=['claude-fable-5-1', 'claude-opus-5'], efforts=['max', 'low'])
    del agent['model'], agent['effort']
    return agent


class ChoiceTests(unittest.TestCase):
    """The picker line and the command line are built from the same two words."""

    def write(self, document):
        handle = tempfile.NamedTemporaryFile('w', suffix='.json', delete=False)
        json.dump(document, handle)
        handle.close()
        self.addCleanup(lambda: Path(handle.name).unlink(missing_ok=True))
        return handle.name

    def test_the_model_and_effort_reach_the_command(self):
        command = launcher.render_command(preset())
        self.assertEqual(command[command.index('--model') + 1], 'claude-fable-5-1')
        self.assertEqual(command[command.index('--effort') + 1], 'max')
        # Literal braces elsewhere in the command are not a template.
        self.assertIn('{"sandbox":{"enabled":false}}', command)

    def test_a_chosen_value_replaces_the_preset(self):
        command = launcher.render_command(preset(), {'model': 'claude-opus-5', 'effort': None})
        self.assertEqual(command[command.index('--model') + 1], 'claude-opus-5')
        self.assertEqual(command[command.index('--effort') + 1], 'max')

    def test_a_preset_that_leaves_the_choice_open_must_be_asked(self):
        agent = open_preset()
        self.assertEqual(launcher.open_choices(agent), ['model', 'effort'])
        self.assertEqual(launcher.open_choices(preset()), [])
        with self.assertRaises(ValueError):
            launcher.render_command(agent)
        command = launcher.render_command(agent, {'model': 'claude-opus-5', 'effort': 'low'})
        self.assertEqual(command[command.index('--model') + 1], 'claude-opus-5')

    def test_the_preset_value_is_offered_first_and_only_once(self):
        agent = preset(models=['claude-opus-5', 'claude-fable-5-1'])
        self.assertEqual(launcher.options(agent, 'model'), ['claude-fable-5-1', 'claude-opus-5'])
        self.assertEqual(launcher.options(open_preset(), 'effort'), ['max', 'low'])

    def test_the_picker_line_names_model_effort_and_trust(self):
        self.assertEqual(launcher.describe(preset()),
                         'Claude · claude-fable-5-1 · max · trusts all')
        self.assertEqual(launcher.describe(open_preset()),
                         'Claude · choose model and effort… · trusts all')
        self.assertEqual(launcher.describe(open_preset(), {'model': 'claude-opus-5'}),
                         'Claude · claude-opus-5 · choose effort… · trusts all')
        self.assertEqual(launcher.describe(preset(trust=False, subtitle='here')),
                         'Claude · claude-fable-5-1 · max — here')
        far = {'id': 'far', 'title': 'Local model on alienware', 'host': 'alienware',
               'model': 'qwen3.5:9b', 'command': ['ollama', 'run', '{model}']}
        self.assertEqual(launcher.describe(far), 'Local model on alienware · qwen3.5:9b')
        far['title'] = 'Local model'
        self.assertEqual(launcher.describe(far), 'Local model · alienware · qwen3.5:9b')

    def test_the_window_title_carries_the_model_and_effort(self):
        self.assertEqual(launcher.title(preset()), 'Claude · claude-fable-5-1 · max')
        self.assertEqual(launcher.title(preset(), {'effort': 'low'}),
                         'Claude · claude-fable-5-1 · low')
        self.assertEqual(launcher.title({'id': 'shell', 'title': 'Shell', 'command': ['zsh']}),
                         'Shell')

    def test_a_named_model_the_command_never_uses_is_refused(self):
        document = config()
        document['agents'][0]['model'] = 'gpt-6-astra'
        with self.assertRaisesRegex(ValueError, 'never uses'):
            launcher.load_config(self.write(document))

    def test_a_placeholder_without_a_model_is_refused(self):
        document = config()
        document['agents'][0]['command'] = ['codex', '--model', '{model}']
        with self.assertRaisesRegex(ValueError, 'neither a model'):
            launcher.load_config(self.write(document))
        document['agents'][0]['models'] = ['gpt-6-astra']
        launcher.load_config(self.write(document))

    def test_lead_and_quick_must_name_real_agents(self):
        for key, value in (('lead', ['codex', 'nope']), ('quick', 'nope'), ('quick', ['codex'])):
            document = config(**{key: value})
            with self.assertRaises(ValueError):
                launcher.load_config(self.write(document))
        document = launcher.load_config(self.write(config(lead=['far', 'codex'], quick='codex')))
        self.assertEqual([agent['id'] for agent in launcher.lead_agents(document)],
                         ['far', 'codex'])
        self.assertEqual(launcher.quick_agent(document)['id'], 'codex')
        self.assertEqual(launcher.lead_agents(config()), [])
        self.assertIsNone(launcher.quick_agent(config()))

    def test_a_disabled_lead_preset_is_left_out(self):
        document = config(lead=['far', 'codex'])
        document['agents'][1]['enabled'] = False
        self.assertEqual([agent['id'] for agent in launcher.lead_agents(document)], ['codex'])

    def test_trust_must_be_a_switch(self):
        document = config()
        document['agents'][0]['trust'] = 'yes'
        with self.assertRaises(ValueError):
            launcher.load_config(self.write(document))

    def test_the_live_file_leads_with_the_best_codex_and_claude(self):
        document = launcher.load_config(LIVE)
        lead = launcher.lead_agents(document)
        self.assertEqual([agent['id'] for agent in lead], ['codex-best', 'claude-best'])
        codex, claude = lead
        self.assertEqual((codex['model'], codex['effort']), ('gpt-6-astra', 'ultra'))
        self.assertEqual((claude['model'], claude['effort']), ('claude-fable-5-1', 'max'))
        for agent in lead:
            self.assertTrue(agent['trust'], agent['id'])
            self.assertEqual(launcher.open_choices(agent), [], agent['id'])
        self.assertEqual(launcher.quick_agent(document)['id'], 'codex-best')
        self.assertEqual(launcher.describe(codex), 'Codex · gpt-6-astra · ultra · trusts all')
        self.assertEqual(launcher.describe(claude),
                         'Claude · claude-fable-5-1 · max · trusts all')

    def test_every_local_codex_and_claude_preset_trusts_all(self):
        document = launcher.load_config(LIVE)
        for agent in launcher.enabled_agents(document):
            if agent.get('host') or trust.tool_name(agent['command']) not in ('claude', 'codex'):
                continue
            self.assertTrue(agent.get('trust'), agent['id'])
            self.assertEqual(launcher.open_choices(agent) or ['model', 'effort'],
                             ['model', 'effort'], agent['id'])

    def test_the_live_choose_presets_lead_with_the_best(self):
        document = launcher.load_config(LIVE)
        agents = {agent['id']: agent for agent in document['agents']}
        self.assertEqual(launcher.options(agents['codex'], 'model')[0], 'gpt-6-astra')
        self.assertEqual(launcher.options(agents['codex'], 'effort')[0], 'ultra')
        self.assertEqual(launcher.options(agents['claude'], 'model')[0], 'claude-fable-5-1')
        self.assertEqual(launcher.options(agents['claude'], 'effort')[0], 'max')


class TrustTests(unittest.TestCase):
    """A trusting preset has its directory accepted before the tool can ask."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='oldbook-agent-trust-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.claude = self.root / '.claude.json'
        self.codex = self.root / 'config.toml'

    def test_claude_gets_the_directory_accepted_in_its_own_file(self):
        self.claude.write_text(json.dumps({'numStartups': 3, 'projects': {
            '/x': {'hasTrustDialogAccepted': False, 'allowedTools': []}}}))
        self.claude.chmod(0o600)
        self.assertEqual(trust.grant_claude('/x', self.claude), self.claude)
        document = json.loads(self.claude.read_text())
        self.assertIs(document['projects']['/x']['hasTrustDialogAccepted'], True)
        self.assertEqual(document['projects']['/x']['allowedTools'], [])
        self.assertEqual(document['numStartups'], 3)
        self.assertEqual(self.claude.stat().st_mode & 0o777, 0o600)
        self.assertIsNone(trust.grant_claude('/x', self.claude), 'already accepted')

    def test_claude_file_and_project_are_created_when_missing(self):
        self.assertEqual(trust.grant_claude('/new place', self.claude), self.claude)
        document = json.loads(self.claude.read_text())
        self.assertIs(document['projects']['/new place']['hasTrustDialogAccepted'], True)

    def test_claude_file_that_is_not_an_object_is_refused_not_replaced(self):
        self.claude.write_text('[1, 2]')
        with self.assertRaises(ValueError):
            trust.grant_claude('/x', self.claude)
        self.assertEqual(self.claude.read_text(), '[1, 2]')

    def test_codex_gets_a_project_table(self):
        self.codex.write_text('model = "gpt-6-astra"\n\n[projects."/home/jack"]\n'
                              'trust_level = "trusted"\n')
        key = '/x/y "quoted"\\slash'
        self.assertEqual(trust.grant_codex(key, self.codex), self.codex)
        document = tomllib.loads(self.codex.read_text())
        self.assertEqual(document['projects'][key]['trust_level'], 'trusted')
        self.assertEqual(document['projects']['/home/jack']['trust_level'], 'trusted')
        self.assertEqual(document['model'], 'gpt-6-astra')
        self.assertIsNone(trust.grant_codex(key, self.codex), 'already trusted')

    def test_codex_file_is_created_when_missing(self):
        trust.grant_codex('/x', self.codex)
        self.assertEqual(tomllib.loads(self.codex.read_text()),
                         {'projects': {'/x': {'trust_level': 'trusted'}}})

    def test_an_earlier_untrusted_answer_is_overturned_in_place(self):
        self.codex.write_text('[projects."/x"]\ntrust_level = "untrusted"\n\n'
                              '[projects."/y"]\ntrust_level = "trusted"\n')
        trust.grant_codex('/x', self.codex)
        document = tomllib.loads(self.codex.read_text())
        self.assertEqual(document['projects']['/x'], {'trust_level': 'trusted'})
        self.assertEqual(document['projects']['/y'], {'trust_level': 'trusted'})
        self.assertEqual(self.codex.read_text().count('[projects."/x"]'), 1)

    def test_the_key_is_the_git_root_inside_a_repository(self):
        plain = self.root / 'plain'
        plain.mkdir()
        self.assertEqual(trust.trust_key(plain), str(plain.resolve()))
        if not shutil.which('git'):
            self.skipTest('git is not installed')
        repo = self.root / 'repo'
        (repo / 'sub').mkdir(parents=True)
        subprocess.run(['git', '-C', str(repo), 'init', '-q'], check=True, timeout=30)
        self.assertEqual(trust.trust_key(repo / 'sub'), str(repo.resolve()))

    def test_only_claude_and_codex_keep_such_an_answer(self):
        self.assertIsNone(trust.grant(['zsh'], self.root, self.claude, self.codex))
        self.assertIsNone(trust.grant(['ollama', 'run', 'x'], self.root, self.claude, self.codex))
        self.assertFalse(self.claude.exists())
        self.assertFalse(self.codex.exists())
        self.assertEqual(trust.grant(['/usr/local/bin/codex', '--search'], self.root,
                                     self.claude, self.codex), self.codex)
        self.assertEqual(trust.grant(['claude'], self.root, self.claude, self.codex),
                         self.claude)


class WorkdirMemoryTests(unittest.TestCase):
    """The directory list opens on wherever the preset last started."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='oldbook-agents-memory-')
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        (self.home / 'src/one').mkdir(parents=True)
        (self.home / 'src/two').mkdir(parents=True)
        self.state = self.home / 'state/last-workdir.json'

    def options(self, document, agent='codex'):
        return launcher.workdir_options(document, agent, home=self.home, state=self.state)

    def test_last_time_leads_the_list_without_repeating(self):
        document = config(workdirs=['~', '~/src/*'])
        paths, last = self.options(document)
        self.assertIsNone(last)
        self.assertEqual(paths[0], self.home.resolve())
        launcher.remember_workdir('codex', self.home / 'src/two', state=self.state)
        paths, last = self.options(document)
        self.assertEqual(last, (self.home / 'src/two').resolve())
        self.assertEqual(paths[0], last)
        self.assertEqual(paths.count(last), 1)
        self.assertEqual(len(paths), 3)
        # Another preset keeps its own memory.
        self.assertIsNone(self.options(document, 'claude')[1])

    def test_a_directory_outside_the_list_is_still_offered_first(self):
        document = config(workdirs=['~'])
        extra = self.home / 'src/one'
        launcher.remember_workdir('codex', extra, state=self.state)
        paths, last = self.options(document)
        self.assertEqual(paths, [extra.resolve(), self.home.resolve()])

    def test_a_vanished_directory_is_forgotten(self):
        document = config(workdirs=['~'])
        gone = self.home / 'src/one'
        launcher.remember_workdir('codex', gone, state=self.state)
        gone.rmdir()
        paths, last = self.options(document)
        self.assertIsNone(last)
        self.assertEqual(paths, [self.home.resolve()])

    def test_a_broken_record_is_ignored_and_rewritten(self):
        self.state.parent.mkdir(parents=True)
        self.state.write_text('not json')
        self.assertIsNone(launcher.remembered_workdir('codex', state=self.state))
        launcher.remember_workdir('codex', self.home, state=self.state)
        self.assertEqual(json.loads(self.state.read_text()), {'codex': str(self.home.resolve())})

    def test_the_memory_can_be_switched_off(self):
        document = config(workdirs=['~'], remember_workdir=False)
        launcher.remember_workdir('codex', self.home / 'src/one', state=self.state)
        self.assertEqual(self.options(document), ([self.home.resolve()], None))


class PickerTests(unittest.TestCase):
    """What Super+N lists, in what order, and what a choice leads to."""

    def module(self):
        return script()

    def test_the_namespace_under_test_is_the_one_the_functions_read(self):
        module = self.module()
        self.assertIs(module, module['choose'].__globals__)
        with mock.patch.dict(module, {'menu': lambda *a, **k: None}):
            self.assertIsNone(module['choose'](open_preset()))
        with self.assertRaises(OSError):
            module['menu']('x ❯ ', ['one'])

    def test_the_lead_presets_come_first_then_sessions_then_the_rest(self):
        module = self.module()
        document = launcher.load_config(LIVE)
        live = [{'name': 'agent-claude-best', 'windows': '2', 'attached': True, 'path': '/tmp/x'}]
        labels, actions = module['entries'](document, live)
        self.assertEqual([actions[label] for label in labels[:3]],
                         [('new', 'codex-best'), ('new', 'claude-best'),
                          ('attach', 'agent-claude-best')])
        self.assertEqual(labels[0], '✦  New Codex · gpt-6-astra · ultra · trusts all')
        self.assertEqual(labels[1], '✦  New Claude · claude-fable-5-1 · max · trusts all')
        self.assertEqual(actions[labels[-1]], ('close', None))
        rest = [actions[label][1] for label in labels[3:-1]]
        self.assertEqual(rest[:2], ['codex', 'claude'])
        self.assertNotIn('codex-best', rest)
        self.assertEqual(len(set(labels)), len(labels), 'every line must be selectable')

    def test_an_open_preset_asks_model_then_effort_with_the_first_option_preselected(self):
        module = self.module()
        asked = []

        def menu(prompt, options, **_):
            asked.append((prompt, options[0]))
            return options[1]

        with mock.patch.dict(module, {'menu': menu}):
            self.assertEqual(module['choose'](open_preset()),
                             {'model': 'claude-opus-5', 'effort': 'low'})
            self.assertEqual(module['choose'](preset()), {})
        self.assertEqual(asked, [('Claude model ❯ ', 'claude-fable-5-1'),
                                 ('Claude effort ❯ ', 'max')])

    def test_escape_while_choosing_launches_nothing(self):
        module = self.module()
        with mock.patch.dict(module, {'menu': lambda *a, **k: None}):
            self.assertIsNone(module['choose'](open_preset()))

    def test_whatever_was_not_asked_takes_the_first_option(self):
        module = self.module()
        self.assertEqual(module['complete'](open_preset()),
                         {'model': 'claude-fable-5-1', 'effort': 'max'})
        self.assertEqual(module['complete'](open_preset(), {'effort': 'low', 'model': None}),
                         {'model': 'claude-fable-5-1', 'effort': 'low'})
        self.assertEqual(module['complete'](preset(), {'model': 'claude-opus-5'}),
                         {'model': 'claude-opus-5'})

    def test_the_directory_menu_opens_on_last_time_and_names_the_session(self):
        module = self.module()
        temp = tempfile.TemporaryDirectory(prefix='oldbook-agents-pick-')
        self.addCleanup(temp.cleanup)
        home = Path(temp.name)
        (home / 'work').mkdir()
        document = config(workdirs=['~'])
        shown = []

        def menu(prompt, options, **_):
            shown.append((prompt, options))
            return options[0]

        def workdir_options(document, agent_id, home=None, state=None):
            return [home_ / 'work', home_], home_ / 'work'
        home_ = home
        with mock.patch.dict(module, {'menu': menu}), \
                mock.patch.object(module['launcher'], 'workdir_options', workdir_options), \
                mock.patch.object(module['launcher'], 'short_path',
                                  lambda path, home=None: str(path).replace(str(home_), '~')):
            chosen = module['choose_workdir'](document, preset(), {'effort': 'low'})
        self.assertEqual(chosen, home / 'work')
        self.assertEqual(shown[0][0], 'Claude · claude-fable-5-1 · low in ❯ ')
        self.assertEqual(shown[0][1][:2], ['~/work  · last time', '~'])
        self.assertEqual(shown[0][1][-1], '…  Another directory')

    def test_start_accepts_trust_before_the_session_exists_and_titles_the_window(self):
        module = self.module()
        document = config()
        agent = preset()
        calls = []

        def run(command, **_):
            calls.append(('run', command[:2]))
            return subprocess.CompletedProcess(command, 0, '', '')

        with mock.patch.dict(module, {'sessions': lambda: [],
                                      'attach': lambda *a, **k: calls.append(('attach', a[2]))}), \
                mock.patch.object(module['subprocess'], 'run', run), \
                mock.patch.object(module['subprocess'], 'Popen',
                                  side_effect=AssertionError('a terminal was opened')), \
                mock.patch.object(module['trust'], 'grant',
                                  lambda command, workdir: calls.append(('grant', command[0], workdir))), \
                mock.patch.object(module['launcher'], 'remember_workdir',
                                  lambda agent_id, path: calls.append(('remember', agent_id))):
            name = module['start'](document, agent, '/tmp/work', choices={'effort': 'low'})
        self.assertEqual(name, 'agent-claude')
        self.assertEqual(calls, [('grant', 'claude', '/tmp/work'),
                                 ('run', ['tmux', 'new-session']),
                                 ('run', ['tmux', 'has-session']),
                                 ('remember', 'claude'),
                                 ('attach', 'Claude · claude-fable-5-1 · low')])

    def test_a_trust_record_that_cannot_be_written_does_not_stop_the_launch(self):
        module = self.module()
        warnings = []

        def failing(command, workdir):
            raise ValueError('config.toml is not valid TOML')

        with mock.patch.dict(module, {'warn': lambda message: warnings.append(message)}), \
                mock.patch.object(module['trust'], 'grant', failing):
            self.assertIsNone(module['grant_trust'](preset(), '/tmp/work'))
        self.assertEqual(len(warnings), 1)
        self.assertIn('config.toml is not valid TOML', warnings[0])
        self.assertIn('will ask about trusting', warnings[0])

    def test_a_preset_without_trust_or_on_a_host_writes_nothing(self):
        module = self.module()
        with mock.patch.object(module['trust'], 'grant', side_effect=AssertionError('written')):
            self.assertIsNone(module['grant_trust'](preset(trust=False), '/tmp/work'))
            self.assertIsNone(module['grant_trust'](preset(host='alienware'), '/tmp/work'))


if __name__ == '__main__':
    unittest.main()
