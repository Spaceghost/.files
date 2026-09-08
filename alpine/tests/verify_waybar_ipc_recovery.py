#!/usr/bin/env python3
"""Verify real Waybar recovers its Sway workspace event subscription."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import selectors
import shlex
import signal
import socket
import struct
import subprocess
import tempfile
import threading
import time


ROOT = Path(__file__).resolve().parents[2]
HEADER = struct.Struct('=6sII')
MAGIC = b'i3-ipc'
INSPECTOR = r'''
#define _GNU_SOURCE
#include <gtk/gtk.h>

static GString *result;

static void labels(GtkWidget *widget, gpointer unused) {
    (void)unused;
    if (GTK_IS_LABEL(widget)) {
        const char *text = gtk_label_get_text(GTK_LABEL(widget));
        if (text && *text) g_string_append_printf(result, "text=%s\t", text);
    }
    if (GTK_IS_CONTAINER(widget)) gtk_container_foreach(GTK_CONTAINER(widget), labels, NULL);
}

static void visit(GtkWidget *widget, gpointer unused) {
    (void)unused;
    if (GTK_IS_BUTTON(widget)) {
        GtkStyleContext *context = gtk_widget_get_style_context(widget);
        GList *classes = gtk_style_context_list_classes(context);
        result = g_string_new(NULL);
        labels(widget, NULL);
        g_string_append(result, "classes=");
        for (GList *item = classes; item; item = item->next) {
            if (item != classes) g_string_append_c(result, ',');
            g_string_append(result, (const char *)item->data);
        }
        g_string_append_c(result, '\n');
        const char *path = g_getenv("MBP_INTEL_WAYBAR_IPC_INSPECTION");
        FILE *stream = fopen(path, "a");
        if (stream) { fputs(result->str, stream); fclose(stream); }
        g_string_free(result, TRUE);
        g_list_free(classes);
    }
    if (GTK_IS_CONTAINER(widget)) gtk_container_foreach(GTK_CONTAINER(widget), visit, NULL);
}

static gboolean inspect(gpointer unused) {
    (void)unused;
    const char *path = g_getenv("MBP_INTEL_WAYBAR_IPC_INSPECTION");
    if (!path) return G_SOURCE_REMOVE;
    g_file_set_contents(path, "", 0, NULL);
    GList *windows = gtk_window_list_toplevels();
    for (GList *item = windows; item; item = item->next) visit(GTK_WIDGET(item->data), NULL);
    g_list_free(windows);
    return G_SOURCE_CONTINUE;
}

__attribute__((constructor)) static void begin(void) {
    if (g_getenv("MBP_INTEL_WAYBAR_IPC_INSPECTION")) g_timeout_add(100, inspect, NULL);
}
'''


def require(condition, message):
    if not condition:
        raise AssertionError(message)


class ProxyConnection:
    def __init__(self, proxy, downstream):
        self.proxy = proxy
        self.downstream = downstream
        self.upstream = socket.socket(socket.AF_UNIX)
        self.upstream.connect(str(proxy.upstream))
        self.client_packets = bytearray()
        self.server_packets = bytearray()
        self.subscribed = False
        self.subscription_ready = False
        self.subscription_payloads = []
        self.running = True
        self.thread = threading.Thread(target=self.serve, daemon=True)
        self.thread.start()

    def parse(self, data, from_client):
        buffered = self.client_packets if from_client else self.server_packets
        buffered.extend(data)
        while len(buffered) >= HEADER.size:
            magic, length, kind = HEADER.unpack(buffered[:HEADER.size])
            if magic != MAGIC or length > 16 * 1024 * 1024:
                return
            total = HEADER.size + length
            if len(buffered) < total:
                return
            body = bytes(buffered[HEADER.size:total])
            del buffered[:total]
            if from_client and kind == 2:
                self.subscribed = True
                try:
                    self.subscription_payloads.append(json.loads(body))
                except (UnicodeDecodeError, ValueError):
                    self.subscription_payloads.append(None)
                self.proxy.changed()
            elif not from_client:
                self.proxy.record_event(kind)
                if kind == 2 and self.subscribed:
                    self.subscription_ready = True
                    self.proxy.changed()

    def serve(self):
        selector = selectors.DefaultSelector()
        try:
            selector.register(self.downstream, selectors.EVENT_READ, (self.upstream, True))
            selector.register(self.upstream, selectors.EVENT_READ, (self.downstream, False))
            while self.running and self.proxy.running:
                for key, _ in selector.select(.1):
                    destination, from_client = key.data
                    try:
                        data = key.fileobj.recv(65536)
                    except (BlockingIOError, OSError):
                        data = b''
                    if not data:
                        return
                    self.parse(data, from_client)
                    destination.sendall(data)
        except OSError:
            pass
        finally:
            self.running = False
            selector.close()
            for connection in (self.downstream, self.upstream):
                try:
                    connection.close()
                except OSError:
                    pass
            self.proxy.changed()

    def close(self):
        self.running = False
        for connection in (self.downstream, self.upstream):
            try:
                connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                connection.close()
            except OSError:
                pass


class IpcProxy:
    def __init__(self, path, upstream):
        self.path = path
        self.upstream = upstream
        self.running = True
        self.lock = threading.Condition()
        self.connections = []
        self.accepted_subscriptions = []
        self.event_counts = {}
        self.last_injection = None
        self.server = socket.socket(socket.AF_UNIX)
        self.server.bind(str(path))
        self.server.listen(16)
        self.server.settimeout(.1)
        self.thread = threading.Thread(target=self.serve, daemon=True)
        self.thread.start()

    def changed(self):
        with self.lock:
            for connection in self.connections:
                if (connection.subscription_ready and
                        connection not in self.accepted_subscriptions):
                    self.accepted_subscriptions.append(connection)
            self.lock.notify_all()

    def record_event(self, kind):
        if kind & (1 << 31):
            with self.lock:
                self.event_counts[kind] = self.event_counts.get(kind, 0) + 1

    def event_count(self, kind):
        with self.lock:
            return self.event_counts.get(kind, 0)

    def serve(self):
        while self.running:
            try:
                downstream, _ = self.server.accept()
                connection = ProxyConnection(self, downstream)
                with self.lock:
                    self.connections.append(connection)
                    self.lock.notify_all()
            except (TimeoutError, OSError):
                continue

    def wait_subscriptions(self, count, seconds=8):
        deadline = time.monotonic() + seconds
        with self.lock:
            while len(self.accepted_subscriptions) < count:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise AssertionError(f'Waybar opened only {len(self.accepted_subscriptions)} subscriptions')
                self.lock.wait(remaining)
            return list(self.accepted_subscriptions)

    def wait_event_sets(self, count, expected, seconds=8):
        deadline = time.monotonic() + seconds
        with self.lock:
            while True:
                ready = self.accepted_subscriptions[:count]
                if len(ready) == count and all(
                        expected.issubset({event for payload in item.subscription_payloads
                                           if payload for event in payload})
                        for item in ready):
                    return ready
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    found = [item.subscription_payloads for item in ready]
                    raise AssertionError(f'Waybar subscription replay was {found}')
                self.lock.wait(remaining)

    def drop_subscriptions(self, mid_payload=False):
        with self.lock:
            active = [item for item in self.connections
                      if item.subscription_ready and item.running]
        require(active, 'no active Waybar subscription to drop')
        payloads = [item.subscription_payloads for item in active]
        for connection in active:
            if mid_payload:
                body = b'{"change":"focus"'
                packet = HEADER.pack(MAGIC, 80, (1 << 31) | 3) + body
                connection.downstream.sendall(packet)
                self.last_injection = {
                    'declared_body_bytes': 80, 'sent_body_bytes': len(body),
                    'header_bytes': HEADER.size,
                }
            connection.close()
        return payloads

    def close(self):
        self.running = False
        try:
            self.server.close()
        except OSError:
            pass
        for connection in list(self.connections):
            connection.close()
        self.thread.join(3)
        for connection in list(self.connections):
            connection.thread.join(3)


def compile_inspector(base):
    source = base / 'inspect.c'
    library = base / 'inspect.so'
    source.write_text(INSPECTOR)
    flags = shlex.split(subprocess.check_output(
        ['pkg-config', '--cflags', '--libs', 'gtk+-3.0'], text=True))
    subprocess.run(['cc', '-shared', '-fPIC', '-Wall', '-Wextra', '-Werror',
                    str(source), '-o', str(library), *flags], check=True)
    return library


def read_buttons(path):
    result = {}
    try:
        for line in path.read_text().splitlines():
            fields = dict(item.split('=', 1) for item in line.split('\t') if '=' in item)
            if fields.get('text'):
                result[fields['text']] = fields.get('classes', '').split(',')
    except (OSError, ValueError):
        pass
    return result


def process_ticks(process):
    fields = Path(f'/proc/{process.pid}/stat').read_text().rsplit(') ', 1)[1].split()
    return int(fields[11]) + int(fields[12])


def verify(waybar, output, stress_seconds=0):
    output.mkdir(parents=True, exist_ok=False)
    report = {
        'status': 'running', 'waybar': str(waybar), 'checks': [], 'host_changes': 0,
        'waybar_sha256': hashlib.sha256(waybar.read_bytes()).hexdigest(),
        'verifier_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'stress_seconds_requested': stress_seconds,
        'isolation': 'private HOME, XDG directories, D-Bus, headless Sway and Unix IPC proxy',
    }
    processes = []
    proxy = None
    log = (output / 'runtime.log').open('w')

    with tempfile.TemporaryDirectory(prefix='waybar-ipc-recovery-') as directory:
        base = Path(directory)
        env = dict(os.environ)
        for key, name in (('HOME', 'home'), ('XDG_RUNTIME_DIR', 'run'),
                          ('XDG_CONFIG_HOME', 'config'), ('XDG_STATE_HOME', 'state'),
                          ('XDG_CACHE_HOME', 'cache'), ('XDG_DATA_HOME', 'data')):
            path = base / name
            path.mkdir(mode=0o700)
            env[key] = str(path)
        for key in ('SWAYSOCK', 'WAYLAND_DISPLAY', 'DISPLAY', 'LD_PRELOAD',
                    'DBUS_SESSION_BUS_ADDRESS'):
            env.pop(key, None)
        env.update(WLR_BACKENDS='headless', WLR_RENDERER='pixman',
                   WLR_HEADLESS_OUTPUTS='1', NO_AT_BRIDGE='1', GTK_USE_PORTAL='0')
        runtime = Path(env['XDG_RUNTIME_DIR'])
        config = Path(env['XDG_CONFIG_HOME']) / 'waybar'
        config.mkdir()
        (config / 'config.jsonc').write_text(json.dumps([{
            'name': 'top', 'output': 'HEADLESS-1', 'height': 32,
            'modules-left': ['sway/workspaces'], 'modules-center': [],
            'modules-right': [],
            'sway/workspaces': {'format': '{value}', 'disable-markup': True,
                                'all-outputs': True},
        }]) + '\n')
        (config / 'style.css').write_text(
            '* { font-family: monospace; font-size: 12px; min-height: 0; }\n'
            'window#waybar { background: #111111; color: #eeeeee; }\n'
            '#workspaces button { color: #aaaaaa; }\n'
            '#workspaces button.focused { color: #ffffff; background: #cc0000; }\n')
        sway_config = output / 'sway.conf'
        sway_config.write_text('xwayland disable\noutput HEADLESS-1 mode 800x600\n'
                               'output * bg #13091f solid_color\nseat seat0 fallback true\n'
                               'focus_follows_mouse no\n')
        foot_config = base / 'foot.ini'
        foot_config.write_text('[main]\nfont=monospace:size=10\n')
        pressure_marker = base / 'title-pressure'
        title_fixture = base / 'title-fixture.py'
        title_fixture.write_text(
            'import sys,time\nfrom pathlib import Path\n'
            'marker=Path(sys.argv[1]); count=0\n'
            'while True:\n'
            ' if marker.exists():\n'
            '  print("\\033]2;private-pressure-%d\\007" % count,end="",flush=True); count+=1\n'
            ' time.sleep(.1)\n')
        inspector = compile_inspector(base)
        observation = output / 'buttons.tsv'
        bus_path = runtime / 'bus'
        bus_config = base / 'bus.conf'
        bus_config.write_text(
            '<busconfig><type>session</type><listen>unix:path=' + str(bus_path) +
            '</listen><auth>EXTERNAL</auth><policy context="default">'
            '<allow send_destination="*"/><allow receive_sender="*"/><allow own="*"/>'
            '</policy></busconfig>')

        def spawn(name, command, local_env=None, stdout=None):
            process = subprocess.Popen(
                command, env=local_env or env, stdin=subprocess.DEVNULL,
                stdout=stdout if stdout is not None else log, stderr=log,
                start_new_session=True, text=True,
            )
            processes.append((name, process))
            return process

        def wait(predicate, message, seconds=10):
            deadline = time.monotonic() + seconds
            while time.monotonic() < deadline:
                for name, process in processes:
                    if process.poll() is not None:
                        raise AssertionError(f'{name} exited {process.returncode}: {message}')
                value = predicate()
                if value:
                    return value
                time.sleep(.05)
            raise AssertionError(message)

        def direct(*arguments):
            return subprocess.run(['swaymsg', '-s', str(real_socket), '-r', *arguments],
                                  env=env, capture_output=True, text=True,
                                  check=True, timeout=5)

        def screenshot(name):
            subprocess.run(['grim', '-g', '0,0 800x64', str(output / name)],
                           env=env, check=True, timeout=5)

        try:
            bus = spawn('dbus-daemon', [
                'dbus-daemon', '--nofork', '--config-file=' + str(bus_config)])
            wait(bus_path.is_socket, 'private D-Bus socket missing')
            env['DBUS_SESSION_BUS_ADDRESS'] = 'unix:path=' + str(bus_path)
            sway = spawn('sway', ['/usr/bin/sway', '-c', str(sway_config)])
            def sway_ready():
                sway_socket = next(runtime.glob('sway-ipc*.sock'), None)
                if not sway_socket:
                    return None
                try:
                    result = subprocess.run(
                        ['swaymsg', '-s', str(sway_socket), '-r', '-t', 'get_version'],
                        env=env, capture_output=True, text=True, timeout=2)
                except subprocess.TimeoutExpired:
                    return None
                return sway_socket if result.returncode == 0 else None

            real_socket = wait(sway_ready, 'private Sway IPC did not become ready', seconds=15)
            env['WAYLAND_DISPLAY'] = wait(
                lambda: next((item.name for item in runtime.glob('wayland-*') if item.is_socket()), None),
                'private Wayland display missing')
            direct('workspace number 1')
            one = spawn('foot-1', ['foot', '--config=' + str(foot_config),
                                   '--app-id=ipc-one', '-e', 'sh', '-c', 'while :; do sleep 60; done'])
            wait(lambda: 'ipc-one' in direct('-t', 'get_tree').stdout, 'workspace 1 client missing')
            direct('workspace number 2')
            two = spawn('foot-2', ['foot', '--config=' + str(foot_config),
                                   '--app-id=ipc-two', '-e', 'python3', str(title_fixture),
                                   str(pressure_marker)])
            wait(lambda: 'ipc-two' in direct('-t', 'get_tree').stdout, 'workspace 2 client missing')
            extra_windows = [
                (1, 'ipc-one-extra', False),
                (2, 'ipc-two-extra', False),
                (3, 'ipc-three-title', True),
                (3, 'ipc-three-extra', False),
                (4, 'ipc-four-title', True),
                (5, 'ipc-five-title', True),
            ]
            for workspace, app_id, changes_title in extra_windows:
                direct(f'workspace number {workspace}')
                command = (['foot', '--config=' + str(foot_config), '--app-id=' + app_id,
                            '-e', 'python3', str(title_fixture), str(pressure_marker)]
                           if changes_title else
                           ['foot', '--config=' + str(foot_config), '--app-id=' + app_id,
                            '-e', 'sh', '-c', 'while :; do sleep 60; done'])
                process = spawn(app_id, command)
                wait(lambda app_id=app_id: app_id in direct('-t', 'get_tree').stdout,
                     f'{app_id} client missing')
            direct('workspace number 1')

            proxy_path = runtime / 'waybar-proxy.sock'
            proxy = IpcProxy(proxy_path, real_socket)
            bar_env = dict(env, SWAYSOCK=str(proxy_path), LD_PRELOAD=str(inspector),
                           MBP_INTEL_WAYBAR_IPC_INSPECTION=str(observation))
            bar = spawn('waybar', [str(waybar), '-l', 'debug'], local_env=bar_env)
            expected_events = {'workspace', 'window'}
            proxy.wait_subscriptions(1, seconds=15)
            proxy.wait_event_sets(1, expected_events)

            def focused(number):
                buttons = read_buttons(observation)
                return (str(number) in buttons and 'focused' in buttons[str(number)] and
                        all('focused' not in classes for text, classes in buttons.items()
                            if text != str(number)))

            wait(lambda: focused(1), 'Waybar did not initially render workspace 1 active')
            report['initial_buttons'] = read_buttons(observation)
            screenshot('initial.png')
            report['subscription_payloads_before_fault'] = proxy.drop_subscriptions()
            report['checks'].append('closed only acknowledged event subscription sockets')
            direct('rename workspace 2 to "2: Recovered Name"')
            direct('workspace "2: Recovered Name"')
            wait(lambda: any(item['name'] == '2: Recovered Name' and item['focused']
                             for item in json.loads(direct('-t', 'get_workspaces').stdout)),
                 'Sway did not focus workspace 2')
            report['sway_after_fault'] = json.loads(direct('-t', 'get_workspaces').stdout)

            tick_start = process_ticks(bar)
            cpu_start = time.monotonic()
            try:
                wait(lambda: focused('2: Recovered Name'),
                     'Waybar did not reconnect and refresh renamed workspace 2 without a later event',
                     seconds=8)
            finally:
                elapsed = time.monotonic() - cpu_start
                ticks = process_ticks(bar) - tick_start
                report['recovery_cpu_percent'] = round(
                    100 * ticks / os.sysconf('SC_CLK_TCK') / elapsed, 2)
                report['buttons_after_fault'] = read_buttons(observation)
                report['subscriptions_after_fault'] = len(proxy.accepted_subscriptions)
            require(report['recovery_cpu_percent'] < 10,
                    f'reconnect used {report["recovery_cpu_percent"]}% CPU')
            proxy.wait_event_sets(2, expected_events)
            report['subscription_payloads_after_recovery'] = [
                item.subscription_payloads for item in proxy.accepted_subscriptions]
            screenshot('recovered.png')
            report['checks'].append('reconnected, fetched current workspace state, and bounded CPU')

            direct('workspace number 1')
            wait(lambda: focused(1), 'workspace events stopped after reconnect')
            direct('workspace "2: Recovered Name"')
            wait(lambda: focused('2: Recovered Name'), 'second event stopped after reconnect')
            report['checks'].append('later workspace events continue after recovery')

            # A valid event header followed by an incomplete body must reconnect too.
            report['mid_payload_subscription'] = proxy.drop_subscriptions(mid_payload=True)
            report['mid_payload_injection'] = proxy.last_injection
            direct('rename workspace 1 to "1: Mid Frame"')
            direct('workspace "1: Mid Frame"')
            wait(lambda: focused('1: Mid Frame'),
                 'Waybar did not recover after an event ended mid-payload', seconds=8)
            proxy.wait_event_sets(3, expected_events)
            screenshot('mid-payload-recovered.png')
            report['checks'].append('mid-payload EOF reconnects and refreshes current state')

            if stress_seconds:
                start_pid = bar.pid
                start_subscriptions = len(proxy.accepted_subscriptions)
                start_ticks = process_ticks(bar)
                start_events = proxy.event_count((1 << 31) | 3)
                started = time.monotonic()
                deadline = started + stress_seconds
                workspace_names = {1: '1: Mid Frame', 2: '2: Recovered Name'}
                iteration = 0
                last_focused = '1: Mid Frame'
                pressure_marker.touch()
                try:
                    while time.monotonic() < deadline:
                        number = 2 if iteration % 2 == 0 else 1
                        replacement = f'{number}: Stress {iteration}'
                        command = ('rename workspace ' + json.dumps(workspace_names[number]) +
                                   ' to ' + json.dumps(replacement))
                        direct(command)
                        workspace_names[number] = replacement
                        direct('workspace ' + json.dumps(replacement))
                        wait(lambda: focused(replacement),
                             f'bar did not render {replacement!r} during title pressure', seconds=5)
                        last_focused = replacement
                        iteration += 1
                        next_change = min(deadline, started + iteration * 5)
                        while time.monotonic() < next_change:
                            require(bar.poll() is None, 'Waybar restarted or exited during pressure')
                            time.sleep(min(.1, next_change - time.monotonic()))
                finally:
                    pressure_marker.unlink(missing_ok=True)
                elapsed = time.monotonic() - started
                event_count = proxy.event_count((1 << 31) | 3) - start_events
                cpu_percent = round(100 * (process_ticks(bar) - start_ticks) /
                                    os.sysconf('SC_CLK_TCK') / elapsed, 2)
                time.sleep(1)
                wait(lambda: focused(last_focused),
                     'bar focus/name changed after title pressure stopped')
                idle_started = time.monotonic()
                idle_ticks = process_ticks(bar)
                time.sleep(3)
                idle_elapsed = time.monotonic() - idle_started
                idle_cpu_percent = round(100 * (process_ticks(bar) - idle_ticks) /
                                         os.sysconf('SC_CLK_TCK') / idle_elapsed, 2)
                report['stress'] = {
                    'elapsed_seconds': round(elapsed, 3), 'waybar_pid': bar.pid,
                    'window_events': event_count,
                    'window_events_per_second': round(event_count / elapsed, 2),
                    'workspace_updates_checked': iteration, 'cpu_percent': cpu_percent,
                    'idle_cpu_percent_after_pressure': idle_cpu_percent,
                    'synthetic_windows': 8, 'title_sources': 4,
                    'subscriptions_before': start_subscriptions,
                    'subscriptions_after': len(proxy.accepted_subscriptions),
                }
                require(bar.pid == start_pid and bar.poll() is None,
                        'Waybar process changed during pressure')
                require(len(proxy.accepted_subscriptions) == start_subscriptions,
                        'Waybar reconnected without an injected outage during pressure')
                require(event_count / elapsed >= 25,
                        f'only {event_count / elapsed:.1f} title events/second reached Waybar')
                require(idle_cpu_percent < 10,
                        f'Waybar retained {idle_cpu_percent}% idle CPU after pressure')
                screenshot('stress-final.png')
                report['checks'].append('sustained title pressure keeps focus/name current without restart')

            # SIGINT runs Waybar's normal shutdown path and must stay bounded during reconnect.
            proxy.drop_subscriptions()
            stopped = time.monotonic()
            os.killpg(bar.pid, signal.SIGINT)
            bar.wait(timeout=3)
            report['stop_during_reconnect_seconds'] = round(time.monotonic() - stopped, 3)
            require(bar.returncode == 0,
                    f'Waybar stop returned {bar.returncode}')
            report['checks'].append('clean stop remains bounded during reconnect')
            report['status'] = 'passed'
        except BaseException as error:
            report['status'] = 'failed'
            report['error'] = str(error)
            try:
                screenshot('failure-stale.png')
            except (OSError, subprocess.SubprocessError):
                pass
            raise
        finally:
            if proxy:
                proxy.close()
            for name, process in reversed(processes):
                if process.poll() is None:
                    try:
                        os.killpg(process.pid, signal.SIGTERM)
                    except ProcessLookupError:
                        pass
            for name, process in reversed(processes):
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    process.wait()
            log.close()
            (output / 'evidence.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--waybar', type=Path, default=Path('/usr/bin/waybar'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--stress-seconds', type=float, default=0)
    args = parser.parse_args()
    report = verify(args.waybar.resolve(), args.output.resolve(), args.stress_seconds)
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
