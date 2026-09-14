"""Bed mode's ceilings, its refusals, and the list of interactions it belongs to.

Every thermal path here runs against a synthetic sysfs tree through
OLDBOOK_SMC_ROOT and OLDBOOK_HWMON_ROOT, the way test_power_mode drives the
power posture through OLDBOOK_POWER_ROOT. Nothing in this file makes this
machine warm, holds a real fan or reads a real sensor.
"""
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

REPO = Path(__file__).resolve().parents[2]
LIBRARY = REPO / 'alpine/desktop/.local/lib/oldbook'
SERVICE = REPO / 'alpine/desktop/.local/bin/oldbook-cat'
SHIPPED = REPO / 'alpine/desktop/.config/oldbook/cat.json'
sys.path.insert(0, str(LIBRARY))
import cat_bed           # noqa: E402
import cat_interactions  # noqa: E402
import cat_panel         # noqa: E402
import thermal           # noqa: E402


def load_service():
    loader = importlib.machinery.SourceFileLoader('oldbook_cat', str(SERVICE))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def sysfs(base, cpu=50.0, battery=32.0, skin=30.0, lid='open'):
    """A synthetic applesmc, coretemp and ACPI lid, with the parts under test."""
    base = Path(base)
    smc, hwmon, button = base / 'smc', base / 'hwmon', base / 'lid'
    smc.mkdir(parents=True, exist_ok=True)
    (hwmon / 'hwmon0').mkdir(parents=True, exist_ok=True)
    (hwmon / 'hwmon0/name').write_text('acpitz\n')
    (hwmon / 'hwmon0/temp1_input').write_text('99000\n')
    (hwmon / 'hwmon1').mkdir(parents=True, exist_ok=True)
    (hwmon / 'hwmon1/name').write_text('coretemp\n')
    if cpu is not None:
        (hwmon / 'hwmon1/temp1_input').write_text(f'{int(cpu * 1000)}\n')
        (hwmon / 'hwmon1/temp2_input').write_text(f'{int((cpu - 4) * 1000)}\n')
    labels = [('TB0T', battery), ('TB1T', battery), ('Ts0P', skin), ('Ts1P', skin),
              ('Ts0S', 45.0), ('TG1D', -127.0)]
    for index, (label, value) in enumerate(labels, start=1):
        (smc / f'temp{index}_label').write_text(label + '\n')
        if value is not None:
            (smc / f'temp{index}_input').write_text(f'{int(value * 1000)}\n')
    for fan in (1, 2):
        (smc / f'fan{fan}_manual').write_text('0\n')
        (smc / f'fan{fan}_output').write_text('5000\n')
        (smc / f'fan{fan}_min').write_text('2000\n')
    if lid is not None:
        (button / 'LID0').mkdir(parents=True, exist_ok=True)
        (button / 'LID0/state').write_text(f'state:      {lid}\n')
    return {'OLDBOOK_SMC_ROOT': str(smc), 'OLDBOOK_HWMON_ROOT': str(hwmon),
            'OLDBOOK_LID_ROOT': str(button)}


class SensorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.env = sysfs(self.tmp.name)
        for name, value in self.env.items():
            os.environ[name] = value
            self.addCleanup(os.environ.pop, name, None)

    def test_the_hottest_core_is_the_one_that_counts(self):
        self.assertEqual(thermal.cpu_celsius(), 50.0)

    def test_only_the_coretemp_chip_is_read(self):
        """A neighbouring hwmon reporting 99 C must not become the CPU reading."""
        self.assertEqual(thermal.cpu_celsius(), 50.0)

    def test_sensors_are_found_by_label_rather_than_by_index(self):
        values = thermal.readings()
        self.assertEqual(values['battery'], 32.0)
        self.assertEqual(values['skin'], 30.0)

    def test_the_internal_skin_keys_are_not_mistaken_for_the_surface(self):
        """Ts0S reads 45 C in the fixture and must not be the skin reading."""
        self.assertEqual(thermal.readings()['skin'], 30.0)
        self.assertNotIn('Ts0S', thermal.SKIN_LABELS)

    def test_a_disconnected_sensor_is_not_a_cold_one(self):
        self.assertIsNone(thermal.labelled_celsius(('TG1D',)))

    def test_an_absent_family_is_reported_as_unreadable(self):
        Path(self.env['OLDBOOK_HWMON_ROOT'], 'hwmon1/temp1_input').unlink()
        Path(self.env['OLDBOOK_HWMON_ROOT'], 'hwmon1/temp2_input').unlink()
        self.assertEqual(thermal.unreadable(thermal.readings()), ['cpu'])

    def test_the_lid_is_read_from_acpi_and_missing_means_unknown(self):
        self.assertIs(thermal.lid_closed(), False)
        Path(self.env['OLDBOOK_LID_ROOT'], 'LID0/state').write_text('state:      closed\n')
        self.assertIs(thermal.lid_closed(), True)
        os.environ['OLDBOOK_LID_ROOT'] = str(Path(self.tmp.name) / 'absent')
        self.assertIsNone(thermal.lid_closed())


