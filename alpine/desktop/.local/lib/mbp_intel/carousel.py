"""Warm, per-compositor window carousel; previews never leave process memory."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import fcntl
import hashlib
import json
import os
from pathlib import Path
import runpy
import signal
import socket
import stat
import struct
import subprocess
import sys
import time

from window_switching import FocusHistory, SwitchState, identity, window_candidates

HEADER = struct.Struct('=6sII')
ACTIONS = ('show', 'next', 'previous', 'commit', 'cancel', 'status')
MAX_PREVIEW_PIXELS = 16 * 1024 * 1024


class EventFrames:
    """Read a nonblocking IPC stream without stalling the GTK frame clock."""

    def __init__(self):
        self.buffer = bytearray()

    def feed(self, data):
        self.buffer.extend(data)
        result = []
        while len(self.buffer) >= HEADER.size:
            magic, length, kind = HEADER.unpack_from(self.buffer)
            if magic != b'i3-ipc' or length > 32 * 1024 * 1024:
                raise ValueError('invalid Sway event frame')
            end = HEADER.size + length
            if len(self.buffer) < end:
                break
            result.append((kind, json.loads(self.buffer[HEADER.size:end])))
            del self.buffer[:end]
        return result


def runtime_directory(runtime, sway):
    token = hashlib.sha256(str(sway).encode()).hexdigest()[:12]
    return runtime / 'mbp-intel' / ('carousel-' + token)


def decode_preview(data):
    from showdesktop import parse_ppm
    if len(data) > MAX_PREVIEW_PIXELS * 3 + 65536:
        raise ValueError('preview exceeds size limit')
    width, height, offset = parse_ppm(data)
    if width * height > MAX_PREVIEW_PIXELS:
        raise ValueError('preview exceeds pixel limit')
    return width, height, data[offset:offset + width * height * 3]


def capture_preview(candidate):
    identifier = candidate.get('foreign_toplevel_identifier')
    if not identifier:
        return None
    try:
        # Keep every pixel supplied by the compositor's toplevel capture.
        # One immutable snapshot per opening is enough; never poll live video.
        result = subprocess.run(['grim', '-T', identifier, '-t', 'ppm', '-'],
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                timeout=3, check=True)
        return decode_preview(result.stdout)
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


class PreviewStore:
    """Ignore completions from an old gesture, even when a container ID repeats."""

    def __init__(self, executor, dispatch, deliver):
        self.executor, self.dispatch, self.deliver = executor, dispatch, deliver
        self.generation = 0
        self.pending = {}
        self.requested = set()
        self.ready = set()
        self.dimensions = {}

    def clear(self):
        self.generation += 1
        for future in self.pending.values():
            future.cancel()
        self.pending.clear()
        self.requested.clear()
        self.ready.clear()
        self.dimensions.clear()

    def request(self, candidates):
        generation = self.generation
        for candidate in candidates:
            token = identity(candidate)
            if token in self.requested or not candidate.get('foreign_toplevel_identifier'):
                continue
            self.requested.add(token)
            future = self.executor.submit(capture_preview, dict(candidate))
            self.pending[token] = future

            def completed(done, item=dict(candidate), key=token):
                def publish():
                    if generation != self.generation or done.cancelled():
                        return False
                    # GTK owns the texture after delivery. Do not retain a
                    # second full-resolution RGB image inside a done Future.
                    self.pending.pop(key, None)
                    try:
                        pixels = done.result()
                    except Exception:
                        pixels = None
                    if pixels is not None:
                        self.ready.add(key)
                        self.dimensions[key] = pixels[:2]
                        self.deliver(item, *pixels)
                    else:
                        self.deliver(item, 0, 0, None)
                    return False
                self.dispatch(publish)
            future.add_done_callback(completed)


def load_ipc():
    return runpy.run_path(str(Path(__file__).resolve().parents[2] / 'bin/mbp-intel-workspaces'))


def private_directory(directory):
    for path in (directory.parent, directory):
        path.mkdir(mode=0o700, exist_ok=True)
        info = path.stat(follow_symlinks=False)
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) != 0o700):
            raise RuntimeError('unsafe carousel runtime directory')


class Controller:
    def __init__(self, ipc, sway, directory, control):
        from showdesktop import preload_layer_shell
        preload_layer_shell()
        import gi
        gi.require_version('Gtk', '4.0')
        from gi.repository import GLib, Gtk
        Gtk.init()
        self.GLib = GLib
        self.ipc, self.sway, self.directory, self.control = ipc, sway, directory, control
        self.loop = GLib.MainLoop()
        self.history = FocusHistory()
        self.state = self.popup = None
        self.graphics_primer = None
        self.mode_active = False
        self.modifier = None
        self.closed_frames = 0
        self.closed_frame_times = []
        self.stopping = False
        self.executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix='window-preview')
        self.previews = PreviewStore(self.executor, GLib.idle_add, self.deliver_preview)
        self.events = socket.socket(socket.AF_UNIX)
        self.events.settimeout(3)
        self.events.connect(str(sway))
        ipc['send'](self.events, 2, '["window","workspace","mode","shutdown"]')
        if not ipc['receive'](self.events)[1].get('success'):
            raise RuntimeError('Sway refused carousel subscription')
        self.events.setblocking(False)
        self.frames = EventFrames()
        self.live = self.candidates()
        self.history.update(self.live)
        self.watches = [
            GLib.io_add_watch(self.events.fileno(), GLib.IO_IN | GLib.IO_HUP | GLib.IO_ERR, self.event),
            GLib.io_add_watch(control.fileno(), GLib.IO_IN, self.message),
        ]
        self.open_timer = None
        for signum in (signal.SIGTERM, signal.SIGINT):
            self.watches.append(GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signum, self.stop))
        from ui_priority import request_priority
        request_priority()
        try:
            from graphics_warmup import warm_graphics
            self.graphics_primer = warm_graphics()
        except Exception as error:
            print('carousel graphics warmup:', error, file=sys.stderr)
        # Realization and the first shader draw create driver worker pools that
        # do not exist at Gtk.init(). Promote those threads after warming too.
        request_priority()
        self.write_status()

    def candidates(self):
        return window_candidates(self.ipc['request'](self.sway, 4))

    def command(self, text):
        self.ipc['command'](self.sway, text)

    def write_status(self):
        popup, state = self.popup, self.state
        live = {identity(item) for item in state.candidates} if state else set()
        self.ipc['write_json'](self.directory / 'state.json', {
            'pid': os.getpid(), 'ready': not self.stopping, 'open': popup is not None,
            'graphics_warm': self.graphics_primer is not None,
            'selected_id': state.selected['id'] if state and state.selected else None,
            'candidate_ids': [item['id'] for item in state.candidates] if state else [],
            'modifier': self.modifier,
            'preview_ids': sorted(token[0] for token in self.previews.ready & live),
            'preview_dimensions': {str(token[0]): list(size)
                                   for token, size in self.previews.dimensions.items() if token in live},
            'frames': popup.frames if popup else self.closed_frames,
            'frame_times': list(popup.frame_times if popup else self.closed_frame_times)[-240:],
        })
        return bool(popup)

    def request_previews(self):
        if self.state is None or self.state.index is None:
            return
        items, index = self.state.candidates, self.state.index
        order = [items[(index + offset) % len(items)] for offset in (0, -1, 1, -2, 2, -3, 3)]
        self.previews.request(order)

    def deliver_preview(self, candidate, width, height, pixels):
        if self.popup and identity(candidate) in {identity(item) for item in self.state.candidates}:
            if pixels is None:
                self.popup.set_preview_unavailable(candidate['id'])
            else:
                self.popup.set_preview(candidate['id'], width, height, pixels)
            self.write_status()

    def mapped(self):
        if self.popup is None:
            return
        self.command('mode "window-switcher"')
        self.mode_active = True
        popup = self.popup

        def released_before_map():
            if self.popup is popup and self.modifier:
                mask = 'Mod4' if self.modifier == 'super' else 'Mod1'
                if mask not in popup.current_modifiers():
                    self.action('commit')
            return False
        popup.when_keyboard_ready(released_before_map)

    def action(self, action, modifier=None):
        if action == 'status':
            self.write_status()
            return
        if action in ('commit', 'cancel'):
            if not self.popup:
                return
            owned_mode = self.ipc['request'](self.sway, 12).get('name') == 'window-switcher'
            target = (self.state.commit_target(self.candidates())
                      if action == 'commit' and owned_mode else None)
            self.dismiss()
            if target is not None:
                self.command(f'[con_id={target}] focus')
                self.history.record(self.candidates(), target)
            return
        if self.popup:
            if action in ('next', 'previous'):
                self.state.step(action)
                self.popup.update(self.state)
                self.request_previews()
                self.write_status()
            return
        # Focus events and hotkey commands travel over different sockets. Drain
        # the subscribed history before freezing a new gesture's order.
        self.event(self.events.fileno(), self.GLib.IO_IN)
        if self.stopping:
            return
        self.live = self.candidates()
        ordered = self.history.update(self.live)
        state = SwitchState(ordered, action)
        if not state.selected:
            self.write_status()
            return
        from carousel_view import Popup
        self.state = state
        self.modifier = modifier if action != 'show' else None
        workspace = next((item for item in self.ipc['request'](self.sway, 1)
                          if item.get('focused')), {})
        self.popup = Popup(state, self.modifier, self.action, self.mapped, workspace.get('output'))
        for candidate in state.candidates:
            if not candidate.get('foreign_toplevel_identifier'):
                self.popup.set_preview_unavailable(candidate['id'])
        self.popup.present()
        self.request_previews()
        self.write_status()
        self.open_timer = self.GLib.timeout_add(200, self.write_status)

    def dismiss(self):
        self.mode_active = False
        popup, self.popup = self.popup, None
        if popup:
            self.closed_frames, self.closed_frame_times = popup.frames, list(popup.frame_times)
            popup.close()
        self.state, self.modifier = None, None
        self.previews.clear()
        if self.open_timer:
            self.GLib.source_remove(self.open_timer)
            self.open_timer = None
        try:
            if self.ipc['request'](self.sway, 12).get('name') == 'window-switcher':
                self.command('mode "default"')
        except (OSError, ValueError, RuntimeError):
            pass
        self.write_status()

    def message(self, _fd, _condition):
        try:
            while True:
                data = json.loads(self.control.recv(1024))
                if data.get('action') in ACTIONS and data.get('modifier') in (None, 'super', 'alt'):
                    self.action(data['action'], data.get('modifier'))
        except BlockingIOError:
            pass
        except (OSError, ValueError, RuntimeError) as error:
            print('carousel command:', error, file=sys.stderr)
            self.dismiss()
        return True

    def event(self, _fd, condition):
        if condition & (self.GLib.IO_HUP | self.GLib.IO_ERR):
            return self.stop()
        try:
            events = []
            while True:
                try:
                    data = self.events.recv(1024 * 1024)
                except BlockingIOError:
                    break
                if not data:
                    return self.stop()
                events.extend(self.frames.feed(data))
            if not events:
                return True
            if any(kind == 0x80000006 for kind, _event in events):
                return self.stop()
            if (self.popup and self.mode_active
                    and any(kind == 0x80000002 and event.get('change') != 'window-switcher'
                            for kind, event in events)
                    and self.ipc['request'](self.sway, 12).get('name') != 'window-switcher'):
                self.dismiss()
            relevant = [(kind, event) for kind, event in events if kind in (0x80000000, 0x80000003)]
            if not relevant:
                return True
            self.live = self.candidates()
            for kind, event in relevant:
                if kind == 0x80000003 and event.get('change') == 'focus':
                    self.history.record(self.live, event.get('container', {}).get('id'))
            self.history.update(self.live)
            if self.popup:
                self.state.refresh(self.live)
                if self.state.selected:
                    self.popup.update(self.state)
                    self.request_previews()
                    self.write_status()
                else:
                    self.dismiss()
        except BlockingIOError:
            pass
        except (OSError, ValueError, RuntimeError) as error:
            print('carousel event:', error, file=sys.stderr)
            return self.stop()
        return True

    def stop(self):
        if not self.stopping:
            self.stopping = True
            self.dismiss()
            if self.graphics_primer is not None:
                self.graphics_primer.close()
                self.graphics_primer = None
            self.loop.quit()
        return False

    def run(self):
        try:
            self.loop.run()
        finally:
            self.stop()
            self.events.close()
            self.executor.shutdown(wait=False, cancel_futures=True)


def send(address, action, modifier):
    with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as client:
        client.sendto(json.dumps({'action': action, 'modifier': modifier}).encode(), str(address))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('daemon', *ACTIONS), nargs='?', default='show')
    parser.add_argument('--modifier', choices=('super', 'alt'))
    args = parser.parse_args()
    ipc = load_ipc()
    runtime = Path(os.environ.get('XDG_RUNTIME_DIR', f'/run/user/{os.getuid()}'))
    sway = ipc['find_socket'](runtime)
    directory = runtime_directory(runtime, sway)
    private_directory(directory)
    address = directory / 'control.sock'
    if args.action != 'daemon':
        try:
            send(address, args.action, args.modifier)
        except (FileNotFoundError, ConnectionRefusedError):
            if args.action in ('cancel', 'commit', 'status'):
                if args.action == 'status':
                    print(json.dumps({'ready': False, 'open': False}))
                return
            executable = Path(__file__).resolve().parents[2] / 'bin/mbp-intel-carousel'
            with (directory / 'daemon.log').open('a') as log:
                subprocess.Popen([str(executable), 'daemon'], stdin=subprocess.DEVNULL,
                                 stdout=log, stderr=log, start_new_session=True, close_fds=True)
            deadline = time.monotonic() + 5
            while True:
                try:
                    send(address, args.action, args.modifier)
                    break
                except (FileNotFoundError, ConnectionRefusedError):
                    if time.monotonic() >= deadline:
                        raise RuntimeError('carousel daemon did not start')
                    time.sleep(.02)
        if args.action == 'status':
            print(json.dumps(ipc['read_json'](directory / 'state.json', {})))
        return
    with (directory / 'daemon.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        address.unlink(missing_ok=True)
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as control:
            control.bind(str(address))
            control.setblocking(False)
            try:
                Controller(ipc, sway, directory, control).run()
            finally:
                address.unlink(missing_ok=True)


if __name__ == '__main__':
    main()
