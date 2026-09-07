# Persistent DHCP ownership

These components are staged under `root/usr/local/lib/privacyctl_runtime`.
They are connected to the staged persistent service and CLI routing, but are
not installed. The live WPA and DHCP services still own the WLAN connection. Exact trusted
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

## Owned address, route and resolver application

`LeaseApplier` accepts typed leases and separate private `IPv6Profile` values.
It records interface identity, generation and a current immutable ownership
record. Addresses and routes use protocol 196; explicit route metrics and
`noprefixroute` avoid adopting unrelated kernel state. Deletion checks the
recorded resource and protects unrelated IPv4 secondary addresses. An empty
IPv6 profile removes only previously owned static values; returning home
explicitly reapplies its configured addresses and gateways.

DNS uses an exact generation-specific openresolv provider. Cleanup checks its
contents and the subscriber output, preserving other providers. Application
shares four seconds across its operations, including IPv6 duplicate-address
detection; removal shares three seconds. The five-second hook deadline and
actual lease expiry remain independent limits and may reject earlier. Partial errors
carry `NetworkError.owned`; `applier.current` remains available after an
interruption. The owner must block first and then remove that recorded state.

Each native command has bounded capture and a contained process lifetime.
Ordinary openresolv PID locking needed an explicit compatibility patch; see
[RESOLVER-LOCKING.md](RESOLVER-LOCKING.md). Stock capability, unmanaged resolver
files and unreviewed service/cache hooks are refused before lease mutation.
This does not change the machine's existing resolver configuration or hooks.

Real private tests cover renewal, home → hotspot → home, unrelated IPv6 and
DNS preservation, stale ownership and off-prefix `/32` gateways. The stock
locking failure, patched lock coexistence and native application results are
recorded separately in [network-verification.json](network-verification.json).

## Reproduce the isolated checks

Run from the repository checkout:

```sh
python3 -m unittest discover -s alpine/security/radio/tests -p test_lease.py -v
doas python3 -m unittest discover -s alpine/security/radio/tests -p test_dhcp.py -v
python3 alpine/security/radio/tests/verify_dhcp_network.py --output /tmp/dhcp-fixture-proof
python3 alpine/security/radio/tests/verify_dhcp_network.py --production-manager --output /tmp/dhcp-manager-proof
python3 alpine/security/radio/tests/verify_dhcp_network.py --production-manager --exercise-cleanup --output /tmp/dhcp-cleanup-proof
```

The native harness creates private network, PID and mount namespaces before
using veth and a synthetic DHCP server. Guards reject the host namespace before
any interface or mount operation. Host rfkill, WPA sockets and resolver paths
are hidden. It exercises acquisition, same-process renewal, NAK, server silence
and no offers, and records both host-state equality and owned-child cleanup.
The fixture must never run Alpine's default DHCP hook against the host.

The separate production-manager run uses the real manager and hook, with only
private fixture address application. It proves manager integration, independent
expiry and teardown, while lease application, radio ownership and firewall
renewal remain separate checks. [dhcp-verification.json](dhcp-verification.json)
records each tested component and its source hash. Unicast renewal UDP 68 → 67 and
offered DNS still need separate packet-gate/OpenSnitch proof; do not silently
widen grants to make those checks pass.

## Remaining integration

The staged persistent owner now drains control and DHCP sockets, invalidates
pending generations on cancellation, and keeps successful sessions after CLI
exit. Startup blocks and rejects stale authorization; emergency off remains
usable without the owner. See [OWNER-SERVICE.md](OWNER-SERVICE.md).

The combined fixture now passes seven native owner cases; its source-hashed
evidence and repeatable command are in [OWNER-SERVICE.md](OWNER-SERVICE.md).
Complete combined blocked-hook cancellation, daemon-death and packet-policy
proofs, per-profile RA/SLAAC decisions, resolver takeover, verified legacy-owner
termination, orphan state recovery and reboot tests before replacing live services. See
[NETWORK-MIGRATION.md](NETWORK-MIGRATION.md).
