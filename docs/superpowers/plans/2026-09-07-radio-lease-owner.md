# Persistent Radio Lease Owner Implementation Plan

> **For agentic workers:** Use Superpowers subagent-driven-development with
> Fossil check-ins. Implement and independently review each unit before live
> activation. The user's standing authorization covers this radio work.

**Goal:** Keep one supervised DHCP client through acquisition and renewal, and
make radio authorization end on disconnect, cancellation or lease failure.

**Architecture:** A root-only owner receives serialized CLI requests and
processes pending WPA/DHCP operations without blocking event ingestion. DHCP
uses a private PID namespace: a parent-death-protected launcher runs `unshare`,
whose namespace init performs a credential-checked handshake before executing
one foreground `udhcpc`. Namespace-init death terminates its descendants.
Lease parsing and network application are separate from process ownership.

**Tech Stack:** Alpine edge, Python 3.14 standard library, BusyBox 1.38.0,
util-linux 2.42.3, iproute2, OpenRC, wpa_supplicant 2.11 and Fossil.

**Spec:** `alpine/security/radio/NETWORK-MIGRATION.md`, the existing radio
activation plan, and the user's full MBP Intel privacy/rebuild objective.

## Global constraints

- Preserve the active WLAN association and current WPA/DHCP owners during
  development. No live scans, service restart, address/DNS changes or migration.
- Preserve the installed Bluetooth-only block and readable/root-writable rfkill.
- Exact home/hotspot identities remain unresolved; do not guess or activate them.
- Preserve all 63 existing radio tests and the existing status/off/scan/connect
  command shapes. Connect/scan must not fall back to direct control without an
  owner. Bootstrap/emergency off must work before the owner starts.
- Use root-private sockets/records, exact generation identities, bounded
  requests and PID handles. Never execute DHCP-supplied text as code.
- Block radios before waiting for child teardown or lease cleanup. Successful
  renewal extends the real lease; there is no arbitrary healthy-session TTL.
- Credentials and actual network/address records stay outside Fossil. Use
  synthetic addresses and namespace guards for destructive test cases.

## Design choices

Keeping the one-shot `-q` client would lose renewal. Handing a lease to a second
client would create overlapping ownership. Keep one foreground client instead.
The previously tested process-group helper is insufficient once a polled leader
has exited. A private PID namespace gives the client and all hooks one lifetime,
including descendants that call `setsid`, without changing host cgroups.

The installed `unshare` and kernel already passed synthetic owner/init death
checks. Use pidfd SIGKILL for `unshare`, whose default fork mode blocks SIGTERM.
Launch from the persistent owner thread. Wait for both launcher and init pidfds
before accepting a replacement. Do not use namespace PID `1` as a host PID file.

## Task 1: Validated lease values

**Files:** Create `alpine/security/radio/root/usr/local/lib/privacyctl_runtime/`
with `__init__.py` and `lease.py`; add `tests/test_lease.py`.

**Interface:**

```python
lease = Lease.from_event(fields, expected_interface="wlan0")
# lease.interface: str; address: IPv4Interface
# routers, dns: tuple[IPv4Address, ...]; server: IPv4Address
# lease_seconds: int; lease.to_dict(): JSON-safe normalized values
```

- [x] Write failing examples for injected/control-character fields, wrong
  interface, oversized input, noncontiguous masks and conflicting mask forms.
- [x] Accept only interface/ip/subnet/mask/router/dns/lease/serverid strings;
  bound router and resolver counts. Handle /31 and /32 hosts explicitly.
- [x] Prove ordinary private/documentation addresses parse without becoming a
  trust decision; profile/firewall authorization belongs to the owner.

Example contract:

```python
lease = Lease.from_event({"interface": "test0", "ip": "192.0.2.2",
    "subnet": "255.255.255.0", "router": "192.0.2.1", "dns": "192.0.2.1",
    "lease": "30", "serverid": "192.0.2.1"}, expected_interface="test0")
assert str(lease.address) == "192.0.2.2/24"
assert lease.lease_seconds == 30
```

## Task 2: Persistent client and bounded event transport

**Files:** Add runtime `dhcp.py`, `launch.py`, `hook.py`, root libexec entrypoints
`privacyctl-dhcp-launch` and `privacyctl-dhcp-event`, and `tests/test_dhcp.py`.

**Interface:** `DHCPManager.start(generation, interface)`, `poll(timeout=0)`,
`reply(event_id, accepted)`, `stop()`. Poll returns typed lease events or failures;
lease events include an ID, kind, receive time and parsed `Lease`. Manager state
tracks launch/acquisition/bound phases, PID handles and CLOCK_BOOTTIME expiry.
It never changes addresses, DNS, firewall policy or radio state.

The event transport is root-private AF_UNIX/SOCK_SEQPACKET. Hook frames are:

```json
{"version":1,"generation":"0123456789abcdef0123456789abcdef","event":"bound","fields":{"interface":"test0","ip":"192.0.2.2","mask":"24","lease":"30","serverid":"192.0.2.1"}}
```