class CeilingTests(unittest.TestCase):
    """The numbers themselves, and the orderings the safety argument rests on."""

    def values(self, cpu=50.0, battery=32.0, skin=30.0):
        return {'cpu': cpu, 'battery': battery, 'skin': skin}

    def test_every_regime_orders_its_ceilings_the_way_the_argument_needs(self):
        for name, limits in thermal.REGIMES.items():
            with self.subTest(regime=name):
                self.assertLess(limits['cpu_target'], limits['fan_release'])
                self.assertLessEqual(limits['fan_release'], limits['cpu_resume'])
                self.assertLess(limits['cpu_resume'], limits['cpu_ceiling'])
                self.assertLess(limits['cpu_ceiling'], limits['abort'])
                self.assertLess(limits['fan_hold_entry'], limits['fan_release'])

    def test_every_ceiling_is_far_below_what_the_hardware_calls_critical(self):
        """Tjmax on this part is 84 C and the critical alarm 100 C."""
        for name, limits in thermal.REGIMES.items():
            with self.subTest(regime=name):
                self.assertLessEqual(limits['abort'], 80.0)
                self.assertLessEqual(limits['cpu_ceiling'], 72.0)

    def test_a_shut_lid_is_stricter_in_every_direction(self):
        closed, opened = thermal.REGIMES['closed'], thermal.REGIMES['open']
        for key in ('cpu_target', 'cpu_ceiling', 'cpu_resume', 'fan_hold_entry',
                    'fan_release', 'battery_ceiling', 'skin_ceiling', 'abort'):
            with self.subTest(ceiling=key):
                self.assertLess(closed[key], opened[key])

    def test_the_regime_for_a_shut_lid_is_the_strict_one(self):
        self.assertEqual(thermal.regime(True), thermal.REGIMES['closed'])
        self.assertEqual(thermal.regime(False), thermal.REGIMES['open'])

    def test_a_cool_machine_runs(self):
        state, _ = thermal.verdict(self.values(), thermal.regime(False))
        self.assertEqual(state, 'run')

    def test_the_cpu_ceiling_pauses_the_load(self):
        limits = thermal.regime(False)
        state, reasons = thermal.verdict(self.values(cpu=limits['cpu_ceiling']), limits)
        self.assertEqual(state, 'coast')
        self.assertTrue(reasons)

    def test_the_pause_holds_until_the_machine_has_actually_cooled(self):
        limits = thermal.regime(False)
        warm = limits['cpu_resume'] + 1
        self.assertEqual(thermal.verdict(self.values(cpu=warm), limits, coasting=True)[0], 'coast')
        self.assertEqual(thermal.verdict(self.values(cpu=warm), limits, coasting=False)[0], 'run')
        cool = limits['cpu_resume'] - 1
        self.assertEqual(thermal.verdict(self.values(cpu=cool), limits, coasting=True)[0], 'run')

    def test_the_abort_line_stops_rather_than_pauses(self):
        limits = thermal.regime(False)
        state, reasons = thermal.verdict(self.values(cpu=limits['abort']), limits)
        self.assertEqual(state, 'stop')
        self.assertIn('abort', reasons[0])

    def test_a_warm_battery_stops_everything(self):
        limits = thermal.regime(False)
        state, reasons = thermal.verdict(
            self.values(battery=limits['battery_ceiling']), limits)
        self.assertEqual(state, 'stop')
        self.assertIn('battery', reasons[0])

    def test_a_hot_surface_stops_everything(self):
        """The cat is lying on this one."""
        limits = thermal.regime(False)
        state, reasons = thermal.verdict(self.values(skin=limits['skin_ceiling']), limits)
        self.assertEqual(state, 'stop')
        self.assertIn('skin', reasons[0])

    def test_an_unreadable_sensor_stops_rather_than_being_ignored(self):
        limits = thermal.regime(False)
        for family in thermal.FAMILIES:
            with self.subTest(family=family):
                values = self.values()
                values[family] = None
                state, reasons = thermal.verdict(values, limits)
                self.assertEqual(state, 'stop')
                self.assertIn(family, reasons[0])

    def test_one_temperature_reads_three_ways_as_the_lid_closes(self):
        """The regimes overlap exactly where the argument needs them to."""
        self.assertEqual(thermal.verdict(self.values(cpu=60.0), thermal.regime(False))[0], 'run')
        self.assertEqual(thermal.verdict(self.values(cpu=68.0), thermal.regime(False))[0], 'run')
        self.assertEqual(thermal.verdict(self.values(cpu=68.0), thermal.regime(True))[0], 'coast')
        self.assertEqual(thermal.verdict(self.values(cpu=72.0), thermal.regime(False))[0], 'coast')
        self.assertEqual(thermal.verdict(self.values(cpu=72.0), thermal.regime(True))[0], 'stop')


class FanRuleTests(unittest.TestCase):
    def values(self, cpu):
        return {'cpu': cpu, 'battery': 32.0, 'skin': 30.0}

    def test_the_hold_is_only_ever_entered_from_cool(self):
        limits = thermal.regime(False)
        self.assertEqual(thermal.fan_verdict(self.values(limits['fan_hold_entry']),
                                             limits, holding=False)[0], 'hold')
        self.assertEqual(thermal.fan_verdict(self.values(limits['fan_hold_entry'] + 1),
                                             limits, holding=False)[0], 'keep')

    def test_the_hold_is_given_up_before_the_load_is_cut(self):
        """Fans come back at fan_release, which is below the load's ceiling."""
        limits = thermal.regime(False)
        self.assertLess(limits['fan_release'], limits['cpu_ceiling'])
        hot = self.values(limits['fan_release'])
        self.assertEqual(thermal.fan_verdict(hot, limits, holding=True)[0], 'release')
        self.assertEqual(thermal.verdict(hot, limits)[0], 'run')

    def test_an_unreadable_sensor_releases_the_fans(self):
        limits = thermal.regime(False)
        action, reasons = thermal.fan_verdict({'cpu': None, 'battery': 32.0, 'skin': 30.0},
                                              limits, holding=True)
        self.assertEqual(action, 'release')
        self.assertIn('unreadable', reasons[0])

    def test_a_shut_lid_lets_the_fans_spin_much_earlier(self):
        warm = self.values(60.0)
        self.assertEqual(thermal.fan_verdict(warm, thermal.regime(True), holding=True)[0],
                         'release')
        self.assertEqual(thermal.fan_verdict(warm, thermal.regime(False), holding=True)[0],
                         'keep')


class DutyTests(unittest.TestCase):
    def values(self, cpu):
        return {'cpu': cpu, 'battery': 32.0, 'skin': 30.0}

    def test_a_cold_machine_is_pushed_harder_and_a_warm_one_less(self):
        limits = thermal.regime(False)
        self.assertGreater(thermal.duty(self.values(40.0), limits, 0.5), 0.5)
        self.assertLess(thermal.duty(self.values(70.0), limits, 0.5), 0.5)

    def test_the_duty_is_clamped_and_slew_limited(self):
        limits = thermal.regime(False)
        self.assertEqual(thermal.duty(self.values(0.0), limits, 1.0), 1.0)
        self.assertEqual(thermal.duty(self.values(120.0), limits, 0.0), 0.0)
        self.assertLessEqual(thermal.duty(self.values(0.0), limits, 0.0), 0.08 + 1e-9)

    def test_the_controller_settles_at_the_target_rather_than_oscillating(self):
        limits = thermal.regime(False)
        self.assertAlmostEqual(thermal.duty(self.values(limits['cpu_target']), limits, 0.4), 0.4)

    def test_an_unreadable_sensor_asks_for_no_load_at_all(self):
        self.assertEqual(thermal.duty({'cpu': None}, thermal.regime(False), 0.9), 0.0)


