"""Ghost Planet cues: the synthesizer, the player's silences, and the battery edges."""
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import wave

import numpy as np

REPO = Path(__file__).resolve().parents[2]
INSTALLED = REPO / 'alpine/desktop/.local/share/sounds/oldbook'


def load(name, relative):
    loader = importlib.machinery.SourceFileLoader(name, str(REPO / relative))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


synth = load('build_sound_theme', 'alpine/bin/build-sound-theme')
player = load('oldbook_sound', 'alpine/desktop/.local/bin/oldbook-sound')
battery = load('oldbook_battery_cue', 'alpine/desktop/.local/bin/oldbook-battery-cue')


class SynthesisTests(unittest.TestCase):
    def test_every_cue_is_short_and_audible(self):
        for name, make in synth.CUES.items():
            frames = make()
            seconds = len(frames) / synth.RATE
            self.assertLess(seconds, 1.0, f'{name} runs for {seconds:.2f}s')
            self.assertGreater(seconds, 0.03, f'{name} is too short to hear')
            self.assertGreater(float(np.max(np.abs(frames))), 0.01, f'{name} is silent')

    def test_normalising_hits_the_quiet_target_without_clipping(self):
        for name, make in synth.CUES.items():
            frames = synth.normalise(synth.stereo(make()))
            peak = float(np.max(np.abs(frames)))
            self.assertAlmostEqual(peak, synth.PEAK, places=6, msg=name)
            self.assertLess(peak, 1.0)

    def test_cues_open_and_close_on_silence(self):
        # A cue that starts or ends mid-waveform clicks in the speakers.
        for name, make in synth.CUES.items():
            frames = synth.normalise(make())
            self.assertLess(abs(float(frames[0])), 1e-3, f'{name} starts with a step')
            self.assertLess(abs(float(frames[-1])), 1e-3, f'{name} ends with a step')

    def test_stereo_widens_without_changing_length(self):
        mono = synth.CUES['tick']()
        wide = synth.stereo(mono)
        self.assertEqual(wide.shape, (len(mono), 2))
        self.assertFalse(np.array_equal(wide[:, 0], wide[:, 1]))

    def test_written_files_are_the_expected_wave_format(self):
        with tempfile.TemporaryDirectory(prefix='oldbook-cues-') as temporary:
            output = Path(temporary)
            written = synth.build(output, ['tick', 'unlock'])
            self.assertEqual(sorted(written), ['tick', 'unlock'])
            for name in written:
                with wave.open(str(output / f'{name}.wav'), 'rb') as handle:
                    self.assertEqual(handle.getnchannels(), 2)
                    self.assertEqual(handle.getsampwidth(), 2)
                    self.assertEqual(handle.getframerate(), synth.RATE)
                    self.assertEqual(handle.getnframes(),
                                     round(written[name]['seconds'] * synth.RATE))

    def test_the_checked_in_cues_are_present_and_playable(self):
        for name in synth.CUES:
            path = INSTALLED / f'{name}.wav'
            self.assertTrue(path.is_file(), name)
            with wave.open(str(path), 'rb') as handle:
                self.assertEqual(handle.getframerate(), synth.RATE)
                self.assertGreater(handle.getnframes(), 0)
                self.assertLess(handle.getnframes() / synth.RATE, 1.0)


class PlayerTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix='oldbook-player-')
        self.sounds = Path(self.directory.name) / 'sounds'
        self.sounds.mkdir()
        for name in player.CUES:
            (self.sounds / f'{name}.wav').write_bytes(b'RIFF')
        self.enter = mock.patch.dict(os.environ, {'OLDBOOK_SOUND_DIR': str(self.sounds)})
        self.enter.start()
        self.addCleanup(self.enter.stop)
        self.addCleanup(self.directory.cleanup)

    def play(self, cue, enabled=True, muted=False, which='pw-play'):
        with mock.patch.object(player, 'preferences',
                               return_value={'enabled': enabled, 'volume': 0.5}), \
             mock.patch.object(player, 'muted', return_value=muted), \
             mock.patch.object(player.shutil, 'which', side_effect=lambda n: which if n == which else None), \
             mock.patch.object(player.subprocess, 'Popen') as popen:
            return player.play(cue), popen

    def test_a_cue_starts_a_detached_player(self):
        started, popen = self.play('unlock')
        self.assertTrue(started)
        command = popen.call_args.args[0]
        self.assertEqual(command[0], 'pw-play')
        self.assertIn('--volume=0.500', command)
        self.assertTrue(popen.call_args.kwargs['start_new_session'])

    def test_the_master_switch_silences_everything(self):
        started, popen = self.play('unlock', enabled=False)
        self.assertFalse(started)
        popen.assert_not_called()

    def test_a_muted_sink_is_silence(self):
        started, popen = self.play('unlock', muted=True)
        self.assertFalse(started)
        popen.assert_not_called()

    def test_no_player_is_silence(self):
        started, popen = self.play('unlock', which='nothing-installed')
        self.assertFalse(started)
        popen.assert_not_called()

    def test_a_missing_file_is_silence(self):
        (self.sounds / 'unlock.wav').unlink()
        started, popen = self.play('unlock')
        self.assertFalse(started)
        popen.assert_not_called()

    def test_paplay_is_used_without_a_volume_flag(self):
        started, popen = self.play('tick', which='paplay')
        self.assertTrue(started)
        self.assertEqual(popen.call_args.args[0][0], 'paplay')
        self.assertNotIn('--volume=0.500', popen.call_args.args[0])

    def test_an_unknown_cue_is_refused_rather_than_played(self):
        self.assertFalse(player.play('applause'))
        self.assertEqual(player.main(['applause']), 64)

    def test_preferences_fall_back_when_the_file_is_nonsense(self):
        with tempfile.NamedTemporaryFile('w', suffix='.json', delete=False) as handle:
            handle.write('{ not json')
            path = Path(handle.name)
        with mock.patch.object(player, 'CONFIG', path):
            self.assertEqual(player.preferences(), {'enabled': True, 'volume': player.DEFAULT_VOLUME})
        path.unlink()

    def test_out_of_range_volume_is_replaced(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'sound.json'
            path.write_text(json.dumps({'enabled': True, 'volume': 9}))
            with mock.patch.object(player, 'CONFIG', path):
                self.assertEqual(player.preferences()['volume'], player.DEFAULT_VOLUME)

    def test_the_switch_round_trips_through_the_preference_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'sound.json'
            with mock.patch.object(player, 'CONFIG', path), \
                 mock.patch.object(player, 'play'):
                self.assertEqual(player.main(['off']), 0)
                self.assertFalse(player.preferences()['enabled'])
                self.assertEqual(player.main(['toggle']), 0)
                self.assertTrue(player.preferences()['enabled'])


class BatteryEdgeTests(unittest.TestCase):
    def decide(self, previous, capacity, charging=False):
        return battery.decide(previous, {'capacity': capacity, 'charging': charging})

    def test_falling_into_the_warning_band_speaks_once(self):
        state, due = self.decide({'armed': True, 'band': 'ok'}, 24)
        self.assertTrue(due)
        self.assertEqual(state['band'], 'warning')
        _, again = self.decide(state, 18)
        self.assertFalse(again, 'drifting down inside a band should stay quiet')

    def test_the_critical_band_speaks_again(self):
        state, _ = self.decide({'armed': True, 'band': 'ok'}, 24)
        state, due = self.decide(state, 9)
        self.assertTrue(due)
        self.assertEqual(state['band'], 'critical')
        _, again = self.decide(state, 4)
        self.assertFalse(again)

    def test_charging_is_always_silent_and_rearms(self):
        state, due = self.decide({'armed': True, 'band': 'critical'}, 6, charging=True)
        self.assertFalse(due)
        self.assertTrue(state['armed'])
        self.assertEqual(state['band'], 'critical')

    def test_climbing_back_above_the_warning_rearms(self):
        state, _ = self.decide({'armed': True, 'band': 'critical'}, 55)
        self.assertEqual(state['band'], 'ok')
        _, due = self.decide(state, 22)
        self.assertTrue(due)

    def test_a_full_battery_says_nothing(self):
        _, due = self.decide({'armed': True, 'band': 'ok'}, 96)
        self.assertFalse(due)

    def test_bands_follow_the_panel_thresholds(self):
        self.assertEqual(battery.band(26), 'ok')
        self.assertEqual(battery.band(25), 'warning')
        self.assertEqual(battery.band(11), 'warning')
        self.assertEqual(battery.band(10), 'critical')

    def test_the_lowest_cell_decides_and_any_charger_counts(self):
        with tempfile.TemporaryDirectory(prefix='oldbook-power-') as temporary:
            root = Path(temporary)
            for name, capacity, status in (('BAT0', 44, 'Discharging'),
                                           ('BAT1', 12, 'Discharging'),
                                           ('AC', None, None)):
                entry = root / name
                entry.mkdir()
                (entry / 'type').write_text('Battery\n' if capacity else 'Mains\n')
                if capacity:
                    (entry / 'capacity').write_text(f'{capacity}\n')
                    (entry / 'status').write_text(f'{status}\n')
            with mock.patch.object(battery, 'POWER', root):
                self.assertEqual(battery.reading(), {'capacity': 12, 'charging': False})
                (root / 'BAT0' / 'status').write_text('Charging\n')
                self.assertTrue(battery.reading()['charging'])

    def test_a_machine_without_a_battery_reports_nothing(self):
        with tempfile.TemporaryDirectory() as temporary:
            with mock.patch.object(battery, 'POWER', Path(temporary)):
                self.assertIsNone(battery.reading())


if __name__ == '__main__':
    unittest.main()
