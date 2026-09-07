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

## Staged controller behavior

`privacyctl` uses the wpa_supplicant Unix datagram control protocol directly;
ordinary mutating commands require the literal `OK` reply. `off` blocks and then
verifies both radio classes through `/sys/class/rfkill`. `scan` disables saved
networks while blocked, requests a numeric ID with `SCAN use_id=1`, requires an
exactly matching `CTRL-EVENT-SCAN-RESULTS id=...`, and
re-blocks both radios on every error. `connect` selects the permitted saved ID
while blocked, verifies its exact SSID, requires the completed ID and SSID,
clears stale routes, runs DHCP, and then records a supervised session. It is
the only command that leaves Wi-Fi unblocked, and
it accepts only `shmecklebucket` or the separately enabled `iphone-hotspot`
profile.  It does not read, print, save, or edit a PSK.

The OpenRC supervisor polls the control socket against the saved trusted
identity. A disconnect, wrong identity, or wpa_supplicant control failure
removes the session and blocks both radios. Successful association deliberately
leaves Wi-Fi enabled while the trusted association stays healthy, or until an
explicit `privacyctl off`; there is no session TTL.

Each supervisor check takes the radio lock without waiting. It skips an active
scan/connect command, whose lock covers the complete authorized transition.
Missing, malformed, or unreadable session state fails off once that command
finishes. Session cleanup errors still trigger radio blocking. The controller
creates its runtime directory privately and refuses symlinked, shared, or
wrong-owner directories; these behaviors are covered by isolated tests.
During a healthy trusted Wi-Fi session it also checks Bluetooth and re-blocks
that radio without disconnecting Wi-Fi. If the Bluetooth block cannot be
verified, the controller fails the session off and attempts to block both.

The installed `72-privacy-rfkill.rules` removes direct user write access to
`/dev/rfkill` while preserving read access for Waybar and other status displays.
Its ordering is deliberate: installed `70-uaccess.rules` adds the `uaccess`
tag, then `73-seat-late.rules` queues elogind's ACL grant. Removing the tag
between those files prevents that grant; placing the override after `73`
would be too late. eudev 3.2.14 supports this tag-removal operation in its
[rule evaluator](https://github.com/eudev-project/eudev/blob/v3.2.14/src/udev/udev-rules.c).
Existing ACLs need separate revocation during activation; the installed helper
completed that step on this host. Rebuild instructions retain the same checks.

The root policy file maps a controller profile to an existing numeric
wpa_supplicant network ID and its exact SSID.  Before connecting, the
controller queries the control protocol `LIST_NETWORKS` command and rejects an ID whose configured
SSID differs from the root policy.  `shmecklebucket` must be exactly spelled
that way.  The local iPhone hotspot has deliberately not been named or enabled:
the owner must add its exact spelling and separately uncomment its exact doas
rule.

The `status --json` contract is suitable for a small GUI:

```json
{"wifi":{"interface":"wlan0","soft_blocked":true,"hard_blocked":false,"wpa_state":"UNAVAILABLE"},"bluetooth":{"soft_blocked":true,"hard_blocked":false}}
```

`soft_blocked` and `hard_blocked` are independent JSON booleans, or `null` when
the corresponding state cannot be determined. This example shows software
blocks without hardware blocks; it is not a claim about the live host.
`status` does not query WPA, so `wpa_state` is always `UNAVAILABLE`. It
intentionally omits the associated SSID and all credential material.

One active transaction has a 45-second timer. Failure cleanup runs afterward
with that timer disarmed and each command still bounded; 45 seconds is not a
total wall-clock limit. Waiting for the radio lock has a separate 60-second
limit. WPA requests, including ATTACH, allow 3 seconds beginning before send;
ordinary commands allow 5 seconds and DHCP allows 20 seconds. Timed-out command
groups, including ordinary DHCP hook children, are terminated before fail-off.

WPA events received before their command reply are retained in a bounded queue.
Before scanning, already buffered events are drained; native scan-ID matching
also rejects older completions still in flight. Real datagram tests cover both
orders, mismatched IDs, malformed replies and event-flood limits. Protocol
semantics were checked against the official FreeBSD vendor import of WPA 2.11
and the installed Alpine binary's version and scan-ID strings. This verifies
the protocol path without requesting a live radio scan.

Full activation still needs the persistent radio owner and CLI integration. The live
`udhcpc` daemon remains running; the staged controller's one-shot `udhcpc -q`
cannot renew leases after it exits. Resolve ownership and test renewal before
enabling controller-managed networking. Exact trusted profile identities and a
working root-only WPA control socket also remain activation prerequisites.
The staged controller's isolated deadline, protocol and soft/hard state checks
are recorded in [controller-verification.json](controller-verification.json).
The staged lease parser, persistent client manager, bounded event hook and
owned network applier now have isolated tests, including real DHCP acquisition,
renewal and native address/route/DNS cleanup. They remain
separate from this legacy CLI, whose one-shot path must not be activated.
See [LEASE-OWNER.md](LEASE-OWNER.md) for the component contracts and
[NETWORK-MIGRATION.md](NETWORK-MIGRATION.md) for remaining WLAN migration and
recovery work. The installed, reproducibly patched openresolv dependency adds
PID-namespace lock compatibility; it has not taken ownership of the live
resolver file or changed its subscriber configuration. See
[RESOLVER-LOCKING.md](RESOLVER-LOCKING.md) for the compatibility contract.

`root/etc/wpa_supplicant/privacy-policy.conf` is a merge-only policy fragment.
It uses the documented `passive_scan=1` and `p2p_disabled=1` global options;
each permitted network should use `scan_ssid=0`.  It is not included
automatically because the active root-only wpa_supplicant configuration and
its include behavior were intentionally left untouched.

Follow [INSTALL-PLAN.md](INSTALL-PLAN.md) only from a local console with the
recovery path checked.  The plan deliberately leaves the pending boot-off vs
automatic-connect decision at boot-off.