class WorkTests(unittest.TestCase):
    def test_the_first_job_with_real_work_waiting_is_the_one_chosen(self):
        jobs = [{'id': 'nothing', 'probe': ['false'], 'run': ['true']},
                {'id': 'something', 'probe': ['true'], 'run': ['true']},
                {'id': 'later', 'probe': ['true'], 'run': ['true']}]
        self.assertEqual(cat_bed.available_work(jobs)['id'], 'something')

    def test_a_job_that_cannot_say_no_is_never_chosen(self):
        """Without a probe it is not real work, it is a command that always runs."""
        self.assertIsNone(cat_bed.available_work([{'id': 'always', 'run': ['true']}]))
        self.assertIsNone(cat_bed.available_work([{'id': 'bad', 'probe': 'true', 'run': ['true']}]))

    def test_a_probe_that_will_not_run_is_skipped_rather_than_fatal(self):
        jobs = [{'id': 'broken', 'probe': ['/nonexistent/probe'], 'run': ['true']},
                {'id': 'good', 'probe': ['true'], 'run': ['true']}]
        self.assertEqual(cat_bed.available_work(jobs)['id'], 'good')

    def test_no_registered_work_means_the_plain_load(self):
        self.assertIsNone(cat_bed.available_work([]))
        self.assertIsNone(cat_bed.available_work(None))

    def test_the_shipped_registry_asks_for_no_local_compiling(self):
        """The standing rule is that packages build on the Alienware, not here."""
        document = json.loads(SHIPPED.read_text())
        self.assertEqual(document.get('work'), [])


