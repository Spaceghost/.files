"""Serialized radio authorization and persistent DHCP lease ownership.

Only the service thread calls this object. Checkpoints may ingest control and
DHCP events inside a bounded WPA/kernel operation, but never recursively apply
leases or tear down resources. Cancellation invalidates authorization and blocks
immediately; the outer step then retries cleanup until every owner is released.
"""
from collections import deque
import re
import secrets
import threading

from .dhcp import Failure, LeaseEvent, boottime
from .network import IPv6Profile


class OwnerError(RuntimeError):
    pass


class Owner:
    def __init__(self, *, server, adapter, dhcp, applier_factory, clock=boottime):
        self.server, self.adapter, self.dhcp = server, adapter, dhcp
        self.applier_factory, self.clock = applier_factory, clock
        self.phase = 'stopped'
        self.generation = None
        self.profile = None
        self.ipv6 = IPv6Profile()
        self.owned = None
        self.applier = None
        self.wpa = None
        self.pending = None
        self._thread = None
        self._requests = deque()
        self._off_requests = []
        self._off_error = None
        self._nonces = set()
        self._nonce_order = deque()
        self._error = None
        self._blocked = False
        self._dhcp_started = False
        self._lease_event = None
        self._applying = False
        self._checking = False
        self._overall_deadline = None
        self._phase_deadline = None
        self._next_status = 0
        self._next_idle_block = 0

    def _same_thread(self):
        if self._thread != threading.get_ident():
            raise OwnerError('radio owner must remain on its persistent thread')

    def start(self):
        if self.phase != 'stopped':
            raise OwnerError('radio owner already started')
        self._thread = threading.get_ident()
        # No readiness or stale authorization survives an owner restart.
        self.adapter.block_all()
        self._blocked = True
        self.adapter.clear_session()
        self.phase = 'idle'
        self._next_idle_block = self.clock() + 1

    @staticmethod
    def _respond(request, ok, result='', error=''):
        try:
            return request.respond(ok, result=result, error=error)
        except Exception:
            return False
        finally:
            request.close()

    def _latch(self, reason):
        self.generation = None
        self._lease_event = None
        self._error = self._error or str(reason)
        self.phase = 'cleanup'
        # This is deliberately the only cancellation side effect at a callback.
        # A failed block prevents cleanup and is retried by the outer loop.
        self._blocked = False
        try:
            self.adapter.block_all()
            self._blocked = True
        except Exception as error:
            self._error = 'radio block failed: ' + str(error)

    def _pump_requests(self):
        requests = self.server.poll()
        accepted = []
        for request in requests:
            if request.nonce in self._nonces:
                self._respond(request, False, error='duplicate request nonce')
                continue
            self._nonces.add(request.nonce)
            self._nonce_order.append(request.nonce)
            if len(self._nonce_order) > 4096:
                self._nonces.remove(self._nonce_order.popleft())
            accepted.append(request)
        off = [request for request in accepted if request.command == 'off']
        if off:
            self._off_requests.extend(off)
            try:
                # This checkpoint can run while unblock holds RadioLock. The
                # atomic fence write must not recursively acquire that lock.
                self.adapter.invalidate_fence()
            except Exception as error:
                self._off_error = 'off cancellation fence failed: ' + str(error)
            self._latch(self._off_error or 'radio authorization cancelled')
            for request in self._requests:
                self._respond(request, False, error='cancelled by off')
            self._requests.clear()
        for request in accepted:
            if request.command == 'off':
                continue
            if off:
                self._respond(request, False, error='cancelled by off')
            elif request.command not in ('scan', 'connect'):
                self._respond(request, False, error='unsupported owner command')
            elif len(self._requests) >= 32:
                self._respond(request, False, error='owner request queue full')
            else:
                self._requests.append(request)
                if self.generation is not None:
                    self._latch('radio request superseded')

    def _poll_dhcp(self):
        if not self._dhcp_started or self.generation is None:
            return
        events = self.dhcp.poll(0)
        failure = next((event for event in events if isinstance(event, Failure)), None)
        if failure:
            raise OwnerError(failure.reason)
        for event in events:
            if not isinstance(event, LeaseEvent):
                raise OwnerError('unknown DHCP event')
            if self._lease_event is not None or self._applying:
                raise OwnerError('overlapping DHCP lease events')
            self._lease_event = (self.generation, event)

    def checkpoint(self):
        """Pump cancellations during bounded native operations; no nested cleanup."""
        self._same_thread()
        if self._checking:
            raise OwnerError('recursive radio checkpoint')
        self._checking = True
        try:
            self._pump_requests()
            if self.generation is None:
                raise OwnerError(self._error or 'radio generation is no longer authorized')
            if self.pending is not None and not self.pending.alive():
                raise OwnerError('requesting client disconnected')
            now = self.clock()
            if (self._overall_deadline is not None and now >= self._overall_deadline
                    or self._phase_deadline is not None and now >= self._phase_deadline):
                raise OwnerError('radio request deadline exceeded')
            self.adapter.check_generation(self.generation)
            if not self.adapter.bluetooth_blocked():
                self.adapter.block_bluetooth()
                if not self.adapter.bluetooth_blocked():
                    raise OwnerError('Bluetooth is not blocked')
            self._poll_dhcp()
        except Exception as error:
            if self.generation is not None:
                self._latch(error)
            raise
        finally:
            self._checking = False

    def _cleanup(self):
        """Called only after callback unwinding; retain partial owners on error."""
        try:
            self.adapter.block_all()
            self._blocked = True
        except Exception as error:
            self._blocked = False
            self._finish_cancel(str(error))
            return False
        errors = []
        if self._dhcp_started:
            try:
                self.dhcp.stop()
                self._dhcp_started = False
            except Exception as error:
                errors.append(str(error))
        if self.applier is not None and not self._dhcp_started:
            try:
                # The wrapper may own a crash marker even before first apply.
                self.owned = self.applier.current
                self.applier.remove(self.owned)
                self.owned = None
                self.applier = None
            except Exception as error:
                self.owned = self.applier.current
                errors.append(str(error))
        if self.wpa is not None:
            try:
                self.wpa.close()
                self.wpa = None
            except Exception as error:
                errors.append(str(error))
        try:
            self.adapter.clear_session()
        except Exception as error:
            errors.append(str(error))
        error = '; '.join(errors)
        self._finish_cancel(error)
        if errors:
            self.phase = 'cleanup'
            return False
        self.phase = 'idle'
        self._next_idle_block = self.clock() + 1
        self.profile = None
        self._error = None
        self._overall_deadline = self._phase_deadline = None
        return True

    def _finish_cancel(self, cleanup_error):
        if self.pending is not None:
            self._respond(self.pending, False, error=cleanup_error or self._error or 'cancelled')
            self.pending = None
        off_error = cleanup_error or self._off_error or ''
        for request in self._off_requests:
            self._respond(request, not off_error, result='radios blocked' if not off_error else '',
                          error=off_error)
        self._off_requests.clear()
        self._off_error = None

    def _begin(self, request):
        if not request.alive():
            request.close()
            return
        self.pending = request
        self._overall_deadline = self.clock() + 45
        self._phase_deadline = self.clock() + (15 if request.command == 'scan' else 20)
        # Replacement only arrives here after verified cleanup of the old owner.
        self.adapter.block_all()
        self._blocked = True
        self.adapter.clear_session()
        self.generation = secrets.token_hex(16)
        self.adapter.begin_generation(self.generation, expected_fence=request.fence)
        self.profile = request.profile if request.command == 'connect' else None
        self.phase = 'scanning' if request.command == 'scan' else 'connecting'
        self.checkpoint()
        if request.command == 'connect':
            self.network_id, self.ssid, self.ipv6 = self.adapter.read_profile(self.profile)
            self.applier = self.applier_factory(self.generation, self.checkpoint)
            prepare = getattr(self.applier, 'prepare', None)
            if prepare is not None:
                # Retain the wrapper first so a partial alias/journal prepare
                # remains reachable by blocked cleanup if preparation fails.
                prepare()
        self.wpa = self.adapter.open_wpa(self.checkpoint)
        self.wpa.expect_ok('DISCONNECT')
        self.wpa.expect_ok('DISABLE_NETWORK all')
        if request.command == 'connect':
            if self.wpa.network_ssid(self.network_id) != self.ssid:
                raise OwnerError('configured network does not match policy')
            self.wpa.expect_ok('SELECT_NETWORK ' + str(self.network_id))
            self.wpa.expect_ok('ENABLE_NETWORK ' + str(self.network_id))
        self.checkpoint()
        self.adapter.unblock_wifi(self.checkpoint)
        self._blocked = False
        if request.command == 'scan':
            self._scan_id = self.wpa.start_scan()
            if type(self._scan_id) is not int or not 0 <= self._scan_id <= 0xffffffff:
                raise OwnerError('invalid native scan identifier')
        else:
            self.wpa.expect_ok('RECONNECT')
            self._next_status = self.clock()

    def _identity(self, *, required):
        status = self.wpa.status()
        completed = status.get('wpa_state') == 'COMPLETED'
        if completed and (status.get('id') != str(self.network_id) or status.get('ssid') != self.ssid):
            raise OwnerError('WPA completed an unauthorized network identity')
        if required and not completed:
            raise OwnerError('trusted WPA association lost')
        return completed

    def _apply_lease(self):
        generation, event = self._lease_event
        self._lease_event = None
        if generation != self.generation:
            raise OwnerError('stale DHCP lease generation')
        self._applying = True
        try:
            self.checkpoint()
            self._identity(required=True)
            self.owned = self.applier.apply(event.lease, previous=self.owned, ipv6=self.ipv6)
            self.checkpoint()
            self._identity(required=True)
            self.checkpoint()
            if not self.dhcp.reply(event.event_id, True):
                raise OwnerError('DHCP lease acknowledgment failed')
            self.checkpoint()
            if self.pending is not None:
                self.adapter.write_session(self.profile, self.network_id, self.ssid)
                self.checkpoint()
                request = self.pending
                if not self._respond(request, True, result='connected ' + self.profile):
                    raise OwnerError('connection result could not reach requesting client')
                self.pending = None
            self.phase = 'bound'
            self._overall_deadline = self._phase_deadline = None
        except Exception:
            self.owned = self.applier.current
            # Rejection/stop happens after blocking even when cancellation came
            # from a dependency rather than one of our explicit checkpoints.
            if self.generation is not None:
                self._latch('DHCP lease application failed')
            self.dhcp.reply(event.event_id, False)
            raise
        finally:
            self._applying = False

    def _advance(self):
        self.checkpoint()
        if self.phase == 'scanning':
            for _ in range(128):
                event = self.wpa.read_event(0)
                if event is None:
                    break
                match = re.fullmatch(r'<[0-9]+>CTRL-EVENT-SCAN-RESULTS id=([0-9]{1,10})', event)
                if match and int(match[1]) == self._scan_id:
                    results = self.wpa.request('SCAN_RESULTS')
                    if not results.startswith('bssid'):
                        raise OwnerError('fresh scan results rejected')
                    self.checkpoint()
                    request, self.pending = self.pending, None
                    self._latch('scan complete')
                    if self._cleanup():
                        self._respond(request, True, result=results)
                    else:
                        self._respond(request, False, error='scan cleanup remains pending')
                    return
        else:
            if self.clock() >= self._next_status:
                completed = self._identity(required=self.phase != 'connecting')
                self._next_status = self.clock() + .25
                if self.phase == 'connecting' and completed:
                    self.phase = 'acquiring'
                    self._phase_deadline = self.clock() + 20
                    # Retain ownership on partially failed start for cleanup.
                    self._dhcp_started = True
                    self.dhcp.start(self.generation, 'wlan0')
                    self.checkpoint()
            if self._lease_event is not None:
                self._apply_lease()

    def step(self):
        self._same_thread()
        if self.phase == 'stopped':
            raise OwnerError('radio owner has not started')
        try:
            self._pump_requests()
            if self._requests and self.generation is not None:
                self._latch('radio request superseded')
            if self.phase == 'cleanup' and not self._cleanup():
                while self._requests:
                    self._respond(self._requests.popleft(), False, error='previous cleanup remains pending')
                return
            if self._requests:
                self._begin(self._requests.popleft())
            if self.generation is not None:
                self._advance()
            elif self.phase == 'idle' and self.clock() >= self._next_idle_block:
                self.adapter.block_all()
                self._blocked = True
                self._next_idle_block = self.clock() + 1
        except Exception as error:
            self._latch(error)
            self._cleanup()

    def shutdown(self):
        self._same_thread()
        self._latch('radio owner shutting down')
        for request in self._requests:
            self._respond(request, False, error='radio owner shutting down')
        self._requests.clear()
        if not self._cleanup():
            raise OwnerError('radio owner cleanup remains pending')
        self.phase = 'stopped'
