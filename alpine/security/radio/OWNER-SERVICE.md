# Persistent radio owner service

The inert `mbp-intel-radio-runtime=0.1.0-r0` APK is installed, providing the CLI,
fourteen Python modules and two private DHCP helpers. Its one-package transaction
preserved all nine compared host-network sections and the same WPA/DHCP process
identities. See the [runtime package instructions](../../packages/privacyctl-runtime/README.md).
The supervisor is not running, and the live WPA, DHCP and resolver owners have
not been replaced. Profiles, exact doas grants, OpenRC services, the sleep hook
and resolver policy remain unactivated. Exact trusted SSIDs, controlled migration,
live policy decisions and reboot/suspend checks remain activation requirements.

## Commands and lifetime

`privacyctl supervise` runs an owner with a separate guardian. `connect PROFILE`
and `scan` submit root-only, bounded requests to `/run/privacyctl/owner.sock`.
They never fall back to the old direct-control code. `status [--json]` preserves
the existing read-only rfkill output and does not require the owner socket.

The owner starts blocked and clears stale session authorization before handling
requests. It checks the saved network's exact ID and SSID before unblocking,
then keeps one foreground DHCP client throughout successful renewals. A lease
is acknowledged only after native application and a second WPA identity check.
The successful CLI response commits the connection; later CLI exit does not
end it. A disconnected caller cancels an unfinished request.

`off`, failed association, lost WPA identity, lease failure or expiry first
invalidate authorization and block radios. Only then may client termination
and owned network cleanup run. Cleanup errors retain the handles and ownership
record; a replacement connection cannot bypass them. Idle checks reassert
blocking once per second. Healthy sessions have no arbitrary expiry timer.

## Cancellation barrier

Each scan/connect request carries the off-fence captured by the privileged CLI
before submission. Both ordinary and emergency off atomically change that
fence. A delayed older request cannot reactivate the radio afterward.

WPA send/receive waits and native lease application call cooperative checkpoints
at approximately 25 ms intervals. Those checkpoints ingest requests and lease
failures; they block on cancellation without recursively applying or removing
network state. Cleanup runs after those callbacks unwind, with cancellation
disabled and its own bounded deadline. Existing command/application deadlines
still bound each phase.

If owner IPC fails or off waits five seconds, the CLI publishes an emergency
fence and attempts blocking directly. Fence publication precedes a two-second
wait for the lock shared with unblock; it publishes again under that lock.
Failure still attempts both radio blocks and returns an error. A failed fence
write can never be reported as successful off.

## Process death and recovery

