"""Superhold: hold a configured key to view contextual shortcuts."""
import argparse
from contextlib import ExitStack
import json
import math
import os
from pathlib import Path
import signal
import sys
import time

from . import __version__
from .config import load_config
from .hold import EvdevMonitor, HoldState
from .service import (AlreadyRunning, ContextProvider, GraphicalSessionGuard,
                      ServiceController, SessionLease, _owned_private_directory,
                      connect_sway_watch, find_sway_socket, print_status,
                      probe_session, screen_locked)


def parse_args(arguments=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version', action='version', version=f'Superhold {__version__}')
    parser.add_argument('command', nargs='?', choices=('daemon', 'dump', 'preview', 'status'))
    aliases = parser.add_mutually_exclusive_group()
    aliases.add_argument('--dump', action='store_true', help='print contextual shortcuts as JSON')
    aliases.add_argument('--preview', action='store_true', help='show without input monitoring')
    parser.add_argument('--seconds', type=float, default=5.0, help='preview duration (default: 5)')
    parser.add_argument('--socket', help='Sway IPC socket')
    parser.add_argument('--profiles', help='explicit application profiles JSON (including legacy files)')
    parser.add_argument('--trigger', choices=('super', 'capslock'), help='physical hold trigger; no remapping')
    parser.add_argument('--backend', choices=('auto', 'sway', 'x11'), help='desktop backend')
    parser.add_argument('--hold-seconds', type=float, help='hold duration, 0.15 to 3 seconds')
    parser.add_argument('--config', help='explicit TOML configuration file')
    args = parser.parse_args(arguments)
    if (args.dump or args.preview) and args.command:
        parser.error('choose either a command or a --dump/--preview alias')
    if not math.isfinite(args.seconds) or not 0 < args.seconds <= 86400:
        parser.error('--seconds must be finite, greater than zero and at most 86400')
    args.command = 'dump' if args.dump else 'preview' if args.preview else args.command or 'daemon'
    try:
        args.settings = load_config(args.config, trigger=args.trigger, backend=args.backend,
                                    hold_seconds=args.hold_seconds)
    except ValueError as error:
        parser.error(str(error))
    return args


def select_backend(configured, socket_path=None, environ=None):
    environ = os.environ if environ is None else environ
    if configured != 'auto':
        if configured == 'x11' and socket_path:
            raise ValueError('--socket is only supported by the Sway backend')
        return configured
    if socket_path or environ.get('SWAYSOCK'):
        return 'sway'
    if environ.get('WAYLAND_DISPLAY'):
        raise RuntimeError('this Wayland session is unsupported; select Sway with --socket')
    if environ.get('DISPLAY'):
        return 'x11'
    raise RuntimeError('no supported graphical display; use Sway or X11')


def _wayland_socket(runtime):
    display = os.environ.get('WAYLAND_DISPLAY')
    if not display:
        raise RuntimeError('WAYLAND_DISPLAY is required')
    path = Path(display)
    return path if path.is_absolute() else runtime / path


def _provider(socket_path, profiles_path=None, decorate=False, *, backend='sway',
              display=None, trigger_label='Super'):
    if backend == 'x11':
        from .x11 import X11ShortcutProvider
        # Connections are owned by each background snapshot, not by Qt.
        return X11ShortcutProvider(display, profiles_path, trigger_label)
    from .sources import ShortcutProvider
    provider = ShortcutProvider(str(socket_path), profiles_path, trigger_label)
    return ContextProvider(provider, socket_path) if decorate else provider


def dump_snapshot(socket_path, profiles_path=None, **options):
    print(json.dumps(_provider(socket_path, profiles_path, **options).snapshot(),
                     ensure_ascii=False, indent=2))


def preview(socket_path, profiles_path=None, seconds=5.0, *, backend='sway',
            display=None, trigger_label='Super'):
    from .qt_overlay import create_application, QtShortcutOverlay
    from PyQt6.QtCore import QTimer
    application = create_application(['superhold'])
    overlay = QtShortcutOverlay(trigger_label=trigger_label)
    try:
        provider = _provider(socket_path, profiles_path, decorate=True,
                             backend=backend, display=display, trigger_label=trigger_label)
        overlay.show(provider.snapshot())
        QTimer.singleShot(max(1, int(seconds * 1000)), application.quit)
        application.exec()
    finally:
        overlay.close()


def _run_daemon(runtime, socket_path, profiles_path=None, *, backend='sway',
                display=None, settings=None):
    from .config import Config
    settings = settings or Config()
    lease = SessionLease(runtime, socket_path, display=display)
    try:
        lease.acquire()
    except AlreadyRunning:
        return
    last_status = None
    with ExitStack() as resources:
        resources.callback(lease.close)
        state = HoldState(settings.trigger, settings.hold_seconds)
        if backend == 'sway':
            watch = connect_sway_watch(socket_path)
            resources.callback(watch.close)
            monitor = EvdevMonitor(state=state)
            wayland_socket = _wayland_socket(runtime)
            lock_probe = screen_locked
        else:
            from .x11 import X11Monitor
            monitor = X11Monitor(state=state, display=display)
            watch = monitor
            wayland_socket = Path('x11')
            lock_probe = lambda _runtime, _socket: (monitor.locked if monitor.has_saver
                                                   else not guard.lock_authority)
        resources.callback(monitor.close)
        guard = GraphicalSessionGuard(
            runtime, wayland_socket,
            activity_probe=lambda: probe_session(backend, runtime, wayland_socket),
            lock_probe=lock_probe)
        resources.callback(guard.close)
        provider = _provider(socket_path, profiles_path, decorate=True, backend=backend,
                             display=display, trigger_label=settings.trigger_label)
        from .qt_overlay import create_application, QtShortcutOverlay
        from PyQt6.QtCore import QTimer
        application = create_application(['superhold'])
        overlay = QtShortcutOverlay(trigger_label=settings.trigger_label)
        resources.callback(overlay.close)
        controller = ServiceController(
            monitor, provider, overlay, watch, guard,
            loading_probe=provider.context if backend == 'x11' else None)
        resources.callback(controller.close)

        def tick():
            nonlocal last_status
            try:
                running = controller.tick(time.monotonic())
                status = (controller.visible, controller.source_pending,
                          controller.graphical_active, monitor.device_count, guard.locked,
                          getattr(monitor, 'error', None))
                if status != last_status:
                    lease.update('visible' if controller.visible else 'running',
                                 visible=controller.visible, source_pending=controller.source_pending,
                                 graphical_active=controller.graphical_active, locked=guard.locked,
                                 device_count=monitor.device_count, trigger=settings.trigger,
                                 hold_seconds=settings.hold_seconds,
                                 error=getattr(monitor, 'error', None))
                    last_status = status
                if not running:
                    application.quit()
            except Exception as error:
                print(f'superhold: {error}', file=sys.stderr)
                application.exit(1)

        timer = QTimer()
        timer.setInterval(25)
        timer.timeout.connect(tick)
        timer.start()
        resources.callback(timer.stop)
        for signum in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
            previous = signal.signal(signum, lambda _signum, _frame: application.quit())
            resources.callback(signal.signal, signum, previous)
        lease.update('running', visible=False, source_pending=False,
                     graphical_active=False, locked=True, device_count=monitor.device_count,
                     trigger=settings.trigger, hold_seconds=settings.hold_seconds)
        return application.exec()


def main(arguments=None):
    args = parse_args(arguments)
    backend = select_backend(args.settings.backend, args.socket)
    runtime_name = os.environ.get('XDG_RUNTIME_DIR')
    if not runtime_name:
        raise RuntimeError('XDG_RUNTIME_DIR is required')
    runtime = Path(runtime_name)
    _owned_private_directory(runtime)
    socket_path = find_sway_socket(runtime, args.socket) if backend == 'sway' else None
    display = os.environ.get('DISPLAY') if backend == 'x11' else None
    if backend == 'x11':
        from .x11 import display_identity
        display_identity(display)
    if args.command == 'status':
        return print_status(runtime, socket_path, display=display)
    options = {'backend': backend, 'display': display, 'trigger_label': args.settings.trigger_label}
    if args.command == 'dump':
        return dump_snapshot(socket_path, args.profiles, **options)
    os.environ['QT_QPA_PLATFORM'] = 'xcb' if backend == 'x11' else 'wayland'
    if args.command == 'preview':
        return preview(socket_path, args.profiles, args.seconds, **options)
    return _run_daemon(runtime, socket_path, args.profiles, backend=backend,
                       display=display, settings=args.settings)
