# Network ownership migration

This migration is not activated. The persistent DHCP transport, lease parser,
owned network applier and isolated harnesses are implemented separately from
the existing CLI; see [LEASE-OWNER.md](LEASE-OWNER.md) for their current
integration and proof scope.
No live client was signalled, no service was started, and no scan was requested.
Exact home and iPhone SSIDs still require
confirmation; neither a hostname nor a guessed hotspot name establishes trust.

## Existing owners

| Component | Verified local behavior |
| --- | --- |
| ifupdown-ng 0.13.0 | `/etc/network/interfaces` automatically starts `wlan0` with IPv4 DHCP and a separate static IPv6 address/gateway. |
| BusyBox 1.38.0 | `/usr/libexec/ifupdown-ng/dhcp` starts persistent `udhcpc -b -R`; `/run/udhcpc.wlan0.pid` identifies PID 2746. |
| WPA 2.11 | OpenRC supervises PID 2651 using `/etc/wpa_supplicant/wpa_supplicant.conf`. The file has one saved network and no `ctrl_interface`; `/run/wpa_supplicant` is empty. |
| OpenRC | `networking` and `wpa_supplicant` are in the boot runlevel. `wpa_cli` and `dhcpcd` are not enabled. |

`/usr/share/udhcpc/default.script` handles `bound`, `renew`, and `deconfig` and
writes routes and DNS. There are no custom `/etc/udhcpc` event hooks. Its final
`exit 0` does not prove every address, route or resolver update succeeded.
The existing client's `-R` requests lease release on exit; stopping it is not
a neutral ownership transfer.

## One DHCP client through acquisition and renewal

Extend the supervised controller to own one foreground DHCP child from its
creation through all renewals. The CLI should submit serialized commands to
that root-only service and wait for a bounded result. Do not start a second
client after a successful one-shot acquisition.

The proposed child command is:

```text
/sbin/udhcpc -f -n -t 5 -T 3 -i wlan0 \
  -s /usr/local/libexec/privacyctl-dhcp-event
```

Omit `-q` and `-b`: the same process must remain available for renewal, and its
supervisor must retain its identity. Keep the 20-second initial acquisition
deadline; success means an authenticated `bound` event followed by verified
address/route application, not that the DHCP process exited.

The implementation uses a private PID namespace and records host PID, start
time, pidfd and namespace identity during a readiness handshake. Do not add a
`-p` file containing namespace PID 1 or signal a host process using that value.
The launcher inherits parent-death protection; killing namespace init removes
its descendants, including hooks that create separate process sessions.

The hook should send bounded, validated event data to the owning daemon using
a private Unix socket and per-connection generation token. The daemon applies
lease changes under its transaction lock. A hook must not acquire `RadioLock`
while `connect` holds it and waits for DHCP; that creates a deadlock. Reject
stale generations and malformed DHCP values, and never evaluate hook data as
shell commands. Record PID/start time, lease generation and actual expiry
privately. Renew the lease indefinitely while the trusted session is healthy;
lease expiry is not an arbitrary session TTL.

Unexpected child exit, expired lease, failed application, or lost WPA identity
must clear authorization, block radios, stop the owned child and its hooks,
and remove owned network state. A daemon restart starts blocked and rejects
stale owner records before creating another client. Resolver changes also need
ownership checks so cleanup cannot overwrite another interface's newer DNS.

## Controlled ownership transfer

During a deliberate local-console migration, first verify radio blocking.
Disable `wlan0` automatic DHCP and static IPv6 provisioning in ifupdown-ng while
retaining unrelated interfaces. Stop only the verified existing DHCP owner and
wait for it and its hook children to exit before starting the new owner. Never
use a broad networking restart or rely only on a PID file.

Keep the existing home IPv6 address/gateway in a private profile. Restore them
only after verified home association. Before hotspot association, flush global
IPv6 addresses and routes from `wlan0`; retain link-local state. Returning home
must explicitly reapply its static settings: merely preserving whatever is
left after the hotspot flush cannot restore them. Decide and test per-profile
RA/autoconfiguration behavior as part of this transition.

## WPA control socket requires a disruptive migration

Installed WPA help says `-C` is used only without `-c`, so appending it to this
service is insufficient. WPA 2.11's `wpa_supplicant_reload_configuration()`
deauthenticates the current association, recreates a changed control interface,
and requests a scan when networks remain enabled. `SIGHUP` is therefore not a
harmless way to add a socket. See the [2.11 source](https://sources.debian.org/src/wpa/2:2.11-2/wpa_supplicant/wpa_supplicant.c).

Prepare an exact root-only backup and validated configuration with a root-only
`ctrl_interface`, explicit scan policy, and all saved networks disabled. With
Wi-Fi verified blocked, reload only the identified supervised process. Check
its identity and a bounded `PING`/`PONG` exchange on the new socket, then inspect
saved IDs privately. Do not unblock or select a network until the permitted
identity and controller path are ready. Socket migration alone should leave
Wi-Fi blocked; a new association is a separate action. This cannot preserve
the existing association without interruption.

## Required isolated proofs

- Exercise real acquisition, renewal, NAK, expiry and server loss using a private
  network namespace and synthetic DHCP server; host radios remain untouched.
- Prove one child PID survives successful renewal and no overlapping DHCP owner
  exists during transitions, failures or supervisor recovery.
- Test blocked hooks, forged/stale events, PID reuse and daemon death; failure
  must block before another client starts, without a lock/hook deadlock.
- Verify home → hotspot → home IPv6 behavior and DNS cleanup ownership.
- Test WPA reload with synthetic credentials and simulated radios: the disabled
  configuration must create its socket without starting discovery. Preserve
  logs of both successful migration and exact-backup recovery.

The persistent client manager and event hook are implemented as staged library
components. The radio owner service, compatible CLI routing and migration
installer are **not integrated**. Keep the existing live DHCP/WPA owners until
the remaining proofs and trusted-profile confirmation are complete. Permission
and Bluetooth-only preparation do not resolve this network ownership work.

## Resolver handoff

The installed dependency is locally patched `openresolv 3.17.4-r1`; its source,
build inputs and signed APK are archived with the current package lock. The
original Alpine `3.17.4-r0` remains archived for rollback and negative tests.
The upgrade changes only the resolver script, adding explicit compatibility
with the native runner's PID namespace. It preserved live addresses, routes,
DNS, radio state and DHCP identities; see
[resolver-bridge-install-verification.json](resolver-bridge-install-verification.json).
The active BusyBox hook continues writing its unmanaged resolver file directly.
Installing the capability does not activate a DNS provider or change hooks.

Native private tests now verify lease application, renewal, home/hotspot IPv6
restoration and ownership-preserving cleanup. The production backend requires
a reviewed libc-only subscriber configuration; the existing live configuration
is deliberately unchanged. See [RESOLVER-LOCKING.md](RESOLVER-LOCKING.md) for
the native locking failure, packaged fix and repeatable acceptance checks.

Initial `resolvconf -u` is a separate, deliberate migration: it takes ownership
of the unmanaged file and creates a backup. Do not invoke it during routine
leases or seed it with old DHCP values that would survive disconnection.
Use a generation-specific `privacyctl.<generation>.<interface>` provider with
`resolvconf -a` and exact-key `resolvconf -f -d`. Subscriber failure can occur
after the provider changed; inspect and remove only recorded owned state.
Private tests must isolate `/etc`, `/run` and subscriber side effects as well
as the network namespace. Native resolver state is not network-namespaced.
