"""One loading language: stepped, themed, bounded, and quiet when it must be.

Every line the library can draw is produced here as a plain string and compared
as one. Nothing in these checks opens a terminal, because a captured escape
sequence proves the rendering and never proves the frame; the physical look of
a build scrolling past on the laptop stays the user's check.
"""
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[2]
LIBRARY = REPO / 'alpine/desktop/.local/lib/oldbook'


def load():
    import sys
    sys.path.insert(0, str(LIBRARY))
    spec = importlib.util.spec_from_file_location('loading', LIBRARY / 'loading.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


m = load()


class Screen(io.StringIO):
    """A stream that claims to be a terminal, so the live path can be read back."""

    encoding = 'UTF-8'

    def __init__(self, tty=True):
        super().__init__()
        self.tty = tty

    def isatty(self):
        return self.tty


def probe(stream=None, **keywords):
    """A terminal that decides colour and repainting for itself, as it ships."""
    keywords.setdefault('width', 60)
    keywords.setdefault('environ', {'TERM': 'foot', 'LANG': 'en_US.UTF-8'})
    keywords.setdefault('allows', lambda effect: True)
    return m.Terminal(Screen() if stream is None else stream, **keywords)


def terminal(stream=None, **keywords):
    """A live terminal with the colour off, so the lines read as themselves."""
    keywords.setdefault('width', 60)
    keywords.setdefault('colour', False)
    keywords.setdefault('environ', {'TERM': 'foot', 'LANG': 'en_US.UTF-8'})
    keywords.setdefault('allows', lambda effect: True)
    return m.Terminal(Screen() if stream is None else stream, **keywords)


def ascii_terminal(**keywords):
    """A terminal that cannot show the drawing glyphs, so the understudies run."""
    stream = Screen()
    stream.encoding = 'ANSI_X3.4-1968'
    keywords.setdefault('environ', {'TERM': 'foot', 'LANG': 'C'})
    return probe(stream, **keywords)


def clock():
    """A hand-wound clock, so frame budgets are decided rather than raced."""
    now = [0.0]

    def read():
        return now[0]

    def advance(seconds):
        now[0] += seconds
    read.advance = advance
    return read


def visible(text):
    """The scrollback a run leaves: the final content of each committed line."""
    chunks = text.split('\n')[:-1] if text.endswith('\n') else text.split('\n')
    return [chunk.split('\r')[-1].replace('\033[2K', '') for chunk in chunks]


def frames(text):
    """Every repaint in order, which is what a frame budget is counted in."""
    return [chunk.replace('\033[2K', '')
            for chunk in text.replace('\n', '\r').split('\r') if chunk]


class BarRendering(unittest.TestCase):
    """The bar is segments, and a segment either landed or it did not."""

    def test_segments_fill_in_proportion_to_the_work(self):
        self.assertEqual(m.render_bar(0, 8, width=8), '▱' * 8)
        self.assertEqual(m.render_bar(2, 8, width=8), '▰▰' + '▱' * 6)
        self.assertEqual(m.render_bar(8, 8, width=8), '▰' * 8)

    def test_the_last_segment_lands_only_when_the_work_is_actually_done(self):
        self.assertEqual(m.render_bar(999, 1000, width=24).count('▰'), 23)
        self.assertEqual(m.render_bar(1000, 1000, width=24).count('▰'), 24)

    def test_counts_outside_the_total_are_clamped_rather_than_believed(self):
        self.assertEqual(m.render_bar(-5, 8, width=8), '▱' * 8)
        self.assertEqual(m.render_bar(80, 8, width=8), '▰' * 8)

    def test_work_with_no_total_draws_an_empty_bar_instead_of_dividing_by_zero(self):
        self.assertEqual(m.render_bar(3, 0, width=4), '▱▱▱▱')

    def test_a_bar_needs_somewhere_to_draw(self):
        with self.assertRaises(ValueError):
            m.render_bar(1, 2, width=0)

    def test_a_terminal_without_the_glyphs_still_gets_segments(self):
        self.assertEqual(m.render_bar(1, 4, width=4, segments=m.ASCII_SEGMENTS), '#---')


class SpinnerRendering(unittest.TestCase):
    """The spinner steps between positions; it never sweeps between them."""

    def test_the_frame_is_chosen_by_the_step_not_by_the_clock(self):
        frames = [m.spinner_frame(step) for step in range(len(m.SPINNER) + 1)]
        self.assertEqual(frames[:-1], list(m.SPINNER))
        self.assertEqual(frames[-1], m.SPINNER[0])

    def test_an_unreported_step_leaves_the_glyph_exactly_where_it_was(self):
        self.assertEqual(m.spinner_frame(2), m.spinner_frame(2))


class StepRendering(unittest.TestCase):
    """A finished phase keeps one line, and that line says how it went."""

    def test_each_outcome_has_the_mark_the_desktop_already_uses(self):
        self.assertEqual(m.render_step('done', 'ship'), '  + ship')
        self.assertEqual(m.render_step('failed', 'ship'), '  x ship')
        self.assertEqual(m.render_step('skipped', 'ship'), '  = ship')
        self.assertEqual(m.render_step('blocked', 'ship'), '  ! ship')

    def test_a_phase_in_hand_wears_the_spinner_at_its_own_step(self):
        self.assertEqual(m.render_step('working', 'ship', frame=1), '  ▘ ship')

    def test_a_counter_appears_only_when_the_caller_knows_the_total(self):
        self.assertEqual(m.render_step('done', 'ship', index=2, total=7), '  + [2/7] ship')
        self.assertEqual(m.render_step('done', 'ship', index=2), '  + ship')

    def test_a_note_rides_after_the_name(self):
        self.assertEqual(m.render_step('done', 'waybar.apk', note='Q1abc'),
                         '  + waybar.apk  Q1abc')

    def test_the_note_is_dropped_before_the_name_is_trimmed(self):
        self.assertEqual(m.render_step('done', 'ship packages', note='to alienware', width=20),
                         '  + ship packages')

    def test_a_long_name_is_trimmed_to_the_terminal_rather_than_wrapped(self):
        line = m.render_step('done', 'p' * 100, width=20)
        self.assertEqual(len(line), 20)
        self.assertTrue(line.endswith('…'))

    def test_remote_build_keeps_the_line_it_has_always_printed(self):
        # The signing loop in alpine/bin/remote-build hands the step list the
        # package name and its apk identity; the bytes must not move.
        self.assertEqual(m.render_step('done', 'waybar-0.14.0-r0.apk  Q1deadbeef'),
                         '  + waybar-0.14.0-r0.apk  Q1deadbeef')


class ProgressRendering(unittest.TestCase):
    def test_the_line_carries_the_bar_the_count_and_the_name(self):
        self.assertEqual(m.render_progress('archive', 3, 12, bar_width=4),
                         '  ▰▱▱▱  3/12  archive')

    def test_the_name_gives_way_to_the_bar_when_the_terminal_is_narrow(self):
        line = m.render_progress('archived APKs', 3, 12, bar_width=8, width=20)
        self.assertEqual(len(line), 20)
        self.assertTrue(line.startswith('  ▰▰▱▱▱▱▱▱  3/12  '))


class ThemeColour(unittest.TestCase):
    """Colour is the active theme's, never a shade chosen here."""

    def theme(self, palette):
        directory = Path(self.enterContext(tempfile.TemporaryDirectory()))
        (directory / 'current').write_text('fixture\n')
        (directory / 'fixture.json').write_text(json.dumps({'palette': palette}))
        return directory

    def test_the_named_colours_come_from_the_theme_descriptor(self):
        directory = self.theme({'background': '#101010', 'foreground': '#eeeeee',
                                'accent': '#fabd2f', 'green': '#b8bb26', 'red': '#fb4934'})
        colours = m.theme_colours(directory)
        self.assertEqual(colours['green'], '#b8bb26')
        self.assertEqual(colours['red'], '#fb4934')
        self.assertEqual(colours['accent'], '#fabd2f')

    def test_a_theme_without_a_green_or_a_red_borrows_a_role_it_does_declare(self):
        directory = self.theme({'background': '#101010', 'foreground': '#eeeeee',
                                'accent': '#fabd2f'})
        colours = m.theme_colours(directory)
        self.assertEqual(colours['green'], colours['accent'])
        self.assertEqual(colours['red'], colours['foreground'])

    def test_an_unreadable_theme_leaves_the_language_drawable(self):
        directory = Path(self.enterContext(tempfile.TemporaryDirectory()))
        colours = m.theme_colours(directory)
        self.assertEqual(set(m.ROLES.values()) - set(colours), set())

    def test_a_theme_name_that_is_not_a_theme_name_reads_no_file(self):
        directory = Path(self.enterContext(tempfile.TemporaryDirectory()))
        (directory / 'current').write_text('../../etc/passwd\n')
        self.assertEqual(m.declared(directory), {})

    def test_every_role_is_painted_with_the_colour_the_theme_gave_it(self):
        directory = self.theme({'background': '#101010', 'foreground': '#eeeeee',
                                'accent': '#fabd2f', 'green': '#b8bb26', 'red': '#fb4934'})
        style = m.theme_style(m.theme_colours(directory))
        self.assertEqual(style('done', '+'), m.sgr('#b8bb26') + '+' + m.RESET)
        self.assertEqual(style('failed', 'x'), m.sgr('#fb4934') + 'x' + m.RESET)
        self.assertEqual(style('filled', '▰'), m.sgr('#fabd2f') + '▰' + m.RESET)

    def test_a_coloured_bar_still_reads_as_the_same_line_underneath(self):
        style = m.Style({'filled': '\033[1m', 'empty': '\033[2m'})
        painted = m.render_bar(1, 4, width=4, style=style)
        self.assertIn('▰', painted)
        self.assertEqual(painted.replace('\033[1m', '').replace('\033[2m', '')
                         .replace(m.RESET, ''), '▰▱▱▱')


class Degradation(unittest.TestCase):
    """Off a terminal, without colour, or off the cord: the events still land."""

    def test_a_pipe_gets_plain_lines_and_no_escape_codes(self):
        stream = Screen(tty=False)
        steps = m.StepList(terminal(stream))
        with steps.step('ship packages'):
            pass
        steps.mark('failed', 'build in container')
        self.assertEqual(stream.getvalue(),
                         '  + ship packages\n  x build in container\n')
        self.assertNotIn('\033', stream.getvalue())

    def test_no_color_keeps_the_live_line_and_drops_every_colour(self):
        screen = probe(environ={'TERM': 'foot', 'NO_COLOR': '1'})
        self.assertTrue(screen.live)
        self.assertFalse(screen.colour)
        self.assertFalse(screen.style)

    def test_an_empty_no_color_is_not_a_request_for_no_colour(self):
        # no-color.org: present *and not empty*. An exported-but-blank variable
        # is a shell accident, not a preference.
        self.assertTrue(probe(environ={'TERM': 'foot', 'NO_COLOR': ''}).colour)

    def test_a_dumb_terminal_gets_neither_colour_nor_repaints(self):
        screen = probe(environ={'TERM': 'dumb'})
        self.assertFalse(screen.live)
        self.assertFalse(screen.colour)

    def test_the_boot_console_keeps_its_own_sixteen_colours(self):
        self.assertFalse(probe(environ={'TERM': 'linux'}).colour)

    def test_a_battery_sheds_the_repaints_and_not_the_events(self):
        stream = Screen()
        screen = m.Terminal(stream, width=60, colour=False, environ={'TERM': 'foot'},
                            allows=lambda effect: False)
        self.assertFalse(screen.live)
        steps = m.StepList(screen)
        steps.mark('done', 'ship packages')
        self.assertEqual(stream.getvalue(), '  + ship packages\n')

    def test_the_ladder_is_asked_about_this_effect_by_name(self):
        asked = []
        m.Terminal(Screen(), width=60, environ={'TERM': 'foot'},
                   allows=lambda effect: asked.append(effect) or True)
        self.assertEqual(asked, ['terminal-progress'])

    def test_the_ladder_entry_is_the_one_the_desktop_registers(self):
        self.assertEqual(m.EFFECT, 'terminal-progress')

    def test_a_terminal_without_the_glyphs_falls_back_to_ascii(self):
        stream = Screen(tty=False)
        stream.encoding = 'ANSI_X3.4-1968'
        screen = terminal(stream, environ={'TERM': 'foot', 'LANG': 'C'})
        self.assertEqual(screen.segments, m.ASCII_SEGMENTS)
        self.assertEqual(screen.spinner, m.ASCII_SPINNER)
        m.StepList(screen).mark('done', 'ship packages')
        self.assertEqual(stream.getvalue(), '  + ship packages\n')

    def test_the_user_can_switch_the_repaints_off_by_hand(self):
        self.assertFalse(probe(environ={'TERM': 'foot', 'OLDBOOK_LOADING': 'plain'}).live)
        self.assertTrue(m.Terminal(io.StringIO(), width=60,
                                   environ={'OLDBOOK_LOADING': 'live'}).live)

    def test_a_closed_stream_never_takes_the_work_down_with_it(self):
        stream = Screen()
        screen = terminal(stream)
        stream.close()
        screen.write('anything')
        self.assertFalse(screen.live)


class FrameDiscipline(unittest.TestCase):
    """Bounded while the work runs, and stopped dead the moment it does not."""

    def test_no_more_than_ten_repaints_a_second(self):
        stream, tick = Screen(), clock()
        bar = m.Progress('archive', 1000, terminal=terminal(stream), width=24, clock=tick)
        for step in range(1000):
            tick.advance(0.001)
            bar.advance()
        painted = stream.getvalue().count('\033[2K')
        self.assertLessEqual(painted, int(1.0 / m.MIN_INTERVAL) + 2)

    def test_a_repaint_that_would_change_nothing_is_not_made(self):
        stream, tick = Screen(), clock()
        bar = m.Progress('archive', 4, terminal=terminal(stream), width=4, clock=tick)
        bar.update(1)
        before = len(stream.getvalue())
        for _ in range(5):
            tick.advance(1.0)
            bar.update(1)
        self.assertEqual(len(stream.getvalue()), before)

    def test_the_drawing_stops_the_instant_the_work_does(self):
        stream, tick = Screen(), clock()
        bar = m.Progress('archive', 4, terminal=terminal(stream), width=4, clock=tick)
        bar.update(4)
        bar.finish()
        settled = stream.getvalue()
        for _ in range(100):
            tick.advance(10.0)
        self.assertEqual(stream.getvalue(), settled)

    def test_the_bar_settles_exactly_on_its_total(self):
        stream, tick = Screen(), clock()
        with m.Progress('archive', 7, terminal=terminal(stream), width=7, clock=tick) as bar:
            for _ in range(7):
                tick.advance(0.5)
                bar.advance()
        self.assertEqual(visible(stream.getvalue())[-1], '  ▰▰▰▰▰▰▰  7/7  archive')

    def test_an_interrupted_bar_leaves_the_terminal_clean(self):
        stream, tick = Screen(), clock()
        with self.assertRaises(RuntimeError):
            with m.Progress('archive', 7, terminal=terminal(stream), width=7, clock=tick) as bar:
                tick.advance(0.5)
                bar.advance()
                raise RuntimeError('the host went away')
        self.assertTrue(stream.getvalue().endswith('\r\033[2K'))

    def test_a_log_hears_nothing_from_work_that_finishes_quickly(self):
        stream, tick = Screen(tty=False), clock()
        with m.Progress('archive', 4, terminal=terminal(stream), width=4, clock=tick) as bar:
            for _ in range(4):
                tick.advance(0.01)
                bar.advance()
        self.assertEqual(stream.getvalue(), '')

    def test_a_log_hears_whole_lines_from_work_that_drags(self):
        stream, tick = Screen(tty=False), clock()
        with m.Progress('archive', 4, terminal=terminal(stream), width=4, clock=tick) as bar:
            for _ in range(4):
                tick.advance(m.PLAIN_INTERVAL + 0.1)
                bar.advance()
        lines = stream.getvalue().splitlines()
        self.assertEqual(lines[0], '  ▰▱▱▱  1/4  archive')
        self.assertEqual(lines[-1], '  ▰▰▰▰  4/4  archive')
        self.assertNotIn('\033', stream.getvalue())


class Steps(unittest.TestCase):
    """The step list is a record, not an animation, and it reads the same either way."""

    def run_phases(self, tty):
        stream, tick = Screen(tty=tty), clock()
        steps = m.StepList(terminal(stream), total=3, clock=tick)
        with steps.step('ship packages'):
            tick.advance(0.5)
        with steps.step('build in container', quiet=False):
            tick.advance(0.5)
        steps.mark('skipped', 'collect the finished APKs')
        return stream.getvalue()

    def test_a_live_run_and_a_piped_run_leave_the_same_record(self):
        self.assertEqual(visible(self.run_phases(tty=True)),
                         self.run_phases(tty=False).splitlines())

    def test_every_phase_is_numbered_when_the_caller_knows_how_many(self):
        self.assertEqual(self.run_phases(tty=False).splitlines(),
                         ['  + [1/3] ship packages',
                          '  + [2/3] build in container',
                          '  = [3/3] collect the finished APKs'])

    def test_a_noisy_phase_is_given_no_line_to_have_drawn_over(self):
        stream, tick = Screen(), clock()
        steps = m.StepList(terminal(stream), clock=tick)
        steps.start('build in container', quiet=False)
        steps.tick()
        self.assertEqual(stream.getvalue(), '')
        steps.finish()
        self.assertEqual(stream.getvalue(), '  + build in container\n')

    def test_a_quiet_phase_holds_one_live_line_until_it_is_over(self):
        stream, tick = Screen(), clock()
        steps = m.StepList(terminal(stream), clock=tick)
        steps.start('ship packages')
        self.assertEqual(frames(stream.getvalue()), ['  ▖ ship packages'])
        tick.advance(0.5)
        steps.tick()
        self.assertEqual(frames(stream.getvalue())[-1], '  ▘ ship packages')
        steps.finish()
        self.assertEqual(stream.getvalue().count('\n'), 1)
        self.assertEqual(visible(stream.getvalue()), ['  + ship packages'])

    def test_a_phase_that_raises_is_marked_failed_and_the_failure_is_not_swallowed(self):
        stream = Screen(tty=False)
        steps = m.StepList(terminal(stream))
        with self.assertRaises(RuntimeError):
            with steps.step('reach a build host'):
                raise RuntimeError('no build host is reachable')
        self.assertEqual(stream.getvalue(), '  x reach a build host\n')
        self.assertEqual(steps.failures(), 1)

    def test_a_phase_may_rename_itself_with_what_it_learned(self):
        # How remote-build keeps its per-APK line: the identity is only known
        # once the package has been signed and verified.
        stream = Screen(tty=False)
        steps = m.StepList(terminal(stream))
        with steps.step('waybar-0.14.0-r0.apk'):
            steps.label = 'waybar-0.14.0-r0.apk  Q1deadbeef'
        self.assertEqual(stream.getvalue(), '  + waybar-0.14.0-r0.apk  Q1deadbeef\n')

    def test_the_spinner_marks_a_wait_with_no_known_total(self):
        stream, tick = Screen(), clock()
        spinner = m.Spinner('waiting on the build host', terminal=terminal(stream), clock=tick)
        for _ in range(3):
            tick.advance(0.5)
            spinner.step()
        spinner.finish()
        drawn = frames(stream.getvalue())
        self.assertEqual(drawn[:3], ['  ▘ waiting on the build host',
                                     '  ▝ waiting on the build host',
                                     '  ▗ waiting on the build host'])
        self.assertEqual(visible(stream.getvalue()), ['  + waiting on the build host'])

    def test_an_unreported_wait_leaves_the_spinner_perfectly_still(self):
        stream, tick = Screen(), clock()
        with m.Spinner('waiting', terminal=terminal(stream), clock=tick):
            for _ in range(50):
                tick.advance(1.0)
        self.assertEqual(frames(stream.getvalue()), ['  ▖ waiting', '  + waiting'])


class Scaling(unittest.TestCase):
    """Where a reading lands on a small scale, and what a flat run means."""

    def test_readings_spread_across_the_whole_scale(self):
        self.assertEqual(m.scale([0, 25, 50, 75, 100], low=0, high=100, steps=8),
                         [0, 2, 4, 6, 7])

    def test_a_series_with_no_spread_reads_as_steady_not_as_empty(self):
        # Sending it to the bottom would claim nothing happened and to the top
        # that it was at maximum; the data says neither.
        self.assertEqual(m.scale([50] * 4, steps=8), [4, 4, 4, 4])

    def test_readings_outside_the_declared_bounds_are_clamped(self):
        self.assertEqual(m.scale([-40, 250], low=0, high=100, steps=8), [0, 7])

    def test_bounds_default_to_the_extremes_of_what_was_measured(self):
        self.assertEqual(m.scale([10, 20], steps=8), [0, 7])

    def test_nothing_measured_draws_nothing(self):
        self.assertEqual(m.scale([], steps=8), [])


class LevelRendering(unittest.TestCase):
    """The shared ramp: one cell a sample, eight heights."""

    def test_one_cell_carries_one_sample(self):
        self.assertEqual(m.render_levels([0, 50, 100], low=0, high=100), '▁▅█')

    def test_the_ramp_is_the_one_the_audio_meter_already_speaks(self):
        # oldbook-cava-bar owned this ramp first; the point of naming it in the
        # library is that the visualiser and the meters cannot drift apart.
        source = (REPO / 'alpine/desktop/.local/bin/oldbook-cava-bar').read_text()
        self.assertIn("GLYPHS = '" + m.LEVELS + "'", source)

    def test_a_terminal_without_the_glyphs_still_gets_a_ramp(self):
        self.assertEqual(m.render_levels([0, 100], low=0, high=100, ramp=m.ASCII_LEVELS), '.@')


class SparklineRendering(unittest.TestCase):
    """Braille: two samples a cell, four dot rows each."""

    def test_two_samples_share_one_cell(self):
        self.assertEqual(len(m.render_sparkline(range(20), low=0, high=19)), 10)

    def test_an_odd_sample_leaves_a_half_filled_cell_rather_than_inventing_one(self):
        self.assertEqual(len(m.render_sparkline([1, 2, 3], low=0, high=3)), 2)

    def test_every_sample_lights_at_least_the_bottom_dot(self):
        # A trace with gaps in it reads as broken instrumentation rather than
        # as a low reading, so the floor of the range still draws a mark.
        self.assertEqual(m.render_sparkline([0, 0], low=0, high=100), '⣀')

    def test_the_top_of_the_range_fills_the_cell(self):
        self.assertEqual(m.render_sparkline([100, 100], low=0, high=100), '⣿')

    def test_nothing_measured_draws_nothing(self):
        self.assertEqual(m.render_sparkline([]), '')


class MeterRendering(unittest.TestCase):
    """The compact bar the panel wears, filled to the eighth of a cell."""

    def test_a_reading_fills_whole_cells_then_part_of_one(self):
        self.assertEqual(m.render_meter(0.5, width=4), '██░░')
        self.assertEqual(m.render_meter(0.625, width=4), '██▌░')

    def test_four_cells_carry_finer_steps_than_the_twenty_four_segment_bar(self):
        readings = {m.render_meter(value / 100, width=4) for value in range(101)}
        self.assertGreater(len(readings), m.BAR_WIDTH)

    def test_the_track_is_visible_with_every_escape_code_stripped_out(self):
        # The meter must not depend on colour to say where it ends: a pipe, a
        # dumb terminal or NO_COLOR would otherwise reduce it to a solid bar.
        self.assertEqual(m.render_meter(0.0, width=4), '░░░░')
        self.assertNotEqual(m.render_meter(0.0, width=4), m.render_meter(1.0, width=4))

    def test_a_full_reading_leaves_no_track_behind_it(self):
        self.assertEqual(m.render_meter(1.0, width=4), '████')

    def test_readings_outside_the_range_are_clamped_rather_than_believed(self):
        self.assertEqual(m.render_meter(-1.0, width=3), '░░░')
        self.assertEqual(m.render_meter(9.0, width=3), '███')

    def test_a_meter_needs_somewhere_to_draw(self):
        with self.assertRaises(ValueError):
            m.render_meter(0.5, width=0)

    def test_a_terminal_without_the_glyphs_still_gets_a_meter(self):
        self.assertEqual(m.render_meter(0.5, width=4, glyphs=m.ASCII_EIGHTHS,
                                        track=m.ASCII_TRACK), '@@..')


class FrameRendering(unittest.TestCase):
    """The closing box, and what it does when there is no room for one."""

    def test_the_title_sits_in_the_top_rule(self):
        lines = m.render_frame(['one'], title='Rebuild', width=40, indent='')
        self.assertTrue(lines[0].startswith('╭─ Rebuild '))
        self.assertTrue(lines[0].endswith('╮'))

    def test_every_line_of_the_box_is_the_same_width(self):
        lines = m.render_frame(['short', 'a much longer line'], title='T', width=60, indent='')
        self.assertEqual(len({len(line) for line in lines}), 1)

    def test_a_terminal_too_narrow_for_a_box_still_gets_the_summary(self):
        # The summary is the information; the frame is the courtesy.
        self.assertEqual(m.render_frame(['2 built'], title='x', width=10, indent=''), ['2 built'])


class SubSteps(unittest.TestCase):
    """Sub-steps tied to the phase that produced them."""

    def scrollback(self, terminal, stream):
        steps = m.StepList(terminal=terminal, total=2)
        steps.start('Rebuild packages')
        steps.detail('swayfx', 'done', '4m12s')
        steps.detail('waybar', 'failed')
        steps.finish('failed')
        steps.mark('done', 'Publish')
        return steps, visible(stream.getvalue())

    def test_the_gutter_closes_on_the_last_sub_step(self):
        stream = Screen()
        _, lines = self.scrollback(terminal(stream), stream)
        self.assertEqual(lines, ['  x [1/2] Rebuild packages',
                                 '    ├─ + swayfx  4m12s',
                                 '    └─ x waybar',
                                 '  + [2/2] Publish'])

    def test_sub_steps_are_held_until_the_phase_they_belong_to_closes(self):
        # Printed as they arrive they would land above the live line of the
        # phase that owns them, and then be overwritten by it.
        stream = Screen()
        steps = m.StepList(terminal=terminal(stream), total=1)
        steps.start('Rebuild packages')
        steps.detail('swayfx', 'done')
        self.assertNotIn('swayfx', stream.getvalue())
        steps.finish()
        self.assertIn('swayfx', stream.getvalue())

    def test_a_phase_that_did_nothing_worth_saying_gets_no_gutter(self):
        stream = Screen()
        steps = m.StepList(terminal=terminal(stream), total=1)
        steps.mark('done', 'Publish')
        self.assertEqual(visible(stream.getvalue()), ['  + [1/1] Publish'])


class Summary(unittest.TestCase):
    """The closing box a run leaves behind."""

    def test_a_clean_run_is_counted_in_the_alphabet_the_marks_use(self):
        stream = Screen()
        steps = m.StepList(terminal=terminal(stream), total=2)
        steps.mark('done', 'one')
        steps.mark('skipped', 'two')
        steps.summary(title='rebuild')
        self.assertIn('+ 1 done  = 1 skipped', stream.getvalue())

    def test_a_run_that_failed_is_framed_heavily_so_it_reads_without_colour(self):
        stream = Screen()
        steps = m.StepList(terminal=terminal(stream), total=1)
        steps.mark('failed', 'one')
        self.assertEqual(steps.summary(title='rebuild'), 1)
        self.assertIn('┏━ rebuild', stream.getvalue())

    def test_a_clean_run_is_framed_lightly(self):
        stream = Screen()
        steps = m.StepList(terminal=terminal(stream), total=1)
        steps.mark('done', 'one')
        self.assertEqual(steps.summary(title='rebuild'), 0)
        self.assertIn('╭─ rebuild', stream.getvalue())


class SpinnerAlphabets(unittest.TestCase):
    """More than one spinner, all of them stepped rather than timed."""

    def test_a_caller_can_name_the_alphabet_its_surface_suits(self):
        self.assertEqual(probe(spinner='braille').spinner, m.SPINNERS['braille'])

    def test_an_unknown_name_falls_back_rather_than_failing_a_build(self):
        self.assertEqual(probe(spinner='no-such-spinner').spinner, m.SPINNER)

    def test_a_terminal_without_the_glyphs_gets_the_plain_frames_whatever_was_asked(self):
        self.assertEqual(ascii_terminal(spinner='braille').spinner, m.ASCII_SPINNER)

    def test_the_whole_alphabet_degrades_together_or_not_at_all(self):
        # Half a vocabulary is worse than none of it: a line carrying an ASCII
        # meter beside a Braille sparkline would be drawn from two faces.
        plain = ascii_terminal()
        self.assertEqual(
            (plain.segments, plain.spinner, plain.ellipsis, plain.levels,
             plain.eighths, plain.track, plain.frame, plain.gutter),
            (m.ASCII_SEGMENTS, m.ASCII_SPINNER, m.ASCII_ELLIPSIS, m.ASCII_LEVELS,
             m.ASCII_EIGHTHS, m.ASCII_TRACK, m.ASCII_FRAME, m.ASCII_GUTTER))

    def test_every_alphabet_steps_on_reported_work_and_never_on_a_clock(self):
        for name, frames_ in m.SPINNERS.items():
            with self.subTest(name):
                self.assertEqual(m.spinner_frame(0, frames_), frames_[0])
                self.assertEqual(m.spinner_frame(len(frames_), frames_), frames_[0])


if __name__ == '__main__':
    unittest.main()