The hook receives `PRIVACYCTL_EVENT_SOCKET` and `PRIVACYCTL_GENERATION`, copies
only whitelisted DHCP fields and waits at most five seconds for `{"ok":true}`
or failure. The owner checks SO_PEERCRED, generation and the recorded client
namespace. Readiness handshake captures host PID/start time/pidfd before exec.
Root-only implementation paths are fixed by the service, not supplied by CLI.

- [x] Prove initial `deconfig` does not cancel acquisition. Post-bound deconfig,
  NAK, leasefail, child exit, hook failure or expiry must produce a failure.
- [x] Acquisition allows 20 seconds; accepted bound/renew starts expiry from
  receipt time, so application latency cannot extend a lease.
- [x] Reject stale/forged frames and partial/oversized messages without hanging.
- [x] Prove one client PID survives renewals, and PID-namespace teardown removes
  detached hooks after owner, launcher or client death. Reject overlapping start.

## Task 3: Apply and remove owned network state

**Files:** Runtime `network.py`, `tests/test_network.py`.

**Interface:** `LeaseApplier.apply(lease, previous)` returns an ownership record;
`remove(owned)` removes only verified recorded state. Profile IPv6 configuration
is root-private, separate from DHCP data. The owner supplies cancellation checks
between bounded kernel/resolver operations.

- [x] Reproduce partial address/route/resolver failures before implementation.
- [x] Apply/verify normalized addresses and tagged routes through argument
  arrays; never interpolate server values into shell commands.
- [x] Use a dedicated openresolv provider and check ownership before deletion;
  preserve another interface's newer resolver state.
- [x] Exercise home → hotspot → home IPv6 restoration, including explicit
  reapplication of home static addresses/gateway after hotspot flushing.
- [x] Keep DHCP/resolver firewall policy separate. Broadcast acquisition does
  not prove that unicast renewal or a newly offered DNS server is permitted.

## Task 4: Owner service and compatible command routing

**Files:** Runtime `service.py`, staged `root/usr/local/sbin/privacyctl`, OpenRC
supervisor definition, and `tests/test_service.py`.

- [x] Keep acquisition/scan as pending states while servicing hook and control
  sockets. Do not call the old blocking connection method on the only event
  ingestion thread. ACK a lease only after verified application and WPA identity.
- [x] Make off invalidate pending generations and block before child cleanup;
  a disconnected requesting CLI cancels an unfinished request. Established
  sessions persist after their successful CLI exits.
- [x] Every owner restart blocks and rejects stale authorization before readiness.
  Preserve root-only emergency/boot off when the service socket is absent.
- [x] Prove component cancellation, no overlapping client, stale request
  rejection and bounded IPC failures; exercise both guardian/owner deaths with
  real private processes and marker callbacks.
- [ ] Prove cancellation during blocked hooks, daemon death, no overlapping
  client, stale request rejection and bounded CLI failures with the combined
  synthetic WPA / real DHCP / native application fixture. Component tests do
  not establish this integrated behavior or the complete radio policy.

## Task 5: Real isolated network proof

**Files:** `tests/verify_dhcp_network.py`, `tests/fixtures/dhcp_event.py`, sanitized
verification JSON under `alpine/security/radio/`.

- [x] Use a stdlib synthetic DHCP server and veth between separate private net
  namespaces, under private PID/mount namespaces. Check namespace identities
  before every setup path can touch ip/mount; use private proc/run/etc/dev/sys.
- [x] Observe real acquisition and short-lease renewal with one udhcpc PID.
  Exercise NAK/deconfig, server silence through expiry and initial no-offer.
- [x] Integrate the production event helper and manager after unit tests;
  record host-state equality and exact owned-process cleanup.
- [x] Integrate production lease application and the radio owner with those
  events: seven combined cases pass with real veth IPv6 DAD, same-client
  renewal, off/stale-fence/scan behavior, profile restoration, NAK and silence.
  Host state matches and no private processes survive. The WPA/radio substitutes
  and remaining combined fault cases are explicitly recorded.
- [ ] Include packet-gate/OpenSnitch renewal behavior in the final activation
  proof; do not silently widen existing grants for DHCP or DNS.

## Task 6: Review and reproducibility

- [x] Run the existing and new isolated suites and independent code review.
  Match source hashes to the exercised versions before recording evidence.
- [x] Update migration instructions with actual implemented component scope
  and remaining trusted-profile, live migration and reboot requirements.
- [x] Archive the openresolv compatibility source, recipe and identical signed
  builds; verify the current 1,080-package lock against the installed world.
- [ ] Update the activation plan and installer for persistent ownership and
  orphan recovery after the remaining combined fault/packet-policy proofs.

Record scoped owner check-ins, the unchanged package-lock comparison and the
consistent Fossil backup in `alpine/PROGRESS.md`. Preserve other contributors'
uncommitted progress while updating that record.

Live activation is a subsequent verified transition after these requirements
and the exact trusted identities are satisfied. A successful isolated component
test alone does not establish the requested live privacy policy.