class BedModeTests(unittest.TestCase):
    """The sitting, driven tick by tick with injected temperatures."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.now = [1000.0]
        self.bed = cat_bed.BedMode(clock=lambda: self.now[0])
        self.addCleanup(lambda: self.bed.stop('test over'))

    def values(self, cpu=50.0, battery=32.0, skin=30.0):
        return {'cpu': cpu, 'battery': battery, 'skin': skin}

    def test_a_sitting_starts_with_a_plain_load_when_no_work_is_waiting(self):
        self.assertTrue(self.bed.start())
        self.assertGreater(len(self.bed.workers), 0)
        self.assertIsNone(self.bed.job)
        self.assertIn('plain controlled load', self.bed.notes[0])

    def test_the_ceiling_stops_the_sitting_and_marks_it_a_safety_stop(self):
        self.bed.start()
        report = self.bed.update(self.values(cpu=95.0), lid_shut=False)
        self.assertFalse(report['running'])
        self.assertTrue(self.bed.safety_stop)
        self.assertEqual(self.bed.workers, [])

    def test_an_unreadable_sensor_stops_the_sitting(self):
        self.bed.start()
        report = self.bed.update({'cpu': 50.0, 'battery': None, 'skin': 30.0}, lid_shut=False)
        self.assertFalse(report['running'])
        self.assertIn('unreadable', report['stopped_reason'])
        self.assertTrue(self.bed.safety_stop)

    def test_the_load_coasts_at_the_ceiling_without_ending_the_sitting(self):
        self.bed.start()
        limits = thermal.regime(False)
        report = self.bed.update(self.values(cpu=limits['cpu_ceiling'] + 1), lid_shut=False)
        self.assertTrue(report['running'])
        self.assertTrue(report['coasting'])
        self.assertEqual(report['duty'], 0.0)

    def test_the_same_temperature_is_a_stop_with_the_lid_shut(self):
        self.bed.start()
        self.assertTrue(self.bed.update(self.values(cpu=72.0), lid_shut=False)['running'])
        report = self.bed.update(self.values(cpu=72.0), lid_shut=True)
        self.assertFalse(report['running'])
        self.assertEqual(report['regime'], 'closed')

    def test_a_sitting_cannot_outlast_its_maximum(self):
        self.bed.start()
        self.now[0] += cat_bed.MAX_SITTING + 1
        report = self.bed.update(self.values(), lid_shut=False)
        self.assertFalse(report['running'])
        self.assertIn('maximum length', report['stopped_reason'])

    def test_stopping_takes_the_load_with_it(self):
        self.bed.start()
        workers = list(self.bed.workers)
        self.assertTrue(workers)
        self.bed.stop('asked')
        for worker in workers:
            self.assertIsNotNone(worker.poll(), 'a worker outlived the sitting')

    def test_the_report_names_every_ceiling_it_is_running_under(self):
        self.bed.start()
        report = self.bed.update(self.values(), lid_shut=False)
        self.assertEqual(report['ceiling'], thermal.REGIMES['open']['cpu_ceiling'])
        self.assertEqual(report['target'], thermal.REGIMES['open']['cpu_target'])
        self.assertEqual(report['temperatures']['cpu'], 50.0)

    def test_no_fan_hold_is_taken_when_no_trusted_helper_is_installed(self):
        original = cat_bed.HELPER
        try:
            cat_bed.HELPER = str(Path(self.tmp.name) / 'absent')
            self.bed.start()
            report = self.bed.update(self.values(cpu=40.0), lid_shut=False)
            self.assertTrue(report['running'])
            self.assertFalse(report['fans_held'])
            self.assertIn('no trusted fan helper', report['fans_note'])
        finally:
            cat_bed.HELPER = original


class WorkerTests(unittest.TestCase):
    """The load itself: it obeys a duty cycle and it dies with its parent."""

    def test_a_worker_exits_when_its_pipe_closes(self):
        worker = subprocess.Popen([sys.executable, '-c', cat_bed.WORKER, '0.05'],
                                  stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                                  stderr=subprocess.DEVNULL)
        try:
            worker.stdin.write(b'0.2\n')
            worker.stdin.flush()
            time.sleep(0.3)
            self.assertIsNone(worker.poll(), 'the worker died while it was being driven')
            worker.stdin.close()
            self.assertEqual(worker.wait(timeout=10), 0)
        finally:
            if worker.poll() is None:
                worker.kill()

    def test_the_worker_runs_nice_so_the_desktop_keeps_its_priority(self):
        self.assertIn('os.nice(19)', cat_bed.WORKER)

    def test_the_load_is_spread_rather_than_pinned_to_one_core(self):
        self.assertGreaterEqual(cat_bed.WORKERS, 1)
        self.assertLessEqual(cat_bed.WORKERS, max(1, (os.cpu_count() or 2)))


class RegistryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'cat.json'
        self.path.write_text(SHIPPED.read_text())

    def test_the_shipped_registry_is_valid_and_selects_bed_mode(self):
        document = cat_interactions.load(self.path)
        cat_interactions.check(document)
        chosen = cat_interactions.selected(document)
        self.assertEqual(chosen['id'], 'bed')
        self.assertTrue(cat_interactions.implemented(chosen))

    def test_the_feature_ships_switched_off(self):
        self.assertFalse(cat_interactions.enabled(cat_interactions.load(self.path)))

    def test_adding_an_interaction_is_adding_an_entry(self):
        cat_interactions.add({'id': 'purr', 'title': 'Purr back', 'date': '2026-09-10',
                              'handler': 'purr', 'summary': 'Not written yet.'},
                             path=self.path, select_it=True)
        document = cat_interactions.load(self.path)
        self.assertEqual(document['selected'], 'purr')
        self.assertFalse(cat_interactions.implemented(cat_interactions.selected(document)))

    def test_an_unimplemented_selection_is_listable_and_harmless(self):
        cat_interactions.add({'id': 'purr', 'title': 'Purr back', 'date': '2026-09-10',
                              'handler': 'purr', 'summary': 'Not written yet.'},
                             path=self.path, select_it=True)
        self.assertEqual(len(cat_interactions.entries(cat_interactions.load(self.path))), 2)

    def test_cycling_wraps_through_the_list(self):
        cat_interactions.add({'id': 'purr', 'title': 'Purr', 'date': '2026-09-10',
                              'summary': 'x'}, path=self.path)
        self.assertEqual(cat_interactions.cycle(1, self.path)['selected'], 'purr')
        self.assertEqual(cat_interactions.cycle(1, self.path)['selected'], 'bed')
        self.assertEqual(cat_interactions.cycle(-1, self.path)['selected'], 'purr')

    def test_removing_the_selected_entry_leaves_a_valid_selection(self):
        cat_interactions.add({'id': 'purr', 'title': 'Purr', 'date': '2026-09-10',
                              'summary': 'x'}, path=self.path)
        document = cat_interactions.remove('bed', self.path)
        self.assertEqual(document['selected'], 'purr')

    def test_a_duplicate_or_unknown_id_is_refused(self):
        with self.assertRaises(ValueError):
            cat_interactions.add({'id': 'bed', 'title': 'x', 'date': '2026-09-10',
                                  'summary': 'x'}, path=self.path)
        with self.assertRaises(ValueError):
            cat_interactions.select('absent', self.path)
        with self.assertRaises(ValueError):
            cat_interactions.remove('absent', self.path)

    def test_a_malformed_registry_falls_back_rather_than_half_reading(self):
        self.path.write_text('{"version": 9}')
        self.assertEqual(cat_interactions.load(self.path), cat_interactions.FALLBACK)
        self.path.write_text('not json at all')
        self.assertEqual(cat_interactions.load(self.path), cat_interactions.FALLBACK)

    def test_the_fallback_is_itself_a_valid_registry_selecting_bed(self):
        cat_interactions.check(cat_interactions.FALLBACK)
        self.assertTrue(cat_interactions.implemented(
            cat_interactions.selected(cat_interactions.FALLBACK)))

    def test_a_selection_that_is_not_in_the_list_is_refused(self):
        document = json.loads(self.path.read_text())
        document['selected'] = 'ghost'
        with self.assertRaises(ValueError):
            cat_interactions.check(document)


class RefusalTests(unittest.TestCase):
    """The gates that decide whether bed mode may begin at all."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.env = sysfs(self.root)
        for name, value in self.env.items():
            os.environ[name] = value
            self.addCleanup(os.environ.pop, name, None)
        self.config = self.root / 'cat.json'
        document = json.loads(SHIPPED.read_text())
        document['enabled'] = True
        self.config.write_text(json.dumps(document))
        self.service = load_service()

    def power(self, mains=True, capacity=80):
        supply = self.root / 'power'
        for name in ('ADP1', 'BAT0'):
            (supply / name).mkdir(parents=True, exist_ok=True)
        (supply / 'ADP1/type').write_text('Mains\n')
        (supply / 'ADP1/online').write_text('1\n' if mains else '0\n')
        (supply / 'BAT0/type').write_text('Battery\n')
        (supply / 'BAT0/capacity').write_text(f'{capacity}\n')
        (supply / 'BAT0/status').write_text('Charging\n' if mains else 'Discharging\n')
        os.environ['OLDBOOK_POWER_ROOT'] = str(supply)
        os.environ['XDG_STATE_HOME'] = str(self.root / 'state')
        self.addCleanup(os.environ.pop, 'OLDBOOK_POWER_ROOT', None)
        self.addCleanup(os.environ.pop, 'XDG_STATE_HOME', None)

    def worker(self):
        service = self.service.Service(config=self.config)
        self.addCleanup(lambda: service.bed and service.bed.stop('test over'))
        return service

    def bed_state(self, service, present=True, lid_shut=False, armed=True):
        """One tick of the bed decision, with the countdown already served.

        `armed` skips the twenty-second wait, which has tests of its own in
        CountdownTests. Every refusal in this class is a refusal whether or not
        the wait has been served, so re-serving it in each of them would test
        the clock rather than the gate.
        """
        document = cat_interactions.load(self.config)
        chosen = cat_interactions.selected(document)
        if armed and service.arming_since is None:
            service.arming_since = service.clock() - self.service.ARMING_SECONDS
        return service.bed_tick(document, chosen, present, True, lid_shut)

    def test_bed_mode_never_runs_on_battery(self):
        """Warming a laptop for a cat off mains is a flat battery."""
        self.power(mains=False, capacity=80)
        state = self.bed_state(self.worker())
        self.assertFalse(state['running'])
        self.assertEqual(state['refusal'], 'not on mains')

    def test_the_cord_is_what_permits_it(self):
        self.power(mains=True)
        state = self.bed_state(self.worker())
        self.assertTrue(state['running'], state)

    def test_a_hand_held_power_override_also_refuses(self):
        """oldbook-power-mode override battery-low must take bed mode with it."""
        self.power(mains=True)
        import power_source
        power_source.write_override('battery-low')
        self.addCleanup(power_source.write_override, None)
        self.assertEqual(self.bed_state(self.worker())['refusal'], 'not on mains')

    def test_no_cat_means_no_warmth(self):
        self.power(mains=True)
        self.assertEqual(self.bed_state(self.worker(), present=False)['refusal'],
                         'no cat is present')

    def test_a_feature_switched_off_refuses_even_with_a_cat_on_the_keys(self):
        self.power(mains=True)
        service = self.worker()
        document = cat_interactions.load(self.config)
        state = service.bed_tick(document, cat_interactions.selected(document),
                                 True, False, False)
        self.assertEqual(state['refusal'], 'the feature is off')

    def test_an_unimplemented_selection_does_nothing_at_all(self):
        self.power(mains=True)
        cat_interactions.add({'id': 'purr', 'title': 'Purr', 'date': '2026-09-10',
                              'handler': 'purr', 'summary': 'x'},
                             path=self.config, select_it=True)
        state = self.bed_state(self.worker())
        self.assertFalse(state['running'])
        self.assertIn('not bed mode', state['refusal'])

    def test_a_ceiling_stop_buys_a_cooldown_and_then_a_latch(self):
        self.power(mains=True)
        service = self.worker()
        sysfs(self.root, cpu=95.0)
        self.assertFalse(self.bed_state(service)['running'])
        self.assertEqual(service.safety_stops, 1)
        sysfs(self.root, cpu=45.0)
        self.assertIn('resting', self.bed_state(service)['refusal'])
        service.cooldown_until = 0.0
        sysfs(self.root, cpu=95.0)
        self.bed_state(service)
        self.assertTrue(service.latched)
        service.cooldown_until = 0.0
        sysfs(self.root, cpu=45.0)
        self.assertIn('latched off', self.bed_state(service)['refusal'])

    def test_a_sitting_that_ran_its_full_length_rests_before_another_begins(self):
        """Without this the next tick would simply start the three hours again."""
        self.power(mains=True)
        service = self.worker()
        self.assertTrue(self.bed_state(service)['running'])
        service.bed.started_at -= cat_bed.MAX_SITTING + 1
        self.assertFalse(self.bed_state(service)['running'])
        refusal = self.bed_state(service)['refusal']
        self.assertIn('resting', refusal)
        self.assertIn('maximum length', refusal)
        self.assertEqual(service.safety_stops, 0)
        self.assertFalse(service.latched)

    def test_an_unknown_lid_is_treated_as_a_shut_one(self):
        self.power(mains=True)
        service = self.worker()
        sysfs(self.root, cpu=72.0)
        state = self.bed_state(service, lid_shut=None)
        self.assertEqual(state['regime'], 'closed')
        self.assertFalse(state['running'])