The guardian watches the owner through a pidfd and blocks before releasing its
lifetime lock. Owner parent-death SIGTERM requests shutdown if the guardian is
killed. During normal shutdown, the guardian blocks before asking the owner to
clean up. Separate process tests exercise both deaths and competing guardians.
The guardian resets inherited SIGCHLD handling before forking, preserving the
unreaped-child guarantee required by [Linux pidfd_open](https://man7.org/linux/man-pages/man2/pidfd_open.2.html).
Parent identity is checked after installing the
[parent-death signal](https://man7.org/linux/man-pages/man2/PR_SET_PDEATHSIG.2const.html).
These mechanisms do not guarantee silence if both processes are killed at once
or the kernel cannot execute the blocking operation.

When started, the installed runtime takes the guardian, owner and DHCP lifetime locks in that
order before exposing IPC readiness. `NativeAdapter.prepare_recovery()`
invalidates the request fence, verifies radio blocking and recovers the fixed
`/var/lib/privacyctl/lease.json` under a 16-second startup recovery deadline. One
`RecoveryJournal` is shared by native commands, lease application and DHCP.
Every native command and DHCP init is durably registered before its execution
gate opens; its slot is cleared only after authenticated init death.

The journal retains conservative address/route/DNS candidates and exact prior
alias bytes. Same-boot recovery drains recorded writers using pidfds, validates
the interface/index/cookie, removes only exact owned resources, repairs managed
resolver output from current providers, and restores the prior alias. It then
commits clean and removes the matching `lease-dirty` marker and journal. Recovery
does not reconnect or adopt an expired lease. Uncertain writes and failed
cleanup retain evidence and route retries through recovery. A failed DHCP stop
prevents lease cleanup; its explicit lifetime lock remains held until successful
`close()`.

Unknown markers, malformed records, changed same-boot namespace/link identities and
unproved writer death refuse replacement. A marker by itself never grants
permission to delete addresses or resolver providers. Different-boot DNS retirement
is implemented separately in the inert runtime; reboot never authorizes silently discarding the persistent
journal. See [DIFFERENT-BOOT-RECOVERY.md](DIFFERENT-BOOT-RECOVERY.md) for its DNS-only
transition and [ORPHAN-RECOVERY.md](ORPHAN-RECOVERY.md) for the same-boot protocol
and pending native acceptance. Do not delete ownership evidence merely to make
a connection succeed.

## Private IPv6 configuration

`/etc/privacyctl/ipv6.json` must be root-owned mode 0600 or 0400 and explicitly
contain the selected profile. Missing settings are rejected before unblock.
The format below uses documentation addresses, never actual home settings:

```json
{"version":1,"profiles":{
  "shmecklebucket":{"addresses":["2001:db8:1::17/64"],"routers":["fe80::1"]},
  "iphone-hotspot":{"addresses":[],"routers":[]}
}}
```

The existing exact-SSID allowlist remains separate. Static IPv6 ownership does
not configure RA/SLAAC policy or remove legacy provisioning. Those decisions
must be made explicitly during the controlled migration.

See [LEASE-OWNER.md](LEASE-OWNER.md), [NETWORK-MIGRATION.md](NETWORK-MIGRATION.md)
and [owner-verification.json](owner-verification.json) for the separate component and native
integration scopes. No isolated fixture substitutes for a live radio, WPA,
firewall or boot acceptance check.

## Reproduce combined checks

From the checkout, use new output directories for each run:

```sh
doas python3 -B -m unittest discover -s alpine/security/radio/tests -v
python3 alpine/security/radio/tests/verify_radio_owner.py --output /tmp/radio-owner-proof
```

The combined fixture runs the production CLI, IPC, owner, DHCP client and native
lease applier in private namespaces. It substitutes a Unix-datagram WPA server
and virtual-interface radio state. Its 32-second lease allows native renewal;
the separate 16-second manager fixture still checks independent expiry.
During server silence, either authenticated deconfiguration or manager expiry
ends authorization; the evidence records which occurred first.

The historical combined run recorded at 2026-09-07T16:39:26Z passed seven cases:
same-client renewal, ordinary off, stale request rejection, exact scan
completion, home/hotspot IPv6 restoration, NAK
and server silence. Host-state comparisons matched and no test processes
survived. A separate seven-case fault fixture, recorded at 2026-09-07T17:10:27Z,
ran the production guardian with the same CLI, owner, DHCP and native applier.
It verified cancellation
during an unanswered WPA request and a paused native command, requesting-client
and DHCP-hook death, competing guardian refusal, and reciprocal guardian/owner
death. Blocking preceded native-command and DHCP teardown. Host-state checks
matched and no private processes survived. See
[fault-verification.json](fault-verification.json) for exact reasons, source
hashes and the preserved earlier reporting failure.

Those historical records preserve the dates and exact source hashes tested
before durable orphan recovery was integrated. Their owner-death result was
marker retention and replacement refusal; it is not a native recovery result
for the current source. The source-stable non-root discovery in
[checkpoint-verification.json](checkpoint-verification.json) passed 270 tests
and skipped 95 root-only cases. It is not root or native recovery evidence.
The separate native run 07 passed nine cases in 118.3246 seconds with 50 ms
injected per journal write. It verified owner-crash recovery and repeated clean
startup, prior-alias restoration, unrelated-provider preservation, and a fresh
explicit connect/off after recovery. All recorded host comparisons matched;
no fixture namespace members survived and source hashes stayed unchanged. See
[orphan-integration-verification.json](orphan-integration-verification.json).
This fixture uses private namespaces, a tmpfs journal and guarded WPA/radio
substitutes. Its old init completed before replacement startup, so draining a
surviving writer from a new observer remains unproved. Different-boot recovery,
actual OpenRC startup, physical radios and live migration remain separate.

The separate [packet-policy fixture](../firewall/radio-policy-verification.json)
now verifies DHCP renewal, exact IPv4 DNS rules, IPv6 neighbor discovery and
fresh DNS denial after daemon death. It preserves existing live rules and does
not replace the owner or OpenRC integration proof.

The veth interface exercises actual IPv6 duplicate-address detection. The
earlier dummy-interface applier checks bypassed DAD because Linux treats
NOARP interfaces specially ([kernel source](https://github.com/torvalds/linux/blob/v6.18/net/ipv6/addrconf.c#L406)).
The current staged application cap is ten seconds, resource removal twelve,
and hook acknowledgment twelve in both client and manager. Manager and launcher
readiness remain five seconds. Normal alias finish has three seconds;
startup and uncertain-cleanup recovery have sixteen. The guardian's owner
shutdown grace is twenty-five seconds, followed by a three-second death wait
after KILL. Staged OpenRC explicitly uses `retry='TERM/35/KILL/5'`; no service
activation or OpenRC lifecycle proof is implied by that setting.

Lease expiry, twenty-second acquisition, cancellation and late-ACK rejection
remain unchanged. Native runs 01–06 remain preserved failures, including the
old four-second apply cap in 03/04 and the unchanged 0.75-second native command
cap under load in 06. Run 02 also retains an unexplained pre-existing DHCP-client
inventory delta; it is not labeled host-unchanged. Run 07 passed with the revised
limits and injected delay. Maximum apply was 9.0522 seconds, live removal
6.6911, recovered removal 7.8271 and startup recovery 8.1318. The dual-stack
fixture has K=6 address/route selectors. Successful completion for the maximum
accepted K=22 is not guaranteed.

Root-owned disk journal measurements were 38 ms median, 50 ms p95 and 70 ms
maximum per measured fsync. Full integrated execution against a real persistent
disk remains unproved. These measurements and cooperative deadlines do not
establish a worst-case bound for synchronous I/O or an overloaded host.
