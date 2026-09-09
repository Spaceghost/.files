"""A failed run says what the generator said, and where the whole run is."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'alpine/wallpapers'))

import failure_notice  # noqa: E402
import new_themes  # noqa: E402
from test_wallpapers import generator  # noqa: E402


LIMIT = ("You've hit your usage limit. Visit https://chatgpt.com/codex/settings/usage "
         "to purchase more credits or try again at Sep 14th, 2026 6:21 PM.")
RUN = [
    {'type': 'thread.started', 'thread_id': '01a08626'},
    {'type': 'turn.started'},
    {'type': 'error', 'message': LIMIT},
    {'type': 'turn.failed', 'error': {'message': LIMIT}},
]


def write_log(path, events):
    path.write_text(''.join(json.dumps(event) + '\n' for event in events))
    return path


class LogReasonTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_the_runners_own_last_words_are_what_comes_out(self):
        log = write_log(self.root / 'run.jsonl', RUN)

        self.assertEqual(new_themes.log_reason(log), LIMIT)

    def test_a_nested_error_message_is_found_as_readily_as_a_flat_one(self):
        log = write_log(self.root / 'run.jsonl',
                        [{'type': 'turn.failed', 'error': {'message': 'Session expired'}}])

        self.assertEqual(new_themes.log_reason(log), 'Session expired')

    def test_a_string_error_is_read_too(self):
        log = write_log(self.root / 'run.jsonl', [{'type': 'turn.failed', 'error': 'No login'}])

        self.assertEqual(new_themes.log_reason(log), 'No login')

    def test_noise_and_absence_are_answered_with_nothing_rather_than_a_guess(self):
        self.assertIsNone(new_themes.log_reason(self.root / 'missing.jsonl'))
        blank = self.root / 'blank.jsonl'
        blank.write_text('not json\n{"type": "turn.started"}\n[]\n')
        self.assertIsNone(new_themes.log_reason(blank))

    def test_a_reason_is_one_line_and_bounded(self):
        log = write_log(self.root / 'run.jsonl',
                        [{'type': 'error', 'message': 'a\n  b\t c ' + 'x' * 900}])
        reason = new_themes.log_reason(log)

        self.assertTrue(reason.startswith('a b c '))
        self.assertLessEqual(len(reason), 400)

    def test_the_caller_only_speaks_when_the_log_does_not(self):
        log = write_log(self.root / 'run.jsonl', RUN)
        self.assertEqual(str(new_themes.failed(log, 'exited with status 1')), LIMIT)

        quiet = write_log(self.root / 'quiet.jsonl', [{'type': 'turn.started'}])
        self.assertEqual(str(new_themes.failed(quiet, 'exited with status 1')),
                         'exited with status 1')


class FailureNotificationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.record = self.root / '1788957050560328661-18614.json'
        self.record.write_text(json.dumps({'status': 'failed', 'phase': 'theme'}))
        patch = mock.patch.object(generator, 'LAST_FAILURE', self.root / 'last-failure')
        patch.start()
        self.addCleanup(patch.stop)

    def logs(self, *attempts):
        first = self.record.with_suffix('.theme.jsonl')
        write_log(first, [{'type': 'turn.started'}])
        for attempt in attempts:
            write_log(first.with_name(first.stem + f'.attempt-{attempt}' + first.suffix), RUN)
        return first

    def notified(self, error='Artwork design failed; see private generation log', phase='theme'):
        """What the desktop was asked to show: (title, message), {urgency, log}."""
        with mock.patch('failure_notice.announce', return_value=True) as announce:
            generator.notify_failure(phase, error, self.record)
        title, message, log = announce.call_args[0]
        return (title, message), {'urgency': 'critical', 'log': log}

    def test_the_attempt_that_failed_is_the_one_read(self):
        self.logs(2, 3, 4)

        self.assertEqual(generator.newest_attempt_log(self.record, 'theme').name,
                         self.record.stem + '.theme.attempt-4.jsonl')

    def test_the_log_outranks_an_exception_that_lost_the_reason(self):
        self.logs(2, 3, 4)
        (_title, message), options = self.notified()

        self.assertIn('usage limit', message)
        self.assertIn('chatgpt.com/codex/settings/usage', message)
        self.assertNotIn('see private generation log', message)
        self.assertEqual(options['urgency'], 'critical')

    def test_a_silent_log_lets_the_exception_speak(self):
        self.logs()
        (_title, message), _options = self.notified('The painter exited with status 2')

        self.assertIn('exited with status 2', message)

    def test_the_fixed_paths_point_at_this_run(self):
        self.logs(2, 3, 4)
        self.notified()

        record_link = generator.LAST_FAILURE.with_suffix('.json')
        log_link = generator.LAST_FAILURE.with_suffix('.jsonl')
        self.assertEqual(record_link.resolve(), self.record.resolve())
        self.assertTrue(log_link.resolve().name.endswith('.theme.attempt-4.jsonl'))

    def test_a_second_failure_moves_the_fixed_paths_rather_than_failing(self):
        self.logs(2, 3, 4)
        self.notified()
        later = self.root / '1788999999999999999-42.json'
        later.write_text('{}')
        write_log(later.with_suffix('.theme.jsonl'), RUN)

        generator.remember_failure(later, later.with_suffix('.theme.jsonl'))

        self.assertEqual(generator.LAST_FAILURE.with_suffix('.json').resolve(), later.resolve())

    def test_the_message_names_where_the_whole_run_is(self):
        self.logs(2, 3, 4)
        (_title, message), _options = self.notified()

        self.assertIn('last-failure.jsonl', message)

    def test_each_phase_is_named_in_the_title(self):
        for phase, expected in (('theme', 'Theme design stopped'),
                                ('scene', 'Scene design stopped'),
                                ('image', 'Painting stopped')):
            with self.subTest(phase=phase):
                (title, _message), _options = self.notified('stopped', phase=phase)
                self.assertEqual(title, expected)

    def test_the_button_is_given_the_fixed_path_to_open(self):
        self.logs(2, 3, 4)
        (_title, _message), options = self.notified()

        self.assertEqual(Path(options['log']).name, 'last-failure.jsonl')
        self.assertTrue(Path(options['log']).resolve().name.endswith('.theme.attempt-4.jsonl'))


class ClickThroughTests(unittest.TestCase):
    """The button on the notification, and what it opens."""

    def test_a_log_earns_a_button_and_no_log_earns_none(self):
        with mock.patch.object(failure_notice.subprocess, 'run') as run:
            run.return_value = mock.Mock(stdout='')
            failure_notice.hold('Theme design stopped', 'why', '/tmp/run.jsonl')
            self.assertIn('--action=open=Show the whole run', run.call_args[0][0])

            failure_notice.hold('Theme design stopped', 'why', None)
            self.assertFalse(any(str(argument).startswith('--action')
                                 for argument in run.call_args[0][0]))

    def test_pressing_the_button_opens_the_run_and_ignoring_it_does_not(self):
        with mock.patch.object(failure_notice, 'open_log') as opened, \
                mock.patch.object(failure_notice.subprocess, 'run') as run:
            run.return_value = mock.Mock(stdout='open\n')
            failure_notice.hold('t', 'm', '/tmp/run.jsonl')
            self.assertEqual(opened.call_args[0][0], '/tmp/run.jsonl')

            opened.reset_mock()
            run.return_value = mock.Mock(stdout='')
            failure_notice.hold('t', 'm', '/tmp/run.jsonl')
            opened.assert_not_called()

    def test_the_notification_is_critical_so_it_is_still_there_later(self):
        with mock.patch.object(failure_notice.subprocess, 'run') as run:
            run.return_value = mock.Mock(stdout='')
            failure_notice.hold('t', 'm', None)

        self.assertIn('--urgency=critical', run.call_args[0][0])

    def test_the_waiting_is_done_by_a_detached_child(self):
        with mock.patch.object(failure_notice.subprocess, 'Popen') as popen:
            self.assertTrue(failure_notice.announce('t', 'm', '/tmp/run.jsonl'))

        self.assertTrue(popen.call_args[1]['start_new_session'])
        self.assertIn('--log', popen.call_args[0][0])

    def test_a_desktop_that_cannot_be_told_never_breaks_the_run(self):
        with mock.patch.object(failure_notice.subprocess, 'Popen', side_effect=OSError):
            self.assertFalse(failure_notice.announce('t', 'm', None))
        with mock.patch.object(failure_notice.subprocess, 'run', side_effect=OSError):
            self.assertFalse(failure_notice.hold('t', 'm', None))
        with mock.patch.object(failure_notice.shutil, 'which', return_value=None):
            self.assertIsNone(failure_notice.pager_command('/tmp/run.jsonl'))
            self.assertFalse(failure_notice.open_log('/tmp/run.jsonl'))

    def test_the_run_opens_at_its_end_where_the_reason_is(self):
        with mock.patch.object(failure_notice.shutil, 'which',
                               side_effect=lambda name: '/usr/bin/' + name
                               if name in ('foot', 'less') else None):
            command = failure_notice.pager_command('/tmp/run.jsonl')

        self.assertEqual(command[0], 'foot')
        self.assertEqual(command[-3:], ['-R', '+G', '/tmp/run.jsonl'])

    def test_the_generator_falls_back_to_a_plain_notification(self):
        record = Path(tempfile.mkdtemp()) / 'r.json'
        record.write_text('{}')
        with mock.patch('failure_notice.announce', return_value=False), \
                mock.patch.object(generator, 'notify') as notify:
            generator.notify_failure('theme', 'usage limit', record)

        self.assertEqual(notify.call_args[1]['urgency'], 'critical')


if __name__ == '__main__':
    unittest.main()