class CountdownTests(unittest.TestCase):
    """No heat is made until the countdown has been served in full.

    The user asked to be told clearly, before it happens, that the machine is
    about to be run warm. A countdown that counts down to something which has
    already started would be a decoration; this one is the real wait, and every
    precondition has to keep holding for the whole of it.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        for name, value in sysfs(self.root).items():
            os.environ[name] = value
            self.addCleanup(os.environ.pop, name, None)
        supply = self.root / 'power'
        (supply / 'ADP1').mkdir(parents=True)
        (supply / 'ADP1/type').write_text('Mains\n')
        (supply / 'ADP1/online').write_text('1\n')
        os.environ['OLDBOOK_POWER_ROOT'] = str(supply)
        os.environ['XDG_STATE_HOME'] = str(self.root / 'state')
        os.environ['XDG_RUNTIME_DIR'] = str(self.root / 'run')
        (self.root / 'run').mkdir(mode=0o700)
        for name in ('OLDBOOK_POWER_ROOT', 'XDG_STATE_HOME', 'XDG_RUNTIME_DIR'):
            self.addCleanup(os.environ.pop, name, None)
        self.config = self.root / 'cat.json'
        document = json.loads(SHIPPED.read_text())
        document['enabled'] = True
        self.config.write_text(json.dumps(document))
        self.service = load_service()
        self.now = 1000.0

    def worker(self):
        service = self.service.Service(config=self.config, clock=lambda: self.now)
        self.addCleanup(lambda: service.bed and service.bed.stop('test over'))
        return service

    def tick(self, service, present=True):
        document = cat_interactions.load(self.config)
        return service.bed_tick(document, cat_interactions.selected(document),
                                present, True, False)

    def pretend_cat(self, service):
        """A locked session with a cat on it, for the whole-tick tests below.

        The load is replaced by a worker that only waits on its pipe. These
        tests are about what the daemon decides and what it draws; making this
        laptop hot to prove it would be both slow and, on this machine, rude.
        """
        idle = 'import sys\nfor line in sys.stdin:\n    pass\n'
        self.addCleanup(setattr, cat_bed, 'WORKER', cat_bed.WORKER)
        cat_bed.WORKER = idle
        # No real lid inhibitor either: a whole tick would otherwise leave an
        # elogind-inhibit behind for every test that ran one.
        held = self.service.hold_lid

        def fake_hold():
            read_fd, write_fd = os.pipe()
            os.close(read_fd)
            return write_fd

        self.service.hold_lid = fake_hold
        self.addCleanup(setattr, self.service, 'hold_lid', held)
        self.addCleanup(lambda: service.lid(False))
        service.presence.judge = lambda now: {
            'present': True, 'deciding': True, 'vetoed': False, 'confidence': 1.0,
            'keys_down': 6, 'patch': True, 'signals': [], 'corroboration': ['patch']}
        original = self.service.session_locked
        self.service.session_locked = lambda: True
        self.addCleanup(setattr, self.service, 'session_locked', original)
        service.arming_since = service.clock() - self.service.ARMING_SECONDS
        self.addCleanup(lambda: service.bed and service.bed.stop('test over'))

    def test_nothing_is_started_until_the_wait_has_been_served(self):
        service = self.worker()
        state = self.tick(service)
        self.assertTrue(state['arming'])
        self.assertFalse(state['running'])
        self.assertIsNone(service.bed)
        self.assertEqual(state['arming_seconds'], self.service.ARMING_SECONDS)
        self.assertAlmostEqual(state['seconds_left'], self.service.ARMING_SECONDS)

        self.now += self.service.ARMING_SECONDS - 1
        self.assertTrue(self.tick(service)['arming'])
        self.assertIsNone(service.bed)

        self.now += 2
        self.assertTrue(self.tick(service)['running'])
        self.assertIsNotNone(service.bed)

    def test_the_countdown_counts_down(self):
        service = self.worker()
        seen = []
        for _ in range(4):
            seen.append(self.tick(service)['seconds_left'])
            self.now += 3
        self.assertEqual(seen, sorted(seen, reverse=True))
        self.assertTrue(all(value > 0 for value in seen))

    def test_a_lapse_in_presence_restarts_the_wait_from_the_beginning(self):
        """Half a countdown is not credit against the next one."""
        service = self.worker()
        self.tick(service)
        self.now += self.service.ARMING_SECONDS - 2
        self.tick(service)
        self.assertEqual(self.tick(service, present=False)['refusal'], 'no cat is present')
        self.assertIsNone(service.arming_since)
        self.now += 1
        state = self.tick(service)
        self.assertTrue(state['arming'])
        self.assertAlmostEqual(state['seconds_left'], self.service.ARMING_SECONDS)

    def test_a_refusal_during_the_wait_never_leaves_it_part_served(self):
        service = self.worker()
        self.tick(service)
        self.now += 10
        (self.root / 'power/ADP1/online').write_text('0\n')
        self.assertEqual(self.tick(service)['refusal'], 'not on mains')
        (self.root / 'power/ADP1/online').write_text('1\n')
        self.assertAlmostEqual(self.tick(service)['seconds_left'],
                               self.service.ARMING_SECONDS)

    def test_the_loop_wakes_faster_only_while_the_countdown_is_running(self):
        service = self.worker()
        self.assertEqual(service.wait(), self.service.TICK)
        self.tick(service)
        self.assertEqual(service.wait(), self.service.COUNTDOWN_TICK)
        self.assertLess(self.service.COUNTDOWN_TICK, self.service.TICK)

    def test_a_failure_drawing_the_panel_never_disturbs_the_warming(self):
        """The picture is the least important thing in this daemon.

        Bed mode holds the fans down on a hot laptop; a traceback out of a
        cairo call must not be able to interrupt the loop that is watching the
        ceilings, and it must not leave a stale hearth on the lock screen.
        """
        service = self.worker()
        self.pretend_cat(service)
        broken, cleared = [], []
        original, clearer = cat_panel.describe, cat_panel.clear
        cat_panel.describe = lambda *a, **k: broken.append(1) or (_ for _ in ()).throw(
            RuntimeError('no cairo today'))
        cat_panel.clear = lambda *a, **k: cleared.append(1)
        self.addCleanup(setattr, cat_panel, 'describe', original)
        self.addCleanup(setattr, cat_panel, 'clear', clearer)
        record = service.tick(service.clock())
        self.assertTrue(broken)
        self.assertTrue(cleared, 'a panel that cannot be drawn is taken down')
        self.assertTrue(record['bed']['running'], record['bed'])
        self.assertIn('thermal', record)
        self.assertTrue(service.panel_complained)

    def test_one_reading_serves_the_controller_and_the_picture_alike(self):
        service = self.worker()
        self.pretend_cat(service)
        seen = []
        original = thermal.readings
        thermal.readings = lambda *a, **k: (seen.append(1),
                                            original(*a, **k))[1]
        self.addCleanup(setattr, thermal, 'readings', original)
        record = service.tick(service.clock())
        self.assertEqual(len(seen), 1, 'the sensors are read exactly once a tick')
        self.assertEqual(record['thermal']['temperatures'],
                         record['bed']['temperatures'])

    def test_the_countdown_carries_the_readings_it_was_given(self):
        """The panel draws from these; nothing downstream reads a sensor again."""
        service = self.worker()
        values = {'cpu': 44.0, 'battery': 31.0, 'skin': 29.0}
        document = cat_interactions.load(self.config)
        state = service.bed_tick(document, cat_interactions.selected(document),
                                 True, True, False, values)
        self.assertEqual(state['temperatures'], values)
        self.assertEqual(state['regime'], 'open')


class HearthTests(unittest.TestCase):
    """The picture the lock screen shows, and the mapping it claims to draw."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / 'run').mkdir(mode=0o700)
        os.environ['XDG_RUNTIME_DIR'] = str(self.root / 'run')
        self.addCleanup(os.environ.pop, 'XDG_RUNTIME_DIR', None)
        self.palette = {'background': '#282828', 'background_hard': '#1d2021',
                        'surface': '#3c3836', 'foreground': '#ebdbb2',
                        'muted': '#928374', 'border': '#504945',
                        'accent': '#fabd2f', 'accent_secondary': '#fabd2f'}

    def record(self, bed, cpu=41.0, battery=30.0, skin=28.0, lid='open', **extra):
        limits = thermal.regime(lid == 'closed')
        base = {'present': True, 'locked': True, 'enabled': True, 'lid': lid, 'bed': bed,
                'thermal': {'regime': 'closed' if lid == 'closed' else 'open',
                            'temperatures': {'cpu': cpu, 'battery': battery, 'skin': skin},
                            'ceilings': dict(limits), 'unreadable': []}}
        base.update(extra)
        return base

    def warming(self, **kw):
        return cat_panel.describe(self.record(
            {'running': True, 'coasting': False, 'duty': 0.5, 'fans_held': True}, **kw))

    def test_the_scale_runs_from_a_stated_floor_to_the_regimes_own_abort_line(self):
        """The top of the hearth is where the sitting ends, not an idea of hot."""
        panel = self.warming()
        self.assertEqual(panel['floor'], cat_panel.SCALE_FLOOR)
        self.assertEqual(panel['stop'], thermal.REGIMES['open']['abort'])
        self.assertEqual(panel['ease'], thermal.REGIMES['open']['cpu_ceiling'])
        self.assertEqual(panel['target'], thermal.REGIMES['open']['cpu_target'])
        closed = self.warming(lid='closed')
        self.assertEqual(closed['stop'], thermal.REGIMES['closed']['abort'])
        self.assertLess(closed['stop'], panel['stop'])

    def test_the_embers_are_the_measured_temperature_on_that_scale(self):
        self.assertEqual(cat_panel.ember_count(self.warming(cpu=cat_panel.SCALE_FLOOR)), 0)
        full = self.warming(cpu=thermal.REGIMES['open']['abort'])
        self.assertEqual(cat_panel.ember_count(full), cat_panel.EMBER_CELLS)
        middle = self.warming(cpu=(cat_panel.SCALE_FLOOR
                                   + thermal.REGIMES['open']['abort']) / 2)
        self.assertEqual(cat_panel.ember_count(middle), cat_panel.EMBER_CELLS // 2)
        # Past the abort line it is still the abort line: nothing is drawn as
        # hotter than the temperature at which this feature gives up.
        self.assertEqual(cat_panel.ember_count(self.warming(cpu=140.0)),
                         cat_panel.EMBER_CELLS)

    def test_an_unreadable_cpu_lights_nothing_rather_than_reading_as_cold(self):
        self.assertEqual(cat_panel.ember_count(self.warming(cpu=None)), 0)

    def test_the_flame_is_the_effort_and_dies_while_the_embers_stay_lit(self):
        hot = cat_panel.describe(self.record(
            {'running': True, 'coasting': True, 'duty': 0.0}, cpu=70.0))
        self.assertEqual(cat_panel.flame_blocks(hot), 0)
        self.assertGreater(cat_panel.ember_count(hot), 0)
        pushing = cat_panel.describe(self.record(
            {'running': True, 'coasting': False, 'duty': 1.0}, cpu=70.0))
        self.assertEqual(cat_panel.flame_blocks(pushing), cat_panel.FLAME_STEPS)

    def test_nothing_is_drawn_without_a_cat_a_lock_and_the_feature_on(self):
        for change in ({'present': False}, {'locked': False}, {'enabled': False}):
            with self.subTest(change=change):
                self.assertIsNone(cat_panel.describe(self.record(
                    {'running': True, 'duty': 0.5}, **change)))
        self.assertIsNone(cat_panel.describe({'present': True, 'locked': True,
                                              'enabled': True, 'bed': {}}))

    def test_no_sensor_is_read_a_second_time(self):
        """The panel and the controller must never disagree about a temperature."""
        seen = []
        original = thermal.readings
        thermal.readings = lambda *a, **k: seen.append(1) or {'cpu': 1.0}
        try:
            panel = cat_panel.describe(self.record(
                {'running': True, 'duty': 0.5}, cpu=57.0))
            cat_panel.publish(panel, self.palette, scale=1)
        finally:
            thermal.readings = original
        self.assertEqual(seen, [])
        self.assertEqual(panel['cpu'], 57.0)

    def test_the_state_file_takes_the_ring_away_while_it_is_up(self):
        """The ring is the one thing on the lock screen that counts keystrokes."""
        panel = self.warming()
        cat_panel.publish(panel, self.palette, scale=1)
        state = cat_panel.read_state()
        self.assertEqual(state['ring'], '0')
        self.assertEqual(state['place'], 'above')
        self.assertEqual(state['panel'], '1')
        self.assertEqual(state['image'], cat_panel.IMAGE_NAMES[0])
        self.assertIn(int(state['stale']), range(1, 60))
        image = self.root / 'run/oldbook' / state['image']
        self.assertTrue(image.is_file())
        self.assertEqual(oct(image.stat().st_mode & 0o777), '0o600')

    def test_the_serial_moves_only_when_the_picture_does(self):
        first = cat_panel.publish(self.warming(cpu=50.0), self.palette, scale=1)
        again = cat_panel.publish(self.warming(cpu=50.0), self.palette, scale=1)
        self.assertEqual(first, again)
        moved = cat_panel.publish(self.warming(cpu=64.0), self.palette, scale=1)
        self.assertEqual(moved, first + 1)
        # And it lands in the other slot, so the locker still has the picture
        # it is fading away from.
        self.assertEqual(cat_panel.read_state()['image'], cat_panel.IMAGE_NAMES[1])

    def test_the_stamp_is_refreshed_without_redrawing_anything(self):
        panel = self.warming(cpu=50.0)
        cat_panel.publish(panel, self.palette, scale=1, now=1000)
        image = self.root / 'run/oldbook' / cat_panel.read_state()['image']
        written = image.stat().st_mtime_ns
        cat_panel.publish(panel, self.palette, scale=1, now=1200)
        self.assertEqual(cat_panel.read_state()['stamp'], '1200')
        self.assertEqual(image.stat().st_mtime_ns, written)

    def test_a_still_panel_is_asked_for_off_mains(self):
        """The ladder entry this wants is cat-hearth; below mains it stops moving."""
        self.assertEqual(cat_panel.LADDER_EFFECT, 'cat-hearth')
        quiet = cat_panel.describe(self.record({'running': False,
                                                'refusal': 'not on mains'}),
                                   posture='battery')
        cat_panel.publish(quiet, self.palette, scale=1)
        state = cat_panel.read_state()
        self.assertEqual(state['fade'], '0')
        self.assertEqual(int(state['poll']), cat_panel.QUIET_POLL_MS)
        cat_panel.publish(self.warming(), self.palette, scale=1)
        self.assertEqual(cat_panel.read_state()['fade'], str(cat_panel.MAINS_FADE_MS))

    def test_taking_the_panel_down_is_removing_the_file(self):
        cat_panel.publish(self.warming(), self.palette, scale=1)
        self.assertTrue(cat_panel.state_path().is_file())
        cat_panel.publish(None, self.palette, scale=1)
        self.assertFalse(cat_panel.state_path().is_file())

    def test_the_switch_is_findable_and_defaults_to_showing(self):
        self.assertTrue(cat_panel.enabled({'version': 1}))
        self.assertFalse(cat_panel.enabled({'version': 1, 'panel': False}))
        os.environ['OLDBOOK_CAT_PANEL'] = '0'
        self.addCleanup(os.environ.pop, 'OLDBOOK_CAT_PANEL', None)
        self.assertFalse(cat_panel.enabled({'version': 1}))

    def test_the_picture_carries_no_finer_clock_than_a_second_or_a_degree(self):
        """A visualisation that tracked tenths would be a timing channel."""
        base = self.record({'running': True, 'coasting': False, 'duty': 0.5}, cpu=57.1)
        drift = self.record({'running': True, 'coasting': False, 'duty': 0.5}, cpu=57.4)
        self.assertEqual(cat_panel.content_key(cat_panel.describe(base)),
                         cat_panel.content_key(cat_panel.describe(drift)))
        counting = self.record({'running': False, 'arming': True,
                                'seconds_left': 6.4, 'arming_seconds': 20.0})
        later = self.record({'running': False, 'arming': True,
                             'seconds_left': 6.1, 'arming_seconds': 20.0})
        self.assertEqual(cat_panel.describe(counting)['countdown'],
                         cat_panel.describe(later)['countdown'])

    def test_every_state_renders_a_real_image(self):
        cases = {
            'countdown': {'running': False, 'arming': True, 'seconds_left': 6.4,
                          'arming_seconds': 20.0},
            'warming': {'running': True, 'coasting': False, 'duty': 0.6, 'fans_held': True},
            'coasting': {'running': True, 'coasting': True, 'duty': 0.0},
            'holding': {'running': False, 'refusal': 'not on mains'},
        }
        for name, bed in cases.items():
            with self.subTest(state=name):
                panel = cat_panel.describe(self.record(bed, cpu=57.0))
                target = self.root / f'{name}.png'
                cat_panel.render(panel, self.palette, 2, target)
                self.assertTrue(target.is_file())
                self.assertGreater(target.stat().st_size, 1000)


class ServiceRecordTests(unittest.TestCase):
    """What the daemon publishes, and the one obvious way to stop it."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / 'run').mkdir(mode=0o700)
        self.env = dict(os.environ, **sysfs(self.root))
        self.env.update(XDG_RUNTIME_DIR=str(self.root / 'run'),
                        XDG_CONFIG_HOME=str(self.root / 'config'),
                        XDG_STATE_HOME=str(self.root / 'state'),
                        OLDBOOK_INPUT_DEVICES='',
                        OLDBOOK_LOCK_RECORD=str(self.root / 'absent.json'))

    def command(self, *arguments, **overrides):
        return subprocess.run([str(SERVICE), *arguments], env=dict(self.env, **overrides),
                              capture_output=True, text=True, timeout=60)

    def test_status_runs_on_a_machine_with_no_watcher_and_names_the_stop_command(self):
        done = self.command('status')
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn('oldbook-cat stop', done.stdout)
        self.assertIn('no watcher running', done.stdout)

    def test_status_json_carries_the_ceilings_and_the_readings(self):
        done = self.command('status', '--json')
        self.assertEqual(done.returncode, 0, done.stderr)
        report = json.loads(done.stdout)
        self.assertEqual(report['selected'], 'bed')
        self.assertEqual(report['thermal']['temperatures']['cpu'], 50.0)
        self.assertEqual(report['thermal']['ceilings']['cpu_ceiling'],
                         thermal.REGIMES['open']['cpu_ceiling'])

    def test_the_interactions_list_marks_the_selected_one(self):
        done = self.command('interactions')
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn('* bed', done.stdout)

    def test_stop_disables_the_feature_and_says_what_it_did(self):
        self.command('on')
        done = self.command('stop')
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn('bed mode is off', done.stdout)
        config = Path(self.env['XDG_CONFIG_HOME']) / 'oldbook/cat.json'
        self.assertFalse(json.loads(config.read_text())['enabled'])

    def test_select_and_next_move_the_selection(self):
        entry = self.root / 'purr.json'
        entry.write_text(json.dumps({'id': 'purr', 'title': 'Purr', 'date': '2026-09-10',
                                     'summary': 'x'}))
        self.command('add', str(entry))
        self.assertIn('* purr', self.command('next').stdout)
        self.assertIn('* bed', self.command('select', 'bed').stdout)

    def test_the_watcher_publishes_a_record_with_a_last_seen_field(self):
        done = self.command('run', '--once', OLDBOOK_INPUT_DEVICES='/dev/null')
        self.assertEqual(done.returncode, 0, done.stderr)
        record = json.loads((self.root / 'run/oldbook/cat.json').read_text())
        self.assertIn('last_seen', record)
        self.assertIn('recent_window', record)
        self.assertEqual(record['recent_window'], 30.0)
        self.assertFalse(record['present'])

    def test_an_unlocked_session_is_never_a_cat(self):
        """The largest single guard against warming a machine someone is using."""
        record = self.root / 'run/lock-ready.json'
        record.parent.mkdir(parents=True, exist_ok=True)
        record.write_text(json.dumps({'process': {'pid': os.getpid()}}))
        service = load_service()
        os.environ['OLDBOOK_LOCK_RECORD'] = str(self.root / 'absent.json')
        self.addCleanup(os.environ.pop, 'OLDBOOK_LOCK_RECORD', None)
        self.assertFalse(service.session_locked())
        os.environ['OLDBOOK_LOCK_RECORD'] = str(record)
        self.assertTrue(service.session_locked())

    def test_a_lock_record_naming_a_dead_process_does_not_count_as_locked(self):
        record = self.root / 'run/lock-ready.json'
        record.parent.mkdir(parents=True, exist_ok=True)
        record.write_text(json.dumps({'process': {'pid': 0x7FFFFFFE}}))
        service = load_service()
        os.environ['OLDBOOK_LOCK_RECORD'] = str(record)
        self.addCleanup(os.environ.pop, 'OLDBOOK_LOCK_RECORD', None)
        self.assertFalse(service.session_locked())


class LidTests(unittest.TestCase):
    """A cat within the last thirty seconds keeps the lid from sleeping the machine."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / 'run').mkdir(mode=0o700)
        for name, value in sysfs(self.root).items():
            os.environ[name] = value
            self.addCleanup(os.environ.pop, name, None)
        os.environ['XDG_RUNTIME_DIR'] = str(self.root / 'run')
        os.environ['OLDBOOK_LOCK_RECORD'] = str(self.root / 'absent.json')
        self.addCleanup(os.environ.pop, 'OLDBOOK_LOCK_RECORD', None)
        self.config = self.root / 'cat.json'
        # An interaction with no implementation, so the lid policy can be
        # exercised without ever starting a real load on this machine.
        self.config.write_text(json.dumps(
            {'version': 1, 'enabled': True, 'selected': 'purr', 'work': [],
             'interactions': [{'id': 'purr', 'title': 'Purr', 'date': '2026-09-10',
                               'handler': 'purr', 'summary': 'x'}]}))
        self.service_module = load_service()
        self.held = []
        self.service_module.hold_lid = self.fake_hold
        self.service = self.service_module.Service(config=self.config)
        self.addCleanup(lambda: self.service.lid(False))

    def fake_hold(self):
        read_fd, write_fd = os.pipe()
        os.close(read_fd)
        self.held.append(write_fd)
        return write_fd

    def closed(self, descriptor):
        try:
            os.fstat(descriptor)
        except OSError:
            return True
        return False

    def seen(self, seconds_ago):
        self.service.last_seen_wall = time.time() - seconds_ago

    def test_a_cat_seen_just_now_holds_the_lid_switch(self):
        self.seen(1)
        record = self.service.tick(1000.0)
        self.assertTrue(record['lid_inhibited'])
        self.assertEqual(len(self.held), 1)
        self.assertFalse(self.closed(self.held[0]))

    def test_the_inhibitor_goes_the_moment_the_thirty_seconds_lapse(self):
        self.seen(1)
        self.service.tick(1000.0)
        self.seen(31)
        record = self.service.tick(1002.0)
        self.assertFalse(record['lid_inhibited'])
        self.assertTrue(self.closed(self.held[0]),
                        'the inhibitor pipe was left open past the window')

    def test_the_window_is_the_thirty_seconds_the_user_asked_for(self):
        self.seen(29)
        self.assertTrue(self.service.tick(1000.0)['lid_inhibited'])
        self.service.lid(False)
        self.seen(30.5)
        self.assertFalse(self.service.tick(1001.0)['lid_inhibited'])

    def test_a_feature_switched_off_never_holds_the_lid(self):
        document = json.loads(self.config.read_text())
        document['enabled'] = False
        self.config.write_text(json.dumps(document))
        self.seen(1)
        self.assertFalse(self.service.tick(1000.0)['lid_inhibited'])
        self.assertEqual(self.held, [])

    def test_a_cat_that_was_never_seen_holds_nothing(self):
        self.assertFalse(self.service.tick(1000.0)['lid_inhibited'])
        self.assertEqual(self.held, [])

    def test_the_inhibitor_is_the_lid_switch_one_and_it_blocks(self):
        argv = self.service_module.LID_HOLDER
        self.assertIn('--what=handle-lid-switch', argv)
        self.assertIn('--mode=block', argv)
        self.assertIn('--who=oldbook-cat', argv)
        self.assertEqual(argv[-2:], ['--', 'cat'])

    def test_the_holder_waits_on_a_pipe_rather_than_tracking_a_process(self):
        """The same guarantee oldbook-lock uses: the pipe closes with us."""
        source = SERVICE.read_text()
        self.assertIn('os.pipe()', source)
        self.assertIn('stdin=read_fd', source)

    def test_no_inhibitor_on_the_host_means_the_lid_still_suspends(self):
        module = load_service()
        module.INHIBITORS = ('a-command-that-is-not-installed',)
        self.assertIsNone(module.hold_lid())


if __name__ == '__main__':
    unittest.main()
