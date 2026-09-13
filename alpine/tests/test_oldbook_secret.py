"""oldbook-secret's op-vs-prompt fallback and output shape, without a real secret."""
from pathlib import Path
import runpy
import sys
import unittest
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
SECRET = runpy.run_path(str(REPO / 'alpine/desktop/.local/bin/oldbook-secret'))
# run_path hands back a *copy* of the module namespace; the functions in it
# keep their real __globals__ pointing at the original, so patching entries in
# SECRET itself would never be seen by a call one of those functions makes to
# another. Patch this instead -- it's the dict fetch()/main() actually resolve
# global names against.
GLOBALS = SECRET['fetch'].__globals__


def completed(returncode=0, stdout='', stderr=''):
    return mock.Mock(returncode=returncode, stdout=stdout, stderr=stderr)


class SignedIn(unittest.TestCase):
    def test_op_whoami_success_means_signed_in(self):
        with mock.patch('subprocess.run', return_value=completed(0)) as run:
            self.assertTrue(SECRET['op_signed_in']())
        self.assertEqual(run.call_args.args[0], ['op', 'whoami'])

    def test_op_whoami_failure_means_not_signed_in(self):
        with mock.patch('subprocess.run', return_value=completed(1)):
            self.assertFalse(SECRET['op_signed_in']())

    def test_op_missing_entirely_means_not_signed_in(self):
        with mock.patch('subprocess.run', side_effect=FileNotFoundError()):
            self.assertFalse(SECRET['op_signed_in']())


class OpField(unittest.TestCase):
    def test_reads_a_secret_reference_built_from_item_and_field(self):
        with mock.patch('subprocess.run', return_value=completed(0, 'sk-abc123\n')) as run:
            value = SECRET['op_field']('Web-ext API', 'issuer')
        self.assertEqual(value, 'sk-abc123')
        self.assertEqual(run.call_args.args[0], ['op', 'read', 'op://Web-ext API/issuer'])

    def test_a_failed_read_raises_with_ops_own_stderr(self):
        with mock.patch('subprocess.run', return_value=completed(1, '', 'isn\'t here\n')):
            with self.assertRaisesRegex(RuntimeError, "isn't here"):
                SECRET['op_field']('Web-ext API', 'issuer')


class PromptField(unittest.TestCase):
    def test_prompts_with_fuzzel_dmenu_password_mode_and_returns_the_typed_line(self):
        with mock.patch('subprocess.run', return_value=completed(0, 'typed-secret\n')) as run:
            value = SECRET['prompt_field']('Web-ext API', 'issuer')
        self.assertEqual(value, 'typed-secret')
        command = run.call_args.args[0]
        self.assertEqual(command[0], 'fuzzel')
        self.assertIn('--dmenu', command)
        self.assertIn('--password', command)
        self.assertTrue(any(part.startswith('--prompt-only=') for part in command))
        self.assertIn('Web-ext API', command[-1])
        self.assertIn('issuer', command[-1])

    def test_a_cancelled_prompt_raises_instead_of_returning_empty(self):
        with mock.patch('subprocess.run', return_value=completed(1, '')):
            with self.assertRaisesRegex(RuntimeError, 'cancelled'):
                SECRET['prompt_field']('Web-ext API', 'issuer')

    def test_a_hung_prompt_times_out_rather_than_blocking_forever(self):
        import subprocess as subprocess_module
        with mock.patch('subprocess.run', side_effect=subprocess_module.TimeoutExpired('fuzzel', 120)):
            with self.assertRaisesRegex(RuntimeError, 'Timed out'):
                SECRET['prompt_field']('Web-ext API', 'issuer')


class Fetch(unittest.TestCase):
    def test_prefers_op_when_signed_in(self):
        op_field = mock.Mock(return_value='from-op')
        prompt_field = mock.Mock(return_value='from-prompt')
        with mock.patch.dict(GLOBALS, {'op_signed_in': lambda: True,
                                       'op_field': op_field, 'prompt_field': prompt_field}):
            self.assertEqual(SECRET['fetch']('item', 'field'), 'from-op')
        prompt_field.assert_not_called()

    def test_falls_back_to_the_prompt_when_op_is_not_signed_in(self):
        op_field = mock.Mock(return_value='from-op')
        prompt_field = mock.Mock(return_value='from-prompt')
        with mock.patch.dict(GLOBALS, {'op_signed_in': lambda: False,
                                       'op_field': op_field, 'prompt_field': prompt_field}):
            self.assertEqual(SECRET['fetch']('item', 'field'), 'from-prompt')
        op_field.assert_not_called()


class Main(unittest.TestCase):
    def run_main(self, argv):
        with mock.patch.object(sys, 'argv', ['oldbook-secret'] + argv):
            return SECRET['main']()

    def test_default_field_is_password_and_prints_one_line(self):
        fetch = mock.Mock(return_value='hunter2')
        with mock.patch.dict(GLOBALS, {'fetch': fetch}):
            with mock.patch('sys.stdout') as out:
                self.assertEqual(self.run_main(['get', 'Some Item']), 0)
        fetch.assert_called_once_with('Some Item', 'password')
        out.write.assert_called_once_with('hunter2\n')

    def test_repeated_field_flags_print_one_line_per_field_in_order(self):
        values = {'issuer': 'the-issuer', 'secret': 'the-secret'}
        fetch = mock.Mock(side_effect=lambda item, field: values[field])
        with mock.patch.dict(GLOBALS, {'fetch': fetch}):
            with mock.patch('sys.stdout') as out:
                code = self.run_main(['get', 'Web-ext API', '--field', 'issuer', '--field', 'secret'])
        self.assertEqual(code, 0)
        out.write.assert_called_once_with('the-issuer\nthe-secret\n')

    def test_a_failed_fetch_reports_to_stderr_and_exits_nonzero(self):
        fetch = mock.Mock(side_effect=RuntimeError('nope'))
        with mock.patch.dict(GLOBALS, {'fetch': fetch}):
            with mock.patch('sys.stderr') as err:
                code = self.run_main(['get', 'Some Item'])
        self.assertEqual(code, 1)
        self.assertIn('nope', ''.join(call.args[0] for call in err.write.call_args_list))

    def test_the_secret_never_appears_on_the_fetch_command_line(self):
        # fetch()'s own argv-safety is structural (fuzzel reads typed text from
        # its own UI, never a CLI argument) -- this only pins that main() passes
        # the item/field names along, never a value it doesn't have yet.
        fetch = mock.Mock(return_value='shh')
        with mock.patch.dict(GLOBALS, {'fetch': fetch}):
            self.run_main(['get', 'Some Item'])
        for call in fetch.call_args_list:
            self.assertNotIn('shh', call.args)


if __name__ == '__main__':
    unittest.main()
