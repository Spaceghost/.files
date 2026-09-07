# Radio privacy controller

## Current activation state

On 2026-09-07, the reviewed permission helper and
`72-privacy-rfkill.rules` were installed. `/dev/rfkill` is now `root:root`,
`0644`, without an access ACL or `uaccess` tag: Jack can read status but cannot
open it for writing. Root retains write access. Independent checks matched the
installed helper/rule hashes to this repository, preserved Wi-Fi identity and
addresses, and confirmed unchanged routes after excluding only `expires`
fields. Both radios remained unblocked during this initial permission-only step.

Subsequent Bluetooth-only preparation installed
`71-privacy-bluetooth-off.rules`. Bluetooth is now software-blocked; WLAN radio
state, association, addresses and routes remain unchanged. Independent checks
verified the same device registrations and exact installed rule instance.
Waybar's radio tooltip data reports Bluetooth blocked and WLAN enabled. See
[bluetooth-verification.json](bluetooth-verification.json) and
[BLUETOOTH.md](BLUETOOTH.md) for the separate policy and token-based recovery.

The controller, trusted profiles, OpenRC services, sleep hook, WPA policy and
DHCP changes remain staged. Waybar still reports radio state correctly; its
existing rfkill handle and both wpa_supplicant handles are read-only. Permission
changes do not revoke previously opened handles or remove the existing
unrestricted wheel `nopass` doas authority. This is a direct-access restriction,
not proof of radio silence or exclusive controller authority.

Sanitized evidence is in [permissions-verification.json](permissions-verification.json).
The exact private recovery journal is
`/var/lib/oldbook/radio-permissions/attempt-0huvvd1q`; keep its association data
out of Fossil. Reboot and seat-change persistence remain unverified.

## Staged persistent controller

`privacyctl supervise` now runs the persistent owner and its process guardian.
`connect PROFILE` and `scan` use its root-only command socket; they cannot
fall back to one-shot DHCP. The existing `status [--json]` output remains
read-only and available without that socket. `off` requests cancellation and
retains a direct emergency blocking path when the service is unavailable.

A scan disables saved networks while blocked, requests a native scan ID, and
requires the matching completion event before reading results. It re-blocks
when finished or on failure. A connection verifies the selected saved ID and
exact SSID before unblocking, then retains one DHCP client through renewal.
The native lease applier verifies generation-owned addresses, routes and DNS;
healthy connections persist until off, disconnection or an authorization failure.

Off invalidates older queued requests as well as current work. Cancellation
blocks before child teardown and owned-state cleanup. An unresolved cleanup
prevents another connection. Startup rejects stale authorization, and a crash
marker prevents silently adopting orphaned lease state. See
[OWNER-SERVICE.md](OWNER-SERVICE.md) for commands, deadlines, process death,
private IPv6 settings and recovery boundaries.

## Trusted policy and display contract

The root policy maps `shmecklebucket` and an explicitly enabled
`iphone-hotspot` profile to existing numeric WPA network IDs and exact SSIDs.
The controller never reads or changes a PSK. Neither profile is activated:
the saved home spelling differs from the requested name, and the exact hotspot
name is unresolved. Do not substitute a guessed name or hostname.

The status contract remains suitable for Waybar and a small GUI:

```json
{"wifi":{"interface":"wlan0","soft_blocked":true,"hard_blocked":false,"wpa_state":"UNAVAILABLE"},"bluetooth":{"soft_blocked":true,"hard_blocked":false}}
```

Software and hardware blocks are independent booleans, or `null` when their
state cannot be read. Status does not query WPA and omits SSIDs and credentials.
This example describes the schema, not the current host's state.

## Activation boundary

The WPA fragment uses `passive_scan=1`, `p2p_disabled=1` and per-network
`scan_ssid=0`; it remains merge-only. The active WPA instance has no control
socket, and creating one requires a controlled disruptive migration. Keep the
live WPA and DHCP owners until that migration and the isolated integration,
packet-gate/OpenSnitch renewal and exact-profile checks are complete.

The installed, reproducibly patched openresolv dependency adds PID-namespace
lock compatibility. It has not taken ownership of live DNS or changed subscriber
configuration. See [RESOLVER-LOCKING.md](RESOLVER-LOCKING.md) and
[LEASE-OWNER.md](LEASE-OWNER.md) for the validated component contracts.

The historical one-shot Controller helpers remain only for their regression
checks; production CLI routing no longer calls them. Earlier component evidence
retains the exact source hashes exercised then. Follow
[NETWORK-MIGRATION.md](NETWORK-MIGRATION.md) for remaining work and adapt
[INSTALL-PLAN.md](INSTALL-PLAN.md) before activation; it predates owner integration.
