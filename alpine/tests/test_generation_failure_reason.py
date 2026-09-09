"""A failed run says what the generator said, and where the whole run is."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'alpine/wallpapers'))

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

    def notified(self, error='Artwork design failed; see private generation log'):
        with mock.patch.object(generator, 'notify') as notify:
            generator.notify_failure('theme', error, self.record)
        return notify.call_args

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
            with self.subTest(phase=phase), mock.patch.object(generator, 'notify') as notify:
                generator.notify_failure(phase, 'stopped', self.record)
                self.assertEqual(notify.call_args[0][0], expected)


if __name__ == '__main__':
    unittest.main()
