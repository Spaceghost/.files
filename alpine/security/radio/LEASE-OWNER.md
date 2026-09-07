# Persistent DHCP ownership

These components are staged under `root/usr/local/lib/privacyctl_runtime`.
They are not installed or connected to the legacy `privacyctl` CLI. The live
WPA and DHCP services still own the current WLAN connection. Exact trusted
network identities and a controlled local-console migration remain prerequisites.

## Components and boundaries

`Lease.from_event()` accepts eight bounded DHCP fields and produces immutable
IPv4 values. It rejects malformed masks, control characters, wrong interfaces,
invalid endpoints and oversized lists. Passing validation does not establish
trust in the server, SSID or offered resolver.

`DHCPManager` owns one foreground BusyBox client from acquisition through
renewal. A root-private, generation-specific `SOCK_SEQPACKET` socket accepts
events only from the recorded PID namespace. Readiness captures host PID,
start time and pidfd before namespace init executes `udhcpc`. The outer
launcher and namespace init have parent-death protection; init death removes
all descendants, including detached hooks. Starts cannot overlap an existing
owner. Production executable paths are fixed, never CLI/environment overrides.

The manager reports lease events and failures; it does not configure radios,
IP addresses, DNS or firewall rules. The owner must verify association and apply
the lease before acknowledging it. On failure, **block radios before stopping
the client or removing network state**. Do not call the old blocking connection
method on the only thread that drains DHCP events.

## Deadlines

Initial acquisition permits 20 seconds; hooks have five seconds total to receive
an acknowledgement. Accepted lease expiry uses `CLOCK_BOOTTIME`, including
suspend, from event receipt rather than completion of address application.
Expiry, client death, invalid data, NAK, lease failure or post-bound deconfig
ends authorization. Initial deconfig is acknowledged without ending acquisition.

The synthetic 16-second lease exposed BusyBox reporting deconfig after lease
expiry. Therefore the owner checks its own expiry clock independently of
BusyBox notifications. Healthy renewals extend the lease without a session TTL.

## Reproduce the isolated checks

Run from the repository checkout:

```sh
python3 -m unittest discover -s alpine/security/radio/tests -p test_lease.py -v
doas python3 -m unittest discover -s alpine/security/radio/tests -p test_dhcp.py -v
python3 alpine/security/radio/tests/verify_dhcp_network.py --help
```

The native harness creates private network, PID and mount namespaces before
using veth and a synthetic DHCP server. Guards reject the host namespace before
any interface or mount operation. Host rfkill, WPA sockets and resolver paths
are hidden. It exercises acquisition, same-process renewal, NAK, server silence
and no offers, and records both host-state equality and owned-child cleanup.
The fixture must never run Alpine's default DHCP hook against the host.

The fixture-client proof alone does not prove the production manager, lease
application, radio owner or firewall renewal path. Evidence records the actual
tested components and their source hashes. Unicast renewal UDP 68 → 67 and
offered DNS still need separate packet-gate/OpenSnitch proof; do not silently
widen grants to make those checks pass.

## Remaining integration

Connect the manager and owned network application to a persistent radio owner
that drains both control and DHCP sockets. Off and cancelled CLI requests must
invalidate pending generations; successful sessions outlive their CLI. A
restart starts blocked and rejects stale authorization. Bootstrap off must
remain usable before the owner starts. Add explicit per-profile IPv6 policy,
resolver takeover, verified legacy-owner termination, recovery and reboot tests
before replacing the live services. See [NETWORK-MIGRATION.md](NETWORK-MIGRATION.md).
